# AI-TRADER

A Claude-style trading cockpit: bring your own AI models, connect MCP tools and
skills, attach brokers, analyse markets, and let models trade on their own
through a hard risk gate — with a live dashboard that shows what the models, bot
and broker are doing right now, plus the full decision history.

Runs as a **desktop app** (Windows/macOS), in the **browser**, and as an
**Android APK** through Capacitor. The same React UI talks to a local Python
core; the core owns the secrets, the risk engine and the broker connections.

> **Status: v0.1.1, paper-first, zero-config.** Paper trading is the default.
> Live trading is off until you explicitly enable it. Core binds to `0.0.0.0`
> by default so LAN/mobile works instantly. Windows Firewall rule auto-added.
> This is not financial advice, and no backtest or demo result here is evidence
> of future profit.

---

## Why it exists

Retail trading bots usually fail for three boring reasons: they overfit, they
hide costs, and they let a model touch real money without a human. AI-TRADER is
built the other way around:

- The model **proposes**, it never executes directly.
- Every ticket passes a deterministic risk gate.
- Every order waits for a human unless you deliberately turn approval off — or
  start the autopilot, which still passes the same gate.
- Live trading is a separate, audited switch that refuses to turn on by accident.
- Keys never appear in chat, logs, the repo or the renderer.

---

## What you can do

| Area | Capability |
|------|-----------|
| **Models** | Add any OpenAI-compatible API, Anthropic, Google Gemini or Azure OpenAI. Per-model **Test** button with latency and reply. Free seeds included. |
| **Chat** | Streaming answers, tool trace cards, analyse / trade / ask modes, markdown + tables. |
| **Autopilot** | A background loop where 1–3 models vote BUY/SELL/HOLD, the core sizes the trade and executes it on paper/demo, and every decision is logged. Same hard risk gate; live hands-free needs two switches. |
| **Dashboard** | What the bot is doing now (stage, symbol, cycle, next run, models voting), KPIs, equity curve, open positions, closed trades, and per-model vote history. |
| **MCP** | Add, edit, start, stop, test and call stdio or Streamable-HTTP MCP servers. 22-item catalog (Context7, Playwright, Firecrawl, Fetch, Brave, GitHub, Postgres, CCXT, Alpaca…). |
| **Skills** | Claude-compatible `skills/<id>/SKILL.md` playbooks. **27 trading skills** seeded (16 built-in + 11 from trader-skill). Create, edit, enable, delete, rescan. |
| **Brokers** | Paper, MT5 (Windows), MetaAPI (cloud MT5/MT4), CCXT crypto, Alpaca, OANDA v20, HMAC webhook. |
| **Risk** | Risk-per-trade, max lots, required SL, symbol allow-list, duplicate exposure, daily loss, peak drawdown, stale-quote rejection, kill switch. |
| **Approvals** | Order cards and dangerous MCP tool calls wait in an approvals inbox. |
| **Audit** | Every provider, setting, order, approval and kill-switch change is appended to a local audit log. |
| **Cross-platform** | Electron for Windows/macOS, browser mode, Capacitor for Android/iOS. |
| **Zero-config (v0.1.1+)** | Bundled Python core (no installs), core binds `0.0.0.0`, Windows Firewall auto-rule, MT5 terminal auto-detect. |

---

## Quick start

### Use a release (no toolchain)

Download the installer for your OS from
<https://github.com/vicky2211-2002/AI-TRADER/releases> and run it. The desktop
builds include their own Python core, so there is nothing else to install.

### Build from source (Windows)

```powershell
cd "C:\Users\Shivani Babar\forex_trader_bot\AI-TRADER"

# 1. Core dependencies (plain `python` on this machine is a pip-less venv,
#    so use the 3.12 launcher):
py -3.12 -m pip install -r core\requirements.txt

# 2. UI
cd app
npm install
npm run build:web

# 3. Desktop app (spawns the core automatically)
npm run electron
```

To reproduce the shipped installer, freeze the core first and then package:

```powershell
py -3.12 core\build_sidecar.py --clean   # -> app\core-runtime\aitrader-core.exe
cd app
npm run dist:win                         # -> app\release\AI-TRADER-0.1.1-x64.exe
```

After `npm run build:web`, the core also serves the built UI itself at
`http://127.0.0.1:8765` (no dev server needed). `npm run dev` is only for
hot-reload development on `http://localhost:5173`.

Browser-only development:

```powershell
# terminal 1
cd core
py -3.12 main.py

# terminal 2
cd app
npm run dev          # http://localhost:5173
```

The core listens on `http://0.0.0.0:8765` (v0.1.1+) and shows up at `/api/health`.
Data lives in `%APPDATA%\AI-TRADER` (override with `AI_TRADER_HOME`).

### First five minutes

1. **Models → Test.** Pick Google AI Studio, Groq, Cerebras or OpenRouter, paste
   a free key, press **Test**. Or point the Ollama entry at your local server.
