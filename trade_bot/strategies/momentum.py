from __future__ import annotations

from statistics import mean
from typing import List

from trade_bot.models import Candle, OrderSide, Position, Signal, StrategyDecision
from trade_bot.strategies.base import Strategy


class MomentumStrategy(Strategy):
    def __init__(self, short_window: int, long_window: int, trade_quantity: float):
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self._short_window = short_window
        self._long_window = long_window
        self._trade_quantity = trade_quantity

    def evaluate(self, history: List[Candle], position: Position) -> StrategyDecision:
        instrument = history[-1].instrument
        if len(history) < self._long_window:
            return StrategyDecision(instrument=instrument, signal=Signal.HOLD, reason="warmup")

        closes = [candle.close for candle in history]
        short_average = mean(closes[-self._short_window :])
        long_average = mean(closes[-self._long_window :])

        if short_average > long_average and position.quantity <= 0:
            return StrategyDecision(
                instrument=instrument,
                signal=Signal.BUY,
                quantity=self._trade_quantity,
                reason="short average crossed above long average",
            )
        if short_average < long_average and position.quantity > 0:
            return StrategyDecision(
                instrument=instrument,
                signal=Signal.SELL,
                quantity=min(position.quantity, self._trade_quantity),
                reason="short average crossed below long average",
            )
        return StrategyDecision(instrument=instrument, signal=Signal.HOLD, reason="no edge")
