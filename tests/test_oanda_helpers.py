import unittest

from trade_bot.oanda import _normalize_units, _oanda_symbol


class OandaHelperTests(unittest.TestCase):
    def test_forex_symbol_is_normalized_for_oanda(self) -> None:
        self.assertEqual(_oanda_symbol("EURUSD"), "EUR_USD")
        self.assertEqual(_oanda_symbol("USD_JPY"), "USD_JPY")

    def test_units_are_rounded_to_integer(self) -> None:
        self.assertEqual(_normalize_units(1000.4), 1000)
        self.assertEqual(_normalize_units(999.6), 1000)


if __name__ == "__main__":
    unittest.main()
