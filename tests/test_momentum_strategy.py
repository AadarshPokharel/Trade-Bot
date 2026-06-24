import unittest
from datetime import datetime, timedelta

from trade_bot.models import AssetClass, Candle, Instrument, Position, Signal
from trade_bot.strategies import MomentumStrategy


class MomentumStrategyTests(unittest.TestCase):
    def test_buy_signal_when_short_average_exceeds_long_average(self) -> None:
        instrument = Instrument(symbol="BTCUSD", asset_class=AssetClass.CRYPTO)
        history = []
        prices = [100, 101, 102, 104, 106, 108]
        start = datetime(2024, 1, 1)
        for index, price in enumerate(prices):
            history.append(
                Candle(
                    instrument=instrument,
                    timestamp=start + timedelta(minutes=index),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=1000,
                )
            )

        strategy = MomentumStrategy(short_window=3, long_window=5, trade_quantity=1)
        decision = strategy.evaluate(history, Position(instrument=instrument))

        self.assertEqual(decision.signal, Signal.BUY)


if __name__ == "__main__":
    unittest.main()
