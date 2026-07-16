"""Fixture — cross-module calls (simulated by having both modules in one file for testing).

This fixture simulates cross-module calls by having functions from
different "modules" call each other. In a real repository, these would
be in separate files.
"""

# Module A functions
def module_a_function() -> str:
    """A function in module A."""
    return "A"


def module_a_calls_b() -> str:
    """Module A calls into module B."""
    return module_b_function()


# Module B functions
def module_b_function() -> str:
    """A function in module B."""
    return "B"


def module_b_calls_a() -> str:
    """Module B calls into module A."""
    return module_a_function()
