---
name: Technical Analysis
description: Price-action playbook with ATR stops, R-multiples and explicit invalidation.
---

# Technical Analysis

Use when the user asks for entry/exit levels or a chart read.

## Inputs

Call `technical_analysis(symbol, interval)` and `get_quote(symbol)`.
Prefer 4h for bias, 1h for entry, 15m only for timing.

## Checklist

| Item | Rule |
|---|---|
| Trend | Price vs SMA20/SMA50/SMA200 |
| Momentum | RSI14 > 55 bullish, < 45 bearish, 45-55 = no edge |
| Volatility | ATR14 = stop unit |
| Structure | Last swing high/low must agree with the bias |
| Reward | TP >= 2x SL distance (2R) or skip |

## Trade template

```
Side:        BUY / SELL
Entry:       market or limit at ...
Stop loss:   entry -/+ 1.5 * ATR14   (never tighter than the spread x 3)
Take profit: entry +/- 3.0 * ATR14   (2R)
Risk:        ...% of equity (= $...)
Invalidation: 4h close beyond ...
```

## Rules

1. One setup per symbol. If a position is already open, no second entry.
2. Stop goes on the structural level, then size the lot from the stop distance -
   never the other way round.
3. Never move a stop away from price. Trailing only reduces risk.
4. If RSI and structure disagree, stand aside.
5. Breakeven move only after +1R and only if the trade is older than one candle
   on the entry timeframe.

## Output

Give the template above, then one sentence on why *now* is the moment.
No trade is a valid answer.
