"""Fixture — simple function calls."""


def helper() -> str:
    """A simple helper function."""
    return "hello"


def process(data: str) -> str:
    """Process data using helper."""
    result = helper()
    return result + data


def main() -> None:
    """Entry point that calls process."""
    output = process("test")
    print(output)


def nested_outer() -> None:
    """Function with a nested function."""

    def nested_inner() -> str:
        """Nested function."""
        return "nested"

    value = nested_inner()
    print(value)
