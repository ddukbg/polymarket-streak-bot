"""Trading execution — paper and live modes."""

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from config import Config, LOCAL_TZ, TIMEZONE_NAME
from polymarket import Market


@dataclass
class Trade:
    """Record of a trade (paper or live) with full history."""

    # === CORE FIELDS ===
    timestamp: int  # market timestamp (unix seconds)
    market_slug: str  # e.g., "btc-updown-5m-1771051500"
    direction: str  # "up" or "down" - your bet direction
    amount: float  # your bet size in USD (after any partial fill)
    entry_price: float  # displayed market price when you decided to bet
    streak_length: int  # for streak strategy
    confidence: float  # signal confidence (0-1)
    paper: bool  # True = simulation, False = live trade

    # === RESOLUTION FIELDS ===
    outcome: str | None = None  # "up" or "down" after market closes
    pnl: float = 0.0  # net profit/loss after fees
    order_id: str | None = None  # order ID from exchange (live only)
    settled_at: int | None = None  # when trade was settled (unix ms)
    won: bool | None = None  # True if direction == outcome

    # === SETTLEMENT BREAKDOWN ===
    shares_bought: float = 0.0  # number of shares purchased
    gross_payout: float = 0.0  # total payout before fees ($1/share if won)
    gross_profit: float = 0.0  # gross_payout - amount (before fees)
    fee_amount: float = 0.0  # actual fee deducted in USD
    net_profit: float = 0.0  # gross_profit - fee_amount

    # === COPYTRADE FIELDS ===
    copied_from: str | None = None  # trader wallet address
    trader_name: str | None = None  # trader pseudonym
    trader_direction: str | None = None  # what trader bet on
    trader_amount: float | None = None  # how much trader bet (USD)
    trader_price: float | None = None  # price trader got
    trader_timestamp: int | None = None  # when trader placed bet (unix ms)
    executed_at: int | None = None  # when you placed your bet (unix ms)
    copy_delay_ms: int | None = None  # delay between trader and your bet
    market_price_at_copy: float | None = None  # market price when you copied

    # === STRATEGY ===
    strategy: str = "streak"  # "streak" or "copytrade"

    # === REALISTIC SIMULATION FIELDS ===
    fee_rate_bps: int = 0  # base fee in basis points (e.g., 1000)
    fee_pct: float = 0.0  # actual fee percentage at execution price
    spread: float = 0.0  # bid-ask spread at entry (in price units)
    slippage_pct: float = 0.0  # slippage from walking the book (%)
    execution_price: float = 0.0  # actual fill price after slippage
    fill_pct: float = 100.0  # percentage of order filled
    delay_impact_pct: float = 0.0  # price impact from copy delay (%)
    requested_amount: float = 0.0  # original requested amount before partial fill

    # === PRICE MOVEMENT ===
    price_at_signal: float = 0.0  # price when signal was generated
    price_at_execution: float = 0.0  # price when order was submitted
    price_movement_pct: float = 0.0  # % change from signal to execution

    # === MARKET CONTEXT ===
    market_volume: float = 0.0  # market volume at time of trade
    best_bid: float = 0.0  # best bid price at execution
    best_ask: float = 0.0  # best ask price at execution

    def to_history_dict(self) -> dict:
        """Convert trade to a detailed history dictionary."""
        exec_time = datetime.fromtimestamp(
            self.executed_at / 1000, tz=LOCAL_TZ
        ).strftime(f"%Y-%m-%d %H:%M:%S {TIMEZONE_NAME}") if self.executed_at else "N/A"

        settle_time = datetime.fromtimestamp(
            self.settled_at / 1000, tz=LOCAL_TZ
        ).strftime(f"%Y-%m-%d %H:%M:%S {TIMEZONE_NAME}") if self.settled_at else "Pending"

        return {
            # Identification
            "market": self.market_slug,
            "strategy": self.strategy,
            "mode": "PAPER" if self.paper else "LIVE",

            # Timing
            "executed_at": exec_time,
            "settled_at": settle_time,
            "copy_delay_ms": self.copy_delay_ms,

            # Position
            "direction": self.direction.upper(),
            "requested_amount": round(self.requested_amount, 2),
            "filled_amount": round(self.amount, 2),
            "fill_pct": round(self.fill_pct, 1),

            # Prices
            "price_at_signal": round(self.price_at_signal, 4),
            "entry_price": round(self.entry_price, 4),
            "execution_price": round(self.execution_price, 4),
            "price_movement_pct": round(self.price_movement_pct, 2),

            # Costs
            "spread_cents": round(self.spread * 100, 1),
            "slippage_pct": round(self.slippage_pct, 2),
            "delay_impact_pct": round(self.delay_impact_pct, 2),
            "fee_pct": round(self.fee_pct * 100, 2),

            # Shares
            "shares_bought": round(self.shares_bought, 2),

            # Result
            "outcome": self.outcome.upper() if self.outcome else "PENDING",
            "won": self.won,
            "gross_profit": round(self.gross_profit, 2),
            "fee_amount": round(self.fee_amount, 2),
            "net_pnl": round(self.pnl, 2),

            # Copytrade specific
            "copied_from": self.trader_name if self.strategy == "copytrade" else None,
            "trader_price": round(self.trader_price, 4) if self.trader_price else None,
            "trader_amount": round(self.trader_amount, 2) if self.trader_amount else None,
        }

    def summary(self) -> str:
        """Return a one-line summary of the trade."""
        status = "✓ WON" if self.won else "✗ LOST" if self.won is False else "⏳ PENDING"
        return (
            f"{self.direction.upper()} ${self.amount:.2f} @ {self.execution_price:.3f} "
            f"| {status} | PnL: ${self.pnl:+.2f}"
        )


