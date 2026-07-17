"""Importer module fixture for benchmark testing."""

from __future__ import annotations

from tests.fixtures.repositories.imports.imported import ImportedClass, format_value, parse_value


class DataImporter:
    """Imports and manages data using ImportedClass.

    Coordinates data import operations by using ImportedClass
    for transformations and format_value for formatting.
    """

    def __init__(self) -> None:
        """Initialize DataImporter."""
        self._imported = ImportedClass()
        self._import_log: list[dict[str, str]] = []

    def import_data(self, raw: str) -> dict[str, str]:
        """Import and parse raw data.

        Args:
            raw: The raw data string to import.

        Returns:
            A dictionary of parsed key-value pairs.
        """
        parsed = parse_value(raw)
        for key, value in parsed.items():
            transformed = self._imported.transform(value)
            self._import_log.append({"key": key, "transformed": transformed})
        return parsed

    def format_imported(self, key: str) -> str | None:
        """Format an imported value.

        Args:
            key: The key to look up.

        Returns:
            The formatted value, or None if not found.
        """
        cached = self._imported.retrieve(key)
        if cached is not None:
            return format_value(cached)
        return None

    def get_import_log(self) -> list[dict[str, str]]:
        """Get the import log.

        Returns:
            A copy of the import log.
        """
        return list(self._import_log)

    def clear_log(self) -> None:
        """Clear the import log and cache."""
        self._import_log.clear()
        self._imported.clear_cache()
