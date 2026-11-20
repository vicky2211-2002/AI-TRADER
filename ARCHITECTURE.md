# AI-TRADER — Architecture

AI-TRADER is two processes and one shared UI bundle:

1. **Core** — Python 3.11/3.12, FastAPI, SQLite. Owns secrets, models, tools,
   risk and brokers. Listens on **`0.0.0.0:8765`** by default (v0.1.1+).
2. **Shell** — Electron (desktop), a browser tab, or a Capacitor WebView
   (Android/iOS). Renders the React UI and talks to the core over HTTP + SSE.
3. **Shared UI** — one Vite build in `app/dist`, loaded by every shell.

```
┌──────────────────────────── shell (untrusted UI) ───────────────────────────┐
│  React 18 + TypeScript + Tailwind                                          │
│  Chat · Models · MCP · Skills · Brokers · Trades · Settings                │
│  localStorage: core URL, token, theme                                      │
└───────────────┬───────────────────────────────────────────┬─────────────────┘
                │ fetch / SSE                               │ Electron IPC
                ▼                                           ▼
┌──────────────────────── core (trusted) ──────────────┐  ┌──────────────────┐
│ FastAPI :8765 (binds 0.0.0.0 by default)             │  │ main.ts          │
│  ├─ agent loop ──▶ provider client ──▶ model API      │  │ spawn/wait/kill  │
│  ├─ built-in tools ──▶ market, trading, db            │  │ core process     │
│  ├─ MCP manager ──▶ stdio / Streamable HTTP servers   │  └──────────────────┘
│  ├─ risk gate ──▶ trading ──▶ broker adapter          │
│  ├─ SQLite (WAL) + audit                              │
│  └─ vault (Fernet or obfuscated)                      │
└───────────────────────────┬───────────────────────────┘
                            │ HTTPS / SDK
        ┌───────────────────┼───────────────────┬──────────────────┐
        ▼                   ▼                   ▼                  ▼
   model APIs          market data          brokers           MCP servers
  Gemini/Groq/...    Yahoo Finance RSS   MT5/MetaAPI/CCXT   npx/uvx/HTTP
```

---

## 1. Process lifecycle

### Desktop

`app/electron/main.ts`:

1. `app.whenReady()` probes `GET /api/health` on `127.0.0.1:8765`.
2. If no AI-TRADER core answers, it spawns one:
   - **First choice — the bundled core** at
     `resources/core-runtime/aitrader-core(.exe)`. This is a PyInstaller freeze of
     `core/` (FastAPI + uvicorn + vault + the Windows MetaTrader5 bridge), so a
     normal install needs no Python at all.
     - **Passes `AI_TRADER_HOST=0.0.0.0`** so core binds to all interfaces.
     - Core auto-attempts a **Windows Firewall rule** for port 8765.
     - Core detects **VC++ Redistributable** and **MT5 terminal** paths.
   - **Fallback — a system interpreter** when `core-runtime` is absent (dev
     checkout, or a build made without `core/build_sidecar.py`): `AI_TRADER_PYTHON`,
     then `py -3.12`, `py -3`, `python` (Windows), or `python3`, `python`
     (macOS/Linux), running `resources/core/main.py`.
3. It waits up to ~30 s, then opens the window. Core stdout/stderr go to
   `<userData>/logs/core.log`.
4. On quit it kills the child process tree (`taskkill /T /F` on Windows).
5. `core:restart` IPC lets Settings restart the core without restarting Electron.

**New IPC endpoints (v0.1.1+):**
- `core:lan-info` → returns `{ lanIp, port, coreUrl, mobileUrl }` for Android app
- `core:mt5-info` → returns MT5 terminal status from core's `/api/brokers/mt5/status`

The window uses `contextIsolation: true`, `nodeIntegration: false`,
`sandbox: true`, and a preload that exposes `coreUrl`, `restartCore`, `info`,
`platform`, `lanInfo`, `mt5Info`.

### Browser

`py -3.12 core/main.py` plus `npm run dev`. Vite proxies nothing; the UI calls
`http://127.0.0.1:8765` directly, so CORS is explicit.

### Mobile

The APK contains only the web bundle. The core runs elsewhere. CORS accepts
`https://localhost` / `capacitor://localhost` (WebView origins) and localhost
dev servers. A token is mandatory for any non-loopback bind.

---

## 2. Request flows

### Chat completion with tools

