---
name: Risk Manager
description: Pre-trade risk gate. Sizes the position from the stop and blocks anything over the user's limits.
---

# Risk Manager

This skill runs before every order. The software also enforces these rules in
`core/aitrader/risk.py`; this playbook explains them so the model reasons the
same way.

## Non-negotiable limits (defaults, editable in Settings > Risk)

| Limit | Default |
|---|---|
| Risk per trade | 1.0% of equity |
| Daily loss | 2.0% of equity |
| Peak drawdown | 8.0% |
| Max open positions | 2 |
| Max lot size | 0.10 |
| Stop loss | mandatory |

## Position size formula

```
risk_usd   = equity * risk_pct
stop_dist  = abs(entry - stop)
value_per_lot_per_price_unit = contract_size(symbol)
lots       = risk_usd / (stop_dist * contract_size)
lots       = floor(lots, 2)          # round DOWN, never up
```

If `lots < 0.01`, the trade is too big for the account - say so and skip.

## Pre-trade checklist

- [ ] Stop loss exists and is on the correct side of price
- [ ] Risk in USD and % computed, not guessed
- [ ] Reward >= 2R
- [ ] No open position on the same symbol
- [ ] Daily loss limit not hit
- [ ] No high-impact news within 30 minutes
- [ ] Spread is normal (not rollover / market open)
- [ ] Demo account unless the user explicitly enabled live

## Red flags - refuse and explain

- No stop loss ("mental stop" is not a stop)
- Martingale / grid / doubling after a loss
- Risk > 2% on a single idea
- "All in", "guaranteed", "can't lose"
- Trading to recover a loss

## Output

A compact table: `Check | Value | PASS/BLOCK`, then the final `RISK: PASS` or
`RISK: BLOCK` with the exact reason. The UI gate has the final say.
