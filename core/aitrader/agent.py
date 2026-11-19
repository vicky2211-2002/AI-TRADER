"""The trading agent: a tool-calling loop with hard guardrails.

Design rules:
  * the model can read market data, skills, MCP tools and propose orders
  * the model can NOT bypass the risk gate or place live orders silently
  * every proposed order becomes an approval card in the UI
  * every tool call is written to the audit log
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from . import market, trading
from .db import get_db, new_id, now
from .mcp_client import MCPManager, content_to_text
from .providers import ProviderError, chat
from .security import decrypt, decrypt_json
from .skills import enabled_skills, read_skill

MAX_STEPS = 6
DANGEROUS = re.compile(
    r"(write|delete|remove|create|update|trade|order|transfer|withdraw|send|post|exec|run|"
    r"click|type|fill|upload|move|rename|kill|install|deploy)",
    re.I,
)

EventFn = Callable[[dict], Awaitable[None]]


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


BUILTIN_TOOLS = [
    _fn("get_quote", "Get the latest price for a symbol (EURUSD, XAUUSD, BTCUSD, US30, AAPL...).",
        {"symbol": {"type": "string"}}, ["symbol"]),
    _fn("get_quotes", "Get latest prices for several symbols at once.",
        {"symbols": {"type": "array", "items": {"type": "string"}}}, ["symbols"]),
    _fn("technical_analysis", "Compute SMA20/50/200, RSI14, ATR14 and trend for a symbol from OHLC candles.",
        {"symbol": {"type": "string"},
         "interval": {"type": "string", "description": "15m, 1h, 4h, 1d", "default": "1h"}},
        ["symbol"]),
    _fn("get_account", "Read broker balance, equity and trade mode for a connected account.",
        {"account_id": {"type": "string"}}, []),
    _fn("get_positions", "List open positions for a connected account.",
        {"account_id": {"type": "string"}}, []),
    _fn("get_recent_orders", "List the most recent order tickets and their status.", {"limit": {"type": "integer"}}, []),
    _fn("list_skills", "List the trading skills/playbooks available in this workspace.", {}, []),
    _fn("read_skill", "Read the full Markdown playbook of a skill before applying it.",
        {"skill_id": {"type": "string"}}, ["skill_id"]),
    _fn("get_news", "Recent news headlines for a symbol or topic.",
        {"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
    _fn("web_search", "Search the web for current market context (DuckDuckGo, no API key).",
        {"query": {"type": "string"}}, ["query"]),
    _fn("fetch_url", "Fetch a public web page and return readable text.",
        {"url": {"type": "string"}}, ["url"]),
    _fn("place_order", "PROPOSE an order. It passes the hard risk gate, then waits for the user's approval in the UI. Never claim it executed.",
        {"symbol": {"type": "string"}, "side": {"type": "string", "enum": ["BUY", "SELL"]},
         "volume": {"type": "number"}, "sl": {"type": "number"}, "tp": {"type": "number"},
         "reason": {"type": "string"}},
        ["symbol", "side", "volume", "sl"]),
    _fn("close_position", "PROPOSE closing an open position by ticket. Requires user approval.",
        {"ticket": {"type": "string"}, "account_id": {"type": "string"}, "symbol": {"type": "string"}},
        ["ticket"]),
    _fn("journal_note", "Append a short note to the local trading journal.",
        {"note": {"type": "string"}}, ["note"]),
]


# ---------------------------------------------------------------------------
# Built-in tool execution
# ---------------------------------------------------------------------------
def _ssrf_ok(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http/https URLs are allowed"
    host = parsed.hostname or ""
    if not host:
        return False, "Missing host"
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Local addresses are blocked"
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False, "Private network addresses are blocked"
    except Exception:
        pass
    return True, ""


def _strip_html(html: str, limit: int = 12000) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return round(100 - (100 / (1 + rs)), 2)


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    trs = []
    for i in range(-period, 0):
        h, l = candles[i]["h"], candles[i]["l"]
        prev = candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    return round(sum(trs) / period, 6)


async def _news(query: str, limit: int = 8) -> dict:
    import xml.etree.ElementTree as ET

    url = "https://news.google.com/rss/search"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(
                url,
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                headers={"User-Agent": "Mozilla/5.0 AI-TRADER"},
            )
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = []
            for item in root.iter("item"):
                items.append(
                    {
                        "title": (item.findtext("title") or "").strip(),
                        "published": (item.findtext("pubDate") or "").strip(),
                        "link": (item.findtext("link") or "").strip(),
                    }
                )
                if len(items) >= limit:
                    break
            return {"query": query, "headlines": items}
    except Exception as exc:
        return {"query": query, "error": str(exc)[:300]}


async def _search(query: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            if r.status_code >= 400:
                return {"query": query, "error": f"HTTP {r.status_code}"}
            results = []
            for m in re.finditer(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S
            ):
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                results.append({"title": title, "url": m.group(1)})
                if len(results) >= 8:
                    break
            return {"query": query, "results": results}
    except Exception as exc:
        return {"query": query, "error": str(exc)[:300]}


async def execute_builtin(name: str, args: dict, account_id: str | None) -> dict:
    if name == "get_quote":
        return await market.get_quote(args["symbol"])
    if name == "get_quotes":
        return {"quotes": await market.get_quotes([str(s) for s in args.get("symbols", [])][:12])}
    if name == "technical_analysis":
        symbol = args["symbol"]
        interval = args.get("interval", "1h")
        candles = await market.get_candles(symbol, interval, "3mo" if interval in ("1h", "4h") else "1y")
        if not candles:
            return {"error": f"No candles for {symbol}"}
        closes = [float(c["c"]) for c in candles]
        price = closes[-1]
        sma20, sma50, sma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
        trend = "range"
        if sma20 and sma50:
            trend = "up" if price > sma20 > sma50 else ("down" if price < sma20 < sma50 else "range")
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "price": price,
            "sma20": round(sma20, 6) if sma20 else None,
            "sma50": round(sma50, 6) if sma50 else None,
            "sma200": round(sma200, 6) if sma200 else None,
            "rsi14": _rsi(closes),
            "atr14": _atr(candles),
            "trend": trend,
            "candles": len(candles),
            "last_5_closes": [round(c, 6) for c in closes[-5:]],
        }
    if name == "get_account":
        row = trading.account_row(args.get("account_id") or account_id)
        return await trading.snapshot(row)
    if name == "get_positions":
        row = trading.account_row(args.get("account_id") or account_id)
        return {"positions": await trading.positions(row)}
    if name == "get_recent_orders":
        return {"orders": trading.recent_orders(int(args.get("limit") or 10))}
    if name == "list_skills":
        return {"skills": [{"id": s["id"], "name": s["name"], "description": s["description"]}
                           for s in enabled_skills()]}
    if name == "read_skill":
        text = read_skill(args["skill_id"])
        return {"skill": args["skill_id"], "content": text[:12000]}
    if name == "get_news":
        return await _news(args["query"], int(args.get("limit") or 8))
    if name == "web_search":
        return await _search(args["query"])
    if name == "fetch_url":
        url = args["url"]
        ok, why = _ssrf_ok(url)
        if not ok:
            return {"error": why}
        try:
            async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 AI-TRADER"})
                return {"url": url, "status": r.status_code, "text": _strip_html(r.text)}
        except Exception as exc:
            return {"error": str(exc)[:300]}
    if name == "place_order":
        result = await trading.propose(
            {
                "account_id": account_id,
                "symbol": args.get("symbol"),
                "side": args.get("side"),
                "volume": args.get("volume"),
                "sl": args.get("sl"),
                "tp": args.get("tp"),
                "reason": args.get("reason") or "agent proposal",
            },
            source="agent",
        )
        if result["status"] == "pending_approval":
            db = get_db()
            db.execute(
                "INSERT INTO approvals(id,kind,payload_json,status,created_at) VALUES(?,?,?,?,?)",
                (new_id("apr_"), "order", json.dumps({"order_id": result["order_id"]}, default=str),
                 "pending", now()),
            )
        return result
    if name == "close_position":
        db = get_db()
        approval_id = new_id("apr_")
        db.execute(
            "INSERT INTO approvals(id,kind,payload_json,status,created_at) VALUES(?,?,?,?,?)",
            (approval_id, "close_position",
             json.dumps({"ticket": args["ticket"], "account_id": args.get("account_id") or account_id,
                         "symbol": args.get("symbol")}), "pending", now()),
        )
        return {"status": "pending_approval", "approval_id": approval_id,
                "message": "Close request queued. Ask the user to approve it in the Approvals panel."}
    if name == "journal_note":
        from .config import HOME_DIR

        path = HOME_DIR / "journal.md"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {stamp}\n{args.get('note','')}\n")
        return {"ok": True, "path": str(path)}
    return {"error": f"Unknown tool '{name}'"}


# ---------------------------------------------------------------------------
# MCP tool bridging
# ---------------------------------------------------------------------------
def mcp_tool_specs(manager: MCPManager) -> tuple[list[dict], dict[str, tuple[dict, dict]]]:
    db = get_db()
    rows = db.query("SELECT * FROM mcp_servers WHERE enabled=1")
    specs: list[dict] = []
    mapping: dict[str, tuple[dict, dict]] = {}
    for row in rows:
        if not manager.is_running(row["id"]):
            continue
        client = manager.get(row["id"])
        if not client:
            continue
        for tool in getattr(client, "tools", []) or []:
            safe_server = re.sub(r"[^a-zA-Z0-9_]", "_", row["name"])[:20]
            safe_tool = re.sub(r"[^a-zA-Z0-9_]", "_", tool["name"])[:36]
            exposed = f"mcp_{safe_server}_{safe_tool}"[:63]
            specs.append(
                _fn(
                    exposed,
                    f"[{row['name']}] {tool.get('description') or tool['name']}"[:1000],
                    (tool.get("input_schema") or {}).get("properties", {}),
                    (tool.get("input_schema") or {}).get("required", []),
                )
            )
            mapping[exposed] = (row, tool)
    return specs, mapping


async def call_mcp(manager: MCPManager, row: dict, tool: str, args: dict) -> dict:
    result = await asyncio.to_thread(manager.call, row, tool, args)
    return {"text": content_to_text(result)[:8000], "raw": result}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
def build_system_prompt(settings: dict, account: dict | None) -> str:
    skills = enabled_skills()
    skill_lines = "\n".join(f"- {s['id']}: {s['description']}" for s in skills) or "- (none enabled)"
    acct_lines = "not connected"
    if account:
        acct_lines = (
            f"{account.get('broker')} | {account.get('trade_mode')} | "
            f"balance {account.get('balance')} {account.get('currency','')} | equity {account.get('equity')}"
        )
    return f"""You are AI-TRADER, a disciplined trading copilot running locally on the user's machine.

