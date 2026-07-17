"""Context Builder.

Assembles repository context for future coding agents by enumerating
symbols from a ``RepositoryIndex`` and returning them in a deterministic
order.

Architecture
------------

Repository
      |
      v
ContextBuilder
      |
      v
RankingEngine
      |
      v
ContextBudget
      |
      v
ContextResult

The Builder depends only on the public ``RepositoryIndex`` API.  It
never accesses the filesystem, parses source code, or touches AST
objects.

Current behaviour
-----------------

Symbols are scored against the query text using the ``RankingEngine``,
estimated against a token budget via ``ContextBudget``, and returned
in relevance order, bounded by ``max_symbols`` and ``max_modules``.

Relationship-aware ranking is supported via the ``SymbolGraphView``
from the repository index.  When enabled, relationship signals are
added to candidates and direct callers/callees may be expanded.

Future extensions (semantic search, DSPARK, memory, Git awareness)
will replace the default ranking strategy without changing the public
API.
"""

from __future__ import annotations

import os

from packages.context.budget import ContextBudget
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.context.ranking import RankingEngine
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.models import Symbol


class ContextBuilder:
    """Assembles repository context from a repository index.

    Attributes:
        _index: The repository index to draw symbols from.
    """

    def __init__(self, index: RepositoryIndex) -> None:
        """Initialise the builder.

        Args:
            index: A ``RepositoryIndex`` providing access to repository
                symbols.
        """
        self._index = index

    def build(
        self,
        query: ContextQuery,
        primary_symbol: ContextCandidate | None = None,
    ) -> ContextResult:
        """Build context from the given query.

        Enumerates all symbols from the repository, scores them against
        the query text using ``RankingEngine``, and applies
        ``max_symbols`` and ``max_modules`` constraints.

        If a ``primary_symbol`` is provided and relationship-aware ranking
        is enabled (via ``RELATIONSHIP_RANKING_ENABLED`` environment
        variable), relationship signals are added and direct callers/callees
        may be expanded.

        Args:
            query: The context query specifying text and limits.
            primary_symbol: Optional primary symbol for relationship scoring
                and expansion.

        Returns:
            A ``ContextResult`` with candidates and selected modules.
        """
        # Enumerate all symbols from the repository.
        all_symbols: list[Symbol] = list(self._index.symbols())

        # Convert to candidates.
        candidates: list[ContextCandidate] = [
            ContextCandidate(
                symbol_id=sym.id,
                qualified_name=sym.qualified_name,
                module=sym.module,
            )
            for sym in all_symbols
        ]

        # Build a SymbolGraphView for relationship lookups.
        from packages.repository.symbols.graph import SymbolGraph

        graph = SymbolGraph(modules=self._index.modules)
        graph_view: SymbolGraphView = SymbolGraphView(graph)

        # Determine relationship configuration from the query (driven by
        # ContextPlan) with environment-variable fallback for backward
        # compatibility.
        relationship_enabled = (
            os.environ.get("RELATIONSHIP_RANKING_ENABLED", "true") != "false"
            and query.relationship_expansion
        )
        expansion_enabled = (
            os.environ.get("RELATIONSHIP_EXPANSION_ENABLED", "true") != "false"
            and query.relationship_expansion
        )

        # Rank candidates by relevance to the query text.
        engine = RankingEngine(
            symbol_graph_view=graph_view if relationship_enabled else None,
            primary_symbol=primary_symbol if relationship_enabled else None,
            relationship_enabled=relationship_enabled,
            expansion_enabled=expansion_enabled,
        )
        candidates = engine.rank(query.text, candidates, max_tokens=query.max_tokens)

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
