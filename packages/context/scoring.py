"""Scoring rules for the Ranking Engine.

Defines the ``RankingReason`` enumeration and pure scoring functions that
assign additive scores to ``ContextCandidate`` instances based on how well
their names and modules match a normalised query.

Ranking v2 — Engineering Relevance Ranking
-------------------------------------------

The scoring model has been upgraded to a **multi-factor engineering
relevance ranking**.  Each candidate receives a composite score computed
from independent factors:

    composite_score = sum(positive_factors) - sum(penalty_factors)

Scoring Rules (Ranking v2)
--------------------------

**Name-matching factors (mutually exclusive, highest wins):**

| Rule | Score |
|------|------:|
| Exact symbol name match | +100 |
| Exact qualified name match | +90 |
| Partial symbol name match | +50 |
| Module name contains query token | +30 |

**Engineering quality factors (additive):**

| Rule | Score |
|------|------:|
| Import proximity | +25 |
| Call graph direct caller | +30 |
| Call graph direct callee | +30 |
| Same module as primary | +20 |
| Same class scope as primary | +25 |
| Shared parent via DEFINES | +20 |
| Symbol type preference | +10 |
| Public API (exported in __init__.py) | +15 |
| Has docstring | +10 |
| Small implementation size | +15 |
| Token overlap (per token) | +10 |
| Public name (no underscore prefix) | +5 |

**Penalty factors:**

| Rule | Score |
|------|------:|
| Generated code pattern | -20 |
| Test code file | -15 |
| Private symbol | -10 |
| Large implementation (>100 lines) | -5 |

**Tie-Breaking Order:**

1. qualified_name ascending (alphabetical)
2. symbol_type preference (CLASS > FUNCTION > METHOD)
3. module path ascending
4. lineno ascending

This ensures **strict total ordering** — no two candidates can ever tie.

Constraints
-----------

- No filesystem access.
- No source code parsing.
- No AST, LLM, embedding, or DSPARK usage.
- Pure function: same input always produces same output.
- Deterministic: same input always produces same output.
- No machine learning.
- No randomness.
- No provider calls.
- No embeddings.
- No vector search.

Public API
----------

.. code-block:: python

    from packages.context.scoring import score_candidate, score_relationship

    score, reasons = score_candidate(candidate, query_tokens)
    rel_score, rel_reasons = score_relationship(candidate, primary, graph_view)

"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

from packages.context.ranking_config import RankingConfig

if TYPE_CHECKING:
    from packages.context.models import ContextCandidate


class SymbolGraphView(Protocol):
    """Minimal interface for a SymbolGraph view used in relationship scoring.

    Duck-typed: any object with ``callers``, ``callees``, ``parents``,
    and ``children`` methods that accept a ``ContextCandidate`` and return
    a list of ``ContextCandidate`` objects is considered a valid view.
    """

    def callers(self, symbol: ContextCandidate) -> list[ContextCandidate]: ...
    def callees(self, symbol: ContextCandidate) -> list[ContextCandidate]: ...
    def parents(self, symbol: ContextCandidate) -> list[ContextCandidate]: ...
    def children(self, symbol: ContextCandidate) -> list[ContextCandidate]: ...


class RankingReason(Enum):
    """Explainability signals for why a candidate received its score.

    These values are attached to candidates for debugging only; they are
    not surfaced to end users.

    Ranking v2 reasons include engineering-specific signals.
    """

    # Name-matching reasons
    EXACT_SYMBOL_NAME = auto()
    EXACT_QUALIFIED_NAME = auto()
    PARTIAL_SYMBOL_NAME = auto()
    MODULE_MATCH = auto()

    # Engineering quality reasons
    IMPORT_PROXIMITY = auto()
    DIRECT_CALLER = auto()
    DIRECT_CALLEE = auto()
    SHARED_PARENT = auto()
    SHARED_MODULE = auto()
    SHARED_CLASS = auto()
    SYMBOL_TYPE_PREFERENCE = auto()
    PUBLIC_API_BONUS = auto()
    DOCUMENTATION_BONUS = auto()
    IMPLEMENTATION_SIZE_BONUS = auto()
    TOKEN_MATCH = auto()
    PUBLIC_NAME = auto()

    # Penalty reasons
    GENERATED_CODE = auto()
    TEST_CODE = auto()
    PRIVATE_SYMBOL = auto()
    LARGE_IMPLEMENTATION = auto()


# ------------------------------------------------------------------
# Query normalisation
# ------------------------------------------------------------------


def normalise_query_text(text: str) -> list[str]:
    """Normalise query text into a list of unique tokens.

    Steps:
    - Lowercase.
    - Split on whitespace.
    - Remove empty tokens.
    - Remove duplicate tokens while preserving order.

    Does **not** stem, lemmatise, remove stop words, or perform fuzzy
    matching.

    Args:
        text: Raw query text.

    Returns:
        Ordered list of unique normalised tokens.
    """
    text = text.lower()
    tokens = text.split()
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if not token:
            continue
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


# ------------------------------------------------------------------
# Symbol name helpers
# ------------------------------------------------------------------

# Pattern that splits a dotted/qualified name into its constituent name
# segments (e.g. "auth.middleware.AuthenticationMiddleware" ->
# ["auth", "middleware", "AuthenticationMiddleware"]).
_SEGMENT_RE = re.compile(r"[a-zA-Z0-9_]+")


def _extract_name_segments(qualified_name: str) -> list[str]:
    """Extract name segments from a qualified name.

    Args:
        qualified_name: A dotted name such as ``auth.middleware.App``.

    Returns:
        List of name segments in order.
    """
    return _SEGMENT_RE.findall(qualified_name)


def _last_segment(qualified_name: str) -> str:
    """Return the rightmost segment of a qualified name.

    Args:
        qualified_name: A dotted name.

    Returns:
        The last segment, or the full name if no dot exists.
    """
    segments = qualified_name.rsplit(".", 1)
    return segments[-1]


# ------------------------------------------------------------------
# Ranking v2 helper functions
# ------------------------------------------------------------------


def _is_generated_code(qualified_name: str) -> bool:
    """Check if a symbol matches generated code patterns.

    Args:
        qualified_name: The fully qualified symbol name.

    Returns:
        True if the symbol appears to be generated code.
    """
    name_lower = qualified_name.lower()
    for pattern in RankingConfig.GENERATED_PATTERNS:
        if pattern in name_lower:
            return True
    return False


def _is_test_file(module: str) -> bool:
    """Check if a module path indicates a test file.

    Args:
        module: Module path relative to repository root.

    Returns:
        True if the module appears to be a test file.
    """
    module_lower = module.lower()
    for pattern in RankingConfig.TEST_FILE_PATTERNS:
        if pattern in module_lower:
            return True
    return False


def _is_private_symbol(qualified_name: str) -> bool:
    """Check if a symbol is private (starts with underscore).

    Args:
        qualified_name: The fully qualified symbol name.

    Returns:
        True if the symbol is private.
    """
    last = _last_segment(qualified_name)
    return last.startswith("_")


def _count_source_lines(source: str) -> int:
    """Count the number of non-empty lines in source code.

    Args:
        source: Source code string.

    Returns:
        Number of non-empty lines.
    """
    if not source:
        return 0
    return sum(1 for line in source.splitlines() if line.strip())


def _has_docstring(candidate: ContextCandidate) -> bool:
    """Check if a candidate has documentation.

    Args:
        candidate: The candidate to check.

    Returns:
        True if the candidate has a docstring.
    """
    return bool(candidate.docstring and candidate.docstring.strip())


def _get_symbol_type_rank(symbol_type: str) -> int:
    """Get the ranking value for a symbol type.

    Higher values indicate higher preference.

    Args:
        symbol_type: The symbol type string.

    Returns:
        Ranking value (CLASS=3, FUNCTION=2, METHOD=1, VARIABLE=0).
    """
    return RankingConfig.SYMBOL_TYPE_RANK.get(symbol_type.upper(), 0)


def _estimate_token_count(text: str) -> int:
    """Estimate token count for text content.

    Each candidate is estimated at ~100 tokens by default.
    For actual content, use 4 characters per token.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return len(text) // 4


