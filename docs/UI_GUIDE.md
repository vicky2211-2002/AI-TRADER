# UI guide

AI-TRADER’s interface is deliberately quiet: warm paper background, serif
headlines, one accent colour for action. Everything important is either a risk
number or a button that sends money — nothing else competes for attention.

```
┌───────────────┬────────────────────────────────────────────────────────┐
│ AI-TRADER     │  [model ▾]  latency   [analyse|trade|ask]              │
│ + New chat    ├────────────────────────────────────────────────────────┤
│               │                                                        │
│ Recent        │   conversation / tool traces / approval cards          │
│  • EURUSD…    │                                                        │
│  • Gold plan  │                                                        │
│               │                                                        │
│ Workspace     ├────────────────────────────────────────────────────────┤
│ Chat          │  ┌──────────────────────────────────────────────────┐  │
│ Models        │  │ Ask about a market…                      [↑]     │  │
│ MCP servers   │  └──────────────────────────────────────────────────┘  │
│ Skills        │  Enter to send · account ▾ · risk % · approval on      │
│ Brokers       │                                                        │
│ Trades & risk │                                                        │
│ Settings      │                                                        │
├───────────────┤                                                        │
│ ● Core online │                                                        │
│ MT5 ready  ☾  │                                                        │
└───────────────┴────────────────────────────────────────────────────────┘
```

---

## Shell and navigation

| Element | Behavior |
|---------|----------|
| **New chat** | Clears the conversation; keeps the selected model |
| **Recent** | Last 12 conversations; hover a row for delete |
| **Workspace** | Autopilot, Models, MCP servers, Skills, Brokers, Trades & risk |
| **Footer** | Core online/offline, version, MT5 availability, theme toggle |
| **Mobile** | Sidebar becomes a drawer; a menu button appears in the header |
| **Offline screen** | Asks for a core URL and retries; use it for LAN/phone setups |

The top banner appears when the health pulse fails: “Core connection lost —
retrying. Orders cannot be sent.”

---

## Autopilot dashboard

The default view. It polls `/api/dashboard` every 5 seconds and answers “what is
the model / AI / bot doing right now, and what happened before?”.

### Status card

- **Running / stopped** — live dot, current stage (`analysing`, `asking models`,
  `executing`, `managing exits`, `waiting`), active symbol and cycle number.
- **Countdown** — seconds to the next cycle while the loop sleeps.
- **Models voting** — the exact provider · model labels being queried.
- **Last decision** — symbol, BUY/SELL/HOLD, confidence, status, age.
- **Risk posture** — risk %, max open, daily loss limit, trading mode.
- **Last error** — shown in amber when a cycle failed; the loop keeps going.

### Controls

| Button | Effect |
|--------|--------|
| **Start autopilot** | Saves the form, sets `autopilot_enabled=true`, starts the loop |
| **Stop** | Stops the loop; open positions and broker SL/TP are untouched |
| **Run one cycle** | One pass without starting the loop (disabled while running) |
| **Save config** | Persists the form without starting |
| **Kill switch** | Stops the loop and blocks all new orders |
| **Reset kill switch** | Clears the block; autopilot stays stopped until you press Start |
| **Refresh** | Immediate poll |

### KPI row

Equity, balance, today P&L (with floating P&L), total P&L and closed-trade count,
open positions with trades-today, win rate and profit factor.

### Equity curve

One point per cycle, last 2,000 kept. Flat until the first cycle runs.

### How it trades

Account, execution mode (`Hands-free` vs `Ask me`), cycle interval, watchlist,
symbols per cycle, max trades per day, confidence slider, voting-model chips,
**Resume after core restart** and **Allow live auto-execution**.

### History

- **Decisions** — newest first. Each row: time, symbol, action, confidence,
  status, price, P&L if any, models involved, reason. Expand **model votes** to
  see each model's individual action, confidence, latency and error.
