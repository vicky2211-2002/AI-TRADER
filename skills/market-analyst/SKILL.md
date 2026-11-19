---
name: Market Analyst
description: Top-down market analysis - regime, structure, levels, catalysts - before any trade idea.
---

# Market Analyst

Use this skill when the user asks "what is the market doing", "should I trade today",
or before every trade proposal.

## Method (in order)

1. **Regime** - Is the market trending, ranging or risk-off? Check the higher
   timeframe first (1d then 4h). Use `technical_analysis` on the lead symbol
   (EURUSD for FX, BTCUSD for crypto, US30 for indices).
2. **Structure** - Mark the last 3 swing highs/lows. Higher highs + higher lows =
   uptrend. Lower highs + lower lows = downtrend. Anything else = range.
3. **Levels** - Identify the nearest support and resistance, the daily open, the
   previous day's high/low and the round number. These are the only levels that
   matter for the stop.
4. **Catalyst** - Use `get_news` for the symbol and check the economic calendar
   for high-impact releases in the next 8 hours (CPI, NFP, FOMC, central bank
   speeches). If a red event is within 30 minutes, no new trade.
5. **Volatility** - ATR14 on the entry timeframe sets the stop distance. If ATR
   is more than 1.5x its 20-period average, halve the position size.
6. **Verdict** - One of: `LONG bias`, `SHORT bias`, `NO TRADE`. State the
   invalidation level that flips the verdict.

## Output contract

```
Regime:      trending up / range / risk-off
Bias:        LONG / SHORT / NONE
Entry zone:  ...
Stop:        ... (reason: below swing low / ATR x1.5)
Target:      ... (reason: prior high / 2R)
Invalidation: price closes below ...
Catalyst risk: ...
```

## Guardrails

- Never call a direction without a level that proves you wrong.
- Do not average down. Do not add to a losing position.
- If data is missing or stale, say "no read" instead of guessing.
- This is analysis, not financial advice.
