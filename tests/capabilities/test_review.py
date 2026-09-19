"""Tests for the dormant ``review`` capability.

``ReviewCapability`` is context assembly only: it turns a query into a pinned
``SEARCH`` plan, a profile-derived ``ContextQuery``, an assembled
``ContextPackage`` and a ``ProviderRequest``.  It never authors review findings,
never comments on source lines, never touches the filesystem, and never calls a
provider.

These tests keep the framework seams honest:

*   the ``REVIEW`` -> ``SEARCH`` vocabulary translation in both directions;
*   profile-over-plan precedence, including the candidate ceiling;
*   the five-stage pipeline order and its delegation to existing public APIs;
*   relationship honesty: ranked candidates never become caller/callee edges;
*   serializer availability through the documented import path, proven in a
    separate interpreter;
*   dormancy -- exported, constructible, but wired into nothing;
*   non-regression of the sibling capabilities and profiles.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import re
from contextlib import ExitStack, contextmanager
from itertools import permutations
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import patch

import pytest

from packages.capabilities import (
    ARCHITECTURE_REVIEW_PROFILE,
    DEBUG_PROFILE,
    EXPLAIN_PROFILE,
    GENERATE_TESTS_PROFILE,
    IMPLEMENT_PROFILE,
    REFACTOR_PROFILE,
    REVIEW_PROFILE,
    Capability,
    CapabilityFactory,
    CapabilityRegistry,
    DebugCapability,
    ExplainCapability,
    GenerateTestsCapability,
    ImplementFeatureCapability,
    PlannerIntent,
    RefactorCapability,
    RetrievalProfile,
    ReviewCapability,
)
from packages.capabilities.architecture_review import ArchitectureReviewCapability
from packages.capabilities.models import CapabilityResult
from packages.capabilities.review import PLANNER_INTENT_FOR_REVIEW
from packages.context.context_package import ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
    ContextResult,
)
from packages.planning.intent import Intent
from packages.planning.plan import ContextPlan
from packages.planning.planner import ContextPlanner
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.symbols.models import Symbol, SymbolType
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType
from tests.capabilities.assembly_probes import (
    assert_fresh_execution_is_honest,
    assert_relationship_honesty,
    candidate,
    run_in_fresh_interpreter,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Repository root, used for the fresh-interpreter probe and the dormancy scan.
REPO_ROOT = Path(__file__).resolve().parents[2]

CAPABILITY_PATH = REPO_ROOT / "packages" / "capabilities" / "review.py"

QUERY = "Review the gateway retry policy"

PRIMARY = "apps.gateway.policies.RetryPolicy.should_retry"
SIBLING = "apps.gateway.policies.RetryPolicy._classify"
FOREIGN = "packages.context.builder.ContextBuilder.build"

#: ``PRIMARY`` and ``SIBLING`` share a module file: co-location, never a call.
PRIMARY_MODULE = "apps/gateway/policies.py"
FOREIGN_MODULE = "packages/context/builder.py"

#: Capability-facing vocabulary (``packages.capabilities.base.PlannerIntent``).
CAPABILITY_INTENT_VALUE = "REVIEW"

#: Planner-facing vocabulary (``packages.planning.intent.Intent``).
PLANNER_INTENT_VALUE = "SEARCH"

#: Candidate ceiling ``ContextQuery`` applies when the caller passes none.
#: ``ContextPlan.maximum_depth`` is relationship traversal depth and must never
#: be reused as a candidate count.
DEFAULT_MAX_SYMBOLS = ContextQuery(text="probe").max_symbols

#: Every token the planning layer knows.  ``REVIEW`` is deliberately absent.
PLANNER_VOCABULARY = frozenset(
    {
        Intent.EXPLAIN,
        Intent.IMPLEMENT,
        Intent.REFACTOR,
        Intent.DEBUG,
        Intent.TEST,
        Intent.SEARCH,
        Intent.DEFAULT,
    }
)

#: Wordings the planner would classify as something other than ``SEARCH`` when
#: left to its own keyword detection.  Between them they cover every planner
#: intent except ``SEARCH`` itself, which is what the capability pins.
NON_SEARCH_WORDINGS: tuple[tuple[str, str], ...] = (
    ("Why does the gateway crash when the provider returns null? debug it", "DEBUG"),
    ("Implement a new retry policy in the gateway", "IMPLEMENT"),
    ("Add tests for the gateway retry policy", "IMPLEMENT"),
    ("Test the gateway retry policy", "TEST"),
    ("Refactor the gateway retry policy", "REFACTOR"),
    ("Explain the gateway retry policy", "EXPLAIN"),
    ("zebra pineapple", "DEFAULT"),
    (QUERY, "DEFAULT"),
)

PROFILE_FIELDS = tuple(field.name for field in dataclasses.fields(RetrievalProfile))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_index() -> RepositoryIndex:
    """Return an empty repository index (no symbols, no relationships)."""
    return RepositoryIndex(
        modules={},
        _symbols=[],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=0,
            class_count=0,
            function_count=0,
            symbol_count=0,
        ),
    )


def _make_context_result() -> ContextResult:
    """Return a result with same-module and cross-module candidates."""
    return ContextResult(
        candidates=[
            candidate(PRIMARY, PRIMARY_MODULE, 120),
            candidate(SIBLING, PRIMARY_MODULE, 90),
            candidate(FOREIGN, FOREIGN_MODULE, 60),
        ],
        selected_modules=[PRIMARY_MODULE, FOREIGN_MODULE],
        budget=ContextBudgetResult(
            estimated_tokens=1024,
            estimated_symbols=3,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        ),
    )


def _result_with(candidates: list[ContextCandidate]) -> ContextResult:
    """Return a context result built from ``candidates``."""
    modules: list[str] = []
    for item in candidates:
        if item.module not in modules:
            modules.append(item.module)
    return ContextResult(
        candidates=candidates,
        selected_modules=modules,
        budget=ContextBudgetResult(
            estimated_tokens=128 * len(candidates),
            estimated_symbols=len(candidates),
            estimated_modules=len(modules),
            within_budget=True,
            truncated=False,
        ),
    )


def _make_plan(
    intent: str = PLANNER_INTENT_VALUE, maximum_depth: int = 0
) -> ContextPlan:
    """Return a plan shaped like the planner's ``SEARCH`` rule output.

    The real :class:`ContextPlanner` pins ``maximum_depth=0`` and
    ``relationship_expansion=False`` for ``SEARCH``; ``REVIEW_PROFILE`` is
    expected to raise both regardless.
    """
    return ContextPlan(
        intent=intent,
        primary_symbols=(),
        relationship_expansion=False,
        ranking_profile=intent,
        maximum_depth=maximum_depth,
        include_callers=False,
        include_callees=False,
        include_modules=False,
        include_diagnostics=False,
        estimated_complexity="SIMPLE",
    )


def _make_provider_request(content: str = QUERY) -> ProviderRequest:
    """Return a minimal provider request."""
    return ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[{"role": "user", "content": content}],
        model="default",
    )


def _symbol(qualified_name: str, module: str = PRIMARY_MODULE) -> Symbol:
    """Return a repository symbol for index-match tests."""
    return Symbol(
        id=qualified_name,
        name=qualified_name.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        symbol_type=SymbolType.FUNCTION,
        module=module,
        lineno=1,
    )


def _stage_recorder(
    stage: Callable[..., Any], name: str, sink: list[str]
) -> Callable[..., Any]:
    """Wrap a stage method so its invocation order can be asserted."""

    def record(*args: Any, **kwargs: Any) -> Any:
        sink.append(name)
        return stage(*args, **kwargs)

    return record


@contextmanager
def patched_pipeline(
    *,
    plan: ContextPlan | None = None,
    context_result: ContextResult | None = None,
    provider_request: ProviderRequest | None = None,
) -> Iterator[dict[str, Any]]:
    """Patch the collaborators used by the pipeline stages.

    The capability's own stage methods run for real; only the planner, the
    context builder and the serializer factory are replaced, so tests can
    assert on how they were configured.
    """
    stack = ExitStack()
    try:
        planner_cls = stack.enter_context(
            patch("packages.planning.planner.ContextPlanner")
        )
        planner_cls.return_value.build.return_value = (
            plan if plan is not None else _make_plan()
        )
        builder_cls = stack.enter_context(
            patch("packages.context.builder.ContextBuilder")
        )
        builder_cls.return_value.build.return_value = (
            context_result
            if context_result is not None
            else _make_context_result()
        )
        serializer_cls = stack.enter_context(
            patch("packages.capabilities.review.SerializerFactory")
        )
        serializer_cls.create.return_value.serialize.return_value = (
            provider_request
            if provider_request is not None
            else _make_provider_request()
        )
        yield {
            "planner": planner_cls,
            "builder": builder_cls,
            "serializer": serializer_cls,
        }
    finally:
        stack.close()


@contextmanager
def patched_context_and_serializer() -> Iterator[dict[str, Any]]:
    """Patch retrieval and serialization while the real planner stays live.

    Used to prove the capability pins the planner intent: the real
    :class:`ContextPlanner` would otherwise classify debug-like,
    implementation-like or ambiguous wording as something else.
    """
    stack = ExitStack()
    try:
        builder_cls = stack.enter_context(
            patch("packages.context.builder.ContextBuilder")
        )
        builder_cls.return_value.build.return_value = _make_context_result()
        serializer_cls = stack.enter_context(
            patch("packages.capabilities.review.SerializerFactory")
        )
        serializer_cls.create.return_value.serialize.return_value = (
            _make_provider_request()
        )
        yield {
            "builder": builder_cls,
            "serializer": serializer_cls,
        }
    finally:
        stack.close()


def _source() -> str:
    """Return the capability source for static boundary checks."""
    return CAPABILITY_PATH.read_text(encoding="utf-8")


def _imported_modules() -> set[str]:
    """Return every module name the capability source refers to."""
    tree = ast.parse(_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _referencing(directory: Path, *patterns: str) -> list[str]:
    """Return files under ``directory`` matching any regex in ``patterns``."""
    compiled = [re.compile(pattern) for pattern in patterns]
    hits: list[str] = []
    for path in sorted(directory.rglob("*.py")):
        if any(regex.search(path.read_text(encoding="utf-8")) for regex in compiled):
            hits.append(path.relative_to(REPO_ROOT).as_posix())
    return hits


@pytest.fixture()
def capability() -> ReviewCapability:
    """Return a freshly constructed capability."""
    return ReviewCapability()


@pytest.fixture()
def source_tree() -> ast.Module:
    """Return the parsed AST of the capability module."""
    return ast.parse(CAPABILITY_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """Return a registry with every implemented capability registered."""
    reg = CapabilityRegistry()
    reg.register("explain", ExplainCapability)
    reg.register("debug", DebugCapability)
    reg.register("refactor", RefactorCapability)
    reg.register("implement-feature", ImplementFeatureCapability)
    reg.register("generate-tests", GenerateTestsCapability)
    reg.register("architecture-review", ArchitectureReviewCapability)
    reg.register("review", ReviewCapability)
    return reg


# ---------------------------------------------------------------------------
# Test: Package exports, registry and factory
# ---------------------------------------------------------------------------


class TestRegistrationAndExports:
    """The capability is exported and resolvable, and registered nowhere."""

    def test_capability_is_exported_from_the_package(self) -> None:
        import packages.capabilities as capabilities_package

        assert "ReviewCapability" in capabilities_package.__all__
        assert capabilities_package.ReviewCapability is ReviewCapability

    def test_profile_is_exported_from_the_package(self) -> None:
        import packages.capabilities as capabilities_package

        assert "REVIEW_PROFILE" in capabilities_package.__all__
        assert capabilities_package.REVIEW_PROFILE is REVIEW_PROFILE

    def test_capability_class_lives_in_its_own_module(self) -> None:
        import packages.capabilities.review as review_module

        assert ReviewCapability is review_module.ReviewCapability
        assert ReviewCapability.__module__ == "packages.capabilities.review"

    def test_registry_resolves_the_capability_class(
        self, registry: CapabilityRegistry
    ) -> None:
        assert registry.get("review") is ReviewCapability
        assert registry.has("review") is True

    def test_registry_lists_names_deterministically(
        self, registry: CapabilityRegistry
    ) -> None:
        assert "review" in registry.all()
        assert registry.all() == sorted(registry.all())

    def test_factory_creates_a_usable_instance(
        self, registry: CapabilityRegistry
    ) -> None:
        created = CapabilityFactory(registry).create("review")

        assert isinstance(created, ReviewCapability)
        assert created.name == "review"
        assert created.intent is PlannerIntent.REVIEW

    def test_duplicate_registration_is_rejected(
        self, registry: CapabilityRegistry
    ) -> None:
        with pytest.raises(ValueError):
            registry.register("review", ReviewCapability)

    def test_unregister_removes_only_this_capability(
        self, registry: CapabilityRegistry
    ) -> None:
        registry.unregister("review")

        assert registry.has("review") is False
        assert registry.has("architecture-review") is True


# ---------------------------------------------------------------------------
# Test: Identity, statelessness and profile
# ---------------------------------------------------------------------------


class TestCapabilityIdentity:
    """The capability presents the framework contract for review."""

    def test_name(self, capability: ReviewCapability) -> None:
        assert capability.name == "review"

    def test_extends_the_base_capability(
        self, capability: ReviewCapability
    ) -> None:
        assert isinstance(capability, Capability)

    def test_intent_is_review(self, capability: ReviewCapability) -> None:
        assert capability.intent is PlannerIntent.REVIEW
        assert capability.intent.value == CAPABILITY_INTENT_VALUE

    def test_profile_is_the_module_singleton(
        self, capability: ReviewCapability
    ) -> None:
        import packages.capabilities.profiles as profiles_module

        assert capability.profile is REVIEW_PROFILE
        assert REVIEW_PROFILE is profiles_module.REVIEW_PROFILE

    def test_profile_is_a_retrieval_profile(
        self, capability: ReviewCapability
    ) -> None:
        assert isinstance(capability.profile, RetrievalProfile)

    def test_capability_holds_no_instance_state(
        self, capability: ReviewCapability
    ) -> None:
        assert capability.__dict__ == {}

    def test_instances_are_independent_objects(self) -> None:
        first = ReviewCapability()
        second = ReviewCapability()

        assert first is not second
        assert first.profile is second.profile
        assert first.__dict__ == second.__dict__ == {}

    def test_execute_is_synchronous(self) -> None:
        assert asyncio.iscoroutinefunction(ReviewCapability.execute) is False

    def test_review_intent_is_shared_with_architecture_review(self) -> None:
        """Both report ``REVIEW``; their names and profiles stay distinct."""
        architecture = ArchitectureReviewCapability()

        assert architecture.intent is PlannerIntent.REVIEW
        assert architecture.name == "architecture-review"
        assert ReviewCapability().name == "review"
        assert architecture.profile is not REVIEW_PROFILE


class TestReviewProfile:
    """``REVIEW_PROFILE`` is the frozen retrieval contract for review."""

    def test_profile_matches_the_documented_table(self) -> None:
        expected = {
            "name": "review",
            "include_callers": True,
            "include_callees": True,
            "include_dependencies": True,
            "include_dependents": True,
            "include_tests": True,
            "include_dead_code": False,
            "include_diagnostics": True,
            "relationship_depth": 2,
            "max_context_tokens": 4096,
        }

        assert dataclasses.asdict(REVIEW_PROFILE) == expected

    def test_profile_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            REVIEW_PROFILE.relationship_depth = 7  # type: ignore[misc]

    def test_profile_is_hashable(self) -> None:
        assert hash(REVIEW_PROFILE) == hash(REVIEW_PROFILE)

    def test_profile_declares_only_scalar_fields(self) -> None:
        for field in dataclasses.fields(REVIEW_PROFILE):
            value = getattr(REVIEW_PROFILE, field.name)
            assert isinstance(value, (str, bool, int)), field.name

    def test_profile_exposes_the_shared_field_names(self) -> None:
        assert PROFILE_FIELDS == tuple(
            field.name for field in dataclasses.fields(REVIEW_PROFILE)
        )

    def test_profile_is_distinct_from_every_sibling(self) -> None:
        siblings = (
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            IMPLEMENT_PROFILE,
            GENERATE_TESTS_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
        )

        assert all(REVIEW_PROFILE is not other for other in siblings)
        assert all(REVIEW_PROFILE != other for other in siblings)

    def test_profile_is_declared_exactly_once(self) -> None:
        source = (REPO_ROOT / "packages" / "capabilities" / "profiles.py").read_text(
            encoding="utf-8"
        )

        assert len(
            re.findall(r"^REVIEW_PROFILE: RetrievalProfile", source, re.MULTILINE)
        ) == 1

    def test_architecture_review_profile_stays_deeper_and_wider(self) -> None:
        """The two review profiles differ on purpose."""
        assert REVIEW_PROFILE.relationship_depth == 2
        assert ARCHITECTURE_REVIEW_PROFILE.relationship_depth == 3
        assert REVIEW_PROFILE.max_context_tokens == 4096
        assert ARCHITECTURE_REVIEW_PROFILE.max_context_tokens == 8192
        assert REVIEW_PROFILE.include_dead_code is False
        assert ARCHITECTURE_REVIEW_PROFILE.include_dead_code is True

    def test_unsupported_include_flags_have_no_query_counterpart(self) -> None:
        """Declarative flags cannot become behaviour: ``ContextQuery`` has no
        field for them, so forwarding them is impossible by construction."""
        query = ContextQuery(text="probe")

        for flag in (
            "include_dependencies",
            "include_dependents",
            "include_tests",
            "include_dead_code",
            "include_diagnostics",
        ):
            assert not hasattr(query, flag), flag


# ---------------------------------------------------------------------------
# Test: REVIEW -> SEARCH planner vocabulary translation
# ---------------------------------------------------------------------------


class TestPlannerVocabularyTranslation:
    """The planner is pinned through the planner's own vocabulary."""

    def test_capability_intent_is_not_part_of_the_planner_vocabulary(self) -> None:
        assert CAPABILITY_INTENT_VALUE not in PLANNER_VOCABULARY

    def test_planner_token_is_part_of_the_planner_vocabulary(self) -> None:
        assert PLANNER_INTENT_FOR_REVIEW in PLANNER_VOCABULARY
        assert PLANNER_INTENT_FOR_REVIEW == Intent.SEARCH
        assert PLANNER_INTENT_FOR_REVIEW == PLANNER_INTENT_VALUE

    def test_planner_receives_the_search_intent_override(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        build = mocks["planner"].return_value.build
        assert build.call_args.kwargs["intent_override"] == PLANNER_INTENT_VALUE

    def test_capability_intent_is_never_sent_to_the_planner(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        build = mocks["planner"].return_value.build
        assert CAPABILITY_INTENT_VALUE not in build.call_args.kwargs.values()

    def test_the_override_is_pinned_by_the_module_constant(
        self, source_tree: ast.Module
    ) -> None:
        """The planner call takes the constant, never an inline spelling."""
        pinned_values = [
            keyword.value
            for node in ast.walk(source_tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "intent_override"
        ]

        assert len(pinned_values) == 1
        assert isinstance(pinned_values[0], ast.Name)
        assert pinned_values[0].id == "PLANNER_INTENT_FOR_REVIEW"

    def test_plan_keeps_the_planner_vocabulary(
        self, capability: ReviewCapability
    ) -> None:
        with patched_context_and_serializer():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_plan.intent == PLANNER_INTENT_VALUE

    def test_result_reports_the_capability_vocabulary(
        self, capability: ReviewCapability
    ) -> None:
        with patched_context_and_serializer():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.intent == CAPABILITY_INTENT_VALUE
        assert result.intent != result.context_plan.intent

    def test_real_planner_produces_the_narrow_search_plan(
        self, capability: ReviewCapability
    ) -> None:
        """The rule behind ``SEARCH`` is a plain lookup: depth 0, no expansion.

        Recording it here keeps the profile-over-plan tests honest: without the
        profile these numbers would cap a review package at one symbol.
        """
        with patched_context_and_serializer():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_plan.maximum_depth == 0
        assert result.context_plan.relationship_expansion is False

    @pytest.mark.parametrize(
        ("query_text", "detected_intent"), NON_SEARCH_WORDINGS
    )
    def test_wording_cannot_change_the_mapping(
        self, query_text: str, detected_intent: str
    ) -> None:
        # Left alone, the planner classifies this wording as something else...
        assert ContextPlanner().build(user_messages=[query_text]).intent == (
            detected_intent
        )

        # ...but the capability pins it, so both vocabularies stay fixed.
        with patched_context_and_serializer():
            result = ReviewCapability().execute(
                query=query_text, repository_index=_empty_index()
            )

        assert result.context_plan.intent == PLANNER_INTENT_VALUE
        assert result.intent == CAPABILITY_INTENT_VALUE

    def test_wording_cannot_change_the_plan_retrieved_either(self) -> None:
        """Same pinning with the real planner and the real builder in play."""
        with patch("packages.capabilities.review.SerializerFactory") as factory:
            factory.create.return_value.serialize.return_value = (
                _make_provider_request()
            )
            for query_text, detected in NON_SEARCH_WORDINGS:
                result = ReviewCapability().execute(
                    query=query_text, repository_index=_empty_index()
                )

                assert result.context_plan.intent == PLANNER_INTENT_VALUE
                assert result.context_plan.intent != detected
                assert result.intent == CAPABILITY_INTENT_VALUE



# ---------------------------------------------------------------------------
# Test: Profile -> ContextQuery wiring
# ---------------------------------------------------------------------------


class TestContextQueryWiring:
    """``REVIEW_PROFILE`` drives retrieval; the plan's shape does not."""

    def test_builder_is_constructed_with_the_index(
        self, capability: ReviewCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        assert mocks["builder"].call_args.kwargs["index"] is index

    def test_query_carries_the_original_text(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert isinstance(query, ContextQuery)
        assert query.text == QUERY

    def test_query_takes_budget_and_depth_from_the_profile(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_tokens == REVIEW_PROFILE.max_context_tokens == 4096
        assert query.maximum_depth == REVIEW_PROFILE.relationship_depth == 2

    def test_query_keeps_the_default_candidate_ceiling(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS == 20

    def test_relationship_expansion_follows_the_caller_and_callee_flags(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert REVIEW_PROFILE.include_callers is True
        assert REVIEW_PROFILE.include_callees is True
        assert query.relationship_expansion is True

    def test_profile_overrides_the_narrow_search_plan(
        self, capability: ReviewCapability
    ) -> None:
        """The ``SEARCH`` rule says depth 0 and no expansion; the profile says 2."""
        plan = _make_plan()

        with patched_pipeline(plan=plan) as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert plan.maximum_depth == 0
        assert query.maximum_depth == REVIEW_PROFILE.relationship_depth == 2
        assert plan.relationship_expansion is False
        assert query.relationship_expansion is True

    @pytest.mark.parametrize("maximum_depth", [0, 1, 2, 3])
    def test_candidate_ceiling_ignores_plan_depth(
        self, capability: ReviewCapability, maximum_depth: int
    ) -> None:
        with patched_pipeline(plan=_make_plan(maximum_depth=maximum_depth)) as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS
        assert query.max_symbols != maximum_depth
        assert query.maximum_depth == REVIEW_PROFILE.relationship_depth

    def test_a_depth_zero_plan_still_produces_a_multi_candidate_package(
        self, capability: ReviewCapability
    ) -> None:
        with patched_context_and_serializer():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_plan.maximum_depth == 0
        assert result.context_package.primary_symbol == PRIMARY
        assert len(result.context_package.supporting_symbols) == 2


# ---------------------------------------------------------------------------
# Test: Pipeline stages, order and delegation
# ---------------------------------------------------------------------------


class TestPipelineStages:
    """Each stage runs once, in order, through an existing public API."""

    STAGE_NAMES = (
        "_stage_planning",
        "_stage_repository_search",
        "_stage_context_building",
        "_stage_assemble_package",
        "_stage_serialization",
    )

    def test_planner_is_invoked_once_with_the_query(
        self, capability: ReviewCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["planner"].return_value.build
        build.assert_called_once()
        assert tuple(build.call_args.kwargs["user_messages"]) == (QUERY,)
        assert build.call_args.kwargs["repository_index"] is index

    def test_repository_is_queried_once(
        self, capability: ReviewCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            with patch.object(
                RepositoryIndex, "find", autospec=True, return_value=[]
            ) as find:
                capability.execute(query=QUERY, repository_index=index)

        find.assert_called_once_with(index, QUERY)

    def test_context_builder_is_invoked_once(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        mocks["builder"].return_value.build.assert_called_once()

    def test_package_assembly_runs_once(
        self, capability: ReviewCapability
    ) -> None:
        calls: list[str] = []
        original = capability._stage_assemble_package  # noqa: SLF001

        with patched_pipeline():
            with patch.object(
                capability,
                "_stage_assemble_package",
                side_effect=_stage_recorder(original, "assemble", calls),
            ):
                capability.execute(query=QUERY, repository_index=_empty_index())

        assert calls == ["assemble"]

    def test_serializer_is_invoked_once_with_the_query(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        serialize = mocks["serializer"].create.return_value.serialize
        serialize.assert_called_once()
        assert serialize.call_args.kwargs["messages"] == [
            {"role": "user", "content": QUERY}
        ]

    def test_stages_run_in_pipeline_order(
        self, capability: ReviewCapability
    ) -> None:
        calls: list[str] = []

        with ExitStack() as stack:
            stack.enter_context(patched_pipeline())
            for name in self.STAGE_NAMES:
                original = getattr(capability, name)
                stack.enter_context(
                    patch.object(
                        capability,
                        name,
                        side_effect=_stage_recorder(original, name, calls),
                    )
                )

            capability.execute(query=QUERY, repository_index=_empty_index())

        assert calls == list(self.STAGE_NAMES)

    def test_serializer_receives_the_assembled_package(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        serialize = mocks["serializer"].create.return_value.serialize
        assert serialize.call_args.kwargs["context_package"] == (
            result.context_package
        )

    def test_index_matches_become_selected_symbols(
        self, capability: ReviewCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            with patch.object(
                RepositoryIndex, "find", autospec=True
            ) as find:
                find.return_value = [_symbol(PRIMARY), _symbol(SIBLING)]
                result = capability.execute(
                    query=QUERY, repository_index=index
                )

        assert result.selected_symbols == (PRIMARY, SIBLING)

    def test_selected_modules_come_from_the_context_result(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.selected_modules == (PRIMARY_MODULE, FOREIGN_MODULE)


# ---------------------------------------------------------------------------
# Test: Package assembly
# ---------------------------------------------------------------------------


class TestPackageAssembly:
    """Assembly keeps ranked membership and publishes nothing else."""

    def assemble(
        self, capability: ReviewCapability, result: ContextResult
    ) -> ContextPackage:
        """Run stage 4 directly, the way the pipeline does."""
        return capability._stage_assemble_package(  # noqa: SLF001
            result, _empty_index()
        )

    def test_first_candidate_becomes_the_primary_symbol(
        self, capability: ReviewCapability
    ) -> None:
        assembled = self.assemble(capability, _make_context_result())

        assert assembled.primary_symbol == PRIMARY

    def test_remaining_candidates_become_supporting_symbols_in_rank_order(
        self, capability: ReviewCapability
    ) -> None:
        package = self.assemble(capability, _make_context_result())

        assert package.supporting_symbols == [SIBLING, FOREIGN]

    def test_related_modules_are_sorted_and_deduplicated(
        self, capability: ReviewCapability
    ) -> None:
        package = self.assemble(
            capability,
            _result_with(
                [
                    candidate(FOREIGN, FOREIGN_MODULE, 90),
                    candidate(PRIMARY, PRIMARY_MODULE, 80),
                    candidate("apps.other.helper.run", FOREIGN_MODULE, 70),
                ]
            ),
        )

        assert package.related_modules == sorted([FOREIGN_MODULE, PRIMARY_MODULE])
        assert package.relationship_summary.module_count == 2

    def test_duplicate_candidates_are_deduplicated(
        self, capability: ReviewCapability
    ) -> None:
        package = self.assemble(
            capability,
            _result_with(
                [
                    candidate(PRIMARY, PRIMARY_MODULE, 120),
                    candidate(FOREIGN, FOREIGN_MODULE, 90),
                    candidate(FOREIGN, FOREIGN_MODULE, 80),
                    candidate(PRIMARY, PRIMARY_MODULE, 70),
                ]
            ),
        )

        assert package.supporting_symbols == [FOREIGN]
        assert package.relationship_summary.symbol_count == 2

    def test_budget_estimate_is_carried_into_the_package(
        self, capability: ReviewCapability
    ) -> None:
        package = self.assemble(capability, _make_context_result())

        assert package.estimated_tokens == 1024
        assert package.metadata is not None
        assert package.metadata.ranking_version == "1"

    def test_no_candidates_produce_an_empty_package(
        self, capability: ReviewCapability
    ) -> None:
        package = self.assemble(capability, _result_with([]))

        assert package.primary_symbol == ""
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == []
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0
        assert package.relationship_summary.module_count == 0
        assert package.relationship_summary.symbol_count == 0


# ---------------------------------------------------------------------------
# Test: Relationship honesty
# ---------------------------------------------------------------------------


class TestRelationshipHonesty:
    """Assembly publishes candidates, never invented call edges."""

    def test_every_candidate_permutation_keeps_edges_empty(
        self, capability: ReviewCapability
    ) -> None:
        base = [
            candidate(PRIMARY, PRIMARY_MODULE, 120),
            candidate(SIBLING, PRIMARY_MODULE, 90),
            candidate(FOREIGN, FOREIGN_MODULE, 60),
        ]

        for order in permutations(base):
            assert_relationship_honesty(capability, list(order))

    def test_same_module_order_never_becomes_a_call_edge(
        self, capability: ReviewCapability
    ) -> None:
        base = [
            candidate(PRIMARY, PRIMARY_MODULE, 120),
            candidate(SIBLING, PRIMARY_MODULE, 90),
            candidate(FOREIGN, PRIMARY_MODULE, 60),
        ]

        for order in permutations(base):
            assert_relationship_honesty(capability, list(order))

    def test_cross_module_candidates_stay_symbols_and_modules(
        self, capability: ReviewCapability
    ) -> None:
        package = assert_relationship_honesty(
            capability,
            [
                candidate(PRIMARY, PRIMARY_MODULE, 120),
                candidate(FOREIGN, FOREIGN_MODULE, 90),
            ],
        )

        assert package.supporting_symbols == [FOREIGN]
        assert package.related_modules == sorted([PRIMARY_MODULE, FOREIGN_MODULE])
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0

    def test_summary_counts_match_the_published_lists(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        package = result.context_package
        summary = package.relationship_summary
        assert summary.caller_count == len(package.related_callers) == 0
        assert summary.callee_count == len(package.related_callees) == 0
        assert summary.module_count == len(package.related_modules) == 2
        assert summary.symbol_count == 3

    def test_the_profile_flags_do_not_fabricate_edges(
        self, capability: ReviewCapability
    ) -> None:
        """``include_callers``/``include_callees`` steer ranking, not output."""
        assert REVIEW_PROFILE.include_callers is True
        assert REVIEW_PROFILE.include_callees is True

        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_package.related_callers == []
        assert result.context_package.related_callees == []


# ---------------------------------------------------------------------------
# Test: Result contract
# ---------------------------------------------------------------------------


def _fields(result: CapabilityResult) -> dict[str, Any]:
    """Return every result field except the wall-clock timing."""
    return {
        field.name: getattr(result, field.name)
        for field in dataclasses.fields(result)
        if field.name != "execution_time_ms"
    }


class TestResultContract:
    """Execution yields one immutable, fully populated result."""

    def test_execute_returns_a_capability_result(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert isinstance(result, CapabilityResult)

    def test_result_carries_the_query_and_both_vocabularies(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.query == QUERY
        assert result.intent == CAPABILITY_INTENT_VALUE
        assert result.context_plan.intent == PLANNER_INTENT_VALUE

    def test_result_is_frozen(self, capability: ReviewCapability) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.query = "changed"  # type: ignore[misc]

    def test_result_carries_the_plan_package_and_request(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert isinstance(result.context_plan, ContextPlan)
        assert isinstance(result.context_package, ContextPackage)
        assert isinstance(result.provider_request, ProviderRequest)
        mocks["serializer"].create.assert_called_once_with(ProviderType.openai)

    def test_token_estimate_mirrors_the_package(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.estimated_tokens == result.context_package.estimated_tokens

    def test_review_produces_no_investigation_report(
        self, capability: ReviewCapability
    ) -> None:
        """Report fields belong to bug investigation, not to review."""
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.investigation_report is None

    def test_execution_time_is_recorded(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert isinstance(result.execution_time_ms, float)
        assert result.execution_time_ms >= 0.0

    def test_empty_repository_still_produces_a_request(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline(context_result=_result_with([])):
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_package.primary_symbol == ""
        assert result.context_package.supporting_symbols == []
        assert result.selected_symbols == ()
        assert result.selected_modules == ()
        assert result.estimated_tokens == 0
        assert result.provider_request.provider_type is ProviderType.openai


# ---------------------------------------------------------------------------
# Test: Determinism and absence of side effects
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Repeated execution yields identical structured output."""

    def test_same_instance_is_deterministic(self) -> None:
        capability = ReviewCapability()

        with patched_pipeline():
            first = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )
            second = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert _fields(first) == _fields(second)

    def test_fresh_instances_agree(self) -> None:
        with patched_pipeline():
            first = ReviewCapability().execute(
                query=QUERY, repository_index=_empty_index()
            )
        with patched_pipeline():
            second = ReviewCapability().execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert _fields(first) == _fields(second)

    def test_repeated_assembly_is_stable(self) -> None:
        capability = ReviewCapability()
        context_result = _make_context_result()

        packages = [
            capability._stage_assemble_package(  # noqa: SLF001
                context_result=context_result,
                repository_index=_empty_index(),
            )
            for _ in range(3)
        ]

        assert all(item == packages[0] for item in packages)

    def test_assembly_returns_fresh_lists(self) -> None:
        """Mutating one package's lists must not leak into the next."""
        capability = ReviewCapability()
        context_result = _make_context_result()

        first = capability._stage_assemble_package(  # noqa: SLF001
            context_result, _empty_index()
        )
        first.supporting_symbols.append("invented.symbol")
        first.related_modules.append("invented/module.py")

        second = capability._stage_assemble_package(  # noqa: SLF001
            context_result, _empty_index()
        )

        assert second.supporting_symbols == [SIBLING, FOREIGN]
        assert second.related_modules == sorted([PRIMARY_MODULE, FOREIGN_MODULE])


def _index_snapshot(index: RepositoryIndex) -> dict[str, Any]:
    """Return a comparable snapshot of the index contents."""
    return {
        "modules": list(index.modules),
        "symbols": [symbol.qualified_name for symbol in index.symbols()],
        "relationships": list(index.relationships()),
        "statistics": index.statistics(),
    }


class TestNoSideEffects:
    """Execution never mutates inputs, touches disk, or reaches a provider."""

    def test_repository_index_is_not_mutated(
        self, capability: ReviewCapability
    ) -> None:
        index = _empty_index()
        before = _index_snapshot(index)

        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=index)

        assert _index_snapshot(index) == before

    def test_context_result_is_not_mutated(
        self, capability: ReviewCapability
    ) -> None:
        context_result = _make_context_result()
        before = (
            list(context_result.candidates),
            list(context_result.selected_modules),
        )

        with patched_pipeline(context_result=context_result):
            capability.execute(query=QUERY, repository_index=_empty_index())

        assert (
            list(context_result.candidates),
            list(context_result.selected_modules),
        ) == before

    def test_execution_creates_no_files(
        self, capability: ReviewCapability
    ) -> None:
        before = sorted(path.name for path in REPO_ROOT.iterdir())

        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=_empty_index())

        assert sorted(path.name for path in REPO_ROOT.iterdir()) == before

    def test_serializer_is_only_asked_to_serialize(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_empty_index())

        serializer = mocks["serializer"].create.return_value
        assert [call[0] for call in serializer.method_calls] == ["serialize"]

    def test_capability_holds_no_state_after_execution(
        self, capability: ReviewCapability
    ) -> None:
        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=_empty_index())

        assert capability.__dict__ == {}

    def test_the_real_builder_runs_against_an_empty_index(
        self, capability: ReviewCapability
    ) -> None:
        """Nothing is patched here except serialization: retrieval is real."""
        with patch("packages.capabilities.review.SerializerFactory") as factory:
            factory.create.return_value.serialize.return_value = (
                _make_provider_request()
            )
            result = capability.execute(
                query=QUERY, repository_index=_empty_index()
            )

        assert result.context_package.primary_symbol == ""
        assert result.context_package.supporting_symbols == []
        assert result.context_plan.intent == PLANNER_INTENT_VALUE


# ---------------------------------------------------------------------------
# Test: Orchestration boundary
# ---------------------------------------------------------------------------


class TestOrchestrationBoundary:
    """The module orchestrates existing public APIs and adds no logic."""

    #: Everything the capability is allowed to name in an import.
    ALLOWED_IMPORTS = frozenset(
        {
            "__future__",
            "time",
            "packages.capabilities.base",
            "packages.capabilities.models",
            "packages.capabilities.profiles",
            "packages.context.builder",
            "packages.context.context_package",
            "packages.context.models",
            "packages.planning.plan",
            "packages.planning.planner",
            "packages.repository.index.models",
            "packages.serializers.factory",
            "packages.serializers.models",
            "packages.serializers.types",
        }
    )

    def test_capability_imports_only_platform_layers(self) -> None:
        assert _imported_modules() <= self.ALLOWED_IMPORTS

    def test_capability_reaches_no_provider_or_transport(self) -> None:
        forbidden = (
            "packages.providers",
            "packages.controller",
            "httpx",
            "requests",
            "socket",
            "urllib",
            "aiohttp",
        )
        offenders = {
            name for name in _imported_modules() if name.startswith(forbidden)
        }

        assert offenders == set()

    def test_capability_does_not_parse_or_walk_the_repository(self) -> None:
        forbidden = (
            "ast",
            "os",
            "pathlib",
            "subprocess",
            "asyncio",
            "packages.repository.symbols",
            "packages.repository.graph",
        )
        offenders = {
            name for name in _imported_modules() if name.startswith(forbidden)
        }

        assert offenders == set()

    def test_capability_does_not_import_a_sibling_capability(self) -> None:
        offenders = {
            name
            for name in _imported_modules()
            if name.startswith("packages.capabilities.")
            and name
            not in {
                "packages.capabilities.base",
                "packages.capabilities.models",
                "packages.capabilities.profiles",
            }
        }

        assert offenders == set()

    def test_capability_touches_no_registration_api(self) -> None:
        source = _source()

        assert "register(" not in source
        assert "get_registry" not in source

    def test_relationship_fields_are_assigned_empty_lists(
        self, source_tree: ast.Module
    ) -> None:
        """Structural guard: stage 4 has nothing to publish but emptiness."""
        values: dict[str, ast.expr] = {}
        for node in ast.walk(source_tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            if node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id in {"related_callers", "related_callees"}
                ):
                    values[target.id] = node.value

        assert set(values) == {"related_callers", "related_callees"}
        for value in values.values():
            assert isinstance(value, ast.List)
            assert value.elts == []


# ---------------------------------------------------------------------------
# Test: Serializer availability in a fresh interpreter
# ---------------------------------------------------------------------------


class TestFreshProcessImportPath:
    """The documented import path serializes without caller-side preparation."""

    def test_execute_serializes_in_a_fresh_interpreter(self) -> None:
        payload = run_in_fresh_interpreter("review", "ReviewCapability")

        assert_fresh_execution_is_honest(payload)
        # Serialization really ran: the real serializer injected a repository
        # context message ahead of the user message.
        assert "gateway.retry.should_retry" in payload["context"]

    def test_factory_is_the_only_serializer_route(self) -> None:
        source = _source()

        assert "SerializerFactory.create(ProviderType.openai)" in source
        assert "OpenAISerializer" not in source
        # Registration lives in the serialization layer, not in this capability.
        assert "packages.serializers.openai" not in source


# ---------------------------------------------------------------------------
# Test: Dormant delivery
# ---------------------------------------------------------------------------


class TestDormantDelivery:
    """Exported for direct use, wired into nothing."""

    #: Patterns that would mean some live layer reached for the capability.
    #: ``\\b`` keeps ``ArchitectureReviewCapability`` out of the match, and the
    #: look-behind keeps ``ARCHITECTURE_REVIEW_PROFILE`` out of it.
    TOKENS = (
        r"\bReviewCapability\b",
        r"capabilities\.review",
        r"(?<![A-Z_])REVIEW_PROFILE",
    )

    def test_gateway_never_references_the_capability(self) -> None:
        assert _referencing(REPO_ROOT / "apps" / "gateway", *self.TOKENS) == []

    def test_pipeline_never_references_the_capability(self) -> None:
        assert (
            _referencing(REPO_ROOT / "packages" / "pipeline", *self.TOKENS) == []
        )

    def test_workflows_never_reference_the_capability(self) -> None:
        assert (
            _referencing(REPO_ROOT / "packages" / "workflows", *self.TOKENS) == []
        )

    def test_controller_never_references_the_capability(self) -> None:
        assert (
            _referencing(REPO_ROOT / "packages" / "controller", *self.TOKENS) == []
        )

    def test_nothing_is_registered_by_default(self) -> None:
        import packages.capabilities  # noqa: F401

        assert CapabilityRegistry().all() == []

    def test_capability_is_constructible_standalone(self) -> None:
        assert ReviewCapability().profile is REVIEW_PROFILE


# ---------------------------------------------------------------------------
# Test: Sibling non-regression
# ---------------------------------------------------------------------------


ALL_CAPABILITIES: tuple[type[Capability], ...] = (
    ExplainCapability,
    DebugCapability,
    RefactorCapability,
    ImplementFeatureCapability,
    GenerateTestsCapability,
    ArchitectureReviewCapability,
    ReviewCapability,
)


class TestSiblingNonRegression:
    """Adding review left the rest of the framework where it was."""

    def test_capability_names_are_unique(self) -> None:
        names = [item().name for item in ALL_CAPABILITIES]

        assert len(names) == len(set(names)) == 7
        assert "review" in names

    def test_sibling_intents_are_unchanged(self) -> None:
        assert ExplainCapability().intent is PlannerIntent.EXPLAIN
        assert DebugCapability().intent is PlannerIntent.DEBUG
        assert RefactorCapability().intent is PlannerIntent.REFACTOR
        assert ImplementFeatureCapability().intent is PlannerIntent.IMPLEMENT
        assert GenerateTestsCapability().intent is PlannerIntent.GENERATE_TESTS

    def test_sibling_profiles_are_unchanged(self) -> None:
        assert EXPLAIN_PROFILE == RetrievalProfile(
            name="explain",
            include_callers=False,
            include_callees=False,
            include_dependencies=False,
            include_dependents=False,
            include_tests=False,
            include_dead_code=False,
            include_diagnostics=False,
            relationship_depth=1,
            max_context_tokens=4096,
        )
        assert DEBUG_PROFILE.relationship_depth == 2
        assert DEBUG_PROFILE.include_dependents is False
        assert REFACTOR_PROFILE.relationship_depth == 3
        assert REFACTOR_PROFILE.include_dead_code is True
        assert IMPLEMENT_PROFILE.name == "implement-feature"
        assert GENERATE_TESTS_PROFILE.include_callees is False
        assert ARCHITECTURE_REVIEW_PROFILE.relationship_depth == 3

    def test_profile_names_are_all_distinct(self) -> None:
        profiles = (
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            IMPLEMENT_PROFILE,
            GENERATE_TESTS_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
            REVIEW_PROFILE,
        )

        assert len({profile.name for profile in profiles}) == len(profiles)

    def test_every_capability_still_publishes_no_invented_edges(self) -> None:
        """The honesty fix holds framework-wide, review included."""
        candidates = [
            candidate(PRIMARY, PRIMARY_MODULE, 120),
            candidate(SIBLING, PRIMARY_MODULE, 90),
            candidate(FOREIGN, FOREIGN_MODULE, 60),
        ]

        for item in ALL_CAPABILITIES:
            assert_relationship_honesty(item(), candidates)
