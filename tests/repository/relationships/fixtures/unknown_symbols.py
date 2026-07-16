"""Fixture — calls to unknown symbols (should be ignored)."""


def known() -> str:
    """A known function."""
    return "known"


def uses_unknown() -> str:
    """Calls an unknown function."""
    # external_lib.do_something() — this is not a known symbol
    result = some_unknown_function()
    return result


def uses_mixed() -> str:
    """Calls both known and unknown."""
    a = known()
    b = unknown_call()
    c = helper()  # helper is not defined in this file
    return a + b + c
