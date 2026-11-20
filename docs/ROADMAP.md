# Roadmap

AI-TRADER is a cockpit, not a promise of profit. The roadmap is ordered by
**safety and evidence**, not by features that demo well.

Status legend: ✅ done · 🟡 in progress · ⬜ planned · ❌ intentionally excluded

---

## 0.1.0 — Foundation (done)

| Area | Status | Notes |
|------|--------|-------|
| Local Python core (FastAPI + SQLite) | ✅ | Loopback by default, optional token |
| Encrypted vault | ✅ | Fernet when `cryptography` is installed |
| Providers: OpenAI-compatible, Anthropic, Google, Azure | ✅ | Test + model discovery |
| 6 free provider seeds | ✅ | Google, Groq, Cerebras, NVIDIA, OpenRouter, Ollama |
| MCP stdio + Streamable HTTP | ✅ | Hand-rolled JSON-RPC, no SDK pinning |
| 22-item MCP catalog | ✅ | Context7, Playwright, Firecrawl, Fetch, … |
| Skills: loader, CRUD, 16 playbooks | ✅ | `SKILL.md`, enable/disable/rescan |
| Brokers: paper, MT5, MetaAPI, CCXT, Alpaca, OANDA, webhook | ✅ | Capability matrix documented |
| Hard risk gate (15 checks) | ✅ | Deterministic, every order |
| Approval inbox + audit | ✅ | Orders, closes, dangerous MCP tools |
| Streaming chat with tool traces | ✅ | SSE, analyse/trade/ask modes |
| Electron shell (Windows/macOS/Linux) | ✅ | Spawns and supervises the core |
| Capacitor shell (Android/iOS) | ✅ | UI only; core stays on the host |
| Documentation set | ✅ | 11 docs + README + architecture |
| Offline tests | ✅ | 14 tests: vault, MCP, skills, paper lifecycle, risk, autopilot |
| Type-check + production build | ✅ | `tsc --noEmit`, `vite build` |

### Known gaps in 0.1.0

- Paper fills ignore spread/slippage/commission.
- `close()` missing for MetaAPI, CCXT, OANDA, webhook.
- `max_spread_points` is not enforced by every adapter.
- No broker-side reconciliation of manual trades.
- No encrypted chat history.
- No screenshot/icon assets in the repo.
- Market data is unofficial (Yahoo), with MT5 fallback.

---

## 0.1.1 — Installable anywhere (done)

| Area | Status | Notes |
|------|--------|-------|
| Frozen Python core in every desktop installer | ✅ | `core/build_sidecar.py` → `resources/core-runtime`; no system Python |
| Version stamped from the git tag | ✅ | `AI-TRADER-<tag>-x64.exe`, never a stale 0.1.0 name |
| Release replaced, not appended | ✅ | CI deletes the old release for the tag before uploading |
| Release notes generated from real files | ✅ | Missing platforms are named, not advertised |
| Android debug APK | ✅ | Pre-installed runner SDK + cleartext LAN config |
| 27 skills (16 + trader-skill pack) | ✅ | MIT attribution kept |
| Installer-level verification | ✅ | Frozen core health/model/broker checks run against the packaged app |

### Known gaps in 0.1.1

- Installers are unsigned (SmartScreen / Gatekeeper warnings).
- Android discovers nothing automatically: the user types the PC's LAN IP.
- iOS is not built (needs the Apple Developer Program and a Mac).
- `ccxt` is not bundled; install it only if you need a crypto exchange adapter.
- The Linux job failed at packaging; the reason was only visible in the raw log.

---

## 0.1.2 — Packaging polish

| Area | Status | Notes |
|------|--------|-------|
| App icon on every platform | ✅ | `app/build/icon.png` + `icon.ico`; wired into electron-builder |
| Packaging failures explain themselves | ✅ | electron-builder tail is emitted as run annotations |
| `deb` metadata valid | ✅ | `author` is an object with a maintainer email |
| Windows installer rebuilt from this tree | ✅ | 0.1.2 NSIS + portable verified locally |

### Known gaps in 0.1.2

- Same signing gap as 0.1.1: unsigned binaries.
- Screenshots for the README are still missing.

---

## 0.2.0 — Reliability and packaging

Priority: make the thing boring to operate.

| Item | Why |
|------|-----|
| 🟡 Bundle the core with PyInstaller per OS | Users should not need Python |
| ⬜ Implement `close()` for MetaAPI, CCXT, OANDA | Close from one place |
| ⬜ Enforce `max_spread_points` in every adapter | The setting currently lies for some brokers |
| ⬜ Broker reconciliation job | Import manual trades, detect drift |
| ⬜ Idempotent order keys | Prevent double-send on retry |
| ⬜ Structured JSON logging + rotation | Post-mortems without guesswork |
| ⬜ Encrypt chat DB at rest (SQLCipher or field-level) | Chat can contain sensitive context |
| ⬜ Health panel: provider latency, MCP uptime, last quote age | One glance, no guessing |
| ⬜ Backup/restore button | Portable, verifiable state |
| ✅ CI matrix (Windows/macOS/Linux/Android) | Reproducible releases |
| ✅ Bundled core runtime (no system Python) | Zero-config install |
| ⬜ Signed builds (Windows cert + Apple notarisation) | Remove SmartScreen/Gatekeeper warnings |
| ⬜ Icon set and screenshots | Distribution polish |

