import unittest

from trade_bot.brokers import PaperBroker
from trade_bot.models import AssetClass, Instrument, OrderRequest, OrderSide


class PaperBrokerTests(unittest.TestCase):
    def test_buy_order_reduces_cash_and_updates_position(self) -> None:
        instrument = Instrument(symbol="SPY", asset_class=AssetClass.ETF)
        broker = PaperBroker(starting_cash=1000.0, commission_per_trade=1.0)

        fill = broker.submit_order(
            OrderRequest(
                instrument=instrument,
                side=OrderSide.BUY,
                quantity=1.0,
                price=100.0,
            )
        )

        portfolio = broker.get_portfolio()
        self.assertEqual(fill.price, 100.0)
        self.assertAlmostEqual(portfolio.cash, 899.0)
        self.assertAlmostEqual(portfolio.get_position(instrument).quantity, 1.0)


if __name__ == "__main__":
    unittest.main()
