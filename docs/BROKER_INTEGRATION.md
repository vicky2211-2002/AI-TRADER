# Broker integration

AI-TRADER ships seven adapters. All of them sit behind the same order lifecycle:

```
proposal → risk gate → approval → Broker.place() → position + audit
```

Adding a broker does **not** change the gate. If you write your own adapter, keep
`place()` thin and let `risk.py` stay the only place that decides whether a trade
is allowed.

---

## Capability matrix

| Adapter | Platforms | Environments | Account | Positions | Place | Close | Notes |
|---------|-----------|--------------|---------|-----------|-------|-------|-------|
| **paper** | all | paper | ✅ | ✅ | ✅ | ✅ | Built-in simulator, Yahoo prices |
| **mt5** | Windows only | demo, live | ✅ | ✅ | ✅ | ✅ | Local terminal; verifies demo/live |
| **metaapi** | all | demo, live | ✅ | ✅ | ✅ | — | Cloud MT4/MT5; close in the MT5 app |
| **ccxt** | all | paper, live | ✅ | ✅ | ✅ | — | Needs `pip install ccxt`; close on the exchange |
| **alpaca** | all | paper, live | ✅ | ✅ | ✅ | ✅ | Stocks + crypto; qty = shares/coins |
| **oanda** | all | demo, live | ✅ | ✅ | ✅ | — | v20 FX/CFD; volume converted lots → units |
| **webhook** | all | demo, live | ✅ (static) | — | ✅ | — | HMAC-signed JSON to your executor |

A "—" means the base class raises `NotImplementedError`; close the position in the
broker's own UI, or extend the adapter. Requests fail loudly rather than
pretending to work.

---

## Paper

**Add account → Paper simulator → Starting balance.**

- Fills at the current Yahoo/MT5 quote with zero slippage and no commission.
- Balance starts at the value you set; closed PnL accumulates.
- Position `ticket` looks like `P96bee...` and is stored in SQLite.
- Perfect for rehearsing the approval flow and testing risk limits.

Limitations: no spread, no swap, no partial fills, no order book. A paper result
is a **plumbing test**, not evidence of edge.

---

## MetaTrader 5

> Windows only. The `MetaTrader5` Python package talks to a local terminal via
> IPC; there is no macOS/Linux build.

### 1. Install

```powershell
py -3.12 -m pip install MetaTrader5
```

### 2. Prepare the terminal

1. Open MT5 and log in to the **demo** account you intend to use.
2. Enable **Tools → Options → Expert Advisors → Allow algorithmic trading**.
3. Leave the terminal running. The adapter attaches to it; it does not need the
   GUI in the foreground, but the process must be alive.

### 3. Add the account (v0.1.1+ auto-detection)

| Field | Example | Notes |
|-------|---------|-------|
| Name | `Octa demo` | Label only |
| Broker | `MetaTrader 5 (local)` | |
| Environment | `demo` | Must match the real account type |
| Login | `108862992` | Numeric |
| Password | `••••••` | Stored encrypted |
| Server | `MetaQuotes-Demo` | Exactly as shown in MT5 |
| **Path** | *(auto-detected)* | **Optional** — core auto-finds `terminal64.exe` |
| Symbol suffix | `.m` / `_raw` | If your broker uses suffixed symbols |

**Auto-detection (v0.1.1+):**
The core checks these paths on startup:
1. `C:\Program Files\MetaTrader 5\terminal64.exe`
2. `C:\Program Files (x86)\MetaTrader 5\terminal64.exe`
3. `%APPDATA%\MetaQuotes\Terminal\*\terminal64.exe`

If found, the `Path` field is pre-filled in the UI. You only need to set it
manually for portable installs or multiple terminals.

Press **Test**. A successful test shows balance, equity, currency, leverage and
`trade_mode`.

### Demo/live verification

The adapter refuses to trade when the configuration and the account disagree:

- `environment=demo` + real account → **"Refusing to trade: account is REAL but
  environment is DEMO."**
- `environment=live` + demo account → **"Account is a DEMO account but the
  adapter is configured for LIVE."**

This is deliberate. It is the last line of defence against a mis-click that sends
a demo strategy to real money.

### Order mapping

