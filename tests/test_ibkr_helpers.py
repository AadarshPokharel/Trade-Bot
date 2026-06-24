import unittest

from trade_bot.ibkr import _contract_spec_from_config


class IbkrHelperTests(unittest.TestCase):
    def test_future_contract_spec_defaults(self) -> None:
        spec = _contract_spec_from_config(
            {
                "symbol": "ES",
                "asset_class": "future",
                "exchange": "CME",
                "currency": "USD",
                "last_trade_date_or_contract_month": "202612",
            }
        )
        self.assertEqual(spec.sec_type, "FUT")
        self.assertEqual(spec.symbol, "ES")

    def test_option_contract_spec_respects_right_and_strike(self) -> None:
        spec = _contract_spec_from_config(
            {
                "symbol": "AAPL",
                "asset_class": "option",
                "exchange": "SMART",
                "currency": "USD",
                "last_trade_date_or_contract_month": "20270115",
                "strike": 250,
                "right": "C",
            }
        )
        self.assertEqual(spec.sec_type, "OPT")
        self.assertEqual(spec.right, "C")
        self.assertEqual(spec.strike, 250.0)


if __name__ == "__main__":
    unittest.main()