Acceptance: a clean Windows VM with no Python installs and runs the app, connects
a paper account, and passes the smoke test. **Met on Windows in the 0.1.1 build**
(frozen core health/model/broker checks), except for the code-signing polish.

---

## 0.3.0 — Strategy validation

Priority: stop confusing a backtest with evidence.

| Item | Why |
|------|-----|
| ⬜ In-app backtester over stored candles | One dataset, one cost model |
| ⬜ Spread, commission, swap, slippage model | Backtests must pay to play |
| ⬜ Walk-forward splits + out-of-sample lockbox | Kill overfitting |
| ⬜ Monte Carlo trade reshuffle | Confidence intervals, not a single equity curve |
| ⬜ Parameter sensitivity grid | Robustness > best cell |
| ⬜ Demo-vs-backtest divergence report | Detect regime/execution drift |
| ⬜ Strategy registry with versioned rules | Know exactly what ran |
| ⬜ Trade journal analytics (R-multiples, expectancy, MAE/MFE) | Feedback that changes rules |
| ⬜ Explicit “no-edge” verdict | The tool must be allowed to say no |

**Validation gate before any live suggestion:**

- ≥ 30 closed demo trades on the exact symbol/timeframe/cost model.
- Profit factor above the user’s threshold, with a confidence interval.
- Max drawdown inside the configured cap.
- Out-of-sample and walk-forward results consistent with in-sample.
- No single trade contributing more than ~30% of total profit.
- Timestamps verified against UTC; stale-bar handling tested.

Backtests alone never unlock live. The app should show “not validated” until the
demo sample exists.

---

## 0.4.0 — Multi-account and teams

| Item | Why |
|------|-----|
| ⬜ Multiple simultaneous accounts with per-account limits | Demo + live side by side |
| ⬜ Portfolio-level exposure and correlation checks | Per-order limits are not enough |
| ⬜ Read-only share link for a mentor/risk partner | Oversight without credentials |
| ⬜ Role separation (trader vs approver) | Two-person rule for size |
| ⬜ SSO / OS auth for the core | Replace the shared token |
| ⬜ Webhooks out (Slack/Telegram) for approvals and fills | Faster human response |
| ⬜ Mobile push for pending approvals | The phone becomes useful |

---

## 0.5.0 — Research workflow

| Item | Why |
|------|-----|
| ⬜ Dataset manager (symbols, timeframes, gaps) | Reproducible research |
| ⬜ Feature registry with point-in-time guarantees | No look-ahead |
| ⬜ Notebook bridge (export candles/features) | Use Python where it belongs |
| ⬜ Model comparison dashboard (not just one ensemble) | Evidence over vibes |
| ⬜ News/event calendar with blackout automation | Avoid known landmines |
| ⬜ Execution quality analytics (slippage by hour/symbol) | The hidden tax |

---

## 1.0.0 — Criteria

Ship 1.0 only when all are true:

- [ ] Clean-VM install works on Windows and macOS with no manual Python.
- [ ] Android APK connects over HTTPS and approves an order end-to-end.
- [ ] Every broker adapter supports account, positions, place and close.
- [ ] Spread/commission/slippage are enforced or explicitly disclosed per adapter.
- [ ] Backtest + walk-forward + Monte Carlo + demo gate implemented and documented.
- [ ] Audit log export and tamper-evidence story documented.
- [ ] Zero critical security issues in a third-party review.
- [ ] A user can explain, from the UI, why every order was allowed or blocked.
- [ ] Documentation matches behavior; no “TODO” claims.

---

## Intentionally excluded

| Idea | Why not |
|------|---------|
| Martingale / grid recovery | Ruin risk; contradicts the risk gate |
| “AI decides everything” autonomous live mode | No accountability, no auditability |
| Copy-trading / signal marketplace | Incentive to overstate results |
| Guaranteed-return marketing | Fraud |
| Leverage above regulatory norms | Blow-up risk |
| Storing broker passwords on the phone | Expands the attack surface for no benefit |
| Hiding fees in paper PnL | Makes validation meaningless |

---

## Lessons carried into this design

From the parent `forex_trader_bot` work and the wider research:

- A frozen backtest is **historical data**, not out-of-sample evidence.
- Timestamps that are not verified UTC poison every downstream metric.
- A 30-trade demo gate with PF ≥ 1.2 is a minimum, not a finish line.
- Watchdogs must be independently verified; a process that “should” restart
  something often does not.
- The only durable edge in retail algo trading is process discipline: small risk,
  hard stops, validated rules, and a human who can say no.

---

## How to influence the roadmap

Open an issue with:

1. The problem (observable behavior, not a preferred solution).
2. A reproduction with the paper account.
3. Why the current design is insufficient.

Safety fixes jump the queue. Feature requests that increase autonomous live
trading without new evidence do not.
