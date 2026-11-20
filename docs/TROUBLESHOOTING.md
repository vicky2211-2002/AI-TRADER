# Troubleshooting

Work from the outside in: **core → browser → model → tool → broker**. Most
problems are one of: wrong Python, wrong URL, wrong key, missing runtime, or a
risk limit doing its job.

---

## 1. The app says "Core offline"

### Check the process

```powershell
cd AI-TRADER\core
py -3.12 main.py
```

You should see:

```
Uvicorn running on http://0.0.0.0:8765
```

If it exits immediately, run it in the foreground and read the traceback.

### Check the port

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

| Result | Meaning |
|--------|---------|
| `{"ok":true,...}` | Core is fine; the UI URL/token is wrong |
| Connection refused | Nothing listening on 8765 |
| 401 | Token required/mismatched |

Another process on 8765:

```powershell
netstat -ano | Select-String ":8765"
```

Kill it or start with `--port 8766` and change the URL in Settings.

### Desktop-specific

- **Log:** `%APPDATA%\AI-TRADER\logs\core.log` (Electron's `userData` folder).
- **Bundled core:** the installer ships `resources\core-runtime\aitrader-core.exe`.
  If it is missing, Electron falls back to a system Python and the app behaves
  like a dev checkout.
- **Bundled MCP runtimes:** `resources\node\node.exe` + `npx.cmd` and
  `resources\uv\uv.exe` + `uvx.exe`. The core puts both folders on `PATH` at
  startup, so every MCP server works without installing Node.js or uv.
- **Antivirus:** unsigned PyInstaller binaries are sometimes quarantined. Allow
  the install folder, then restart the app.
- **SmartScreen** ("Windows protected your PC"): *More info → Run anyway*. The
  builds are unsigned; signing needs a code-signing certificate.
- **Python not found** only matters for dev builds: install Python 3.12 or set
  `AI_TRADER_PYTHON` to the full `python.exe` path, then restart the app.
- **Packaged app:** confirm `resources\core-runtime\aitrader-core.exe` exists
  next to `resources\core`, `resources\node` and `resources\uv`.
- **Firewall dialog:** Windows will prompt once — click "Allow access" for Private networks.
- **VC++ Redistributable missing:** Core prints download URL at startup:
  `https://aka.ms/vs/17/release/vc_redist.x64.exe`
- **MT5 terminal not found:** Core prints warning; install MT5, log in once, enable
  **Tools → Options → Expert Advisors → Allow algorithmic trading**. The Python
  bridge itself is bundled — only the terminal is external.
- **"MetaTrader5 is not importable":** the build shipped without the bridge
  (or without numpy, which the native bridge imports from C code and
  PyInstaller cannot detect on its own). Re-download the installer; a build
  without it fails CI on purpose — the frozen core is booted and must report
  `mt5_available: true`.
- **`No module named 'numpy'` in the core log:** same root cause as above.
  The `numpy` folder and `numpy.libs` (the native DLLs) must both exist under
  `resources\core-runtime\_internal\`.

### MCP servers

| Symptom | Cause | Fix |
|---------|-------|-----|
| `npx` not found | `resources\node` missing from the install | Reinstall; the folder must contain `node.exe`, `npx.cmd` **and** `node_modules\npm\` |
| `Cannot find module '../lib/cli.js'` | `npx.cmd` was copied without the npm package | Reinstall — the full `node_modules\npm` tree is required |
| `uvx` not found | `resources\uv` missing `uvx.exe` (it is a separate binary from `uv.exe`) | Reinstall; both `uv.exe` and `uvx.exe` must be present |
| `MCP process exited` immediately | The runtime is on PATH but its CLI tree is missing | Check `resources\node\node_modules\npm\lib` exists |
| Server needs an API key | Firecrawl / Tavily / Alpaca require their own account | Add the key in the server's **Edit** dialog |

### Browser-specific

- Open the console. A CORS error means you are serving the UI from an origin not
  in the allow-list. Use `npm run dev` on port 5173 or rebuild and let the core
  serve `/`.
- `Mixed Content` means an HTTPS page is calling HTTP localhost. Serve the UI over
  HTTP locally, or put both behind HTTPS.

---

## 2. Python / dependency errors

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: fastapi` | `py -3.12 -m pip install -r core\requirements.txt` |
| `ModuleNotFoundError: uvicorn` | same |
| `ModuleNotFoundError: httpx` | same |
| `No module named MetaTrader5` | Windows only: `py -3.12 -m pip install MetaTrader5` |
| `No module named ccxt` | `py -3.12 -m pip install ccxt` |
| `plain python has no pip` | Use `py -3.12` explicitly, not `python` |
| `pydantic` version error | Ensure Pydantic 2.x; create a fresh venv |
| `vault` says `obfuscated` | `py -3.12 -m pip install cryptography`, restart, re-enter secrets |

Recommended isolation:

```powershell
cd AI-TRADER
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r core\requirements.txt
python core\main.py
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

---

## 3. Provider / model problems

### "Add and test a model first"

No provider is enabled. Models → enable one → **Test**.

### 401 / 403

- Wrong or expired key.
- Key pasted with whitespace or quotes.
- The vendor requires a different header (Azure uses `api-key`; choose kind
  `azure`).
- OpenRouter needs a key even for `:free` models.

### 404 / model not found

- Base URL includes `/chat/completions` — remove it; enter the root only.
- Model id changed. Press **Refresh models** and pick a current id.
- Some routers require a vendor prefix (`openai/gpt-oss-120b`).

### 429 / quota

Free tiers throttle. Wait, switch model, or reduce tool loops. The provider row
records the last error.

### Timeout / connection reset

- Corporate proxy or VPN. Set `HTTPS_PROXY` for the core process.
- Local server not running (`ollama serve`, LM Studio server, vLLM).
- Firewall blocking outbound 443.

### Streaming hangs

- A tool is waiting on a slow MCP server (60 s start timeout).
- The model supports tools poorly and loops. Stop, lower the task complexity,
  switch to a stronger model.
- Check the core console for the last tool name.

### "thinking" forever with no text

The model returned a tool call but the tool crashed silently. Open the tool card
or the core log. MCP servers report errors on stderr.

---

## 4. MCP servers

| Error | Cause | Fix |
|-------|-------|-----|
| `spawn npx ENOENT` | Node not on the core's PATH | Install Node 18+, restart the core |
| `uvx not found` | `uv` missing | `py -3.12 -m pip install uv` |
| `initialize timed out` | First-run package download | Run `npx -y <pkg> --help` once in a terminal |
| `401` from an HTTP MCP | Missing auth header | Put it in env, restart the server |
| Tool list empty | Server exposes resources, not tools | Check its README |
| `ENOENT` for a path | Filesystem server folder does not exist | Create it, fix the arg |
| Server exits immediately | Bad args or missing env | Test the command manually |

Manual test:

```powershell
npx -y @modelcontextprotocol/server-everything
```

It should wait for JSON-RPC on stdin (press Ctrl+C). If it errors, the issue is
the package/runtime, not AI-TRADER.

Windows path arguments need forward slashes or escaped backslashes in JSON.

---

## 5. Broker problems

### MT5 (v0.1.1+ auto-detection)

| Error | Fix |
|-------|-----|
| `initialize failed` | Terminal closed, wrong login/server, or another terminal instance |
| `IPC timeout` | Restart MT5, then Test again |
| `Symbol unknown` | Set `symbol_suffix` (`.m`, `_raw`, …) |
| `retcode 10027` | Enable algorithmic trading in MT5 options |
| `account is REAL but environment is DEMO` | Intentional. Fix the environment or use a demo login. |
| Balance 0 / no account info | Log in manually once, keep the terminal open |
| **Terminal not found** | Core auto-checks common paths. Install MT5 from broker, log in once. |

**Auto-detection paths (checked in order):**
1. `C:\Program Files\MetaTrader 5\terminal64.exe`
2. `C:\Program Files (x86)\MetaTrader 5\terminal64.exe`
3. `%APPDATA%\MetaQuotes\Terminal\*\terminal64.exe`

Only one MT5 terminal can serve a given login at a time. Close extra instances.

### MetaAPI

- Account state must be `DEPLOYED`, not `UNDEPLOYED`.
- Region must match the account (`new-york`, `london`, `singapore`).
- Token expires/rotates; re-copy it.
- `close()` is not implemented — close in the MT5 app.

### CCXT

- `Exchange not found`: use the exact ccxt id (`binance`, `bybit`, `okx`).
- `Invalid API-key`: check key permissions and IP allow-list.
- `market not found`: symbol conversion expects `BTCUSD` → `BTC/USDT`; pass
  `BTC/USDT` directly if needed.
- Testnet keys need testnet endpoints; the adapter does not auto-switch.

### Alpaca

- Paper keys only work against the paper host; the adapter selects it from the
  environment.
- `qty` is shares/coins, not lots.
- Bracket orders require a valid TP/SL relationship.

### OANDA

- Account id includes dashes (`101-004-1234567-001`).
- Use practice token with practice host.
- Volume is converted from lots; do not enter raw units.

### Webhook

- Must be HTTPS in production.
- Verify `X-AI-TRADER-Signature` against the **raw** body.
- Respond JSON `{"ticket": "...", "price": ...}`.
- A 4xx/5xx becomes a `failed` order with the response body.

---

## 6. Orders and risk

### "Blocked by ..."

The gate is working. Read the failing row:

| Blocked by | Fix |
|------------|-----|
| Kill switch | Turn it off in Brokers/Settings |
| Live trading disabled | Enable the live switch **and** set mode live |
| Symbol allow-list | Add the symbol to the watchlist in Settings |
| Max lot size | Reduce volume or raise the cap deliberately |
| Stop loss required | Enter a stop |
| Stop loss side | BUY → SL below price; SELL → SL above |
| Risk per trade | Widen? No. Reduce volume or tighten the stop |
| Max open positions | Close one, or raise the cap |
| Duplicate exposure | One position per symbol by design |
| Daily loss limit | Stop for the day |
| Peak drawdown | Review the strategy; do not "reset" casually |
| Fresh quote | Market data stale/offline; retry |

### Order stuck in `pending_approval`

Open **Approvals**. If the card is gone but the status remains, the approval row
may have been rejected in another window. Check the Audit tab.

### Order `failed`

Read `broker_response` in the Orders table (hover/expand) or the audit detail.
Common causes: market closed, wrong symbol suffix, insufficient margin, spread
too wide at the broker, SL/TP too close to price.

### Close does nothing

Some adapters do not implement close (`metaapi`, `ccxt`, `oanda`, `webhook`).
Close in the broker UI. For paper, confirm the ticket still exists.

### PnL looks wrong

- Paper uses Yahoo quotes, not your broker's bid/ask.
- Contract size may not match your instrument. Set `config.contract_size`.
- OANDA volume is converted from lots; check the filled units.
- Alpaca qty is shares/coins.

---

## 7. Skills

| Problem | Fix |
|---------|-----|
| Skill not listed | Folder needs `SKILL.md`; press **Rescan folder** |
| Invalid id | Lowercase letters, numbers, `-`, `_`, 2–64 chars |
| Edits not saved | Check file permissions; the core writes under `skills/` |
| Agent ignores a skill | Ensure it is enabled; ask it to "read the <id> skill" |
| Delete failed | Close editors/antivirus locks; retry |

Frontmatter must start on line 1 with `---`.

---

## 8. UI

| Symptom | Fix |
|---------|-----|
| Blank white window | `app/dist` missing or wrong `loadFile` path; rebuild |
| Styles missing | Tailwind build failed; check `npm run build:web` |
| Theme half-applied | Hard reload; all colours use CSS variables, a custom style may override them |
| Text overflow in tables | Expected on narrow screens; scroll horizontally |
| Toasts never appear | `ToastProvider` missing (only relevant if you fork the UI) |
| Endless boot spinner | Core not answering; open the offline screen and set the URL |
| Mobile drawer won't close | Tap the backdrop or a nav item |

---

## 9. Mobile (Android)

| Symptom | Fix |
|---------|-----|
| `Core offline` on Wi-Fi | Type the PC's LAN address in Settings → Core URL: `http://192.168.x.x:8765`. `127.0.0.1` means *the phone itself* and will never work. |
| `CLEARTEXT not permitted` | CI-built APKs already allow LAN cleartext. For local builds, see [BUILD_CROSS_PLATFORM](BUILD_CROSS_PLATFORM.md#cleartext-http-on-android). |
| Blank after install | `cd app && npm run build:web`, then `npx cap sync android`, rebuild |
| `webDir` not found | Build the UI first |
| Gradle SDK error | Set `ANDROID_HOME` or `android/local.properties` |
| App can't start MCP servers | Expected: `npx`/`uvx` run on the core host |
| Token rejected | Paste the exact `AI_TRADER_TOKEN`; restart the core after changing it |

**Setup flow:**
1. Desktop app running on the PC (core listens on `0.0.0.0:8765`).
2. Firewall: allow port 8765 for the private network.
3. Phone and PC on the same Wi-Fi.
4. Phone → Settings → Core URL → `http://<PC-IP>:8765` → Connect.

Find the PC IP:
```powershell
ipconfig | findstr /R "IPv4.*192.168\|IPv4.*10\.\|IPv4.*172\."
```

---

## 10. Data, vault and reset

### Where is my data?

```
%APPDATA%\AI-TRADER\data\aitrader.db
%APPDATA%\AI-TRADER\vault.key
```

Override with `AI_TRADER_HOME`.

### Backup

Copy both files. Keep `vault.key` separate from the DB backup.

### Reset everything

```powershell
Stop-Process -Name python,aitrader-core,AI-TRADER -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\AI-TRADER" -Recurse -Force
```

This deletes providers, accounts, chat history, orders and the vault. Skills on
disk remain. Re-enter secrets.

### Forgot the vault key

Secrets cannot be recovered. Re-enter each provider key and broker password.

### Database locked

Only one core should use a given `AI_TRADER_HOME`. Stop duplicate processes;
SQLite WAL allows concurrent readers but not two writers fighting.

---

## 11. Logs and diagnostics

| What | Where |
|------|-------|
| Core console | The terminal running `main.py` |
| Desktop core log | `%APPDATA%\AI-TRADER\logs\core.log` |
| Audit trail | UI → Trades & risk → Audit, or `GET /api/audit` |
| Provider test | Models row status + toast |
| MCP stderr | "Test" result on failure |
| Broker response | Orders table / audit detail |

Useful one-liners:

```powershell
# is the core alive?
Invoke-RestMethod http://127.0.0.1:8765/api/health

# what version and vault backend?
Invoke-RestMethod http://127.0.0.1:8765/api/system

# recent audit
Invoke-RestMethod "http://127.0.0.1:8765/api/audit?limit=20" | Format-Table ts,actor,action

# run tests
$env:AI_TRADER_HOME="$env:TEMP\aitrader_pytest"; py -3.12 -m pytest core\tests -q

# MT5 status (v0.1.1+)
Invoke-RestMethod http://127.0.0.1:8765/api/brokers/mt5/status
```

---

## 12. Still stuck?

Collect:

1. `GET /api/system` output (redact paths if needed).
2. The exact error text and where it appeared.
3. Audit rows around the failure.
4. Whether it reproduces with the **paper** account and a **local** model.

Do not post API keys, passwords, account numbers or `vault.key`.