- **Trades** — closed positions (time, symbol, side, volume, P&L, note) plus the
  last few orders with their status/ticket.
- **Open positions** — side, volume, entry/now/SL/TP, floating P&L, close button.
- **Bot activity** — recent audit entries from the core and the autopilot.

Full behaviour and limits: [AUTOPILOT.md](AUTOPILOT.md).

---

## Chat

### Header

- **Model picker** — only enabled providers. Shows `name · model`.
- **Status chip** — `412 ms` after a successful test, `untested`, or `no key`.
- **Mode**
  - `analyse` — read-only bias; orders only if you explicitly ask.
  - `trade` — may propose orders with SL/TP and a reason.
  - `ask` — general assistant, no trading framing.

### Empty state

Suggestions: analyse EURUSD, what moved gold, size a trade, review positions.
If no provider is enabled, a card points to **Models** instead.

### Messages

- User messages: right-aligned, soft panel.
- Assistant: sparkle avatar, markdown, tables, code blocks.
- **Tool cards** — collapsible: tool name, one-line summary, arguments and full
  JSON result. `running…` until the result arrives.
- **Typing dots** while streaming; **Stop** button replaces send.

### Approval cards

An order that passes the risk gate appears inline:

```
Approval required                              expires when you decide
BUY 0.02 EURUSD   acc_...    risk $14.20 (0.142%)
Entry 1.0971   SL 1.09   TP 1.13   Type market
"Donchian breakout, 4h close above channel"
[Approve & send] [Reject]
```

- **Approve & send** calls the broker and reports the ticket or the error.
- **Reject** closes the card and tells the model.
- Other approvals (dangerous MCP tools, position closes) use the same pattern
  with a JSON payload preview.

### Composer

- `Enter` sends, `Shift+Enter` adds a line.
- The textarea grows to 160 px.
- Bottom row: account picker, risk %, approval on/off — read-only reminders of
  the active settings.

---

## Models

- **Add provider** — name, kind, base URL, model, model list, headers, key.
- **Test** — per-row button; result appears as a chip and a toast.
- **Refresh models** — calls the vendor’s `/models` when supported.
- **Default star** — sets the provider used by new chats.
- **Edit / delete** — delete removes the encrypted key.
- **Key field** — shows a mask after saving; leave blank to keep the old key.

Empty state explains the free options and links to the provider doc.

---

## MCP servers

Two tabs:

- **Installed** — your servers with status dot, tool count, Start/Stop/Test,
  enable toggle, auto-start, edit, delete.
- **Catalog** — 22 presets. **Install** copies one in; already-installed items are
  marked.

Expanding a server lists its tools. Each tool opens a manual call dialog: JSON
arguments, **Call**, and the raw result. Useful for debugging an unfamiliar
server before letting the agent use it.

Badges: `running` green, `stopped` grey, `error` red with the message. If `npx`
or `uvx` is missing, a warning explains which runtime is absent.

---

## Skills

- Grid of cards: name, description, source (`bundled`/`local`), size, enabled
  toggle.
- **Eye** opens a rendered viewer.
- **Pencil** opens the Markdown editor with frontmatter.
- **New skill** starts from a template.
- **Rescan folder** imports skills added on disk.
- **Delete** removes the folder — the confirmation says so.

Skills are instructions. Disabling one hides it from the agent; it does not
affect orders already placed.

---

## Brokers

- **Kill switch** at the top: one click blocks every new order.
- Account cards: broker, environment, status, balance/equity if a snapshot was
  loaded, last error.
- **Add account** — the form is generated from the broker catalog, so fields
  differ per adapter. Secret fields are masked.
- **Test** — connects and loads a snapshot.
- **Details** — raw snapshot JSON.
- **Edit / delete** — deleting never closes broker positions.

Environment matters: `demo` and `live` are verified by the MT5 adapter. A
mismatch is refused, not “fixed”.

---

## Trades & risk

Four tabs:

