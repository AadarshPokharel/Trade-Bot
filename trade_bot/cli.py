from __future__ import annotations

import argparse
from typing import Any, Dict

from trade_bot.brokers import PaperBroker
from trade_bot.config import load_config
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


def build_engine(config: Dict[str, Any]) -> TradingEngine:
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
    return TradingEngine(
        broker=broker,
        data_feed=data_feed,
        strategy=strategy,
        risk_manager=risk_manager,
    )


def run_command(config_path: str) -> int:
    config = load_config(config_path)
    engine = build_engine(config)
    result = engine.run()

    print("Simulation complete")
    print(f"Starting cash: {result.starting_cash:.2f}")
    print(f"Ending cash:   {result.ending_cash:.2f}")
    print(f"Ending equity: {result.ending_equity:.2f}")
    print(f"Total fills:   {len(result.fills)}")
    print("")
    print("Open positions:")
    for symbol, position in sorted(result.open_positions.items()):
        latest_price = result.latest_prices.get(symbol, position.average_price)
        print(
            f"- {symbol}: qty={position.quantity:.4f}, "
            f"avg={position.average_price:.4f}, last={latest_price:.4f}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the trade bot scaffold")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a paper-trading simulation")
    run_parser.add_argument(
        "--config",
        default="config/demo.json",
        help="Path to a JSON config file",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return run_command(args.config)

    parser.error(f"Unknown command: {args.command}")
    return 2
