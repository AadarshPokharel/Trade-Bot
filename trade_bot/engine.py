from __future__ import annotations

from typing import Dict, List

from trade_bot.brokers.base import Broker
from trade_bot.data.base import MarketDataFeed
from trade_bot.models import (
    Candle,
    DecisionStatus,
    DecisionTrace,
    OrderRequest,
    OrderSide,
    Signal,
    SimulationResult,
)
from trade_bot.risk import RiskManager
from trade_bot.strategies.base import Strategy


class TradingEngine:
    def __init__(
        self,
        broker: Broker,
        data_feed: MarketDataFeed,
        strategy: Strategy,
        risk_manager: RiskManager,
    ):
        self._broker = broker
        self._data_feed = data_feed
        self._strategy = strategy
        self._risk_manager = risk_manager

    def run(self) -> SimulationResult:
        rolling_history: Dict[str, List[Candle]] = {}
        decision_trace: List[DecisionTrace] = []
        portfolio = self._broker.get_portfolio()
        starting_cash = portfolio.cash

        for market_snapshot in self._data_feed.stream():
            for symbol, candle in market_snapshot.items():
                self._broker.set_latest_price(candle.instrument, candle.close)
                symbol_history = rolling_history.setdefault(symbol, [])
                symbol_history.append(candle)

                position = portfolio.get_position(candle.instrument)
                decision = self._strategy.evaluate(symbol_history, position)
                if decision.signal == Signal.HOLD:
                    continue

                order = OrderRequest(
                    instrument=decision.instrument,
                    side=OrderSide(decision.signal.value),
                    quantity=decision.quantity,
                    price=candle.close,
                )
                try:
                    self._risk_manager.approve(order, current_position_size=position.quantity)
                    self._broker.submit_order(order)
                    decision_trace.append(
                        DecisionTrace(
                            instrument=decision.instrument,
                            signal=decision.signal,
                            status=DecisionStatus.EXECUTED,
                            timestamp=candle.timestamp,
                            price=candle.close,
                            quantity=decision.quantity,
                            reason=decision.reason,
                        )
                    )
                except ValueError as error:
                    decision_trace.append(
                        DecisionTrace(
                            instrument=decision.instrument,
                            signal=decision.signal,
                            status=DecisionStatus.REJECTED,
                            timestamp=candle.timestamp,
                            price=candle.close,
                            quantity=decision.quantity,
                            reason=decision.reason,
                            detail=str(error),
                        )
                    )

        latest_prices = self._broker.latest_prices()
        final_portfolio = self._broker.get_portfolio()
        return SimulationResult(
            starting_cash=starting_cash,
            ending_cash=final_portfolio.cash,
            ending_equity=final_portfolio.total_equity(latest_prices),
            fills=list(final_portfolio.fills),
            open_positions=dict(final_portfolio.positions),
            latest_prices=latest_prices,
            decision_trace=decision_trace,
            candle_history={symbol: list(history) for symbol, history in rolling_history.items()},
        )
