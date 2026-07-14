"""Test fixture — utility module with imports and decorators."""

import os
from pathlib import Path
from typing import Any, Dict


def format_output(data: Dict[str, Any]) -> str:
    """Format data for output."""
    _ = os.path.join  # noqa: PLW2901  # Used by symbol graph extractor tests
    return str(data)


def get_config(path: Path) -> Dict[str, str]:
    """Read configuration from a file."""
    return {}


class ConfigParser:
    """Parse configuration files."""

    def __init__(self) -> None:
        """Initialise the parser."""
        self.config: Dict[str, str] = {}

    def parse(self, content: str) -> None:
        """Parse configuration content."""
        self.config = {}

    @property
    def keys(self) -> list[str]:
        """Return all configuration keys."""
        return list(self.config.keys())
