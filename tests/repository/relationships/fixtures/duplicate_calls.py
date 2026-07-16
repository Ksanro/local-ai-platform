"""Fixture — duplicate calls (same call repeated multiple times)."""


def helper() -> str:
    """A helper function called multiple times."""
    return "helper"


def process() -> None:
    """Calls helper multiple times."""
    a = helper()
    b = helper()
    c = helper()
    print(a, b, c)


def main() -> None:
    """Entry point."""
    process()
    process()
    process()