```
POST /api/chat/stream
  { message, conversation_id?, provider_id?, account_id?, mode }
        │
        ▼
agent.run() ── load conversation history (last N messages)
        │      build system prompt (date, mode, account, enabled skills)
        │
        ├─ provider.chat(messages, tools=[builtin + MCP tools])
        │       │
        │       ├─ model returns content ──▶ SSE {"type":"text"}
        │       └─ model returns tool_calls
        │               │
        │               ├─ built-in tool ──▶ execute locally
        │               ├─ MCP tool ──▶ MCPManager.call()
        │               └─ dangerous tool && !auto_execute ──▶ approval row
        │
        ├─ append tool result, loop (bounded)
        └─ final content ──▶ SSE {"type":"done", trace:[...]}
```

SSE event types: `text`, `tool_start`, `tool_result`, `error`, `done`.
The UI renders each tool call as a collapsible trace card.

Modes:

| Mode | System-prompt effect |
|------|----------------------|
| `analyse` | Read-only bias; explicit "do not propose orders unless asked" |
| `trade` | May propose orders with SL/TP and reasoning |
| `ask` | Plain assistant; no trading emphasis |

### Order proposal

```
POST /api/orders  (or place_order tool)
        │
        ├─ resolve account + broker snapshot (balance, equity, positions)
        ├─ fetch quote (Yahoo, then MT5) and mark stale if old
        ├─ risk.evaluate_order(...)        ← pure, deterministic
        │
        ├─ blocked ──▶ order row status=blocked, return checks
        └─ allowed ──▶ order row status=pending_approval
                        + approval row kind=order
                              │
                    POST /api/orders/{id}/approve
                              │
                        broker.place(order)
                              │
                    filled / failed + position row + audit
```

`require_order_approval=false` short-circuits the approval card for
*auto-executed* flows, but the risk gate still runs. Manual orders in the UI keep
the card until approved.

### Autopilot cycle

```
POST /api/autopilot/start  (or the background timer)
        │
        ▼
AutopilotEngine._cycle()
        ├─ read settings + account + positions
        ├─ paper only: close positions whose quote crossed SL/TP
        ├─ caps: kill switch, max open, daily trade cap, cooldown
        ├─ rotate watchlist → fetch quote + 1h candles (SMA/RSI/ATR/trend)
        ├─ ask 1–3 providers in parallel → strict JSON BUY/SELL/HOLD
        ├─ aggregate vote (ties = HOLD) → confidence gate
        ├─ size = risk% × equity ÷ (ATR × sl_atr × contract size)
        └─ trading.propose(..., auto_execute=True)
                ├─ risk.evaluate_order(...)   ← unchanged hard gate
                ├─ executes on paper/demo, approval on live
                └─ decisions row + audit + equity point
```

`GET /api/dashboard` reads the engine state plus the `decisions`, `positions`,
`orders`, `equity_points` and `audit` tables in one payload.

### MCP tool calls

The MCP manager keeps one client per server, starts it lazily, performs the
`initialize` handshake, caches `tools/list`, and exposes call/read. Two
transports:

- **stdio** — spawn `command + args` with `env`, JSON-RPC over newline-delimited
  stdin/stdout. Logs go to stderr only.
- **Streamable HTTP** — `POST` JSON-RPC with `Accept: application/json,
  text/event-stream`; handles both plain JSON and SSE responses.

Tool names are namespaced as `server__tool` to avoid collisions. Names matching
`delete|write|create|update|execute|run|send|trade|order|transfer|post|put|
patch|remove|drop|kill|install` require approval unless auto-execute is on.

---

## 3. Modules

| Module | Responsibility | Notes |
|--------|----------------|-------|
| `config.py` | Paths, host/port/token, CORS list, safe defaults | **Defaults to `0.0.0.0` bind** (v0.1.1+) |
| `db.py` | SQLite schema, settings, CRUD helpers, audit | WAL mode, one lock, dict rows |
| `security.py` | Encrypt/decrypt secrets, masking | Fernet when `cryptography` is present; XOR fallback marked `obfuscated` |
| `providers.py` | Unified chat + model listing + test | OpenAI, Anthropic, Google native, Azure |
| `mcp_client.py` | MCP stdio + HTTP clients + manager | Hand-rolled JSON-RPC, no SDK pinning |
| `skills.py` | `SKILL.md` parse/sync/CRUD | YAML-ish frontmatter, safe ids |
| `market.py` | Quotes, candles, news | Yahoo primary, MT5 fallback, TTL cache |
| `brokers.py` | Broker adapters + catalog | Paper, MT5, MetaAPI, CCXT, Alpaca, OANDA, webhook |
| `risk.py` | The hard gate + equity tracking | Returns structured checks, never raises on block |
| `trading.py` | Order lifecycle, approvals, positions, audit | Single source of truth for execution |
| `agent.py` | Tool loop, system prompt, built-in tools | SSRF guard on `fetch_url` |
| `autopilot.py` | Background loop: model voting, sizing, paper exits, decision/equity persistence, dashboard payload | Uses the same `risk.evaluate_order` gate |
| `api.py` | HTTP surface + streaming | **New: `/api/brokers/mt5/status` endpoint** |
| `seed.py` | First-run providers/MCP/accounts | Idempotent |
| `build_sidecar.py` | PyInstaller freeze of the core for the installers | Outputs `app/core-runtime/` |
| `main.py` | Uvicorn entry — **auto firewall, VC++ check, MT5 detect** | `--lan`, `--reload`, `--port` |

