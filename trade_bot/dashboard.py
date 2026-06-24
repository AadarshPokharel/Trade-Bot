from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from trade_bot.config import load_config
from trade_bot.live import build_live_dashboard_payload
from trade_bot.modes import mode_for_config, mode_label_for_config
from trade_bot.models import Candle, DecisionTrace, Fill, Position, SimulationResult
from trade_bot.runtime import build_engine


def _to_timestamp(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp())


def _serialize_candle(candle: Candle) -> Dict[str, Any]:
    return {
        "time": _to_timestamp(candle.timestamp),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _serialize_fill(fill: Fill) -> Dict[str, Any]:
    return {
        "symbol": fill.instrument.symbol,
        "asset_class": fill.instrument.asset_class.value,
        "side": fill.side.value,
        "quantity": fill.quantity,
        "price": fill.price,
        "commission": fill.commission,
        "time": _to_timestamp(fill.timestamp),
    }


def _serialize_decision(decision: DecisionTrace) -> Dict[str, Any]:
    return {
        "symbol": decision.instrument.symbol,
        "asset_class": decision.instrument.asset_class.value,
        "signal": decision.signal.value,
        "status": decision.status.value,
        "quantity": decision.quantity,
        "price": decision.price,
        "reason": decision.reason,
        "detail": decision.detail,
        "time": _to_timestamp(decision.timestamp),
    }


def _serialize_position(position: Position, latest_price: Optional[float]) -> Dict[str, Any]:
    market_value = position.quantity * (latest_price or position.average_price)
    return {
        "symbol": position.instrument.symbol,
        "asset_class": position.instrument.asset_class.value,
        "quantity": position.quantity,
        "average_price": position.average_price,
        "last_price": latest_price,
        "market_value": market_value,
    }


def _build_bot_summary(result: SimulationResult, symbol: str) -> str:
    position = result.open_positions.get(symbol)
    latest_price = result.latest_prices.get(symbol)
    recent_signal = next(
        (
            decision
            for decision in reversed(result.decision_trace)
            if decision.instrument.symbol == symbol
        ),
        None,
    )
    stance = "flat"
    if position and position.quantity > 0:
        stance = "long"

    if recent_signal is None:
        return f"The bot is {stance} on {symbol} with no recent executed signal."

    signal_word = recent_signal.signal.value.upper()
    if recent_signal.status.value == "rejected":
        return (
            f"The bot attempted a {signal_word} on {symbol} near {latest_price:.2f}, "
            f"but risk controls blocked it."
        )

    return (
        f"The bot is {stance} on {symbol}. Its latest {signal_word} decision was driven by "
        f"{recent_signal.reason}."
    )


def build_dashboard_payload(config_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    broker_type = config.get("broker", {}).get("type")
    market_data_type = config.get("market_data", {}).get("type")
    if broker_type in {"alpaca", "oanda", "ibkr"} or market_data_type in {"alpaca", "oanda", "ibkr"}:
        return build_live_dashboard_payload(config_path)

    engine = build_engine(config)
    result = engine.run()
    mode = mode_for_config(config)
    mode_label = mode_label_for_config(config)

    instruments: List[Dict[str, Any]] = []
    for symbol, candles in sorted(result.candle_history.items()):
        latest_candle = candles[-1]
        first_candle = candles[0]
        latest_price = latest_candle.close
        price_change = latest_price - first_candle.open
        change_pct = (price_change / first_candle.open) * 100 if first_candle.open else 0.0
        position = result.open_positions.get(symbol)
        last_signal = next(
            (
                decision
                for decision in reversed(result.decision_trace)
                if decision.instrument.symbol == symbol
            ),
            None,
        )
        instruments.append(
            {
                "symbol": symbol,
                "asset_class": latest_candle.instrument.asset_class.value,
                "latest_price": latest_price,
                "price_change": price_change,
                "change_pct": change_pct,
                "position": _serialize_position(position, latest_price) if position else None,
                "last_signal": _serialize_decision(last_signal) if last_signal else None,
                "analysis_summary": _build_bot_summary(result, symbol),
                "candles": [_serialize_candle(candle) for candle in candles],
            }
        )

    fills = [_serialize_fill(fill) for fill in result.fills]
    decisions = [_serialize_decision(decision) for decision in result.decision_trace]
    open_positions = [
        _serialize_position(position, result.latest_prices.get(symbol))
        for symbol, position in sorted(result.open_positions.items())
        if position.quantity > 0
    ]
    starting_cash = result.starting_cash
    pnl = result.ending_equity - starting_cash
    return_pct = (pnl / starting_cash) * 100 if starting_cash else 0.0
    active_symbol = instruments[0]["symbol"] if instruments else ""

    return {
        "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "paper_trading": True,
        "mode": mode,
        "mode_label": mode_label,
        "strategy": config["strategy"],
        "risk": config["risk"],
        "metrics": {
            "starting_cash": starting_cash,
            "ending_cash": result.ending_cash,
            "ending_equity": result.ending_equity,
            "pnl": pnl,
            "return_pct": return_pct,
            "fill_count": len(result.fills),
            "open_position_count": len(open_positions),
        },
        "bot_summary": _build_bot_summary(result, active_symbol) if active_symbol else "",
        "instruments": instruments,
        "fills": fills,
        "decisions": decisions,
        "open_positions": open_positions,
    }
