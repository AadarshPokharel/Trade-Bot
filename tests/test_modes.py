import unittest

from trade_bot.modes import mode_for_config, mode_label_for_config, resolve_mode_or_config


class ModeTests(unittest.TestCase):
    def test_demo_mode_is_detected(self) -> None:
        config = {}
        self.assertEqual(mode_for_config(config), "demo")
        self.assertEqual(mode_label_for_config(config), "Demo Mode")

    def test_paper_mode_is_detected(self) -> None:
        config = {"broker": {"type": "alpaca", "paper": True}, "live": {"execute_orders": False}}
        self.assertEqual(mode_for_config(config), "paper")
        self.assertEqual(mode_label_for_config(config), "Paper Mode")

    def test_oanda_is_also_treated_as_broker_backed_mode(self) -> None:
        config = {"broker": {"type": "oanda", "paper": True}, "live": {"execute_orders": False}}
        self.assertEqual(mode_for_config(config), "paper")
        self.assertEqual(mode_label_for_config(config), "Paper Mode")

    def test_live_preview_label_is_used_when_orders_disabled(self) -> None:
        config = {"broker": {"type": "alpaca", "paper": False}, "live": {"execute_orders": False}}
        self.assertEqual(mode_for_config(config), "live")
        self.assertEqual(mode_label_for_config(config), "Live Preview")

    def test_mode_resolution_uses_presets(self) -> None:
        self.assertEqual(resolve_mode_or_config("paper", None), "config/alpaca_paper.json")


if __name__ == "__main__":
    unittest.main()
