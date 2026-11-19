"""Autonomous trading loop.

The operator starts this once. Every cycle it:

1. reads the account and open positions,
2. enforces stops/targets on paper positions,
3. picks a rotating slice of the watchlist,
4. asks one or more configured models for a strict JSON BUY/SELL/HOLD vote,
5. aggregates the votes, sizes the trade from the risk budget,
6. sends it through the *same* hard risk gate as every other order,
7. writes the decision (reason, votes, status) to SQLite for the dashboard.

Safety rules baked in:
  * off by default; the operator presses Start,
  * live auto-execution needs both allow_live_trading and autopilot_allow_live_auto,
  * kill switch / daily loss / drawdown still block entries,
  * the model can never bypass `risk.evaluate_order`.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import statistics
import time
from datetime import datetime, timezone

from . import market, providers, trading
from .brokers import contract_size
from .db import get_db, new_id, now
from .security import decrypt

QUOTE_CACHE_HINT = 8.0

DECISION_SYSTEM = """You are one independent voting model inside AI-TRADER's autopilot.
You analyse ONE symbol and decide what to do over the next 1-4 hours.

Rules:
- Risk first. A missing or bad setup means HOLD.
- Never invent prices or news. Use only the JSON data supplied.
- If the trend and momentum disagree, prefer HOLD.
- A stop loss is mandatory for BUY or SELL.
- sl_atr / tp_atr are multiples of ATR14 (typical: 1.5-3.0 and 3.0-6.0).
- Do not promise profit.

Reply with exactly ONE JSON object and nothing else:
{"action":"BUY|SELL|HOLD","confidence":0.0,"reason":"<=240 chars","sl_atr":2.0,"tp_atr":4.0}

