"""Broker adapters.

The core ships with:
  paper     - built-in simulator (default, always available)
  mt5       - local MetaTrader 5 terminal (Octa, IC Markets, etc.)
  ccxt      - 100+ crypto exchanges
  alpaca    - US stocks/crypto (paper + live)
  oanda     - FX/CFD REST v20
  metaapi   - cloud bridge to any MT4/MT5 account (works from macOS/Android)
  webhook   - forward approved orders to your own execution service

Adding a broker = subclass `Broker` and register it in `BROKER_CATALOG`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from .db import get_db, new_id, now
from .market import get_quote

MAGIC = 20261119


class BrokerError(RuntimeError):
    pass


def contract_size(symbol: str, cfg: dict | None = None) -> float:
    cfg = cfg or {}
    if cfg.get("contract_size"):
        return float(cfg["contract_size"])
    s = symbol.upper()
    if s.startswith(("BTC", "ETH", "SOL", "XRP")):
        return 1.0
    if s.startswith("XAU"):
        return 100.0
    if s.startswith("XAG"):
        return 5000.0
    if s in {"US30", "SPX500", "NAS100", "GER40", "UK100", "JP225"}:
        return 1.0
    if len(s) == 6 and s.isalpha():
        return 100000.0
    return 1.0


def _paper_pnl(pos: dict, price: float, cfg: dict | None) -> float:
    size = contract_size(pos["symbol"], cfg)
    diff = (price - pos["entry"]) if pos["side"].upper() == "BUY" else (pos["entry"] - price)
    return round(diff * float(pos["volume"]) * size, 4)


class Broker:
    id = "base"
    label = "Base"
    environments: tuple[str, ...] = ("paper",)

    def __init__(self, row: dict, secret: dict | None = None):
        self.row = row
        self.id = row.get("id", "")
        self.cfg = json.loads(row.get("config_json") or "{}")
        self.secret = secret or {}
        self.environment = row.get("environment", "paper")

    async def connect(self) -> dict:
        return {"ok": True}

    async def account(self) -> dict:
        raise NotImplementedError

    async def positions(self) -> list[dict]:
        return []

    async def place(self, order: dict) -> dict:
        raise NotImplementedError

    async def close(self, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
        raise NotImplementedError

    async def history(self, limit: int = 50) -> list[dict]:
        return []


# ---------------------------------------------------------------------------
class PaperBroker(Broker):
    id = "paper"
    label = "Paper (built-in simulator)"
    environments = ("paper",)

    async def account(self) -> dict:
        db = get_db()
        balance = float(self.cfg.get("balance", 10000))
        rows = db.query(
            "SELECT * FROM positions WHERE account_id=? AND status='open'", (self.id,)
        )
        pnl = 0.0
        for p in rows:
            try:
                q = await get_quote(p["symbol"])
                pnl += _paper_pnl(p, q["price"], self.cfg)
            except LookupError:
                pass
        closed = db.one(
            "SELECT COALESCE(SUM(pnl),0) AS s FROM positions WHERE account_id=? AND status='closed'",
            (self.id,),
        )
        return {
            "ok": True,
            "broker": "paper",
            "login": "paper",
            "server": "simulator",
            "currency": self.cfg.get("currency", "USD"),
            "balance": round(balance + float(closed["s"] if closed else 0), 2),
            "equity": round(balance + float(closed["s"] if closed else 0) + pnl, 2),
            "floating_pnl": round(pnl, 2),
            "margin_free": round(balance, 2),
            "leverage": 1,
            "trade_mode": "DEMO",
            "open_positions": len(rows),
        }

    async def positions(self) -> list[dict]:
        rows = get_db().query(
            "SELECT * FROM positions WHERE account_id=? AND status='open' ORDER BY opened_at DESC",
            (self.id,),
        )
        out = []
        for p in rows:
            p = dict(p)
            try:
                q = await get_quote(p["symbol"])
                p["price"] = q["price"]
                p["pnl"] = _paper_pnl(p, q["price"], self.cfg)
            except LookupError:
                p["price"] = p["entry"]
                p["pnl"] = 0.0
            p["broker"] = "paper"
            out.append(p)
        return out

    async def place(self, order: dict) -> dict:
        quote = await get_quote(order["symbol"])
        db = get_db()
        ticket = new_id("P")
        db.execute(
            "INSERT INTO positions(ticket,account_id,symbol,side,volume,entry,sl,tp,pnl,status,opened_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ticket,
                self.id,
                order["symbol"].upper(),
                order["side"].upper(),
                float(order["volume"]),
                quote["price"],
                float(order.get("sl") or 0),
                float(order.get("tp") or 0),
                0.0,
                "open",
                now(),
                order.get("reason", ""),
            ),
        )
        return {
            "ok": True,
            "ticket": ticket,
            "price": quote["price"],
            "message": f"Paper {order['side'].upper()} {order['volume']} {order['symbol']} @ {quote['price']}",
            "raw": {"quote": quote},
        }

    async def close(self, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
        db = get_db()
        pos = db.one("SELECT * FROM positions WHERE ticket=? AND account_id=?", (ticket, self.id))
        if not pos:
            raise BrokerError(f"Paper position {ticket} not found")
        try:
            q = await get_quote(pos["symbol"])
            price = q["price"]
        except LookupError:
            price = pos["entry"]
        pnl = _paper_pnl(pos, price, self.cfg)
        db.execute(
            "UPDATE positions SET status='closed', closed_at=?, pnl=?, note=note||? WHERE ticket=?",
            (now(), pnl, f" | closed@{price}", ticket),
        )
        return {"ok": True, "ticket": ticket, "price": price, "pnl": pnl}


# ---------------------------------------------------------------------------
class MT5Broker(Broker):
    id = "mt5"
    label = "MetaTrader 5 (local terminal)"
    environments = ("demo", "live")

    def __init__(self, row, secret=None):
        super().__init__(row, secret)
        self._connected = False
        self._mt5 = None

    def _module(self):
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except Exception as exc:  # pragma: no cover - platform dependent
                raise BrokerError(
                    "The MetaTrader5 Python package is not installed. "
                    "On Windows run: pip install MetaTrader5. "
                    "On macOS/Android use the 'metaapi' cloud bridge instead."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def _connect_sync(self) -> dict:
        mt5 = self._module()
        cfg = self.cfg
        kwargs: dict[str, Any] = {}
        if cfg.get("path"):
            kwargs["path"] = cfg["path"]
        if cfg.get("login"):
            kwargs["login"] = int(cfg["login"])
            kwargs["password"] = self.secret.get("password", "")
            kwargs["server"] = cfg.get("server", "")
        ok = mt5.initialize(**kwargs)
        if not ok:
            raise BrokerError(f"MT5 initialize failed: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            raise BrokerError("MT5 connected but returned no account info. Log in to the terminal first.")
        self._connected = True
        data = info._asdict()
        trade_mode = data.get("trade_mode")
        if self.environment == "live" and trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise BrokerError("Account is a DEMO account but the adapter is configured for LIVE.")
        if self.environment == "demo" and trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL:
            raise BrokerError("Refusing to trade: account is REAL but environment is DEMO.")
        return {
            "ok": True,
            "login": data.get("login"),
            "server": data.get("server"),
            "currency": data.get("currency"),
            "balance": data.get("balance"),
            "equity": data.get("equity"),
            "leverage": data.get("leverage"),
            "trade_mode": "DEMO" if trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "LIVE",
            "company": data.get("company"),
        }

    async def connect(self) -> dict:
        return await asyncio.to_thread(self._connect_sync)

    async def account(self) -> dict:
        def _run():
            mt5 = self._module()
            info = mt5.account_info()
            if info is None:
                raise BrokerError("MT5 is not connected")
            d = info._asdict()
            d["ok"] = True
            d["broker"] = "mt5"
            d["trade_mode"] = "DEMO" if d.get("trade_mode") == mt5.ACCOUNT_TRADE_MODE_DEMO else "LIVE"
            return d

        return await asyncio.to_thread(_run)

    async def positions(self) -> list[dict]:
        def _run():
            mt5 = self._module()
            out = []
            for p in mt5.positions_get() or []:
                d = p._asdict()
                if d.get("magic") not in (0, MAGIC):
                    continue
                d["side"] = "BUY" if d.get("type") == mt5.POSITION_TYPE_BUY else "SELL"
                d["ticket"] = str(d.get("ticket"))
                d["broker"] = "mt5"
                out.append(d)
            return out

        return await asyncio.to_thread(_run)

    def _place_sync(self, order: dict) -> dict:
        mt5 = self._module()
        symbol = order["symbol"].upper()
        if self.cfg.get("symbol_suffix") and not symbol.endswith(self.cfg["symbol_suffix"]):
            symbol = symbol + self.cfg["symbol_suffix"]
        info = mt5.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"Symbol '{symbol}' is unknown to this broker.")
        if not info.visible:
            mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"No tick for '{symbol}'.")
        side = order["side"].upper()
        price = tick.ask if side == "BUY" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(order["volume"]),
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(order.get("sl") or 0),
            "tp": float(order.get("tp") or 0),
            "deviation": int(self.cfg.get("deviation", 20)),
            "magic": MAGIC,
            "comment": "AI-TRADER",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None:
            raise BrokerError(f"order_send returned None: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerError(f"MT5 rejected order: {result.retcode} {result.comment}")
        return {
            "ok": True,
            "ticket": str(result.order),
            "price": result.price,
            "message": f"MT5 {side} {order['volume']} {symbol} @ {result.price}",
            "raw": result._asdict(),
        }

    async def place(self, order: dict) -> dict:
        return await asyncio.to_thread(self._place_sync, order)

    def _close_sync(self, ticket: str) -> dict:
        mt5 = self._module()
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            raise BrokerError(f"Position {ticket} not found")
        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        closing_buy = pos.type == mt5.POSITION_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
            "position": int(ticket),
            "price": tick.ask if closing_buy else tick.bid,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "AI-TRADER close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerError(f"Close failed: {getattr(result, 'comment', 'no result')}")
        return {"ok": True, "ticket": ticket, "price": result.price}

    async def close(self, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
        return await asyncio.to_thread(self._close_sync, ticket)


# ---------------------------------------------------------------------------
class CCXTBroker(Broker):
    id = "ccxt"
    label = "Crypto via CCXT"
    environments = ("paper", "live")

    def _exchange(self):
        try:
            import ccxt  # type: ignore
        except Exception as exc:
            raise BrokerError("ccxt is not installed. Run: pip install ccxt") from exc
        name = self.cfg.get("exchange", "binance")
        if not hasattr(ccxt, name):
            raise BrokerError(f"Unknown ccxt exchange '{name}'")
        opts = {
            "apiKey": self.secret.get("api_key", ""),
            "secret": self.secret.get("api_secret", ""),
            "password": self.secret.get("password", ""),
            "enableRateLimit": True,
            "options": {"defaultType": self.cfg.get("market_type", "spot")},
        }
        return getattr(ccxt, name)({k: v for k, v in opts.items() if v != ""})

    async def account(self) -> dict:
        def _run():
            ex = self._exchange()
            bal = ex.fetch_balance()
            total = bal.get("total", {})
            usdt = float(total.get("USDT") or total.get("USD") or 0)
            return {
                "ok": True,
                "broker": "ccxt",
                "login": self.cfg.get("exchange"),
                "server": self.cfg.get("market_type", "spot"),
                "currency": "USDT",
                "balance": usdt,
                "equity": usdt,
                "trade_mode": "DEMO" if self.environment == "paper" else "LIVE",
                "balances": {k: v for k, v in total.items() if v},
            }

        return await asyncio.to_thread(_run)

    async def positions(self) -> list[dict]:
        def _run():
            ex = self._exchange()
            out = []
            if ex.has.get("fetchPositions"):
                for p in ex.fetch_positions() or []:
                    out.append(
                        {
                            "ticket": str(p.get("id") or ""),
                            "symbol": p.get("symbol"),
                            "side": (p.get("side") or "").upper(),
                            "volume": p.get("contracts") or 0,
                            "entry": p.get("entryPrice") or 0,
                            "pnl": p.get("unrealizedPnl") or 0,
                            "broker": "ccxt",
                        }
                    )
            return out

        return await asyncio.to_thread(_run)

    async def place(self, order: dict) -> dict:
        def _run():
            ex = self._exchange()
            symbol = order["symbol"]
            if "/" not in symbol:
                base = symbol[:-3] if symbol.upper().endswith("USD") else symbol[:-4]
                symbol = f"{base}/USDT" if self.cfg.get("quote", "USDT") == "USDT" else f"{base}/USD"
            params = {}
            if order.get("sl"):
                params["stopLoss"] = {"triggerPrice": float(order["sl"])}
            if order.get("tp"):
                params["takeProfit"] = {"triggerPrice": float(order["tp"])}
            res = ex.create_order(
                symbol, order.get("order_type", "market"), order["side"].lower(),
                float(order["volume"]), None, params,
            )
            return {
                "ok": True,
                "ticket": str(res.get("id")),
                "price": res.get("average") or res.get("price") or 0,
                "message": f"ccxt {order['side']} {order['volume']} {symbol}",
                "raw": res,
            }

        return await asyncio.to_thread(_run)

    async def close(self, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
        raise BrokerError("Close the position from your exchange UI or via a reduce-only market order.")


# ---------------------------------------------------------------------------
class AlpacaBroker(Broker):
    id = "alpaca"
    label = "Alpaca (stocks + crypto)"
    environments = ("paper", "live")

    def _client(self) -> httpx.AsyncClient:
        live = self.environment == "live"
        base = "https://api.alpaca.markets/v2" if live else "https://paper-api.alpaca.markets/v2"
        headers = {
            "APCA-API-KEY-ID": self.secret.get("api_key", ""),
            "APCA-API-SECRET-KEY": self.secret.get("api_secret", ""),
            "Content-Type": "application/json",
        }
        return httpx.AsyncClient(base_url=base, headers=headers, timeout=30)

    @staticmethod
    def _symbol(symbol: str) -> str:
        s = symbol.upper()
        if s.endswith("USD") and len(s) > 5:
            return s[:-3] + "/USD"
        return s

    async def account(self) -> dict:
        async with self._client() as c:
            r = await c.get("/account")
            if r.status_code >= 400:
                raise BrokerError(f"Alpaca {r.status_code}: {r.text[:300]}")
            d = r.json()
        return {
            "ok": True,
            "broker": "alpaca",
            "login": d.get("account_number"),
            "server": "alpaca-paper" if self.environment != "live" else "alpaca-live",
            "currency": d.get("currency", "USD"),
            "balance": float(d.get("cash") or 0),
            "equity": float(d.get("equity") or 0),
            "trade_mode": "LIVE" if self.environment == "live" else "DEMO",
            "buying_power": float(d.get("buying_power") or 0),
        }

    async def positions(self) -> list[dict]:
        async with self._client() as c:
            r = await c.get("/positions")
            if r.status_code >= 400:
                return []
            rows = r.json()
        return [
            {
                "ticket": p.get("asset_id"),
                "symbol": p.get("symbol"),
                "side": (p.get("side") or "").upper(),
                "volume": abs(float(p.get("qty") or 0)),
                "entry": float(p.get("avg_entry_price") or 0),
                "price": float(p.get("current_price") or 0),
                "pnl": float(p.get("unrealized_pl") or 0),
                "broker": "alpaca",
            }
            for p in rows
        ]

    async def place(self, order: dict) -> dict:
        payload: dict[str, Any] = {
            "symbol": self._symbol(order["symbol"]),
            "qty": str(order["volume"]),
            "side": order["side"].lower(),
            "type": order.get("order_type", "market"),
            "time_in_force": "gtc",
        }
        if order.get("sl") or order.get("tp"):
            payload["order_class"] = "bracket"
            if order.get("tp"):
                payload["take_profit"] = {"limit_price": str(order["tp"])}
            if order.get("sl"):
                payload["stop_loss"] = {"stop_price": str(order["sl"])}
        async with self._client() as c:
            r = await c.post("/orders", json=payload)
            if r.status_code >= 400:
                raise BrokerError(f"Alpaca {r.status_code}: {r.text[:300]}")
            d = r.json()
        return {"ok": True, "ticket": str(d.get("id")), "price": 0, "message": f"Alpaca order {d.get('status')}", "raw": d}

    async def close(self, ticket: str, symbol: str | None = None, volume: float | None = None) -> dict:
        if not symbol:
            raise BrokerError("Alpaca close requires the symbol.")
        async with self._client() as c:
            r = await c.delete(f"/positions/{self._symbol(symbol)}")
            if r.status_code >= 400:
                raise BrokerError(f"Alpaca close {r.status_code}: {r.text[:300]}")
            return {"ok": True, "ticket": ticket, "raw": r.json()}


# ---------------------------------------------------------------------------
class OandaBroker(Broker):
    id = "oanda"
    label = "OANDA v20 (FX/CFD)"
    environments = ("demo", "live")

    def _client(self) -> httpx.AsyncClient:
        base = (
            "https://api-fxpractice.oanda.com/v3"
            if self.environment != "live"
            else "https://api-fxtrade.oanda.com/v3"
        )
        return httpx.AsyncClient(
            base_url=base,
            headers={
                "Authorization": f"Bearer {self.secret.get('api_token','')}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    @staticmethod
    def _instr(symbol: str) -> str:
        s = symbol.upper().replace("/", "_")
        if "_" in s:
            return s
        return s[:3] + "_" + s[3:6]

    async def account(self) -> dict:
        acct = self.cfg.get("account_id", "")
        async with self._client() as c:
            r = await c.get(f"/accounts/{acct}/summary")
            if r.status_code >= 400:
                raise BrokerError(f"OANDA {r.status_code}: {r.text[:300]}")
            d = r.json().get("account", {})
        return {
            "ok": True,
            "broker": "oanda",
            "login": d.get("id"),
            "server": "oanda-practice" if self.environment != "live" else "oanda-live",
            "currency": d.get("currency"),
            "balance": float(d.get("balance") or 0),
            "equity": float(d.get("NAV") or 0),
            "trade_mode": "LIVE" if self.environment == "live" else "DEMO",
        }

    async def positions(self) -> list[dict]:
        acct = self.cfg.get("account_id", "")
        async with self._client() as c:
            r = await c.get(f"/accounts/{acct}/openPositions")
            if r.status_code >= 400:
                return []
            rows = r.json().get("positions") or []
        out = []
        for p in rows:
            long_units = float(p.get("long", {}).get("units", 0))
            units = long_units or float(p.get("short", {}).get("units", 0))
            size = contract_size(p.get("instrument", "").replace("_", ""))
            out.append(
                {
                    "ticket": p.get("id"),
                    "symbol": p.get("instrument", "").replace("_", ""),
                    "side": "BUY" if long_units > 0 else "SELL",
                    "volume": round(abs(units) / size, 4),
                    "entry": float(p.get("long", {}).get("averagePrice") or p.get("short", {}).get("averagePrice") or 0),
                    "pnl": float(p.get("unrealizedPL") or 0),
                    "broker": "oanda",
                }
            )
        return out

    async def place(self, order: dict) -> dict:
        acct = self.cfg.get("account_id", "")
        # AI-TRADER expresses volume in lots, like MT5. OANDA takes units.
        units = float(order["volume"]) * contract_size(order["symbol"])
        if order["side"].upper() == "SELL":
            units = -units
        payload: dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": self._instr(order["symbol"]),
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if order.get("sl"):
            payload["order"]["stopLossOnFill"] = {"price": str(order["sl"])}
        if order.get("tp"):
            payload["order"]["takeProfitOnFill"] = {"price": str(order["tp"])}
        async with self._client() as c:
            r = await c.post(f"/accounts/{acct}/orders", json=payload)
            if r.status_code >= 400:
                raise BrokerError(f"OANDA {r.status_code}: {r.text[:300]}")
            d = r.json()
        fill = (d.get("orderFillTransaction") or {})
        return {
            "ok": True,
            "ticket": fill.get("id") or "",
            "price": float(fill.get("price") or 0),
            "message": f"OANDA filled {fill.get('units')} {fill.get('instrument')}",
            "raw": d,
        }


# ---------------------------------------------------------------------------
class MetaApiBroker(Broker):
    """Cloud bridge: reach MT4/MT5 from macOS/Android through MetaAPI."""

    id = "metaapi"
    label = "MetaAPI cloud (MT4/MT5 bridge)"
    environments = ("demo", "live")

    def _base(self) -> str:
        region = self.cfg.get("region", "new-york")
        return f"https://mt-client-api-v1.{region}.agiliumtrade.agiliumtrade.ai"

    def _headers(self) -> dict:
        return {"auth-token": self.secret.get("token", ""), "Content-Type": "application/json"}

    async def account(self) -> dict:
        acct = self.cfg.get("account_id", "")
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{self._base()}/users/current/accounts/{acct}/account-information",
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise BrokerError(f"MetaAPI {r.status_code}: {r.text[:300]}")
            d = r.json()
        return {
            "ok": True,
            "broker": "metaapi",
            "login": d.get("login"),
            "server": d.get("server"),
            "currency": d.get("currency"),
            "balance": d.get("balance"),
            "equity": d.get("equity"),
            "trade_mode": "LIVE" if self.environment == "live" else "DEMO",
        }

    async def positions(self) -> list[dict]:
        acct = self.cfg.get("account_id", "")
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{self._base()}/users/current/accounts/{acct}/positions",
                headers=self._headers(),
            )
            if r.status_code >= 400:
                return []
            rows = r.json()
        out = []
        for p in rows:
            out.append(
                {
                    "ticket": p.get("id"),
                    "symbol": p.get("symbol"),
                    "side": (p.get("type") or "").replace("POSITION_TYPE_", ""),
                    "volume": p.get("volume"),
                    "entry": p.get("openPrice"),
                    "pnl": p.get("profit"),
                    "broker": "metaapi",
                }
            )
        return out

    async def place(self, order: dict) -> dict:
        acct = self.cfg.get("account_id", "")
        payload = {
            "actionType": "ORDER_TYPE_BUY" if order["side"].upper() == "BUY" else "ORDER_TYPE_SELL",
            "symbol": order["symbol"].upper(),
            "volume": float(order["volume"]),
        }
        if order.get("sl"):
            payload["stopLoss"] = float(order["sl"])
        if order.get("tp"):
            payload["takeProfit"] = float(order["tp"])
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self._base()}/users/current/accounts/{acct}/trade",
                headers=self._headers(),
                json=payload,
            )
            if r.status_code >= 400:
                raise BrokerError(f"MetaAPI {r.status_code}: {r.text[:300]}")
            return {"ok": True, "ticket": "", "price": 0, "raw": r.json(), "message": "MetaAPI order accepted"}


# ---------------------------------------------------------------------------
class WebhookBroker(Broker):
    id = "webhook"
    label = "Custom webhook / execution service"
    environments = ("demo", "live")

    async def account(self) -> dict:
        return {"ok": True, "broker": "webhook", "login": "webhook", "server": self.cfg.get("url", ""),
                "currency": "USD", "balance": 0, "equity": 0,
                "trade_mode": "LIVE" if self.environment == "live" else "DEMO"}

    async def place(self, order: dict) -> dict:
        url = self.cfg.get("url", "")
        if not url.startswith(("http://", "https://")):
            raise BrokerError("Webhook URL must start with http:// or https://")
        body = json.dumps({"type": "order", "order": order, "ts": time.time()}).encode()
        headers = {"Content-Type": "application/json"}
        secret = self.secret.get("secret", "")
        if secret:
            headers["X-AI-TRADER-Signature"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, content=body, headers=headers)
            if r.status_code >= 400:
                raise BrokerError(f"Webhook {r.status_code}: {r.text[:300]}")
            try:
                return {"ok": True, "ticket": str(r.json().get("ticket", "")), "price": r.json().get("price", 0), "raw": r.json()}
            except Exception:
                return {"ok": True, "ticket": "", "price": 0, "message": r.text[:300]}


BROKER_CLASSES = {
    "paper": PaperBroker,
    "mt5": MT5Broker,
    "ccxt": CCXTBroker,
    "alpaca": AlpacaBroker,
    "oanda": OandaBroker,
    "metaapi": MetaApiBroker,
    "webhook": WebhookBroker,
}

BROKER_CATALOG = [
    {
        "id": "paper",
        "label": "Paper simulator",
        "tagline": "Built-in, zero setup, no real money.",
        "environments": ["paper"],
        "fields": [{"key": "balance", "label": "Starting balance", "type": "number", "default": 10000}],
        "docs": "docs/BROKER_INTEGRATION.md#paper",
    },
    {
        "id": "mt5",
        "label": "MetaTrader 5 (local)",
        "tagline": "Octa, IC Markets, Exness, any MT5 broker. Windows only.",
        "environments": ["demo", "live"],
        "fields": [
            {"key": "login", "label": "MT5 login", "type": "text"},
            {"key": "password", "label": "Password", "type": "password", "secret": True},
            {"key": "server", "label": "Server", "type": "text", "placeholder": "OctaFX-Demo"},
            {"key": "path", "label": "terminal64.exe (optional)", "type": "text"},
            {"key": "symbol_suffix", "label": "Symbol suffix (e.g. .m)", "type": "text"},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#metatrader-5",
    },
    {
        "id": "metaapi",
        "label": "MetaAPI cloud bridge",
        "tagline": "MT4/MT5 from macOS, Linux or Android.",
        "environments": ["demo", "live"],
        "fields": [
            {"key": "token", "label": "MetaAPI token", "type": "password", "secret": True},
            {"key": "account_id", "label": "MetaAPI account id", "type": "text"},
            {"key": "region", "label": "Region", "type": "text", "default": "new-york"},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#metaapi",
    },
    {
        "id": "ccxt",
        "label": "Crypto exchange (CCXT)",
        "tagline": "Binance, Bybit, OKX, Kraken, KuCoin and 100+.",
        "environments": ["paper", "live"],
        "fields": [
            {"key": "exchange", "label": "Exchange id", "type": "text", "default": "binance"},
            {"key": "api_key", "label": "API key", "type": "password", "secret": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "secret": True},
            {"key": "market_type", "label": "Market", "type": "select", "options": ["spot", "future"], "default": "spot"},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#ccxt",
    },
    {
        "id": "alpaca",
        "label": "Alpaca",
        "tagline": "US stocks and crypto, paper + live REST.",
        "environments": ["paper", "live"],
        "fields": [
            {"key": "api_key", "label": "API key id", "type": "password", "secret": True},
            {"key": "api_secret", "label": "API secret", "type": "password", "secret": True},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#alpaca",
    },
    {
        "id": "oanda",
        "label": "OANDA v20",
        "tagline": "FX and CFDs, practice and live.",
        "environments": ["demo", "live"],
        "fields": [
            {"key": "api_token", "label": "API token", "type": "password", "secret": True},
            {"key": "account_id", "label": "Account id", "type": "text"},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#oanda",
    },
    {
        "id": "webhook",
        "label": "Custom webhook",
        "tagline": "Forward approved tickets to your own executor (HMAC signed).",
        "environments": ["demo", "live"],
        "fields": [
            {"key": "url", "label": "Webhook URL", "type": "text"},
            {"key": "secret", "label": "HMAC secret", "type": "password", "secret": True},
        ],
        "docs": "docs/BROKER_INTEGRATION.md#webhook",
    },
]


def build_broker(row: dict, secret: dict | None = None) -> Broker:
    cls = BROKER_CLASSES.get(row.get("broker", "paper"))
    if not cls:
        raise BrokerError(f"Unknown broker adapter '{row.get('broker')}'")
    return cls(row, secret or {})