# ------------------------------------------------------------------
# Ranking v2 Scoring
# ------------------------------------------------------------------


def score_candidate_v2(
    candidate: ContextCandidate,
    query_tokens: list[str],
    symbol_graph_view: SymbolGraphView | None = None,
    primary_symbol: ContextCandidate | None = None,
    relationship_enabled: bool = True,
    expansion_enabled: bool = True,
) -> tuple[int, list[RankingReason]]:
    """Score a candidate using Ranking v2 multi-factor engineering ranking.

    This is the **new** scoring function that replaces ``score_candidate``.
    It incorporates engineering-aware factors:

    - Symbol type preference
    - Public API bonus (exported in __init__.py)
    - Documentation bonus (has docstring)
    - Implementation size bonus/penalty
    - Call graph relationships
    - Generated code penalty
    - Test code penalty
    - Private symbol penalty

    The score is computed as:

        composite_score = sum(positive_factors) - sum(penalty_factors)

    Args:
        candidate: The candidate to score.
        query_tokens: Normalised unique query tokens.
        symbol_graph_view: Optional SymbolGraphView for relationship lookups.
        primary_symbol: Optional primary symbol for relationship scoring.
        relationship_enabled: Whether relationship scoring is enabled.
        expansion_enabled: Whether expansion scoring is enabled.

    Returns:
        A ``(score, reasons)`` tuple.
    """
    from packages.context.models import ContextCandidate  # noqa: F401

    if not query_tokens:
        return 0, []

    score = 0
    reasons: list[RankingReason] = []

    name_segments = _extract_name_segments(candidate.qualified_name)
    last_segment = _last_segment(candidate.qualified_name)
    module = candidate.module

    # ================================================================
    # PHASE 1: Name-matching rules (mutually exclusive, highest wins)
    # ================================================================

    # EXACT_SYMBOL_NAME: +100
    # Any name segment exactly matches a query token (case-insensitive).
    exact_symbol = False
    for token in query_tokens:
        if any(seg.lower() == token for seg in name_segments):
            exact_symbol = True
            break

    # EXACT_QUALIFIED_NAME: +90
    # The full qualified name (lowercased) exactly equals a query token.
    exact_qualified = False
    if not exact_symbol:
        for token in query_tokens:
            if candidate.qualified_name.lower() == token:
                exact_qualified = True
                break

    # PARTIAL_SYMBOL_NAME: +50
    # A name segment contains a query token as a substring
    # (case-insensitive), and no exact match was found.
    partial = False
    if not exact_symbol and not exact_qualified:
        for token in query_tokens:
            if any(token in seg.lower() for seg in name_segments):
                partial = True
                break

    # MODULE_MATCH: +30
    # The module path contains a query token (case-insensitive).
    # Only fires if no name rule matched.
    module_match = False
    if not exact_symbol and not exact_qualified and not partial:
        for token in query_tokens:
            if token in module.lower():
                module_match = True
                break

    # Apply the best name-matching rule.
    if exact_symbol:
        score += RankingConfig.WEIGHT_EXACT_MATCH
        reasons.append(RankingReason.EXACT_SYMBOL_NAME)
    elif exact_qualified:
        score += RankingConfig.WEIGHT_QUALIFIED_NAME
        reasons.append(RankingReason.EXACT_QUALIFIED_NAME)
    elif partial:
        score += RankingConfig.WEIGHT_PARTIAL_MATCH
        reasons.append(RankingReason.PARTIAL_SYMBOL_NAME)
    elif module_match:
        score += RankingConfig.WEIGHT_MODULE_RELEVANCE
        reasons.append(RankingReason.MODULE_MATCH)

    # ================================================================
    # PHASE 2: Token overlap (additive)
    # ================================================================

    # A query token appears anywhere in the qualified name
    # (case-insensitive). Accumulates per unique matching token.
    token_match_count = 0
    for token in query_tokens:
        if token in candidate.qualified_name.lower():
            token_match_count += 1
    if token_match_count > 0:
        score += token_match_count * RankingConfig.WEIGHT_TOKEN_OVERLAP
        reasons.append(RankingReason.TOKEN_MATCH)

    # ================================================================
    # PHASE 3: Engineering quality factors (additive)
    # ================================================================

    # PUBLIC_NAME_BONUS: +5
    # The symbol name does not start with "_".
    if not last_segment.startswith("_"):
        score += RankingConfig.WEIGHT_PUBLIC_NAME_BONUS
        reasons.append(RankingReason.PUBLIC_NAME)

    # SYMBOL_TYPE_PREFERENCE: +10
    # Applied if symbol_type is known.
    if candidate.symbol_type:
        type_rank = _get_symbol_type_rank(candidate.symbol_type)
        if type_rank > 0:
            score += RankingConfig.WEIGHT_SYMBOL_TYPE_PREFERENCE
            reasons.append(RankingReason.SYMBOL_TYPE_PREFERENCE)

    # PUBLIC_API_BONUS: +15
    # Symbol is exported from package __init__.py.
    if RankingConfig.API_BONUS_ENABLED and candidate.is_in_init_py:
        score += RankingConfig.WEIGHT_PUBLIC_API_BONUS
        reasons.append(RankingReason.PUBLIC_API_BONUS)

    # DOCUMENTATION_BONUS: +10
    # Symbol has a docstring.
    if _has_docstring(candidate):
        score += RankingConfig.WEIGHT_DOCUMENTATION_BONUS
        reasons.append(RankingReason.DOCUMENTATION_BONUS)

    # IMPLEMENTATION_SIZE_BONUS: +15
    # Smaller implementations are preferred.
    source_lines = _count_source_lines(candidate.source)
    if source_lines > 0 and source_lines <= RankingConfig.MAX_SIZE_FOR_BONUS:
        score += RankingConfig.WEIGHT_IMPLEMENTATION_SIZE_BONUS
        reasons.append(RankingReason.IMPLEMENTATION_SIZE_BONUS)

    # ================================================================
    # PHASE 4: Call graph relationships (additive, if enabled)
    # ================================================================

    if RankingConfig.CALL_GRAPH_BONUS_ENABLED and relationship_enabled:
        if symbol_graph_view is not None and primary_symbol is not None:
            # Guard against scoring the primary symbol itself.
            if candidate.symbol_id != primary_symbol.symbol_id:
                try:
                    # SHARED_MODULE: +20
                    if candidate.module == primary_symbol.module:
                        score += RankingConfig.WEIGHT_CALL_GRAPH_SAME_MODULE
                        reasons.append(RankingReason.SHARED_MODULE)

                        # SHARED_CLASS: +25
                        # Same class scope (same parent module and similar path prefix)
                        candidate_class = _extract_class_scope(candidate.qualified_name)
                        primary_class = _extract_class_scope(primary_symbol.qualified_name)
                        if candidate_class and primary_class and candidate_class == primary_class:
                            score += RankingConfig.WEIGHT_CALL_GRAPH_SAME_CLASS
                            reasons.append(RankingReason.SHARED_CLASS)

                    # DIRECT_CALLER: +30
                    # Candidate calls the primary symbol.
                    callers = symbol_graph_view.callers(primary_symbol)
                    for caller in callers:
                        if caller.qualified_name == candidate.qualified_name:
                            score += RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLER
                            reasons.append(RankingReason.DIRECT_CALLER)
                            break

                    # DIRECT_CALLEE: +30
                    # Primary symbol calls the candidate.
                    callees = symbol_graph_view.callees(primary_symbol)
                    for callee in callees:
                        if callee.qualified_name == candidate.qualified_name:
                            score += RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLEE
                            reasons.append(RankingReason.DIRECT_CALLEE)
                            break

                    # SHARED_PARENT: +20
                    # Candidate and primary share a parent via DEFINES.
                    primary_parents = symbol_graph_view.parents(primary_symbol)
                    for parent in primary_parents:
                        candidate_children = symbol_graph_view.children(parent)
                        for child in candidate_children:
                            if child.qualified_name == candidate.qualified_name:
                                score += RankingConfig.WEIGHT_CALL_GRAPH_SHARED_PARENT
                                reasons.append(RankingReason.SHARED_PARENT)
                                break
                        if reasons and reasons[-1] == RankingReason.SHARED_PARENT:
                            break

                except (AttributeError, TypeError):
                    # Symbol graph view doesn't have expected methods.
                    pass

    # ================================================================
    # PHASE 5: Penalty factors (subtractive)
    # ================================================================

    # GENERATED_CODE: -20
    if RankingConfig.GENERATED_PENALTY_ENABLED and _is_generated_code(candidate.qualified_name):
        score += RankingConfig.PENALTY_GENERATED_CODE
        reasons.append(RankingReason.GENERATED_CODE)

    # TEST_CODE: -15
    if RankingConfig.TEST_PENALTY_ENABLED and _is_test_file(module):
        score += RankingConfig.PENALTY_TEST_CODE
        reasons.append(RankingReason.TEST_CODE)

    # PRIVATE_SYMBOL: -10
    if _is_private_symbol(candidate.qualified_name):
        score += RankingConfig.PENALTY_PRIVATE_SYMBOL
        reasons.append(RankingReason.PRIVATE_SYMBOL)

    # LARGE_IMPLEMENTATION: -5
    if source_lines > RankingConfig.MAX_SIZE_BEFORE_PENALTY:
        score += RankingConfig.PENALTY_LARGE_IMPLEMENTATION
        reasons.append(RankingReason.LARGE_IMPLEMENTATION)

    return score, reasons


