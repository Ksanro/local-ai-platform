"""Fixture — nested calls (calls within calls)."""


def inner() -> str:
    """Inner function."""
    return "inner"


def middle(value: str) -> str:
    """Middle function."""
    return value + "middle"


def outer() -> str:
    """Outer function with nested calls."""
    result = middle(inner())
    return result


def chained() -> str:
    """Chained calls."""
    return middle(middle(inner()))
