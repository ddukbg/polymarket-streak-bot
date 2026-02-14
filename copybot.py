#!/usr/bin/env python3
"""
Polymarket BTC 5-Min Copytrade Bot

Monitors specific wallets and copies their BTC 5-min trades.
"""

import argparse
import signal
import sys
import time
from datetime import datetime, timezone

from config import Config
from copytrade import CopytradeMonitor, CopySignal
from polymarket import PolymarketClient
from trader import LiveTrader, PaperTrader, TradingState

running = True


def handle_signal(sig, frame):
    global running
    print("\n[copybot] Shutting down gracefully...")
    running = False


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def main():
    global running
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    parser = argparse.ArgumentParser(description="Polymarket BTC Copytrade Bot")
    parser.add_argument("--paper", action="store_true", help="Force paper trading")
    parser.add_argument("--amount", type=float, help="Bet amount in USD")
    parser.add_argument("--bankroll", type=float, help="Starting bankroll")
    parser.add_argument(
        "--wallets", type=str, help="Comma-separated wallet addresses to copy"
    )
    args = parser.parse_args()

    paper_mode = args.paper or Config.PAPER_TRADE
    bet_amount = args.amount or Config.BET_AMOUNT

    # Parse wallets
    wallets = Config.COPY_WALLETS
    if args.wallets:
        wallets = [w.strip() for w in args.wallets.split(",") if w.strip()]

    if not wallets:
        print("[copybot] No wallets to copy. Set COPY_WALLETS in .env or use --wallets")
        sys.exit(1)

    # Init
    monitor = CopytradeMonitor(wallets)
    client = PolymarketClient()
    state = TradingState.load()
    if args.bankroll:
        state.bankroll = args.bankroll

    if paper_mode:
        trader = PaperTrader()
        log("Paper trading mode")
    else:
        trader = LiveTrader()
        log("LIVE trading mode")

    log(f"Copying {len(wallets)} wallet(s):")
    for w in wallets:
        log(f"  - {w}")
    log(f"Bet amount: ${bet_amount:.2f}")
    log(f"Bankroll: ${state.bankroll:.2f}")
    log(f"Poll interval: {Config.COPY_POLL_INTERVAL}s")
    log("")

    # Track what markets we've already copied
    copied_markets: set[tuple[str, int]] = set()  # (wallet, market_ts)
    # Track pending trades
    pending: list = []

    # Show recent trades from copied wallets
    log("Recent BTC 5-min trades from copied wallets:")
    for wallet in wallets:
        recent = monitor.get_latest_btc_5m_trades(wallet, limit=3)
        for sig in recent:
            log(f"  {sig.trader_name}: {sig.side} {sig.direction} @ {sig.price:.2f} (${sig.usdc_amount:.2f})")
    log("")

    while running:
        try:
            now = int(time.time())

            # === SETTLE PENDING TRADES ===
            for trade in list(pending):
                market = client.get_market(trade.timestamp)
                if market and market.closed and market.outcome:
                    state.settle_trade(trade, market.outcome)
                    emoji = "+" if trade.pnl > 0 else "-"
                    log(
                        f"[{emoji}] Settled: {trade.direction} @ {trade.market_slug} "
                        f"-> {market.outcome} | PnL: ${trade.pnl:+.2f} "
                        f"| Bankroll: ${state.bankroll:.2f}"
                    )
                    pending.remove(trade)
                    state.save()

            # === CHECK IF WE CAN TRADE ===
            can_trade, reason = state.can_trade()
            if not can_trade:
                log(f"Cannot trade: {reason}")
                time.sleep(30)
                continue

            # === POLL FOR NEW SIGNALS ===
            signals = monitor.poll()

            for sig in signals:
                # Skip if already copied this market from this wallet
                key = (sig.wallet, sig.market_ts)
                if key in copied_markets:
                    continue

                # Skip SELL signals (we only copy buys for now)
                if sig.side != "BUY":
                    log(f"[skip] {sig.trader_name} SELL {sig.direction} (only copying BUYs)")
                    copied_markets.add(key)
                    continue

                # Check if market is still tradeable
                market = client.get_market(sig.market_ts)
                if not market:
                    log(f"[skip] Market not found for ts={sig.market_ts}")
                    copied_markets.add(key)
                    continue

                if market.closed:
                    log(f"[skip] Market already closed: {market.slug}")
                    copied_markets.add(key)
                    continue

                if not market.accepting_orders:
                    log(f"[skip] Market not accepting orders: {market.slug}")
                    copied_markets.add(key)
                    continue

                # === COPY THE TRADE ===
                direction = sig.direction.lower()  # "up" or "down"
                amount = min(bet_amount, state.bankroll * 0.1)
                amount = max(Config.MIN_BET, amount)

                # Calculate copy delay (milliseconds since trader's trade)
                now_ms = int(time.time() * 1000)
                trader_ts_ms = sig.trade_ts * 1000  # actual trade timestamp
                copy_delay_ms = now_ms - trader_ts_ms

                # Get current market price for our entry
                current_price = market.up_price if direction == "up" else market.down_price

                log(
                    f"[COPY] {sig.trader_name} -> {sig.side} {sig.direction} "
                    f"@ {sig.price:.2f} | Copying with ${amount:.2f} | Delay: {copy_delay_ms}ms"
                )

                trade = trader.place_bet(
                    market=market,
                    direction=direction,
                    amount=amount,
                    confidence=0.6,  # default confidence for copied trades
                    streak_length=0,
                    # Copytrade analysis fields
                    strategy="copytrade",
                    copied_from=sig.wallet,
                    trader_name=sig.trader_name,
                    trader_direction=sig.direction,
                    trader_amount=sig.usdc_amount,
                    trader_price=sig.price,
                    trader_timestamp=sig.trade_ts,  # when trader placed the trade
                    copy_delay_ms=copy_delay_ms,
                )
                state.record_trade(trade)
                copied_markets.add(key)
                pending.append(trade)
                state.save()

                log(
                    f"Daily: {state.daily_bets} bets, PnL: ${state.daily_pnl:+.2f} "
                    f"| Bankroll: ${state.bankroll:.2f} | Pending: {len(pending)}"
                )

            # === HEARTBEAT ===
            if now % 60 < Config.COPY_POLL_INTERVAL:
                log(f"Watching... Pending: {len(pending)} | Copied: {len(copied_markets)}")

            time.sleep(Config.COPY_POLL_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(10)

    # Save state on exit
    state.save()
    log(f"State saved. Bankroll: ${state.bankroll:.2f}")
    log(f"Session: {state.daily_bets} bets, PnL: ${state.daily_pnl:+.2f}")


if __name__ == "__main__":
    main()
