from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trade_bot.config import load_config
from trade_bot.env import load_dotenv
from trade_bot.ibkr import build_ibkr_dashboard_payload, run_ibkr_live_trading
from trade_bot.modes import mode_for_config, mode_label_for_config
from trade_bot.oanda import build_oanda_dashboard_payload, run_oanda_live_trading
from trade_bot.models import (
    AssetClass,
    Candle,
    Instrument,
    OrderRequest,
    OrderSide,
    Position,
    Signal,
)
from trade_bot.risk import RiskLimits, RiskManager
from trade_bot.runtime import build_strategy


ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE_URL = "https://api.alpaca.markets"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"


class LiveTradingError(RuntimeError):
    """Raised when the live trading configuration or request fails."""


@dataclass(frozen=True)
class LiveDecisionResult:
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
class LiveNewsItem:
    headline: str
    summary: str
    source: str
    author: str
    url: str
    created_at: datetime
    related_symbols: List[str]
    image_url: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_timestamp(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _normalize_crypto_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    for suffix in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            base = symbol[: -len(suffix)]
            return f"{base}/{suffix}"
    return symbol


def _alpaca_symbol(symbol: str, asset_class: AssetClass) -> str:
    if asset_class == AssetClass.CRYPTO:
        return _normalize_crypto_symbol(symbol)
    return symbol


def _instrument_from_config(config: Dict[str, Any]) -> Instrument:
    return Instrument(
        symbol=config["symbol"],
        asset_class=AssetClass(config["asset_class"]),
    )


def _symbol_key(symbol: str) -> str:
    return symbol.replace("/", "").upper()


def _select_news_image(images: List[Dict[str, Any]]) -> str:
    preferred_sizes = ["thumb", "small", "large"]
    by_size = {str(image.get("size", "")).lower(): str(image.get("url", "")) for image in images}
    for size in preferred_sizes:
        if by_size.get(size):
            return by_size[size]
    for image in images:
        url = str(image.get("url", ""))
        if url:
            return url
    return ""


def _normalize_news_item(article: Dict[str, Any]) -> LiveNewsItem:
    created_at = article.get("created_at") or article.get("updated_at") or _utc_now().isoformat()
    raw_symbols = article.get("symbols") or []
    raw_images = article.get("images") or []
    related_symbols = sorted(
        {
            _symbol_key(str(symbol))
            for symbol in raw_symbols
            if str(symbol).strip()
        }
    )
    return LiveNewsItem(
        headline=str(article.get("headline", "")).strip(),
        summary=str(article.get("summary", "")).strip(),
        source=str(article.get("source", "")).strip(),
        author=str(article.get("author", "")).strip(),
        url=str(article.get("url", "")).strip(),
        created_at=_parse_timestamp(str(created_at)),
        related_symbols=related_symbols,
        image_url=_select_news_image(list(raw_images)),
    )


def _serialize_news_item(article: LiveNewsItem) -> Dict[str, Any]:
    return {
        "headline": article.headline,
        "summary": article.summary,
        "source": article.source,
        "author": article.author,
        "url": article.url,
        "time": _to_timestamp(article.created_at),
        "related_symbols": article.related_symbols,
        "image_url": article.image_url,
    }


def _group_news_by_symbol(
    instruments: Iterable[Instrument],
    articles: List[LiveNewsItem],
    *,
    per_symbol_limit: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for instrument in instruments:
        symbol_key = _symbol_key(instrument.symbol)
        grouped[instrument.symbol] = [
            _serialize_news_item(article)
            for article in articles
            if symbol_key in article.related_symbols
        ][:per_symbol_limit]
    return grouped


class AlpacaClient:
    def __init__(self, broker_config: Dict[str, Any], market_data_config: Dict[str, Any]):
        load_dotenv()
        api_key = os.getenv("ALPACA_API_KEY")
        api_secret = os.getenv("ALPACA_API_SECRET")
        if not api_key or not api_secret:
            raise LiveTradingError(
                "Missing Alpaca credentials. Add ALPACA_API_KEY and ALPACA_API_SECRET to your shell or .env file."
            )

        use_paper = bool(broker_config.get("paper", True))
        self._api_key = api_key
        self._api_secret = api_secret
        self._trading_base_url = broker_config.get(
            "trading_base_url",
            ALPACA_PAPER_BASE_URL if use_paper else ALPACA_LIVE_BASE_URL,
        ).rstrip("/")
        self._data_base_url = broker_config.get("data_base_url", ALPACA_DATA_BASE_URL).rstrip("/")
        self._stock_feed = market_data_config.get("stock_feed", "iex")
        self._crypto_loc = market_data_config.get("crypto_loc", "us")

    def _request_json(
        self,
        method: str,
        base_url: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        query = f"?{urlencode(params, doseq=True)}" if params else ""
        request = Request(
            f"{base_url}{path}{query}",
            method=method,
            headers={
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._api_secret,
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
            raise LiveTradingError(f"Alpaca API error {error.code}: {details}") from error
        except URLError as error:
            raise LiveTradingError(f"Unable to reach Alpaca API: {error}") from error

    def get_account(self) -> Dict[str, Any]:
        return self._request_json("GET", self._trading_base_url, "/v2/account")

    def list_positions(self) -> List[Dict[str, Any]]:
        return self._request_json("GET", self._trading_base_url, "/v2/positions")

    def list_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._request_json(
            "GET",
            self._trading_base_url,
            "/v2/orders",
            params={"status": "all", "direction": "desc", "limit": limit},
        )

    def submit_order(
        self,
        instrument: Instrument,
        side: OrderSide,
        quantity: float,
    ) -> Dict[str, Any]:
        alpaca_symbol = _alpaca_symbol(instrument.symbol, instrument.asset_class)
        time_in_force = "gtc" if instrument.asset_class == AssetClass.CRYPTO else "day"
        payload = {
            "symbol": alpaca_symbol,
            "side": side.value,
            "type": "market",
            "time_in_force": time_in_force,
        }
        payload["qty"] = str(quantity)
        return self._request_json("POST", self._trading_base_url, "/v2/orders", body=payload)

    def get_bars(
        self,
        instruments: Iterable[Instrument],
        limit: int,
        timeframe: str = "1Min",
    ) -> Dict[str, List[Candle]]:
        grouped: Dict[AssetClass, List[Instrument]] = {}
        for instrument in instruments:
            grouped.setdefault(instrument.asset_class, []).append(instrument)

        history: Dict[str, List[Candle]] = {}
        stock_like_assets = {AssetClass.STOCK, AssetClass.ETF}
        if any(asset_class in grouped for asset_class in stock_like_assets):
            stock_instruments = [
                instrument
                for asset_class in stock_like_assets
                for instrument in grouped.get(asset_class, [])
            ]
            history.update(
                self._fetch_stock_bars(
                    instruments=stock_instruments,
                    limit=limit,
                    timeframe=timeframe,
                )
            )

        if AssetClass.CRYPTO in grouped:
            crypto_instruments = grouped[AssetClass.CRYPTO]
            history.update(
                self._fetch_crypto_bars(
                    instruments=crypto_instruments,
                    limit=limit,
                    timeframe=timeframe,
                )
            )

        unsupported = [
            asset_class.value
            for asset_class in grouped
            if asset_class not in stock_like_assets and asset_class != AssetClass.CRYPTO
        ]
        if unsupported:
            raise LiveTradingError(
                "Live Alpaca mode currently supports stocks, ETFs, and crypto only. "
                f"Unsupported asset classes: {', '.join(sorted(unsupported))}"
            )
        return history

    def get_news(
        self,
        instruments: Iterable[Instrument],
        *,
        limit: int = 12,
    ) -> List[LiveNewsItem]:
        symbols = sorted({_symbol_key(_alpaca_symbol(item.symbol, item.asset_class)) for item in instruments})
        if not symbols:
            return []
        payload = self._request_json(
            "GET",
            self._data_base_url,
            "/v1beta1/news",
            params={
                "symbols": ",".join(symbols),
                "limit": max(1, min(limit, 50)),
                "sort": "desc",
            },
        )
        return [_normalize_news_item(article) for article in payload.get("news", [])]

    def _fetch_stock_bars(
        self,
        instruments: List[Instrument],
        limit: int,
        timeframe: str,
    ) -> Dict[str, List[Candle]]:
        symbols = [_alpaca_symbol(instrument.symbol, instrument.asset_class) for instrument in instruments]
        symbol_map = {
            _alpaca_symbol(instrument.symbol, instrument.asset_class): instrument
            for instrument in instruments
        }
        end_time = _utc_now()
        start_time = end_time - timedelta(minutes=max(limit * 4, 120))
        payload = self._request_json(
            "GET",
            self._data_base_url,
            "/v2/stocks/bars",
            params={
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "limit": limit,
                "start": _isoformat(start_time),
                "end": _isoformat(end_time),
                "feed": self._stock_feed,
            },
        )
        bars_by_symbol = payload.get("bars", {})
        return {
            symbol.replace("/", ""): self._parse_bars(symbol_map[symbol], bars)
            for symbol, bars in bars_by_symbol.items()
        }

    def _fetch_crypto_bars(
        self,
        instruments: List[Instrument],
        limit: int,
        timeframe: str,
    ) -> Dict[str, List[Candle]]:
        symbols = [_alpaca_symbol(instrument.symbol, instrument.asset_class) for instrument in instruments]
        symbol_map = {
            _alpaca_symbol(instrument.symbol, instrument.asset_class): instrument
            for instrument in instruments
        }
        end_time = _utc_now()
        start_time = end_time - timedelta(minutes=max(limit * 4, 120))
        payload = self._request_json(
            "GET",
            self._data_base_url,
            f"/v1beta3/crypto/{self._crypto_loc}/bars",
            params={
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "limit": limit,
                "start": _isoformat(start_time),
                "end": _isoformat(end_time),
            },
        )
        bars_by_symbol = payload.get("bars", {})
        return {
            symbol.replace("/", ""): self._parse_bars(symbol_map[symbol], bars)
            for symbol, bars in bars_by_symbol.items()
        }

    def _parse_bars(
        self,
        instrument: Instrument,
        bars: List[Dict[str, Any]],
    ) -> List[Candle]:
        parsed: List[Candle] = []
        for bar in bars:
            parsed.append(
                Candle(
                    instrument=instrument,
                    timestamp=_parse_timestamp(bar["t"]),
                    open=float(bar["o"]),
                    high=float(bar["h"]),
                    low=float(bar["l"]),
                    close=float(bar["c"]),
                    volume=float(bar.get("v", 0.0)),
                )
            )
        return parsed


def _build_risk_manager(config: Dict[str, Any]) -> RiskManager:
    risk_config = config["risk"]
    return RiskManager(
        RiskLimits(
            max_position_size=float(risk_config["max_position_size"]),
            max_notional_per_trade=float(risk_config["max_notional_per_trade"]),
        )
    )


def _position_map(
    client: AlpacaClient,
    expected_instruments: Dict[str, Instrument],
) -> Dict[str, Position]:
    positions: Dict[str, Position] = {}
    for raw_position in client.list_positions():
        symbol = raw_position["symbol"].replace("/", "")
        instrument = expected_instruments.get(
            symbol,
            Instrument(
                symbol=symbol,
                asset_class=AssetClass.CRYPTO if "/" in raw_position["symbol"] else AssetClass.STOCK,
            ),
        )
        quantity = float(raw_position["qty"])
        entry_price = float(raw_position.get("avg_entry_price", 0.0))
        positions[symbol] = Position(
            instrument=instrument,
            quantity=quantity,
            average_price=entry_price,
        )
    return positions


def build_live_dashboard_payload(config_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    broker_config = config.get("broker", {})
    if broker_config.get("type") == "oanda":
        return build_oanda_dashboard_payload(config_path)
    if broker_config.get("type") == "ibkr":
        return build_ibkr_dashboard_payload(config_path)

    market_data_config = config["market_data"]
    mode = mode_for_config(config)
    mode_label = mode_label_for_config(config)
    client = AlpacaClient(broker_config=broker_config, market_data_config=market_data_config)
    instruments = [_instrument_from_config(item) for item in market_data_config["instruments"]]
    instrument_map = {instrument.symbol: instrument for instrument in instruments}
    strategy = build_strategy(config["strategy"])
    positions = _position_map(client, instrument_map)
    account = client.get_account()
    history_limit = int(market_data_config.get("history_limit", 60))
    bars_by_symbol = client.get_bars(instruments=instruments, limit=history_limit)
    serialized_news: List[Dict[str, Any]] = []
    news_by_symbol: Dict[str, List[Dict[str, Any]]] = {instrument.symbol: [] for instrument in instruments}
    news_error = ""
    try:
        news_items = client.get_news(
            instruments=instruments,
            limit=int(market_data_config.get("news_limit", 12)),
        )
        serialized_news = [_serialize_news_item(article) for article in news_items]
        news_by_symbol = _group_news_by_symbol(instruments, news_items)
    except LiveTradingError as error:
        news_error = str(error)

    instrument_payloads: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    for instrument in instruments:
        candles = bars_by_symbol.get(instrument.symbol, [])
        if not candles:
            continue
        last_candle = candles[-1]
        first_candle = candles[0]
        position = positions.get(
            instrument.symbol,
            Position(instrument=instrument, quantity=0.0, average_price=0.0),
        )
        decision = strategy.evaluate(candles, position)
        last_signal_payload = None
        if decision.signal != Signal.HOLD:
            last_signal_payload = {
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
            decisions.append(last_signal_payload)

        price_change = last_candle.close - first_candle.open
        change_pct = (price_change / first_candle.open) * 100 if first_candle.open else 0.0
        stance = "long" if position.quantity > 0 else "flat"
        summary = (
            f"The bot is {stance} on {instrument.symbol}. "
            f"Latest live signal: {decision.signal.value.upper()} because {decision.reason}."
        )
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
                "last_signal": last_signal_payload,
                "analysis_summary": summary,
                "news": news_by_symbol.get(instrument.symbol, []),
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

    orders = client.list_orders(limit=20)
    fills = []
    latest_prices = {item["symbol"]: item["latest_price"] for item in instrument_payloads}
    for order in orders:
        if order.get("status") not in {"filled", "partially_filled"}:
            continue
        filled_at = order.get("filled_at") or order.get("updated_at") or order.get("submitted_at")
        fills.append(
            {
                "symbol": order["symbol"].replace("/", ""),
                "asset_class": "crypto" if "/" in order["symbol"] else "stock",
                "side": order["side"],
                "quantity": float(order.get("filled_qty") or order.get("qty") or 0.0),
                "price": float(order.get("filled_avg_price") or 0.0),
                "commission": 0.0,
                "time": _to_timestamp(_parse_timestamp(filled_at)),
            }
        )

    previous_equity = float(account.get("last_equity") or account.get("equity") or 0.0)
    current_equity = float(account.get("equity") or 0.0)
    return_pct = ((current_equity - previous_equity) / previous_equity * 100) if previous_equity else 0.0
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

    return {
        "generated_at": _utc_now().isoformat(),
        "paper_trading": bool(broker_config.get("paper", True)),
        "mode": mode,
        "mode_label": mode_label,
        "strategy": config["strategy"],
        "risk": config["risk"],
        "metrics": {
            "starting_cash": previous_equity,
            "ending_cash": float(account.get("cash") or 0.0),
            "ending_equity": current_equity,
            "pnl": current_equity - previous_equity,
            "return_pct": return_pct,
            "fill_count": len(fills),
            "open_position_count": len(open_positions),
        },
        "bot_summary": instrument_payloads[0]["analysis_summary"] if instrument_payloads else "",
        "instruments": instrument_payloads,
        "fills": fills[:20],
        "decisions": decisions,
        "open_positions": open_positions,
        "news": serialized_news,
        "news_error": news_error,
        "live_mode": True,
        "execute_orders": bool(config.get("live", {}).get("execute_orders", False)),
    }


def run_live_trading(
    config_path: str,
    *,
    iterations: int = 0,
    poll_seconds: Optional[int] = None,
) -> int:
    config = load_config(config_path)
    if config.get("broker", {}).get("type") == "oanda":
        return run_oanda_live_trading(
            config_path,
            iterations=iterations,
            poll_seconds=poll_seconds,
        )
    if config.get("broker", {}).get("type") == "ibkr":
        return run_ibkr_live_trading(
            config_path,
            iterations=iterations,
            poll_seconds=poll_seconds,
        )

    try:
        broker_config = config.get("broker", {})
        market_data_config = config["market_data"]
        live_config = config.get("live", {})
        execute_orders = bool(live_config.get("execute_orders", False))
        poll_interval = int(poll_seconds or live_config.get("poll_seconds", 60))

        client = AlpacaClient(broker_config=broker_config, market_data_config=market_data_config)
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
            bars_by_symbol = client.get_bars(instruments=instruments, limit=history_limit)
            cycle_results: List[LiveDecisionResult] = []

            for instrument in instruments:
                candles = bars_by_symbol.get(instrument.symbol, [])
                if len(candles) < int(config["strategy"]["long_window"]):
                    cycle_results.append(
                        LiveDecisionResult(
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
                        LiveDecisionResult(
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
                        LiveDecisionResult(
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
                        LiveDecisionResult(
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
                cycle_results.append(
                    LiveDecisionResult(
                        symbol=instrument.symbol,
                        asset_class=instrument.asset_class.value,
                        signal=decision.signal.value,
                        status=response.get("status", "submitted"),
                        quantity=float(response.get("qty") or decision.quantity),
                        reference_price=latest_price,
                        reason=decision.reason,
                        detail="Order submitted to Alpaca.",
                        order_id=response.get("id", ""),
                    )
                )

            print(f"\nLive cycle {iteration} at {_utc_now().isoformat()}")
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
    except LiveTradingError as error:
        print(f"Live trading setup error: {error}")
        return 1
