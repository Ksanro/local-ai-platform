"""Context Builder.

Assembles repository context for future coding agents by enumerating
symbols from a ``SymbolGraphView`` and returning them in a deterministic
order.

Architecture
------------

Repository
      │
      ▼
ContextBuilder
      │
      ▼
RankingEngine
      │
      ▼
ContextBudget
      │
      ▼
ContextResult

The Builder depends only on the public ``SymbolGraphView`` API.  It
never accesses the filesystem, parses source code, or touches AST
objects.

Current behaviour
-----------------

Symbols are scored against the query text using the ``RankingEngine``,
estimated against a token budget via ``ContextBudget``, and returned
in relevance order, bounded by ``max_symbols`` and ``max_modules``.

Future extensions (semantic search, DSPARK, memory, Git awareness)
will replace the default ranking strategy without changing the public
API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.context.budget import ContextBudget
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.context.ranking import RankingEngine
from packages.repository.symbols.models import Symbol

if TYPE_CHECKING:
    from packages.repository.symbols.graph import SymbolGraphView


class ContextBuilder:
    """Assembles repository context from a symbol graph.

    Attributes:
        graph_view: The read-only symbol graph view to draw symbols from.
    """

    def __init__(self, graph_view: SymbolGraphView) -> None:
        """Initialise the builder.

        Args:
            graph_view: A ``SymbolGraphView`` providing access to repository
                symbols.
        """
        self._graph_view = graph_view

    def build(self, query: ContextQuery) -> ContextResult:
        """Build context from the given query.

        Enumerates all symbols from the repository, scores them against
        the query text using ``RankingEngine``, and applies
        ``max_symbols`` and ``max_modules`` constraints.

        Args:
            query: The context query specifying text and limits.

        Returns:
            A ``ContextResult`` with candidates and selected modules.
        """
        # Enumerate all symbols from the repository.
        all_symbols: list[Symbol] = list(self._graph_view.symbols())

        # Convert to candidates.
        candidates: list[ContextCandidate] = [
            ContextCandidate(
                symbol_id=sym.id,
                qualified_name=sym.qualified_name,
                module=sym.module,
            )
            for sym in all_symbols
        ]

        # Rank candidates by relevance to the query text.
        engine = RankingEngine()
        candidates = engine.rank(query.text, candidates)

        # Apply max_symbols limit (0 means no candidates).
        if query.max_symbols > 0:
            candidates = candidates[: query.max_symbols]
        else:
            candidates = []

        # Derive selected_modules: unique, insertion order, bounded by max_modules.
        selected_modules: list[str] = []
        seen_modules: set[str] = set()
        max_modules = query.max_modules if query.max_modules > 0 else 0

        for candidate in candidates:
            if max_modules <= 0:
                break
            if candidate.module not in seen_modules:
                seen_modules.add(candidate.module)
                selected_modules.append(candidate.module)
                if len(selected_modules) >= max_modules:
                    break

        # Estimate context size against the token budget.
        budget_engine = ContextBudget()
        budget = budget_engine.estimate(
            candidates=candidates,
            modules=selected_modules,
            max_tokens=query.max_tokens,
        )

        return ContextResult(
            candidates=candidates,
            selected_modules=selected_modules,
            budget=budget,
        )
