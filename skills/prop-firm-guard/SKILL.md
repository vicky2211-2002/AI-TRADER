---
name: Prop Firm Guard
description: Protect a funded/prop account with daily loss, consistency and news rules.
---

# Prop Firm Guard

Use for FTMO-style evaluations and funded accounts. Rules vary by firm - always
paste the firm's actual numbers into the plan first.

## Typical limits (verify with your firm)

| Rule | Typical value |
|---|---|
| Daily loss | 5% (includes floating) |
| Max loss | 10% |
| Profit target | 8-10% |
| Consistency | no day > 40-50% of total profit |
| News trading | restricted around red events |
| Weekend holding | often forbidden on crypto/indices |

## Operating rules

1. Set AI-TRADER's daily loss to **half** the firm's limit (e.g. 2.5% for a 5% rule).
2. Risk 0.5-1% per trade. Two losses in a day = stop.
3. Never hold a position through a red event if the firm forbids it.
4. Keep a buffer: stop at 80% of the profit target, then reduce size.
5. Log the firm's exact rules in the journal and re-read before each session.

## Pre-session check

- [ ] Daily loss used so far
- [ ] Distance to max loss
- [ ] Consistency percentage
- [ ] Red news in the next 4 hours
- [ ] Weekend/holding restriction

## If a limit is close

- Close risk, do not "trade out of it".
- The software's kill switch is the final authority.
- A blown account is unrecoverable; a missed trade costs nothing.

## Output

```
Firm limit: ...
Used today: ...
Remaining: ...
Max risk per trade: ...
Verdict: trade / reduced size / stop for the day
```
