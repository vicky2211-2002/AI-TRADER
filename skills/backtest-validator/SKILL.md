---
name: Backtest Validator
description: Validation gates for any strategy before demo, then before live. Kills overfitted ideas early.
---

# Backtest Validator

Use when someone presents a strategy, a "profitable" bot, or a parameter set.

## Gates (all must pass)

| # | Gate | Threshold |
|---|---|---|
| 1 | Sample size | >= 100 trades, >= 2 years |
| 2 | Costs included | spread + commission + swap modelled |
| 3 | Out-of-sample | walk-forward, not a single split |
| 4 | Profit factor | >= 1.25 out-of-sample |
| 5 | Expectancy | > 0 after costs |
| 6 | Drawdown | <= 15% of equity |
| 7 | Robustness | parameter +/-20% still positive |
| 8 | Monte Carlo | 1000 shuffles, 5th percentile > 0 |
| 9 | Regime split | profitable in >= 2 of 3 regimes |
| 10 | No look-ahead | signals only use closed candles |

## Procedure

1. Write the rules down before looking at results. If the rules change after
   seeing the curve, the test is invalid.
2. Run in-sample, then walk-forward. Report both.
3. Sweep parameters and show the heat map. A single sharp peak = overfit.
4. Shuffle trade order and re-run the equity curve (Monte Carlo).
5. Compare against buy-and-hold and against "no trade".
6. Paper trade >= 30 trades before any live discussion.

## Red flags

- Win rate > 90% with no costs
- Equity curve that only goes up
- Results that die when spread doubles
- "Works on every pair" with the same parameters
- Backtest on 1 month of data
- Strategy needs martingale/grid to be profitable

## Output

```
Verdict: PASS / FAIL / NEEDS WORK
Failed gates: ...
Evidence: <numbers>
Next step: paper 30 trades / fix costs / discard
```

The demo gate is 30 verified demo trades with PF >= 1.2. Live is a separate,
explicit decision by the user.
