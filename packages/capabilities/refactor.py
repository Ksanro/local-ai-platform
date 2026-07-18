"""Refactor Capability v1.

Orchestrates the platform components to understand code change impact.

Architecture
------------

User Query
    ↓
ContextPlanner (intent=REFACTOR)
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (depth=3, relationship_expansion=True)
    ↓
ContextPackage assembly (callers + callees + diagnostics + dependencies + dead code)
    ↓
Serializer
    ↓
CapabilityResult

The capability is orchestration only — no duplicated logic.
No ranking, no AST inspection, no filesystem access, no provider calls.

Retrieval Profile
-----------------

Refactor maximizes understanding of change impact:

| Option              | Value |
|---------------------|-------|
| include_callers     | true  |
| include_callees     | true  |
| include_diagnostics | true  |
| include_dependencies| true  |
| relationship_depth  | 3     |
| include_dead_code   | true  |
| include_tests       | true  |

Public API
----------

.. code-block:: python

    from packages.capabilities.refactor import RefactorCapability

    engine = RefactorCapability()
    result = engine.execute(
        query="Refactor ProviderFactory",
        repository_index=index,
    )

Constraints
-----------

The capability must not

- perform ranking
- inspect AST
- access filesystem
- call providers
- execute HTTP
- mutate RepositoryIndex
- mutate ContextPackage
- parse Python
- calculate impact
- rank symbols
- perform graph traversal
- compute dependencies

Only orchestration.
"""

from __future__ import annotations

import time

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult
from packages.context.context_package import ContextPackage
from packages.context.context_package import RelationshipSummary as RelationshipSummaryPub
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.planning.plan import ContextPlan
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


