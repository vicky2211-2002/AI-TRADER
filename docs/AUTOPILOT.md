# Autopilot — models decide, the risk gate disposes

AI-TRADER's autopilot is a background loop that lets your configured models
choose **BUY / SELL / HOLD** on their own, sizes the trade from your risk budget,
and sends it through the **same hard risk gate** as every manual order. The
dashboard shows what the models, bot and broker are doing right now, plus the
full decision history.

> **There is no profit guarantee.** Model output is a forecast, not a fact.
> Autopilot is designed to make the process disciplined and auditable — not to
> promise returns. Run it on **paper** until you have your own verified
> track record, and never enable live hands-free trading with money you cannot
> afford to lose.

---

## 1. What "automatic" means here

| Layer | Who decides |
|-------|-------------|
| Direction (BUY/SELL/HOLD) | Your voting models (1–3 providers), each returning strict JSON |
| Stop loss / take profit | The winning votes' `sl_atr` / `tp_atr` multiples of ATR14 |
| Position size | The core: `risk% × equity ÷ (stop distance × contract size)` |
| Whether the order is allowed | The **hard risk gate** — kill switch, live switch, daily loss, drawdown, spread, symbol allow-list, lot cap, open-position cap |
| Execution | The selected broker adapter (paper by default) |

The model can propose. It cannot bypass the gate, cannot raise its own lot size,
and cannot trade a symbol outside the allow-list.

---

## 2. One cycle, step by step

1. **Read account + positions** from the selected broker (paper by default).
2. **Manage exits first** (paper broker): any position whose quote crossed its
   SL or TP is closed and logged as a `CLOSE` decision.
3. **Check entry conditions**: kill switch, max open positions, daily autopilot
   trade cap.
4. **Pick symbols**: a rotating slice of the watchlist
   (`autopilot_symbols_per_cycle`, default 2) so you don't burn model calls on
   every symbol every cycle.
5. **Fetch market context**: live quote + 1h candles → price, SMA20/50/200,
   RSI14, ATR14, trend, 20-bar high/low, last 10 closes.
6. **Ask the models** in parallel. Each gets the same JSON context and must reply
   with exactly one object:
   ```json
   {"action":"BUY|SELL|HOLD","confidence":0.0,"reason":"<=240 chars","sl_atr":2.0,"tp_atr":4.0}
   ```
7. **Aggregate the votes** (see below). If the result is HOLD or below the
   confidence gate, the decision is recorded as `held`.
8. **Size the order** from the risk budget, then call the normal order path with
   `auto_execute` — which still runs every risk check.
9. **Record everything**: decision row (votes + market snapshot), order row,
   audit entry, equity point. The dashboard reads these.

Between cycles the engine sleeps for `autopilot_interval_sec` (default 300s).

---

## 3. How votes are aggregated

- Only valid JSON decisions from enabled models count.
- If every model says HOLD → **HOLD** (reason taken from the most confident).
- If BUY and SELL weights are exactly equal → **HOLD**. A tie never picks a side.
- Otherwise the heavier side wins:
  - `share = weight(side) / weight(all active votes)`
  - `avg_conf = mean confidence of that side's voters`
  - `confidence = share × avg_conf` (0–1)
- `sl_atr` / `tp_atr` = mean of the winning votes (clamped to sane ranges).
- If `confidence < autopilot_confidence` → **HOLD**, recorded with the gate
  reason so you can see near-misses.

One model failing (timeout, bad JSON, missing key) is recorded as a failed vote
with its error. It does not silently become a HOLD vote, and it does not crash
the cycle.

---

## 4. Position sizing

```
risk_usd  = equity × max_risk_per_trade_pct / 100
sl_dist   = ATR14 × sl_atr
volume    = risk_usd / (sl_dist × contract_size)
volume    = floor(volume, 0.01), capped at max_lot_size
```

