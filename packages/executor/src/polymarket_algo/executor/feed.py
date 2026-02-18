from collections.abc import Callable

from polymarket_algo.executor.ws import PolymarketWebSocket, TradeEvent


class PolymarketDataFeed:
    """Thin DataFeed adapter around ``PolymarketWebSocket``."""

    name = "polymarket-websocket"

    def __init__(self):
        self._callbacks: list[Callable[[str, float, float], None]] = []
        self._ws = PolymarketWebSocket(on_trade=self._handle_trade)

    def start(self) -> None:
        self._ws.start()

    def stop(self) -> None:
        self._ws.stop()

    def on_price(self, callback: Callable[[str, float, float], None]) -> None:
        self._callbacks.append(callback)

    def is_connected(self) -> bool:
        return self._ws.is_connected()

    def subscribe_market(self, condition_id: str, token_ids: list[str] | None = None) -> None:
        """Forward market subscription to the underlying websocket."""
        self._ws.subscribe_market(condition_id, token_ids)

    def unsubscribe_market(self, condition_id: str) -> None:
        self._ws.unsubscribe_market(condition_id)

    def _handle_trade(self, trade: TradeEvent) -> None:
        symbol = trade.market_id or trade.token_id
        for callback in self._callbacks:
            callback(symbol, trade.price, trade.timestamp)
