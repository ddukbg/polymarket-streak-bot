#!/usr/bin/env python3
"""
Trade History Viewer

View, export, and analyze your trading history.

Usage:
    python history.py                  # Show last 20 trades
    python history.py --all            # Show all trades
    python history.py --limit 50       # Show last 50 trades
    python history.py --stats          # Show statistics only
    python history.py --export json    # Export to trade_history.json
    python history.py --export csv     # Export to trade_history.csv
    python history.py --backfill       # Backfill settlement data for unsettled trades
    python history.py --backfill --watch  # Keep retrying until all settled (every 5 min)
    python history.py --compact        # Migrate history: remove dead fields, backfill final_price
"""

import argparse
import json
import os
import time
from datetime import datetime
from config import TIMEZONE_NAME
from trader import Trade, TradingState


# Fields that were declared but never populated (dead code)
DEAD_CODE_FIELDS = {
    "trader_recent_trades",
    "trader_recent_wins",
    "trader_win_rate",
    "actual_price_impact_pct",
    "gas_price_gwei",
    "tx_status",
}

# Fields that are only valid during pending state
TRANSIENT_FIELDS = {"current_price", "unrealized_pnl", "implied_outcome"}


def compact_history():
    """Migrate trade history: remove dead fields, transient fields, and backfill final_price."""
    history_file = "trade_history_full.json"

    if not os.path.exists(history_file):
        print(f"[compact] No history file found: {history_file}")
        return

    # Load history
    try:
        with open(history_file) as f:
            history = json.load(f)
    except Exception as e:
        print(f"[compact] Error loading history: {e}")
        return

    if not history:
        print("[compact] History file is empty")
        return

    print(f"[compact] Processing {len(history)} trades...")

    dead_removed = 0
    transient_removed = 0
    final_price_backfilled = 0

    for entry in history:
        # Remove dead code fields
        for field in DEAD_CODE_FIELDS:
            if field in entry:
                del entry[field]
                dead_removed += 1

        # Remove transient fields from settled trades
        if entry.get("outcome") is not None:
            for field in TRANSIENT_FIELDS:
                if field in entry:
                    del entry[field]
                    transient_removed += 1

        # Backfill final_price for settled trades where won is known
        if entry.get("won") is not None and entry.get("final_price") is None:
            entry["final_price"] = 1.0 if entry["won"] else 0.0
            final_price_backfilled += 1

    # Save compacted history
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)

    print(f"[compact] Done!")
    print(f"  - Removed {dead_removed} dead code field instances")
    print(f"  - Removed {transient_removed} transient field instances")
    print(f"  - Backfilled final_price for {final_price_backfilled} trades")
    print(f"  - Saved to {history_file}")


def main():
    parser = argparse.ArgumentParser(description="Trade History Viewer")
    parser.add_argument("--all", action="store_true", help="Show all trades")
    parser.add_argument("--limit", type=int, default=20, help="Number of trades to show")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    parser.add_argument("--export", choices=["json", "csv"], help="Export history to file")
    parser.add_argument("--output", type=str, help="Output file path for export")
    parser.add_argument("--recent", action="store_true", help="Only show recent trades (from working state)")
    parser.add_argument("--backfill", action="store_true", help="Backfill settlement data for unsettled trades")
    parser.add_argument("--watch", action="store_true", help="Keep retrying backfill every 5 min until all settled")
    parser.add_argument("--interval", type=int, default=300, help="Retry interval in seconds (default: 300)")
    parser.add_argument("--compact", action="store_true", help="Migrate history: remove dead/transient fields, backfill final_price")
    args = parser.parse_args()

    # Backfill settlement data if requested
    if args.backfill:
        print("Backfilling settlement data for unsettled trades...")
        total_updated = 0

        while True:
            updated, remaining = TradingState.backfill_settlements()
            total_updated += updated

            if remaining == 0:
                # All trades settled
                if total_updated > 0:
                    print(f"\nDone! Updated {total_updated} trades. Run 'python history.py --stats' to see results.")
                else:
                    print("\nNo trades needed updating.")
                break

            if not args.watch:
                # Not watching, just report and exit
                print(f"\n{remaining} trade(s) still pending settlement.")
                print(f"Run with --watch to keep retrying every {args.interval // 60} minutes.")
                break

            # Watch mode: wait and retry
            next_check = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{next_check}] {remaining} trade(s) still pending. Retrying in {args.interval // 60} min...")
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped watching.")
                break

        return

    # Compact migration
    if args.compact:
        compact_history()
        return

    # Load full history by default, or recent only if requested
    if args.recent:
        state = TradingState.load()
        print("(Showing recent trades from working state)")
    else:
        state = TradingState.load_full_history()
        print(f"(Loaded full history: {len(state.trades)} trades)")

    if not state.trades:
        print("No trade history found. Run the bot first to generate trades.")
        return

    # Export if requested
    if args.export:
        if args.export == "json":
            filepath = args.output or "trade_history.json"
            state.export_history_json(filepath)
        else:
            filepath = args.output or "trade_history.csv"
            state.export_history_csv(filepath)
        return

    # Show statistics
    if args.stats:
        stats = state.get_statistics()
        print("\n" + "=" * 60)
        print(f"TRADING STATISTICS ({TIMEZONE_NAME})")
        print("=" * 60)
        print(f"\nTrades:")
        print(f"  Total:    {stats['total_trades']}")
        print(f"  Settled:  {stats['settled_trades']}")
        print(f"  Pending:  {stats['pending_trades']}")
        print(f"  Wins:     {stats['wins']}")
        print(f"  Losses:   {stats['losses']}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")

        print(f"\nProfit & Loss:")
        print(f"  Realized P&L:    ${stats['realized_pnl']:+.2f}")
        if stats['pending_trades'] > 0:
            print(f"  Unrealized P&L:  ${stats['unrealized_pnl']:+.2f} ({stats['pending_trades']} pending)")
            print(f"  Total P&L (est): ${stats['total_pnl']:+.2f}")
        print(f"  Gross Profit:    ${stats['total_gross_profit']:+.2f}")
        print(f"  Fees Paid:       ${stats['total_fees_paid']:.2f}")
        print(f"  Avg Win:         ${stats['avg_win']:+.2f}")
        print(f"  Avg Loss:        ${stats['avg_loss']:+.2f}")
        print(f"  Largest Win:     ${stats['largest_win']:+.2f}")
        print(f"  Largest Loss:    ${stats['largest_loss']:+.2f}")

        print(f"\nCosts (Averages):")
        print(f"  Fee:             {stats['avg_fee_pct']:.2f}%")
        print(f"  Slippage:        {stats['avg_slippage_pct']:.2f}%")
        print(f"  Delay Impact:    {stats['avg_delay_impact_pct']:.2f}%")

        print(f"\nBankroll: ${stats['bankroll']:.2f}")
        print("=" * 60 + "\n")
        return

    # Show trade history
    limit = len(state.trades) if args.all else args.limit
    state.print_history(limit=limit)


if __name__ == "__main__":
    main()
