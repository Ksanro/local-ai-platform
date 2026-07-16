"""Fixture — recursive and mutual recursion calls."""


def factorial(n: int) -> int:
    """Recursive factorial."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def is_even(n: int) -> bool:
    """Mutual recursion — even calls odd."""
    if n == 0:
        return True
    return is_odd(n - 1)


def is_odd(n: int) -> bool:
    """Mutual recursion — odd calls even."""
    if n == 0:
        return False
    return is_even(n - 1)


def nested_recursive() -> None:
    """Function with a nested recursive function."""

    def inner_recursive(n: int) -> int:
        """Nested recursive function."""
        if n <= 0:
            return 0
        return n + inner_recursive(n - 1)

    result = inner_recursive(5)
    print(result)
