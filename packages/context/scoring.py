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
| Module name contains query token | +30 |
| Matching query token | +10 per token |
| Public symbol (name does not start with "_") | +5 |

Each rule contributes at most once, except TOKEN_MATCH which accumulates
per matching token.

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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.context.models import ContextCandidate


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
