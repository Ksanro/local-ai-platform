"""Architecture Review Capability.

Orchestrates the platform components to produce an architectural assessment.

Architecture
------------

User Query
    ↓
ArchitectureAnalyzer
    ↓
RepositoryIndex
    ↓
ArchitectureReview
    ↓
CapabilityResult

The capability is orchestration only — no duplicated logic.
No ranking, no AST inspection, no filesystem access, no provider calls.

Public API
----------

.. code-block:: python

    from packages.capabilities.architecture_review import ArchitectureReviewCapability

    engine = ArchitectureReviewCapability()
    result = engine.execute(
        query="Review the architecture",
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

Only orchestration.
"""

from __future__ import annotations

import time

from packages.architecture.analyzer import ArchitectureAnalyzer
from packages.architecture.models import ArchitectureReview
from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import (
    ARCHITECTURE_REVIEW_PROFILE,
    RetrievalProfile,
)
from packages.context.context_package import ContextPackage
from packages.context.context_package import RelationshipSummary as RelationshipSummaryPub
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.planning.plan import ContextPlan
from packages.repository.index.models import RepositoryIndex
from packages.serializers.models import ProviderRequest


class ArchitectureReviewCapability(Capability):
    """Orchestrates the architecture review capability pipeline.

    Attributes:
        None — the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "architecture-review"

    @property
    def intent(self) -> PlannerIntent:
        """Planner intent for this capability.

        Returns:
            PlannerIntent.REVIEW.
        """
        return PlannerIntent.REVIEW

    @property
    def profile(self) -> RetrievalProfile:
        """Retrieval profile for this capability.

        Returns:
            The ARCHITECTURE_REVIEW_PROFILE singleton.
        """
        return ARCHITECTURE_REVIEW_PROFILE

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the architecture review capability pipeline.

        Orchestrates exactly this pipeline:

            User Query → ArchitectureAnalyzer → Context → Serializer → Result

        Args:
            query: The user's natural language query.
            repository_index: The repository index to search.

        Returns:
            An immutable ``CapabilityResult``.
        """
        # Start timing.
        start_time = time.monotonic()

        # Stage 1: Run ArchitectureAnalyzer.
        architecture_review = self._stage_architecture_analysis(query, repository_index)

        # Stage 2: Build context from the architecture review.
        context_result = self._stage_context_building(query, architecture_review, repository_index)

        # Stage 3: Assemble context package.
        context_package = self._stage_assemble_package(context_result, repository_index)

        # Stage 4: Serialize to provider request.
        provider_request = self._stage_serialization(context_package, query)

        # Calculate execution time.
        execution_time_ms = (time.monotonic() - start_time) * 1000.0

        # Aggregate results into immutable CapabilityResult.
        return CapabilityResult(
            query=query,
            intent=self.intent.value,
            context_plan=self._build_context_plan(architecture_review),
            context_package=context_package,
            provider_request=provider_request,
            selected_symbols=tuple(m.module for m in architecture_review.modules),
            selected_modules=tuple(context_result.selected_modules),
            estimated_tokens=context_package.estimated_tokens,
            execution_time_ms=execution_time_ms,
        )

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def _stage_architecture_analysis(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> ArchitectureReview:
        """Stage 1: Run the ArchitectureAnalyzer.

        Args:
            query: The user query.
            repository_index: The repository index.

        Returns:
            An immutable ArchitectureReview.
        """
        analyzer = ArchitectureAnalyzer()
        review = analyzer.analyze(repository_index=repository_index)
        return review

    def _stage_context_building(
        self,
        query: str,
        architecture_review: ArchitectureReview,
        repository_index: RepositoryIndex,
    ) -> ContextResult:
        """Stage 2: Build context from the architecture review.

        Derives ContextQuery parameters from the retrieval profile.

        Args:
            query: The user query.
            architecture_review: The architecture review result.
            repository_index: The repository index.

        Returns:
            A ContextResult with candidates and selected modules.
        """
        from packages.context.builder import ContextBuilder

        profile = self.profile
        # Build a ContextQuery from the retrieval profile and architecture review.
        context_query = ContextQuery(
            text=query,
            max_symbols=len(architecture_review.modules) if architecture_review.modules else 20,
            max_modules=10,
            max_tokens=profile.max_context_tokens,
            maximum_depth=profile.relationship_depth,
            relationship_expansion=profile.include_callers or profile.include_callees,
        )

        builder = ContextBuilder(index=repository_index)
        result = builder.build(query=context_query)
        return result

    def _stage_assemble_package(
        self,
        context_result: ContextResult,
        repository_index: RepositoryIndex,
    ) -> ContextPackage:
        """Stage 3: Assemble a ContextPackage from the ContextResult.

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

        # Guard: no candidates means no context to assemble.
        if not candidates:
            from packages.context.context_package import (
                ContextMetadata,
                RelationshipSummary,
            )

            return ContextPackage(
                primary_symbol="",
                supporting_symbols=[],
                related_callers=[],
                related_callees=[],
                related_modules=[],
                relationship_summary=RelationshipSummary(
                    caller_count=0,
                    callee_count=0,
                    module_count=0,
                    symbol_count=0,
                ),
                estimated_tokens=budget.estimated_tokens,
                metadata=ContextMetadata(
                    ranking_version="1",
                    repository_revision="",
                    estimated_tokens=budget.estimated_tokens,
                ),
            )

        # Determine the primary symbol (first candidate).
        primary_candidate = candidates[0]
        supporting_candidates = list(candidates[1:])

        # Extract primary symbol qualified name.
        primary_symbol_name = primary_candidate.qualified_name

        # Extract supporting symbols: remaining candidates, ordered by
        # rank, deduplicated by qualified_name.
        supporting_symbols: list[str] = []
        seen_symbols: set[str] = {primary_symbol_name}
        for candidate in supporting_candidates:
            qname = candidate.qualified_name
            if qname not in seen_symbols:
                seen_symbols.add(qname)
                supporting_symbols.append(qname)

        # Collect related callers and callees from the primary symbol's
        # module.
        related_callers: list[str] = []
        related_callees: list[str] = []

        module = primary_candidate.module
        module_symbols: list[ContextCandidate] = [
            c for c in candidates if c.module == module
        ]
        for candidate in supporting_candidates:
            if candidate.module == module:
                qname = candidate.qualified_name
                if qname not in seen_symbols:
                    module_symbols.append(candidate)

        primary_index = -1
        for i, sym in enumerate(module_symbols):
            if sym.qualified_name == primary_symbol_name:
                primary_index = i
                break

        if primary_index >= 0:
            callers_set: set[str] = set()
            for i in range(0, primary_index):
                qname = module_symbols[i].qualified_name
                if qname not in callers_set and qname != primary_symbol_name:
                    callers_set.add(qname)
                    related_callers.append(qname)

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
        all_symbols_set: set[str] = {module}
        for candidate in supporting_candidates:
            all_symbols_set.add(candidate.module)
        for caller in related_callers:
            for candidate in candidates:
                if candidate.qualified_name == caller:
                    all_symbols_set.add(candidate.module)
                    break
            else:
                for candidate in supporting_candidates:
                    if candidate.qualified_name == caller:
                        all_symbols_set.add(candidate.module)
                        break
        for callee in related_callees:
            for candidate in candidates:
                if candidate.qualified_name == callee:
                    all_symbols_set.add(candidate.module)
                    break
            else:
                for candidate in supporting_candidates:
                    if candidate.qualified_name == callee:
                        all_symbols_set.add(candidate.module)
                        break

        related_modules: list[str] = sorted(all_symbols_set)

        # Build relationship summary.
        all_symbol_names: set[str] = {primary_symbol_name}
        all_symbol_names.update(supporting_symbols)
        all_symbol_names.update(related_callers)
        all_symbol_names.update(related_callees)

        from packages.context.context_package import (
            ContextMetadata,
            RelationshipSummary,
        )

        relationship_summary = RelationshipSummary(
            caller_count=len(related_callers),
            callee_count=len(related_callees),
            module_count=len(related_modules),
            symbol_count=len(all_symbol_names),
        )

        # Build metadata.
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
        """Stage 4: Serialize the context package.

        Args:
            context_package: The assembled context package.
            query: The original user query.

        Returns:
            A ProviderRequest ready for provider consumption.
        """
        from packages.serializers.factory import SerializerFactory
        from packages.serializers.types import ProviderType

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
    # Helper methods
    # ------------------------------------------------------------------

    def _build_context_plan(self, architecture_review: ArchitectureReview) -> ContextPlan:
        """Build a ContextPlan from the architecture review.

        Derives plan values from the retrieval profile so the plan
        accurately reflects what the capability requested.

        Args:
            architecture_review: The architecture review result.

        Returns:
            A ContextPlan representing the architecture review.
        """
        profile = self.profile
        return ContextPlan(
            intent=self.intent.value,
            primary_symbols=tuple(m.module for m in architecture_review.modules[:5]),
            relationship_expansion=profile.include_callers or profile.include_callees,
            ranking_profile="DEFAULT",
            maximum_depth=profile.relationship_depth,
            include_callers=profile.include_callers,
            include_callees=profile.include_callees,
            include_modules=False,
            include_diagnostics=profile.include_diagnostics,
            estimated_complexity="SIMPLE",
        )
