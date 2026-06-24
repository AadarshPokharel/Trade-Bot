from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, Iterable, List

from trade_bot.data.base import MarketDataFeed
from trade_bot.models import AssetClass, Candle, Instrument


class SyntheticMarketDataFeed(MarketDataFeed):
    def __init__(self, instrument_configs: List[dict], length: int, seed: int = 0):
        self._rng = random.Random(seed)
        self._series: Dict[str, List[Candle]] = {}
        self._build_series(instrument_configs=instrument_configs, length=length)

    def _build_series(self, instrument_configs: List[dict], length: int) -> None:
        base_time = datetime.utcnow() - timedelta(minutes=length)
        for config in instrument_configs:
            instrument = Instrument(
                symbol=config["symbol"],
                asset_class=AssetClass(config["asset_class"]),
            )
            price = float(config["base_price"])
            volatility = float(config.get("volatility", 0.01))
            candles: List[Candle] = []
            for index in range(length):
                drift = self._rng.uniform(-volatility, volatility)
                next_price = max(price * (1 + drift), 0.01)
                high = max(price, next_price) * (1 + abs(drift) * 0.4)
                low = min(price, next_price) * (1 - abs(drift) * 0.4)
                candles.append(
                    Candle(
                        instrument=instrument,
                        timestamp=base_time + timedelta(minutes=index),
                        open=round(price, 4),
                        high=round(high, 4),
                        low=round(low, 4),
                        close=round(next_price, 4),
                        volume=round(self._rng.uniform(100, 10000), 2),
                    )
                )
                price = next_price
            self._series[instrument.symbol] = candles

    def stream(self) -> Iterable[Dict[str, Candle]]:
        if not self._series:
            return
        length = len(next(iter(self._series.values())))
        symbols = list(self._series.keys())
        for index in range(length):
            yield {symbol: self._series[symbol][index] for symbol in symbols}

    def history(self) -> Dict[str, List[Candle]]:
        return {symbol: list(candles) for symbol, candles in self._series.items()}
