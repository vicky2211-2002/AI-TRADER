---
name: Crypto Perp Guard
description: Funding, liquidation distance and exchange-risk checks for perpetual futures.
---

# Crypto Perp Guard

Use for BTC/ETH/SOL perpetual futures, not spot.

## Before any perp entry

1. **Leverage** - default max 3x. Above 5x requires explicit user confirmation.
2. **Liquidation distance** - must be at least 3x the stop distance. If not,
   lower leverage or skip.
3. **Funding** - check the current and predicted funding rate. Positive funding
   charges longs; avoid entering a crowded long right before funding.
4. **Open interest** - a rapid OI spike + flat price = squeeze risk.
5. **Exchange risk** - keep only trading capital on the exchange, never savings.

## Sizing with leverage

```
notional = equity * risk_pct / (stop_pct)
margin   = notional / leverage
```

Risk stays the same in dollars; leverage only changes margin, not risk.

## Rules

- Always use isolated margin, never cross, for an automated strategy.
- Stop loss is mandatory and must sit on the exchange, not "mental".
- No averaging down. No removing a stop.
- Weekend liquidity is thin: half size.
- Stablecoin depeg or exchange maintenance = stand aside.

## Output

```
Symbol / side: ...
Leverage: ...x   Margin: $...
Stop: ... (liquidation at ...)
Funding: ...%/8h
Verdict: PASS / BLOCK (reason)
```
