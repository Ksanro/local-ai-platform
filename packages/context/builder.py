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
enriched with source data (signatures, docstrings, source bodies),
estimated against a token budget via ``ContextBudget``, and returned
in relevance order, bounded by ``max_symbols`` and ``max_modules``.

Relationship-aware ranking is supported via the ``SymbolGraphView``
from the repository index.  When enabled, relationship signals are
added to candidates and direct callers/callees may be expanded.

Context Quality v2
------------------

For the PRIMARY symbol the builder provides:

- Complete source body
- Signature, docstring, decorators
- Source location

For SUPPORTING symbols the builder provides:

- Signature and docstring
- Short source preview (configurable budget)
- Source location

This replaces the previous identifier-only context with engineering-grade
source context that substantially improves LLM answer quality.

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
        _primary_symbol_max_tokens: Max tokens for primary symbol source.
        _supporting_symbol_max_tokens: Shared budget for supporting symbols.
        _maximum_supporting_symbols: Max supporting symbols to include.
        _maximum_module_descriptions: Max module descriptions to include.
    """

    def __init__(
        self,
        index: RepositoryIndex,
        primary_symbol_max_tokens: int = 2048,
        supporting_symbol_max_tokens: int = 512,
        maximum_supporting_symbols: int = 20,
        maximum_module_descriptions: int = 10,
    ) -> None:
        """Initialise the builder.

        Args:
            index: A ``RepositoryIndex`` providing access to repository
                symbols.
            primary_symbol_max_tokens: Maximum token budget for the primary
                symbol's complete source body.
            supporting_symbol_max_tokens: Maximum token budget shared across
                all supporting symbols.
            maximum_supporting_symbols: Maximum number of supporting symbols
                to include.
            maximum_module_descriptions: Maximum number of module descriptions
                to include.
        """
        self._index = index
        self._primary_symbol_max_tokens = primary_symbol_max_tokens
        self._supporting_symbol_max_tokens = supporting_symbol_max_tokens
        self._maximum_supporting_symbols = maximum_supporting_symbols
        self._maximum_module_descriptions = maximum_module_descriptions

    def build(
        self,
        query: ContextQuery,
        primary_symbol: ContextCandidate | None = None,
    ) -> ContextResult:
        """Build context from the given query.

        Enumerates all symbols from the repository, scores them against
        the query text using ``RankingEngine``, enriches them with source
        data (signatures, docstrings, source bodies), and applies
        ``max_symbols`` and ``max_modules`` constraints.

        Context Quality v2 enhancements:

        - PRIMARY symbol receives complete source body, signature, docstring,
          decorators, and location.
        - SUPPORTING symbols receive signature, docstring, short source
          preview, and location.
        - Source data is fetched from ``RepositoryIndex`` public APIs only.

        If a ``primary_symbol`` is provided and relationship-aware ranking
        is enabled (via ``RELATIONSHIP_RANKING_ENABLED`` environment
        variable), relationship signals are added and direct callers/callees
        may be expanded.

        Args:
            query: The context query specifying text and limits.
            primary_symbol: Optional primary symbol for relationship scoring
                and expansion.

        Returns:
            A ``ContextResult`` with candidates (enriched with source data)
            and selected modules.
        """
        # Enumerate all symbols from the repository.
        all_symbols: list[Symbol] = list(self._index.symbols())

        # Convert to candidates with engineering metadata.
        candidates: list[ContextCandidate] = []
        for sym in all_symbols:
            # Determine if symbol is exported from __init__.py.
            is_in_init_py = (
                "packages/__init__.py" in self._index.modules
                or "app/__init__.py" in self._index.modules
            ) and sym.module.endswith(("/__init__.py", "\\__init__.py"))

            candidates.append(ContextCandidate(
                symbol_id=sym.id,
                qualified_name=sym.qualified_name,
                module=sym.module,
                symbol_type=sym.symbol_type.value if hasattr(sym.symbol_type, 'value') else str(sym.symbol_type),
                is_in_init_py=is_in_init_py,
            ))

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

        # Enrich candidates with source data (Context Quality v2).
        candidates = self._enrich_with_source_data(candidates, primary_symbol)

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

        # Estimate context size against the token budget using actual
        # assembled content (Context Quality v2).
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

    def _enrich_with_source_data(
        self,
        candidates: list[ContextCandidate],
        primary_symbol: ContextCandidate | None,
    ) -> list[ContextCandidate]:
        """Enrich candidates with source data from the RepositoryIndex.

        For the PRIMARY symbol: fetch complete source body, signature,
        docstring, decorators, and location.

        For SUPPORTING symbols: fetch signature, docstring, short source
        preview, and location.

        Also populates source_lines for implementation size scoring.

        Args:
            candidates: Ranked candidate list.
            primary_symbol: Optional primary symbol.

        Returns:
            Enriched candidate list with source data populated.
        """
        if not candidates:
            return candidates

        # Determine which candidate is primary.
        primary_qualified_name = ""
        if primary_symbol is not None:
            primary_qualified_name = primary_symbol.qualified_name
        elif candidates:
            primary_qualified_name = candidates[0].qualified_name

        # Track remaining budget for supporting symbols.
        remaining_support_tokens = self._supporting_symbol_max_tokens

        for i, candidate in enumerate(candidates):
            is_primary = candidate.qualified_name == primary_qualified_name

            # Fetch full context from RepositoryIndex.
            full_context = self._index.get_symbol_full_context(
                candidate.qualified_name
            )

            if full_context is None:
                continue

            signature = full_context.get("signature", "")
            docstring = full_context.get("docstring", "")
            decorators = full_context.get("decorators", [])
            location = full_context.get("location", None)
            source = full_context.get("source", "")

            if is_primary:
                # PRIMARY: complete source body (within budget).
                candidate.signature = signature or ""
                candidate.docstring = docstring or ""
                candidate.decorators = decorators or []
                candidate.source = source or ""
                candidate.location = location if isinstance(location, tuple) else None
                # Count source lines for implementation size scoring.
                candidate.source_lines = len(source.splitlines()) if source else 0
            else:
                # SUPPORTING: signature, docstring, source preview.
                candidate.signature = signature or ""
                candidate.docstring = docstring or ""
                candidate.decorators = decorators or []
                candidate.location = location if isinstance(location, tuple) else None

                # Source preview within remaining budget.
                if source and remaining_support_tokens > 0:
                    preview = self._index.get_symbol_source_excerpts(
                        candidate.qualified_name,
                        max_tokens=remaining_support_tokens,
                    )
                    if preview:
                        candidate.source_preview = preview
                        # Count source lines for implementation size scoring.
                        candidate.source_lines = len(source.splitlines()) if source else 0
                        # Deduct from remaining budget.
                        estimated_tokens = len(preview) // 4
                        remaining_support_tokens = max(0, remaining_support_tokens - estimated_tokens)
                elif source:
                    # Still count lines even if no preview.
                    candidate.source_lines = len(source.splitlines()) if source else 0

        return candidates
