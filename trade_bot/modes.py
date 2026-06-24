from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


MODE_PRESETS = {
    "demo": {
        "label": "Demo Mode",
        "description": "Synthetic candles with simulated fills.",
        "config_path": "config/demo.json",
    },
    "paper": {
        "label": "Paper Mode",
        "description": "Real Alpaca market data with paper-trading execution.",
        "config_path": "config/alpaca_paper.json",
    },
    "live": {
        "label": "Live Mode",
        "description": "Real Alpaca market data with real account access.",
        "config_path": "config/alpaca_live.json",
    },
}


def mode_for_config(config: Dict[str, Any]) -> str:
    broker = config.get("broker", {})
    if broker.get("type"):
        return "paper" if bool(broker.get("paper", True)) else "live"
    return "demo"


def mode_label_for_config(config: Dict[str, Any]) -> str:
    mode = mode_for_config(config)
    if mode == "live" and not bool(config.get("live", {}).get("execute_orders", False)):
        return "Live Preview"
    return MODE_PRESETS[mode]["label"]


def resolve_mode_or_config(mode: str | None, config_path: str | None) -> str:
    if mode:
        preset = MODE_PRESETS.get(mode)
        if preset is None:
            raise ValueError(f"Unknown mode '{mode}'. Expected one of: {', '.join(sorted(MODE_PRESETS))}")
        return preset["config_path"]
    if config_path:
        return config_path
    return MODE_PRESETS["demo"]["config_path"]


def available_modes() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for mode_key, preset in MODE_PRESETS.items():
        results.append(
            {
                "key": mode_key,
                "label": preset["label"],
                "description": preset["description"],
                "config_path": preset["config_path"],
                "available": Path(preset["config_path"]).exists(),
            }
        )
    return results
