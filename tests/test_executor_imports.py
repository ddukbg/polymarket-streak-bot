import importlib

from polymarket_algo.core import DataFeed
from polymarket_algo.executor.feed import PolymarketDataFeed


def test_executor_submodules_import() -> None:
    modules = [
        "polymarket_algo.executor",
        "polymarket_algo.executor.blockchain",
        "polymarket_algo.executor.client",
        "polymarket_algo.executor.feed",
        "polymarket_algo.executor.resilience",
        "polymarket_algo.executor.trader",
        "polymarket_algo.executor.ws",
    ]
    for module in modules:
        importlib.import_module(module)


def test_polymarket_data_feed_conforms_protocol() -> None:
    feed = PolymarketDataFeed()
    assert isinstance(feed, DataFeed)


def test_data_feed_protocol_importable_from_core() -> None:
    # Imported at module level; this verifies re-export and symbol availability.
    assert DataFeed is not None