2. **Chat → "Analyse EURUSD"** and watch the tool trace.
3. **Skills → open `risk-manager`.** Edit it to match your own rules.
4. **MCP servers → Catalog → Context7 → Install → Start.** Ask the chat to use it.
5. **Brokers → Add account → Paper.** Try an order on Trades; the risk gate will
   tell you exactly which limit blocked it.
6. **Autopilot → Run one cycle.** Watch the models vote, the core size the trade
   and the risk gate decide. Press **Start autopilot** once you are happy.

---

## Autopilot in one screen

```
every N seconds (default 300s)
    │
    ▼
read account + positions ──► manage paper SL/TP exits ──► caps: max open,
    │                                                    daily trades, cooldown
    ▼
fetch quote + 1h candles (price, SMA, RSI, ATR, trend, 20-bar range)
    │
    ▼
ask 1–3 models in parallel ──► strict JSON BUY/SELL/HOLD + confidence + SL/TP ATR
    │
    ▼
aggregate (weighted vote, ties = HOLD) ──► below confidence gate? record HOLD
    │
    ▼
size = risk% × equity ÷ (ATR × sl_atr × contract size)   [capped by max lots]
    │
    ▼
HARD RISK GATE ──► execute (paper/demo auto) ──► log decision + order + equity point
```

Nothing skips the gate. The kill switch always wins, live auto-execution needs
both `allow_live_trading` and `autopilot_allow_live_auto`, and every model vote is
stored so you can audit exactly why a trade happened.

**No profit is promised.** Paper results are an upper bound; run your own demo
sample before risking money. Full details: [`docs/AUTOPILOT.md`](docs/AUTOPILOT.md).

---

## Safety model in one screen

```
model / user
    │  place_order(symbol, side, volume, sl, tp, reason)
    ▼
┌───────────────────────────────────────────────────────────────┐
│ Hard risk gate (core, deterministic)                           │
│ kill switch · live gate · symbol allow-list · side · max lots │
│ stop loss required & on the correct side · TP side            │
│ risk % of equity · max open positions · duplicate exposure    │
│ daily loss · peak drawdown · quote freshness                  │
└───────────────────────────────────────────────────────────────┘
    │ allowed                       │ blocked
    ▼                               ▼
pending approval card           rejected + audit row
    │ approve
    ▼
broker adapter (paper / MT5 / MetaAPI / CCXT / Alpaca / OANDA / webhook)
```

Nothing in the UI can skip a check. Editing the React bundle, replaying a
request or prompt-injecting the model only changes *what is proposed* — the gate
and approval inbox still decide.

Read [`docs/SECURITY_AND_RISK.md`](docs/SECURITY_AND_RISK.md) before connecting a
live account.

---

## Zero-config install (v0.1.1+)

The installers are **completely self-contained**. They ship a frozen Python
core (`resources/core-runtime/aitrader-core.exe`) *and* the two runtimes that
MCP servers need (Node.js for `npx`, uv for `uvx`). You do not install Python,
pip, Node.js, uv or any package to run the desktop app.

| Feature | Before v0.1.1 | Now |
|---------|---------------|-----|
| **Python runtime** | User installs Python 3.12 + `pip install -r requirements.txt` | **Bundled** — nothing to install |
| **Node.js (`npx`)** | User installs Node 20+ | **Bundled** (`resources/node`, with the full npm CLI) |
| **uv (`uvx`)** | User runs `pip install uv` | **Bundled** (`resources/uv/uv.exe` + `uvx.exe`) |
| **MetaTrader5 bridge** | `pip install MetaTrader5` | **Bundled** on Windows |
| **Core binding** | `127.0.0.1` only | **`0.0.0.0`** — LAN/mobile works instantly |
| **Windows Firewall** | Manual `netsh` command | **Auto-attempted** on first launch; Windows may ask once |
| **VC++ Redistributable** | User downloads manually | **Detected at startup**, prints URL if missing |
| **MT5 Terminal** | User finds path manually | **Auto-detected** (common paths + registry) |
| **Asset names** | Could differ from the tag | **Stamped from the tag** — `AI-TRADER-0.1.4-x64.exe` |

**End user experience (Windows):**
1. Download `AI-TRADER-<version>-x64.exe` → run it.
2. If Windows asks about the firewall, click **Allow** (needed only for phone access).
3. The app opens; its own core is already running on port 8765.
4. **Models** → paste a key → **Test**.
5. **Brokers** → MT5 path is pre-filled → login/password/server → **Test**.
6. **MCP servers** → every server is already runnable (no Node.js/uv install).

The only thing still external is the **MetaTrader 5 terminal** itself — it is a
proprietary Windows application that must be installed from your broker and
logged into once. If you do not use MT5, the Paper broker and the MetaAPI
cloud bridge work with no terminal at all.

**Android:** install the APK, then type your PC's LAN address
(`http://192.168.x.x:8765`) in the Core URL field. The phone cannot discover the
PC by itself, and the core never runs on the phone.

---

## Project layout

