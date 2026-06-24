from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trade_bot.config import load_config
from trade_bot.env import load_dotenv
from trade_bot.modes import mode_for_config, mode_label_for_config
from trade_bot.models import AssetClass, Candle, Instrument, OrderRequest, OrderSide, Position, Signal
from trade_bot.risk import RiskLimits, RiskManager
from trade_bot.runtime import build_strategy


OANDA_PRACTICE_BASE_URL = "https://api-fxpractice.oanda.com"
OANDA_LIVE_BASE_URL = "https://api-fxtrade.oanda.com"


class OandaTradingError(RuntimeError):
    """Raised when the OANDA setup or request fails."""


@dataclass(frozen=True)
class OandaDecisionResult:
    symbol: str
    asset_class: str
    signal: str
    status: str
    quantity: float
    reference_price: float
    reason: str
    detail: str = ""
    order_id: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_timestamp(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _instrument_from_config(config: Dict[str, Any]) -> Instrument:
    return Instrument(symbol=config["symbol"], asset_class=AssetClass(config["asset_class"]))


def _oanda_symbol(symbol: str) -> str:
    if "_" in symbol:
        return symbol
    if len(symbol) == 6:
        return f"{symbol[:3]}_{symbol[3:]}"
    return symbol


def _normalize_units(quantity: float) -> int:
    units = int(round(quantity))
    if units == 0:
        raise OandaTradingError(
            "OANDA orders require non-zero integer unit sizes. Increase strategy.trade_quantity."
        )
    return units


class OandaClient:
    def __init__(self, broker_config: Dict[str, Any], market_data_config: Dict[str, Any]):
        load_dotenv()
        api_token = os.getenv("OANDA_API_TOKEN")
        account_id = os.getenv("OANDA_ACCOUNT_ID")
        if not api_token or not account_id:
            raise OandaTradingError(
                "Missing OANDA credentials. Add OANDA_API_TOKEN and OANDA_ACCOUNT_ID to your shell or .env file."
            )

        self._api_token = api_token
        self._account_id = account_id
        self._base_url = broker_config.get(
            "base_url",
            OANDA_PRACTICE_BASE_URL if bool(broker_config.get("paper", True)) else OANDA_LIVE_BASE_URL,
        ).rstrip("/")
        self._granularity = market_data_config.get("granularity", "M1")

    def _request_json(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        query = f"?{urlencode(params, doseq=True)}" if params else ""
        request = Request(
            f"{self._base_url}{path}{query}",
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Accept-Datetime-Format": "RFC3339",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            data=json.dumps(body).encode("utf-8") if body is not None else None,
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise OandaTradingError(f"OANDA API error {error.code}: {details}") from error
        except URLError as error:
            raise OandaTradingError(f"Unable to reach OANDA API: {error}") from error

    def get_account_summary(self) -> Dict[str, Any]:
        payload = self._request_json("GET", f"/v3/accounts/{self._account_id}/summary")
        return payload.get("account", {})

    def list_open_positions(self) -> List[Dict[str, Any]]:
        payload = self._request_json("GET", f"/v3/accounts/{self._account_id}/openPositions")
        return payload.get("positions", [])

    def get_candles(self, instruments: Iterable[Instrument], limit: int) -> Dict[str, List[Candle]]:
        candles_by_symbol: Dict[str, List[Candle]] = {}
        for instrument in instruments:
            oanda_symbol = _oanda_symbol(instrument.symbol)
            payload = self._request_json(
                "GET",
                f"/v3/instruments/{oanda_symbol}/candles",
                params={
                    "price": "M",
                    "granularity": self._granularity,
                    "count": limit,
                },
            )
            candles = []
            for raw_candle in payload.get("candles", []):
                mid = raw_candle.get("mid")
                if not mid:
                    continue
                candles.append(
                    Candle(
                        instrument=instrument,
                        timestamp=_parse_timestamp(raw_candle["time"]),
                        open=float(mid["o"]),
                        high=float(mid["h"]),
                        low=float(mid["l"]),
                        close=float(mid["c"]),
                        volume=float(raw_candle.get("volume", 0.0)),
                    )
                )
            candles_by_symbol[instrument.symbol] = candles
        return candles_by_symbol

    def submit_order(self, instrument: Instrument, side: OrderSide, quantity: float) -> Dict[str, Any]:
        units = _normalize_units(quantity)
        signed_units = units if side == OrderSide.BUY else -units
        payload = {
            "order": {
                "type": "MARKET",
                "instrument": _oanda_symbol(instrument.symbol),
                "units": str(signed_units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        return self._request_json(
            "POST",
            f"/v3/accounts/{self._account_id}/orders",
            body=payload,
        )


def _build_risk_manager(config: Dict[str, Any]) -> RiskManager:
    risk_config = config["risk"]
    return RiskManager(
        RiskLimits(
            max_position_size=float(risk_config["max_position_size"]),
            max_notional_per_trade=float(risk_config["max_notional_per_trade"]),
        )
    )


def _position_map(client: OandaClient, expected_instruments: Dict[str, Instrument]) -> Dict[str, Position]:
    positions: Dict[str, Position] = {}
    for raw_position in client.list_open_positions():
        symbol = raw_position["instrument"].replace("_", "")
        instrument = expected_instruments.get(symbol)
        if instrument is None:
            continue
        long_units = float(raw_position.get("long", {}).get("units", 0.0))
        short_units = float(raw_position.get("short", {}).get("units", 0.0))
        net_units = long_units + short_units
        average_price = 0.0
        if long_units > 0:
            average_price = float(raw_position.get("long", {}).get("averagePrice", 0.0))
        elif short_units < 0:
            average_price = float(raw_position.get("short", {}).get("averagePrice", 0.0))
        positions[symbol] = Position(
            instrument=instrument,
            quantity=max(net_units, 0.0),
            average_price=average_price,
        )
    return positions


def build_oanda_dashboard_payload(config_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    broker_config = config.get("broker", {})
    market_data_config = config["market_data"]
    client = OandaClient(broker_config=broker_config, market_data_config=market_data_config)
    instruments = [_instrument_from_config(item) for item in market_data_config["instruments"]]
    instrument_map = {instrument.symbol: instrument for instrument in instruments}
    strategy = build_strategy(config["strategy"])
    positions = _position_map(client, instrument_map)
    account = client.get_account_summary()
    history_limit = max(
        int(market_data_config.get("history_limit", 60)),
        int(config["strategy"]["long_window"]) + 2,
    )
    candles_by_symbol = client.get_candles(instruments=instruments, limit=history_limit)

    instrument_payloads: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    for instrument in instruments:
        candles = candles_by_symbol.get(instrument.symbol, [])
        if not candles:
            continue

        first_candle = candles[0]
        last_candle = candles[-1]
        position = positions.get(
            instrument.symbol,
            Position(instrument=instrument, quantity=0.0, average_price=0.0),
        )
        decision = strategy.evaluate(candles, position)
        last_signal = None
        if decision.signal != Signal.HOLD:
            last_signal = {
                "symbol": instrument.symbol,
                "asset_class": instrument.asset_class.value,
                "signal": decision.signal.value,
                "status": "preview",
                "quantity": decision.quantity,
                "price": last_candle.close,
                "reason": decision.reason,
                "detail": "Live dashboard preview only; no order placed.",
                "time": _to_timestamp(last_candle.timestamp),
            }
            decisions.append(last_signal)

        price_change = last_candle.close - first_candle.open
        change_pct = (price_change / first_candle.open) * 100 if first_candle.open else 0.0
        stance = "long" if position.quantity > 0 else "flat"
        instrument_payloads.append(
            {
                "symbol": instrument.symbol,
                "asset_class": instrument.asset_class.value,
                "latest_price": last_candle.close,
                "price_change": price_change,
                "change_pct": change_pct,
                "position": {
                    "symbol": instrument.symbol,
                    "asset_class": instrument.asset_class.value,
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "last_price": last_candle.close,
                    "market_value": position.quantity * last_candle.close,
                },
                "last_signal": last_signal,
                "analysis_summary": (
                    f"The bot is {stance} on {instrument.symbol}. "
                    f"Latest forex signal: {decision.signal.value.upper()} because {decision.reason}."
                ),
                "candles": [
                    {
                        "time": _to_timestamp(candle.timestamp),
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
                    for candle in candles
                ],
            }
        )

    latest_prices = {item["symbol"]: item["latest_price"] for item in instrument_payloads}
    open_positions = [
        {
            "symbol": symbol,
            "asset_class": position.instrument.asset_class.value,
            "quantity": position.quantity,
            "average_price": position.average_price,
            "last_price": latest_prices.get(symbol),
            "market_value": position.quantity * latest_prices.get(symbol, position.average_price),
        }
        for symbol, position in sorted(positions.items())
        if position.quantity > 0
    ]

    balance = float(account.get("balance", 0.0))
    nav = float(account.get("NAV", balance))
    pnl = nav - balance
    return_pct = (pnl / balance * 100) if balance else 0.0
    mode = mode_for_config(config)
    mode_label = mode_label_for_config(config)
    return {
        "generated_at": _utc_now().isoformat(),
        "paper_trading": bool(broker_config.get("paper", True)),
        "mode": mode,
        "mode_label": mode_label,
        "strategy": config["strategy"],
        "risk": config["risk"],
        "metrics": {
            "starting_cash": balance,
            "ending_cash": balance,
            "ending_equity": nav,
            "pnl": pnl,
            "return_pct": return_pct,
            "fill_count": 0,
            "open_position_count": len(open_positions),
        },
        "bot_summary": instrument_payloads[0]["analysis_summary"] if instrument_payloads else "",
        "instruments": instrument_payloads,
        "fills": [],
        "decisions": decisions,
        "open_positions": open_positions,
        "live_mode": True,
        "execute_orders": bool(config.get("live", {}).get("execute_orders", False)),
    }


def run_oanda_live_trading(
    config_path: str,
    *,
    iterations: int = 0,
    poll_seconds: Optional[int] = None,
) -> int:
    try:
        config = load_config(config_path)
        broker_config = config.get("broker", {})
        market_data_config = config["market_data"]
        live_config = config.get("live", {})
        execute_orders = bool(live_config.get("execute_orders", False))
        poll_interval = int(poll_seconds or live_config.get("poll_seconds", 60))

        client = OandaClient(broker_config=broker_config, market_data_config=market_data_config)
        instruments = [_instrument_from_config(item) for item in market_data_config["instruments"]]
        instrument_map = {instrument.symbol: instrument for instrument in instruments}
        strategy = build_strategy(config["strategy"])
        risk_manager = _build_risk_manager(config)
        history_limit = max(
            int(market_data_config.get("history_limit", 60)),
            int(config["strategy"]["long_window"]) + 2,
        )

        iteration = 0
        while True:
            iteration += 1
            positions = _position_map(client, instrument_map)
            candles_by_symbol = client.get_candles(instruments=instruments, limit=history_limit)
            cycle_results: List[OandaDecisionResult] = []

            for instrument in instruments:
                candles = candles_by_symbol.get(instrument.symbol, [])
                if len(candles) < int(config["strategy"]["long_window"]):
                    cycle_results.append(
                        OandaDecisionResult(
                            symbol=instrument.symbol,
                            asset_class=instrument.asset_class.value,
                            signal="hold",
                            status="skipped",
                            quantity=0.0,
                            reference_price=candles[-1].close if candles else 0.0,
                            reason="not enough market history yet",
                        )
                    )
                    continue

                position = positions.get(
                    instrument.symbol,
                    Position(instrument=instrument, quantity=0.0, average_price=0.0),
                )
                decision = strategy.evaluate(candles, position)
                latest_price = candles[-1].close
                if decision.signal == Signal.HOLD:
                    cycle_results.append(
                        OandaDecisionResult(
                            symbol=instrument.symbol,
                            asset_class=instrument.asset_class.value,
                            signal="hold",
                            status="skipped",
                            quantity=0.0,
                            reference_price=latest_price,
                            reason=decision.reason,
                        )
                    )
                    continue

                order = OrderRequest(
                    instrument=instrument,
                    side=OrderSide(decision.signal.value),
                    quantity=decision.quantity,
                    price=latest_price,
                )
                try:
                    risk_manager.approve(order, current_position_size=position.quantity)
                except ValueError as error:
                    cycle_results.append(
                        OandaDecisionResult(
                            symbol=instrument.symbol,
                            asset_class=instrument.asset_class.value,
                            signal=decision.signal.value,
                            status="rejected",
                            quantity=decision.quantity,
                            reference_price=latest_price,
                            reason=decision.reason,
                            detail=str(error),
                        )
                    )
                    continue

                if not execute_orders:
                    cycle_results.append(
                        OandaDecisionResult(
                            symbol=instrument.symbol,
                            asset_class=instrument.asset_class.value,
                            signal=decision.signal.value,
                            status="preview",
                            quantity=decision.quantity,
                            reference_price=latest_price,
                            reason=decision.reason,
                            detail="Live execution disabled. Set live.execute_orders to true to place orders.",
                        )
                    )
                    continue

                response = client.submit_order(
                    instrument=instrument,
                    side=OrderSide(decision.signal.value),
                    quantity=decision.quantity,
                )
                fill = response.get("orderFillTransaction", {})
                create = response.get("orderCreateTransaction", {})
                cycle_results.append(
                    OandaDecisionResult(
                        symbol=instrument.symbol,
                        asset_class=instrument.asset_class.value,
                        signal=decision.signal.value,
                        status="filled" if fill else "submitted",
                        quantity=abs(float(fill.get("units") or create.get("units") or decision.quantity)),
                        reference_price=latest_price,
                        reason=decision.reason,
                        detail="Order submitted to OANDA.",
                        order_id=str(fill.get("id") or create.get("id") or ""),
                    )
                )

            print(f"\nOANDA live cycle {iteration} at {_utc_now().isoformat()}")
            for result in cycle_results:
                suffix = f" ({result.detail})" if result.detail else ""
                print(
                    f"- {result.symbol}: {result.signal.upper()} {result.quantity} @ "
                    f"{result.reference_price:.5f} -> {result.status}{suffix}"
                )

            if iterations and iteration >= iterations:
                break
            if poll_interval <= 0:
                break
            time.sleep(poll_interval)

        return 0
    except OandaTradingError as error:
        print(f"OANDA setup error: {error}")
        return 1
