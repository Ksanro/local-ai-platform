"""ImplementFeature Capability v1.

Orchestrates the platform components that gather the repository context
needed to implement a new feature across an existing request path.

The capability is dormant: it is exported for direct use but is not wired
into the live gateway pipeline.

Architecture
------------

User Query
    ↓
ContextPlanner (intent_override="IMPLEMENT")
    ↓
RepositoryIndex.find()
    ↓
ContextBuilder (maximum_depth=2, relationship_expansion=True)
    ↓
ContextPackage assembly (primary + supporting symbols, related modules)
    ↓
Serializer
    ↓
CapabilityResult

The capability is orchestration only — no duplicated logic.
No ranking, no AST inspection, no filesystem access, no provider calls.

Retrieval Profile
-----------------

ImplementFeature maximizes cross-layer context for new functionality:

| Option                | Value |
|-----------------------|-------|
| include_callers       | true  |
| include_callees       | true  |
| include_dependencies  | true  |
| include_dependents    | true  |
| include_tests         | true  |
| include_dead_code     | false |
| include_diagnostics   | true  |
| relationship_depth    | 2     |
| max_context_tokens    | 4096  |

Only ``relationship_depth``, ``max_context_tokens`` and the caller/callee
pair (which decides ``relationship_expansion``) reach ``ContextQuery``. The
current ``ContextQuery`` API has no ``include_tests``,
``include_dependencies``, ``include_dependents`` or ``include_diagnostics``
fields, so those flags stay declarative profile intent and are not forwarded
to the context builder. ``include_dead_code`` is likewise declarative.

The candidate ceiling is not derived from the profile or the plan either:
``ContextQuery`` keeps its own default (20 symbols) because
``ContextPlan.maximum_depth`` measures relationship traversal depth, not the
number of candidates.

Public API
----------

.. code-block:: python

    from packages.capabilities.implement_feature import ImplementFeatureCapability

    engine = ImplementFeatureCapability()
    result = engine.execute(
        query="Implement feature X across the gateway pipeline",
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
- generate code
- modify source code
- perform graph traversal
- compute dependencies

Only orchestration.
"""

from __future__ import annotations

import time

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import IMPLEMENT_PROFILE, RetrievalProfile
from packages.context.context_package import ContextPackage
from packages.context.context_package import RelationshipSummary as RelationshipSummaryPub
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.planning.plan import ContextPlan
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


class ImplementFeatureCapability(Capability):
    """Orchestrates the implement-feature capability pipeline.

    Attributes:
        None — the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "implement-feature"

    @property
    def intent(self) -> PlannerIntent:
        """Planner intent for this capability.

        Returns:
            PlannerIntent.IMPLEMENT.
        """
        return PlannerIntent.IMPLEMENT

    @property
    def profile(self) -> RetrievalProfile:
        """Retrieval profile for this capability.

        Returns:
            The IMPLEMENT_PROFILE singleton.
        """
        return IMPLEMENT_PROFILE

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the implement-feature capability pipeline.

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
        context_result = self._stage_context_building(
            query, context_plan, repository_index
        )

        # Stage 4: Assemble context package.
        context_package = self._stage_assemble_package(
            context_result, repository_index
        )

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

        The capability pins the planner intent with ``intent_override`` so an
        ambiguous or debug-like query can never steer the pipeline into an
        ``EXPLAIN``/``DEBUG``/``SEARCH`` plan.

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
            intent_override=self.intent.value,
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

        ImplementFeature derives its token budget and relationship depth
        from ``IMPLEMENT_PROFILE``: features normally span several layers
        of an existing request path, so callers and callees are expanded to
        depth 2 while dead code stays out of the package.

        ``ContextPlan.maximum_depth`` is relationship traversal depth, not a
        candidate-count limit, so it is never reused as ``max_symbols``. The
        candidate ceiling stays at the established ``ContextQuery`` default,
        which keeps a multi-candidate package possible for an ``IMPLEMENT``
        plan whose rule-supplied traversal depth is ``1``.

        Args:
            query: The user query.
            context_plan: The planning result. Accepted for pipeline
                symmetry; the intent it carries is already pinned by
                ``_stage_planning``.
            repository_index: The repository index.

        Returns:
            A ContextResult with candidates and selected modules.
        """
        from packages.context.builder import ContextBuilder

        profile = self.profile

        # Build a ContextQuery from the retrieval profile.
        #
        # The profile owns the token budget and the relationship traversal
        # depth. The candidate ceiling is not passed at all, so it stays at
        # the ContextQuery default (ContextQuery.max_symbols == 20) instead
        # of being mistaken for ContextPlan.maximum_depth.
        context_query = ContextQuery(
            text=query,
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

        # Relationship fields stay empty: ContextResult publishes ranked
        # candidates, not verified CALLS edges. Neither candidate order nor
        # same-module membership establishes that one symbol calls another, so
        # this capability publishes no caller/callee claim at all.
        related_callers: list[str] = []
        related_callees: list[str] = []

        # Collect related modules from every ranked candidate.
        all_modules_set: set[str] = set()
        for candidate in candidates:
            all_modules_set.add(candidate.module)

        related_modules: list[str] = sorted(all_modules_set)

        # Build relationship summary.
        all_symbol_names: set[str] = set()
        if primary_candidate is not None:
            all_symbol_names.add(primary_candidate.qualified_name)
        for symbol_name in supporting_symbols:
            all_symbol_names.add(symbol_name)

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
