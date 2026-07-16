"""Fixture — method calls."""


class Service:
    """A service class."""

    def __init__(self) -> None:
        """Initialise the service."""
        self.data: list[str] = []

    def add(self, item: str) -> None:
        """Add an item."""
        self.data.append(item)

    def get_all(self) -> list[str]:
        """Get all items."""
        return self.data

    def process(self) -> str:
        """Process all items."""
        return ", ".join(self.get_all())


class Controller:
    """A controller that uses Service."""

    def __init__(self) -> None:
        """Initialise the controller."""
        self.service = Service()

    def handle(self, item: str) -> str:
        """Handle an item."""
        self.service.add(item)
        return self.service.process()
