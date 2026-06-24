import unittest

from trade_bot.live import (
    _alpaca_symbol,
    _group_news_by_symbol,
    _normalize_crypto_symbol,
    _normalize_news_item,
    _select_news_image,
)
from trade_bot.models import AssetClass
from trade_bot.models import Instrument


class LiveHelperTests(unittest.TestCase):
    def test_crypto_symbol_is_normalized_for_alpaca(self) -> None:
        self.assertEqual(_normalize_crypto_symbol("BTCUSD"), "BTC/USD")
        self.assertEqual(_alpaca_symbol("ETHUSDT", AssetClass.CRYPTO), "ETH/USDT")

    def test_non_crypto_symbol_is_left_alone(self) -> None:
        self.assertEqual(_alpaca_symbol("AAPL", AssetClass.STOCK), "AAPL")

    def test_news_image_prefers_thumb_then_first_available(self) -> None:
        self.assertEqual(
            _select_news_image(
                [
                    {"size": "large", "url": "https://example.com/large.png"},
                    {"size": "thumb", "url": "https://example.com/thumb.png"},
                ]
            ),
            "https://example.com/thumb.png",
        )

    def test_news_item_is_normalized(self) -> None:
        article = _normalize_news_item(
            {
                "headline": "Apple moves on AI plan",
                "summary": "AAPL headlines stay active.",
                "source": "benzinga",
                "author": "Reporter",
                "url": "https://example.com/story",
                "created_at": "2026-06-24T19:31:27Z",
                "symbols": ["AAPL", "BTCUSD"],
                "images": [{"size": "small", "url": "https://example.com/small.png"}],
            }
        )
        self.assertEqual(article.related_symbols, ["AAPL", "BTCUSD"])
        self.assertEqual(article.image_url, "https://example.com/small.png")

    def test_news_is_grouped_per_instrument(self) -> None:
        news_item = _normalize_news_item(
            {
                "headline": "Bitcoin and Apple react",
                "summary": "Both symbols moved.",
                "source": "benzinga",
                "author": "Reporter",
                "url": "https://example.com/story",
                "created_at": "2026-06-24T19:31:27Z",
                "symbols": ["AAPL", "BTCUSD"],
            }
        )
        grouped = _group_news_by_symbol(
            [
                Instrument(symbol="AAPL", asset_class=AssetClass.STOCK),
                Instrument(symbol="BTCUSD", asset_class=AssetClass.CRYPTO),
            ],
            [news_item],
        )
        self.assertEqual(len(grouped["AAPL"]), 1)
        self.assertEqual(len(grouped["BTCUSD"]), 1)


if __name__ == "__main__":
    unittest.main()