| AI-TRADER | MT5 |
|-----------|-----|
| `side=BUY/SELL` | `ORDER_TYPE_BUY/SELL` |
| `volume` | lots (0.01 = micro) |
| `sl`, `tp` | absolute prices in the `order_send` request |
| `price` | live `ask`/`bid`; `deviation=20` points |
| `magic` | adapter magic number, so it can filter its own positions |
| `comment` | `AI-TRADER` |
| filling | `ORDER_FILLING_IOC` |

Symbols are uppercased and suffixed if configured. If a symbol is hidden, the
adapter calls `symbol_select(symbol, True)` before requesting a tick.

### Common MT5 errors

| Error | Cause | Fix |
|-------|-------|-----|
| `initialize failed: (-6, 'Terminal: Authorization failed')` | Wrong login/server/password | Re-check, log in manually once |
| `(-10005, 'IPC timeout')` | Terminal busy or not running | Open MT5, retry |
| `Symbol 'EURUSD.m' is unknown` | Suffix missing/wrong | Set `symbol_suffix` |
| `MT5 rejected order: 10027` | Algo trading disabled | Enable it in terminal options |
| `no account info` | Not logged in | Log in to the terminal |

### MT5 Status endpoint (v0.1.1+)

```
GET /api/brokers/mt5/status
```

Returns:
```json
{
  "mt5_available": true,
  "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
  "vcpp_ok": true,
  "message": "MT5 Python package available"
}
```

Used by the Electron shell to pre-fill the MT5 path field and show status in the
Brokers tab.

---

## MetaAPI

MetaAPI hosts a cloud terminal for your MT4/MT5 account, so macOS, Linux and
Android can trade without a local Windows box.

1. Create an account at <https://metaapi.cloud>, add your broker account, and
   wait for the state to become `DEPLOYED`.
2. Copy the **auth token** and the **account id**.
3. Add account → **MetaAPI cloud bridge**:

| Field | Value |
|-------|-------|
| Environment | `demo` or `live` (must match the broker account) |
| Token | MetaAPI auth token (secret) |
| Account id | MetaAPI account UUID |
| Region | `new-york`, `london`, `singapore`… |

The adapter calls:

```
GET  https://mt-client-api-v1.<region>.agiliumtrade.agiliumtrade.ai/users/current/accounts/<id>/account-information
GET  .../positions
POST .../trade
```

`trade` sends `actionType`, `symbol`, `volume`, `stopLoss`, `takeProfit`.

Limitations: `close()` is not implemented in 0.1.0 — close from the MT5 mobile
app or via a webhook executor. Position volume is reported as the broker reports
it; verify against the terminal for the first few trades.

---

## CCXT (crypto)

```powershell
py -3.12 -m pip install ccxt
```

| Field | Example | Notes |
|-------|---------|-------|
| Exchange id | `binance`, `bybit`, `okx`, `kraken`, `kucoin` | Must exist in `ccxt` |
| API key / secret | … | Create **trade-only**, no withdrawal |
| Market | `spot` or `future` | Sets `defaultType` |
| Environment | `paper` or `live` | Paper only changes the reported mode; placing still hits the exchange unless keys are testnet |

Symbol conversion:

- `BTCUSD` → `BTC/USDT` (when quote is USDT)
- `ETHUSD` → `ETH/USDT`
- `BTC/USDT` passes through unchanged

SL/TP are attached as `stopLoss`/`takeProfit` trigger prices when the exchange
supports them.

Limitations: `close()` is not implemented. Use the exchange UI or a reduce-only
order. Rate limiting is enabled (`enableRateLimit: True`).

Safety: never enable withdrawal permissions on an exchange key used here.
Consider IP allow-listing and a sub-account with a small balance.

---

## Alpaca

US stocks and crypto, paper and live.

1. Create keys at <https://app.alpaca.markets>.
2. Add account → **Alpaca**, environment `paper` for the paper endpoint.
3. Enter key id and secret.

| Environment | Base URL |
|-------------|----------|
| paper | `https://paper-api.alpaca.markets/v2` |
| live | `https://api.alpaca.markets/v2` |

Order payload:

```json
{
  "symbol": "AAPL",
  "qty": "10",
  "side": "buy",
  "type": "market",
  "time_in_force": "gtc",
  "order_class": "bracket",
  "take_profit": { "limit_price": "200" },
  "stop_loss": { "stop_price": "180" }
}
```

