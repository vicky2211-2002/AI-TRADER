# API reference

Base URL: `http://127.0.0.1:8765`

- All endpoints are under `/api` except the optional static UI at `/`.
- Interactive OpenAPI docs: <http://127.0.0.1:8765/docs> (FastAPI default).
- Content type: `application/json` unless noted.
- Errors: `{"detail": "message"}` with 400/401/404/500.

### Authentication

If the core was started with `AI_TRADER_TOKEN`, every `/api/*` request needs one
of:

```
X-AI-Trader-Token: <token>
Authorization: Bearer <token>
```

Missing or wrong token → `401 {"detail":"Unauthorized"}`.

### Conventions

- Timestamps are Unix seconds (float).
- IDs are prefixed: `prv_`, `mcp_`, `conv_`, `ord_`, `apr_`, `acc_`, `P...`
  (paper ticket).
- `environment` is `paper`, `demo` or `live`.
- `side` is `BUY` or `SELL`.
- Secrets are never returned; expect `has_key`, `key_hint`, or masked env values.

---

## System

### `GET /api/health`

```json
{ "ok": true, "app": "AI-TRADER", "version": "0.1.0", "ts": 1795070673.26 }
```

### `GET /api/system`

```json
{
  "app": "AI-TRADER",
  "version": "0.1.0",
  "platform": "Windows",
  "machine": "AMD64",
  "python": "3.12.7",
  "home": "C:\\Users\\me\\AppData\\Roaming\\AI-TRADER",
  "data_dir": "...\\AI-TRADER\\data",
  "skills_dir": "...\\AI-TRADER\\skills",
  "vault": "fernet",
  "host": "127.0.0.1",
  "port": 8765,
  "mt5_available": true,
  "node": true,
  "uv": false
}
```

### `GET /api/bootstrap`

Everything the UI needs on first paint: `system`, `settings`, `providers`, `mcp`,
`skills`, `accounts`, `broker_catalog`, `conversations` (50 newest), `approvals`
(pending).

---

## Providers

### `GET /api/providers`

Array of public provider rows:

```json
[{
  "id": "prv_...",
  "name": "Groq",
  "kind": "openai",
  "base_url": "https://api.groq.com/openai/v1",
  "model": "qwen/qwen3.8-27b",
  "models": ["qwen/qwen3.8-27b"],
  "headers": {},
  "enabled": true,
  "is_default": true,
  "has_key": true,
  "key_hint": "••••abcd",
  "last_status": "ok",
  "last_latency_ms": 480,
  "last_checked": 1795070000.0
}]
```

### `POST /api/providers`

```json
{
  "name": "Groq",
  "kind": "openai",
  "base_url": "https://api.groq.com/openai/v1",
  "model": "qwen/qwen3.8-27b",
  "models": ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"],
  "headers": {},
  "api_key": "gsk_...",
  "enabled": true,
  "is_default": true
}
```

`kind` ∈ `openai | anthropic | google | azure`. Returns the public row.

### `PATCH /api/providers/{id}`

Any of: `name`, `kind`, `base_url`, `model`, `models`, `headers`, `enabled`,
`is_default`, `api_key`, `clear_key`. Setting `is_default=true` clears the flag on
all other providers.

### `DELETE /api/providers/{id}`

`{"ok": true}`. The encrypted key is deleted with the row.

### `POST /api/providers/{id}/test`

Sends a tiny prompt, records status.

```json
{ "ok": true, "latency_ms": 412, "reply": "OK", "error": null, "hint": null }
```

Failure example:

```json
{ "ok": false, "error": "401 Unauthorized", "hint": "Check the API key." }
```

### `GET /api/providers/{id}/models`

`{"models": ["...", "..."]}`. Updates the stored list when non-empty.

---

## MCP servers

### `GET /api/mcp` · `GET /api/mcp/catalog`

Server rows include `status` (`running|stopped|error`), `error`, `tool_count`,
`tools[]`. Catalog items add `installed: bool`.

### `POST /api/mcp`