@dataclass
class TradingState:
    """Persistent state across bot restarts."""

    trades: list[Trade] = field(default_factory=list)
    daily_bets: int = 0
    daily_pnl: float = 0.0
    last_reset_date: str = ""
    bankroll: float = 100.0  # starting bankroll

    # Track which trades have been saved to full history
    _saved_trade_ids: set = field(default_factory=set)
    _last_saved_trade_id: str = ""

    def reset_daily_if_needed(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            self.daily_bets = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today

    def can_trade(self) -> tuple[bool, str]:
        self.reset_daily_if_needed()
        if self.daily_bets >= Config.MAX_DAILY_BETS:
            return False, f"Max daily bets reached ({Config.MAX_DAILY_BETS})"
        if self.daily_pnl <= -Config.MAX_DAILY_LOSS:
            return False, f"Max daily loss reached (${Config.MAX_DAILY_LOSS})"
        if self.bankroll < Config.BET_AMOUNT:
            return False, f"Bankroll too low (${self.bankroll:.2f})"
        return True, "OK"

    def record_trade(self, trade: Trade):
        self.trades.append(trade)
        self.daily_bets += 1

    def settle_trade(self, trade: Trade, outcome: str):
        """Settle a trade and calculate all P&L details."""
        trade.outcome = outcome
        trade.won = trade.direction == outcome
        trade.settled_at = int(time.time() * 1000)

        # Use execution price (includes slippage) if available, else entry_price
        exec_price = trade.execution_price if trade.execution_price > 0 else trade.entry_price

        # Calculate shares bought
        trade.shares_bought = trade.amount / exec_price if exec_price > 0 else 0

        if trade.won:
            # Win: receive $1 per share
            trade.gross_payout = trade.shares_bought  # $1 per share on win
            trade.gross_profit = trade.gross_payout - trade.amount

            # Apply fee to the profit (fee is on proceeds, not principal)
            fee_pct = trade.fee_pct if trade.fee_pct > 0 else 0.0
            trade.fee_amount = trade.gross_profit * fee_pct if trade.gross_profit > 0 else 0.0

            trade.net_profit = trade.gross_profit - trade.fee_amount
            trade.pnl = trade.net_profit
        else:
            # Loss: lose the entire amount
            trade.gross_payout = 0.0
            trade.gross_profit = -trade.amount
            trade.fee_amount = 0.0  # No fee on losses
            trade.net_profit = -trade.amount
            trade.pnl = -trade.amount

        self.daily_pnl += trade.pnl
        self.bankroll += trade.pnl

    def save(self):
        """Save current state and append new trades to full history."""
        # Save working state (recent trades for fast loading)
        data = {
            "trades": [asdict(t) for t in self.trades[-100:]],  # keep last 100 for working state
            "daily_bets": self.daily_bets,
            "daily_pnl": self.daily_pnl,
            "last_reset_date": self.last_reset_date,
            "bankroll": self.bankroll,
            "last_trade_id": self._last_saved_trade_id,
        }
        with open(Config.TRADES_FILE, "w") as f:
            json.dump(data, f, indent=2)

        # Append new trades to full history file (never truncated)
        self._append_to_full_history()

    def _append_to_full_history(self):
        """Append only new trades to the full history file."""
        history_file = "trade_history_full.json"

        # Find trades that haven't been saved yet
        new_trades = []
        for t in self.trades:
            trade_id = f"{t.timestamp}_{t.executed_at}_{t.direction}"
            if trade_id not in self._saved_trade_ids:
                new_trades.append(t)
                self._saved_trade_ids.add(trade_id)
                self._last_saved_trade_id = trade_id

        if not new_trades:
            return

        # Load existing history or create new
        existing = []
        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, Exception):
                existing = []

        # Append new trades
        for t in new_trades:
            existing.append(asdict(t))

        # Save full history
        with open(history_file, "w") as f:
            json.dump(existing, f, indent=2)

        if new_trades:
            print(f"[history] Appended {len(new_trades)} trade(s) to {history_file} (total: {len(existing)})")

    def export_history_json(self, filepath: str = "trade_history.json"):
        """Export full trade history to JSON file."""
        history = [t.to_history_dict() for t in self.trades]
        with open(filepath, "w") as f:
            json.dump(history, f, indent=2)
        print(f"Exported {len(history)} trades to {filepath}")

    def export_history_csv(self, filepath: str = "trade_history.csv"):
        """Export trade history to CSV file."""
        import csv

        if not self.trades:
            print("No trades to export")
            return

        history = [t.to_history_dict() for t in self.trades]
        fieldnames = history[0].keys()

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(history)
        print(f"Exported {len(history)} trades to {filepath}")

    def print_history(self, limit: int = 20):
        """Print recent trade history to console."""
        trades = self.trades[-limit:]
        if not trades:
            print("No trade history")
            return

        print(f"\n{'='*80}")
        print(f"TRADE HISTORY (last {len(trades)} trades) - {TIMEZONE_NAME}")
        print(f"{'='*80}")

        for i, t in enumerate(trades, 1):
            exec_time = datetime.fromtimestamp(
                t.executed_at / 1000, tz=LOCAL_TZ
            ).strftime("%m/%d %H:%M") if t.executed_at else "N/A"

            status = "✓" if t.won else "✗" if t.won is False else "⏳"
            strategy_icon = "📋" if t.strategy == "copytrade" else "📈"

            print(f"\n{i}. {strategy_icon} {exec_time} | {t.market_slug}")
            print(f"   Position: {t.direction.upper()} ${t.amount:.2f} @ {t.execution_price:.3f}")

            # Show costs
            costs = []
            if t.fee_pct > 0:
                costs.append(f"Fee: {t.fee_pct:.2%}")
            if t.slippage_pct > 0:
                costs.append(f"Slip: {t.slippage_pct:.2f}%")
            if t.delay_impact_pct > 0:
                costs.append(f"Delay: +{t.delay_impact_pct:.2f}%")
            if costs:
                print(f"   Costs: {' | '.join(costs)}")

            # Show result
            if t.outcome:
                print(f"   Result: {status} {t.outcome.upper()} | "
                      f"Gross: ${t.gross_profit:+.2f} | Fee: ${t.fee_amount:.2f} | "
                      f"Net: ${t.pnl:+.2f}")
            else:
                print(f"   Result: {status} PENDING")

            # Copytrade details
            if t.strategy == "copytrade" and t.trader_name:
                print(f"   Copied: {t.trader_name} (${t.trader_amount:.2f} @ {t.trader_price:.3f}) | "
                      f"Delay: {t.copy_delay_ms}ms")

        print(f"\n{'='*80}")
        print(f"SUMMARY")
        print(f"{'='*80}")
        total_pnl = sum(t.pnl for t in trades if t.outcome)
        wins = sum(1 for t in trades if t.won is True)
        losses = sum(1 for t in trades if t.won is False)
        pending = sum(1 for t in trades if t.outcome is None)
        total_fees = sum(t.fee_amount for t in trades if t.outcome)

        print(f"Trades: {wins}W / {losses}L / {pending}P | "
              f"Win Rate: {wins/(wins+losses)*100:.1f}%" if wins+losses > 0 else "N/A")
        print(f"Total P&L: ${total_pnl:+.2f} | Total Fees Paid: ${total_fees:.2f}")
        print(f"Current Bankroll: ${self.bankroll:.2f}")
        print(f"{'='*80}\n")

    def get_statistics(self) -> dict:
        """Get comprehensive trading statistics."""
        settled = [t for t in self.trades if t.outcome]
        wins = [t for t in settled if t.won]
        losses = [t for t in settled if not t.won]

        return {
            "total_trades": len(self.trades),
            "settled_trades": len(settled),
            "pending_trades": len(self.trades) - len(settled),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(settled) * 100 if settled else 0,
            "total_pnl": sum(t.pnl for t in settled),
            "total_fees_paid": sum(t.fee_amount for t in settled),
            "total_gross_profit": sum(t.gross_profit for t in settled),
            "avg_win": sum(t.pnl for t in wins) / len(wins) if wins else 0,
            "avg_loss": sum(t.pnl for t in losses) / len(losses) if losses else 0,
            "largest_win": max((t.pnl for t in wins), default=0),
            "largest_loss": min((t.pnl for t in losses), default=0),
            "avg_slippage_pct": sum(t.slippage_pct for t in settled) / len(settled) if settled else 0,
            "avg_fee_pct": sum(t.fee_pct for t in settled) / len(settled) * 100 if settled else 0,
            "avg_delay_impact_pct": sum(t.delay_impact_pct for t in settled) / len(settled) if settled else 0,
            "bankroll": self.bankroll,
        }

    @classmethod
    def load(cls) -> "TradingState":
        state = cls()

        # Load working state
        if os.path.exists(Config.TRADES_FILE):
            try:
                with open(Config.TRADES_FILE) as f:
                    data = json.load(f)
                state.trades = [Trade(**t) for t in data.get("trades", [])]
                state.daily_bets = data.get("daily_bets", 0)
                state.daily_pnl = data.get("daily_pnl", 0.0)
                state.last_reset_date = data.get("last_reset_date", "")
                state.bankroll = data.get("bankroll", 100.0)
                state._last_saved_trade_id = data.get("last_trade_id", "")
            except Exception as e:
                print(f"[trader] Error loading state: {e}")

        # Load saved trade IDs from full history to avoid duplicates
        history_file = "trade_history_full.json"
        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    history = json.load(f)
                for t in history:
                    trade_id = f"{t.get('timestamp')}_{t.get('executed_at')}_{t.get('direction')}"
                    state._saved_trade_ids.add(trade_id)
                print(f"[history] Loaded {len(state._saved_trade_ids)} trades from history")
            except Exception as e:
                print(f"[history] Error loading history: {e}")

        return state

    @classmethod
    def load_full_history(cls) -> "TradingState":
        """Load complete trade history from the full history file."""
        state = cls()
        history_file = "trade_history_full.json"

        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    history = json.load(f)
                state.trades = [Trade(**t) for t in history]
                print(f"[history] Loaded {len(state.trades)} trades from full history")
            except Exception as e:
                print(f"[history] Error loading full history: {e}")

        # Also load current bankroll from working state
        if os.path.exists(Config.TRADES_FILE):
            try:
                with open(Config.TRADES_FILE) as f:
                    data = json.load(f)
                state.bankroll = data.get("bankroll", 100.0)
            except Exception:
                pass

        return state


