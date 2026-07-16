"""Deterministic Ranking Engine.

Scores ``ContextCandidate`` instances against a user query and returns
them ordered by relevance.

Architecture
------------

Query
      │
      ▼
RankingEngine
      │
      ▼
Sorted ContextCandidates

The engine is a **pure function**.

- No filesystem access.
- No source code parsing.
- No AST, LLM, embedding, or DSPARK usage.
- Same input always produces identical output.

Public API
----------

.. code-block:: python

    engine = RankingEngine()
    ranked = engine.rank(query_text, candidates)

Ranking Model
-------------

Each candidate receives:

- ``score`` (int): additive relevance score.
- ``reasons`` (list[RankingReason]): explainability signals.

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

Tie Breaking
------------

Candidates are sorted by:

1. ``score`` descending.
2. ``qualified_name`` ascending.

No other ordering is permitted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.context.models import ContextCandidate
from packages.context.scoring import normalise_query_text, score_candidate

if TYPE_CHECKING:
    from packages.context.scoring import RankingReason


class RankingEngine:
    """Score and rank ``ContextCandidate`` instances against a query.

    Attributes:
        None — the engine is stateless.
    """

    def rank(
        self,
        query_text: str,
        candidates: list[ContextCandidate],
    ) -> list[ContextCandidate]:
        """Rank candidates by relevance to the query.

        Each candidate is scored, annotated with ``score`` and ``reasons``,
        then sorted by score descending and qualified_name ascending.

        Args:
            query_text: Raw query text from the user.
            candidates: Unranked candidate symbols.

        Returns:
            Candidates ordered by relevance (deterministic).
        """
        query_tokens = normalise_query_text(query_text)

        # Score each candidate.
        scored: list[tuple[int, str, list[RankingReason], ContextCandidate]] = []
        for candidate in candidates:
            s, reasons = score_candidate(candidate, query_tokens)
            scored.append((s, candidate.qualified_name, reasons, candidate))

        # Sort: score descending, qualified_name ascending.
        scored.sort(key=lambda t: (-t[0], t[1]))

        # Attach score and reasons back to candidates.
        for s, _qname, reasons, candidate in scored:
            candidate.score = s
            candidate.reasons = reasons

        return [c for _, _, _, c in scored]
