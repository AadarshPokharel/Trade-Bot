from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from trade_bot.models import Fill, Instrument, OrderRequest, Portfolio


class Broker(ABC):
    @abstractmethod
    def submit_order(self, request: OrderRequest) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def get_portfolio(self) -> Portfolio:
        raise NotImplementedError

    @abstractmethod
    def latest_prices(self) -> Dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def set_latest_price(self, instrument: Instrument, price: float) -> None:
        raise NotImplementedError
