from __future__ import annotations

from dataclasses import dataclass

from trade_bot.models import OrderRequest


@dataclass(frozen=True)
class RiskLimits:
    max_position_size: float
    max_notional_per_trade: float


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self._limits = limits

    def approve(self, order: OrderRequest, current_position_size: float) -> None:
        if order.quantity <= 0:
            raise ValueError("Order quantity must be positive")

        notional = order.quantity * order.price
        if notional > self._limits.max_notional_per_trade:
            raise ValueError(
                f"Order notional {notional:.2f} exceeds limit "
                f"{self._limits.max_notional_per_trade:.2f}"
            )

        if order.side == "buy":
            projected_position = current_position_size + order.quantity
            if projected_position > self._limits.max_position_size:
                raise ValueError(
                    f"Projected position {projected_position} exceeds limit "
                    f"{self._limits.max_position_size}"
                )