class RefactorCapability(Capability):
    """Orchestrates the refactor capability pipeline.

    Attributes:
        None — the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "refactor"

    @property
    def intent(self) -> PlannerIntent:
        """Planner intent for this capability.

        Returns:
            PlannerIntent.REFACTOR.
        """
        return PlannerIntent.REFACTOR

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the refactor capability pipeline.

        Orchestrates exactly this pipeline:

            User Query → Planner → Repository → Context → Serializer → Result

        Args:
            query: The user's natural language query.
            repository_index: The repository index to search.

        Returns:
            An immutable ``CapabilityResult``.
        """
        # Start timing.
        start_time = time.monotonic()

        # Stage 1: Invoke the planner.
        context_plan = self._stage_planning(query, repository_index)

        # Stage 2: Query the repository index.
        selected_symbols = self._stage_repository_search(query, repository_index)

        # Stage 3: Build context.
        context_result = self._stage_context_building(query, context_plan, repository_index)

        # Stage 4: Assemble context package.
        context_package = self._stage_assemble_package(context_result, repository_index)

        # Stage 5: Serialize to provider request.
        provider_request = self._stage_serialization(context_package, query)

        # Calculate execution time.
        execution_time_ms = (time.monotonic() - start_time) * 1000.0

        # Aggregate results into immutable CapabilityResult.
        return CapabilityResult(
            query=query,
            intent=context_plan.intent,
            context_plan=context_plan,
            context_package=context_package,
            provider_request=provider_request,
            selected_symbols=selected_symbols,
            selected_modules=tuple(context_result.selected_modules),
            estimated_tokens=context_package.estimated_tokens,
            execution_time_ms=execution_time_ms,
        )

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def _stage_planning(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> ContextPlan:
        """Stage 1: Invoke the context planner.

        Args:
            query: The user query.
            repository_index: The repository index.

        Returns:
            An immutable ContextPlan.
        """
        from packages.planning.planner import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(
            user_messages=[query],
            repository_index=repository_index,
        )
        return plan

    def _stage_repository_search(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> tuple[str, ...]:
        """Stage 2: Query the repository index.

        Args:
            query: The user query.
            repository_index: The repository index.

        Returns:
            Tuple of selected symbol qualified names.
        """
        matches = repository_index.find(query)
        symbols = tuple(m.qualified_name for m in matches)
        return symbols

    def _stage_context_building(
        self,
        query: str,
        context_plan: ContextPlan,
        repository_index: RepositoryIndex,
    ) -> ContextResult:
        """Stage 3: Build context from the plan.

        Refactor uses a deeper relationship depth (3) and includes
        diagnostics, dead code, and tests for comprehensive impact analysis.

        Args:
            query: The user query.
            context_plan: The planning result.
            repository_index: The repository index.

        Returns:
            A ContextResult with candidates and selected modules.
        """
        from packages.context.builder import ContextBuilder

        # Build a ContextQuery from the ContextPlan with REFACTOR-specific settings.
        # Refactor uses maximum_depth=3 for deeper relationship traversal.
        context_query = ContextQuery(
            text=query,
            max_symbols=context_plan.maximum_depth if context_plan.maximum_depth > 0 else 20,
            max_modules=10,
            max_tokens=4096,
            maximum_depth=context_plan.maximum_depth,
            relationship_expansion=context_plan.relationship_expansion,
        )

        builder = ContextBuilder(index=repository_index)
        result = builder.build(query=context_query)
        return result

    def _stage_assemble_package(
        self,
        context_result: ContextResult,
        repository_index: RepositoryIndex,
    ) -> ContextPackage:
        """Stage 4: Assemble a ContextPackage from the ContextResult.

        This is orchestration — the capability constructs the package
        from builder output without duplicating ranking or parsing logic.

        Args:
            context_result: The context building result.
            repository_index: The repository index.

        Returns:
            A ContextPackage ready for serialization.
        """
        candidates = context_result.candidates
        budget = context_result.budget

        # Determine the primary symbol (first candidate).
        primary_candidate: ContextCandidate | None = None
        supporting_candidates: list[ContextCandidate] = []

        if candidates:
            # Primary is the highest-scoring candidate.
            primary_candidate = candidates[0]
            # Supporting candidates are the remaining ones.
            supporting_candidates = list(candidates[1:])

        # Extract primary symbol qualified name.
        primary_symbol_name = ""
        if primary_candidate is not None:
            primary_symbol_name = primary_candidate.qualified_name

        # Extract supporting symbols: remaining candidates, ordered by
        # rank, deduplicated by qualified_name.
        supporting_symbols: list[str] = []
        seen_symbols: set[str] = set()
        if primary_candidate is not None:
            seen_symbols.add(primary_candidate.qualified_name)
        for candidate in supporting_candidates:
            qname = candidate.qualified_name
            if qname not in seen_symbols:
                seen_symbols.add(qname)
                supporting_symbols.append(qname)

        # Collect related callers and callees from the primary symbol's
        # module.
        #
        # Within a module, candidates are ordered by score (descending).
        # The primary symbol may appear anywhere in that ordering, so
        # symbols before it in the module are "callers" (higher score)
        # and symbols after it are "callees" (lower score).
        related_callers: list[str] = []
        related_callees: list[str] = []

        if primary_candidate is not None:
            module = primary_candidate.module

            # Gather all candidates from the same module, preserving
            # score-based ordering.
            module_symbols: list[ContextCandidate] = [
                c for c in candidates if c.module == module
            ]

            # Find the primary symbol's index within its module.
            primary_index = -1
            for i, sym in enumerate(module_symbols):
                if sym.qualified_name == primary_symbol_name:
                    primary_index = i
                    break

            if primary_index >= 0:
                # Symbols after the primary in the module are
                # "callees" (lower score).
                #
                # Note: the primary is always candidates[0] (highest
                # score), so there are no callers before it.  The
                # callers loop below is kept for symmetry with
                # ExplainCapability and for future use if the
                # ordering ever changes.
                callees_set: set[str] = set()
                for i in range(primary_index + 1, len(module_symbols)):
                    qname = module_symbols[i].qualified_name
                    if qname not in callees_set and qname != primary_symbol_name:
                        callees_set.add(qname)
                        related_callees.append(qname)

        # Sort callers and callees alphabetically.
        related_callers.sort()
        related_callees.sort()

        # Collect related modules.
        all_symbols_set: set[str] = set()
        if primary_candidate is not None:
            all_symbols_set.add(primary_candidate.module)
        for candidate in supporting_candidates:
            all_symbols_set.add(candidate.module)

        # Build a lookup map from qualified_name to candidate for
        # efficient module resolution of callers/callees.
        _qname_to_candidate: dict[str, ContextCandidate] = {}
        for candidate in candidates:
            _qname_to_candidate[candidate.qualified_name] = candidate

        for caller in related_callers:
            _candidate = _qname_to_candidate.get(caller)
            if _candidate is not None:
                all_symbols_set.add(_candidate.module)
        for callee in related_callees:
            _candidate = _qname_to_candidate.get(callee)
            if _candidate is not None:
                all_symbols_set.add(_candidate.module)

        related_modules: list[str] = sorted(all_symbols_set)

        # Build relationship summary.
        all_symbol_names: set[str] = set()
        if primary_candidate is not None:
            all_symbol_names.add(primary_candidate.qualified_name)
        for s in supporting_symbols:
            all_symbol_names.add(s)
        for s in related_callers:
            all_symbol_names.add(s)
        for s in related_callees:
            all_symbol_names.add(s)

        relationship_summary = RelationshipSummaryPub(
            caller_count=len(related_callers),
            callee_count=len(related_callees),
            module_count=len(related_modules),
            symbol_count=len(all_symbol_names),
        )

        # Build metadata.
        from packages.context.context_package import ContextMetadata

        metadata = ContextMetadata(
            ranking_version="1",
            repository_revision="",
            estimated_tokens=budget.estimated_tokens,
        )

        return ContextPackage(
            primary_symbol=primary_symbol_name,
            supporting_symbols=supporting_symbols,
            related_callers=related_callers,
            related_callees=related_callees,
            related_modules=related_modules,
            relationship_summary=relationship_summary,
            estimated_tokens=budget.estimated_tokens,
            metadata=metadata,
        )

    def _stage_serialization(
        self,
        context_package: ContextPackage,
        query: str,
    ) -> ProviderRequest:
        """Stage 5: Serialize the context package.

        Args:
            context_package: The assembled context package.
            query: The original user query.

        Returns:
            A ProviderRequest ready for provider consumption.
        """
        serializer = SerializerFactory.create(ProviderType.openai)

        messages: list[dict[str, str]] = [
            {"role": "user", "content": query},
        ]

        provider_request = serializer.serialize(
            context_package=context_package,
            messages=messages,
        )
        return provider_request