```json
{
  "name": "Context7",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "url": "",
  "env": {},
  "enabled": true,
  "auto_start": false,
  "category": "docs",
  "notes": ""
}
```

For HTTP: `transport: "http"`, `url: "https://host/mcp"`, `command`/`args` empty.

### `PATCH /api/mcp/{id}`

Partial: `name`, `transport`, `command`, `args`, `url`, `env`, `enabled`,
`auto_start`, `category`, `notes`. Disabling stops a running server. `env`
values that are blank or equal to the masked value shown by `GET /api/mcp`
keep the stored secret, so editing a server never wipes its keys. Restart the
server to apply command/env changes.

### `DELETE /api/mcp/{id}`

Stops the process and deletes the row.

### `POST /api/mcp/{id}/start`

```json
{ "ok": true, "tools": [{"name": "...", "description": "...", "input_schema": {}}],
  "server_info": {...} }
```

On failure: `{"ok": false, "error": "..."}` (HTTP 200).

### `POST /api/mcp/{id}/stop`

`{"ok": true}`.

### `POST /api/mcp/{id}/test`

Starts if needed and returns tools plus `tool_count`, `server_info`. Includes
`stderr` tail on failure.

### `POST /api/mcp/{id}/call`

```json
{ "tool": "resolve-library-id", "arguments": { "libraryName": "react" } }
```

Returns `{"ok": true, "result": <raw MCP result>, "text": "flattened text"}`.

---

## Skills

### `GET /api/skills`

Array: `id`, `name`, `description`, `path`, `enabled`, `source`, `size`,
`preview`.

### `GET /api/skills/{id}`

`{"id": "...", "content": "---\nname: ...\n---\n..."}`

### `POST /api/skills`

```json
{ "id": "my-playbook", "name": "My Playbook", "description": "...",
  "content": "---\nname: My Playbook\n---\n\n# ...", "enabled": true }
```

`id` is optional; it is derived from `name` when omitted. Must match
`^[a-z0-9][a-z0-9-_]{1,63}$`.

### `PUT /api/skills/{id}`

`name`, `description`, `content`, `enabled`. Empty `content` means “leave the file
alone” (used by the enable toggle).

### `DELETE /api/skills/{id}`

Deletes the row and `skills/<id>/` from disk.

### `POST /api/skills/rescan`

`{"synced": 16}` — imports `SKILL.md` folders added outside the app.

---

## Brokers and accounts

### `GET /api/brokers`

Static catalog used to render the form: `id`, `label`, `tagline`,
`environments[]`, `fields[]`, `docs`.

### `POST /api/accounts`

```json
{
  "name": "Octa demo",
  "broker": "mt5",
  "environment": "demo",
  "config": { "login": "108862992", "server": "MetaQuotes-Demo", "symbol_suffix": "" },
  "secret": { "password": "..." },
  "enabled": true
}
```

Secret keys by broker:

| Broker | `secret` keys |
|--------|---------------|
| mt5 | `password` |
| metaapi | `token` |
| ccxt | `api_key`, `api_secret`, `password` (optional) |
| alpaca | `api_key`, `api_secret` |
| oanda | `api_token` |
| webhook | `secret` |

### `PATCH /api/accounts/{id}`

Partial `name`, `environment`, `config`, `secret`, `enabled`. Secrets merge; send
a new non-empty value to replace one, blank or masked values keep the stored
secret.

### `DELETE /api/accounts/{id}`

Removes the local account. Broker positions are untouched.

### `POST /api/accounts/{id}/test`

```json
{ "ok": true, "account": { "balance": 10000, "equity": 10000, "trade_mode": "DEMO" } }
```

Failure: `{"ok": false, "error": "..."}`.

### `GET /api/accounts/{id}/snapshot`

Live account snapshot from the adapter (`balance`, `equity`, `floating_pnl`,
`trade_mode`, `open_positions`, …).

`account_id` may be omitted on order/position endpoints when exactly one account
is configured; otherwise the first enabled account is used.

---

## Market data

