"""Order lifecycle: risk gate -> approval -> broker execution -> audit."""
from __future__ import annotations

import json

from .brokers import BrokerError, build_broker
from .db import get_db, new_id, now
from .market import get_quote
from .risk import evaluate_order, track_equity
from .security import decrypt, decrypt_json


def _settings() -> dict:
    return get_db().all_settings()


def list_accounts() -> list[dict]:
    return get_db().query("SELECT * FROM accounts ORDER BY created_at")


def account_row(account_id: str | None = None) -> dict:
    db = get_db()
    if account_id:
        row = db.one("SELECT * FROM accounts WHERE id=?", (account_id,))
        if not row:
            raise LookupError(f"Account '{account_id}' not found")
        return row
    row = db.one("SELECT * FROM accounts WHERE enabled=1 ORDER BY (broker='paper') DESC, created_at LIMIT 1")
    if not row:
        row = db.one("SELECT * FROM accounts ORDER BY created_at LIMIT 1")
    if not row:
        raise LookupError("No broker account configured")
    return row


def broker_for(row: dict):
    return build_broker(row, decrypt_json(row.get("secret_enc")))


async def snapshot(row: dict) -> dict:
    broker = broker_for(row)
    try:
        info = await broker.account()
        track_equity(row["id"], float(info.get("equity") or 0))
        return info
    except Exception as exc:
        return {
            "ok": False,
            "broker": row.get("broker"),
            "error": str(exc)[:400],
            "balance": 0,
            "equity": 0,
            "trade_mode": "DEMO" if row.get("environment") != "live" else "LIVE",
        }


async def positions(row: dict) -> list[dict]:
    broker = broker_for(row)
    try:
        return await broker.positions()
    except Exception:
        return []


async def propose(payload: dict, source: str = "ui", auto_execute: bool = False) -> dict:
    db = get_db()
    settings = _settings()
    account = account_row(payload.get("account_id"))
    quote = None
    try:
        quote = await get_quote(payload["symbol"])
    except Exception:
        quote = None

    acct = await snapshot(account)
    open_positions = await positions(account)
    env = "LIVE" if account.get("environment") == "live" else "DEMO"
    order = {
        "account_id": account["id"],
        "symbol": (payload.get("symbol") or "").upper(),
        "side": (payload.get("side") or "").upper(),
        "volume": float(payload.get("volume") or 0),
        "sl": float(payload.get("sl") or 0),
        "tp": float(payload.get("tp") or 0),
        "order_type": payload.get("order_type", "market"),
        "price": float(payload.get("price") or (quote or {}).get("price") or 0),
        "environment": env,
        "reason": (payload.get("reason") or "")[:1000],
    }
    verdict = await evaluate_order(order, acct, open_positions, settings, quote)
    order["risk_usd"] = verdict["risk_usd"]
    order["risk_pct"] = verdict["risk_pct"]

    require_approval = bool(settings.get("require_order_approval", True)) or env == "LIVE"
    if auto_execute:
        # Autopilot can skip the click for paper/demo. Live still needs an
        # explicit second switch, on top of allow_live_trading.
        require_approval = env == "LIVE" and not bool(settings.get("autopilot_allow_live_auto", False))
    status = "blocked" if not verdict["allowed"] else ("pending_approval" if require_approval else "approved")
    order_id = new_id("ord_")
    db.execute(
        "INSERT INTO orders(id,account_id,symbol,side,volume,order_type,price,sl,tp,status,risk_usd,risk_pct,reason,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            order_id, order["account_id"], order["symbol"], order["side"], order["volume"],
            order["order_type"], order["price"], order["sl"], order["tp"], status,
            order["risk_usd"], order["risk_pct"], order["reason"], now(),
        ),
    )
    db.audit(
        "order.proposed",
        json.dumps({"id": order_id, "symbol": order["symbol"], "side": order["side"], "volume": order["volume"],
                    "status": status, "blocked_by": verdict["blocked_by"], "source": source}),
        actor=source,
    )
    if status == "pending_approval":
        db.execute(
            "INSERT INTO approvals(id,kind,payload_json,status,created_at) VALUES(?,?,?,?,?)",
            (new_id("apr_"), "order", json.dumps({"order_id": order_id}), "pending", now()),
        )
    result = {
        "order_id": order_id,
        "status": status,
        "allowed": verdict["allowed"],
        "checks": verdict["checks"],
        "blocked_by": verdict["blocked_by"],
        "risk_usd": verdict["risk_usd"],
        "risk_pct": verdict["risk_pct"],
        "quote": quote,
        "account": acct,
    }
    if status == "approved":
        result["execution"] = await execute(order_id)
    return result


async def execute(order_id: str) -> dict:
    db = get_db()
    order = db.one("SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        raise LookupError("Order not found")
    account = account_row(order["account_id"])
    broker = broker_for(account)
    try:
        res = await broker.place(order)
        db.execute(
            "UPDATE orders SET status=?, ticket=?, broker_response=?, approved_at=? WHERE id=?",
            ("filled", str(res.get("ticket", "")), json.dumps(res)[:4000], now(), order_id),
        )
        db.audit("order.filled", json.dumps({"id": order_id, "ticket": res.get("ticket"), "price": res.get("price")}))
        return {"ok": True, **{k: v for k, v in res.items() if k != "raw"}}
    except (BrokerError, Exception) as exc:
        db.execute(
            "UPDATE orders SET status=?, broker_response=? WHERE id=?",
            ("failed", str(exc)[:4000], order_id),
        )
        db.audit("order.failed", f"{order_id}: {exc}", actor="broker")
        return {"ok": False, "error": str(exc)[:500]}


async def approve(order_id: str) -> dict:
    db = get_db()
    order = db.one("SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        raise LookupError("Order not found")
    if order["status"] not in ("pending_approval", "approved"):
        raise ValueError(f"Order is {order['status']}, not awaiting approval")
    if get_db().all_settings().get("kill_switch"):
        raise ValueError("Kill switch is on")
    result = await execute(order_id)
    db.execute("UPDATE approvals SET status='resolved', resolved_at=?, result_json=? WHERE payload_json LIKE ?",
               (now(), json.dumps(result)[:2000], f"%{order_id}%"))
    return result


def reject(order_id: str, reason: str = "Rejected by user") -> dict:
    db = get_db()
    db.execute("UPDATE orders SET status=?, broker_response=? WHERE id=? AND status='pending_approval'",
               ("rejected", reason, order_id))
    db.audit("order.rejected", f"{order_id}: {reason}")
    return {"ok": True, "order_id": order_id, "status": "rejected"}


async def close_position(account_id: str, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
    account = account_row(account_id)
    broker = broker_for(account)
    try:
        res = await broker.close(ticket, symbol, volume)
        db = get_db()
        db.execute(
            "UPDATE positions SET status='closed', closed_at=?, pnl=COALESCE(?,pnl) WHERE ticket=?",
            (now(), res.get("pnl"), ticket),
        )
        db.audit("position.closed", json.dumps({"ticket": ticket, "result": res})[:2000])
        return {"ok": True, **res}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}


def recent_orders(limit: int = 40) -> list[dict]:
    return get_db().query("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))


def recent_positions(limit: int = 40) -> list[dict]:
    return get_db().query("SELECT * FROM positions ORDER BY opened_at DESC LIMIT ?", (limit,))


def audit_log(limit: int = 100) -> list[dict]:
    return get_db().query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


__all__ = [
    "account_row", "approve", "audit_log", "broker_for", "close_position", "decrypt",
    "execute", "list_accounts", "positions", "propose", "recent_orders", "recent_positions", "reject", "snapshot",
]
