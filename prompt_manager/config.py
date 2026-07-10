"""Config file loader for prompt-manager."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "prompt_dir": str(Path.home() / ".config" / "prompt-manager" / "prompts"),
    "default_environment": "staging",
    "eval": {
        "auto_validate": True,
        "run_evalh": True,
    },
    "canary": {
        "default_weight": 10,
        "checks": 3,
        "interval_sec": 60,
        "metric": "error_rate < 0.05",
    },
}

_config: dict | None = None


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config
    config_path = Path.home() / ".config" / "prompt-manager" / "config.yaml"
    if config_path.exists():
        _config = {**DEFAULT_CONFIG, **yaml.safe_load(config_path.read_text() or {})}
    else:
        _config = dict(DEFAULT_CONFIG)
    return _config


def get(key: str, default=None):
    config = load_config()
    parts = key.split(".")
    val = config
    for p in parts:
        val = val.get(p, {})
    return val if val != {} else default