### `GET /api/market/quote?symbol=EURUSD`

```json
{
  "symbol": "EURUSD",
  "price": 1.0971,
  "prev_close": 1.105,
  "change_pct": -0.715,
  "currency": "USD",
  "source": "yahoo:EURUSD=X",
  "ts": 1795070691.19,
  "stale": false
}
```

### `GET /api/market/quotes?symbols=EURUSD,GBPUSD,XAUUSD`

`{"quotes": [...]}` (max 20 symbols).

### `GET /api/market/candles?symbol=EURUSD&interval=1h&span=1mo`

`{"symbol":"EURUSD","candles":[{"t":...,"o":...,"h":...,"l":...,"c":...,"v":...}]}`

`interval`: `15m`, `1h`, `4h`, `1d`. `span`: Yahoo ranges such as `5d`, `1mo`,
`6mo`, `1y`.

### `GET /api/market/news?query=gold&limit=8`

`{"items": [{"title": "...", "link": "...", "published": "...", "source": "..."}]}`

---

## Orders

### `GET /api/orders?limit=40`

Recent orders, newest first. Fields include `id`, `account_id`, `symbol`, `side`,
`volume`, `order_type`, `price`, `sl`, `tp`, `status`, `risk_usd`, `risk_pct`,
`reason`, `ticket`, `broker_response`, `created_at`, `pnl`.

### `POST /api/orders`

```json
{
  "account_id": "acc_...",
  "symbol": "EURUSD",
  "side": "BUY",
  "volume": 0.02,
  "sl": 1.09,
  "tp": 1.13,
  "order_type": "market",
  "price": 0,
  "reason": "Donchian breakout",
  "environment": null
}
```

Response:

```json
{
  "order_id": "ord_...",
  "status": "pending_approval",
  "allowed": true,
  "checks": [{"ok": true, "label": "Risk per trade", "detail": "0.142% ($14.20)"}],
  "blocked_by": [],
  "risk_usd": 14.2,
  "risk_pct": 0.142,
  "quote": {...},
  "account": {...}
}
```

`status` is `blocked`, `pending_approval`, or `filled` when approval is disabled
for an auto-executed path. A blocked request still returns HTTP 200 — read
`allowed`/`blocked_by`.

### `POST /api/orders/{id}/approve`

```json
{ "ok": true, "ticket": "P96bee...", "price": 1.0971, "message": "Paper BUY ..." }
```

Errors: `400` with `Order not found`, `already resolved`, or the broker message.

### `POST /api/orders/{id}/reject`

```json
{ "reason": "Spread too wide" }
```

`{"ok": true}`.

---

## Positions

### `GET /api/positions?account_id=acc_...`

```json
{
  "account_id": "acc_...",
  "positions": [{
    "ticket": "P96bee...", "account_id": "acc_...", "symbol": "EURUSD",
    "side": "BUY", "volume": 0.02, "entry": 1.0971, "sl": 1.09, "tp": 1.13,
    "pnl": 0.0, "status": "open", "price": 1.0971, "broker": "paper"
  }]
}
```

### `POST /api/positions/{ticket}/close`

```json
{ "account_id": "acc_...", "symbol": "EURUSD", "volume": null }
```

`{"ok": true, "ticket": "...", "price": 1.0971, "pnl": 0.0}`

---

## Approvals

### `GET /api/approvals?status=pending`

Rows: `id`, `kind` (`order|close_position|mcp_tool`), `payload_json`, `status`,
`created_at`, `resolved_at`, `result_json`.

### `POST /api/approvals/{id}/approve`

Dispatches by kind and returns the execution result. Single use.

### `POST /api/approvals/{id}/reject`

`{"ok": true}`.

---

## Audit

### `GET /api/audit?limit=100`

```json
[{ "ts": 1795070000.0, "actor": "ui", "action": "order.proposed",
   "detail": "{\"id\":\"ord_...\",\"symbol\":\"EURUSD\"}" }]
```

---

## Autopilot & dashboard