class PaperTrader:
    """Paper trading — logs trades without executing, with realistic simulation."""

    def __init__(self):
        # Import here to avoid circular import
        from polymarket import PolymarketClient

        self._client = PolymarketClient()

    def place_bet(
        self,
        market: Market,
        direction: str,
        amount: float,
        confidence: float,
        streak_length: int,
        **kwargs,  # copytrade fields
    ) -> Trade | None:
        """Place a simulated bet with realistic fees, slippage, and fill simulation.

        Returns None if order is rejected (e.g., below minimum size).
        """
        # Validate minimum order size
        if amount < Config.MIN_BET:
            print(
                f"[PAPER] ❌ Order rejected: ${amount:.2f} below minimum ${Config.MIN_BET:.2f}"
            )
            return None

        entry_price = market.up_price if direction == "up" else market.down_price
        executed_at = int(time.time() * 1000)  # milliseconds

        # Get token ID for the direction we're betting on
        token_id = market.up_token_id if direction == "up" else market.down_token_id

        # Default simulation values
        fee_rate_bps = 0
        fee_pct = 0.0
        spread = 0.0
        slippage_pct = 0.0
        fill_pct = 100.0
        delay_impact_pct = 0.0
        execution_price = entry_price if entry_price > 0 else 0.5
        best_bid = 0.0
        best_ask = 0.0
        market_volume = market.volume if hasattr(market, 'volume') else 0.0

        # Price at signal (before any processing)
        price_at_signal = entry_price

        # Get copy delay if this is a copytrade
        copy_delay_ms = kwargs.get("copy_delay_ms", 0)

        # Query real fee rate and orderbook for realistic simulation
        if token_id:
            try:
                # Get fee rate
                fee_rate_bps = self._client.get_fee_rate(token_id)
                fee_pct = self._client.calculate_fee(execution_price, fee_rate_bps)

                # Get orderbook for best bid/ask
                book = self._client.get_orderbook(token_id)
                if book:
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    if bids:
                        best_bid = max(float(b["price"]) for b in bids)
                    if asks:
                        best_ask = min(float(a["price"]) for a in asks)

                # Get execution price with slippage and copy delay impact
                exec_price, spread, slippage_pct, fill_pct, delay_impact_pct = (
                    self._client.get_execution_price(
                        token_id, "BUY", amount, copy_delay_ms
                    )
                )
                if exec_price > 0:
                    execution_price = exec_price
                    # Recalculate fee at actual execution price
                    fee_pct = self._client.calculate_fee(execution_price, fee_rate_bps)
            except Exception as e:
                print(f"[PAPER] Warning: Could not fetch market data: {e}")

        # Calculate price movement from signal to execution
        price_movement_pct = 0.0
        if price_at_signal > 0:
            price_movement_pct = ((execution_price - price_at_signal) / price_at_signal) * 100

        # Adjust amount for partial fill
        filled_amount = amount * (fill_pct / 100.0)
        if fill_pct < 100.0:
            print(
                f"[PAPER] ⚠️  Partial fill: {fill_pct:.1f}% of ${amount:.2f} = ${filled_amount:.2f}"
            )

        trade = Trade(
            timestamp=market.timestamp,
            market_slug=market.slug,
            direction=direction,
            amount=filled_amount,  # Use filled amount, not requested amount
            entry_price=entry_price if entry_price > 0 else 0.5,
            streak_length=streak_length,
            confidence=confidence,
            paper=True,
            executed_at=executed_at,
            market_price_at_copy=entry_price,
            # Realistic simulation fields
            fee_rate_bps=fee_rate_bps,
            fee_pct=fee_pct,
            spread=spread,
            slippage_pct=slippage_pct,
            execution_price=execution_price,
            fill_pct=fill_pct,
            delay_impact_pct=delay_impact_pct,
            requested_amount=amount,  # Original requested amount
            # Price movement tracking
            price_at_signal=price_at_signal,
            price_at_execution=execution_price,
            price_movement_pct=price_movement_pct,
            # Market context
            market_volume=market_volume,
            best_bid=best_bid,
            best_ask=best_ask,
            **kwargs,  # pass copytrade fields
        )

        # Log based on strategy type
        spread_cents = spread * 100  # Convert to cents for display
        if kwargs.get("strategy") == "copytrade":
            trader = kwargs.get("trader_name", "unknown")
            trader_amt = kwargs.get("trader_amount", 0)
            delay = kwargs.get("copy_delay_ms", 0)
            delay_info = f" | Delay impact: +{delay_impact_pct:.2f}%" if delay_impact_pct > 0 else ""
            print(
                f"[PAPER] Copied {trader}: ${filled_amount:.2f} on {direction.upper()} @ {execution_price:.3f} "
                f"| Trader bet ${trader_amt:.2f} @ {kwargs.get('trader_price', 0):.2f}"
            )
            print(
                f"        Fee: {fee_pct:.2%} | Spread: {spread_cents:.0f}¢ | "
                f"Slippage: {slippage_pct:.2f}%{delay_info}"
            )
        else:
            print(
                f"[PAPER] Bet ${filled_amount:.2f} on {direction.upper()} @ {execution_price:.3f} "
                f"| {market.title} | streak={streak_length} conf={confidence:.1%}"
            )
            print(
                f"        Fee: {fee_pct:.2%} | Spread: {spread_cents:.0f}¢ | Slippage: {slippage_pct:.2f}%"
            )
        return trade