| Tab | Contents |
|-----|----------|
| **Approvals** | Order cards and other approvals, with Approve/Reject |
| **Orders** | Every proposal: time, symbol, side, volume, entry, SL, TP, risk, status, ticket |
| **Positions** | Open positions with live PnL and a **Close** button (confirmation) |
| **Audit** | Append-only action log with actor and detail |

**New order** opens a proposal form:

1. Account, symbol, side, volume.
2. **Stop loss is required**; TP is optional.
3. Reason (shown on the approval card).
4. **Run risk check & propose** shows the full checklist inline:

```
Risk gate: BLOCKED
✓ Kill switch — Off
✓ Trading mode — DEMO
✓ Symbol allow-list — EURUSD
✗ Risk per trade — 2.355% > 1.0% ($235.50)
✓ Max open positions — 0/2
...
Blocked by: Risk per trade
```

A blocked order stays in the Orders tab with the reason. Nothing is sent.

---

## Settings

Sections:

1. **Trading mode** — paper/demo/live cards, live switch, approval, kill switch,
   auto-execute MCP tools.
2. **Risk limits** — risk %, daily loss, drawdown, positions, lots, spread,
   watchlist.
3. **Core connection** — URL (LAN/tunnel), access token, apply, restart core
   (desktop only).
4. **Appearance** — light/dark.
5. **System** — app version, platform, Python, data/skills paths, vault backend,
   host:port, MT5, Node/uv, plus the vault explanation.

**Save changes** is disabled until something changes. Live mode cannot be saved
while the live switch is off.

---

## Themes

- Light: warm paper (`#faf9f5`), terracotta accent.
- Dark: deep olive-black (`#181713`), lighter terracotta.
- Toggle in the sidebar footer or Settings.
- Stored in `localStorage`; the core also stores `theme` for new devices.
- Widgets, gauges, chips and code blocks all use CSS variables, so nothing is
  left unreadable.

---

## Keyboard and accessibility

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Esc` | Close modal |
| `Tab` | Move through controls |

- Buttons are real `<button>` elements; modals have `role="dialog"`.
- Status is conveyed by text as well as colour (`running`, `blocked`, `error`).
- Approval cards state the risk in dollars and percent, not colour alone.
- Focus rings come from the browser; the accent border on inputs is additional.

---

## Mobile layout

- Sidebar is a full-height drawer with a backdrop; closes on navigation.
- Chat header keeps the model picker, mode switch and a menu button.
- Tables scroll horizontally; cards stack.
- The composer sits above the keyboard (Capacitor `Keyboard.resize: native`).
- Settings/Core URL is the first thing to fix if the app shows “Core offline”.

---

## Empty, loading and error states

| State | What you see |
|-------|--------------|
| Booting | Logo + “starting the local core…” |
| Core offline | URL field, retry, and the start command |
| No provider | Card in chat and Models empty state |
| No MCP servers | Catalog CTA |
| No skills | “Rescan folder” / “New skill” |
| No orders | “No orders yet.” |
| Risk blocked | Full checklist, red rows, blocked-by line |
| Provider error | Inline red banner + toast; message kept in history |
| Stream aborted | Partial text stays; send again |

---

## Design tokens

| Token | Light | Dark |
|-------|-------|------|
| `--bg` | `#faf9f5` | `#181713` |
| `--panel` | `#f2f0e9` | `#201e19` |
| `--card` | `#ffffff` | `#23211b` |
| `--text` | `#26241f` | `#f1ede2` |
| `--muted` | `#6f6a5f` | `#a39d8e` |
| `--accent` | `#c96442` | `#d97757` |
| `--ok` | `#2f8f63` | `#62b98d` |
| `--warn` | `#b07d24` | `#d3a552` |
| `--err` | `#b2443a` | `#e07267` |

Fonts: Inter for UI, Georgia for display, JetBrains Mono/Cascadia for code.
Radii: 16 px cards, 10 px controls, pill chips.