### Storage

SQLite at `<home>/data/aitrader.db`:

| Table | Purpose |
|-------|---------|
| `providers` | Model endpoints; `api_key_enc` holds ciphertext |
| `mcp_servers` | Transport, command/args/url, env (encrypted), tool cache |
| `skills` | Registry mirrored from disk; `enabled` and metadata |
| `accounts` | Broker, environment, config JSON, `secret_enc` |
| `conversations`, `messages` | Chat history; message `meta_json` stores tool traces |
| `orders` | Every proposal, status, risk numbers, broker response |
| `positions` | Open/closed positions, PnL, ticket |
| `approvals` | Pending/resolved approvals, payload + result |
| `settings` | Key/value, seeded from `SAFE_DEFAULTS` |
| `decisions` | Every autopilot cycle: action, confidence, reason, model label, status, order id, risk, PnL, per-model votes, market snapshot |
| `equity_points` | Equity sampled each autopilot cycle (last 2,000 kept) for the dashboard curve |
| `audit` | Append-only action log |

Files:

```
<home>/
├─ data/aitrader.db
├─ vault.key            ← 0600 where supported
└─ logs/core.log        ← Electron-managed
```

---

## 4. Security boundaries

| Boundary | Control |
|----------|---------|
| Renderer → core | Loopback bind optional; default `0.0.0.0`; optional `X-AI-Trader-Token`; explicit CORS |
| Core → model APIs | Keys decrypted in memory per request, never returned |
| Core → broker | Credentials decrypted per call; never sent to the UI |
| Model → tools | Tool schema allow-list; SSRF guard; dangerous-tool approval |
| Tools → filesystem | Only via MCP servers you install; filesystem server is path-scoped |
| Order → broker | Risk gate + approval + audit |

Assumptions: the core host is trusted, the OS account is not shared, and the
user reviews approvals. If an attacker has code execution on the core host, the
vault key is readable — no local vault can prevent that.

---

## 5. Failure behavior

| Failure | Result |
|---------|--------|
| Model API down / bad key | SSE `error`; chat keeps history; provider status updated |
| MCP server crashes | `status=error`, tool list cleared; agent continues without it |
| Quote stale | Order blocked with "Fresh quote" |
| Broker rejects | Order `failed`, broker message stored, no position created |
| Core killed mid-chat | Client stream ends; conversation remains; resend is safe |
| Duplicate order clicks | Second approval returns "already resolved" |
| Disk full | Writes fail loudly; UI surfaces HTTP 500 |
| Firewall rule add fails | Non-fatal; core starts anyway; user sees warning in logs |
| VC++ missing | Warning at startup with download URL; core may still run |
| MT5 terminal not found | Warning at startup; MT5 broker test will fail gracefully |

---

## 6. Extension points

- **New model vendor** — add a branch in `providers.py` or use any
  OpenAI-compatible base URL. No schema change needed.
- **New broker** — subclass `Broker` in `brokers.py`, implement
  `snapshot/place/close/positions`, add a `BROKER_CATALOG` entry. The risk gate
  is broker-agnostic.
- **New built-in tool** — add `_fn(...)` to `BUILTIN_TOOLS` and handle it in the
  dispatcher in `agent.py`.
- **New MCP server** — no code: add from the catalog or a custom entry.
- **New skill** — drop a folder with `SKILL.md` in `skills/` and press Rescan.
- **New risk check** — append a `_pass/_fail` pair in `risk.evaluate_order`.
  Keep it deterministic and side-effect free.

---

## 7. Non-goals (for now)

- Multi-user hosting or a shared cloud account.
- Sub-second/HFT execution.
- Automatic strategy optimisation inside the app.
- Storing broker passwords on the phone.
- Claiming profitability from backtests.

See [`ROADMAP.md`](docs/ROADMAP.md) for what comes next.