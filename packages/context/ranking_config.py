"""Ranking v2 Configuration Constants.

Deterministic multi-factor engineering relevance ranking weights and
configuration.  All weights are **immutable constants** — no runtime
modification.

Architecture
------------

RankingConfig
       |
       v
RankingEngine (consumes only)

Ranking Model
-------------

Each candidate receives a **composite score** computed from independent
factors:

    composite_score = sum(positive_factors) - sum(penalty_factors)

Positive factors (bonuses):

- EXACT_SYMBOL_MATCH: Symbol name exactly matches a query token (+100)
- EXACT_QUALIFIED_NAME: Full qualified name matches query token (+90)
- PARTIAL_SYMBOL_MATCH: Symbol name contains query token (+50)
- MODULE_RELEVANCE: Module path contains query token (+30)
- IMPORT_PROXIMITY: Symbol is imported near query context (+25)
- CALL_GRAPH_DIRECT_CALLER: Direct caller of primary symbol (+30)
- CALL_GRAPH_DIRECT_CALLEE: Direct callee of primary symbol (+30)
- CALL_GRAPH_SAME_MODULE: Same module as primary symbol (+20)
- CALL_GRAPH_SAME_CLASS: Same class scope as primary symbol (+25)
- CALL_GRAPH_SHARED_PARENT: Shares DEFINES parent with primary (+20)
- SYMBOL_TYPE_PREFERENCE: PREFER: CLASS > FUNCTION > METHOD (+10)
- PUBLIC_API_BONUS: Symbol exported from __init__.py (+15)
- DOCUMENTATION_BONUS: Symbol has a docstring (+10)
- IMPLEMENTATION_SIZE_BONUS: Smaller implementations preferred (+15)
- TOKEN_OVERLAP: Per-query-token overlap (accumulative, +10 per token)
- PUBLIC_NAME_BONUS: Name doesn't start with "_" (+5)

Penalty factors:

- GENERATED_CODE: Symbol name matches generated patterns (-20)
- TEST_CODE: Symbol is in a test file (-15)
- PRIVATE_SYMBOL: Name starts with "_" (double underscore) (-10)
- LARGE_IMPLEMENTATION: Implementation exceeds 100 lines (-5)

Tie-Breaking Order
------------------

When two candidates have identical composite scores:

1. qualified_name ascending (alphabetical)
2. symbol_type preference (CLASS > FUNCTION > METHOD)
3. module path ascending
4. lineno ascending

This ensures **strict total ordering** — no two candidates can ever tie.

Constraints
-----------

- No machine learning.
- No randomness.
- No provider calls.
- No embeddings.
- No vector search.
- All weights are documented constants.

Public API
----------

.. code-block:: python

    from packages.context.ranking_config import RankingConfig

    # Access any weight directly
    assert RankingConfig.WEIGHT_EXACT_MATCH == 100
    assert RankingConfig.PENALTY_GENERATED_CODE == -20
"""

from __future__ import annotations


