import unittest

from trade_bot.dashboard import build_dashboard_payload
from trade_bot.system_status import build_system_status


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_payload_contains_chart_ready_instruments(self) -> None:
        payload = build_dashboard_payload("config/demo.json")

        self.assertTrue(payload["paper_trading"])
        self.assertGreater(len(payload["instruments"]), 0)
        instrument = payload["instruments"][0]
        self.assertIn("analysis_summary", instrument)
        self.assertGreater(len(instrument["candles"]), 0)
        self.assertIn("metrics", payload)
        self.assertEqual(payload["system_status"]["execution_label"], "Simulation")
        self.assertEqual(payload["system_status"]["symbol_count"], 3)

    def test_system_status_builds_live_preview_summary(self) -> None:
        status = build_system_status(
            {
                "broker": {"type": "alpaca", "paper": True},
                "market_data": {
                    "type": "alpaca",
                    "stock_feed": "iex",
                    "crypto_loc": "us",
                    "history_limit": 60,
                    "instruments": [
                        {"symbol": "AAPL"},
                        {"symbol": "BTCUSD"},
                    ],
                },
                "live": {"poll_seconds": 30},
                "strategy": {"name": "momentum"},
            },
            live_mode=True,
            paper_trading=True,
            execute_orders=False,
            supports_news=True,
            news_provider="alpaca",
        )
        self.assertEqual(status["broker_label"], "Alpaca")
        self.assertEqual(status["execution_label"], "Paper Preview")
        self.assertEqual(status["symbols_preview"], "AAPL, BTCUSD")
        self.assertTrue(status["supports_news"])


if __name__ == "__main__":
    unittest.main()
