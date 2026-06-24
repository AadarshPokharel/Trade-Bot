import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trade_bot.env import load_dotenv


class DotenvLoaderTests(unittest.TestCase):
    def test_loads_values_from_dotenv_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text(
                "ALPACA_API_KEY=test_key\nALPACA_API_SECRET=test_secret\n",
                encoding="utf-8",
            )
            with patch("pathlib.Path.cwd", return_value=temp_path):
                with patch.dict(os.environ, {}, clear=True):
                    load_dotenv()
                    self.assertEqual(os.environ["ALPACA_API_KEY"], "test_key")
                    self.assertEqual(os.environ["ALPACA_API_SECRET"], "test_secret")


if __name__ == "__main__":
    unittest.main()
