# Skills catalog

Skills are Markdown playbooks that teach the agent *how* you want a job done:
risk rules, analysis order, journal format, broker onboarding. They are the same
idea as Claude skills — a folder with a `SKILL.md` — stored in
`AI-TRADER/skills/`.

The agent sees the enabled skill list and reads a full playbook with the built-in
`read_skill` tool when it needs it. Skills are **instructions, not code**. They
cannot place an order or bypass the risk gate.

---

## The 27 skills (v0.1.1+)

**16 built-in + 11 from [trader-skill](https://github.com/Jakeschincariol/trader-skill) (MIT licensed)**

### Analysis

| Skill | What it does | Use it when |
|-------|--------------|-------------|
| **market-analyst** | Top-down regime → structure → levels → catalyst, before any idea | Starting a session or a new symbol |
| **technical-analysis** | Price-action playbook: structure, ATR stops, R-multiples, explicit invalidation | Turning a bias into levels |
| **pair-screener** | Ranks a watchlist by trend quality, volatility and spread | Choosing what to trade today |
| **news-catalyst** | Economic calendar, headlines, blackout windows | Before entries around CPI/NFP/FOMC |
| **web-research** | Uses Playwright/Firecrawl/Fetch/Tavily MCP tools to research markets and brokers | The answer is on a live web page |

### Risk & sizing

| Skill | What it does | Use it when |
|-------|--------------|-------------|
| **risk-manager** | Pre-trade gate: size from the stop, reject anything over limits | Every order proposal |
| **position-sizing** | Fixed-fractional and fractional-Kelly with hard caps | Deciding lot size |
| **portfolio-rebalance** | Exposure, correlation and cash buffer without overtrading | Multiple open positions |
| **prop-firm-guard** | Daily loss, consistency and news rules for funded accounts | Trading a prop/funded account |
| **crypto-perp-guard** | Funding, liquidation distance and exchange-risk checks | Perpetual futures |

### Execution & process

| Skill | What it does | Use it when |
|-------|--------------|-------------|
| **trade-execution** | Idea → risk check → approval → broker ticket → record | Sending an order |
| **trade-journal** | After-action review with R-multiples and rule changes | After every close |
| **backtest-validator** | Validation gates before demo and before live; kills overfit ideas | Evaluating a strategy |

### Platform

| Skill | What it does | Use it when |
|-------|--------------|-------------|
| **model-provider-setup** | Add and verify any OpenAI/Anthropic/Google-compatible endpoint | Connecting a model |
| **broker-connect** | Step-by-step MT5/Octa, MetaAPI, OANDA, Alpaca, CCXT onboarding with demo checks | Connecting a broker |
| **mcp-builder** | Add, edit, test and remove MCP servers safely | Extending tools |

---

### trader-skill pack (11 skills, MIT licensed)

*Cloned from [Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill)*

| Skill | What it does | Use it when |
|-------|--------------|-------------|
| **trader-analyst** | Reads SEC EDGAR XBRL facts (10-Q/10-K/8-K) and sums up quarterly revenue, margins, EPS | "How did Apple's earnings look", "analyze the earnings", "check the 10-Q" |
| **trader-broker** | Places APPROVED orders through your broker; only fires after trader-risk passes and you type yes | Executing a trade idea that passed risk checks |
| **trader-budget** | Sizes every position to your budget before it reaches the broker | Deciding how much to buy/sell |
| **trader-copycat** | Reads 13F filings of famous investors and reverse-engineers their holdings | "What is Buffett buying", "copy Scion's portfolio" |
| **trader-news** | Watches breaking market news and SEC filings; classifies red/amber/green | Before entries, when price moves without technical reason |
| **trader-pelosi** | Tracks congressional stock trades (Pelosi tracker) via Senate PTR PDFs | "What did Congress trade this week" |
| **trader-rebalance** | Brings portfolio back to target weights without overtrading; respects correlation groups | Weekly, after big move, when adding symbol |
| **trader-risk** | Checks every proposed order against your limits; blocks anything over them; prints PASS/BLOCK | Before every order, always |
| **trader-screener** | Checks a list of companies against fundamental/technical rules; outputs a ranked table | "What should I buy", "screen my watchlist" |
| **trader-tax** | Tracks cost-basis lots for every position (FIFO/LIFO), estimates tax on closes | Tax planning, realizing losses, wash-sale checks |
| **trader-alerts** | Price alerts — rings when price target, stop or open interest is hit; writes JSON state | Setting targets, managing stops |

---

## Skill format

```markdown
---
name: Risk Manager
description: Pre-trade risk gate. Sizes the position from the stop and blocks anything over the user's limits.
---

# Risk Manager

## When to use
Before proposing any order.

## Method
1. Read account equity and current open positions.
2. Compute risk in account currency from entry, stop and lot size.
3. Reject if risk > the configured percent, if the stop is missing, or if a
   position already exists on the symbol.
4. Return the allowed lot size and the exact blocked reason.

## Hard rules
- Never widen a stop to make a trade fit.
- Never average down.
- One position per symbol.

## Output
A short table: symbol, side, entry, stop, risk %, lots, verdict.
```

Rules:

- The file must be named `SKILL.md` inside a folder whose id is lowercase
  letters, numbers, `-` or `_` (2–64 chars).
- Frontmatter is a simple `key: value` block between `---` lines. `name` and
  `description` are what the list shows.
- The body is ordinary Markdown. Headings, tables, checklists and code fences
  all render in the viewer.
- Keep it short enough for a model to read in one tool call. 100–250 lines is a
  good range.

---

## Managing skills in the UI

| Action | Where | Effect |
|--------|-------|--------|
| **New skill** | Skills → New skill | Creates `skills/<id>/SKILL.md` and registers it |
| **Edit** | Pencil | Full Markdown editor with frontmatter |
| **View** | Eye | Read-only renderer |
| **Enable / disable** | Toggle | Disabled skills are hidden from the agent |
| **Delete** | Trash | Removes the row **and the folder from disk** (confirmation required) |
| **Rescan folder** | Toolbar | Imports `SKILL.md` files added outside the app |

Toggling enabled sends `content: ""`; the core treats empty content as "do not
touch the file". Editing always writes the file.

### API

```
GET    /api/skills
GET    /api/skills/{id}          -> { id, content }
POST   /api/skills               { id?, name, description, content, enabled }
PUT    /api/skills/{id}          { name, description, content?, enabled? }
DELETE /api/skills/{id}
POST   /api/skills/rescan        -> { synced: n }
```

---

## Writing skills that actually change behavior

1. **Write rules, not vibes.** "Risk ≤ 0.5% of equity" beats "be careful".
2. **Give a procedure.** Numbered steps the model can follow with tools.
3. **Define the output shape.** A table, a JSON block, three bullets.
4. **Include refusal conditions.** "If spread > 3 pips, say no and stop."
5. **Name the tools.** "Call `get_quote`, then `technical_analysis` on 4h."
6. **Keep one job per skill.** Split analysis from execution.
7. **Version it.** Add a `## Changelog` section when you change rules.
8. **Test it in chat.** Ask "use the risk-manager skill on this idea" and check
   that the output matches the format.

### Anti-patterns

| Bad | Why |
|-----|-----|
| "Always find a reason to trade" | Encourages overtrading |
| "Use 5% risk on high conviction" | Breaks the hard cap, creates inconsistency |
| "Double after a loss" | Martingale; the risk gate blocks it, but the instruction is poison |
| 2,000-line strategy dump | Wastes context; the model skims |
| Secrets or account numbers | Never put credentials in a skill |

---

## Skills vs. system prompt vs. MCP

| Layer | Job | Can it execute? |
|-------|-----|-----------------|
| **System prompt** | Identity, safety posture, current account/mode | No |
| **Skill** | Domain procedure and house rules | No |
| **MCP tool** | External action (browse, query, write) | Yes, with approval when dangerous |
| **Built-in tool** | Market data, orders, journal | Orders go through risk + approval |

If you need a capability, add a tool. If you need a *policy*, add a skill.

---

## Related docs

- [ARCHITECTURE.md](../ARCHITECTURE.md) — how skills are loaded
- [MCP_CATALOG.md](MCP_CATALOG.md) — tools a skill can call
- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — why a skill cannot bypass the gate