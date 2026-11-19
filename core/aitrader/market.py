"""Market data with no API key required.

Primary source: Yahoo Finance chart endpoint (unofficial but stable enough for
quotes). Falls back to the connected MT5 terminal when available, then to the
last cached value. AI-TRADER never fabricates a price for a live order: if no
fresh quote is available the order is blocked.
"""
from __future__ import annotations

import asyncio
import time

import httpx

_ALIASES = {
    "XAUUSD": ["XAUUSD=X", "GC=F"],
    "XAGUSD": ["XAGUSD=X", "SI=F"],
    "WTIUSD": ["CL=F"],
    "US30": ["^DJI"],
    "SPX500": ["^GSPC"],
    "NAS100": ["^IXIC"],
    "GER40": ["^GDAXI"],
    "UK100": ["^FTSE"],
    "JP225": ["^N225"],
    "BTCUSD": ["BTC-USD"],
    "ETHUSD": ["ETH-USD"],
    "SOLUSD": ["SOL-USD"],
    "XRPUSD": ["XRP-USD"],
}

_cache: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 8.0
_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def yahoo_symbols(symbol: str) -> list[str]:
    s = (symbol or "").upper().replace("/", "").replace("-", "").strip()
    if s in _ALIASES:
        return _ALIASES[s]
    if len(s) == 6 and s.isalpha():
        return [f"{s}=X", s]
    return [symbol]


async def _yahoo(symbol: str) -> dict | None:
    async with httpx.AsyncClient(timeout=12, headers=_UA, follow_redirects=True) as client:
        for candidate in yahoo_symbols(symbol):
            try:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{candidate}",
                    params={"interval": "5m", "range": "5d"},
                )
                if resp.status_code >= 400:
                    continue
                data = resp.json()
                meta = ((data.get("chart") or {}).get("result") or [{}])[0].get("meta") or {}
                price = meta.get("regularMarketPrice") or meta.get("previousClose")
                if not price:
                    continue
                prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
                return {
                    "symbol": symbol.upper(),
                    "price": float(price),
                    "prev_close": float(prev),
                    "change_pct": round((float(price) - float(prev)) / float(prev) * 100, 3) if prev else 0.0,
                    "currency": meta.get("currency", ""),
                    "source": f"yahoo:{candidate}",
                    "ts": time.time(),
                }
            except Exception:
                continue
    return None


async def _mt5_quote(symbol: str) -> dict | None:
    try:
        import MetaTrader5 as mt5  # type: ignore

        tick = await asyncio.to_thread(mt5.symbol_info_tick, symbol)
        if tick is None:
            return None
        price = float(tick.bid or tick.last or 0)
        if not price:
            return None
        return {
            "symbol": symbol.upper(),
            "price": price,
            "prev_close": price,
            "change_pct": 0.0,
            "currency": "",
            "source": "mt5",
            "ts": time.time(),
        }
    except Exception:
        return None


async def get_quote(symbol: str) -> dict:
    key = symbol.upper().strip()
    cached = _cache.get(key)
    if cached and (time.time() - cached[0]) < CACHE_SECONDS:
        return cached[1]
    quote = await _yahoo(key)
    if not quote:
        quote = await _mt5_quote(key)
    if not quote:
        if cached:
            stale = dict(cached[1])
            stale["stale"] = True
            return stale
        raise LookupError(f"No quote available for '{symbol}'.")
    _cache[key] = (time.time(), quote)
    return quote


async def get_candles(symbol: str, interval: str = "1h", span: str = "1mo") -> list[dict]:
    """OHLCV candles from Yahoo (no key). Used by the technical-analysis tool."""
    async with httpx.AsyncClient(timeout=20, headers=_UA, follow_redirects=True) as client:
        for candidate in yahoo_symbols(symbol):
            try:
                resp = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{candidate}",
                    params={"interval": interval, "range": span},
                )
                if resp.status_code >= 400:
                    continue
                result = ((resp.json().get("chart") or {}).get("result") or [None])[0]
                if not result:
                    continue
                ts = result.get("timestamp") or []
                quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
                opens, highs, lows, closes, vols = (
                    quote.get("open") or [], quote.get("high") or [],
                    quote.get("low") or [], quote.get("close") or [],
                    quote.get("volume") or [],
                )
                candles = []
                for i, t in enumerate(ts):
                    c = closes[i] if i < len(closes) else None
                    if c is None:
                        continue
                    candles.append(
                        {
                            "t": t,
                            "o": opens[i] if i < len(opens) else c,
                            "h": highs[i] if i < len(highs) else c,
                            "l": lows[i] if i < len(lows) else c,
                            "c": c,
                            "v": vols[i] if i < len(vols) else 0,
                        }
                    )
                if candles:
                    return candles
            except Exception:
                continue
    return []


async def get_quotes(symbols: list[str]) -> list[dict]:
    results = await asyncio.gather(*[get_quote(s) for s in symbols], return_exceptions=True)
    out = []
    for s, r in zip(symbols, results):
        if isinstance(r, Exception):
            out.append({"symbol": s, "error": str(r)})
        else:
            out.append(r)
    return out
