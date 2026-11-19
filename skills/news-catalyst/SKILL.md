---
name: News and Catalysts
description: Economic calendar, headlines and blackout windows around high-impact events.
---

# News and Catalysts

Use before entries, and any time price moves without a technical reason.

## Workflow

1. `get_news("<symbol> forex")` and `get_news("central bank <currency>")`.
2. `web_search("<currency> economic calendar today")` if the calendar matters.
3. Classify each item:

| Class | Examples | Action |
|---|---|---|
| Red | FOMC, CPI, NFP, GDP, rate decision | no new trade 30 min before/after |
| Amber | PMI, retail sales, central bank speech | half size, tighter stop |
| Green | analyst notes, minor data | ignore for entries |

4. Check the session: forex liquidity is best at London (07:00-16:00 UTC) and
   New York (12:00-21:00 UTC). Avoid the 21:00-22:00 UTC rollover spread spike.
5. On crypto, weekends are thinner - size down, expect wicks.

## Blackout rule

If a red event is within 30 minutes:
- no new entries
- do not widen stops to "make room"
- existing positions: either accept the risk or reduce before the release

## Sourcing rules

- Prefer primary sources: central bank sites, statistics agencies, exchange notices.
- A headline is not a fact until a second source confirms it.
- Never trade a rumour from a single social post.
- Always timestamp the news in UTC.

## Output

```
Next red event: <name> at <UTC time> (<currency>)
Blackout: yes/no
Headline risk: low/medium/high
Action: trade normally / half size / stand aside
```