# ------------------------------------------------------------------
# Legacy score_candidate (backward compatibility)
# ------------------------------------------------------------------


def score_candidate(
    candidate: ContextCandidate,
    query_tokens: list[str],
) -> tuple[int, list[RankingReason]]:
    """Score a single candidate against normalised query tokens.

    **Ranking v2**: This function now delegates to ``score_candidate_v2``
    for full engineering-aware scoring.  The function signature is
    preserved for backward compatibility.

    The name-matching rules are mutually exclusive — only the
    highest-scoring rule fires.  TOKEN_MATCH and PUBLIC_SYMBOL are
    additive on top.

    Scoring Rules (Ranking v2)
    --------------------------

    | Rule | Score |
    |------|------:|
    | Exact symbol name match | +100 |
    | Exact qualified name match | +90 |
    | Partial symbol name match | +50 |
    | Module name contains query token | +30 |
    | Matching query token | +10 per token |
    | Public symbol (name does not start with "_") | +5 |
    | Engineering bonuses | +5 to +30 |
    | Penalties | -5 to -20 |

    Args:
        candidate: The candidate to score.
        query_tokens: Normalised unique query tokens.

    Returns:
        A ``(score, reasons)`` tuple.
    """
    return score_candidate_v2(candidate, query_tokens)


