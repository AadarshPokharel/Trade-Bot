from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class AssetClass(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    FOREX = "forex"
    OPTION = "option"
    FUTURE = "future"
    COMMODITY = "commodity"


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: AssetClass
    quote_currency: str = "USD"


@dataclass(frozen=True)
class Candle:
    instrument: Instrument
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class StrategyDecision:
    instrument: Instrument
    signal: Signal
    quantity: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class OrderRequest:
    instrument: Instrument
    side: OrderSide
    quantity: float
    price: float


@dataclass(frozen=True)
class Fill:
    instrument: Instrument
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0


@dataclass
class Position:
    instrument: Instrument
    quantity: float = 0.0
    average_price: float = 0.0

    def apply_fill(self, fill: Fill) -> None:
        if fill.side == OrderSide.BUY:
            new_quantity = self.quantity + fill.quantity
            if new_quantity <= 0:
                self.quantity = 0.0
                self.average_price = 0.0
                return
            total_cost = (self.average_price * self.quantity) + (
                fill.price * fill.quantity
            )
            self.quantity = new_quantity
            self.average_price = total_cost / new_quantity
            return

        new_quantity = self.quantity - fill.quantity
        self.quantity = max(new_quantity, 0.0)
        if self.quantity == 0:
            self.average_price = 0.0


@dataclass
class Portfolio:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    fills: List[Fill] = field(default_factory=list)

    def get_position(self, instrument: Instrument) -> Position:
        position = self.positions.get(instrument.symbol)
        if position is None:
            position = Position(instrument=instrument)
            self.positions[instrument.symbol] = position
        return position

    def total_equity(self, latest_prices: Dict[str, float]) -> float:
        equity = self.cash
        for symbol, position in self.positions.items():
            equity += position.quantity * latest_prices.get(symbol, position.average_price)
        return equity


@dataclass(frozen=True)
class SimulationResult:
    starting_cash: float
    ending_cash: float
    ending_equity: float
    fills: List[Fill]
    open_positions: Dict[str, Position]
    latest_prices: Dict[str, float]
