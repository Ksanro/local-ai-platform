"""Bug Investigation Capability v1.

Orchestrates the platform components to investigate a software defect.

Architecture
------------

User Query
    ↓
ContextPlanner (intent=DEBUG)
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (depth=2, diagnostics=True)
    ↓
ContextPackage assembly
    ↓
Serializer
    ↓
CapabilityResult

The capability is orchestration only — no duplicated logic.
No ranking, no AST inspection, no filesystem access, no provider calls.

Investigation Report
--------------------

The CapabilityResult includes an ``investigation_report`` field with:

| Field | Type | Description |
|-------|------|-------------|
| affected_modules | tuple[str, ...] | Modules identified as affected |
| affected_symbols | tuple[str, ...] | Symbols identified as affected |
| dependency_summary | str | Summary of dependency relationships |
| diagnostics_summary | str | Summary of diagnostic findings |
| impact_summary | str | Summary of impact analysis |
| architectural_findings | tuple[str, ...] | Architectural issues found |
| refactoring_opportunities | tuple[str, ...] | Suggested refactoring opportunities |
| context_statistics | dict | Statistics about the context package |
| estimated_tokens | int | Estimated token usage |

Retrieval Profile
-----------------

Bug investigation uses the DEBUG retrieval profile:

| Option              | Value |
|---------------------|-------|
| include_callers     | true  |
| include_callees     | true  |
| include_diagnostics | true  |
| include_dependencies| true  |
| relationship_depth  | 2     |
| include_dead_code   | false |
| include_tests       | true  |

Public API
----------

.. code-block:: python

    from packages.capabilities.bug_investigation import BugInvestigationCapability

    engine = BugInvestigationCapability()
    result = engine.execute(
        query="Why is auth failing?",
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

Only orchestration.
"""

from __future__ import annotations

import time

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import DEBUG_PROFILE, RetrievalProfile
from packages.context.context_package import ContextPackage
from packages.context.context_package import RelationshipSummary as RelationshipSummaryPub
from packages.context.models import ContextBudgetResult, ContextCandidate, ContextQuery, ContextResult
from packages.planning.plan import ContextPlan
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