class RankingConfig:
    """Deterministic ranking configuration constants.

    This class is intentionally immutable — all attributes are
    uppercase constants that cannot be modified at runtime.

    To change weights for testing, use the test configuration
    parameters in ``RankingEngine`` instead of modifying this class.
    """

    # ------------------------------------------------------------------
    # Positive scoring factors (bonuses)
    # ------------------------------------------------------------------

    # Name-matching factors (mutually exclusive, highest wins)
    WEIGHT_EXACT_MATCH: int = 100
    """Exact symbol name match: any name segment exactly matches a query
    token (case-insensitive)."""

    WEIGHT_QUALIFIED_NAME: int = 90
    """Exact qualified name match: the full qualified name (lowercased)
    exactly equals a query token."""

    WEIGHT_PARTIAL_MATCH: int = 50
    """Partial symbol name match: a name segment contains a query token
    as a substring (case-insensitive)."""

    WEIGHT_MODULE_RELEVANCE: int = 30
    """Module name contains query token: the module path contains a query
    token (case-insensitive). Only fires if no name rule matched."""

    WEIGHT_IMPORT_PROXIMITY: int = 25
    """Import proximity: symbol appears in an import statement near the
    query context. Higher weight for direct imports vs re-exports."""

    # Call graph factors (additive, multiple can fire)
    WEIGHT_CALL_GRAPH_DIRECT_CALLER: int = 30
    """Direct caller bonus: candidate calls the primary symbol via a
    CALLS relationship."""

    WEIGHT_CALL_GRAPH_DIRECT_CALLEE: int = 30
    """Direct callee bonus: primary symbol calls the candidate via a
    CALLS relationship."""

    WEIGHT_CALL_GRAPH_SAME_MODULE: int = 20
    """Same module bonus: candidate and primary symbol are in the same
    module (file)."""

    WEIGHT_CALL_GRAPH_SAME_CLASS: int = 25
    """Same class bonus: candidate and primary symbol share the same
    class scope (same parent module and similar path prefix)."""

    WEIGHT_CALL_GRAPH_SHARED_PARENT: int = 20
    """Shared parent bonus: candidate and primary share a parent via
    DEFINES relationship."""

    # Engineering quality factors
    WEIGHT_SYMBOL_TYPE_PREFERENCE: int = 10
    """Symbol type preference: CLASS symbols are preferred over FUNCTION,
    which are preferred over METHOD. Applied per matching type."""

    WEIGHT_PUBLIC_API_BONUS: int = 15
    """Public API bonus: symbol is exported by package __init__.py.
    Indicates the symbol is part of the public interface."""

    WEIGHT_DOCUMENTATION_BONUS: int = 10
    """Documentation bonus: symbol has a docstring. Indicates the symbol
    is documented and likely important."""

    WEIGHT_IMPLEMENTATION_SIZE_BONUS: int = 15
    """Implementation size bonus: smaller implementations are preferred.
    Applied inversely — smaller functions get higher scores."""

    # Token overlap (additive, accumulates per matching token)
    WEIGHT_TOKEN_OVERLAP: int = 10
    """Token overlap: a query token appears anywhere in the qualified
    name (case-insensitive). Accumulates per unique matching token."""

    # Name prefix bonus
    WEIGHT_PUBLIC_NAME_BONUS: int = 5
    """Public name bonus: the symbol name does not start with "_".
    Applied to all non-private symbols."""

    # ------------------------------------------------------------------
    # Penalty factors (negative scores)
    # ------------------------------------------------------------------

    PENALTY_GENERATED_CODE: int = -20
    """Generated code penalty: symbol name matches generated patterns
    (generated_, _gen_, _auto_, etc.)."""

    PENALTY_TEST_CODE: int = -15
    """Test code penalty: symbol is in a test file (test_*.py, *_test.py)."""

    PENALTY_PRIVATE_SYMBOL: int = -10
    """Private symbol penalty: name starts with "_" (single underscore)
    or "__" (double underscore)."""

    PENALTY_LARGE_IMPLEMENTATION: int = -5
    """Large implementation penalty: implementation exceeds 100 lines.
    Applied once per symbol."""

    # ------------------------------------------------------------------
    # Configuration limits
    # ------------------------------------------------------------------

    MAX_CANDIDATES: int = 20
    """Default maximum number of candidates to return."""

    MAX_MODULES: int = 10
    """Default maximum number of unique modules in the result."""

    TEST_PENALTY_ENABLED: bool = True
    """Whether test code penalty is applied."""

    GENERATED_PENALTY_ENABLED: bool = True
    """Whether generated code penalty is applied."""

    API_BONUS_ENABLED: bool = True
    """Whether public API bonus is applied."""

    CALL_GRAPH_BONUS_ENABLED: bool = True
    """Whether call graph bonuses are applied."""

    # ------------------------------------------------------------------
    # Implementation size thresholds
    # ------------------------------------------------------------------

    MAX_SIZE_FOR_BONUS: int = 50
    """Maximum number of lines for implementation size bonus. Functions
    with <= this many lines receive the full IMPLEMENTATION_SIZE_BONUS."""

    MAX_SIZE_BEFORE_PENALTY: int = 100
    """Maximum number of lines before large implementation penalty.
    Functions with > this many lines receive PENALTY_LARGE_IMPLEMENTATION."""

    # ------------------------------------------------------------------
    # Generated code patterns
    # ------------------------------------------------------------------

    GENERATED_PATTERNS: tuple[str, ...] = (
        "generated_",
        "_gen_",
        "_auto_",
        "_generated",
        "__generated__",
        "stub_",
        "_stub",
    )
    """Patterns that indicate generated code. Applied to symbol names."""

    # ------------------------------------------------------------------
    # Test file patterns
    # ------------------------------------------------------------------

    TEST_FILE_PATTERNS: tuple[str, ...] = (
        "test_",
        "_test.py",
        "conftest.py",
    )
    """Patterns that indicate test files. Applied to module paths."""

    # ------------------------------------------------------------------
    # Symbol type ordering (for tie-breaking)
    # ------------------------------------------------------------------

    SYMBOL_TYPE_RANK: dict[str, int] = {
        "CLASS": 3,
        "FUNCTION": 2,
        "METHOD": 1,
        "VARIABLE": 0,
    }
    """Symbol type preference ordering. Higher values = preferred."""