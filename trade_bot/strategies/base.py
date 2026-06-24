from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from trade_bot.models import Candle, Position, StrategyDecision


class Strategy(ABC):
    @abstractmethod
    def evaluate(self, history: List[Candle], position: Position) -> StrategyDecision:
        raise NotImplementedError