```
AI-TRADER/
├─ core/                  Python FastAPI core
│  ├─ main.py             entry point (uvicorn) — zero-config startup
│  ├─ aitrader/
│  │  ├─ api.py           all HTTP routes (+ /api/brokers/mt5/status)
│  │  ├─ agent.py         tool-calling loop + built-in tools
│  │  ├─ autopilot.py     autonomous loop: votes, sizing, exits, dashboard data
│  │  ├─ providers.py     OpenAI/Anthropic/Google/Azure client
│  │  ├─ mcp_client.py    stdio + Streamable HTTP MCP client
│  │  ├─ skills.py        SKILL.md loader/CRUD
│  │  ├─ market.py        Yahoo quotes/candles/news, MT5 fallback
│  │  ├─ brokers.py       paper/MT5/MetaAPI/CCXT/Alpaca/OANDA/webhook
│  │  ├─ risk.py          the hard gate
│  │  ├─ trading.py       order lifecycle + approvals
│  │  ├─ security.py      local vault (Fernet or obfuscated)
│  │  ├─ db.py            SQLite store + audit
│  │  ├─ config.py        config with 0.0.0.0 default bind
│  │  └─ seed.py          first-run seeds
│  ├─ seed/*.json         6 providers, 4 MCP servers, 22 catalog items
│  └─ tests/              14 offline regression tests
├─ app/                   React + TypeScript + Tailwind + Vite
│  ├─ electron/
│  │  ├─ main.ts          Electron main — spawns bundled core, LAN + MT5 IPC
│  │  └─ preload.js
│  ├─ core-runtime/       frozen Python core (built by core/build_sidecar.py)
│  └─ src/components/     Autopilot dashboard, Chat, Models, MCP, Skills, Brokers, Trades, Settings
├─ mobile/                Capacitor shell for Android/iOS
├─ skills/                **27 Markdown trading playbooks**
└─ docs/                  everything else
```

---

## Configuration

Environment variables for the core:

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_TRADER_HOME` | `%APPDATA%\AI-TRADER` | Data, vault and SQLite location |
| `AI_TRADER_SKILLS` | `AI-TRADER/skills` | Skills folder |
| `AI_TRADER_HOST` | `0.0.0.0` | Bind address (v0.1.1+) |
| `AI_TRADER_PORT` | `8765` | HTTP port |
| `AI_TRADER_TOKEN` | empty | Required `X-AI-Trader-Token` when set |

See [`.env.example`](.env.example). The core never reads a `.env` automatically;
pass variables in your shell, Electron, or a service wrapper.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Process model, data flow, modules, storage |
| [docs/AUTOPILOT.md](docs/AUTOPILOT.md) | Autonomous loop: voting, sizing, exits, dashboard, safety |
| [docs/FREE_API_PROVIDERS.md](docs/FREE_API_PROVIDERS.md) | Free model providers, base URLs, keys, limits |
| [docs/MCP_CATALOG.md](docs/MCP_CATALOG.md) | Every MCP server, install command, risk notes |
| [docs/SKILLS_CATALOG.md](docs/SKILLS_CATALOG.md) | The 27 playbooks + how to write your own |
| [docs/BROKER_INTEGRATION.md](docs/BROKER_INTEGRATION.md) | Per-broker setup and symbol mapping |
| [docs/SECURITY_AND_RISK.md](docs/SECURITY_AND_RISK.md) | Threat model, vault, risk gate, live checklist |
| [docs/BUILD_CROSS_PLATFORM.md](docs/BUILD_CROSS_PLATFORM.md) | Windows, macOS, Android builds and signing |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Every endpoint with payloads |
| [docs/UI_GUIDE.md](docs/UI_GUIDE.md) | Screen-by-screen tour |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and fixes |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What is done, what is next, validation gates |

---

## Tests

```powershell
cd AI-TRADER
$env:AI_TRADER_HOME="$env:TEMP\aitrader_pytest"
py -3.12 -m pytest core\tests -q
```

Current suite covers the vault round-trip, provider public shape, MCP stdio
handshake with a local echo server, skill CRUD, paper order lifecycle, risk
gate blocking, autopilot decision parsing/aggregation/sizing, and the dashboard
endpoints. Type-check and build:

```powershell
cd app
npx tsc -p tsconfig.json --noEmit
npm run build
```

The frozen core is verified the same way by hand: build it, start it on a spare
port, and check `/api/health`, `/api/skills` and `/api/brokers/mt5/status`
against a temporary `AI_TRADER_HOME`.

---

## Non-negotiables

- **Demo first.** A strategy earns live money only after a documented demo
  sample with a profit factor above your threshold — not after a backtest.
- **One position per symbol.** Duplicate exposure is blocked by default.
- **Stop loss on every order.** There is no "mental stop" option.
- **No martingale, no grid recovery.** Size down after losses, never up.
- **Secrets stay on the core host.** The phone and browser are remote controls.

If you are new to systematic trading, read *Trading in the Zone*, *Trade Your Way
to Financial Freedom* and *Fooled by Randomness* before funding anything.

---

## License

MIT — see [LICENSE](LICENSE). Trading is risky; you are responsible for every order you approve.