# ------------------------------------------------------------------
# Relationship scoring (Ranking v2)
# ------------------------------------------------------------------


def score_relationship(
    candidate: ContextCandidate,
    primary_symbol: ContextCandidate | None,
    symbol_graph_view: SymbolGraphView | None,
    relationship_enabled: bool,
) -> tuple[int, list[RankingReason]]:
    """Score a candidate based on relationship signals to the primary symbol.

    **Ranking v2**: This function now uses the weights from ``RankingConfig``
    and incorporates all call graph relationship types.

    Relationship signals:

    - DIRECT_CALLER: candidate calls the primary symbol (+WEIGHT_DIRECT_CALLER)
    - DIRECT_CALLEE: primary symbol calls the candidate (+WEIGHT_DIRECT_CALLEE)
    - SHARED_PARENT: candidate and primary share a parent via DEFINES (+WEIGHT_SHARED_PARENT)
    - SHARED_MODULE: candidate and primary are in the same module (+WEIGHT_SHARED_MODULE)
    - SHARED_CLASS: candidate and primary share the same class scope (+WEIGHT_SHARED_CLASS)

    Args:
        candidate: The candidate to score.
        primary_symbol: The primary symbol being requested.
        symbol_graph_view: A SymbolGraphView instance for relationship lookups.
        relationship_enabled: Whether relationship scoring is enabled.

    Returns:
        A ``(score, reasons)`` tuple.
    """
    from packages.context.models import ContextCandidate  # noqa: F401

    if not relationship_enabled or primary_symbol is None or symbol_graph_view is None:
        return 0, []

    # Guard against synthetic or missing symbols.
    if candidate.symbol_id == primary_symbol.symbol_id:
        return 0, []

    score = 0
    reasons: list[RankingReason] = []

    try:
        # SHARED_MODULE: same module path
        if candidate.module == primary_symbol.module:
            score += RankingConfig.WEIGHT_CALL_GRAPH_SAME_MODULE
            reasons.append(RankingReason.SHARED_MODULE)

        # SHARED_CLASS: same class scope
        candidate_class = _extract_class_scope(candidate.qualified_name)
        primary_class = _extract_class_scope(primary_symbol.qualified_name)
        if candidate_class and primary_class and candidate_class == primary_class:
            score += RankingConfig.WEIGHT_CALL_GRAPH_SAME_CLASS
            reasons.append(RankingReason.SHARED_CLASS)

    except (AttributeError, TypeError):
        return 0, []

    try:
        # DIRECT_CALLER: candidate calls the primary symbol
        callers = symbol_graph_view.callers(primary_symbol)
        for caller in callers:
            if caller.qualified_name == candidate.qualified_name:
                score += RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLER
                reasons.append(RankingReason.DIRECT_CALLER)
                break

        # DIRECT_CALLEE: primary symbol calls the candidate
        callees = symbol_graph_view.callees(primary_symbol)
        for callee in callees:
            if callee.qualified_name == candidate.qualified_name:
                score += RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLEE
                reasons.append(RankingReason.DIRECT_CALLEE)
                break

        # SHARED_PARENT: candidate and primary share a parent via DEFINES
        primary_parents = symbol_graph_view.parents(primary_symbol)
        for parent in primary_parents:
            candidate_children = symbol_graph_view.children(parent)
            for child in candidate_children:
                if child.qualified_name == candidate.qualified_name:
                    score += RankingConfig.WEIGHT_CALL_GRAPH_SHARED_PARENT
                    reasons.append(RankingReason.SHARED_PARENT)
                    break
            if reasons and reasons[-1] == RankingReason.SHARED_PARENT:
                break

    except (AttributeError, TypeError):
        pass

    return score, reasons


def _extract_class_scope(qualified_name: str) -> str:
    """Extract the class scope from a qualified name.

    For a method like ``auth.App.run``, returns ``auth.App``.
    For a function like ``auth.run``, returns empty string.

    Args:
        qualified_name: A dotted qualified name.

    Returns:
        The class scope, or empty string if not a method.
    """
    # A method has at least 3 segments: module.Class.method
    segments = qualified_name.split(".")
    if len(segments) >= 3:
        # The second-to-last segment is the class.
        return ".".join(segments[:-1])
    return ""