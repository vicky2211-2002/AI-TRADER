---
name: Trade Execution
description: Turn an approved idea into a broker ticket. Proposal, approval, fill, record.
---

# Trade Execution

Use when the user says "buy", "sell", "close", "take the trade" or approves a
proposal.

## Flow (never skip a step)

1. **Confirm the idea** is still valid: price has not run past the entry zone and
   no red news landed in the last 5 minutes.
2. **Build the ticket**:
   - symbol, side, volume (from the Risk Manager formula)
   - stop loss (mandatory)
   - take profit (>= 2R)
   - reason (one line, stored in the audit log)
3. **Call `place_order`**. This only *proposes* the order. The hard risk gate in
   the core evaluates it and the UI shows an approval card.
4. **Wait for the user's yes.** Never say "order placed" before a fill event
   exists. Paper fills are instant; MT5 returns a ticket.
5. **Record** the result: ticket, fill price, slippage, and the original thesis.

## Broker notes

- **MT5**: symbol may need a suffix (`.m`, `.raw`, `micro`). Connect the terminal
  first, log in, enable Algo Trading. Demo accounts only until verified.
- **Paper**: fills at the latest quote, no slippage. Good for testing the flow.
- **OANDA**: units, not lots. 1 lot EURUSD = 100,000 units.
- **Alpaca**: bracket orders carry the SL/TP.
- **CCXT**: keep API keys read+trade only, never withdrawal.

## Failure handling

| Error | Action |
|---|---|
| `Invalid stops` | widen the stop beyond the broker minimum, resend |
| `No money` | reduce lots, never increase leverage |
| `Market closed` | wait for the next session, do not queue blindly |
| `Trade disabled` | the terminal/account has algo trading off |
| Timeout | check positions before retrying - the order may have filled |

## Guardrails

- One retry maximum per ticket.
- Never re-send after an ambiguous timeout until positions are checked.
- Never close a position the user did not ask to close.
- Every order must be traceable in Trades and the audit log.
