---
name: Portfolio Rebalance
description: Keep exposure, correlation and cash buffer inside the plan without overtrading.
---

# Portfolio Rebalance

Use weekly, after a big move, or when adding a symbol.

## Inputs

- open positions + floating PnL (`get_positions`)
- account equity (`get_account`)
- target allocation per asset class (defaults):
  - FX majors 50%
  - metals 20%
  - crypto 20%
  - indices 10%
- cash buffer >= 20% of equity

## Steps

1. Compute exposure per position: notional / equity.
2. Compute correlation groups:
   - USD bloc: EURUSD, GBPUSD, AUDUSD, XAUUSD, USDJPY (inverted)
   - crypto bloc: BTC, ETH, SOL
   - index bloc: US30, SPX500, NAS100
3. If a group exceeds 40% of equity, reduce the smallest-conviction position.
4. If a single position exceeds 25%, trim to 20%.
5. If cash < 20%, close the weakest position before opening anything else.
6. Re-check after each change - never rebalance in one blind burst.

## Output

| Position | Notional | % equity | Group | Action |
|---|---|---|---|---|
| EURUSD long | ... | 31% | USD bloc | reduce 1/3 |

Then: "Post-rebalance exposure: ... Cash: ...%".

## Rules

- Rebalance with limit orders where possible; avoid paying full spread twice.
- No rebalancing in the first 15 minutes of a session.
- Do not rebalance a losing position just because it is small.
- Rebalancing is risk management, not a profit strategy.
