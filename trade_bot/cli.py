from __future__ import annotations

import argparse
from typing import Any, Dict

from trade_bot.config import load_config
from trade_bot.live import run_live_trading
from trade_bot.runtime import build_engine
from trade_bot.webapp import run_server


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

    web_parser = subparsers.add_parser("web", help="Run the trading bot web dashboard")
    web_parser.add_argument(
        "--config",
        default="config/demo.json",
        help="Path to a JSON config file",
    )
    web_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    web_parser.add_argument("--port", default=8000, type=int, help="Port to bind")

    live_parser = subparsers.add_parser("live", help="Run live market analysis and trading")
    live_parser.add_argument(
        "--config",
        default="config/alpaca_live.json",
        help="Path to a live trading config file",
    )
    live_parser.add_argument(
        "--iterations",
        default=1,
        type=int,
        help="Number of live polling cycles to run. Use 0 for continuous mode.",
    )
    live_parser.add_argument(
        "--poll-seconds",
        default=None,
        type=int,
        help="Override the polling interval in seconds",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return run_command(args.config)
    if args.command == "web":
        return run_server(host=args.host, port=args.port, config_path=args.config)
    if args.command == "live":
        return run_live_trading(
            args.config,
            iterations=args.iterations,
            poll_seconds=args.poll_seconds,
        )

    parser.error(f"Unknown command: {args.command}")
    return 2
