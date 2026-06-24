from __future__ import annotations

from datetime import datetime
from typing import Dict

from trade_bot.brokers.base import Broker
from trade_bot.models import Fill, Instrument, OrderRequest, OrderSide, Portfolio


class PaperBroker(Broker):
    def __init__(self, starting_cash: float, commission_per_trade: float = 0.0):
        self._portfolio = Portfolio(cash=starting_cash)
        self._latest_prices: Dict[str, float] = {}
        self._commission_per_trade = commission_per_trade

    def submit_order(self, request: OrderRequest) -> Fill:
        commission = self._commission_per_trade
        fill = Fill(
            instrument=request.instrument,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            commission=commission,
            timestamp=datetime.utcnow(),
        )
        position = self._portfolio.get_position(request.instrument)
        notional = request.quantity * request.price

        if request.side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self._portfolio.cash:
                raise ValueError(
                    f"Insufficient cash for {request.instrument.symbol}: "
                    f"need {total_cost:.2f}, have {self._portfolio.cash:.2f}"
                )
            self._portfolio.cash -= total_cost
        else:
            if request.quantity > position.quantity:
                raise ValueError(
                    f"Insufficient position for {request.instrument.symbol}: "
                    f"trying to sell {request.quantity}, have {position.quantity}"
                )
            self._portfolio.cash += notional - commission

        position.apply_fill(fill)
        self._portfolio.fills.append(fill)
        self._latest_prices[request.instrument.symbol] = request.price
        return fill

    def get_portfolio(self) -> Portfolio:
        return self._portfolio

    def latest_prices(self) -> Dict[str, float]:
        return dict(self._latest_prices)

    def set_latest_price(self, instrument: Instrument, price: float) -> None:
        self._latest_prices[instrument.symbol] = price
