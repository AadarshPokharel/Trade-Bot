import unittest

from trade_bot.live import _alpaca_symbol, _normalize_crypto_symbol
from trade_bot.models import AssetClass


class LiveHelperTests(unittest.TestCase):
    def test_crypto_symbol_is_normalized_for_alpaca(self) -> None:
        self.assertEqual(_normalize_crypto_symbol("BTCUSD"), "BTC/USD")
        self.assertEqual(_alpaca_symbol("ETHUSDT", AssetClass.CRYPTO), "ETH/USDT")

    def test_non_crypto_symbol_is_left_alone(self) -> None:
        self.assertEqual(_alpaca_symbol("AAPL", AssetClass.STOCK), "AAPL")


if __name__ == "__main__":
    unittest.main()
