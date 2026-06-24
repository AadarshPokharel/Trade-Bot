from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
