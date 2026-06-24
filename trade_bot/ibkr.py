from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from trade_bot.config import load_config
from trade_bot.env import load_dotenv
from trade_bot.modes import mode_for_config, mode_label_for_config
from trade_bot.models import AssetClass, Candle, Instrument, OrderRequest, OrderSide, Position, Signal
from trade_bot.risk import RiskLimits, RiskManager
from trade_bot.runtime import build_strategy


IBKR_PAPER_PORT = 7497
IBKR_LIVE_PORT = 7496


class IbkrTradingError(RuntimeError):
    """Raised when the IBKR setup or request fails."""


@dataclass(frozen=True)
class IbkrDecisionResult:
    symbol: str
    asset_class: str
    signal: str
    status: str
    quantity: float
    reference_price: float
    reason: str
    detail: str = ""
    order_id: str = ""


@dataclass(frozen=True)
class IbkrContractSpec:
    symbol: str
    asset_class: AssetClass
    sec_type: str
    exchange: str
    currency: str
    primary_exchange: str = ""
    last_trade_date_or_contract_month: str = ""
    strike: float = 0.0
    right: str = ""
    multiplier: str = ""
    local_symbol: str = ""
    trading_class: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_timestamp(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


def _import_ib() -> Any:
    try:
        from ib_insync import Contract, Forex, Future, IB, MarketOrder, Option, Stock  # type: ignore
    except ImportError as error:
        raise IbkrTradingError(
            "Missing optional dependency ib_insync. Install it with 'pip install ib-insync'."
        ) from error
    return {
        "IB": IB,
        "Contract": Contract,
        "Stock": Stock,
        "Forex": Forex,
        "Option": Option,
        "Future": Future,
        "MarketOrder": MarketOrder,
    }


def _contract_spec_from_config(config: Dict[str, Any]) -> IbkrContractSpec:
    asset_class = AssetClass(config["asset_class"])
    sec_type_default = {
        AssetClass.STOCK: "STK",
        AssetClass.ETF: "STK",
        AssetClass.FOREX: "CASH",
        AssetClass.OPTION: "OPT",
        AssetClass.FUTURE: "FUT",
        AssetClass.COMMODITY: "FUT",
    }.get(asset_class, "STK")
    return IbkrContractSpec(
        symbol=config["symbol"],
        asset_class=asset_class,
        sec_type=str(config.get("sec_type", sec_type_default)).upper(),
        exchange=str(config.get("exchange", "SMART")),
        currency=str(config.get("currency", "USD")),
        primary_exchange=str(config.get("primary_exchange", "")),
        last_trade_date_or_contract_month=str(
            config.get("last_trade_date_or_contract_month", "")
        ),
        strike=float(config.get("strike", 0.0)),
        right=str(config.get("right", "")),
        multiplier=str(config.get("multiplier", "")),
        local_symbol=str(config.get("local_symbol", "")),
        trading_class=str(config.get("trading_class", "")),
    )


def _build_risk_manager(config: Dict[str, Any]) -> RiskManager:
    risk_config = config["risk"]
    return RiskManager(
        RiskLimits(
            max_position_size=float(risk_config["max_position_size"]),
            max_notional_per_trade=float(risk_config["max_notional_per_trade"]),
        )
    )


class IbkrClient:
    def __init__(
        self,
        broker_config: Dict[str, Any],
        market_data_config: Dict[str, Any],
        *,
        readonly: bool = True,
    ):
        load_dotenv()
        ib = _import_ib()
        host = broker_config.get("host") or os.getenv("IBKR_HOST", "127.0.0.1")
        port = int(
            broker_config.get(
                "port",
                os.getenv(
                    "IBKR_PORT_PAPER" if bool(broker_config.get("paper", True)) else "IBKR_PORT_LIVE",
                    IBKR_PAPER_PORT if bool(broker_config.get("paper", True)) else IBKR_LIVE_PORT,
                ),
            )
        )
        client_id = int(broker_config.get("client_id", os.getenv("IBKR_CLIENT_ID", 1)))
        account = str(broker_config.get("account", os.getenv("IBKR_ACCOUNT", "")))
        self._bar_size = market_data_config.get("bar_size", "1 min")
        self._duration = market_data_config.get("duration", "2 D")
        self._use_rth = bool(market_data_config.get("use_rth", False))
        self._account = account
        self._ib = ib["IB"]()
        try:
            self._ib.connect(host, port, clientId=client_id, readonly=readonly, timeout=8)
        except Exception as error:
            raise IbkrTradingError(
                f"Unable to connect to IBKR at {host}:{port}. Start TWS or IB Gateway and ensure API access is enabled."
            ) from error
        self._ib.reqMarketDataType(int(market_data_config.get("market_data_type", 1)))
        self._classes = ib

    def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()

    def _contract_from_spec(self, spec: IbkrContractSpec) -> Any:
        Contract = self._classes["Contract"]
        if spec.sec_type == "STK":
            contract = self._classes["Stock"](
                spec.symbol,
                spec.exchange,
                spec.currency,
                primaryExchange=spec.primary_exchange or None,
            )
        elif spec.sec_type == "CASH":
            pair = spec.symbol if "/" in spec.symbol else f"{spec.symbol[:3]}/{spec.symbol[3:]}"
            contract = self._classes["Forex"](pair, exchange=spec.exchange)
        elif spec.sec_type == "OPT":
            contract = self._classes["Option"](
                spec.symbol,
                spec.last_trade_date_or_contract_month,
                spec.strike,
                spec.right,
                spec.exchange,
                multiplier=spec.multiplier or "100",
                currency=spec.currency,
                tradingClass=spec.trading_class or None,
            )
        elif spec.sec_type == "FUT":
            contract = self._classes["Future"](
                spec.symbol,
                spec.last_trade_date_or_contract_month,
                spec.exchange,
                currency=spec.currency,
                multiplier=spec.multiplier or None,
                tradingClass=spec.trading_class or None,
                localSymbol=spec.local_symbol or None,
            )
        else:
            contract = Contract(
                symbol=spec.symbol,
                secType=spec.sec_type,
                exchange=spec.exchange,
                currency=spec.currency,
                localSymbol=spec.local_symbol or None,
                lastTradeDateOrContractMonth=spec.last_trade_date_or_contract_month or None,
                strike=spec.strike or None,
                right=spec.right or None,
                multiplier=spec.multiplier or None,
                tradingClass=spec.trading_class or None,
                primaryExchange=spec.primary_exchange or None,
            )
        return contract

    def qualify(self, specs: Iterable[IbkrContractSpec]) -> Dict[str, Any]:
        contract_map: Dict[str, Any] = {}
        raw_contracts = [self._contract_from_spec(spec) for spec in specs]
        try:
            qualified = self._ib.qualifyContracts(*raw_contracts)
        except Exception as error:
            raise IbkrTradingError(f"IBKR contract qualification failed: {error}") from error
        for spec, contract in zip(specs, qualified):
            contract_map[spec.symbol] = contract
        return contract_map

    def get_account_summary(self) -> Dict[str, float]:
        values = self._ib.accountSummary(self._account or "")
        summary: Dict[str, float] = {}
        for item in values:
            try:
                summary[item.tag] = float(item.value)
            except (TypeError, ValueError):
                continue
        return summary

    def get_positions(
        self,
        specs: Dict[str, IbkrContractSpec],
        contracts: Dict[str, Any],
    ) -> Dict[str, Position]:
        positions: Dict[str, Position] = {}
        for position in self._ib.positions(self._account or ""):
            symbol = self._match_contract_to_symbol(position.contract, specs, contracts)
            if symbol is None:
                continue
            spec = specs[symbol]
            positions[symbol] = Position(
                instrument=Instrument(symbol=symbol, asset_class=spec.asset_class),
                quantity=max(float(position.position), 0.0),
                average_price=float(position.avgCost),
            )
        return positions

    def get_candles(
        self,
        specs: Dict[str, IbkrContractSpec],
        contracts: Dict[str, Any],
        limit: int,
    ) -> Dict[str, List[Candle]]:
        candles_by_symbol: Dict[str, List[Candle]] = {}
        for symbol, spec in specs.items():
            contract = contracts[symbol]
            what_to_show = "MIDPOINT" if spec.sec_type == "CASH" else "TRADES"
            bars = self._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=self._duration,
                barSizeSetting=self._bar_size,
                whatToShow=what_to_show,
                useRTH=self._use_rth,
                formatDate=1,
            )
            parsed = []
            for bar in bars[-limit:]:
                date_value = bar.date
                if isinstance(date_value, datetime):
                    timestamp = date_value.astimezone(timezone.utc)
                else:
                    timestamp = datetime.strptime(str(date_value), "%Y%m%d  %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                parsed.append(
                    Candle(
                        instrument=Instrument(symbol=symbol, asset_class=spec.asset_class),
                        timestamp=timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=float(getattr(bar, "volume", 0.0)),
                    )
                )
            candles_by_symbol[symbol] = parsed
        return candles_by_symbol

    def submit_order(self, contract: Any, side: OrderSide, quantity: float) -> Tuple[str, str]:
        MarketOrder = self._classes["MarketOrder"]
        order = MarketOrder(side.value.upper(), quantity)
        trade = self._ib.placeOrder(contract, order)
        self._ib.sleep(1)
        order_id = str(getattr(order, "orderId", "") or getattr(trade.order, "orderId", ""))
        status = getattr(trade.orderStatus, "status", "submitted")
        return order_id, status

    def recent_fills(
        self,
        specs: Dict[str, IbkrContractSpec],
        contracts: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        fills = []
        for fill in self._ib.fills()[-20:]:
            symbol = self._match_contract_to_symbol(fill.contract, specs, contracts)
            if symbol is None:
                continue
            spec = specs[symbol]
            fills.append(
                {
                    "symbol": symbol,
                    "asset_class": spec.asset_class.value,
                    "side": "buy" if fill.execution.side.upper() == "BOT" else "sell",
                    "quantity": float(fill.execution.shares),
                    "price": float(fill.execution.price),
                    "commission": 0.0,
                    "time": _to_timestamp(fill.execution.time.replace(tzinfo=timezone.utc)),
                }
            )
        return list(reversed(fills))

    @staticmethod
    def _match_contract_to_symbol(
        contract: Any,
        specs: Dict[str, IbkrContractSpec],
        contracts: Dict[str, Any],
    ) -> Optional[str]:
        for symbol, qualified in contracts.items():
            if getattr(contract, "conId", None) and getattr(qualified, "conId", None):
                if contract.conId == qualified.conId:
                    return symbol
        for symbol, spec in specs.items():
            if getattr(contract, "symbol", "") != spec.symbol:
                continue
            if spec.last_trade_date_or_contract_month and getattr(
                contract, "lastTradeDateOrContractMonth", ""
            ) != spec.last_trade_date_or_contract_month:
                continue
            if spec.sec_type and getattr(contract, "secType", "") != spec.sec_type:
                continue
            if spec.sec_type == "OPT":
                if abs(float(getattr(contract, "strike", 0.0)) - spec.strike) > 1e-9:
                    continue
                if getattr(contract, "right", "") != spec.right:
                    continue
            return symbol
        return None


def build_ibkr_dashboard_payload(config_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    broker_config = config.get("broker", {})
    market_data_config = config["market_data"]
    specs = {
        spec.symbol: spec
        for spec in (_contract_spec_from_config(item) for item in market_data_config["instruments"])
    }
    client = IbkrClient(broker_config=broker_config, market_data_config=market_data_config, readonly=True)
    try:
        contracts = client.qualify(specs.values())
        strategy = build_strategy(config["strategy"])
        positions = client.get_positions(specs, contracts)
        summary = client.get_account_summary()
        history_limit = max(
            int(market_data_config.get("history_limit", 60)),
            int(config["strategy"]["long_window"]) + 2,
        )
        candles_by_symbol = client.get_candles(specs, contracts, history_limit)

        instrument_payloads: List[Dict[str, Any]] = []
        decisions: List[Dict[str, Any]] = []
        for symbol, spec in specs.items():
            candles = candles_by_symbol.get(symbol, [])
            if not candles:
                continue
            first_candle = candles[0]
            last_candle = candles[-1]
            position = positions.get(
                symbol,
                Position(
                    instrument=Instrument(symbol=symbol, asset_class=spec.asset_class),
                    quantity=0.0,
                    average_price=0.0,
                ),
            )
            decision = strategy.evaluate(candles, position)
            last_signal = None
            if decision.signal != Signal.HOLD:
                last_signal = {
                    "symbol": symbol,
                    "asset_class": spec.asset_class.value,
                    "signal": decision.signal.value,
                    "status": "preview",
                    "quantity": decision.quantity,
                    "price": last_candle.close,
                    "reason": decision.reason,
                    "detail": "IBKR dashboard preview only; no order placed.",
                    "time": _to_timestamp(last_candle.timestamp),
                }
                decisions.append(last_signal)

            price_change = last_candle.close - first_candle.open
            change_pct = (price_change / first_candle.open) * 100 if first_candle.open else 0.0
            stance = "long" if position.quantity > 0 else "flat"
            instrument_payloads.append(
                {
                    "symbol": symbol,
                    "asset_class": spec.asset_class.value,
                    "latest_price": last_candle.close,
                    "price_change": price_change,
                    "change_pct": change_pct,
                    "position": {
                        "symbol": symbol,
                        "asset_class": spec.asset_class.value,
                        "quantity": position.quantity,
                        "average_price": position.average_price,
                        "last_price": last_candle.close,
                        "market_value": position.quantity * last_candle.close,
                    },
                    "last_signal": last_signal,
                    "analysis_summary": (
                        f"The bot is {stance} on {symbol}. Latest IBKR signal: "
                        f"{decision.signal.value.upper()} because {decision.reason}."
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
        net_liquidation = float(summary.get("NetLiquidation", 0.0))
        total_cash = float(summary.get("TotalCashValue", net_liquidation))
        pnl = float(summary.get("UnrealizedPnL", 0.0))
        return_pct = (pnl / total_cash * 100) if total_cash else 0.0
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
                "starting_cash": total_cash,
                "ending_cash": total_cash,
                "ending_equity": net_liquidation,
                "pnl": pnl,
                "return_pct": return_pct,
                "fill_count": len(client.recent_fills(specs, contracts)),
                "open_position_count": len(open_positions),
            },
            "bot_summary": instrument_payloads[0]["analysis_summary"] if instrument_payloads else "",
            "instruments": instrument_payloads,
            "fills": client.recent_fills(specs, contracts),
            "decisions": decisions,
            "open_positions": open_positions,
            "live_mode": True,
            "execute_orders": bool(config.get("live", {}).get("execute_orders", False)),
        }
    finally:
        client.disconnect()


def run_ibkr_live_trading(
    config_path: str,
    *,
    iterations: int = 0,
    poll_seconds: Optional[int] = None,
) -> int:
    config = load_config(config_path)
    broker_config = config.get("broker", {})
    market_data_config = config["market_data"]
    live_config = config.get("live", {})
    execute_orders = bool(live_config.get("execute_orders", False))
    poll_interval = int(poll_seconds or live_config.get("poll_seconds", 60))
    specs = {
        spec.symbol: spec
        for spec in (_contract_spec_from_config(item) for item in market_data_config["instruments"])
    }
    try:
        client = IbkrClient(
            broker_config=broker_config,
            market_data_config=market_data_config,
            readonly=not execute_orders,
        )
    except IbkrTradingError as error:
        print(f"IBKR setup error: {error}")
        return 1

    try:
        contracts = client.qualify(specs.values())
        strategy = build_strategy(config["strategy"])
        risk_manager = _build_risk_manager(config)
        history_limit = max(
            int(market_data_config.get("history_limit", 60)),
            int(config["strategy"]["long_window"]) + 2,
        )

        iteration = 0
        while True:
            iteration += 1
            positions = client.get_positions(specs, contracts)
            candles_by_symbol = client.get_candles(specs, contracts, history_limit)
            cycle_results: List[IbkrDecisionResult] = []

            for symbol, spec in specs.items():
                candles = candles_by_symbol.get(symbol, [])
                if len(candles) < int(config["strategy"]["long_window"]):
                    cycle_results.append(
                        IbkrDecisionResult(
                            symbol=symbol,
                            asset_class=spec.asset_class.value,
                            signal="hold",
                            status="skipped",
                            quantity=0.0,
                            reference_price=candles[-1].close if candles else 0.0,
                            reason="not enough market history yet",
                        )
                    )
                    continue

                position = positions.get(
                    symbol,
                    Position(
                        instrument=Instrument(symbol=symbol, asset_class=spec.asset_class),
                        quantity=0.0,
                        average_price=0.0,
                    ),
                )
                decision = strategy.evaluate(candles, position)
                latest_price = candles[-1].close
                if decision.signal == Signal.HOLD:
                    cycle_results.append(
                        IbkrDecisionResult(
                            symbol=symbol,
                            asset_class=spec.asset_class.value,
                            signal="hold",
                            status="skipped",
                            quantity=0.0,
                            reference_price=latest_price,
                            reason=decision.reason,
                        )
                    )
                    continue

                order = OrderRequest(
                    instrument=Instrument(symbol=symbol, asset_class=spec.asset_class),
                    side=OrderSide(decision.signal.value),
                    quantity=decision.quantity,
                    price=latest_price,
                )
                try:
                    risk_manager.approve(order, current_position_size=position.quantity)
                except ValueError as error:
                    cycle_results.append(
                        IbkrDecisionResult(
                            symbol=symbol,
                            asset_class=spec.asset_class.value,
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
                        IbkrDecisionResult(
                            symbol=symbol,
                            asset_class=spec.asset_class.value,
                            signal=decision.signal.value,
                            status="preview",
                            quantity=decision.quantity,
                            reference_price=latest_price,
                            reason=decision.reason,
                            detail="Live execution disabled. Set live.execute_orders to true to place orders.",
                        )
                    )
                    continue

                order_id, status = client.submit_order(
                    contracts[symbol],
                    OrderSide(decision.signal.value),
                    decision.quantity,
                )
                cycle_results.append(
                    IbkrDecisionResult(
                        symbol=symbol,
                        asset_class=spec.asset_class.value,
                        signal=decision.signal.value,
                        status=status,
                        quantity=decision.quantity,
                        reference_price=latest_price,
                        reason=decision.reason,
                        detail="Order submitted to IBKR.",
                        order_id=order_id,
                    )
                )

            print(f"\nIBKR live cycle {iteration} at {_utc_now().isoformat()}")
            for result in cycle_results:
                suffix = f" ({result.detail})" if result.detail else ""
                print(
                    f"- {result.symbol}: {result.signal.upper()} {result.quantity} @ "
                    f"{result.reference_price:.2f} -> {result.status}{suffix}"
                )

            if iterations and iteration >= iterations:
                break
            if poll_interval <= 0:
                break
            time.sleep(poll_interval)

        return 0
    except IbkrTradingError as error:
        print(f"IBKR setup error: {error}")
        return 1
    finally:
        client.disconnect()
