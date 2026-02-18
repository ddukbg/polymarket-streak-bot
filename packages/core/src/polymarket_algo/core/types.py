from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

import pandas as pd


class Indicator(Protocol):
    name: str

    def compute(self, series: pd.Series, **params: Any) -> pd.Series | pd.DataFrame: ...


class Strategy(Protocol):
    name: str
    description: str
    timeframe: str

    def evaluate(self, candles: pd.DataFrame, **params: Any) -> pd.DataFrame: ...
    @property
    def default_params(self) -> dict[str, Any]: ...
    @property
    def param_grid(self) -> dict[str, list[Any]]: ...


@runtime_checkable
class DataFeed(Protocol):
    name: str

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def on_price(self, callback: Callable[[str, float, float], None]) -> None: ...
    def is_connected(self) -> bool: ...
