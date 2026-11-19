---
name: Position Sizing
description: Fixed-fractional and fractional-Kelly sizing with hard caps. Never risk more than the plan.
---

# Position Sizing

Use whenever a volume is needed. Sizing is derived from the stop, never guessed.

## Fixed fractional (default)

```
equity      = account equity
risk_pct    = min(user_limit, 1.0)          # default 1%
risk_usd    = equity * risk_pct / 100
stop_points = abs(entry - stop)
lots        = risk_usd / (stop_points * contract_size)
lots        = floor(lots * 100) / 100       # round down
lots        = max(0.01, min(lots, max_lot))
```

If the minimum lot risks more than the limit, **do not trade** - the setup does
not fit the account.

## Fractional Kelly (optional, only with a measured edge)

```
win_rate p, payoff b = avg_win / avg_loss
kelly  = (p*b - (1-p)) / b
size   = kelly * 0.25                       # quarter Kelly
risk_pct = min(size, 1.0)
```

Only use Kelly with >= 100 verified trades from the journal. Below that, use
fixed fractional. Never full Kelly.

## Volatility adjustment

- ATR > 1.5x its 20-period mean: halve size.
- ATR < 0.6x mean: do not increase size - low volatility often precedes a spike.
- Correlated positions (EURUSD + GBPUSD long): combined risk counts as one.

## Example

Equity $10,000, risk 1% = $100. EURUSD entry 1.0850, stop 1.0820 => 30 pips.
1 lot = $10/pip => 0.33 lots risks $99. Round down to 0.33.

## Output

Show the arithmetic in one line so the user can audit it:
`$100 risk / (30 pips x $10) = 0.33 lots`.