`volume` means **shares or coins**, not lots. `close()` deletes the position by
symbol (`DELETE /v2/positions/{symbol}`), so the symbol must be stored with the
position. Fractional crypto is allowed if the account permits it.

Risk math: `contract_size()` returns 1 for stock-like symbols, so risk in USD is
`|entry − stop| × qty`. For crypto pairs like `BTCUSD` it is `|entry − stop| ×
qty` too. Check the first ticket against the Alpaca dashboard.

---

## OANDA v20

FX and CFDs, practice and live.

| Field | Value |
|-------|-------|
| API token | Personal access token (secret) |
| Account id | e.g. `101-004-1234567-001` |
| Environment | `demo` (practice) or `live` |

```
practice: https://api-fxpractice.oanda.com/v3
live:     https://api-fxtrade.oanda.com/v3
```

- Symbols: `EURUSD` → `EUR_USD`.
- **Volume is converted from lots to units**: `0.01 EURUSD` → `1,000` units
  (contract size 100,000). This keeps sizing consistent with MT5.
- SL/TP are sent as `stopLossOnFill` / `takeProfitOnFill`.
- `close()` is not implemented; close in OANDA's web platform.

Start with the practice host until the account snapshot and the first fill match.

---

## Custom webhook

Use this to forward approved tickets to your own executor (a VPS process, a
serverless function, another broker API).

| Field | Value |
|-------|-------|
| URL | `https://your-executor.example.com/hook` |
| HMAC secret | long random string (secret) |

Request:

```
POST /hook
Content-Type: application/json
X-AI-TRADER-Signature: <hex hmac-sha256 of the raw body>

{"type":"order","order":{...},"ts":1795070698.33}
```

Verify the signature before acting:

```python
import hmac, hashlib
expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
ok = hmac.compare_digest(expected, request.headers["X-AI-TRADER-Signature"])
```

Respond with JSON `{"ticket": "...", "price": 1.2345}` to record the fill.

The webhook adapter reports a static account (balance 0) because it cannot query
your executor. `positions()` and `close()` are not implemented — the executor
owns that state.

Security: use HTTPS, verify the signature, reject replayed timestamps, and keep
the executor's own risk checks. The webhook is a second pair of eyes, not a
replacement for this app's gate.

---

## Symbol and contract-size model

`brokers.contract_size(symbol, cfg)` decides how price distance becomes money:

| Symbol pattern | Contract size | Meaning |
|----------------|---------------|---------|
| `BTC*`, `ETH*`, `SOL*`, `XRP*` | 1 | 1 unit of the coin |
| `XAU*` | 100 | 100 oz per lot |
| `XAG*` | 5,000 | 5,000 oz per lot |
| `US30`, `SPX500`, `NAS100`, `GER40`, `UK100`, `JP225` | 1 | 1 index unit |
| six letters (`EURUSD`, `GBPJPY`…) | 100,000 | standard FX lot |
| anything else | 1 | share/unit |

Override per account with `config.contract_size` (API only today). If your broker
uses non-standard contract sizes (some gold CFDs are 10 oz, some indices are
$1/point), set it — otherwise risk percentages will be wrong.

---

## Order statuses

| Status | Meaning |
|--------|---------|
| `blocked` | Risk gate said no; no approval card created |
| `pending_approval` | Passed the gate, waiting for a human |
| `approved` | Approval recorded, execution in progress |
| `filled` | Broker accepted; ticket stored |
| `failed` | Broker rejection or transport error; message stored |
| `rejected` | Human rejected before execution |

Every transition writes an audit row.

---

## Adding your own broker

1. Subclass `Broker` in `core/aitrader/brokers.py`.
2. Implement `account`, `positions`, `place`, optionally `close`, `history`.
3. Register the class in `BROKER_CLASSES` and add a `BROKER_CATALOG` entry so the
   UI knows which fields to render.
4. Use `contract_size()` for risk math; do not invent a second sizing path.
5. Raise `BrokerError` with an actionable message on failure.
6. Add a contract test with a fake HTTP transport.

Keep secrets in the `secret` dict only; it is decrypted per call and never
serialized back to the UI.

---

## Related docs

- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — live checklist and threat model
- [SKILLS_CATALOG.md](SKILLS_CATALOG.md) — `broker-connect` and `trade-execution`
- [API_REFERENCE.md](API_REFERENCE.md) — account and order endpoints
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — MT5 auto-detection and common errors