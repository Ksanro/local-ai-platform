"""Configuration management for Local AI Platform."""

import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATHS = [
    Path(os.environ.get("CONFIG_DIR", Path(__file__).parent)),
    Path(os.getcwd()),
]


def load_config(filename: str = "config.yaml") -> dict[str, Any]:
    """Load configuration from YAML file.

    Searches multiple directories for the config file.
    Falls back to empty dict if not found.
    """
    for config_dir in _CONFIG_PATHS:
        config_file = config_dir / filename
        if config_file.exists():
            with open(config_file, "r") as f:
                return yaml.safe_load(f) or {}
    return {}


def get_env_or_config(key: str, default: Any = None, config: dict[str, Any] | None = None) -> Any:
    """Get value from environment variables or config dict.

    Priority: environment variable > config file > default.
    """
    env_value = os.environ.get(key)
    if env_value is not None:
        return env_value

    if config is not None and key in config:
        return config[key]

    return default