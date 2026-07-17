"""Deterministic Ranking Engine.

Scores ``ContextCandidate`` instances against a user query and returns
them ordered by relevance.

Architecture
------------

Query
      |
      v
RankingEngine
      |
      v
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
| Filename match | +40 |
| Module name contains query token | +30 |
| Matching query token | +10 per token |
| Public symbol (name does not start with "_") | +5 |

Relationship signals (optional, enabled via constructor):

| Rule | Score |
|------|------:|
| Shared module | +15 |
| Shared class | +25 |
| Direct caller | +20 |
| Direct callee | +20 |
| Shared parent | +25 |

Tie Breaking
------------

Candidates are sorted by:

1. ``score`` descending.
2. ``qualified_name`` ascending.

No other ordering is permitted.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from packages.context.models import ContextCandidate
from packages.context.scoring import (
    normalise_query_text,
    score_candidate,
    score_relationship,
)

if TYPE_CHECKING:
    from packages.context.scoring import RankingReason


class RankingEngine:
    """Score and rank ``ContextCandidate`` instances against a query.

    Attributes:
        _symbol_graph_view: Optional SymbolGraphView for relationship scoring.
        _primary_symbol: Optional primary symbol for relationship scoring.
        _relationship_enabled: Whether relationship signals are applied.
        _expansion_enabled: Whether relationship expansion is applied.
    """

    def __init__(
        self,
        symbol_graph_view: Any | None = None,
        primary_symbol: ContextCandidate | None = None,
        relationship_enabled: bool | None = None,
        expansion_enabled: bool | None = None,
    ) -> None:
        """Initialise the ranking engine.

        Args:
            symbol_graph_view: Optional SymbolGraphView for relationship lookups.
                Accepts any duck-typed object with ``callers``, ``callees``,
                ``parents``, and ``children`` methods.
            primary_symbol: Optional primary symbol for relationship scoring.
            relationship_enabled: Whether relationship signals are applied.
                Defaults to ``True`` if environment variable
                ``RELATIONSHIP_RANKING_ENABLED`` is not ``"false"``.
            expansion_enabled: Whether relationship expansion is applied.
                Defaults to ``True`` if environment variable
                ``RELATIONSHIP_EXPANSION_ENABLED`` is not ``"false"``.
        """
        # Determine defaults from environment variables.
        if relationship_enabled is None:
            relationship_enabled = os.environ.get(
                "RELATIONSHIP_RANKING_ENABLED", "true"
            ) != "false"
        if expansion_enabled is None:
            expansion_enabled = os.environ.get(
                "RELATIONSHIP_EXPANSION_ENABLED", "true"
            ) != "false"

        self._symbol_graph_view = symbol_graph_view
        self._primary_symbol = primary_symbol
        self._relationship_enabled = relationship_enabled
        self._expansion_enabled = expansion_enabled

    @property
    def relationship_enabled(self) -> bool:
        """Whether relationship scoring is enabled."""
        return self._relationship_enabled

    @property
    def expansion_enabled(self) -> bool:
        """Whether relationship expansion is enabled."""
        return self._expansion_enabled

    def rank(
        self,
        query_text: str,
        candidates: list[ContextCandidate],
        max_tokens: int = 4096,
    ) -> list[ContextCandidate]:
        """Rank candidates by relevance to the query.

        Each candidate is scored, annotated with ``score`` and ``reasons``,
        then sorted by score descending and qualified_name ascending.

        If relationship-aware ranking is enabled, relationship signals are
        added to candidates that have a relationship to the primary symbol.

        If relationship expansion is enabled, direct callers and callees of
        the primary symbol are appended to the candidate list (after the
        main ranking pass) within the token budget.

        Args:
            query_text: Raw query text from the user.
            candidates: Unranked candidate symbols.
            max_tokens: Token budget for context expansion.

        Returns:
            Candidates ordered by relevance (deterministic).
        """
        query_tokens = normalise_query_text(query_text)

        # Score each candidate with lexical signals.
        scored: list[tuple[int, str, list[RankingReason], ContextCandidate]] = []
        for candidate in candidates:
            s, reasons = score_candidate(candidate, query_tokens)
            scored.append((s, candidate.qualified_name, reasons, candidate))

        # Add relationship signals if enabled.
        if self._relationship_enabled and self._symbol_graph_view is not None:
            for i, (s, qualified_name, reasons, candidate) in enumerate(scored):
                rel_score, rel_reasons = score_relationship(
                    candidate=candidate,
                    primary_symbol=self._primary_symbol,
                    symbol_graph_view=self._symbol_graph_view,
                    relationship_enabled=True,
                )
                if rel_score > 0:
                    scored[i] = (
                        s + rel_score,
                        qualified_name,
                        reasons + rel_reasons,
                        candidate,
                    )

        # Sort: score descending, qualified_name ascending.
        scored.sort(key=lambda t: (-t[0], t[1]))

        # Attach score and reasons back to candidates.
        for s, _qname, reasons, candidate in scored:
            candidate.score = s
            candidate.reasons = reasons

        ranked: list[ContextCandidate] = [c for _, _, _, c in scored]

        # Relationship expansion: add direct callers/callees.
        if self._expansion_enabled and self._symbol_graph_view is not None:
            ranked = self._expand_with_relationships(ranked, max_tokens)

        return ranked

    def _expand_with_relationships(
        self,
        ranked: list[ContextCandidate],
        max_tokens: int,
    ) -> list[ContextCandidate]:
        """Expand the ranked list with relationship candidates.

        Appends direct callers and callees of the primary symbol to the
        end of the ranked list.  Only candidates not already present are
        added.  Budget constraints always win.

        Args:
            ranked: The already-ranked candidate list.
            max_tokens: Token budget for context expansion.

        Returns:
            The expanded candidate list.
        """
        if self._primary_symbol is None or self._symbol_graph_view is None:
            return ranked

        # Estimate tokens for existing candidates.
        existing_tokens = self._estimate_tokens(ranked)

        # Collect expansion candidates: direct callers first, then callees.
        expansion_candidates: list[ContextCandidate] = []
        seen_ids: set[str] = {c.symbol_id for c in ranked}

        try:
            # Direct callers.
            callers = self._symbol_graph_view.callers(self._primary_symbol)
            for caller in callers:
                if caller.qualified_name not in seen_ids:
                    expansion_candidates.append(ContextCandidate(
                        symbol_id=caller.qualified_name,
                        qualified_name=caller.qualified_name,
                        module=caller.module,
                    ))
                    seen_ids.add(caller.qualified_name)

            # Direct callees.
            callees = self._symbol_graph_view.callees(self._primary_symbol)
            for callee in callees:
                if callee.qualified_name not in seen_ids:
                    expansion_candidates.append(ContextCandidate(
                        symbol_id=callee.qualified_name,
                        qualified_name=callee.qualified_name,
                        module=callee.module,
                    ))
                    seen_ids.add(callee.qualified_name)
        except (AttributeError, TypeError):
            # Symbol graph view doesn't have expected methods.
            return ranked

        # Score expansion candidates with relationship signals only.
        for candidate in expansion_candidates:
            rel_score, rel_reasons = score_relationship(
                candidate=candidate,
                primary_symbol=self._primary_symbol,
                symbol_graph_view=self._symbol_graph_view,
                relationship_enabled=True,
            )
            candidate.score = rel_score
            candidate.reasons = rel_reasons

        # Sort expansion candidates by score descending, qualified_name ascending.
        expansion_candidates.sort(
            key=lambda c: (-c.score, c.qualified_name)
        )

        # Add expansion candidates within budget.
        result: list[ContextCandidate] = list(ranked)
        for candidate in expansion_candidates:
            est = self._estimate_tokens_for_candidate(candidate)
            if existing_tokens + est <= max_tokens:
                result.append(candidate)
                existing_tokens += est
            else:
                break

        return result

    @staticmethod
    def _estimate_tokens(candidates: list[ContextCandidate]) -> int:
        """Estimate token count for a list of candidates.

        Each candidate is estimated at ~100 tokens.

        Args:
            candidates: The candidate list.

        Returns:
            Estimated token count.
        """
        return len(candidates) * 100

    @staticmethod
    def _estimate_tokens_for_candidate(candidate: ContextCandidate) -> int:
        """Estimate token count for a single candidate.

        Args:
            candidate: The candidate.

        Returns:
            Estimated token count (~100 per candidate).
        """
        return 100