CURRENT TIME (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}
ACCOUNT: {acct_lines}
MODE: {settings.get('trading_mode')} | live allowed: {settings.get('allow_live_trading')} | kill switch: {settings.get('kill_switch')}
RISK LIMITS: {settings.get('max_risk_per_trade_pct')}% per trade, {settings.get('max_daily_loss_pct')}% daily loss,
max {settings.get('max_open_positions')} positions, max lot {settings.get('max_lot_size')}.

AVAILABLE SKILLS (read one with read_skill before using it):
{skill_lines}

RULES
1. Analyse first, trade second. Use get_quote / technical_analysis / get_news and the relevant skill.
2. Never invent prices, news, fills or account numbers. If a tool fails, say so.
3. place_order only *proposes* an order. It always goes through a hard risk gate and requires the
   user's explicit approval. Never claim an order was filled.
4. Always include a stop loss that is on the correct side of price, and size from the risk budget.
5. If the market is unclear, say "no trade" and explain what would change your mind.
6. You are not a financial adviser. Do not promise profit. Reference the user's own risk limits.
7. Keep answers tight: thesis, levels (entry / SL / TP), risk in $ and %, invalidation.
8. Use tables sparingly and Markdown for structure.
"""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def run_turn(
    *,
    provider: dict,
    api_key: str,
    history: list[dict],
    user_text: str,
    account_id: str | None,
    manager: MCPManager,
    mode: str = "analyse",
    on_event: EventFn | None = None,
) -> dict:
    db = get_db()
    settings = db.all_settings()
    account = None
    try:
        row = trading.account_row(account_id)
        account = await trading.snapshot(row)
        account["broker"] = row.get("broker")
    except Exception:
        account = None

    mcp_specs, mcp_map = mcp_tool_specs(manager)
    tools = BUILTIN_TOOLS + mcp_specs
    system = build_system_prompt(settings, account)
    if mode == "trade":
        system += "\nThe user asked for a trade idea. Produce a concrete, risk-sized proposal or an explicit no-trade."

    messages: list[dict] = []
    for m in history[-24:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})

    trace: list[dict] = []

    async def emit(event: dict) -> None:
        if on_event:
            await on_event(event)

    for step in range(MAX_STEPS):
        try:
            result = await chat(
                kind=provider.get("kind", "openai"),
                base_url=provider.get("base_url", ""),
                api_key=api_key,
                model=provider.get("model", ""),
                messages=messages,
                system=system,
                tools=tools,
                temperature=0.25,
                max_tokens=1800,
            )
        except ProviderError as exc:
            await emit({"type": "error", "message": str(exc), "status": exc.status})
            return {"text": f"Provider error: {exc}", "trace": trace, "error": True}

        calls = result.get("tool_calls") or []
        text = (result.get("text") or "").strip()
        if not calls:
            await emit({"type": "text", "text": text})
            return {"text": text, "trace": trace, "usage": result.get("usage")}

        assistant_msg: dict = {"role": "assistant", "content": text, "tool_calls": calls}
        messages.append(assistant_msg)
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "tool_start", "name": name, "args": args})
            db.audit("tool.call", json.dumps({"name": name, "args": args})[:2000], actor="agent")

            if name in mcp_map:
                server_row, tool = mcp_map[name]
                if not settings.get("auto_execute_tools", False) and DANGEROUS.search(tool["name"]):
                    approval_id = new_id("apr_")
                    db.execute(
                        "INSERT INTO approvals(id,kind,payload_json,status,created_at) VALUES(?,?,?,?,?)",
                        (approval_id, "mcp_tool",
                         json.dumps({"server_id": server_row["id"], "tool": tool["name"], "args": args}),
                         "pending", now()),
                    )
                    output = {"status": "pending_approval", "approval_id": approval_id,
                              "message": "This MCP tool can change external state and needs approval in the UI."}
                else:
                    try:
                        output = await call_mcp(manager, server_row, tool["name"], args)
                    except Exception as exc:
                        output = {"error": str(exc)[:500]}
            elif name in {t["function"]["name"] for t in BUILTIN_TOOLS}:
                try:
                    output = await execute_builtin(name, args, account_id)
                except Exception as exc:
                    output = {"error": str(exc)[:500]}
            else:
                output = {"error": f"Unknown tool '{name}'"}

            trace.append({"name": name, "args": args, "result": output})
            await emit({"type": "tool_result", "name": name, "result": output})
            payload = json.dumps(output, default=str)
            if len(payload) > 12000:
                payload = payload[:12000] + "...[truncated]"
            tool_msg = {"role": "tool", "tool_call_id": call.get("id", ""), "content": payload}
            if mcp_map.get(name):
                tool_msg["tool_name"] = mcp_map[name][1]["name"]
            messages.append(tool_msg)

    # Ran out of steps: ask for a concise wrap-up without tools.
    try:
        final = await chat(
            kind=provider.get("kind", "openai"),
            base_url=provider.get("base_url", ""),
            api_key=api_key,
            model=provider.get("model", ""),
            messages=messages + [{"role": "user", "content": "Summarise your findings and next step. No more tool calls."}],
            system=system,
            temperature=0.2,
            max_tokens=900,
        )
        text = (final.get("text") or "").strip()
    except ProviderError as exc:
        text = f"Provider error: {exc}"
    await emit({"type": "text", "text": text})
    return {"text": text, "trace": trace}


def save_turn(conversation_id: str, user_text: str, assistant_text: str, meta: dict) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO messages(id,conversation_id,role,content,meta_json,created_at) VALUES(?,?,?,?,?,?)",
        (new_id("msg_"), conversation_id, "user", user_text, "{}", now()),
    )
    db.execute(
        "INSERT INTO messages(id,conversation_id,role,content,meta_json,created_at) VALUES(?,?,?,?,?,?)",
        (new_id("msg_"), conversation_id, "assistant", assistant_text, json.dumps(meta, default=str)[:8000], now()),
    )
    db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), conversation_id))
