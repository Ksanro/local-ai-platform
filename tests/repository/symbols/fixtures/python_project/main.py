"""Test fixture — main module with classes, functions, and methods."""



class Base:
    """Base class with no inheritance."""

    def __init__(self) -> None:
        """Initialise the base."""
        pass


class App(Base):
    """Application class that inherits from Base."""

    def __init__(self, name: str) -> None:
        """Initialise the app."""
        self.name = name

    def run(self) -> None:
        """Run the application."""
        pass

    @staticmethod
    def helper() -> None:
        """A static helper method."""
        pass


def main() -> None:
    """Entry point."""
    app = App("test")
    app.run()


def helper() -> None:
    """Module-level helper."""
    pass


def nested_outer() -> None:
    """Function with a nested function."""

    def nested_inner() -> None:
        """Nested function inside another function."""
        pass

    nested_inner()


async def async_handler() -> None:
    """Async function at module level."""
    pass
