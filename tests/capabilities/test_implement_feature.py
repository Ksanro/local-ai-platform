"""Tests for the dormant ImplementFeatureCapability v1.

Covers the requirement groups: package exports, capability identity, the
``IMPLEMENT_PROFILE`` retrieval contract, the six-stage execution pipeline,
determinism, absence of side effects, and the boundary rules (no duplicated
repository/context/serializer logic and no provider execution).

The capability is intentionally not wired into the live gateway pipeline, so
these tests exercise it through direct instantiation, the
:class:`CapabilityRegistry`, and the :class:`CapabilityFactory`.
"""

from __future__ import annotations

import dataclasses
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
    IMPLEMENT_PROFILE,
    REFACTOR_PROFILE,
    Capability,
    CapabilityFactory,
    DebugCapability,
    ExplainCapability,
    ImplementFeatureCapability,
    PlannerIntent,
    RefactorCapability,
    RetrievalProfile,
)
from packages.capabilities.models import CapabilityResult
from packages.capabilities.registry import CapabilityRegistry
from packages.context.context_package import ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
    ContextResult,
)
from packages.planning.plan import ContextPlan
from packages.planning.planner import ContextPlanner
from packages.repository.index.models import (
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.repository.symbols.models import Symbol, SymbolType
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType
from tests.capabilities.assembly_probes import (
    assert_fresh_execution_is_honest,
    assert_relationship_honesty,
    run_in_fresh_interpreter,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERY = "Implement the new retrieval profile in the gateway pipeline"

#: The candidate ceiling ``ContextQuery`` applies when the caller does not
#: override it. ``ContextPlan.maximum_depth`` is relationship traversal depth
#: and must never be reused as a candidate count.
DEFAULT_MAX_SYMBOLS = ContextQuery(text="probe").max_symbols

PRIMARY = "packages.services.gateway.GatewayService.handle"
SIBLING = "packages.services.gateway.GatewayService._notify"
FOREIGN = "packages.context.builder.ContextBuilder.build"

PRIMARY_MODULE = "packages/services/gateway.py"
FOREIGN_MODULE = "packages/context/builder.py"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_index() -> RepositoryIndex:
    """Return an empty in-memory index (no filesystem or AST access)."""
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


def _candidate(qualified_name: str, module: str, score: int) -> ContextCandidate:
    """Return a context candidate for pipeline tests."""
    return ContextCandidate(
        symbol_id=qualified_name,
        qualified_name=qualified_name,
        module=module,
        score=score,
    )


def _make_context_result() -> ContextResult:
    """Return a context result with same-module and cross-module candidates."""
    return ContextResult(
        candidates=[
            _candidate(PRIMARY, PRIMARY_MODULE, 120),
            _candidate(SIBLING, PRIMARY_MODULE, 90),
            _candidate(FOREIGN, FOREIGN_MODULE, 60),
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


def _make_plan(intent: str = "IMPLEMENT", maximum_depth: int = 2) -> ContextPlan:
    """Return a minimal context plan."""
    return ContextPlan(
        intent=intent,
        primary_symbols=(),
        relationship_expansion=True,
        ranking_profile="IMPLEMENT",
        maximum_depth=maximum_depth,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=False,
        estimated_complexity="MODERATE",
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

    The capability's own stage methods run for real; only the planner,
    context builder, and serializer collaborators are replaced so tests can
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
            patch("packages.capabilities.implement_feature.SerializerFactory")
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
    :class:`ContextPlanner` would otherwise classify debug-like or ambiguous
    wording as ``DEBUG``/``SEARCH``/``EXPLAIN``.
    """
    stack = ExitStack()
    try:
        builder_cls = stack.enter_context(
            patch("packages.context.builder.ContextBuilder")
        )
        builder_cls.return_value.build.return_value = _make_context_result()
        serializer_cls = stack.enter_context(
            patch("packages.capabilities.implement_feature.SerializerFactory")
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


@pytest.fixture()
def capability() -> ImplementFeatureCapability:
    """Return a freshly constructed capability."""
    return ImplementFeatureCapability()


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """Return a registry with every implemented capability registered."""
    reg = CapabilityRegistry()
    reg.register("explain", ExplainCapability)
    reg.register("debug", DebugCapability)
    reg.register("refactor", RefactorCapability)
    reg.register("implement-feature", ImplementFeatureCapability)
    return reg


# ---------------------------------------------------------------------------
# Test: Package exports and registry integration
# ---------------------------------------------------------------------------


class TestRegistrationAndExports:
    """Capability is exported and resolvable without gateway wiring."""

    def test_capability_class_lives_in_its_own_module(self) -> None:
        assert ImplementFeatureCapability.__module__ == (
            "packages.capabilities.implement_feature"
        )

    def test_exports_listed_in_dunder_all(self) -> None:
        import packages.capabilities as capabilities_pkg

        assert "ImplementFeatureCapability" in capabilities_pkg.__all__
        assert "IMPLEMENT_PROFILE" in capabilities_pkg.__all__

    def test_registry_resolves_capability_class(
        self, registry: CapabilityRegistry
    ) -> None:
        assert registry.get("implement-feature") is ImplementFeatureCapability

    def test_registry_reports_the_capability_name(
        self, registry: CapabilityRegistry
    ) -> None:
        assert registry.has("implement-feature") is True
        assert sorted(registry.all()) == [
            "debug",
            "explain",
            "implement-feature",
            "refactor",
        ]

    def test_factory_creates_capability(
        self, registry: CapabilityRegistry
    ) -> None:
        created = CapabilityFactory(registry).create("implement-feature")

        assert isinstance(created, ImplementFeatureCapability)

    def test_factory_created_instances_are_independent(
        self, registry: CapabilityRegistry
    ) -> None:
        factory = CapabilityFactory(registry)

        first = factory.create("implement-feature")
        second = factory.create("implement-feature")

        assert first is not second
        assert first.name == second.name

    def test_capability_extends_base_capability(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert isinstance(capability, Capability)

    def test_fresh_registry_does_not_include_capability(self) -> None:
        reg = CapabilityRegistry()

        assert reg.has("implement-feature") is False
        assert reg.get("implement-feature") is None


# ---------------------------------------------------------------------------
# Test: Capability identity
# ---------------------------------------------------------------------------


class TestCapabilityIdentity:
    """The capability identifies itself as IMPLEMENT, not explain/debug/refactor."""

    def test_name(self, capability: ImplementFeatureCapability) -> None:
        assert capability.name == "implement-feature"

    def test_intent_is_implement(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert capability.intent is PlannerIntent.IMPLEMENT

    def test_intent_value(self, capability: ImplementFeatureCapability) -> None:
        assert capability.intent.value == "IMPLEMENT"

    def test_intent_is_not_an_existing_intent(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert capability.intent not in {
            PlannerIntent.EXPLAIN,
            PlannerIntent.DEBUG,
            PlannerIntent.REFACTOR,
        }

    def test_profile_is_the_module_singleton(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert capability.profile is IMPLEMENT_PROFILE

    def test_profile_is_a_retrieval_profile(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert isinstance(capability.profile, RetrievalProfile)

    def test_sibling_capabilities_keep_their_intents(self) -> None:
        assert ExplainCapability().intent is PlannerIntent.EXPLAIN
        assert DebugCapability().intent is PlannerIntent.DEBUG
        assert RefactorCapability().intent is PlannerIntent.REFACTOR

    def test_capability_is_not_a_sibling_subclass(self) -> None:
        assert not issubclass(
            ImplementFeatureCapability,
            (ExplainCapability, DebugCapability, RefactorCapability),
        )


# ---------------------------------------------------------------------------
# Test: IMPLEMENT_PROFILE contract
# ---------------------------------------------------------------------------


PROFILE_FIELDS = tuple(field.name for field in dataclasses.fields(RetrievalProfile))


class TestImplementProfile:
    """The profile encodes the implementation retrieval contract."""

    def test_profile_name(self) -> None:
        assert IMPLEMENT_PROFILE.name == "implement-feature"

    def test_profile_relationships_and_diagnostics_are_included(self) -> None:
        assert IMPLEMENT_PROFILE.include_callers is True
        assert IMPLEMENT_PROFILE.include_callees is True
        assert IMPLEMENT_PROFILE.include_dependencies is True
        assert IMPLEMENT_PROFILE.include_dependents is True
        assert IMPLEMENT_PROFILE.include_tests is True
        assert IMPLEMENT_PROFILE.include_diagnostics is True

    def test_profile_excludes_dead_code(self) -> None:
        assert IMPLEMENT_PROFILE.include_dead_code is False

    def test_profile_budget(self) -> None:
        assert IMPLEMENT_PROFILE.max_context_tokens == 4096

    def test_profile_depth(self) -> None:
        assert IMPLEMENT_PROFILE.relationship_depth == 2

    def test_profile_matches_expected_literal(self) -> None:
        expected = RetrievalProfile(
            name="implement-feature",
            include_callers=True,
            include_callees=True,
            include_dependencies=True,
            include_dependents=True,
            include_tests=True,
            include_dead_code=False,
            include_diagnostics=True,
            relationship_depth=2,
            max_context_tokens=4096,
        )

        assert IMPLEMENT_PROFILE == expected

    def test_profile_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            IMPLEMENT_PROFILE.max_context_tokens = 8192  # type: ignore[misc]

    def test_profile_is_hashable(self) -> None:
        assert isinstance(hash(IMPLEMENT_PROFILE), int)

    def test_profile_is_module_level_singleton(self) -> None:
        import packages.capabilities.profiles as profiles_module

        assert profiles_module.IMPLEMENT_PROFILE is IMPLEMENT_PROFILE

    def test_profile_does_not_alias_sibling_profiles(self) -> None:
        assert IMPLEMENT_PROFILE is not EXPLAIN_PROFILE
        assert IMPLEMENT_PROFILE is not DEBUG_PROFILE
        assert IMPLEMENT_PROFILE is not REFACTOR_PROFILE
        assert IMPLEMENT_PROFILE is not ARCHITECTURE_REVIEW_PROFILE

    def test_profile_is_distinct_from_sibling_profiles(self) -> None:
        assert IMPLEMENT_PROFILE != EXPLAIN_PROFILE
        assert IMPLEMENT_PROFILE != DEBUG_PROFILE
        assert IMPLEMENT_PROFILE != REFACTOR_PROFILE
        assert IMPLEMENT_PROFILE != ARCHITECTURE_REVIEW_PROFILE

    def test_profile_declares_only_scalar_fields(self) -> None:
        for field in dataclasses.fields(IMPLEMENT_PROFILE):
            value = getattr(IMPLEMENT_PROFILE, field.name)
            assert isinstance(value, (str, int, bool)), field.name

    def test_profiles_module_field_names_are_shared(self) -> None:
        for profile in (
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
            IMPLEMENT_PROFILE,
        ):
            assert tuple(f.name for f in dataclasses.fields(profile)) == (
                PROFILE_FIELDS
            )
            assert tuple(f.name for f in dataclasses.fields(profile)) == (
                PROFILE_FIELDS
            )


# ---------------------------------------------------------------------------
# Test: Pipeline stages
# ---------------------------------------------------------------------------


class TestPipelineStages:
    """Each stage of the pipeline is invoked exactly once."""

    def test_planner_is_invoked_with_the_query(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        planner = mocks["planner"].return_value.build
        planner.assert_called_once()
        assert tuple(planner.call_args.kwargs["user_messages"]) == (QUERY,)
        assert planner.call_args.kwargs["repository_index"] is index
        assert planner.call_args.kwargs["intent_override"] == "IMPLEMENT"

    def test_repository_is_queried(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patch.object(
            RepositoryIndex, "find", autospec=True, return_value=[]
        ) as find:
            with patched_pipeline():
                capability.execute(query=QUERY, repository_index=index)

        find.assert_called_once_with(index, QUERY)

    def test_context_builder_is_configured_from_the_profile(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["builder"].return_value.build
        build.assert_called_once()
        query = build.call_args.kwargs["query"]
        assert query.text == QUERY
        assert query.max_tokens == IMPLEMENT_PROFILE.max_context_tokens
        assert query.maximum_depth == IMPLEMENT_PROFILE.relationship_depth
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS
        assert query.relationship_expansion is True

    def test_context_builder_receives_the_repository_index(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["builder"].return_value.build
        build.assert_called_once()
        assert mocks["builder"].call_args.kwargs["index"] is index

    def test_profile_settings_win_over_plan_values(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline(plan=_make_plan(maximum_depth=0)) as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.maximum_depth == IMPLEMENT_PROFILE.relationship_depth
        assert query.max_tokens == IMPLEMENT_PROFILE.max_context_tokens

    def test_package_is_assembled_from_the_context_result(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()
        captured: list[ContextPackage] = []

        def capture(package: ContextPackage, query: str) -> ProviderRequest:
            captured.append(package)
            return _make_provider_request(query)

        with patched_pipeline():
            with patch.object(
                capability, "_stage_serialization", side_effect=capture
            ):
                capability.execute(query=QUERY, repository_index=index)

        package = captured[0]
        assert package.primary_symbol == PRIMARY
        assert package.supporting_symbols == [SIBLING, FOREIGN]
        # SIBLING only shares a module with PRIMARY, and both rank below it.
        # Neither fact is a call edge, so both relationship lists stay empty.
        assert package.related_callees == []
        assert package.related_callers == []
        assert package.related_modules == sorted([PRIMARY_MODULE, FOREIGN_MODULE])
        assert package.estimated_tokens == 1024
        assert package.relationship_summary.symbol_count == 3
        assert package.relationship_summary.module_count == 2

    def test_stages_run_in_pipeline_order(
        self, capability: ImplementFeatureCapability
    ) -> None:
        calls: list[str] = []
        stage_names = (
            "_stage_planning",
            "_stage_repository_search",
            "_stage_context_building",
            "_stage_assemble_package",
            "_stage_serialization",
        )

        with ExitStack() as stack:
            stack.enter_context(patched_pipeline())
            for name in stage_names:
                original = getattr(capability, name)
                stack.enter_context(
                    patch.object(
                        capability,
                        name,
                        side_effect=_stage_recorder(original, name, calls),
                    )
                )

            capability.execute(query=QUERY, repository_index=_make_index())

        assert calls == list(stage_names)

    def test_serializer_receives_the_assembled_package(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assembled: list[ContextPackage] = []

        with ExitStack() as stack:
            mocks = stack.enter_context(patched_pipeline())
            original = capability._stage_assemble_package  # noqa: SLF001

            def assemble(*args: Any, **kwargs: Any) -> ContextPackage:
                package = original(*args, **kwargs)
                assembled.append(package)
                return package

            stack.enter_context(
                patch.object(
                    capability, "_stage_assemble_package", side_effect=assemble
                )
            )

            capability.execute(query=QUERY, repository_index=_make_index())

        serialize = mocks["serializer"].create.return_value.serialize
        serialize.assert_called_once()
        assert serialize.call_args.kwargs["context_package"] is assembled[0]

    def test_index_matches_become_selected_symbols(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()
        matches = [_symbol(PRIMARY), _symbol(SIBLING)]

        with patch.object(
            RepositoryIndex, "find", autospec=True, return_value=matches
        ):
            with patched_pipeline():
                result = capability.execute(query=QUERY, repository_index=index)

        assert result.selected_symbols == (PRIMARY, SIBLING)


class TestPlannerIntentAndCandidateCeiling:
    """The planner is pinned to IMPLEMENT and the ceiling is not plan depth."""

    def test_planner_receives_the_implement_intent_override(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["planner"].return_value.build
        assert capability.intent.value == "IMPLEMENT"
        assert build.call_args.kwargs["intent_override"] == capability.intent.value

    @pytest.mark.parametrize(
        ("query_text", "detected_intent"),
        [
            (
                "Why does the gateway crash when the provider returns null? debug it",
                "DEBUG",
            ),
            ("Find every place that references ContextBuilder", "SEARCH"),
            ("Explain the serializer factory", "EXPLAIN"),
            ("Look into that thing", "SEARCH"),
        ],
    )
    def test_wording_cannot_change_the_result_intent(
        self, query_text: str, detected_intent: str
    ) -> None:
        # Planned on its own, this wording is detected as something else...
        assert ContextPlanner().build(user_messages=[query_text]).intent == (
            detected_intent
        )

        # ...but the capability overrides it, so the result stays IMPLEMENT.
        with patched_context_and_serializer():
            result = ImplementFeatureCapability().execute(
                query=query_text, repository_index=_make_index()
            )

        assert result.intent == "IMPLEMENT"
        assert result.context_plan.intent == "IMPLEMENT"

    def test_established_query_ceiling(self) -> None:
        """The ceiling the capability inherits is the documented default."""
        assert DEFAULT_MAX_SYMBOLS == 20

    @pytest.mark.parametrize("maximum_depth", [0, 1, 2, 3])
    def test_candidate_ceiling_ignores_plan_depth(
        self, capability: ImplementFeatureCapability, maximum_depth: int
    ) -> None:
        index = _make_index()

        with patched_pipeline(
            plan=_make_plan(maximum_depth=maximum_depth)
        ) as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS
        assert query.max_symbols != maximum_depth
        assert query.maximum_depth == IMPLEMENT_PROFILE.relationship_depth

    def test_mocked_depth_one_plan_keeps_multiple_candidates(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_pipeline(plan=_make_plan(maximum_depth=1)) as mocks:
            result = capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS
        assert result.context_package.primary_symbol == PRIMARY
        assert len(result.context_package.supporting_symbols) == 2

    def test_real_depth_one_implement_plan_keeps_multiple_candidates(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()

        with patched_context_and_serializer() as mocks:
            result = capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert result.context_plan.intent == "IMPLEMENT"
        assert result.context_plan.maximum_depth == 1
        assert query.max_symbols == DEFAULT_MAX_SYMBOLS
        assert result.context_package.supporting_symbols
        assert len(result.context_package.supporting_symbols) == 2


# ---------------------------------------------------------------------------
# Test: Result contract and empty repositories
# ---------------------------------------------------------------------------


class TestResultContract:
    """The capability returns a frozen CapabilityResult with every field."""

    def test_execute_returns_capability_result(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        assert isinstance(result, CapabilityResult)

    def test_result_reports_the_implementation_intent(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        assert result.intent == "IMPLEMENT"

    def test_result_is_frozen(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.query = "other"  # type: ignore[misc]

    def test_serializer_is_invoked_once_with_the_query(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=_make_index())

        serialize = mocks["serializer"].create.return_value.serialize
        serialize.assert_called_once()
        assert serialize.call_args.kwargs["messages"] == [
            {"role": "user", "content": QUERY}
        ]

    def test_result_carries_the_provider_request_shape(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline() as mocks:
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        mocks["serializer"].create.assert_called_once_with(ProviderType.openai)
        assert result.provider_request is (
            mocks["serializer"].create.return_value.serialize.return_value
        )
        assert result.provider_request.model == "default"
        assert result.provider_request.messages == [
            {"role": "user", "content": QUERY}
        ]

    def test_empty_index_produces_an_empty_package(
        self, capability: ImplementFeatureCapability
    ) -> None:
        empty_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=ContextBudgetResult(estimated_tokens=0),
        )

        with patched_pipeline(context_result=empty_result):
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        assert result.context_package.primary_symbol == ""
        assert result.context_package.supporting_symbols == []
        assert result.context_package.related_callers == []
        assert result.context_package.related_callees == []
        assert result.context_package.related_modules == []
        assert result.selected_symbols == ()
        assert result.selected_modules == ()
        assert result.estimated_tokens == 0




# ---------------------------------------------------------------------------
# Test: Deterministic execution
# ---------------------------------------------------------------------------

RESULT_FIELDS = tuple(
    field.name
    for field in dataclasses.fields(CapabilityResult)
    if field.name != "execution_time_ms"
)


def _fields(result: CapabilityResult) -> dict[str, Any]:
    """Return every result field except the wall-clock timing."""
    return {name: getattr(result, name) for name in RESULT_FIELDS}


class TestDeterministicExecution:
    """Repeated execution yields identical structured output."""

    def test_same_instance_is_deterministic(self) -> None:
        capability = ImplementFeatureCapability()

        with patched_pipeline():
            first = capability.execute(
                query=QUERY, repository_index=_make_index()
            )
            second = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        assert _fields(first) == _fields(second)

    def test_fresh_instances_are_deterministic(self) -> None:
        with patched_pipeline():
            first = ImplementFeatureCapability().execute(
                query=QUERY, repository_index=_make_index()
            )
        with patched_pipeline():
            second = ImplementFeatureCapability().execute(
                query=QUERY, repository_index=_make_index()
            )

        assert _fields(first) == _fields(second)

    def test_repeated_package_assembly_is_stable(self) -> None:
        capability = ImplementFeatureCapability()
        context_result = _make_context_result()

        packages = [
            capability._stage_assemble_package(  # noqa: SLF001
                context_result=context_result,
                repository_index=_make_index(),
            )
            for _ in range(3)
        ]

        assert all(item == packages[0] for item in packages)

    def test_execution_time_is_recorded(
        self, capability: ImplementFeatureCapability
    ) -> None:
        with patched_pipeline():
            result = capability.execute(
                query=QUERY, repository_index=_make_index()
            )

        assert isinstance(result.execution_time_ms, float)
        assert result.execution_time_ms >= 0.0


# ---------------------------------------------------------------------------
# Test: Statelessness and side effects
# ---------------------------------------------------------------------------


def _index_snapshot(index: RepositoryIndex) -> dict[str, Any]:
    """Return a comparable snapshot of the index contents."""
    return {
        "modules": list(index.modules),
        "symbols": [symbol.qualified_name for symbol in index.symbols()],
        "relationships": list(index.relationships()),
        "statistics": index.statistics(),
    }


class TestNoSideEffects:
    """Execution never mutates repository state or the filesystem."""

    def test_repository_index_is_not_mutated(
        self, capability: ImplementFeatureCapability
    ) -> None:
        index = _make_index()
        before = _index_snapshot(index)

        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=index)

        assert _index_snapshot(index) == before

    def test_context_result_is_not_mutated(
        self, capability: ImplementFeatureCapability
    ) -> None:
        context_result = _make_context_result()
        before = (
            list(context_result.candidates),
            list(context_result.selected_modules),
        )

        with patched_pipeline(context_result=context_result):
            capability.execute(query=QUERY, repository_index=_make_index())

        assert (
            list(context_result.candidates),
            list(context_result.selected_modules),
        ) == before

    def test_execution_creates_no_files(
        self, capability: ImplementFeatureCapability
    ) -> None:
        before = sorted(path.name for path in REPO_ROOT.iterdir())

        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=_make_index())

        assert sorted(path.name for path in REPO_ROOT.iterdir()) == before

    def test_capability_holds_no_state(
        self, capability: ImplementFeatureCapability
    ) -> None:
        assert capability.__dict__ == {}



# ---------------------------------------------------------------------------
# Test: Boundary rules (no duplicated logic, no provider execution)
# ---------------------------------------------------------------------------

SOURCE_PATH = REPO_ROOT / "packages" / "capabilities" / "implement_feature.py"


def _source() -> str:
    """Return the capability source for static boundary checks."""
    return SOURCE_PATH.read_text(encoding="utf-8")


class TestBoundaryRules:
    """The capability orchestrates; it never re-implements platform layers."""

    def test_delegates_to_existing_components(self) -> None:
        source = _source()

        for delegate in (
            "ContextPlanner",
            "repository_index.find",
            "ContextBuilder",
            "ContextPackage",
            "SerializerFactory",
        ):
            assert delegate in source, delegate

    def test_no_ast_or_python_parsing(self) -> None:
        source = _source()

        for token in ("import ast", "ast.", "tokenize", "PythonAst", "SymbolExtractor"):
            assert token not in source, token

    def test_no_repository_scanning_or_graph_traversal(self) -> None:
        source = _source()

        for token in (
            "RepositoryScanner",
            "SymbolGraph",
            "DependencyGraph",
            "traverse",
            "networkx",
            "importlib",
        ):
            assert token not in source, token

    def test_no_ranking_or_token_estimation_logic(self) -> None:
        source = _source()

        for token in (
            "RankingEngine",
            "RankingConfig",
            "estimate_tokens(",
            "tiktoken",
            "encoding=",
        ):
            assert token not in source, token

    def test_no_filesystem_or_ast_walking(self) -> None:
        source = _source()

        for token in (
            "open(",
            "Path(",
            "iterdir",
            "rglob",
            "glob(",
            "read_text",
            "write_text",
            "os.walk",
        ):
            assert token not in source, token

    def test_no_code_generation_or_mutation(self) -> None:
        source = _source()

        for token in (
            "difflib",
            "unified_diff",
            "modify(",
            "write(",
            "packages.modification",
            "packages.execution",
        ):
            assert token not in source, token

    def test_no_provider_or_http_clients(self) -> None:
        source = _source()

        for token in (
            "packages.providers",
            "httpx",
            "requests",
            "urllib",
            "socket",
            "aiohttp",
            "chat.completions",
        ):
            assert token not in source, token

    def test_execute_never_imports_the_providers_layer(
        self, capability: ImplementFeatureCapability
    ) -> None:
        import sys

        providers_before = {
            name for name in sys.modules if name.startswith("packages.providers")
        }

        with patched_pipeline():
            capability.execute(query=QUERY, repository_index=_make_index())

        assert {
            name for name in sys.modules if name.startswith("packages.providers")
        } == providers_before


# ---------------------------------------------------------------------------
# Test: Dormant delivery (not wired into the live gateway)
# ---------------------------------------------------------------------------


class TestDormantDelivery:
    """The v1 capability is exported for direct use, not wired into the gateway."""

    @staticmethod
    def _referencing(directory: Path, *tokens: str) -> list[str]:
        return [
            path.relative_to(REPO_ROOT).as_posix()
            for path in directory.rglob("*.py")
            if any(token in path.read_text(encoding="utf-8") for token in tokens)
        ]

    def test_gateway_never_references_the_capability(self) -> None:
        assert (
            self._referencing(
                REPO_ROOT / "apps" / "gateway",
                "ImplementFeature",
                "capabilities.implement_feature",
                "implement-feature",
            )
            == []
        )

    def test_pipeline_never_registers_the_capability(self) -> None:
        assert (
            self._referencing(
                REPO_ROOT / "packages" / "pipeline",
                "ImplementFeatureCapability",
                "capabilities.implement_feature",
                "IMPLEMENT_PROFILE",
            )
            == []
        )

    def test_pipeline_implement_feature_workflow_is_a_different_abstraction(
        self,
    ) -> None:
        """The pipeline's live ``implement-feature`` workflow is a Workflow, not a Capability.

        ``WorkflowStage`` registers a default workflow named
        ``"implement-feature"`` in the *workflow* registry. The dormant
        capability registers in the *capability* registry, so the shared
        string is not a collision — but the pipeline must keep importing the
        workflow layer only.
        """
        source = (
            REPO_ROOT / "packages" / "pipeline" / "stages" / "workflow_stage.py"
        ).read_text(encoding="utf-8")

        assert '_DEFAULT_WORKFLOW = "implement-feature"' in source
        assert "packages.workflows" in source
        assert "packages.capabilities" not in source
        assert CapabilityRegistry().has("implement-feature") is False

    def test_no_automatic_registration_side_effects(self) -> None:
        import packages.capabilities  # noqa: F401

        assert CapabilityRegistry().has("implement-feature") is False


# ---------------------------------------------------------------------------
# Test: Existing capabilities and profiles are unchanged
# ---------------------------------------------------------------------------


class TestExistingCapabilitiesUnchanged:
    """Adding IMPLEMENT_PROFILE must not perturb siblings."""

    def test_explain_profile_is_unchanged(self) -> None:
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

    def test_debug_profile_is_unchanged(self) -> None:
        assert DEBUG_PROFILE.name == "debug"
        assert DEBUG_PROFILE.include_dependents is False
        assert DEBUG_PROFILE.include_dead_code is False
        assert DEBUG_PROFILE.include_diagnostics is True
        assert DEBUG_PROFILE.relationship_depth == 2
        assert DEBUG_PROFILE.max_context_tokens == 4096

    def test_refactor_profile_is_unchanged(self) -> None:
        assert REFACTOR_PROFILE.name == "refactor"
        assert REFACTOR_PROFILE.include_dead_code is True
        assert REFACTOR_PROFILE.relationship_depth == 3
        assert REFACTOR_PROFILE.max_context_tokens == 4096

    def test_architecture_review_profile_is_unchanged(self) -> None:
        assert ARCHITECTURE_REVIEW_PROFILE.name == "architecture-review"
        assert ARCHITECTURE_REVIEW_PROFILE.include_diagnostics is True
        assert ARCHITECTURE_REVIEW_PROFILE.relationship_depth == 3
        assert ARCHITECTURE_REVIEW_PROFILE.max_context_tokens == 8192

    def test_sibling_capability_names_are_unchanged(self) -> None:
        assert ExplainCapability().name == "explain"
        assert DebugCapability().name == "debug"
        assert RefactorCapability().name == "refactor"

    def test_capability_names_are_unique(self) -> None:
        names = {
            ExplainCapability().name,
            DebugCapability().name,
            RefactorCapability().name,
            ImplementFeatureCapability().name,
        }

        assert len(names) == 4

    def test_profiles_are_all_distinct(self) -> None:
        profiles = [
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
            IMPLEMENT_PROFILE,
        ]

        assert len({profile.name for profile in profiles}) == len(profiles)

    def test_capability_module_is_self_contained(self) -> None:
        source = (
            REPO_ROOT / "packages" / "capabilities" / "implement_feature.py"
        ).read_text(encoding="utf-8")

        for sibling in (
            "packages.capabilities.explain",
            "packages.capabilities.debug",
            "packages.capabilities.refactor",
            "packages.capabilities.bug_investigation",
            "packages.capabilities.architecture_review",
        ):
            assert sibling not in source, sibling

    def test_capability_is_registered_once_in_profiles(self) -> None:
        source = (
            REPO_ROOT / "packages" / "capabilities" / "profiles.py"
        ).read_text(encoding="utf-8")

        assert source.count("IMPLEMENT_PROFILE: RetrievalProfile") == 1


# ---------------------------------------------------------------------------
# Test: Relationship honesty
# ---------------------------------------------------------------------------


class TestRelationshipHonesty:
    """Assembly publishes candidates, never invented call edges."""

    def test_same_module_order_never_becomes_a_call_edge(
        self, capability: ImplementFeatureCapability
    ) -> None:
        base = [
            _candidate(PRIMARY, PRIMARY_MODULE, 120),
            _candidate(SIBLING, PRIMARY_MODULE, 90),
            _candidate(
                "packages.services.gateway.GatewayService._audit",
                PRIMARY_MODULE,
                60,
            ),
        ]

        for order in permutations(base):
            assert_relationship_honesty(capability, list(order))

    def test_cross_module_candidates_stay_symbols_and_modules(
        self, capability: ImplementFeatureCapability
    ) -> None:
        package = assert_relationship_honesty(
            capability,
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
                _candidate(FOREIGN, FOREIGN_MODULE, 60),
            ],
        )

        assert package.supporting_symbols == [SIBLING, FOREIGN]
        assert package.related_modules == sorted(
            [PRIMARY_MODULE, FOREIGN_MODULE]
        )
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0

    def test_duplicate_symbols_and_modules_are_deduplicated(
        self, capability: ImplementFeatureCapability
    ) -> None:
        package = assert_relationship_honesty(
            capability,
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(FOREIGN, FOREIGN_MODULE, 90),
                _candidate(FOREIGN, FOREIGN_MODULE, 80),
                _candidate(PRIMARY, PRIMARY_MODULE, 70),
            ],
        )

        assert package.supporting_symbols == [FOREIGN]
        assert package.relationship_summary.symbol_count == 2


# ---------------------------------------------------------------------------
# Test: Serializer availability in a fresh interpreter
# ---------------------------------------------------------------------------


class TestFreshProcessImportPath:
    """The documented import path serializes without caller-side registration."""

    def test_execute_serializes_in_a_fresh_interpreter(self) -> None:
        payload = run_in_fresh_interpreter(
            "implement_feature", "ImplementFeatureCapability"
        )

        assert_fresh_execution_is_honest(payload)
        assert "gateway.retry.should_retry" in payload["context"]

    def test_factory_is_the_only_serializer_route(self) -> None:
        """Registration lives in the serialization layer, not here."""
        source = (
            REPO_ROOT / "packages" / "capabilities" / "implement_feature.py"
        ).read_text(encoding="utf-8")

        assert "SerializerFactory.create(ProviderType.openai)" in source
        assert "OpenAISerializer" not in source
        assert "packages.serializers.openai" not in source
