import unittest

from trade_bot.dashboard import build_dashboard_payload


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_payload_contains_chart_ready_instruments(self) -> None:
        payload = build_dashboard_payload("config/demo.json")

        self.assertTrue(payload["paper_trading"])
        self.assertGreater(len(payload["instruments"]), 0)
        instrument = payload["instruments"][0]
        self.assertIn("analysis_summary", instrument)
        self.assertGreater(len(instrument["candles"]), 0)
        self.assertIn("metrics", payload)


if __name__ == "__main__":
    unittest.main()
