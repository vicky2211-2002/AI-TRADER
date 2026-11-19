"""Hard risk gate. Every order passes through here, including agent orders.

Rules are evaluated independently and returned as a transparent checklist so
the UI can show exactly why an order was blocked. No rule can be bypassed by
the model: the agent can only *propose* an order.
"""
from __future__ import annotations

import time

from .brokers import BrokerError, contract_size
from .db import get_db, now


def _fail(checks: list, label: str, detail: str = "") -> None:
    checks.append({"ok": False, "label": label, "detail": detail})


def _pass(checks: list, label: str, detail: str = "") -> None:
    checks.append({"ok": True, "label": label, "detail": detail})


async def evaluate_order(
    order: dict,
    account: dict,
    positions: list[dict],
    settings: dict,
    quote: dict | None = None,
) -> dict:
    checks: list[dict] = []
    symbol = (order.get("symbol") or "").upper()
    side = (order.get("side") or "").upper()
    volume = float(order.get("volume") or 0)
    price = float(order.get("price") or (quote or {}).get("price") or 0)
    sl = float(order.get("sl") or 0)
    tp = float(order.get("tp") or 0)
    environment = (order.get("environment") or account.get("trade_mode") or "paper").upper()

    if settings.get("kill_switch"):
        _fail(checks, "Kill switch", "Trading is halted in Settings > Risk.")
    else:
        _pass(checks, "Kill switch", "Off")

    if environment == "LIVE" and not settings.get("allow_live_trading", False):
        _fail(checks, "Live trading disabled", "Enable it in Settings > Risk. Demo is the default.")
    else:
        _pass(checks, "Trading mode", environment)

    allowed = [s.upper() for s in settings.get("default_symbols", [])]
    allowed += [s.upper() for s in settings.get("autopilot_symbols", [])]
    allowed = list(dict.fromkeys(allowed))
    if allowed and symbol not in allowed:
        _fail(checks, "Symbol allow-list", f"{symbol} is not in {', '.join(allowed[:8])}")
    else:
        _pass(checks, "Symbol allow-list", symbol or "missing")

    if side not in ("BUY", "SELL"):
        _fail(checks, "Order side", "Must be BUY or SELL")
    else:
        _pass(checks, "Order side", side)

    if volume <= 0:
        _fail(checks, "Volume", "Volume must be greater than 0")
    elif volume > float(settings.get("max_lot_size", 0.1)):
        _fail(checks, "Max lot size", f"{volume} > {settings.get('max_lot_size')}")
    else:
        _pass(checks, "Max lot size", f"{volume} <= {settings.get('max_lot_size')}")

    if not sl or sl <= 0:
        _fail(checks, "Stop loss required", "Every order must carry a stop loss.")
    elif price and ((side == "BUY" and sl >= price) or (side == "SELL" and sl <= price)):
        _fail(checks, "Stop loss side", f"SL {sl} is on the wrong side of {price}")
    else:
        _pass(checks, "Stop loss", str(sl))

    if tp and price and ((side == "BUY" and tp <= price) or (side == "SELL" and tp >= price)):
        _fail(checks, "Take profit side", f"TP {tp} is on the wrong side of {price}")
    else:
        _pass(checks, "Take profit", str(tp) if tp else "optional")

    equity = float(account.get("equity") or account.get("balance") or 0)
    risk_usd = 0.0
    risk_pct = 0.0
    if price and sl:
        size = contract_size(symbol)
        risk_usd = round(abs(price - sl) * volume * size, 2)
        risk_pct = round((risk_usd / equity) * 100, 3) if equity else 0.0
        max_pct = float(settings.get("max_risk_per_trade_pct", 1.0))
        if risk_pct > max_pct:
            _fail(checks, "Risk per trade", f"{risk_pct}% > {max_pct}% (${risk_usd:.2f})")
        else:
            _pass(checks, "Risk per trade", f"{risk_pct}% (${risk_usd:.2f})")

    open_count = len(positions)
    max_open = int(settings.get("max_open_positions", 2))
    if open_count >= max_open:
        _fail(checks, "Max open positions", f"{open_count}/{max_open}")
    else:
        _pass(checks, "Max open positions", f"{open_count}/{max_open}")

    if any(p.get("symbol", "").upper() == symbol and p.get("status", "open") == "open" for p in positions):
        _fail(checks, "Duplicate exposure", f"An open position already exists on {symbol}")
    else:
        _pass(checks, "Duplicate exposure", "None")

    floating = float(account.get("floating_pnl") or 0)
    today_start = time.time() - (time.time() % 86400)
    db = get_db()
    row = db.one(
        "SELECT COALESCE(SUM(pnl),0) AS s FROM positions WHERE status='closed' AND closed_at>=?",
        (today_start,),
    )
    day_pnl = float(row["s"] if row else 0) + floating
    max_daily = float(settings.get("max_daily_loss_pct", 2.0))
    day_loss_pct = (-day_pnl / equity) * 100 if equity and day_pnl < 0 else 0.0
    if day_loss_pct >= max_daily:
        _fail(checks, "Daily loss limit", f"-{day_loss_pct:.2f}% reached (limit {max_daily}%)")
    else:
        _pass(checks, "Daily loss limit", f"{day_pnl:+.2f} today")

    peak = float(settings.get("_peak_equity") or equity or 0)
    dd_pct = ((peak - equity) / peak * 100) if peak else 0.0
    if dd_pct >= float(settings.get("max_drawdown_pct", 8.0)):
        _fail(checks, "Peak drawdown", f"{dd_pct:.2f}% (limit {settings.get('max_drawdown_pct')}%)")
    else:
        _pass(checks, "Peak drawdown", f"{dd_pct:.2f}%")

    if quote and quote.get("stale"):
        _fail(checks, "Fresh quote", "Quote is stale - refusing to size an order.")
    elif quote:
        _pass(checks, "Fresh quote", f"{quote.get('price')} from {quote.get('source')}")

    blocked = [c for c in checks if not c["ok"]]
    return {
        "allowed": not blocked,
        "checks": checks,
        "blocked_by": [c["label"] for c in blocked],
        "risk_usd": risk_usd,
        "risk_pct": risk_pct,
        "equity": equity,
    }


def track_equity(account_id: str, equity: float) -> None:
    if not equity:
        return
    db = get_db()
    key = f"_peak_equity"
    peak = float(db.get_setting(key, equity) or equity)
    if equity > peak:
        db.set_setting(key, equity)
    db.set_setting(f"_last_equity_{account_id}", equity)
