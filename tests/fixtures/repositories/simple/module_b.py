"""Module B fixture for benchmark testing."""


class ServiceB:
    """A simple service class."""

    def __init__(self, prefix: str) -> None:
        """Initialize ServiceB."""
        self.prefix = prefix
        self._items: list[str] = []

    def add(self, item: str) -> None:
        """Add an item with prefix."""
        self._items.append(f"{self.prefix}:{item}")

    def get_all(self) -> list[str]:
        """Return all items."""
        return list(self._items)

    def count(self) -> int:
        """Return the number of items."""
        return len(self._items)


def helper_b(value: int) -> int:
    """A helper function for module B."""
    return value * 2


def validate_b(items: list[object]) -> bool:
    """Validate items list for module B."""
    if not isinstance(items, list):
        return False
    return len(items) > 0
