"""Review Capability v1.

Assembles the repository context a downstream reviewer needs: the symbols that
match the query, ranked, together with the modules they live in.

The capability is dormant: it is exported for direct use but is not wired into
the live gateway pipeline.  It never produces a review, never comments on a
line of code, never touches files -- it stops after ``ProviderRequest``
creation, exactly like the sibling capabilities.  Anything that turns the
serialized context into review findings lives downstream of this class.

Two other names in this repository carry the word "review" and are not this
capability:

- ``ArchitectureReviewCapability``
  (``packages/capabilities/architecture_review.py``, name
  ``"architecture-review"``) analyses repository-wide architecture: stage 1 runs
  ``ArchitectureAnalyzer`` to get an ``ArchitectureReview``, and it plans by
  synthesizing a ``ContextPlan`` from ``ARCHITECTURE_REVIEW_PROFILE`` -- deeper
  (3), wider (8192 tokens) and dead-code aware, where general review stays at
  depth 2 and goes through ``ContextPlanner``.
- ``PullRequestReviewCapability``
  (``packages/capabilities/pull_request_review.py``, name
  ``"pull-request-review"``) is not a framework capability at all: it does not
  subclass ``packages.capabilities.base.Capability``, does not assemble a
  ``ContextPackage`` and shares no code with this module.

Architecture
------------

User Query
    |
    v
ContextPlanner (intent_override="SEARCH")
    |
    v
RepositoryIndex.find()
    |
    v
ContextBuilder (maximum_depth=2, relationship_expansion=True)
    |
    v
ContextPackage assembly (primary + supporting symbols, related modules,
caller/callee fields left empty)
    |
    v
Serializer
    |
    v
CapabilityResult

The capability is orchestration only -- no duplicated logic.
No ranking, no AST inspection, no filesystem access, no provider calls, and no
inference of call relationships from ranking order.

Intent Vocabulary Boundary
--------------------------

The capability layer and the planning layer use two different vocabularies,
and the translation between them is deliberate:

- ``PlannerIntent.REVIEW`` -- the capability intent, value ``"REVIEW"``
  (``packages.capabilities.base``).
- ``Intent.SEARCH`` -- the planner intent, value ``"SEARCH"``
  (``packages.planning.intent``).  ``ContextPlanner`` only knows EXPLAIN /
  IMPLEMENT / REFACTOR / DEBUG / TEST / SEARCH / DEFAULT: the planning layer has
  no review intent to hand it.

``ContextPlanner.build()`` silently drops an ``intent_override`` that is not
part of its own vocabulary (it falls back to keyword detection), so the
capability passes ``intent_override=PLANNER_INTENT_FOR_REVIEW`` -- ``"SEARCH"``
-- instead of ``self.intent.value``.

``SEARCH`` was chosen because review is read-only inspection of everything the
change under review touches, and ``SEARCH`` is the only planner intent that
asks for reach without asking for an outcome.  The rejected alternatives each
narrow or mutate the task:

- ``DEBUG`` presumes a defect and steers retrieval toward failure evidence.
- ``REFACTOR`` presumes a restructure and steers retrieval toward impact.
- ``IMPLEMENT`` presumes new code being written, which review never does.
- ``TEST`` presumes coverage work on code that already exists.
- ``EXPLAIN`` presumes the goal is understanding rather than judgement.
- ``DEFAULT`` is the no-match fallback, not a deliberate review posture.

The consequence, which is intentional and covered by tests:

- ``CapabilityResult.context_plan.intent`` stays ``"SEARCH"`` -- the plan the
  planner produced belongs to the planner vocabulary.
- ``CapabilityResult.intent`` is ``"REVIEW"`` -- the framework contract reports
  the capability intent, so this field is taken from ``self.intent.value`` and
  not from the plan.  It is the only result field that does not mirror the plan.

The plan's structural settings do not cap retrieval either.  The ``SEARCH`` rule
ships ``relationship_expansion=False`` and ``maximum_depth=0``, which would make
a review package a single-symbol lookup, so stage 3 takes depth and expansion
from ``REVIEW_PROFILE`` instead -- the same profile-over-plan precedence the
other directly executable capabilities document.

Retrieval Profile
-----------------

Review reads a change from every direction it can reach, but it is a lookup, not
a whole-repository audit:

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

Only ``relationship_depth``, ``max_context_tokens`` and the caller/callee pair
(which decides ``relationship_expansion``) reach ``ContextQuery``.  The current
``ContextQuery`` API has no ``include_tests``, ``include_dependencies``,
``include_dependents``, ``include_diagnostics`` or ``include_dead_code`` fields,
so those flags stay declarative retrieval intent and are not forwarded to the
context builder.  Dead code stays out of the profile because a change under
review is by definition live code, and pulling unused modules into the package
would only dilute the budget.

Every ``include_*`` flag is declarative intent.  The only behavioural
consequence of the caller/callee pair is the ``relationship_expansion`` switch
that feeds: that switch lets the ranking engine weigh verified ``CALLS`` edges
while it scores candidates.  It does not deliver those edges to this capability,
so no flag here can fill ``ContextPackage.related_callers`` or
``related_callees`` -- see "Relationship Honesty" below.

The candidate ceiling is not derived from the profile or the plan either:
``ContextQuery`` keeps its own default (20 symbols) because
``ContextPlan.maximum_depth`` measures relationship traversal depth, not the
number of candidates -- and the ``SEARCH`` rule sets that traversal depth to
``0``, which must not shrink a review package to one symbol.

Relationship Honesty
--------------------

``ContextResult`` hands over ranked candidates, and ``ContextCandidate``
carries a score and a module path -- never a ``CALLS`` edge.  Neither candidate
position nor two symbols sharing a module file says that one symbol calls the
other, so ``related_callers`` and ``related_callees`` stay empty lists in the
assembled package and ``RelationshipSummary.caller_count`` / ``callee_count``
follow them at ``0``.  Naming ranked neighbours as callers and callees would put
a call graph in the serialized context that nothing in the platform verified.

Verified edges do exist one layer down, in the symbol graph view the ranking
engine already consumes, but ``ContextResult`` does not surface them and
reaching for them from here would mean relationship analysis and graph
traversal inside the capability, which the constraints below forbid.  Supplying
relationship data to capabilities is a platform task.

Serializer Availability
------------------------

Stage 5 never instantiates a serializer class.  It asks
``SerializerFactory.create(ProviderType.openai)`` and resolves it through the
registry, which the ``packages.serializers`` package initializer populates for
the built-ins: importing any part of the serialization layer (which this module
does for ``SerializerFactory`` itself) imports the built-in serializer modules,
and each of those registers itself exactly once.  So the documented public API
serializes in a fresh interpreter with no caller- or test-side import of a
serializer module, and no capability carries a bootstrap import of its own.
Provider types that genuinely have no registered serializer still raise
``UnknownSerializerError``, and no provider is contacted: execution still stops
at ``ProviderRequest``.

Public API
----------

.. code-block:: python

    from packages.capabilities.review import ReviewCapability

    engine = ReviewCapability()
    result = engine.execute(
        query="Review the gateway retry policy",
        repository_index=index,
    )

That snippet is the whole contract.  It needs no extra import to reach a
serializer, and no registration helper to be called first.

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
- author review findings
- comment on source lines
- modify source code
- perform graph traversal
- compute dependencies
- infer call relationships from candidate order or module membership

Only orchestration.
"""

