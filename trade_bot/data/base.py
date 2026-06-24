from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List

from trade_bot.models import Candle


class MarketDataFeed(ABC):
    @abstractmethod
    def stream(self) -> Iterable[Dict[str, Candle]]:
        raise NotImplementedError

    @abstractmethod
    def history(self) -> Dict[str, List[Candle]]:
        raise NotImplementedError
