# AGENTS.md — Polymarket Streak Bot

## Project Overview
A Python bot that trades BTC 5-min up/down markets on Polymarket using either:
1. **Streak reversal strategy** — bet against streaks of consecutive outcomes
2. **Copytrade strategy** — copy trades from specific wallet addresses

## Architecture
- `bot.py` — Main event loop for streak strategy. Monitors markets, checks streaks, places bets.
- `copybot.py` — Main event loop for copytrade. Monitors wallets, copies BTC 5-min trades.
- `copytrade.py` — Copytrade logic. Polls data-api.polymarket.com for wallet activity, filters BTC 5-min trades.
- `polymarket.py` — API client. Read-only calls to Gamma (market discovery) and CLOB (orderbook/prices). Live trading uses `py-clob-client` SDK.
- `strategy.py` — Streak strategy logic. Streak detection, signal generation, Kelly criterion bet sizing. No I/O.
- `trader.py` — Execution layer. Paper trader (logs only) and live trader (submits orders). Manages persistent state (trades.json).
- `config.py` — Reads `.env`, exposes typed config.
- `backtest.py` — Offline backtest against historical JSON data.

## Key Decisions
- **Trigger=4** is the sweet spot: good balance of trade frequency and win rate
- Entry at ~50¢ (before window opens) maximizes edge
- Quarter-Kelly sizing for conservative bankroll management
- Graceful degradation: if a market fetch fails, skip and continue

## Data
- Polymarket BTC 5-min markets: slug pattern `btc-updown-5m-{unix_ts}` every 300s
- Gamma API for market discovery (no auth)
- CLOB API for orderbook/prices (no auth for reads)
- Trading requires Polygon wallet + EIP-712 derived API creds

## Dev
```bash
uv sync                          # install deps
uv run python bot.py --paper     # paper trade (streak strategy)
uv run python backtest.py        # backtest streak strategy

# Copytrade
uv run python copybot.py --paper --wallets 0x1d0034134e339a309700ff2d34e99fa2d48b0313
```

## Copytrade Config (.env)
```
COPY_WALLETS=0x1d0034134e339a309700ff2d34e99fa2d48b0313,0xanotherWallet
COPY_POLL_INTERVAL=5
```

## Caveats
- Only ~2 days of historical data (markets launched Feb 12 2026)
- Streak reversal is a known mean-reversion pattern but may not persist
- Polymarket fees (~5%) eat into margins
- Thin liquidity on some windows
