from __future__ import annotations

from typing import Any, Dict

from trade_bot.brokers import PaperBroker
from trade_bot.data import SyntheticMarketDataFeed
from trade_bot.engine import TradingEngine
from trade_bot.risk import RiskLimits, RiskManager
from trade_bot.strategies import MomentumStrategy


def build_strategy(config: Dict[str, Any]) -> MomentumStrategy:
    if config.get("name") != "momentum":
        raise ValueError("Only the momentum strategy is implemented in this scaffold")
    return MomentumStrategy(
        short_window=int(config["short_window"]),
        long_window=int(config["long_window"]),
        trade_quantity=float(config["trade_quantity"]),
    )


def build_runtime(config: Dict[str, Any]) -> Dict[str, Any]:
    engine_config = config["engine"]
    market_data_config = config["market_data"]
    risk_config = config["risk"]

    broker = PaperBroker(
        starting_cash=float(engine_config["starting_cash"]),
        commission_per_trade=float(engine_config.get("commission_per_trade", 0.0)),
    )
    data_feed = SyntheticMarketDataFeed(
        instrument_configs=market_data_config["instruments"],
        length=int(market_data_config["length"]),
        seed=int(market_data_config.get("seed", 0)),
    )
    strategy = build_strategy(config["strategy"])
    risk_manager = RiskManager(
        RiskLimits(
            max_position_size=float(risk_config["max_position_size"]),
            max_notional_per_trade=float(risk_config["max_notional_per_trade"]),
        )
    )
    return {
        "broker": broker,
        "data_feed": data_feed,
        "strategy": strategy,
        "risk_manager": risk_manager,
    }


def build_engine(config: Dict[str, Any]) -> TradingEngine:
    return TradingEngine(**build_runtime(config))
