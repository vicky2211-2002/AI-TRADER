---
name: Broker Connect
description: Step-by-step onboarding for MT5/Octa, MetaAPI, OANDA, Alpaca and CCXT - with demo verification.
---

# Broker Connect

Use when the user wants to connect a broker or an account shows `error`.

## 1. MetaTrader 5 (Octa, IC Markets, Exness, ...)

Needs Windows and the MT5 desktop terminal (the Python package talks to it).

1. Install MT5 and log in to the account **once** in the terminal.
2. Enable **Tools > Options > Expert Advisors > Allow algorithmic trading**.
3. In AI-TRADER: Brokers > Add account > MetaTrader 5.
   - login: the account number
   - password: the **investor or main** password (stored encrypted locally)
   - server: exactly as shown in MT5, e.g. `OctaFX-Demo`
   - path: optional `terminal64.exe`
4. Click **Test**. A green card must show `trade_mode: DEMO`.
5. If the symbol has a suffix (`EURUSD.m`), set it in the account config.

Safety: a REAL account is refused while the adapter is set to `demo`.
Flip to live only in Settings > Risk after the demo gate passes.

## 2. MetaAPI (macOS / Android / cloud)

MT5 cannot run on macOS or Android. MetaAPI hosts the terminal for you.

1. Create a MetaAPI account, add your broker account, wait for `DEPLOYED`.
2. Copy the **auth token** and **account id**.
3. AI-TRADER: Brokers > Add > MetaAPI cloud. Region defaults to `new-york`.
4. Test. Use demo credentials until you have 30 verified demo trades.

## 3. OANDA v20

1. Practice account > Manage API access > generate token.
2. Broker config: token + account id. Practice base URL is used when the
   environment is `demo`.

## 4. Alpaca

1. Paper account > API keys.
2. Broker config: key id + secret. Paper endpoint is the default.
3. Crypto pairs use `BTC/USD`; the adapter converts `BTCUSD` automatically.

## 5. CCXT (crypto)

1. Exchange > API management > create key with **read + trade only**.
2. Broker config: exchange id (`binance`, `bybit`, `okx`...), key, secret,
   market type (`spot` / `future`).
3. Test, then start with the smallest lot the exchange allows.

## Common errors

| Symptom | Fix |
|---|---|
| `MT5 initialize failed` | terminal not running / wrong path / 32-bit Python |
| `Authorization failed` | wrong login, investor password, or wrong server |
| `Symbol not found` | add the suffix, or enable the symbol in Market Watch |
| `trade_mode LIVE` while demo | wrong account number - stop and re-check |
| `Insufficient balance` | reduce volume; never raise leverage to force a trade |

## Acceptance

An account is "connected" only when Test returns a balance and a trade mode.
Everything else is `error` with the broker's own message shown to the user.
