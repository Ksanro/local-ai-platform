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

from packages.context.budget import CHARS_PER_TOKEN, ContextBudget
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
    ContextResult,
)
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
                symbol_type=(
                    sym.symbol_type.value
                    if hasattr(sym.symbol_type, "value")
                    else str(sym.symbol_type)
                ),
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
        # The RankingEngine consumes ContextPlan retrieval hints to
        # bias candidate scoring based on engineering intent.
        engine = RankingEngine(
            symbol_graph_view=graph_view if relationship_enabled else None,
            primary_symbol=primary_symbol if relationship_enabled else None,
            relationship_enabled=relationship_enabled,
            expansion_enabled=expansion_enabled,
            token_estimator=self._estimate_candidate_tokens_for_ranking,
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

        # Enforce the context token budget after enrichment, where actual
        # source/docstring content is available to estimate.
        candidates, selected_modules, budget = self._enforce_budget(
            candidates,
            selected_modules,
            query.max_tokens,
        )

        return ContextResult(
            candidates=candidates,
            selected_modules=selected_modules,
            budget=budget,
        )

    def _enforce_budget(
        self,
        candidates: list[ContextCandidate],
        selected_modules: list[str],
        max_tokens: int,
    ) -> tuple[list[ContextCandidate], list[str], ContextBudgetResult]:
        """Trim enriched context until it fits the configured token budget.

        Keeps the primary candidate whenever possible, drops supporting
        candidates from the tail, then trims verbose primary/supporting
        source fields if the remaining package is still over budget.
        """
        budget_engine = ContextBudget()
        effective_max = max_tokens if max_tokens > 0 else 4096
        budget = budget_engine.estimate(candidates, selected_modules, effective_max)
        if budget.within_budget:
            return candidates, selected_modules, budget

        trimmed = list(candidates)
        while len(trimmed) > 1:
            trimmed.pop()
            modules = self._select_modules_for_candidates(trimmed, selected_modules)
            budget = budget_engine.estimate(trimmed, modules, effective_max)
            if budget.within_budget:
                return trimmed, modules, budget

        if trimmed:
            modules = self._select_modules_for_candidates(trimmed, selected_modules)
            self._trim_candidate_content_to_budget(trimmed[0], modules, effective_max)

        modules = self._select_modules_for_candidates(trimmed, selected_modules)
        budget = budget_engine.estimate(trimmed, modules, effective_max)
        return trimmed, modules, budget

    @staticmethod
    def _select_modules_for_candidates(
        candidates: list[ContextCandidate],
        selected_modules: list[str],
    ) -> list[str]:
        """Keep selected modules that still have included candidates."""
        candidate_modules = {candidate.module for candidate in candidates}
        return [module for module in selected_modules if module in candidate_modules]

    @staticmethod
    def _trim_candidate_content_to_budget(
        candidate: ContextCandidate,
        selected_modules: list[str],
        max_tokens: int,
    ) -> None:
        """Trim verbose candidate fields to fit approximately within budget."""
        max_chars = max(0, (max_tokens * 4) - 4)
        fixed_chars = (
            len(candidate.qualified_name)
            + len(candidate.module)
            + len(candidate.signature)
            + sum(len(module) for module in selected_modules)
        )
        available_chars = max(0, max_chars - fixed_chars)

        if candidate.source and len(candidate.source) > available_chars:
            candidate.source = candidate.source[:available_chars]
            candidate.source_preview = ""
            candidate.docstring = ""
            return

        used = len(candidate.source) + len(candidate.source_preview)
        remaining = max(0, available_chars - used)
        if candidate.docstring and len(candidate.docstring) > remaining:
            candidate.docstring = candidate.docstring[:remaining]

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

            raw_signature = full_context.get("signature", "")
            raw_docstring = full_context.get("docstring", "")
            raw_decorators = full_context.get("decorators", [])
            location = full_context.get("location", None)
            raw_source = full_context.get("source", "")

            signature = raw_signature if isinstance(raw_signature, str) else ""
            docstring = raw_docstring if isinstance(raw_docstring, str) else ""
            decorators = (
                raw_decorators
                if isinstance(raw_decorators, list)
                and all(isinstance(item, str) for item in raw_decorators)
                else []
            )
            source = raw_source if isinstance(raw_source, str) else ""

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
                        remaining_support_tokens = max(
                            0,
                            remaining_support_tokens - estimated_tokens,
                        )
                elif source:
                    # Still count lines even if no preview.
                    candidate.source_lines = len(source.splitlines()) if source else 0

        return candidates

    def _estimate_candidate_tokens_for_ranking(
        self,
        candidate: ContextCandidate,
        is_primary: bool,
    ) -> int:
        """Estimate candidate cost using the same content model as final budget."""
        total_chars = len(candidate.qualified_name) + len(candidate.module)

        full_context = self._index.get_symbol_full_context(candidate.qualified_name)
        if full_context is None:
            return max(1, int(total_chars / CHARS_PER_TOKEN))

        signature = full_context.get("signature", "")
        docstring = full_context.get("docstring", "")
        source = full_context.get("source", "")

        if isinstance(signature, str):
            total_chars += len(signature)
        if isinstance(docstring, str):
            total_chars += len(docstring)

        if is_primary:
            if isinstance(source, str):
                total_chars += len(source)
        else:
            preview = self._index.get_symbol_source_excerpts(
                candidate.qualified_name,
                max_tokens=self._supporting_symbol_max_tokens,
            )
            if preview:
                total_chars += len(preview)

        return max(1, int(total_chars / CHARS_PER_TOKEN))
