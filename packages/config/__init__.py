"""Configuration management for Local AI Platform.

Provides utilities for loading YAML configuration files from multiple
search paths and resolving environment variable overrides.
"""

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

    Searches multiple directories for the config file in order:
    the directory containing this module, then the current working
    directory. Falls back to an empty dict if not found.

    Args:
        filename: Name of the YAML config file to load.
            Defaults to ``"config.yaml"``.

    Returns:
        Parsed config dict, or empty dict if file not found.
    """
    for config_dir in _CONFIG_PATHS:
        config_file = config_dir / filename
        if config_file.exists():
            with open(config_file, "r") as f:
                return yaml.safe_load(f) or {}
    return {}


def get_env_or_config(
    key: str,
    default: Any = None,
    config: dict[str, Any] | None = None,
) -> Any:
    """Get value from environment variables or config dict.

    Priority order: environment variable > config file value > default.

    Args:
        key: The environment variable or config key to look up.
        default: Value to return if neither env var nor config has the key.
        config: Optional config dict to search. If ``None``, only the
            environment variable is checked.

    Returns:
        The resolved value, or ``default`` if not found.
    """
    env_value = os.environ.get(key)
    if env_value is not None:
        return env_value

    if config is not None and key in config:
        return config[key]

    return default