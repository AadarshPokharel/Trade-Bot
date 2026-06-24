from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from trade_bot.config import load_config


DEFAULT_BROKER_FAMILY = "alpaca"
BROKER_MODE_CONFIGS = {
    "alpaca": {
        "paper": "config/alpaca_paper.json",
        "live": "config/alpaca_live.json",
    },
    "oanda": {
        "paper": "config/oanda_paper.json",
        "live": "config/oanda_live.json",
    },
    "ibkr": {
        "paper": "config/ibkr_paper.json",
        "live": "config/ibkr_live.json",
    },
}

MODE_PRESETS = {
    "demo": {
        "label": "Demo Mode",
        "description": "Synthetic candles with simulated fills.",
        "config_path": "config/demo.json",
    },
    "paper": {
        "label": "Paper Mode",
        "description": "Configured broker market data with paper or simulated execution.",
        "config_path": "config/alpaca_paper.json",
    },
    "live": {
        "label": "Live Mode",
        "description": "Configured broker market data with real account access.",
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


def _broker_family_from_config_path(config_path: str | None) -> str:
    if not config_path:
        return DEFAULT_BROKER_FAMILY
    try:
        broker_type = str(load_config(config_path).get("broker", {}).get("type", "")).lower()
    except Exception:
        return DEFAULT_BROKER_FAMILY
    if broker_type in BROKER_MODE_CONFIGS:
        return broker_type
    return DEFAULT_BROKER_FAMILY


def resolve_mode_or_config(mode: str | None, config_path: str | None) -> str:
    if mode:
        preset = MODE_PRESETS.get(mode)
        if preset is None:
            raise ValueError(f"Unknown mode '{mode}'. Expected one of: {', '.join(sorted(MODE_PRESETS))}")
        if mode == "demo":
            return preset["config_path"]
        broker_family = _broker_family_from_config_path(config_path)
        return BROKER_MODE_CONFIGS[broker_family][mode]
    if config_path:
        return config_path
    return MODE_PRESETS["demo"]["config_path"]


def available_modes(config_path: str | None = None) -> List[Dict[str, Any]]:
    broker_family = _broker_family_from_config_path(config_path)
    results: List[Dict[str, Any]] = []
    for mode_key, preset in MODE_PRESETS.items():
        resolved_path = preset["config_path"]
        if mode_key in {"paper", "live"}:
            resolved_path = BROKER_MODE_CONFIGS[broker_family][mode_key]
        results.append(
            {
                "key": mode_key,
                "label": preset["label"],
                "description": preset["description"],
                "config_path": resolved_path,
                "available": Path(resolved_path).exists(),
            }
        )
    return results
