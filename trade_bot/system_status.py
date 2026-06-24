from __future__ import annotations

from typing import Any, Dict, Iterable, List


BROKER_LABELS = {
    "alpaca": "Alpaca",
    "oanda": "OANDA",
    "ibkr": "IBKR",
    "paper": "Demo Engine",
    "synthetic": "Demo Engine",
}


def _symbol_preview(symbols: List[str]) -> str:
    if not symbols:
        return "No symbols configured"
    visible = symbols[:3]
    preview = ", ".join(visible)
    hidden = len(symbols) - len(visible)
    if hidden > 0:
        return f"{preview} +{hidden} more"
    return preview


def _market_context(config: Dict[str, Any], market_data_type: str) -> str:
    market_data = config.get("market_data", {})
    if market_data_type == "alpaca":
        parts: List[str] = []
        stock_feed = str(market_data.get("stock_feed", "")).strip()
        crypto_loc = str(market_data.get("crypto_loc", "")).strip()
        history_limit = market_data.get("history_limit")
        if stock_feed:
            parts.append(stock_feed.upper())
        if crypto_loc:
            parts.append(f"{crypto_loc.upper()} crypto")
        if history_limit:
            parts.append(f"{history_limit} bars")
        return " · ".join(parts) or "Broker market data"
    if market_data_type == "oanda":
        granularity = str(market_data.get("granularity", "M1")).strip()
        history_limit = market_data.get("history_limit")
        parts = [granularity] if granularity else []
        if history_limit:
            parts.append(f"{history_limit} candles")
        return " · ".join(parts) or "Forex market data"
    if market_data_type == "ibkr":
        parts = []
        bar_size = str(market_data.get("bar_size", "")).strip()
        duration = str(market_data.get("duration", "")).strip()
        if bar_size:
            parts.append(bar_size)
        if duration:
            parts.append(duration)
        return " · ".join(parts) or "Broker market data"

    length = market_data.get("length")
    seed = market_data.get("seed")
    parts = []
    if length:
        parts.append(f"{length} synthetic bars")
    if seed is not None:
        parts.append(f"seed {seed}")
    return " · ".join(parts) or "Synthetic market data"


def _execution_label(*, live_mode: bool, paper_trading: bool, execute_orders: bool) -> str:
    if not live_mode:
        return "Simulation"
    if execute_orders and paper_trading:
        return "Paper Armed"
    if execute_orders and not paper_trading:
        return "Live Armed"
    if not execute_orders and paper_trading:
        return "Paper Preview"
    return "Live Preview"


def build_system_status(
    config: Dict[str, Any],
    *,
    live_mode: bool,
    paper_trading: bool,
    execute_orders: bool,
    supports_news: bool = False,
    news_provider: str = "",
) -> Dict[str, Any]:
    broker_type = str(config.get("broker", {}).get("type", "")).strip().lower()
    market_data_type = str(config.get("market_data", {}).get("type", "")).strip().lower()
    provider_key = broker_type or market_data_type or "paper"
    symbols = [
        str(instrument.get("symbol", "")).strip()
        for instrument in config.get("market_data", {}).get("instruments", [])
        if str(instrument.get("symbol", "")).strip()
    ]
    return {
        "broker_type": broker_type or "paper",
        "broker_label": BROKER_LABELS.get(provider_key, provider_key.upper()),
        "market_data_type": market_data_type or "synthetic",
        "market_context": _market_context(config, market_data_type or "synthetic"),
        "execution_label": _execution_label(
            live_mode=live_mode,
            paper_trading=paper_trading,
            execute_orders=execute_orders,
        ),
        "paper_trading": paper_trading,
        "live_mode": live_mode,
        "execute_orders": execute_orders,
        "poll_seconds": config.get("live", {}).get("poll_seconds"),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "symbols_preview": _symbol_preview(symbols),
        "supports_news": supports_news,
        "news_provider": news_provider,
        "strategy_name": str(config.get("strategy", {}).get("name", "")).strip(),
    }
