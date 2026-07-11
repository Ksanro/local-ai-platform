"""Structured logging setup.

Configures the root logger with a consistent format and writes
log output to stdout for containerized environments.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Sets up the root logger with a timestamp, logger name, level,
    and message format. Output is directed to stdout.

    Args:
        level: The logging level string (e.g. ``"DEBUG"``, ``"INFO"``,
            ``"WARNING"``, ``"ERROR"``). Defaults to ``"INFO"``.
    """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
    )


