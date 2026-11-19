---
name: Trade Journal
description: After-action review for every closed trade, with R-multiples and lessons that change rules.
---

# Trade Journal

Use after a close, at the end of a session, and for the weekly review.

## Per-trade entry (append with `journal_note`)

```
Date (UTC):
Symbol / side:
Entry / exit / stop / target:
Volume and risk ($ / %):
R multiple:        (exit - entry) / (entry - stop), signed
Thesis (1 line):
What actually happened:
Execution quality: slippage, spread, latency
Mistake:           none / early entry / late exit / oversized / revenge / moved stop
Rule change:       none, or the exact wording change
```

## Weekly stats

- trades, win rate, average win, average loss, expectancy in R
- profit factor = gross win / gross loss
- max losing streak, max drawdown
- % of trades that followed the checklist
- top 3 mistakes by cost

## Rules that actually change behaviour

1. Every loss gets a mistake label. "Bad luck" is not a label.
2. After 3 consecutive losses, size halves until the next win.
3. After a -2% day, stop. No exceptions.
4. A rule change needs 20 trades of evidence, not one bad day.
5. Journal the **process**, not the PnL. PnL is an output.

## Review prompts

- Did I take a trade that was not on the plan?
- Did I skip a valid setup out of fear?
- Did I move a stop? Why?
- Which hour of the day produced the worst trades?

## Guardrails

- Never delete a losing trade from the journal.
- Never edit history to make the stats look better.
- The journal is local: `%APPDATA%\AI-TRADER\journal.md`.