from __future__ import annotations

import time

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import REVIEW_PROFILE, RetrievalProfile
from packages.context.context_package import ContextPackage
from packages.context.context_package import RelationshipSummary as RelationshipSummaryPub
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.planning.plan import ContextPlan
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType

#: Planner-vocabulary token this capability pins ``intent_override`` to.
#:
#: ``PlannerIntent.REVIEW`` belongs to the capability layer and has no
#: counterpart in ``packages.planning.intent.Intent``, and an unknown
#: ``intent_override`` is ignored by ``ContextPlanner.build()``.  ``"SEARCH"`` is
#: therefore the token handed to the planner, while ``self.intent`` keeps
#: reporting ``REVIEW`` to capability consumers.  Review is read-only inspection,
#: and ``SEARCH`` is the only read-only, reach-oriented planner intent: ``DEBUG``,
#: ``REFACTOR`` and ``IMPLEMENT`` would each imply a narrower or a mutating task.
PLANNER_INTENT_FOR_REVIEW: str = "SEARCH"


class ReviewCapability(Capability):
    """Orchestrates the review-context assembly pipeline.

    Attributes:
        None -- the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "review"

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
            The REVIEW_PROFILE singleton.
        """
        return REVIEW_PROFILE

    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the review capability pipeline.

        Orchestrates exactly this pipeline:

            User Query -> Planner -> Repository -> Context -> Serializer -> Result

        The pipeline is assembled by calling existing public APIs in a
        fixed order.  No stage is skipped, duplicated, or reordered.

        Args:
            query: The user query.
            repository_index: The repository index to search.

        Returns:
            An immutable CapabilityResult with the context a downstream review
            step consumes -- never with review findings of its own.
        """
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
            # The capability intent, deliberately not ``context_plan.intent``:
            # the plan speaks the planner vocabulary (``SEARCH``), while the
            # framework contract reports ``REVIEW``.
            intent=self.intent.value,
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

        The planner is pinned through the ``SEARCH`` token of its own
        vocabulary.  ``REVIEW`` is a capability intent and is not a member of
        ``packages.planning.intent.Intent``, so passing it as ``intent_override``
        would be ignored and the planner would fall back to keyword detection.
        Using ``"SEARCH"`` means a debug-like, implementation-like, test-like or
        ambiguous query can never steer the pipeline into a
        ``DEBUG``/``IMPLEMENT``/``TEST``/``EXPLAIN`` plan.

        Args:
            query: The user query.
            repository_index: The repository index.

        Returns:
            An immutable ContextPlan whose ``intent`` is ``"SEARCH"``.
        """
        from packages.planning.planner import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(
            user_messages=[query],
            repository_index=repository_index,
            intent_override=PLANNER_INTENT_FOR_REVIEW,
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

        Review derives its token budget and relationship traversal depth from
        ``REVIEW_PROFILE``: judging a change needs both directions of its
        dependency neighbourhood at depth 2, while dead code stays out of the
        package.

        ``ContextPlan.maximum_depth`` is relationship traversal depth, not a
        candidate-count limit, so it is never reused as ``max_symbols``.  The
        candidate ceiling stays at the established ``ContextQuery`` default,
        which keeps a multi-candidate package possible for a ``SEARCH`` plan
        whose rule-supplied traversal depth is ``0``.

        Args:
            query: The user query.
            context_plan: The planning result.  Accepted for pipeline
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
        # depth; the caller/callee pair is what turns relationship expansion on.
        # The declarative include_tests / include_dependencies /
        # include_dependents / include_diagnostics / include_dead_code flags
        # have no ContextQuery counterpart and are not forwarded. The candidate
        # ceiling is not passed at all, so it stays at the ContextQuery default
        # (ContextQuery.max_symbols == 20) instead of being mistaken for
        # ContextPlan.maximum_depth, which the SEARCH rule pins at 0.
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

        This is orchestration -- the capability constructs the package from
        builder output without duplicating ranking or parsing logic.  It keeps
        the ranked symbol membership (one primary, the rest supporting) and the
        modules those symbols live in, and it keeps the caller and callee lists
        empty because builder output carries no verified ``CALLS`` edge.

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

        # Related callers and related callees stay empty.
        #
        # The builder output carries ranked candidates, and a candidate carries
        # a score and a module path -- never a CALLS edge.  Candidate position
        # therefore says nothing about who calls whom, and two symbols sharing
        # a module file is co-location, not a call relationship.  Deriving
        # callers or callees from that ordering would publish a call graph the
        # platform never verified, in the package, in the relationship summary
        # and in the serialized context message.  An honest empty list keeps
        # ``REVIEW_PROFILE``'s caller/callee flags declarative: they steer
        # relationship expansion while ranking, and nothing more.
        related_callers: list[str] = []
        related_callees: list[str] = []

        # Collect related modules: the modules the ranked candidates reached.
        # Empty caller and callee lists cannot contribute modules.
        all_modules_set: set[str] = set()
        for candidate in candidates:
            all_modules_set.add(candidate.module)

        related_modules: list[str] = sorted(all_modules_set)

        # Build relationship summary from the lists actually reported.
        all_symbol_names: set[str] = set()
        if primary_candidate is not None:
            all_symbol_names.add(primary_candidate.qualified_name)
        all_symbol_names.update(supporting_symbols)
        all_symbol_names.update(related_callers)
        all_symbol_names.update(related_callees)

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

        Stops at ``ProviderRequest`` creation: the request is the boundary a
        downstream review step would consume, and nothing here sends it.

        The serializer comes from ``SerializerFactory``, and the registry that
        factory reads is populated by the serialization layer itself when it is
        imported, so this stage needs no bootstrap import of its own.  Nothing is
        instantiated directly and no provider is contacted.

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
