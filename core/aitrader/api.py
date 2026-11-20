"""FastAPI app: the local AI-TRADER core.

Runs on 127.0.0.1:8765 by default. The Electron app, the Android build and the
browser UI all talk to this one API, so MT5 only needs to be installed on the
machine that hosts the core.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from . import agent as agent_mod
from . import autopilot as autopilot_mod
from . import market, trading
from .autopilot import engine as autopilot_engine
from .brokers import BROKER_CATALOG, BrokerError
from .config import (ALLOWED_ORIGINS, API_PREFIX, DATA_DIR, HOME_DIR, HOST, PORT,
                     PROJECT_DIR, SAFE_DEFAULTS, TOKEN)
from .db import get_db, new_id, now
from .mcp_client import MCPManager, MCPError, content_to_text
from .providers import ProviderError, list_models, test_provider
from .risk import evaluate_order, track_equity
from .security import decrypt, decrypt_json, encrypt, encrypt_json, mask, vault_backend
from .seed import seed_all
from .skills import (SKILLS_DIR, create_skill, delete_skill, read_skill,
                     skill_catalog, sync_skills, update_skill)
from .config import SEED_DIR

manager = MCPManager()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ProviderIn(BaseModel):
    name: str
    kind: str = "openai"
    base_url: str
    model: str
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    headers: dict = Field(default_factory=dict)
    enabled: bool = True
    is_default: bool = False
    clear_key: bool = False


class ProviderPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    headers: dict | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    clear_key: bool = False


class MCPIn(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict = Field(default_factory=dict)
    enabled: bool = True
    auto_start: bool = False
    category: str = "general"
    notes: str = ""


class AccountIn(BaseModel):
    name: str
    broker: str
    environment: str = "paper"
    config: dict = Field(default_factory=dict)
    secret: dict = Field(default_factory=dict)
    enabled: bool = True


class OrderIn(BaseModel):
    account_id: str | None = None
    symbol: str
    side: str
    volume: float
    sl: float = 0
    tp: float = 0
    order_type: str = "market"
    price: float = 0
    reason: str = ""
    environment: str | None = None


class ChatIn(BaseModel):
    message: str
    conversation_id: str | None = None
    provider_id: str | None = None
    account_id: str | None = None
    mode: str = "analyse"


class SkillIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    content: str = ""
    enabled: bool = True


class ConversationIn(BaseModel):
    title: str = "New chat"


class CloseIn(BaseModel):
    account_id: str | None = None
    symbol: str | None = None
    volume: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def provider_public(row: dict) -> dict:
    key = decrypt(row.get("api_key_enc") or "")
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "base_url": row["base_url"],
        "model": row["model"],
        "models": json.loads(row.get("models_json") or "[]"),
        "headers": json.loads(row.get("headers_json") or "{}"),
        "enabled": bool(row.get("enabled")),
        "is_default": bool(row.get("is_default")),
        "has_key": bool(key),
        "key_hint": mask(key),
        "last_status": row.get("last_status") or "",
        "last_latency_ms": row.get("last_latency_ms") or 0,
        "last_checked": row.get("last_checked") or 0,
    }


def mcp_public(row: dict) -> dict:
    client = manager.get(row["id"])
    running = bool(client and client.alive())
    tools = getattr(client, "tools", None) or json.loads(row.get("tools_json") or "[]")
    return {
        "id": row["id"],
        "name": row["name"],
        "transport": row["transport"],
        "command": row["command"],
        "args": json.loads(row.get("args_json") or "[]"),
        "url": row["url"],
        "env": {k: ("" if not v else mask(str(v))) for k, v in json.loads(row.get("env_json") or "{}").items()},
        "enabled": bool(row.get("enabled")),
        "auto_start": bool(row.get("auto_start")),
        "category": row.get("category") or "general",
        "notes": row.get("notes") or "",
        "status": "running" if running else (row.get("last_status") or "stopped"),
        "error": manager.error(row["id"]) or row.get("last_error") or "",
        "tool_count": len(tools),
        "tools": tools,
    }


def merge_secret_fields(existing: dict, incoming: dict) -> dict:
    """Merge UI input with stored secrets without letting masks overwrite them.

    The UI only ever receives masks, so a field that is blank or exactly equal
    to the mask of the stored value keeps whatever is already in the vault.
    """
    merged: dict[str, str] = {}
    for key, value in (incoming or {}).items():
        text = "" if value is None else str(value)
        old = str(existing.get(key) or "")
        if old and (not text or text == mask(old)):
            merged[key] = old
        else:
            merged[key] = text
    return merged


def account_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "broker": row["broker"],
        "environment": row["environment"],
        "config": json.loads(row.get("config_json") or "{}"),
        "enabled": bool(row.get("enabled")),
        "status": row.get("status") or "disconnected",
        "last_error": row.get("last_error") or "",
        "has_secret": bool(decrypt(row.get("secret_enc") or "")),
        "created_at": row.get("created_at"),
    }


def default_provider() -> dict:
    row = get_db().one("SELECT * FROM providers WHERE is_default=1 AND enabled=1 LIMIT 1")
    if not row:
        row = get_db().one("SELECT * FROM providers WHERE enabled=1 ORDER BY created_at LIMIT 1")
    if not row:
        raise HTTPException(400, "No model provider configured. Add one in Models.")
    return row


def _conversation(conversation_id: str | None, first_message: str = "") -> dict:
    db = get_db()
    if conversation_id:
        row = db.one("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        if row:
            return row
    cid = new_id("conv_")
    title = (first_message.strip().splitlines()[0] if first_message.strip() else "New chat")[:60]
    db.execute("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",
               (cid, title or "New chat", now(), now()))
    return db.one("SELECT * FROM conversations WHERE id=?", (cid,))  # type: ignore[return-value]


def _history(conversation_id: str) -> list[dict]:
    rows = get_db().query("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,))
    return rows


def _order_public(row: dict) -> dict:
    row = dict(row)
    row["checks"] = None
    return row


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    info = seed_all()
    db = get_db()
    autostart = db.query("SELECT * FROM mcp_servers WHERE enabled=1 AND auto_start=1")
    for row in autostart:
        try:
            client = await asyncio.to_thread(manager.start, row, 30)
            db.execute("UPDATE mcp_servers SET last_status=?, tools_json=?, last_error='' WHERE id=?",
                       ("running", json.dumps(client.tools), row["id"]))
        except Exception as exc:
            db.execute("UPDATE mcp_servers SET last_status=?, last_error=? WHERE id=?",
                       ("error", str(exc)[:500], row["id"]))
    db.audit("core.start", json.dumps(info))
    if db.get_setting("autopilot_enabled") and db.get_setting("autopilot_autostart"):
        try:
            autopilot_engine.start()
        except Exception as exc:
            db.audit("autopilot.start_failed", str(exc)[:500])
    yield
    if autopilot_engine.state.get("running"):
        autopilot_engine.stop("core shutdown", persist=False)
    manager.stop_all()


app = FastAPI(title="AI-TRADER Core", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|capacitor://localhost|ionic://localhost)$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if TOKEN and request.url.path.startswith(API_PREFIX):
        supplied = request.headers.get("x-ai-trader-token") or ""
        if not supplied:
            auth = request.headers.get("authorization", "")
            supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
        if supplied != TOKEN:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/health")
async def health():
    return {"ok": True, "app": "AI-TRADER", "version": __version__, "ts": now()}


@app.get(f"{API_PREFIX}/system")
async def system_info():
    node = _which("npx")
    uv = _which("uvx")
    return {
        "app": "AI-TRADER",
        "version": __version__,
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "home": str(HOME_DIR),
        "data_dir": str(DATA_DIR),
        "skills_dir": str(SKILLS_DIR),
        "vault": vault_backend(),
        "host": HOST,
        "port": PORT,
        "mt5_available": _mt5_available(),
        "node": node,
        "uv": uv,
        # True when the runtime ships inside the installer rather than being
        # installed on the machine. The UI uses this to say "bundled" instead
        # of telling the user to install something they already have.
        "node_bundled": node and _is_bundled("npx"),
        "uv_bundled": uv and _is_bundled("uvx"),
    }


def _which(cmd: str) -> bool:
    import shutil

    return bool(shutil.which(cmd) or shutil.which(cmd + ".cmd"))


def _is_bundled(cmd: str) -> bool:
    """True when ``cmd`` resolves inside the installer's bundled tools folder.

    The test is a positive match against the folders this install actually
    ships (``aitrader.tools.bundled_tool_dirs``). A looser check such as
    "the parent directory exists" is true for almost every path on disk and
    would tell the user that a system-wide Node.js is "bundled with
    AI-TRADER" when it is not.
    """
    import shutil
    from pathlib import Path

    from .tools import is_bundled_command

    found = shutil.which(cmd) or shutil.which(cmd + ".cmd")
    if not found:
        return False
    try:
        resolved = Path(found).resolve()
    except Exception:
        return False
    return is_bundled_command(resolved)


def _mt5_available() -> bool:
    try:
        import MetaTrader5  # noqa: F401

        return True
    except Exception:
        return False


@app.get(f"{API_PREFIX}/bootstrap")
async def bootstrap():
    db = get_db()
    return {
        "system": await system_info(),
        "settings": db.all_settings(),
        "providers": [provider_public(r) for r in db.query("SELECT * FROM providers ORDER BY is_default DESC, name")],
        "mcp": [mcp_public(r) for r in db.query("SELECT * FROM mcp_servers ORDER BY category, name")],
        "skills": skill_catalog(),
        "accounts": [account_public(r) for r in trading.list_accounts()],
        "broker_catalog": BROKER_CATALOG,
        "conversations": db.query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 50"),
        "approvals": db.query("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at DESC"),
        "autopilot": autopilot_engine.status(),
    }


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/providers")
async def get_providers():
    return [provider_public(r) for r in get_db().query("SELECT * FROM providers ORDER BY is_default DESC, name")]


@app.post(f"{API_PREFIX}/providers")
async def add_provider(body: ProviderIn):
    db = get_db()
    pid = new_id("prv_")
    if body.is_default:
        db.execute("UPDATE providers SET is_default=0")
    db.execute(
        "INSERT INTO providers(id,name,kind,base_url,api_key_enc,model,models_json,headers_json,enabled,is_default,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (pid, body.name, body.kind, body.base_url.rstrip("/"), encrypt(body.api_key or ""),
         body.model, json.dumps(body.models), json.dumps(body.headers), 1 if body.enabled else 0,
         1 if body.is_default else 0, now()),
    )
    db.audit("provider.added", f"{pid} {body.name} {body.model}")
    return provider_public(db.one("SELECT * FROM providers WHERE id=?", (pid,)))


@app.patch(f"{API_PREFIX}/providers/{{provider_id}}")
async def patch_provider(provider_id: str, body: ProviderPatch):
    db = get_db()
    row = db.one("SELECT * FROM providers WHERE id=?", (provider_id,))
    if not row:
        raise HTTPException(404, "Provider not found")
    updates: dict[str, Any] = {}
    for field in ("name", "kind", "base_url", "model"):
        value = getattr(body, field)
        if value is not None:
            updates[field] = value.rstrip("/") if field == "base_url" else value
    if body.models is not None:
        updates["models_json"] = json.dumps(body.models)
    if body.headers is not None:
        updates["headers_json"] = json.dumps(body.headers)
    if body.enabled is not None:
        updates["enabled"] = 1 if body.enabled else 0
    if body.clear_key:
        updates["api_key_enc"] = ""
    elif body.api_key:
        updates["api_key_enc"] = encrypt(body.api_key)
    if body.is_default:
        db.execute("UPDATE providers SET is_default=0")
        updates["is_default"] = 1
    if updates:
        cols = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE providers SET {cols} WHERE id=?", (*updates.values(), provider_id))
    return provider_public(db.one("SELECT * FROM providers WHERE id=?", (provider_id,)))


@app.delete(f"{API_PREFIX}/providers/{{provider_id}}")
async def remove_provider(provider_id: str):
    db = get_db()
    db.execute("DELETE FROM providers WHERE id=?", (provider_id,))
    db.audit("provider.deleted", provider_id)
    return {"ok": True}


@app.post(f"{API_PREFIX}/providers/{{provider_id}}/test")
async def test_provider_endpoint(provider_id: str):
    db = get_db()
    row = db.one("SELECT * FROM providers WHERE id=?", (provider_id,))
    if not row:
        raise HTTPException(404, "Provider not found")
    result = await test_provider(row, decrypt(row.get("api_key_enc") or ""))
    db.execute(
        "UPDATE providers SET last_status=?, last_latency_ms=?, last_checked=? WHERE id=?",
        ("ok" if result.get("ok") else "error", result.get("latency_ms", 0), now(), provider_id),
    )
    db.audit("provider.tested", json.dumps({"id": provider_id, "ok": result.get("ok")})[:1000])
    return result


@app.get(f"{API_PREFIX}/providers/{{provider_id}}/models")
async def provider_models(provider_id: str):
    db = get_db()
    row = db.one("SELECT * FROM providers WHERE id=?", (provider_id,))
    if not row:
        raise HTTPException(404, "Provider not found")
    models = await list_models(row, decrypt(row.get("api_key_enc") or ""))
    if models:
        db.execute("UPDATE providers SET models_json=? WHERE id=?", (json.dumps(models), provider_id))
    return {"models": models}


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/mcp")
async def get_mcp():
    return [mcp_public(r) for r in get_db().query("SELECT * FROM mcp_servers ORDER BY category, name")]


@app.get(f"{API_PREFIX}/mcp/catalog")
async def mcp_catalog():
    path = SEED_DIR / "mcp_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    installed = {r["id"] for r in get_db().query("SELECT id FROM mcp_servers")}
    for item in catalog:
        item["installed"] = item["id"] in installed
    return catalog


@app.post(f"{API_PREFIX}/mcp")
async def add_mcp(body: MCPIn):
    db = get_db()
    server_id = new_id("mcp_")
    db.execute(
        "INSERT INTO mcp_servers(id,name,transport,command,args_json,url,env_json,enabled,auto_start,"
        "category,notes,tools_json,last_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (server_id, body.name, body.transport, body.command, json.dumps(body.args), body.url,
         json.dumps(body.env), 1 if body.enabled else 0, 1 if body.auto_start else 0,
         body.category, body.notes, "[]", "stopped", now()),
    )
    db.audit("mcp.added", f"{server_id} {body.name}")
    return mcp_public(db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,)))


@app.patch(f"{API_PREFIX}/mcp/{{server_id}}")
async def patch_mcp(server_id: str, body: dict):
    db = get_db()
    row = db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,))
    if not row:
        raise HTTPException(404, "MCP server not found")
    updates: dict[str, Any] = {}
    for key in ("name", "transport", "command", "url", "category", "notes"):
        if key in body:
            updates[key] = body[key]
    if "args" in body:
        updates["args_json"] = json.dumps(body["args"] or [])
    if "env" in body:
        existing_env = json.loads(row.get("env_json") or "{}")
        updates["env_json"] = json.dumps(merge_secret_fields(existing_env, body["env"]))
    for key in ("enabled", "auto_start"):
        if key in body:
            updates[key] = 1 if body[key] else 0
    if updates:
        cols = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE mcp_servers SET {cols} WHERE id=?", (*updates.values(), server_id))
        if "enabled" in updates and not updates["enabled"]:
            manager.stop(server_id)
    return mcp_public(db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,)))


@app.delete(f"{API_PREFIX}/mcp/{{server_id}}")
async def remove_mcp(server_id: str):
    manager.stop(server_id)
    get_db().execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
    get_db().audit("mcp.deleted", server_id)
    return {"ok": True}


@app.post(f"{API_PREFIX}/mcp/{{server_id}}/start")
async def start_mcp(server_id: str):
    db = get_db()
    row = db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,))
    if not row:
        raise HTTPException(404, "MCP server not found")
    try:
        client = await asyncio.to_thread(manager.start, row, 60)
        db.execute("UPDATE mcp_servers SET last_status=?, tools_json=?, last_error='' WHERE id=?",
                   ("running", json.dumps(client.tools), server_id))
        db.audit("mcp.started", f"{server_id} ({len(client.tools)} tools)")
        return {"ok": True, "tools": client.tools, "server_info": getattr(client, "server_info", {})}
    except (MCPError, Exception) as exc:
        db.execute("UPDATE mcp_servers SET last_status=?, last_error=? WHERE id=?",
                   ("error", str(exc)[:800], server_id))
        return {"ok": False, "error": str(exc)}


@app.post(f"{API_PREFIX}/mcp/{{server_id}}/stop")
async def stop_mcp(server_id: str):
    manager.stop(server_id)
    get_db().execute("UPDATE mcp_servers SET last_status='stopped' WHERE id=?", (server_id,))
    return {"ok": True}


@app.post(f"{API_PREFIX}/mcp/{{server_id}}/test")
async def test_mcp(server_id: str):
    db = get_db()
    row = db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,))
    if not row:
        raise HTTPException(404, "MCP server not found")
    try:
        client = await asyncio.to_thread(manager.start, row, 60)
        db.execute("UPDATE mcp_servers SET last_status='running', tools_json=?, last_error='' WHERE id=?",
                   (json.dumps(client.tools), server_id))
        return {"ok": True, "tools": client.tools, "tool_count": len(client.tools),
                "server_info": getattr(client, "server_info", {})}
    except Exception as exc:
        db.execute("UPDATE mcp_servers SET last_status='error', last_error=? WHERE id=?",
                   (str(exc)[:800], server_id))
        return {"ok": False, "error": str(exc), "stderr": getattr(manager.get(server_id), "stderr_tail", lambda: "")()}


@app.post(f"{API_PREFIX}/mcp/{{server_id}}/call")
async def call_mcp_tool(server_id: str, body: dict):
    db = get_db()
    row = db.one("SELECT * FROM mcp_servers WHERE id=?", (server_id,))
    if not row:
        raise HTTPException(404, "MCP server not found")
    tool = body.get("tool")
    if not tool:
        raise HTTPException(400, "Missing tool name")
    try:
        result = await asyncio.to_thread(manager.call, row, tool, body.get("arguments") or {})
        return {"ok": True, "result": result, "text": content_to_text(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/skills")
async def get_skills():
    return skill_catalog()


@app.get(f"{API_PREFIX}/skills/{{skill_id}}")
async def get_skill(skill_id: str):
    try:
        return {"id": skill_id, "content": read_skill(skill_id)}
    except FileNotFoundError:
        raise HTTPException(404, "Skill not found")


@app.post(f"{API_PREFIX}/skills")
async def add_skill(body: SkillIn):
    skill_id = body.id or body.name.lower().replace(" ", "-")
    try:
        return create_skill(skill_id, body.name, body.description, body.content, body.enabled)
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@app.put(f"{API_PREFIX}/skills/{{skill_id}}")
async def edit_skill(skill_id: str, body: SkillIn):
    try:
        return update_skill(skill_id, content=body.content or None, enabled=body.enabled,
                            name=body.name, description=body.description)
    except FileNotFoundError:
        raise HTTPException(404, "Skill not found")


@app.delete(f"{API_PREFIX}/skills/{{skill_id}}")
async def remove_skill(skill_id: str):
    delete_skill(skill_id)
    return {"ok": True}


@app.post(f"{API_PREFIX}/skills/rescan")
async def rescan_skills():
    return {"synced": sync_skills()}


# ---------------------------------------------------------------------------
# Brokers / accounts
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/brokers")
async def brokers():
    return {
        "catalog": BROKER_CATALOG,
        "accounts": [account_public(r) for r in trading.list_accounts()],
        "mt5_available": _mt5_available(),
    }


@app.get(f"{API_PREFIX}/brokers/mt5/status")
async def mt5_status():
    """Get MT5 terminal status for UI guidance."""
    mt5_available = _mt5_available()
    terminal_path = None
    if mt5_available:
        try:
            import MetaTrader5 as mt5
            # Try to get terminal path from initialized instance
            terminal_info = mt5.terminal_info()
            if terminal_info:
                terminal_path = terminal_info.path
        except Exception:
            pass
    # Fallback: check common paths
    if not terminal_path:
        import os, glob
        common = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        ]
        for p in common:
            if os.path.exists(p):
                terminal_path = p
                break
        if not terminal_path:
            matches = glob.glob(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\*\terminal64.exe"))
            if matches:
                terminal_path = matches[0]
    return {
        "mt5_available": mt5_available,
        "terminal_path": terminal_path,
        "vcpp_ok": True,  # Checked at startup
        "message": "MT5 Python package available" if mt5_available else "MetaTrader5 package not installed. Run: pip install MetaTrader5",
    }


@app.post(f"{API_PREFIX}/accounts")
async def add_account(body: AccountIn):
    db = get_db()
    aid = new_id("acc_")
    if body.environment == "live":
        raise HTTPException(400, "Live accounts are disabled by default. Create a demo account, verify it, "
                                 "then enable live trading in Settings > Risk.")
    db.execute(
        "INSERT INTO accounts(id,name,broker,environment,config_json,secret_enc,enabled,status,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (aid, body.name, body.broker, body.environment, json.dumps(body.config),
         encrypt_json(body.secret), 1 if body.enabled else 0, "disconnected", now()),
    )
    db.audit("account.added", f"{aid} {body.broker} {body.environment}")
    return account_public(db.one("SELECT * FROM accounts WHERE id=?", (aid,)))


@app.patch(f"{API_PREFIX}/accounts/{{account_id}}")
async def patch_account(account_id: str, body: dict):
    db = get_db()
    row = db.one("SELECT * FROM accounts WHERE id=?", (account_id,))
    if not row:
        raise HTTPException(404, "Account not found")
    updates: dict[str, Any] = {}
    for key in ("name", "broker", "environment"):
        if key in body:
            updates[key] = body[key]
    if "config" in body:
        updates["config_json"] = json.dumps(body["config"])
    if "secret" in body:
        existing = decrypt_json(row.get("secret_enc"))
        existing.update(merge_secret_fields(existing, body["secret"] or {}))
        updates["secret_enc"] = encrypt_json(existing)
    if "enabled" in body:
        updates["enabled"] = 1 if body["enabled"] else 0
    if updates:
        cols = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE accounts SET {cols} WHERE id=?", (*updates.values(), account_id))
    return account_public(db.one("SELECT * FROM accounts WHERE id=?", (account_id,)))


@app.delete(f"{API_PREFIX}/accounts/{{account_id}}")
async def remove_account(account_id: str):
    db = get_db()
    row = db.one("SELECT id FROM accounts WHERE id=?", (account_id,))
    if not row:
        raise HTTPException(404, "Account not found")
    db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    db.audit("account.deleted", account_id)
    return {"ok": True}


@app.post(f"{API_PREFIX}/accounts/{{account_id}}/test")
async def test_account(account_id: str):
    db = get_db()
    row = db.one("SELECT * FROM accounts WHERE id=?", (account_id,))
    if not row:
        raise HTTPException(404, "Account not found")
    try:
        broker = trading.broker_for(row)
        result = await broker.connect()
        db.execute("UPDATE accounts SET status='connected', last_error='' WHERE id=?", (account_id,))
        return {"ok": True, "account": result}
    except BrokerError as exc:
        db.execute("UPDATE accounts SET status='error', last_error=? WHERE id=?", (str(exc)[:500], account_id))
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        db.execute("UPDATE accounts SET status='error', last_error=? WHERE id=?", (str(exc)[:500], account_id))
        return {"ok": False, "error": str(exc)[:500]}


@app.get(f"{API_PREFIX}/accounts/{{account_id}}/snapshot")
async def account_snapshot(account_id: str):
    row = trading.account_row(account_id)
    snap = await trading.snapshot(row)
    snap["positions"] = await trading.positions(row)
    return snap


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/market/quote")
async def quote(symbol: str):
    try:
        return await market.get_quote(symbol)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@app.get(f"{API_PREFIX}/market/quotes")
async def quotes(symbols: str):
    return {"quotes": await market.get_quotes([s.strip() for s in symbols.split(",") if s.strip()][:20])}


@app.get(f"{API_PREFIX}/market/candles")
async def candles(symbol: str, interval: str = "1h", span: str = "1mo"):
    return {"symbol": symbol, "candles": await market.get_candles(symbol, interval, span)}


@app.get(f"{API_PREFIX}/market/news")
async def news(query: str, limit: int = 8):
    return await agent_mod._news(query, limit)


# ---------------------------------------------------------------------------
# Orders / positions / approvals
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/orders")
async def orders(limit: int = 40):
    return trading.recent_orders(limit)


@app.post(f"{API_PREFIX}/orders")
async def propose_order(body: OrderIn):
    try:
        return await trading.propose(body.model_dump(), source="ui")
    except LookupError as exc:
        raise HTTPException(400, str(exc))


@app.post(f"{API_PREFIX}/orders/{{order_id}}/approve")
async def approve_order(order_id: str):
    try:
        return await trading.approve(order_id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.post(f"{API_PREFIX}/orders/{{order_id}}/reject")
async def reject_order(order_id: str, body: dict | None = None):
    return trading.reject(order_id, (body or {}).get("reason", "Rejected by user"))


@app.get(f"{API_PREFIX}/positions")
async def positions(account_id: str | None = None):
    row = trading.account_row(account_id)
    return {"account_id": row["id"], "positions": await trading.positions(row)}


@app.post(f"{API_PREFIX}/positions/{{ticket}}/close")
async def close_position(ticket: str, body: CloseIn):
    return await trading.close_position(body.account_id or "", ticket, body.symbol, body.volume)


@app.get(f"{API_PREFIX}/approvals")
async def approvals(status: str = "pending"):
    return get_db().query("SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC", (status,))


@app.post(f"{API_PREFIX}/approvals/{{approval_id}}/approve")
async def approve_action(approval_id: str):
    db = get_db()
    row = db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not row:
        raise HTTPException(404, "Approval not found")
    payload = json.loads(row["payload_json"])
    if row["kind"] == "order":
        result = await trading.approve(payload.get("order_id", ""))
    elif row["kind"] == "close_position":
        result = await trading.close_position(payload.get("account_id", ""), payload.get("ticket", ""),
                                              payload.get("symbol"))
    elif row["kind"] == "mcp_tool":
        server = db.one("SELECT * FROM mcp_servers WHERE id=?", (payload["server_id"],))
        if not server:
            raise HTTPException(404, "MCP server no longer exists")
        try:
            raw = await asyncio.to_thread(manager.call, server, payload["tool"], payload.get("args") or {})
            result = {"ok": True, "text": content_to_text(raw)}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
    else:
        raise HTTPException(400, f"Unknown approval kind {row['kind']}")
    db.execute("UPDATE approvals SET status='resolved', resolved_at=?, result_json=? WHERE id=?",
               (now(), json.dumps(result, default=str)[:4000], approval_id))
    db.audit("approval.approved", f"{approval_id} {row['kind']}")
    return result


@app.post(f"{API_PREFIX}/approvals/{{approval_id}}/reject")
async def reject_action(approval_id: str):
    db = get_db()
    db.execute("UPDATE approvals SET status='rejected', resolved_at=? WHERE id=?", (now(), approval_id))
    db.audit("approval.rejected", approval_id)
    return {"ok": True}


@app.get(f"{API_PREFIX}/audit")
async def audit(limit: int = 100):
    return trading.audit_log(limit)


# ---------------------------------------------------------------------------
# Autopilot + dashboard
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/autopilot")
async def autopilot_status():
    return autopilot_engine.status()


@app.get(f"{API_PREFIX}/autopilot/decisions")
async def autopilot_decisions(limit: int = 60):
    return autopilot_mod.recent_decisions(max(1, min(limit, 500)))


@app.get(f"{API_PREFIX}/dashboard")
async def dashboard():
    return await autopilot_mod.dashboard_payload()


@app.post(f"{API_PREFIX}/autopilot/start")
async def autopilot_start(body: dict | None = None):
    db = get_db()
    body = body or {}
    if body.get("interval_sec") is not None:
        db.set_setting("autopilot_interval_sec", max(60, min(int(body["interval_sec"]), 86400)))
    if body.get("symbols") is not None:
        db.set_setting("autopilot_symbols", [str(s).upper().strip() for s in body["symbols"] if str(s).strip()])
    if body.get("provider_ids") is not None:
        db.set_setting("autopilot_provider_ids", [str(s) for s in body["provider_ids"]])
    if body.get("execution") in ("auto", "approval"):
        db.set_setting("autopilot_execution", body["execution"])
    if body.get("confidence") is not None:
        db.set_setting("autopilot_confidence", max(0.05, min(float(body["confidence"]), 1.0)))
    if body.get("symbols_per_cycle") is not None:
        db.set_setting("autopilot_symbols_per_cycle", max(1, min(int(body["symbols_per_cycle"]), 10)))
    if body.get("max_trades_per_day") is not None:
        db.set_setting("autopilot_max_trades_per_day", max(1, min(int(body["max_trades_per_day"]), 100)))
    if body.get("account_id"):
        if not db.one("SELECT id FROM accounts WHERE id=?", (body["account_id"],)):
            raise HTTPException(400, "Account not found")
        db.set_setting("default_account_id", body["account_id"])
    db.set_setting("autopilot_enabled", True)
    return autopilot_engine.start()


@app.post(f"{API_PREFIX}/autopilot/stop")
async def autopilot_stop():
    return autopilot_engine.stop()


@app.post(f"{API_PREFIX}/autopilot/run-once")
async def autopilot_run_once():
    return await autopilot_engine.run_once()


@app.post(f"{API_PREFIX}/autopilot/kill")
async def autopilot_kill():
    db = get_db()
    db.set_setting("kill_switch", True)
    db.audit("autopilot.kill", "operator pulled the kill switch", actor="user")
    autopilot_engine.stop("kill switch")
    return {"ok": True, "kill_switch": True, "autopilot": autopilot_engine.status()}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ALLOWED_SETTINGS = set(SAFE_DEFAULTS) | {"theme", "ui_density", "onboarding_done", "risk_profile",
                                         "default_account_id", "auto_approve_mcp_dangerous"}


@app.get(f"{API_PREFIX}/settings")
async def get_settings():
    return get_db().all_settings()


@app.put(f"{API_PREFIX}/settings")
async def put_settings(body: dict):
    db = get_db()
    for key, value in body.items():
        if key not in ALLOWED_SETTINGS:
            continue
        if key == "allow_live_trading" and value:
            if not db.all_settings().get("allow_live_trading"):
                db.audit("settings.live_enabled", "operator enabled live trading", actor="user")
        if key in ("max_risk_per_trade_pct", "max_daily_loss_pct", "max_drawdown_pct"):
            value = max(0.05, min(float(value), 50.0))
        if key == "max_lot_size":
            value = max(0.01, min(float(value), 100.0))
        if key in ("max_open_positions", "max_spread_points"):
            value = max(1, min(int(value), 100))
        if key == "autopilot_interval_sec":
            value = max(60, min(int(value), 86400))
        if key == "autopilot_cooldown_sec":
            value = max(0, min(int(value), 86400))
        if key == "autopilot_symbols_per_cycle":
            value = max(1, min(int(value), 10))
        if key == "autopilot_max_trades_per_day":
            value = max(1, min(int(value), 100))
        if key in ("autopilot_sl_atr", "autopilot_tp_atr"):
            value = max(0.2, min(float(value), 20.0))
        if key == "autopilot_confidence":
            value = max(0.05, min(float(value), 1.0))
        if key == "autopilot_execution":
            value = "auto" if value == "auto" else "approval"
        if key == "autopilot_symbols":
            value = [str(s).upper().strip() for s in (value or []) if str(s).strip()]
        if key == "autopilot_provider_ids":
            value = [str(s) for s in (value or []) if str(s).strip()]
        if key == "default_account_id" and value:
            if not db.one("SELECT id FROM accounts WHERE id=?", (value,)):
                raise HTTPException(400, "Account not found")
        if key == "trading_mode" and value == "live":
            if not db.all_settings().get("allow_live_trading"):
                raise HTTPException(400, "Enable 'allow_live_trading' before switching to live mode.")
        db.set_setting(key, value)
    db.audit("settings.updated", json.dumps(body)[:2000], actor="user")
    if "autopilot_enabled" in body:
        if db.get_setting("autopilot_enabled"):
            autopilot_engine.start()
        else:
            autopilot_engine.stop("disabled in settings")
    return db.all_settings()


# ---------------------------------------------------------------------------
# Conversations + chat
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/conversations")
async def conversations():
    return get_db().query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100")


@app.post(f"{API_PREFIX}/conversations")
async def create_conversation(body: ConversationIn):
    db = get_db()
    cid = new_id("conv_")
    db.execute("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",
               (cid, body.title or "New chat", now(), now()))
    return db.one("SELECT * FROM conversations WHERE id=?", (cid,))


@app.patch(f"{API_PREFIX}/conversations/{{conversation_id}}")
async def rename_conversation(conversation_id: str, body: ConversationIn):
    get_db().execute("UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                     (body.title, now(), conversation_id))
    return {"ok": True}


@app.delete(f"{API_PREFIX}/conversations/{{conversation_id}}")
async def delete_conversation(conversation_id: str):
    db = get_db()
    db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return {"ok": True}


@app.get(f"{API_PREFIX}/conversations/{{conversation_id}}/messages")
async def conversation_messages(conversation_id: str):
    rows = get_db().query(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,)
    )
    for row in rows:
        try:
            row["meta"] = json.loads(row.get("meta_json") or "{}")
        except json.JSONDecodeError:
            row["meta"] = {}
    return rows


@app.post(f"{API_PREFIX}/chat")
async def chat_once(body: ChatIn):
    row = get_db().one("SELECT * FROM providers WHERE id=?", (body.provider_id,)) if body.provider_id else default_provider()
    if not row:
        raise HTTPException(404, "Provider not found")
    api_key = decrypt(row.get("api_key_enc") or "")
    if not api_key and row.get("kind") not in ("ollama",):
        raise HTTPException(400, f"Add an API key for {row['name']} in Models.")
    conv = _conversation(body.conversation_id, body.message)
    history = _history(conv["id"])
    result = await agent_mod.run_turn(
        provider=row, api_key=api_key, history=history, user_text=body.message,
        account_id=body.account_id, manager=manager, mode=body.mode,
    )
    agent_mod.save_turn(conv["id"], body.message, result["text"], {"trace": result.get("trace", []), "provider": row["id"]})
    return {"conversation_id": conv["id"], **result}


@app.post(f"{API_PREFIX}/chat/stream")
async def chat_stream(body: ChatIn):
    row = get_db().one("SELECT * FROM providers WHERE id=?", (body.provider_id,)) if body.provider_id else default_provider()
    if not row:
        raise HTTPException(404, "Provider not found")
    api_key = decrypt(row.get("api_key_enc") or "")
    if not api_key and row.get("kind") != "ollama" and "localhost" not in (row.get("base_url") or "") \
            and "127.0.0.1" not in (row.get("base_url") or ""):
        raise HTTPException(400, f"Add an API key for {row['name']} in Models.")
    conv = _conversation(body.conversation_id, body.message)
    history = _history(conv["id"])
    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    task = asyncio.create_task(
        agent_mod.run_turn(
            provider=row, api_key=api_key, history=history, user_text=body.message,
            account_id=body.account_id, manager=manager, mode=body.mode, on_event=on_event,
        )
    )

    async def generator():
        yield ": connected\n\n"
        while True:
            if task.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.4)
                yield f"data: {json.dumps(event, default=str)}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield ": ping\n\n"
        try:
            result = task.result()
        except Exception as exc:
            result = {"text": f"Agent error: {exc}", "trace": []}
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        agent_mod.save_turn(conv["id"], body.message, result.get("text", ""),
                            {"trace": result.get("trace", []), "provider": row["id"]})
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv['id'], 'text': result.get('text', ''), 'trace': result.get('trace', [])}, default=str)}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Static UI (browser / mobile fallback)
# ---------------------------------------------------------------------------
_DIST = Path(os.environ.get("AI_TRADER_UI") or (PROJECT_DIR / "app" / "dist"))
if not _DIST.is_dir():
    _DIST = PROJECT_DIR / "ui"          # packaged layout (resources/ui)
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="ui")
