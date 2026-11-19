"""First-run seeding. Safe to call on every boot (idempotent)."""
from __future__ import annotations

import json

from .config import SEED_DIR
from .db import get_db, new_id, now
from .security import encrypt
from .skills import sync_skills


def _load(name: str) -> list[dict]:
    path = SEED_DIR / name
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def seed_providers() -> int:
    db = get_db()
    if db.one("SELECT id FROM providers LIMIT 1"):
        return 0
    added = 0
    for item in _load("providers.json"):
        db.execute(
            "INSERT INTO providers(id,name,kind,base_url,api_key_enc,model,models_json,headers_json,"
            "enabled,is_default,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                item["id"], item["name"], item.get("kind", "openai"), item["base_url"],
                encrypt(item.get("api_key", "")), item["model"],
                json.dumps(item.get("models", [])), json.dumps(item.get("headers", {})),
                1, 1 if item.get("is_default") else 0, now(),
            ),
        )
        added += 1
    return added


def seed_mcp() -> int:
    db = get_db()
    added = 0
    for item in _load("mcp_servers.json"):
        if db.one("SELECT id FROM mcp_servers WHERE id=?", (item["id"],)):
            continue
        db.execute(
            "INSERT INTO mcp_servers(id,name,transport,command,args_json,url,env_json,enabled,auto_start,"
            "category,notes,tools_json,last_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item["id"], item["name"], item.get("transport", "stdio"), item.get("command", ""),
                json.dumps(item.get("args", [])), item.get("url", ""), json.dumps(item.get("env", {})),
                1 if item.get("enabled") else 0, 1 if item.get("auto_start") else 0,
                item.get("category", "general"), item.get("notes", ""), "[]", "stopped", now(),
            ),
        )
        added += 1
    return added


def seed_accounts() -> int:
    db = get_db()
    if db.one("SELECT id FROM accounts LIMIT 1"):
        return 0
    db.execute(
        "INSERT INTO accounts(id,name,broker,environment,config_json,secret_enc,enabled,status,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (new_id("acc_"), "Paper Simulator", "paper", "paper",
         json.dumps({"balance": 10000, "currency": "USD"}), "", 1, "connected", now()),
    )
    return 1


def seed_all() -> dict:
    providers = seed_providers()
    mcp = seed_mcp()
    accounts = seed_accounts()
    skills = sync_skills()
    return {"providers": providers, "mcp": mcp, "accounts": accounts, "skills": skills}