confidence is 0.0-1.0. Use <0.55 when the setup is marginal."""


# ---------------------------------------------------------------------------
# Small indicators (self-contained, no agent import)
# ---------------------------------------------------------------------------
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


def _price_decimals(price: float) -> int:
    if price < 10:
        return 5
    if price < 1000:
        return 3
    return 2


# ---------------------------------------------------------------------------
# Decision parsing / aggregation / sizing (pure, unit-tested)
# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_decision(text: str, default_sl: float = 2.0, default_tp: float = 4.0) -> dict | None:
    data = extract_json(text)
    if not data:
        return None
    action = str(data.get("action") or "").upper().strip()
    if action not in ("BUY", "SELL", "HOLD"):
        return None
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100 if confidence <= 100 else 1.0
    confidence = max(0.0, min(confidence, 1.0))
    try:
        sl_atr = float(data.get("sl_atr") or default_sl)
    except (TypeError, ValueError):
        sl_atr = default_sl
    try:
        tp_atr = float(data.get("tp_atr") or default_tp)
    except (TypeError, ValueError):
        tp_atr = default_tp
    return {
        "action": action,
        "confidence": round(confidence, 3),
        "reason": str(data.get("reason") or "")[:400],
        "sl_atr": max(0.5, min(sl_atr, 10.0)),
        "tp_atr": max(0.5, min(tp_atr, 20.0)),
    }


def aggregate_votes(votes: list[dict], threshold: float, default_sl: float, default_tp: float) -> dict:
    valid = [v for v in votes if v.get("ok") and v.get("action") in ("BUY", "SELL", "HOLD")]
    if not valid:
        errors = [str(v.get("error") or "").strip() for v in votes if str(v.get("error") or "").strip()]
        reason = "No model returned a valid decision."
        if errors:
            reason = f"{reason} First error: {errors[0][:200]}"
        return {
            "action": "HOLD", "confidence": 0.0, "sl_atr": default_sl, "tp_atr": default_tp,
            "reason": reason, "winners": 0, "voters": 0,
        }
    active = [v for v in valid if v["action"] in ("BUY", "SELL")]
    if not active:
        top = max(valid, key=lambda v: float(v.get("confidence") or 0))
        return {
            "action": "HOLD", "confidence": round(float(top.get("confidence") or 0), 3),
            "sl_atr": default_sl, "tp_atr": default_tp,
            "reason": top.get("reason") or "All models voted HOLD.",
            "winners": 0, "voters": len(valid),
        }

    buy = sum(float(v.get("confidence") or 0) for v in active if v["action"] == "BUY")
    sell = sum(float(v.get("confidence") or 0) for v in active if v["action"] == "SELL")
    if abs(buy - sell) < 1e-9:
        return {
            "action": "HOLD", "confidence": 0.0, "sl_atr": default_sl, "tp_atr": default_tp,
            "reason": f"Models split evenly ({len(active)} votes).", "winners": 0, "voters": len(valid),
        }

    side = "BUY" if buy > sell else "SELL"
    winners = [v for v in active if v["action"] == side]
    total_side = sum(float(v.get("confidence") or 0) for v in active)
    share = sum(float(v.get("confidence") or 0) for v in winners) / total_side if total_side else 0
    avg_conf = statistics.fmean(float(v.get("confidence") or 0) for v in winners) if winners else 0
    confidence = round(max(0.0, min(share * avg_conf, 1.0)), 3)

    sl_values = [float(v.get("sl_atr") or default_sl) for v in winners]
    tp_values = [float(v.get("tp_atr") or default_tp) for v in winners]
    sl_atr = round(statistics.fmean(sl_values), 2) if sl_values else default_sl
    tp_atr = round(statistics.fmean(tp_values), 2) if tp_values else default_tp
    lead = max(winners, key=lambda v: float(v.get("confidence") or 0))
    reason = lead.get("reason") or ""
    summary = f"{len(winners)}/{len(valid)} votes for {side}"
    if reason:
        summary = f"{summary}: {reason}"
    return {
        "action": side,
        "confidence": confidence,
        "sl_atr": max(0.5, min(sl_atr, 10.0)),
        "tp_atr": max(0.5, min(tp_atr, 20.0)),
        "reason": summary[:400],
        "winners": len(winners),
        "voters": len(valid),
        "meets_threshold": confidence >= threshold,
    }


def size_order(snapshot: dict, side: str, settings: dict, equity: float,
               sl_atr: float, tp_atr: float) -> dict | None:
    price = float(snapshot.get("price") or 0)
    atr = float(snapshot.get("atr14") or 0)
    if not price or atr <= 0 or equity <= 0:
        return None
    sl_dist = atr * sl_atr
    tp_dist = atr * tp_atr
    if sl_dist <= 0:
        return None
    sl = price - sl_dist if side == "BUY" else price + sl_dist
    tp = price + tp_dist if side == "BUY" else price - tp_dist
    risk_budget = equity * max(0.0, float(settings.get("max_risk_per_trade_pct", 1.0))) / 100
    size = contract_size(snapshot.get("symbol", ""))
    volume = risk_budget / (sl_dist * size)
    volume = math.floor(volume * 100) / 100
    cap = float(settings.get("max_lot_size", 0.1))
    volume = min(volume, cap)
    if volume < 0.01:
        return None
    decimals = _price_decimals(price)
    return {
        "volume": round(volume, 2),
        "sl": round(sl, decimals),
        "tp": round(tp, decimals),
        "entry": round(price, decimals),
        "risk_usd": round(abs(price - sl) * volume * size, 2),
        "sl_distance": round(sl_dist, decimals),
        "tp_distance": round(tp_dist, decimals),
    }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
def in_cooldown(cooldowns: dict, symbol: str, ts: float | None = None) -> bool:
    """True while a symbol is cooling down after its last entry."""
    until = float(cooldowns.get(symbol.upper()) or 0)
    return until > (time.time() if ts is None else ts)


def provider_ready(row: dict) -> bool:
    """A provider can be queried if it has a key or points at a local server."""
    if str(row.get("api_key_enc") or "").strip():
        return True
    url = str(row.get("base_url") or "").lower()
    return any(host in url for host in ("127.0.0.1", "localhost", "0.0.0.0", "::1"))


def record_decision(**fields) -> str:
    db = get_db()
    decision_id = fields.pop("id", None) or new_id("dec_")
    db.execute(
        "INSERT INTO decisions(id,ts,account_id,symbol,action,confidence,price,reason,model,status,"
        "order_id,risk_usd,pnl,votes_json,snapshot_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            decision_id,
            fields.get("ts") or now(),
            fields.get("account_id") or "",
            fields.get("symbol") or "",
            fields.get("action") or "HOLD",
            float(fields.get("confidence") or 0),
            float(fields.get("price") or 0),
            str(fields.get("reason") or "")[:2000],
            str(fields.get("model") or "")[:300],
            fields.get("status") or "",
            fields.get("order_id") or "",
            float(fields.get("risk_usd") or 0),
            float(fields.get("pnl") or 0),
            json.dumps(fields.get("votes") or [], default=str)[:12000],
            json.dumps(fields.get("snapshot") or {}, default=str)[:12000],
        ),
    )
    return decision_id


def recent_decisions(limit: int = 60) -> list[dict]:
    rows = get_db().query("SELECT * FROM decisions ORDER BY ts DESC LIMIT ?", (limit,))
    for row in rows:
        for key, fallback in (("votes", "[]"), ("snapshot", "{}")):
            try:
                row[key] = json.loads(row.get(f"{key}_json") or fallback)
            except json.JSONDecodeError:
                row[key] = json.loads(fallback)
        row.pop("votes_json", None)
        row.pop("snapshot_json", None)
    return rows


def _start_of_day() -> float:
    return time.time() - (time.time() % 86400)


def build_stats(account_id: str) -> dict:
    db = get_db()
    closed = db.query(
        "SELECT symbol, side, volume, pnl, opened_at, closed_at FROM positions "
        "WHERE account_id=? AND status='closed'",
        (account_id,),
    )
    total = sum(float(r.get("pnl") or 0) for r in closed)
    day_start = _start_of_day()
    today = sum(float(r.get("pnl") or 0) for r in closed if float(r.get("closed_at") or 0) >= day_start)
    wins = [float(r["pnl"]) for r in closed if float(r.get("pnl") or 0) > 0]
    losses = [float(r["pnl"]) for r in closed if float(r.get("pnl") or 0) < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    decided = db.query(
        "SELECT COUNT(*) AS n FROM decisions WHERE ts>=? AND account_id=? "
        "AND status IN ('executed','pending_approval') AND action IN ('BUY','SELL')",
        (day_start, account_id),
    )
    return {
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / (len(wins) + len(losses)) * 100, 1) if (wins or losses) else 0.0,
        "total_pnl": round(total, 2),
        "today_pnl": round(today, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0.0),
        "trades_today": int(decided[0]["n"] if decided else 0),
    }


# ---------------------------------------------------------------------------
# Market context
# ---------------------------------------------------------------------------
async def market_snapshot(symbol: str) -> dict:
    quote = await market.get_quote(symbol)
    candles = await market.get_candles(symbol, "1h", "1mo")
    out: dict = {
        "symbol": symbol.upper(),
        "price": float(quote.get("price") or 0),
        "change_pct": quote.get("change_pct"),
        "source": quote.get("source"),
        "ts": quote.get("ts"),
        "stale": bool(quote.get("stale")),
    }
    if candles:
        closes = [float(c["c"]) for c in candles]
        highs = [float(c["h"]) for c in candles]
        lows = [float(c["l"]) for c in candles]
        last_close = closes[-1]
        ref_price = out["price"] or last_close
        sma20, sma50, sma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
        trend = "range"
        if sma20 and sma50:
            trend = "up" if ref_price > sma20 > sma50 else ("down" if ref_price < sma20 < sma50 else "range")
        out.update(
            {
                "last_close": last_close,
                "sma20": round(sma20, 6) if sma20 else None,
                "sma50": round(sma50, 6) if sma50 else None,
                "sma200": round(sma200, 6) if sma200 else None,
                "rsi14": _rsi(closes),
                "atr14": _atr(candles),
                "trend": trend,
                "candles": len(candles),
                "last_10_closes": [round(c, 6) for c in closes[-10:]],
                "high_20": round(max(highs[-20:]), 6) if highs else None,
                "low_20": round(min(lows[-20:]), 6) if lows else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class AutopilotEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._busy = False
        self._cursor = 0
        self._cooldowns: dict[str, float] = {}
        self.state: dict = {
            "running": False,
            "stage": "stopped",
            "symbol": "",
            "cycle": 0,
            "started_at": 0.0,
            "last_cycle_at": 0.0,
            "next_run_at": 0.0,
            "last_error": "",
            "last_decision": None,
            "using_models": [],
            "halted_reason": "",
        }

    # -- lifecycle ---------------------------------------------------------
    def status(self) -> dict:
        return {**self.state, "cooldowns": {k: round(v, 1) for k, v in self._cooldowns.items()}}

    def start(self) -> dict:
        if self._task and not self._task.done():
            return self.status()
        db = get_db()
        self._stop = asyncio.Event()
        self.state.update(
            running=True, stage="starting", started_at=now(), next_run_at=0.0,
            last_error="", halted_reason="", symbol="",
        )
        db.set_setting("autopilot_enabled", True)
        db.audit("autopilot.started", "operator pressed start", actor="user")
        self._task = asyncio.create_task(self._run())
        return self.status()

    def stop(self, reason: str = "operator stopped", persist: bool = True) -> dict:
        self._stop.set()
        task = self._task
        self._task = None
        if task and not task.done():
            task.cancel()
        db = get_db()
        if persist:
            db.set_setting("autopilot_enabled", False)
        db.audit("autopilot.stopped", reason, actor="user" if persist else "system")
        self.state.update(running=False, stage="stopped", next_run_at=0.0, symbol="", halted_reason=reason)
        return self.status()

    async def run_once(self) -> dict:
        if self._busy:
            return {"ok": False, "error": "A cycle is already running."}
        if self.state.get("running"):
            return {"ok": False, "error": "Stop autopilot before running a single cycle."}
        self._busy = True
        try:
            await self._cycle()
            return {"ok": True, "state": self.status()}
        except Exception as exc:
            self.state.update(stage="error", last_error=str(exc)[:500])
            get_db().audit("autopilot.error", str(exc)[:1000])
            return {"ok": False, "error": str(exc)[:500]}
        finally:
            self._busy = False

    # -- loop --------------------------------------------------------------
    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self.state.update(cycle=int(self.state.get("cycle") or 0) + 1, last_cycle_at=now())
                try:
                    await self._cycle()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.state.update(stage="error", last_error=str(exc)[:500])
                    get_db().audit("autopilot.error", str(exc)[:1000])
                settings = get_db().all_settings()
                interval = max(60, min(int(settings.get("autopilot_interval_sec") or 300), 86400))
                self.state.update(stage="waiting", symbol="", next_run_at=now() + interval)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
        finally:
            self.state.update(running=False, next_run_at=0.0, stage="stopped")

    # -- one cycle ---------------------------------------------------------
    async def _cycle(self) -> None:
        db = get_db()
        settings = db.all_settings()
        if settings.get("kill_switch"):
            self.state.update(stage="halted", halted_reason="Kill switch is on.")
            db.audit("autopilot.halted", "kill switch", actor="autopilot")
            return
        self.state.update(stage="connecting", halted_reason="", last_error="")

        account = trading.account_row(settings.get("default_account_id") or None)
        acct = await trading.snapshot(account)
        if acct.get("ok") is False and account.get("broker") != "paper":
            raise RuntimeError(acct.get("error") or "Broker account is unavailable.")
        equity = float(acct.get("equity") or acct.get("balance") or 0)
        if equity > 0:
            db.execute(
                "INSERT INTO equity_points(ts,account_id,equity) VALUES(?,?,?)",
                (now(), account["id"], equity),
            )
            db.execute(
                "DELETE FROM equity_points WHERE id IN "
                "(SELECT id FROM equity_points ORDER BY id DESC LIMIT -1 OFFSET 2000)"
            )

        positions = await trading.positions(account)
        await self._manage_exits(account, positions, settings)
        positions = await trading.positions(account)

        if not self._entry_allowed(settings, positions, account):
            return

        symbols = resolve_symbols(settings)
        if not symbols:
            raise RuntimeError("No watchlist symbols configured.")
        per_cycle = max(1, min(int(settings.get("autopilot_symbols_per_cycle") or 2), len(symbols)))
        start = self._cursor % len(symbols)
        chosen = [symbols[(start + i) % len(symbols)] for i in range(per_cycle)]
        self._cursor = (start + per_cycle) % len(symbols)

        provider_rows = select_providers(settings)
        if not provider_rows:
            raise RuntimeError("No enabled model provider. Add or enable one in Models.")
        self.state["using_models"] = [f"{r['name']} · {r['model']}" for r in provider_rows]

        open_symbols = {str(p.get("symbol", "")).upper() for p in positions}
        for symbol in chosen:
            if self._stop.is_set():
                break
            if symbol in open_symbols:
                continue
            if in_cooldown(self._cooldowns, symbol):
                self.state.update(stage="waiting", halted_reason=f"{symbol} cooldown active.")
                continue
            self.state.update(stage="analysing", symbol=symbol, last_error="")
            try:
                snapshot = await market_snapshot(symbol)
            except Exception as exc:
                record_decision(
                    account_id=account["id"], symbol=symbol, action="HOLD", model="",
                    status="error", reason=f"Market data failed: {exc}"[:500],
                )
                self.state["last_error"] = f"{symbol}: {exc}"[:300]
                continue
            if snapshot.get("stale") or not snapshot.get("price"):
                record_decision(
                    account_id=account["id"], symbol=symbol, action="HOLD", status="error",
                    model="", price=snapshot.get("price") or 0,
                    reason="Stale or missing quote - skipping entry.", snapshot=snapshot,
                )
                continue

            self.state["stage"] = "asking models"
            votes = await ask_models(provider_rows, snapshot, settings, positions, acct)
            aggregate = aggregate_votes(
                votes,
                float(settings.get("autopilot_confidence") or 0.55),
                float(settings.get("autopilot_sl_atr") or 2.0),
                float(settings.get("autopilot_tp_atr") or 4.0),
            )
            model_label = ", ".join(v["model"] for v in votes if v.get("ok"))[:300]
            decision_common = {
                "account_id": account["id"],
                "symbol": symbol,
                "confidence": aggregate["confidence"],
                "price": snapshot.get("price") or 0,
                "model": model_label,
                "votes": votes,
                "snapshot": snapshot,
            }
            threshold = float(settings.get("autopilot_confidence") or 0.55)
            if aggregate["action"] == "HOLD" or aggregate["confidence"] < threshold:
                reason = aggregate["reason"]
                if aggregate["action"] != "HOLD":
                    reason = f"Below confidence gate ({aggregate['confidence']:.0%} < {threshold:.0%}). {reason}"
                record_decision(action="HOLD", status="held", reason=reason[:1000], **decision_common)
                self.state["last_decision"] = {
                    "symbol": symbol, "action": "HOLD", "confidence": aggregate["confidence"],
                    "status": "held", "reason": reason[:300], "ts": now(),
                }
                continue

            side = aggregate["action"]
            sizing = size_order(snapshot, side, settings, equity, aggregate["sl_atr"], aggregate["tp_atr"])
            if not sizing:
                record_decision(
                    action="HOLD", status="held", reason="Risk budget too small for the minimum lot.",
                    **decision_common,
                )
                continue

            self.state["stage"] = "executing"
            result = await trading.propose(
                {
                    "account_id": account["id"],
                    "symbol": symbol,
                    "side": side,
                    "volume": sizing["volume"],
                    "sl": sizing["sl"],
                    "tp": sizing["tp"],
                    "reason": f"Autopilot: {aggregate['reason']}",
                },
                source="autopilot",
                auto_execute=str(settings.get("autopilot_execution") or "auto") == "auto",
            )
            status = map_result_status(result)
            pnl = 0.0
            execution = result.get("execution") or {}
            if isinstance(execution, dict):
                pnl = float(execution.get("pnl") or 0)
            decision_id = record_decision(
                action=side,
                status=status,
                order_id=result.get("order_id") or "",
                risk_usd=result.get("risk_usd") or sizing["risk_usd"],
                reason=aggregate["reason"],
                pnl=pnl,
                **decision_common,
            )
            if status in ("executed", "pending_approval"):
                self._cooldowns[symbol] = now() + max(0, int(settings.get("autopilot_cooldown_sec") or 0))
            db.audit(
                "autopilot.decision",
                json.dumps({
                    "id": decision_id, "symbol": symbol, "action": side,
                    "confidence": aggregate["confidence"], "status": status,
                    "order_id": result.get("order_id"),
                }),
                actor="autopilot",
            )
            self.state["last_decision"] = {
                "symbol": symbol, "action": side, "confidence": aggregate["confidence"],
                "status": status, "reason": aggregate["reason"][:300], "ts": now(),
            }
            if status == "blocked":
                self.state["last_error"] = f"{symbol}: {', '.join(result.get('blocked_by') or [])}"[:300]

    async def _manage_exits(self, account: dict, positions: list[dict], settings: dict) -> None:
        if account.get("broker") != "paper":
            return
        self.state.update(stage="managing exits", symbol="")
        for pos in positions:
            symbol = str(pos.get("symbol") or "")
            try:
                quote = await market.get_quote(symbol)
            except Exception:
                continue
            price = float(quote.get("price") or 0)
            if not price:
                continue
            side = str(pos.get("side") or "").upper()
            sl = float(pos.get("sl") or 0)
            tp = float(pos.get("tp") or 0)
            reason = ""
            if side == "BUY":
                if sl and price <= sl:
                    reason = f"Stop loss hit at {price}"
                elif tp and price >= tp:
                    reason = f"Take profit hit at {price}"
            else:
                if sl and price >= sl:
                    reason = f"Stop loss hit at {price}"
                elif tp and price <= tp:
                    reason = f"Take profit hit at {price}"
            if not reason:
                continue
            result = await trading.close_position(account["id"], str(pos.get("ticket")), symbol)
            record_decision(
                account_id=account["id"], symbol=symbol, action="CLOSE",
                confidence=1.0, price=price, reason=reason,
                model="risk manager", status="executed" if result.get("ok") else "failed",
                pnl=float(result.get("pnl") or 0), snapshot={"quote": quote, "position": pos},
            )
            self.state["last_decision"] = {
                "symbol": symbol, "action": "CLOSE", "confidence": 1.0,
                "status": "executed" if result.get("ok") else "failed",
                "reason": reason, "ts": now(),
            }

    def _entry_allowed(self, settings: dict, positions: list[dict], account: dict) -> bool:
        db = get_db()
        max_open = int(settings.get("max_open_positions") or 2)
        if len(positions) >= max_open:
            self.state.update(stage="waiting", halted_reason=f"Max open positions ({len(positions)}/{max_open}).")
            return False
        cap = int(settings.get("autopilot_max_trades_per_day") or 6)
        row = db.one(
            "SELECT COUNT(*) AS n FROM decisions WHERE ts>=? AND account_id=? "
            "AND status IN ('executed','pending_approval') AND action IN ('BUY','SELL')",
            (_start_of_day(), account.get("id") or ""),
        )
        if row and int(row["n"]) >= cap:
            self.state.update(stage="waiting", halted_reason=f"Daily autopilot trade cap reached ({cap}).")
            return False
        self.state["halted_reason"] = ""
        return True


# ---------------------------------------------------------------------------
# Providers / prompt helpers
# ---------------------------------------------------------------------------
def resolve_symbols(settings: dict) -> list[str]:
    raw = settings.get("autopilot_symbols") or settings.get("default_symbols") or []
    out: list[str] = []
    for item in raw:
        symbol = str(item).upper().strip()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def select_providers(settings: dict) -> list[dict]:
    rows = get_db().query("SELECT * FROM providers WHERE enabled=1 ORDER BY is_default DESC, name")
    wanted = [str(x) for x in (settings.get("autopilot_provider_ids") or [])]
    if wanted:
        rows = [r for r in rows if r["id"] in wanted]
    else:
        ready = [r for r in rows if provider_ready(r)]
        rows = (ready or rows)[:1]
    return rows[:3]


async def ask_models(provider_rows: list[dict], snapshot: dict, settings: dict,
                     positions: list[dict], account: dict) -> list[dict]:
    context = {
        "now_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "market": snapshot,
        "account": {
            "broker": account.get("broker"),
            "balance": account.get("balance"),
            "equity": account.get("equity"),
            "floating_pnl": account.get("floating_pnl"),
            "currency": account.get("currency", "USD"),
        },
        "open_positions": [
            {k: p.get(k) for k in ("symbol", "side", "volume", "entry", "pnl")}
            for p in positions
        ],
        "risk": {
            "risk_per_trade_pct": settings.get("max_risk_per_trade_pct"),
            "max_open_positions": settings.get("max_open_positions"),
            "daily_loss_limit_pct": settings.get("max_daily_loss_pct"),
            "drawdown_limit_pct": settings.get("max_drawdown_pct"),
        },
        "recent_results": [
            {"symbol": r["symbol"], "pnl": r["pnl"], "side": r["side"]}
            for r in get_db().query(
                "SELECT symbol,side,pnl FROM positions WHERE status='closed' ORDER BY closed_at DESC LIMIT 5"
            )
        ],
    }
    user = json.dumps(context, default=str)
    votes = await asyncio.gather(
        *[_ask_one(row, user) for row in provider_rows], return_exceptions=False
    )
    return list(votes)


async def _ask_one(row: dict, user: str) -> dict:
    started = time.perf_counter()
    label = f"{row.get('name')} · {row.get('model')}"
    base = {
        "provider_id": row.get("id"),
        "name": row.get("name"),
        "model": label,
        "ok": False,
        "action": "HOLD",
        "confidence": 0.0,
        "reason": "",
        "sl_atr": 2.0,
        "tp_atr": 4.0,
        "latency_ms": 0,
        "error": "",
    }
    if not provider_ready(row):
        base["error"] = "No API key configured - add one in Models."
        return base
    try:
        result = await providers.chat(
            kind=row.get("kind", "openai"),
            base_url=row.get("base_url", ""),
            api_key=decrypt(row.get("api_key_enc") or ""),
            model=row.get("model", ""),
            messages=[{"role": "user", "content": user}],
            system=DECISION_SYSTEM,
            temperature=0.15,
            max_tokens=360,
            extra_headers=json.loads(row.get("headers_json") or "{}"),
            timeout=60,
        )
        parsed = parse_decision(result.get("text") or "")
        if not parsed:
            raise ValueError("model did not return valid decision JSON")
        base.update(parsed)
        base.update(ok=True, latency_ms=int((time.perf_counter() - started) * 1000))
    except Exception as exc:
        base.update(error=str(exc)[:300], latency_ms=int((time.perf_counter() - started) * 1000))
    return base


def map_result_status(result: dict) -> str:
    status = str(result.get("status") or "")
    if status == "approved":
        execution = result.get("execution") or {}
        return "executed" if execution.get("ok") else "failed"
    return status or "error"


# ---------------------------------------------------------------------------
# Dashboard payload
# ---------------------------------------------------------------------------
async def dashboard_payload() -> dict:
    db = get_db()
    settings = db.all_settings()
    try:
        account = trading.account_row(settings.get("default_account_id") or None)
        snapshot = await trading.snapshot(account)
        positions = await trading.positions(account)
    except Exception as exc:
        account = None
        snapshot = {"ok": False, "error": str(exc)[:300], "balance": 0, "equity": 0}
        positions = []

    account_id = account["id"] if account else ""
    equity = db.query(
        "SELECT ts,equity FROM equity_points WHERE account_id=? ORDER BY id DESC LIMIT 240",
        (account_id,),
    )
    equity.reverse()
    closed = db.query(
        "SELECT * FROM positions WHERE account_id=? AND status='closed' ORDER BY closed_at DESC LIMIT 30",
        (account_id,),
    )
    keys = (
        "autopilot_enabled", "autopilot_autostart", "autopilot_interval_sec",
        "autopilot_symbols", "autopilot_symbols_per_cycle", "autopilot_provider_ids",
        "autopilot_execution", "autopilot_confidence", "autopilot_max_trades_per_day",
        "autopilot_sl_atr", "autopilot_tp_atr", "autopilot_cooldown_sec",
        "autopilot_allow_live_auto", "default_account_id", "default_symbols",
        "kill_switch", "trading_mode", "allow_live_trading",
        "max_risk_per_trade_pct", "max_daily_loss_pct", "max_drawdown_pct",
        "max_open_positions", "max_lot_size",
    )
    return {
        "autopilot": engine.status(),
        "control": {k: settings.get(k) for k in keys},
        "account": {
            "id": account_id,
            "name": account.get("name") if account else "",
            "broker": account.get("broker") if account else "",
            "environment": account.get("environment") if account else "",
            "snapshot": snapshot,
        },
        "positions": positions,
        "stats": build_stats(account_id),
        "decisions": recent_decisions(60),
        "closed_positions": closed,
        "orders": trading.recent_orders(20),
        "equity": equity,
        "activity": db.query("SELECT ts,actor,action,detail FROM audit ORDER BY id DESC LIMIT 14"),
    }


engine = AutopilotEngine()
