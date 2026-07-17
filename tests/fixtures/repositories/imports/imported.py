"""Imported module fixture for benchmark testing."""

from __future__ import annotations


class ImportedClass:
    """A class that is imported by other modules.

    Provides utility methods for data transformation
    and validation.
    """

    def __init__(self, prefix: str = "item") -> None:
        """Initialize ImportedClass.

        Args:
            prefix: The prefix for transformed values.
        """
        self.prefix = prefix
        self._cache: dict[str, str] = {}

    def transform(self, value: str) -> str:
        """Transform a value with the configured prefix.

        Args:
            value: The value to transform.

        Returns:
            The transformed value.
        """
        result = f"{self.prefix}:{value}"
        self._cache[value] = result
        return result

    def retrieve(self, key: str) -> str | None:
        """Retrieve a previously transformed value.

        Args:
            key: The original value used as lookup key.

        Returns:
            The transformed value, or None if not found.
        """
        return self._cache.get(key)

    def clear_cache(self) -> None:
        """Clear the transformation cache."""
        self._cache.clear()

    def has_cached(self, key: str) -> bool:
        """Check if a value is cached.

        Args:
            key: The lookup key.

        Returns:
            True if cached, False otherwise.
        """
        return key in self._cache


def format_value(value: str, separator: str = "-") -> str:
    """Format a value with a separator.

    Args:
        value: The value to format.
        separator: The separator character.

    Returns:
        The formatted value.
    """
    return separator.join(value.split())


def parse_value(raw: str) -> dict[str, str]:
    """Parse a raw string into a dictionary.

    Args:
        raw: The raw string to parse.

    Returns:
        A dictionary with parsed key-value pairs.
    """
    parts = raw.split(",")
    result: dict[str, str] = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()
    return result