If the result is below the minimum lot, the trade is skipped and the decision is
recorded as `held` ("risk budget too small for the minimum lot"). No order is
sent with a fabricated size.

---

## 5. Exits

| Broker | Stop loss / take profit enforced by |
|--------|-------------------------------------|
| `paper` | The autopilot itself, each cycle (quote vs SL/TP) |
| `demo` / `live` (MT5, OANDA, MetaAPI, etc.) | The broker, server-side, from the SL/TP sent with the order |

For real brokers the autopilot does **not** second-guess the broker: the order
carries its SL/TP at entry, and the broker closes it. The loop still records the
close when it sees the position disappear from the account.

---

## 6. Safety invariants

These hold no matter what the model says:

- **Off by default.** `autopilot_enabled=false` until you press Start (or set
  `autopilot_autostart`).
- **Kill switch wins.** `kill_switch=true` blocks every new order and halts the
  loop.
- **Live needs two switches.** Live auto-execution requires both
  `allow_live_trading=true` **and** `autopilot_allow_live_auto=true`. Otherwise
  live orders become approvals.
- **Same gate for everyone.** Daily loss %, peak drawdown %, spread, lot cap,
  open-position cap, symbol allow-list and stop-loss requirement are evaluated
  in `risk.evaluate_order` for autopilot orders exactly as for UI orders.
- **Daily trade cap.** `autopilot_max_trades_per_day` counts executed and
  pending-approval entries for the day.
- **Per-symbol cooldown.** After an entry, the symbol waits
  `autopilot_cooldown_sec` before another entry attempt.
- **Stale data is rejected.** A missing/stale quote skips the symbol and logs
  why; the bot never invents a price.
- **Full audit.** Every start, stop, cycle decision, block and kill is written to
  the audit log and visible on the dashboard.

---

## 7. Settings

All keys live in `Settings` and can be changed from the dashboard or
`PUT /api/settings`.

| Key | Default | Meaning |
|-----|---------|---------|
| `autopilot_enabled` | `false` | Loop on/off (Start/Stop) |
| `autopilot_autostart` | `false` | Resume after a core restart |
| `autopilot_interval_sec` | `300` | Seconds between cycles (60–86400) |
| `autopilot_symbols` | `[]` | Watchlist; empty falls back to `default_symbols` |
| `autopilot_symbols_per_cycle` | `2` | Symbols analysed per cycle (1–10) |
| `autopilot_provider_ids` | `[]` | Up to 3 voting models; empty = default model |
| `autopilot_execution` | `"auto"` | `auto` executes paper/demo; `approval` queues |
| `autopilot_confidence` | `0.55` | Minimum aggregated confidence to trade |
| `autopilot_max_trades_per_day` | `6` | Daily entry cap |
| `autopilot_sl_atr` | `2.0` | Default stop distance in ATR |
| `autopilot_tp_atr` | `4.0` | Default target distance in ATR |
| `autopilot_cooldown_sec` | `900` | Per-symbol re-entry cooldown |
| `autopilot_allow_live_auto` | `false` | Live hands-free (with `allow_live_trading`) |

---

## 8. Dashboard

Open **Autopilot** in the sidebar (it is the default view). It polls
`GET /api/dashboard` every 5 seconds and shows:

- **Live status** — running/stopped, current stage (`analysing`, `asking models`,
  `executing`, `managing exits`, `waiting`), symbol, cycle number, countdown to
  the next cycle, last error.
- **Models voting** — exactly which providers/models are being queried.
- **Last decision** — action, confidence, status and age.
- **Risk posture** — risk %, max open, daily loss limit, trading mode.
- **KPIs** — equity, balance, today P&L, total P&L, open positions, win rate and
  profit factor.
- **Equity curve** — one point recorded per cycle (last 2,000 kept).
- **How it trades** — account, execution mode, interval, watchlist, symbols per
  cycle, daily cap, confidence slider, voting models, autostart and live-auto
  switches.
