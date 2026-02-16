# Polymarket BTC 5-Min Trading Bot

> 🤖 Built by [Dexter](https://github.com/0xrsydn) — a superintelligent AI coding agent running on [OpenClaw](https://github.com/openclaw/openclaw). Yes, an AI wrote this entire trading bot. No, it doesn't have a Polymarket account (yet).

Automated trading bot for Polymarket's BTC 5-minute up/down prediction markets. Supports multiple strategies — from statistical mean reversion to copying profitable wallets in real-time.

> ⚠️ **Work in Progress.** This project is under active development. Expect breaking changes, rough edges, and the occasional existential crisis from its AI developer. Use at your own risk. Start with paper trading.

## Strategies

### 1. Streak Reversal (Mean Reversion)

Detects streaks of consecutive same outcomes (e.g., 4x "Up" in a row) and bets on reversal.

**Why it works:** After 4+ consecutive same outcomes, historical data shows ~67-73% reversal rate while the market prices both sides at ~50/50.

| Streak Length | Reversal Rate | Sample Size |
|--------------|---------------|-------------|
| 4 | 66.7% | 51 |
| 5 | 82.4% | 17 |

```bash
# Paper trade
uv run python bot.py --paper

# Backtest
uv run python scripts/backtest.py
```

### 2. Copytrade

Monitors profitable wallets on-chain and copies their BTC 5-min trades with ~1.5-2s latency. Uses WebSocket for orderbook data with REST fallback.

```bash
# Copy a wallet (paper mode)
uv run python copybot_v2.py --paper --wallets 0x1d0034134e339a309700ff2d34e99fa2d48b0313

# Multiple wallets
uv run python copybot_v2.py --paper --wallets 0x1d00...,0x5678...
```

**Finding wallets to copy:**
1. Go to [Polymarket Leaderboard](https://polymarket.com/leaderboard)
2. Filter by "Crypto" category
3. Find traders with consistent BTC 5-min P&L
4. Grab wallet address from their profile

### 3. Selective Copytrade

Same as copytrade but with quality filters — skips trades with bad execution conditions (high delay, wide spread, low depth, excessive price movement).

```bash
# Enable selective mode
uv run python copybot_v2.py --paper --selective --wallets 0x1d00...
```

## Quick Start

```bash
git clone https://github.com/0xrsydn/polymarket-streak-bot.git
cd polymarket-streak-bot
uv sync

cp .env.example .env
# Edit .env with your settings

# Pick your strategy:
uv run python bot.py --paper              # Streak reversal
uv run python copybot_v2.py --paper       # Copytrade
```

## Live Trading

1. Get a Polygon wallet funded with USDC
2. Configure `.env`:
   ```
   PRIVATE_KEY=0x_your_key
   PAPER_TRADE=false
   ```
3. Run your chosen strategy without `--paper`

## Configuration

All settings live in `.env` (see `.env.example` for the full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER_TRADE` | `true` | Paper mode (no real money) |
| `BET_AMOUNT` | `5` | USD per trade |
| `MAX_DAILY_BETS` | `50` | Daily bet limit |
| `MAX_DAILY_LOSS` | `50` | Daily loss limit |
| `STREAK_TRIGGER` | `4` | Streak length before betting reversal |
| `COPY_WALLETS` | — | Wallets to copy (comma-separated) |
| `USE_WEBSOCKET` | `true` | WebSocket for orderbook data |

## Project Structure

```
├── bot.py                         # Streak reversal entrypoint
├── copybot_v2.py                  # Copytrade v2 entrypoint
├── src/
│   ├── config.py                  # Settings from .env
│   ├── strategies/
│   │   ├── streak.py              # Mean reversion logic
│   │   ├── copytrade.py           # Wallet monitoring + signals
│   │   ├── copytrade_ws.py        # WebSocket copytrade monitor
│   │   └── selective_filter.py    # Trade quality filter
│   ├── core/
│   │   ├── polymarket.py          # REST API client (Gamma + CLOB)
│   │   ├── polymarket_ws.py       # WebSocket client (orderbook)
│   │   ├── blockchain.py          # Polygonscan API
│   │   └── trader.py              # Paper & live execution
│   └── infra/
│       ├── resilience.py          # Circuit breaker + rate limiter
│       └── logging_config.py      # Structured logging
├── scripts/
│   ├── backtest.py                # Backtest against historical data
│   └── history.py                 # Trade history CLI + analysis
├── .env.example
├── pyproject.toml
└── flake.nix                      # Nix devshell
```

## Trade History & Analysis

```bash
uv run python scripts/history.py --stats      # View statistics
uv run python scripts/history.py --limit 50   # Last 50 trades
uv run python scripts/history.py --export csv  # Export to CSV
```

## How It Works

**Streak Reversal:**
1. Fetches recent resolved BTC 5-min outcomes
2. Detects streaks (N consecutive up/down)
3. Bets on reversal ~30s before next window opens (50¢ odds)
4. Settles and tracks bankroll

**Copytrade:**
1. Polls target wallet activity every 1.5s
2. Detects new BTC 5-min positions
3. Places matching market order (FOK for guaranteed fill)
4. Tracks execution quality (delay, spread, slippage)

**Selective Filter** adds pre-trade checks:
- Copy delay < threshold
- Fill price within acceptable range
- Spread, depth, and volatility checks

## Disclaimer

This is experimental software built by an AI agent for research and educational purposes. Prediction markets involve real financial risk. Past performance does not guarantee future results. The developers (human and artificial) are not responsible for any losses.

## License

MIT
