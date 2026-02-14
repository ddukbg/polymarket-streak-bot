# Polymarket BTC 5-Min Trading Bot

Two strategies for trading BTC 5-minute up/down markets on Polymarket:

1. **Copytrade** — Copy trades from profitable wallets in real-time
2. **Streak Reversal** — Bet against consecutive streaks (mean reversion)

> **Disclaimer:** This is experimental. Past performance does not guarantee future results. Use at your own risk. Start with paper trading.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/0xrsydn/polymarket-streak-bot.git
cd polymarket-streak-bot
uv sync

# Copy .env and configure
cp .env.example .env

# Copytrade strategy (copy a wallet)
uv run python copybot.py --paper --wallets 0x1d0034134e339a309700ff2d34e99fa2d48b0313

# Streak reversal strategy
uv run python bot.py --paper --trigger 4

# View trade history
uv run python history.py --stats
```

## Strategies

### Copytrade (`copybot.py`)

Monitors wallet addresses and copies their BTC 5-min trades within seconds.

```bash
# Copy single wallet
uv run python copybot.py --paper --wallets 0x1d00...

# Copy multiple wallets
uv run python copybot.py --paper --wallets 0x1d00...,0x5678...

# Custom settings
uv run python copybot.py --paper --amount 10 --poll 3 --wallets 0x1d00...
```

**Finding wallets to copy:**
1. Go to [Polymarket Leaderboard](https://polymarket.com/leaderboard)
2. Filter by "Crypto" category
3. Find traders with consistent BTC 5-min P&L
4. Copy wallet address from profile URL

### Streak Reversal (`bot.py`)

Bets against streaks of consecutive outcomes. After N ups in a row, bet down (and vice versa).

```bash
# Trigger on 4-streak (default)
uv run python bot.py --paper

# Trigger on 5-streak (more conservative)
uv run python bot.py --paper --trigger 5

# Custom bet amount
uv run python bot.py --paper --amount 10
```

## Realistic Paper Trading

Paper trading simulates real costs from Polymarket CLOB API:

| Cost | Source | Example |
|------|--------|---------|
| **Fees** | `clob.polymarket.com/fee-rate` | ~2.5% at 50¢ price |
| **Spread** | Real bid-ask from orderbook | ~1¢ typical |
| **Slippage** | Orderbook walking | Depends on size |
| **Copy Delay** | Time since trader's entry | ~0.3%/second |

All costs are deducted from your simulated bankroll, so paper P&L reflects realistic expectations.

## Trade History

Full trade history is recorded with fees, slippage, timestamps, and outcomes.

```bash
# View statistics
uv run python history.py --stats

# Show last 50 trades
uv run python history.py --limit 50

# Show all trades
uv run python history.py --all

# Export to CSV/JSON
uv run python history.py --export csv
uv run python history.py --export json
```

## Configuration

Create `.env` from template:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER_TRADE` | `true` | Set `false` for live trading |
| `BET_AMOUNT` | `5` | USD per trade |
| `MIN_BET` | `1` | Minimum bet size |
| `MAX_DAILY_BETS` | `50` | Stop after N bets/day |
| `MAX_DAILY_LOSS` | `50` | Stop if daily loss exceeds |
| `STREAK_TRIGGER` | `4` | Streak length to trigger (bot.py) |
| `ENTRY_SECONDS_BEFORE` | `30` | Seconds before window to enter |
| `COPY_WALLETS` | (empty) | Comma-separated wallets to copy |
| `COPY_POLL_INTERVAL` | `5` | Seconds between activity checks |
| `TIMEZONE` | `Asia/Jakarta` | Display timezone |
| `PRIVATE_KEY` | (empty) | Polygon wallet key (live only) |

## Live Trading

1. Get a Polygon wallet with USDC
2. Configure `.env`:
   ```
   PRIVATE_KEY=0x_your_private_key
   PAPER_TRADE=false
   COPY_WALLETS=0x1d0034134e339a309700ff2d34e99fa2d48b0313
   ```
3. Run:
   ```bash
   uv run python copybot.py --live
   # or
   uv run python bot.py --live
   ```

## CLI Reference

All bots have comprehensive `--help`:

```bash
uv run python copybot.py --help
uv run python bot.py --help
uv run python history.py --help
```

**Common flags:**

| Flag | Description |
|------|-------------|
| `--paper` | Force paper trading mode |
| `--live` | Force live trading mode |
| `--amount USD` | Bet amount per trade |
| `--bankroll USD` | Override starting bankroll |
| `--max-bets N` | Daily bet limit |
| `--max-loss USD` | Daily loss limit |

**Copybot-specific:**

| Flag | Description |
|------|-------------|
| `--wallets ADDR` | Comma-separated wallet addresses |
| `--poll SEC` | Poll interval in seconds |

**Bot-specific:**

| Flag | Description |
|------|-------------|
| `--trigger N` | Streak length to trigger bet |

## Architecture

```
├── copybot.py      — Copytrade main loop
├── copytrade.py    — Wallet monitoring + signal generation
├── bot.py          — Streak reversal main loop
├── strategy.py     — Streak detection + Kelly sizing
├── polymarket.py   — API client (Gamma + CLOB)
├── trader.py       — Paper/live execution + state
├── history.py      — Trade history CLI
├── config.py       — Settings from .env
└── backtest.py     — Offline backtesting
```

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `data-api.polymarket.com/activity` | Wallet trade activity |
| `gamma-api.polymarket.com/markets` | Market discovery + outcomes |
| `clob.polymarket.com/book` | Orderbook + prices |
| `clob.polymarket.com/fee-rate` | Fee rates |

## Risk Management

The bot enforces:
- Minimum bet size ($5 on Polymarket)
- Max 10% of bankroll per trade
- Daily loss limit stops trading
- Daily bet count limit

**Recommended sizing:**

| Bankroll | Bet Size | Risk % |
|----------|----------|--------|
| $50 | $2-5 | 4-10% |
| $100 | $5-10 | 5-10% |
| $500+ | $10-25 | 2-5% |

## License

MIT