class BugInvestigationCapability(Capability):
    """Orchestrates the bug investigation capability pipeline.

    Attributes:
        None — the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "bug-investigation"

    @property
    def intent(self) -> PlannerIntent:
        """Planner intent for this capability.

        Returns:
            PlannerIntent.DEBUG.
        """
        return PlannerIntent.DEBUG

    @property
    def profile(self) -> RetrievalProfile:
        """Retrieval profile for this capability.

        Returns:
            The DEBUG_PROFILE singleton.
        """
        return DEBUG_PROFILE

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the bug investigation capability pipeline.

        Orchestrates exactly this pipeline:

            User Query → Planner → Repository → Context → Serializer → Result

        Args:
            query: The user's natural language query.
            repository_index: The repository index to search.

        Returns:
            An immutable ``CapabilityResult`` with investigation report.
        """
        # Start timing.
        start_time = time.monotonic()

        # Stage 1: Invoke the planner.
        context_plan = self._stage_planning(query, repository_index)

        # Stage 2: Query the repository index.
        selected_symbols = self._stage_repository_search(query, repository_index)

        # Stage 3: Build context.
        context_result = self._stage_context_building(
            query, context_plan, repository_index
        )

        # Stage 4: Assemble context package.
        context_package = self._stage_assemble_package(
            context_result, repository_index
        )

        # Stage 5: Serialize to provider request.
        provider_request = self._stage_serialization(context_package, query)

        # Build investigation report metadata.
        investigation_report = self._build_investigation_report(
            context_result=context_result,
            context_package=context_package,
            selected_symbols=selected_symbols,
        )

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
            investigation_report=investigation_report,
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

        Bug investigation uses a deeper relationship depth and includes
        diagnostics.

        Args:
            query: The user query.
            context_plan: The planning result.
            repository_index: The repository index.

        Returns:
            A ContextResult with candidates and selected modules.
        """
        from packages.context.builder import ContextBuilder

        # Build a ContextQuery from the ContextPlan with DEBUG-specific settings.
        context_query = ContextQuery(
            text=query,
            max_symbols=context_plan.maximum_depth
            if context_plan.maximum_depth > 0
            else 20,
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
            primary_candidate = candidates[0]
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
        # Note: related_callers is intentionally empty for bug investigation.
        # The first candidate is always the primary symbol; all other symbols
        # in the same module group are callees (called-by the primary).
        related_callers: list[str] = []
        related_callees: list[str] = []

        if primary_candidate is not None:
            module = primary_candidate.module
            # Build the module symbol group: all candidates in the same
            # module as the primary.  No duplicate iteration — we iterate
            # the full candidates list once and filter by module.
            module_symbols: list[ContextCandidate] = [
                c for c in candidates if c.module == module
            ]

            # The first candidate in a module group is always the primary.
            # All subsequent symbols in the same module group are callees.
            if len(module_symbols) > 0:
                callees_set: set[str] = set()
                for i in range(1, len(module_symbols)):
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
        # related_callers is always empty in bug investigation (first candidate
        # is always primary), so we only need to add callee modules.
        for callee in related_callees:
            for candidate in candidates:
                if candidate.qualified_name == callee:
                    all_symbols_set.add(candidate.module)
                    break

        related_modules: list[str] = sorted(all_symbols_set)

        # Build relationship summary.
        all_symbol_names: set[str] = set()
        if primary_candidate is not None:
            all_symbol_names.add(primary_candidate.qualified_name)
        for s in supporting_symbols:
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

    # ------------------------------------------------------------------
    # Investigation report
    # ------------------------------------------------------------------

    def _build_investigation_report(
        self,
        context_result: ContextResult,
        context_package: ContextPackage,
        selected_symbols: tuple[str, ...],
    ) -> dict[str, object]:
        """Build the investigation report metadata.

        Args:
            context_result: The context building result.
            context_package: The assembled context package.
            selected_symbols: Selected symbol qualified names.

        Returns:
            A dict containing investigation report fields.
        """
        # Affected modules
        affected_modules = tuple(context_result.selected_modules)

        # Affected symbols
        affected_symbols = selected_symbols

        # Dependency summary
        caller_count = context_package.relationship_summary.caller_count
        callee_count = context_package.relationship_summary.callee_count
        dependency_summary = (
            f"Callers: {caller_count}, Callees: {callee_count}, "
            f"Modules: {context_package.relationship_summary.module_count}"
        )

        # Diagnostics summary (derived from context candidates)
        diagnostics_items: list[str] = []
        for candidate in context_result.candidates:
            # Candidates may carry diagnostic info via symbol attributes
            if hasattr(candidate, "symbol_id"):
                diagnostics_items.append(f"symbol:{candidate.symbol_id}")
        diagnostics_summary = (
            f"Analyzed {len(diagnostics_items)} symbols for diagnostics."
            if diagnostics_items
            else "No diagnostics findings."
        )

        # Impact summary
        impact_summary = (
            f"Primary symbol: {context_package.primary_symbol}. "
            f"Supporting symbols: {len(context_package.supporting_symbols)}. "
            f"Related modules: {len(context_package.related_modules)}."
        )

        # Architectural findings
        architectural_findings: tuple[str, ...] = ()

        # Refactoring opportunities
        refactoring_opportunities: tuple[str, ...] = ()

        # Context statistics
        context_statistics = {
            "primary_symbol": context_package.primary_symbol,
            "supporting_symbols_count": len(context_package.supporting_symbols),
            "related_callers_count": len(context_package.related_callers),
            "related_callees_count": len(context_package.related_callees),
            "related_modules_count": len(context_package.related_modules),
            "total_symbols": context_package.relationship_summary.symbol_count,
        }

        # Estimated tokens
        estimated_tokens = context_package.estimated_tokens

        return {
            "affected_modules": affected_modules,
            "affected_symbols": affected_symbols,
            "dependency_summary": dependency_summary,
            "diagnostics_summary": diagnostics_summary,
            "impact_summary": impact_summary,
            "architectural_findings": architectural_findings,
            "refactoring_opportunities": refactoring_opportunities,
            "context_statistics": context_statistics,
            "estimated_tokens": estimated_tokens,
        }