The autopilot is an optional background loop. It is **off until started**, and it
places orders through the same hard risk gate as the UI. See
[AUTOPILOT.md](AUTOPILOT.md) for the full design and safety notes.

### `GET /api/dashboard`

One call that powers the dashboard: live status, account, positions, KPIs,
decision history, closed trades, orders, equity points and audit activity.

```json
{
  "autopilot": { "running": true, "stage": "analysing", "symbol": "EURUSD",
                 "cycle": 12, "next_run_at": 1795070900.0,
                 "using_models": ["Groq · llama-3.3-70b"], "last_decision": { } },
  "control": { "autopilot_interval_sec": 300, "autopilot_execution": "auto",
               "autopilot_confidence": 0.55, "max_open_positions": 2, "kill_switch": false },
  "account": { "id": "acc_...", "name": "Paper", "broker": "paper",
               "environment": "paper", "snapshot": { "equity": 10000, "balance": 10000 } },
  "positions": [],
  "stats": { "closed_trades": 0, "win_rate": 0, "total_pnl": 0, "today_pnl": 0,
             "profit_factor": 0, "trades_today": 0 },
  "decisions": [],
  "closed_positions": [],
  "orders": [],
  "equity": [{ "ts": 1795070000.0, "equity": 10000 }],
  "activity": [{ "ts": 1795070000.0, "actor": "autopilot",
                 "action": "autopilot.decision", "detail": "{...}" }]
}
```

### `GET /api/autopilot`

Current engine state only (`running`, `stage`, `symbol`, `cycle`, `next_run_at`,
`using_models`, `last_decision`, `last_error`, `halted_reason`).

### `GET /api/autopilot/decisions?limit=60`

Every model vote and risk-gate outcome, newest first. Each row contains
`action`, `confidence`, `price`, `reason`, `model`, `status`, `order_id`,
`risk_usd`, `pnl`, plus `votes` (per-model JSON) and `snapshot` (market context).

`status` is one of `executed`, `pending_approval`, `held`, `blocked`, `failed`,
`error`.

### `POST /api/autopilot/start`

Starts the loop. Optional body overrides settings for this run:

```json
{ "interval_sec": 300, "symbols": ["EURUSD","XAUUSD"], "provider_ids": ["prv_..."],
  "execution": "auto", "confidence": 0.55, "symbols_per_cycle": 2,
  "max_trades_per_day": 6, "account_id": "acc_..." }
```

### `POST /api/autopilot/stop`

Stops the loop. Open positions are left untouched; broker-side SL/TP still
protects them.

### `POST /api/autopilot/run-once`

Runs exactly one cycle without starting the loop. Returns
`{"ok": true, "state": {...}}` or `{"ok": false, "error": "..."}`.

### `POST /api/autopilot/kill`

Sets `kill_switch=true`, stops the loop and blocks all new orders. Reset with
`PUT /api/settings {"kill_switch": false}`; the autopilot stays stopped until you
press Start again.

---

## Settings

### `GET /api/settings`

The full key/value map (safe defaults + UI keys).

### `PUT /api/settings`

Any allowed key:

| Key | Type | Range / notes |
|-----|------|---------------|
| `trading_mode` | `paper|demo|live` | `live` requires `allow_live_trading` |
| `allow_live_trading` | bool | audited when turned on |
| `require_order_approval` | bool | default true |
| `kill_switch` | bool | blocks all orders |
| `max_risk_per_trade_pct` | number | 0.05–50 |
| `max_daily_loss_pct` | number | 0.05–50 |
| `max_drawdown_pct` | number | 0.05–50 |
| `max_open_positions` | int | 1–100 |
| `max_lot_size` | number | 0.01–100 |
| `max_spread_points` | int | 1–100 |
| `default_symbols` | string[] | allow-list |
| `auto_execute_tools` | bool | dangerous MCP calls |
| `autopilot_enabled` | bool | loop on/off (Start/Stop buttons) |
| `autopilot_autostart` | bool | resume the loop after a core restart |
| `autopilot_interval_sec` | int | 60–86400, default 300 |
| `autopilot_symbols` | string[] | watchlist; falls back to `default_symbols` |
| `autopilot_symbols_per_cycle` | int | 1–10, default 2 |
| `autopilot_provider_ids` | string[] | up to 3 voting models; empty = default |
| `autopilot_execution` | `auto|approval` | `auto` skips the click for paper/demo |
| `autopilot_confidence` | number | 0.05–1.0 gate, default 0.55 |
| `autopilot_max_trades_per_day` | int | 1–100, default 6 |
| `autopilot_sl_atr` / `autopilot_tp_atr` | number | ATR multiples, defaults 2.0 / 4.0 |
| `autopilot_cooldown_sec` | int | per-symbol re-entry cooldown, default 900 |
| `autopilot_allow_live_auto` | bool | live hands-free; also needs `allow_live_trading` |
| `theme` | `light|dark` | UI |
| `ui_density`, `onboarding_done`, `risk_profile`, `default_account_id`, `auto_approve_mcp_dangerous` | various | UI/metadata |

`trading_mode=live` without `allow_live_trading` → `400`.

---

## Conversations

### `GET /api/conversations`

100 newest: `id`, `title`, `model`, `created_at`, `updated_at`.

### `POST /api/conversations`

`{"title": "New chat"}` → conversation row.

### `PATCH /api/conversations/{id}`

`{"title": "EURUSD plan"}` → `{"ok": true}`.

### `DELETE /api/conversations/{id}`

Deletes messages and the conversation.

### `GET /api/conversations/{id}/messages`

Messages with `id`, `conversation_id`, `role`, `content`, `created_at`, and
`meta` (`{"trace": [...], "provider": "prv_..."}`).

---

## Chat

### `POST /api/chat`

Non-streaming.

```json
{ "message": "Analyse EURUSD", "conversation_id": null,
  "provider_id": "prv_...", "account_id": "acc_...", "mode": "analyse" }
```

```json
{ "conversation_id": "conv_...", "text": "...", "trace": [
  {"name": "get_quote", "args": {"symbol": "EURUSD"}, "result": {...}}
] }
```

### `POST /api/chat/stream`

Same body. Response is `text/event-stream`:

```
: connected

data: {"type":"tool_start","name":"get_quote","args":{"symbol":"EURUSD"}}

data: {"type":"tool_result","name":"get_quote","result":{"price":1.0971}}

data: {"type":"text","text":"EURUSD is ..."}

data: {"type":"done","conversation_id":"conv_...","text":"...","trace":[...]}
```

Event types: `text`, `tool_start`, `tool_result`, `error`, `done`. Keep-alive
comments (`: ping`) are ignored by the client. A model error emits `error` and
still finishes with `done`.

`mode` ∈ `analyse | trade | ask`. In `analyse`, the prompt discourages order
proposals; in `trade`, proposals with SL/TP are expected.

---

## Static UI

If `app/dist/` exists when the core starts, `/` serves the built UI with SPA
fallback. That means a single `py -3.12 core/main.py` can host both API and UI at
<http://127.0.0.1:8765>.

---

## Quick examples

```bash
# health
curl http://127.0.0.1:8765/api/health

# propose a small paper trade
curl -X POST http://127.0.0.1:8765/api/orders -H "Content-Type: application/json" -d '{
  "symbol":"EURUSD","side":"BUY","volume":0.02,"sl":1.09,"tp":1.13,"reason":"test"
}'

# approve it
curl -X POST http://127.0.0.1:8765/api/orders/ord_.../approve

# stream a chat (with token)
curl -N -X POST http://127.0.0.1:8765/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-AI-Trader-Token: $AI_TRADER_TOKEN" \
  -d '{"message":"What is EURUSD doing?","mode":"analyse"}'
```

---

## Related docs

- [ARCHITECTURE.md](../ARCHITECTURE.md) — flows behind these routes
- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — auth and the risk checks
- [BROKER_INTEGRATION.md](BROKER_INTEGRATION.md) — account fields per broker
