"""Scoring rules for the Ranking Engine.

Defines the ``RankingReason`` enumeration and pure scoring functions that
assign additive scores to ``ContextCandidate`` instances based on how well
their names and modules match a normalised query.

Scoring Rules
-------------

| Rule | Score |
|------|------:|
| Exact symbol name match | +100 |
| Exact qualified name match | +90 |
| Partial symbol name match | +50 |
| Module match | +30 |
| Shared class | +25 |
| Direct caller | +20 |
| Direct callee | +20 |
| Shared module | +15 |
| Token overlap | +10 |
| Public symbol (name does not start with "_") | +5 |

Each rule contributes at most once, except TOKEN_MATCH which accumulates
per matching token.

Relationship signals are only applied when the ranking engine is
configured with a symbol graph and a primary symbol.

Constraints
-----------

- No filesystem access.
- No source code parsing.
- No AST, LLM, embedding, or DSPARK usage.
- Pure function: same input always produces same output.
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

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
    """

    EXACT_SYMBOL_NAME = auto()
    PARTIAL_SYMBOL_NAME = auto()
    MODULE_MATCH = auto()
    TOKEN_MATCH = auto()
    PUBLIC_SYMBOL = auto()
    # Relationship signals
    DIRECT_CALLER = auto()
    DIRECT_CALLEE = auto()
    SHARED_PARENT = auto()
    SHARED_MODULE = auto()
    SHARED_CLASS = auto()


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
# Relationship scoring constants
# ------------------------------------------------------------------

# Default weights for all ranking signals.
# These are the authoritative defaults — no magic numbers elsewhere.
WEIGHT_EXACT_MATCH = 100
WEIGHT_QUALIFIED_NAME = 90
WEIGHT_MODULE = 30
WEIGHT_SHARED_CLASS = 25
WEIGHT_DIRECT_CALLER = 20
WEIGHT_DIRECT_CALLEE = 20
WEIGHT_SHARED_PARENT = 25
WEIGHT_SHARED_MODULE = 15
WEIGHT_TOKEN_OVERLAP = 10
WEIGHT_PUBLIC_SYMBOL = 5


# ------------------------------------------------------------------
# Scoring
# ------------------------------------------------------------------


def score_candidate(
    candidate: ContextCandidate,
    query_tokens: list[str],
) -> tuple[int, list[RankingReason]]:
    """Score a single candidate against normalised query tokens.

    The name-matching rules are mutually exclusive — only the
    highest-scoring rule fires.  TOKEN_MATCH and PUBLIC_SYMBOL are
    additive on top.

    Scoring Rules
    -------------

    | Rule | Score |
    |------|------:|
    | Exact symbol name match | +100 |
    | Exact qualified name match | +90 |
    | Partial symbol name match | +50 |
    | Module name contains query token | +30 |
    | Matching query token | +10 per token |
    | Public symbol (name does not start with "_") | +5 |

    Args:
        candidate: The candidate to score.
        query_tokens: Normalised unique query tokens.

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

    # --- Name-matching rules (mutually exclusive, highest wins) ---

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
        score += 100
        reasons.append(RankingReason.EXACT_SYMBOL_NAME)
    elif exact_qualified:
        score += 90
        reasons.append(RankingReason.EXACT_SYMBOL_NAME)
    elif partial:
        score += 50
        reasons.append(RankingReason.PARTIAL_SYMBOL_NAME)
    elif module_match:
        score += 30
        reasons.append(RankingReason.MODULE_MATCH)

    # --- TOKEN_MATCH: +10 per matching token (additive) ---
    # A query token appears anywhere in the qualified name
    # (case-insensitive). Accumulates per unique matching token.
    token_match_count = 0
    for token in query_tokens:
        if token in candidate.qualified_name.lower():
            token_match_count += 1
    if token_match_count > 0:
        score += token_match_count * 10
        reasons.append(RankingReason.TOKEN_MATCH)

    # --- PUBLIC_SYMBOL: +5 (additive) ---
    # The symbol name does not start with "_".
    if not last_segment.startswith("_"):
        score += 5
        reasons.append(RankingReason.PUBLIC_SYMBOL)

    return score, reasons


def score_relationship(
    candidate: ContextCandidate,
    primary_symbol: ContextCandidate | None,
    symbol_graph_view: SymbolGraphView | None,
    relationship_enabled: bool,
) -> tuple[int, list[RankingReason]]:
    """Score a candidate based on relationship signals to the primary symbol.

    This is a pure function that only uses the symbol graph to compute
    relationship-based scoring signals.  It does not modify the graph.

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

    # Import the SymbolGraphView type to avoid circular imports.
    # We use duck typing: the view must have callers(), callees(), parents(),
    # children(), and modules() methods.
    try:
        # SHARED_MODULE: same module path
        if candidate.module == primary_symbol.module:
            score += WEIGHT_SHARED_MODULE
            reasons.append(RankingReason.SHARED_MODULE)

            # SHARED_CLASS: same class scope (same parent module and similar path prefix)
            # Extract class scope from qualified_name: e.g. "auth.App.run" -> "auth.App"
            candidate_class = _extract_class_scope(candidate.qualified_name)
            primary_class = _extract_class_scope(primary_symbol.qualified_name)
            if candidate_class and primary_class and candidate_class == primary_class:
                score += WEIGHT_SHARED_CLASS
                reasons.append(RankingReason.SHARED_CLASS)

    except (AttributeError, TypeError):
        # Symbol graph view doesn't have expected methods — skip relationship scoring.
        return 0, []

    # Check CALLS relationships via the symbol graph view.
    try:
        # DIRECT_CALLER: candidate calls the primary symbol
        # The callers() method returns symbols that call the given symbol.
        callers = symbol_graph_view.callers(primary_symbol)
        for caller in callers:
            if caller.qualified_name == candidate.qualified_name:
                score += WEIGHT_DIRECT_CALLER
                reasons.append(RankingReason.DIRECT_CALLER)
                break

        # DIRECT_CALLEE: primary symbol calls the candidate
        # The callees() method returns symbols that the given symbol calls.
        callees = symbol_graph_view.callees(primary_symbol)
        for callee in callees:
            if callee.qualified_name == candidate.qualified_name:
                score += WEIGHT_DIRECT_CALLEE
                reasons.append(RankingReason.DIRECT_CALLEE)
                break

        # SHARED_PARENT: candidate and primary share a parent via DEFINES
        primary_parents = symbol_graph_view.parents(primary_symbol)
        for parent in primary_parents:
            # Check if candidate is a child of the same parent
            candidate_children = symbol_graph_view.children(parent)
            for child in candidate_children:
                if child.qualified_name == candidate.qualified_name:
                    score += WEIGHT_SHARED_PARENT
                    reasons.append(RankingReason.SHARED_PARENT)
                    break
            if reasons and reasons[-1] == RankingReason.SHARED_PARENT:
                break

    except (AttributeError, TypeError):
        # Symbol graph view doesn't have expected methods — skip relationship scoring.
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
