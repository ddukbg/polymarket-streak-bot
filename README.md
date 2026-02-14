# Polymarket BTC 5-Min Copytrade Bot

A bot that copies BTC 5-minute up/down trades from profitable Polymarket traders.

## Strategy

Polymarket offers binary markets every 5 minutes: will BTC go up or down? Instead of predicting yourself, this bot monitors successful traders and copies their trades in real-time.

**Why it works:** Some traders have consistent edge in these markets. By copying their entries, you can piggyback on their analysis without doing the work yourself.

| Approach | Description |
|----------|-------------|
| Wallet Monitoring | Poll trader activity via Polymarket data API |
| BTC 5-min Only | Filter for `btc-updown-5m-*` markets only |
| Real-time Copy | Detect new trades within 5 seconds |

> **Disclaimer:** This is experimental. Copied traders can lose. Past performance does not equal future results. Use at your own risk. Start with paper trading.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/0xrsydn/polymarket-streak-bot.git
cd polymarket-streak-bot
uv sync

# Paper trade (no real money)
cp .env.example .env
uv run python copybot.py --paper --wallets 0x1d0034134e339a309700ff2d34e99fa2d48b0313

# Or use the original streak reversal strategy
uv run python bot.py --paper
```

## Finding Traders to Copy

1. Go to [Polymarket Leaderboard](https://polymarket.com/leaderboard)
2. Filter by "Crypto" category
3. Find traders with consistent P&L
4. Copy their wallet address from their profile URL

Example profitable BTC trader:
```
https://polymarket.com/@0x1d0034134e339a309700ff2d34e99fa2d48b031
Wallet: 0x1d0034134e339a309700ff2d34e99fa2d48b0313
```

## Live Trading Setup

1. Get a Polygon wallet with USDC
2. Set your private key in `.env`:
   ```
   PRIVATE_KEY=0x_your_key
   PAPER_TRADE=false
   COPY_WALLETS=0x1d0034134e339a309700ff2d34e99fa2d48b0313
   ```
3. Run: `uv run python copybot.py`

## Configuration

Edit `.env` to tune:

| Variable | Default | Description |
|----------|---------|-------------|
| `COPY_WALLETS` | (empty) | Comma-separated wallet addresses to copy |
| `COPY_POLL_INTERVAL` | 5 | Seconds between activity checks |
| `BET_AMOUNT` | 5 | USD per copied trade |
| `MIN_BET` | 1 | Minimum bet size |
| `MAX_DAILY_BETS` | 50 | Stop after N bets per day |
| `MAX_DAILY_LOSS` | 50 | Stop if daily loss exceeds this |
| `PAPER_TRADE` | true | Set false for live trading |

## Architecture

```
├── copybot.py      — Main loop: monitors wallets, copies BTC 5-min trades
├── copytrade.py    — Wallet activity monitoring + signal generation
├── bot.py          — Original streak reversal strategy
├── polymarket.py   — Polymarket API client (Gamma + CLOB)
├── strategy.py     — Streak detection + Kelly criterion sizing
├── trader.py       — Paper & live order execution + state management
├── config.py       — Settings from .env
└── .env.example    — Template config
```

## How It Works

1. **Monitor** — Polls `/activity` endpoint for each tracked wallet
2. **Filter** — Only processes BTC 5-min trades (`btc-updown-5m-*`)
3. **Detect** — Compares timestamps to find new trades
4. **Copy** — Places same direction bet (Up/Down) on same market
5. **Settle** — Tracks outcome when market resolves, updates bankroll

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `data-api.polymarket.com/activity?user={wallet}` | Get trader's recent trades |
| `gamma-api.polymarket.com/markets/slug/{slug}` | Get market details + outcome |
| `clob.polymarket.com` | Place orders (live trading) |

## Risk Management

With a small bankroll ($10-50), use conservative sizing:

| Bankroll | Bet Size | Risk % |
|----------|----------|--------|
| $10 | $1 | 10% |
| $50 | $2-5 | 4-10% |
| $100+ | $5-10 | 5-10% |

The bot enforces:
- `MIN_BET` floor (default $1)
- Max 10% of bankroll per trade
- Daily loss limit stops trading

## License

MIT
