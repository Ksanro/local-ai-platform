"""Module A fixture for benchmark testing."""


class ServiceA:
    """A simple service class."""

    def __init__(self, name: str) -> None:
        """Initialize ServiceA."""
        self.name = name
        self._data: list[str] = []

    def process(self, item: str) -> str:
        """Process an item and store the result."""
        result = f"processed:{item}"
        self._data.append(result)
        return result

    def get_results(self) -> list[str]:
        """Return all processed results."""
        return list(self._data)

    def clear(self) -> None:
        """Clear all stored results."""
        self._data.clear()


def helper_a(value: str) -> str:
    """A helper function for module A."""
    return value.strip().lower()


def validate_a(data: dict) -> bool:
    """Validate data for module A."""
    if not isinstance(data, dict):
        return False
    return "key" in data