- **Decisions history** — every cycle's outcome with the model's reason; expand a
  row to see **each model's individual vote, confidence, latency and error**.
- **Trades** — closed positions with P&L plus recent orders.
- **Open positions** — entry/now/SL/TP, floating P&L, one-click close.
- **Bot activity** — recent audit entries.

Controls: **Start autopilot**, **Stop**, **Run one cycle**, **Save config**,
**Kill switch** / **Reset kill switch**, **Refresh**.

---

## 9. Trying it without money

1. **Models** → add a provider and press **Test** until it answers. Free options
   are listed in [FREE_API_PROVIDERS.md](FREE_API_PROVIDERS.md).
2. **Brokers** → confirm the seeded **Paper** account is selected (or create a
   demo account).
3. **Autopilot** → keep execution on `Hands-free`, pick your watchlist and
   voting models, press **Run one cycle**.
4. Watch the decision row appear with per-model votes. If it says `held`, the
   reason tells you whether it was a HOLD vote, a confidence miss, or the risk
   gate.
5. Only then press **Start autopilot**.

A cycle needs at least one working provider. With no enabled provider the
endpoint returns `{"ok": false, "error": "No enabled model provider..."}` — that
is a configuration error, not a crash.

---

## 10. Limitations — read before trusting it

- **Models can be wrong, slow or rate-limited.** Free tiers often throttle. A
  failed vote is recorded and ignored; if all fail, the cycle is a HOLD.
- **Market data is best-effort.** Quotes come from Yahoo (unofficial) with MT5
  fallback. Stale data blocks entries rather than guessing.
- **Paper fills are simplified.** No queue position, no partial fills, no swap
  beyond the modelled rollover. Paper results are an upper bound on real
  performance.
- **Costs matter.** Spread, commission and slippage decide whether a thin edge
  survives. The risk gate caps spread but cannot model everything.
- **Local exits only work while the core runs** (paper broker). If the app is
  closed, paper positions do not get their SL/TP checked until it runs again.
- **Timestamps are local to the core host.** Session boundaries and daily caps
  use the host clock.
- **Not investment advice.** You are responsible for every order.

---

## 11. API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/dashboard` | Everything the dashboard needs |
| GET | `/api/autopilot` | Engine status |
| GET | `/api/autopilot/decisions?limit=60` | Decision history |
| POST | `/api/autopilot/start` | Start (optional config overrides) |
| POST | `/api/autopilot/stop` | Stop (positions untouched) |
| POST | `/api/autopilot/run-once` | One cycle without starting |
| POST | `/api/autopilot/kill` | Kill switch + stop |

See [API_REFERENCE.md](API_REFERENCE.md) for payloads.

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `No enabled model provider` | Add or enable a provider in **Models**, and press **Test** |
| `HOLD` with "First error: No API key configured" | The selected provider has no key (only localhost URLs may skip a key). Add one in **Models** |
| Every decision is `held` with "Below confidence gate" | Lower `autopilot_confidence` slightly or pick models that agree |
| `held` with "Risk budget too small for the minimum lot" | Increase equity/risk % or widen the stop; the core will not round up the lot |
| Decisions show `blocked` | Read `blocked_by` in the decision / order — usually kill switch, live disabled, spread or lot cap |
| No new entries | Max open positions, daily cap or per-symbol cooldown reached |
| `last_error` mentions stale quote | Market data unavailable; the bot refuses to trade blind |
| Live orders still need approval | `autopilot_allow_live_auto` is off — this is intentional |

---

## Related docs

- [ARCHITECTURE.md](../ARCHITECTURE.md) — where the engine sits in the core
- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — every risk check explained
- [BROKER_INTEGRATION.md](BROKER_INTEGRATION.md) — broker setup and SL/TP behaviour
- [FREE_API_PROVIDERS.md](FREE_API_PROVIDERS.md) — free models to vote with
- [UI_GUIDE.md](UI_GUIDE.md) — screen-by-screen tour