class LiveTrader:
    """Live trading via Polymarket CLOB API."""

    def __init__(self):
        if not Config.PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY not set in .env")
        self._init_client()

    def _init_client(self):
        """Initialize py-clob-client with wallet credentials."""
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import OrderArgs, OrderType

            self.client = ClobClient(
                Config.CLOB_API,
                key=Config.PRIVATE_KEY,
                chain_id=Config.CHAIN_ID,
            )
            # Derive API credentials
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            self.OrderArgs = OrderArgs
            self.OrderType = OrderType
            print("[trader] ✅ Live trading client initialized")
        except ImportError:
            raise ImportError("py-clob-client not installed. Run: pip install py-clob-client")
        except Exception as e:
            raise RuntimeError(f"Failed to init trading client: {e}")

    def place_bet(
        self,
        market: Market,
        direction: str,
        amount: float,
        confidence: float,
        streak_length: int,
        **kwargs,  # copytrade fields
    ) -> Trade:
        token_id = market.up_token_id if direction == "up" else market.down_token_id
        if not token_id:
            raise ValueError(f"No token ID for {direction} side")

        entry_price = market.up_price if direction == "up" else market.down_price
        if entry_price <= 0:
            entry_price = 0.5

        executed_at = int(time.time() * 1000)  # milliseconds

        # Calculate size (number of shares)
        size = round(amount / entry_price, 2)

        try:
            order = self.client.create_and_post_order(
                self.OrderArgs(
                    token_id=token_id,
                    price=entry_price,
                    size=size,
                    side="BUY",
                )
            )
            order_id = order.get("orderID", order.get("id", "unknown"))

            # Log based on strategy type
            if kwargs.get("strategy") == "copytrade":
                trader = kwargs.get("trader_name", "unknown")
                print(
                    f"[LIVE] Copied {trader}: ${amount:.2f} on {direction.upper()} @ {entry_price:.2f} "
                    f"| order={order_id}"
                )
            else:
                print(
                    f"[LIVE] Bet ${amount:.2f} on {direction.upper()} @ {entry_price:.2f} "
                    f"| {market.title} | order={order_id}"
                )
        except Exception as e:
            print(f"[LIVE] Order failed: {e}")
            order_id = f"FAILED:{e}"

        return Trade(
            timestamp=market.timestamp,
            market_slug=market.slug,
            direction=direction,
            amount=amount,
            entry_price=entry_price,
            streak_length=streak_length,
            confidence=confidence,
            paper=False,
            order_id=order_id,
            executed_at=executed_at,
            market_price_at_copy=entry_price,
            **kwargs,  # pass copytrade fields
        )
