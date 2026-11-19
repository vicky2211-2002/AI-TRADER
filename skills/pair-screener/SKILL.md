---
name: Pair Screener
description: Rank a watchlist by trend quality, volatility and spread so only the best setup is traded.
---

# Pair Screener

Use for "what should I trade today?" or a morning routine.

## Universe

Default: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, XAUUSD, BTCUSD, US30.
Only symbols the broker actually offers (check `get_quote`).

## Score (0-100)

| Factor | Weight | Rule |
|---|---|---|
| Trend alignment | 30 | price vs SMA20/50/200 agree |
| ADX / momentum | 20 | RSI14 distance from 50 |
| Volatility fit | 20 | ATR between 0.7x and 1.5x its mean |
| Structure clarity | 20 | clean swings, no chop |
| Spread / session | 10 | normal spread, active session |

## Procedure

1. `get_quotes` for the universe.
2. `technical_analysis` on each (4h), then the top 3 on 1h.
3. Drop anything with a red news event in the next 2 hours.
4. Rank, keep the top 2, and explain the losers in one line each.

## Output

| # | Symbol | Bias | Score | ATR | Setup | Why |
|---|---|---|---|---|---|---|
| 1 | ... | LONG | 82 | 0.0041 | pullback to SMA20 | ... |

Then: "Best risk-adjusted setup: <symbol>. Do you want a ticket?"

## Rules

- No more than 2 concurrent positions.
- If everything scores below 60, the answer is "no trade today".
- Never rank a symbol you cannot price.
