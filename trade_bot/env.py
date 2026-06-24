from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def load_dotenv(filenames: Iterable[str] = (".env", ".env.local")) -> None:
    """Load simple KEY=VALUE pairs from local dotenv files if present."""
    root = Path.cwd()
    for filename in filenames:
        dotenv_path = root / filename
        if not dotenv_path.exists():
            continue
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)
