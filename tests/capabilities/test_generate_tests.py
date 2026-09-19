"""Tests for the dormant ``generate-tests`` capability.

The capability is context assembly only: it turns a query into a pinned
``TEST`` plan, a profile-derived ``ContextQuery``, an assembled
``ContextPackage`` and a ``ProviderRequest``. It never authors test code, never
touches the filesystem, and never calls a provider.

These tests keep the framework seams honest: the planner-vocabulary
translation (``TEST`` plan versus ``GENERATE_TESTS`` result intent), the
profile wiring into ``ContextQuery``, the five-stage pipeline order, the
serializer bootstrap that makes the documented import path work in a fresh
interpreter, the rule that ranked candidates are never reported as callers or
callees, and dormancy (exported, but not wired into gateway/pipeline/workflows).
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
from contextlib import ExitStack, contextmanager
from itertools import permutations
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import patch

import pytest

from packages.capabilities import (
    GENERATE_TESTS_PROFILE,
    Capability,
    CapabilityFactory,
    CapabilityRegistry,
    DebugCapability,
    ExplainCapability,
    GenerateTestsCapability,
    PlannerIntent,
    RefactorCapability,
    RetrievalProfile,
)
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import (
    ARCHITECTURE_REVIEW_PROFILE,
    DEBUG_PROFILE,
    EXPLAIN_PROFILE,
    IMPLEMENT_PROFILE,
    REFACTOR_PROFILE,
)
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
    FRESH_INTERPRETER_SCRIPT,
    assert_fresh_execution_is_honest,
    run_in_fresh_interpreter,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CAPABILITY_PATH = Path("packages/capabilities/generate_tests.py")

#: Repository root, used to point a fresh interpreter at ``packages.*`` the
#: same way the documented public API is imported.
REPO_ROOT = Path(__file__).resolve().parents[2]

QUERY = "Generate tests for the gateway retry policy"

PRIMARY = "apps.gateway.policies.RetryPolicy.should_retry"
SIBLING = "apps.gateway.policies.RetryPolicy.__init__"
FOREIGN = "packages.providers.base.Provider.chat"

PRIMARY_MODULE = "apps/gateway/policies.py"
SIBLING_MODULE = "apps/gateway/retries.py"
FOREIGN_MODULE = "packages/providers/base.py"

#: Capability vocabulary token (``packages.capabilities.base``).
CAPABILITY_INTENT_VALUE = "GENERATE_TESTS"

#: Planner vocabulary token (``packages.planning.intent``).
PLANNER_INTENT_VALUE = "TEST"


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


def _candidate(qualified_name: str, module: str, score: int) -> ContextCandidate:
    """Return a ranked context candidate."""
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


def _make_empty_context_result() -> ContextResult:
    """Return a context result with no candidates."""
    return ContextResult(
        candidates=[],
        selected_modules=[],
        budget=ContextBudgetResult(
            estimated_tokens=0,
            estimated_symbols=0,
            estimated_modules=0,
            within_budget=True,
            truncated=False,
        ),
    )


def _result_with(
    candidates: list[ContextCandidate], estimated_tokens: int = 1024
) -> ContextResult:
    """Return a context result built from ``candidates``."""
    modules: list[str] = []
    for candidate in candidates:
        if candidate.module not in modules:
            modules.append(candidate.module)
    budget = ContextBudgetResult(
        estimated_tokens=estimated_tokens,
        estimated_symbols=len(candidates),
        estimated_modules=len(modules),
        within_budget=True,
        truncated=False,
    )
    return ContextResult(
        candidates=candidates, selected_modules=modules, budget=budget
    )


def _make_plan(
    intent: str = PLANNER_INTENT_VALUE, maximum_depth: int = 1
) -> ContextPlan:
    """Return a plan shaped like the planner's ``TEST`` rule output.

    The real :class:`ContextPlanner` pins ``maximum_depth=1`` for ``TEST``;
    the profile is expected to raise that to ``2`` regardless.
    """
    return ContextPlan(
        intent=intent,
        primary_symbols=(),
        relationship_expansion=True,
        ranking_profile=intent,
        maximum_depth=maximum_depth,
        include_callers=True,
        include_callees=False,
        include_modules=True,
        include_diagnostics=True,
        estimated_complexity="MODERATE",
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


def _make_provider_request(content: str = QUERY) -> ProviderRequest:
    """Return a minimal provider request."""
    return ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[{"role": "user", "content": content}],
        model="default",
    )


@contextmanager
def patched_pipeline(
    *,
    plan: ContextPlan | None = None,
    context_result: ContextResult | None = None,
    provider_request: ProviderRequest | None = None,
) -> Iterator[dict[str, Any]]:
    """Patch the collaborators used by the pipeline stages.

    The capability's own stage methods run for real; only the planner, the
    context builder, and the serializer factory are replaced so tests can
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
            patch("packages.capabilities.generate_tests.SerializerFactory")
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
    :class:`ContextPlanner` would otherwise classify debug-like or
    implementation-like wording as ``DEBUG``/``IMPLEMENT``/``EXPLAIN``.
    """
    stack = ExitStack()
    try:
        builder_cls = stack.enter_context(
            patch("packages.context.builder.ContextBuilder")
        )
        builder_cls.return_value.build.return_value = _make_context_result()
        serializer_cls = stack.enter_context(
            patch("packages.capabilities.generate_tests.SerializerFactory")
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
def capability() -> GenerateTestsCapability:
    """Return a freshly constructed capability."""
    return GenerateTestsCapability()


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """Return a registry with every implemented capability registered."""
    reg = CapabilityRegistry()
    reg.register("explain", ExplainCapability)
    reg.register("debug", DebugCapability)
    reg.register("refactor", RefactorCapability)
    reg.register("generate-tests", GenerateTestsCapability)
    return reg


@pytest.fixture()
def source_tree() -> ast.Module:
    """Return the parsed AST of the capability module."""
    return ast.parse(CAPABILITY_PATH.read_text(encoding="utf-8"))



# ---------------------------------------------------------------------------
# Test: Package exports and registry integration
# ---------------------------------------------------------------------------


class TestRegistrationAndExports:
    """Capability is exported and resolvable without gateway wiring."""

    def test_capability_class_lives_in_its_own_module(self) -> None:
        assert GenerateTestsCapability.__module__ == (
            "packages.capabilities.generate_tests"
        )

    def test_exports_listed_in_dunder_all(self) -> None:
        import packages.capabilities as capabilities_pkg

        assert "GenerateTestsCapability" in capabilities_pkg.__all__
        assert "GENERATE_TESTS_PROFILE" in capabilities_pkg.__all__

    def test_registry_resolves_capability_class(
        self, registry: CapabilityRegistry
    ) -> None:
        assert registry.get("generate-tests") is GenerateTestsCapability

    def test_registry_reports_the_capability_name(
        self, registry: CapabilityRegistry
    ) -> None:
        assert registry.has("generate-tests") is True
        assert sorted(registry.all()) == [
            "debug",
            "explain",
            "generate-tests",
            "refactor",
        ]

    def test_factory_creates_capability(
        self, registry: CapabilityRegistry
    ) -> None:
        created = CapabilityFactory(registry).create("generate-tests")

        assert isinstance(created, GenerateTestsCapability)

    def test_factory_created_instances_are_independent(
        self, registry: CapabilityRegistry
    ) -> None:
        factory = CapabilityFactory(registry)

        assert factory.create("generate-tests") is not factory.create(
            "generate-tests"
        )

    def test_capability_extends_base_capability(self) -> None:
        assert issubclass(GenerateTestsCapability, Capability)

    def test_fresh_registry_does_not_include_capability(self) -> None:
        assert CapabilityRegistry().has("generate-tests") is False

    def test_importing_the_module_registers_nothing(self) -> None:
        import packages.capabilities.generate_tests as module

        assert not hasattr(module, "REGISTRY")
        assert not hasattr(module, "_default_registry")


# ---------------------------------------------------------------------------
# Test: Capability identity
# ---------------------------------------------------------------------------


class TestCapabilityIdentity:
    """Name, intent, and profile are the capability's contract."""

    def test_name(self, capability: GenerateTestsCapability) -> None:
        assert capability.name == "generate-tests"

    def test_intent_is_generate_tests(
        self, capability: GenerateTestsCapability
    ) -> None:
        assert capability.intent is PlannerIntent.GENERATE_TESTS

    def test_intent_value(self, capability: GenerateTestsCapability) -> None:
        assert capability.intent.value == CAPABILITY_INTENT_VALUE

    def test_intent_is_a_new_vocabulary_member(self) -> None:
        values = {member.value for member in PlannerIntent}

        assert CAPABILITY_INTENT_VALUE in values
        assert values == {
            "EXPLAIN",
            "DEBUG",
            "REVIEW",
            "REFACTOR",
            "IMPLEMENT",
            "GENERATE_TESTS",
        }

    def test_capability_intent_has_no_planner_counterpart(self) -> None:
        planner_values = {
            Intent.EXPLAIN,
            Intent.IMPLEMENT,
            Intent.REFACTOR,
            Intent.DEBUG,
            Intent.TEST,
            Intent.SEARCH,
            Intent.DEFAULT,
        }

        assert CAPABILITY_INTENT_VALUE not in planner_values
        assert PLANNER_INTENT_VALUE in planner_values

    def test_intents_are_unique_across_capabilities(self) -> None:
        capabilities = (
            ExplainCapability(),
            DebugCapability(),
            RefactorCapability(),
            GenerateTestsCapability(),
        )

        assert len({item.intent for item in capabilities}) == len(capabilities)

    def test_profile_is_the_module_singleton(
        self, capability: GenerateTestsCapability
    ) -> None:
        assert capability.profile is GENERATE_TESTS_PROFILE

    def test_profile_is_a_retrieval_profile(
        self, capability: GenerateTestsCapability
    ) -> None:
        assert isinstance(capability.profile, RetrievalProfile)

    def test_capability_is_not_a_sibling_subclass(self) -> None:
        assert not issubclass(GenerateTestsCapability, ExplainCapability)
        assert not issubclass(GenerateTestsCapability, DebugCapability)
        assert not issubclass(GenerateTestsCapability, RefactorCapability)

    def test_sibling_capabilities_keep_their_profiles(self) -> None:
        assert ExplainCapability().profile is EXPLAIN_PROFILE
        assert DebugCapability().profile is DEBUG_PROFILE
        assert RefactorCapability().profile is REFACTOR_PROFILE

    def test_identity_attributes_are_read_only(
        self, capability: GenerateTestsCapability
    ) -> None:
        with pytest.raises(AttributeError):
            capability.name = "other"  # type: ignore[misc]

    def test_capability_holds_no_instance_state(
        self, capability: GenerateTestsCapability
    ) -> None:
        assert capability.__dict__ == {}


# ---------------------------------------------------------------------------
# Test: Retrieval profile
# ---------------------------------------------------------------------------


class TestGenerateTestsProfile:
    """The coverage-oriented profile is pinned and isolated."""

    def test_profile_name(self) -> None:
        assert GENERATE_TESTS_PROFILE.name == "generate-tests"

    def test_callers_are_included_and_callees_are_not(self) -> None:
        """Declarative retrieval intent -- see the test right below.

        ``include_callers`` / ``include_callees`` describe what a future
        relationship-aware retrieval should prefer. Their only live effect is
        the ``relationship_expansion`` switch they feed in stage 3.
        """
        assert GENERATE_TESTS_PROFILE.include_callers is True
        assert GENERATE_TESTS_PROFILE.include_callees is False

    def test_caller_and_callee_flags_never_fill_the_package_lists(
        self, capability: GenerateTestsCapability
    ) -> None:
        """The flags steer ranking; they do not invent CALLS edges."""
        package = capability._stage_assemble_package(
            _make_context_result(), _empty_index()
        )

        assert GENERATE_TESTS_PROFILE.include_callers is True
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0

    def test_test_files_are_in_scope(self) -> None:
        assert GENERATE_TESTS_PROFILE.include_tests is True

    def test_dependencies_and_dependents_are_in_scope(self) -> None:
        assert GENERATE_TESTS_PROFILE.include_dependencies is True
        assert GENERATE_TESTS_PROFILE.include_dependents is True

    def test_dead_code_is_excluded(self) -> None:
        assert GENERATE_TESTS_PROFILE.include_dead_code is False

    def test_diagnostics_are_included(self) -> None:
        assert GENERATE_TESTS_PROFILE.include_diagnostics is True

    def test_profile_budget(self) -> None:
        assert GENERATE_TESTS_PROFILE.max_context_tokens == 4096

    def test_profile_depth(self) -> None:
        assert GENERATE_TESTS_PROFILE.relationship_depth == 2


    def test_profile_matches_the_documented_table(self) -> None:
        expected = {
            "name": "generate-tests",
            "include_callers": True,
            "include_callees": False,
            "include_dependencies": True,
            "include_dependents": True,
            "include_tests": True,
            "include_dead_code": False,
            "include_diagnostics": True,
            "relationship_depth": 2,
            "max_context_tokens": 4096,
        }

        actual = {
            field.name: getattr(GENERATE_TESTS_PROFILE, field.name)
            for field in dataclasses.fields(GENERATE_TESTS_PROFILE)
        }

        assert actual == expected

    def test_profile_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            GENERATE_TESTS_PROFILE.relationship_depth = 7  # type: ignore[misc]

    def test_profile_is_hashable(self) -> None:
        assert hash(GENERATE_TESTS_PROFILE) == hash(GENERATE_TESTS_PROFILE)

    def test_profile_is_module_level_singleton(self) -> None:
        import packages.capabilities.profiles as profiles_module

        assert GENERATE_TESTS_PROFILE is profiles_module.GENERATE_TESTS_PROFILE

    def test_profile_does_not_alias_sibling_profiles(self) -> None:
        assert GENERATE_TESTS_PROFILE is not EXPLAIN_PROFILE
        assert GENERATE_TESTS_PROFILE is not DEBUG_PROFILE
        assert GENERATE_TESTS_PROFILE is not REFACTOR_PROFILE
        assert GENERATE_TESTS_PROFILE is not ARCHITECTURE_REVIEW_PROFILE

    def test_profile_is_distinct_from_every_sibling(self) -> None:
        siblings = (
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            IMPLEMENT_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
        )

        assert all(GENERATE_TESTS_PROFILE != other for other in siblings)

    def test_all_profiles_stay_distinct(self) -> None:
        profiles = (
            EXPLAIN_PROFILE,
            DEBUG_PROFILE,
            REFACTOR_PROFILE,
            IMPLEMENT_PROFILE,
            GENERATE_TESTS_PROFILE,
            ARCHITECTURE_REVIEW_PROFILE,
        )

        assert len({hash(item) for item in profiles}) == len(profiles)

    def test_profile_declares_only_scalar_fields(self) -> None:
        for field in dataclasses.fields(GENERATE_TESTS_PROFILE):
            value = getattr(GENERATE_TESTS_PROFILE, field.name)
            assert isinstance(value, (bool, int, str))
            assert not isinstance(value, float)

    def test_profiles_expose_the_same_field_names(self) -> None:
        def names(profile: RetrievalProfile) -> tuple[str, ...]:
            return tuple(field.name for field in dataclasses.fields(profile))

        assert names(GENERATE_TESTS_PROFILE) == names(EXPLAIN_PROFILE)
        assert names(GENERATE_TESTS_PROFILE) == names(DEBUG_PROFILE)
        assert names(GENERATE_TESTS_PROFILE) == names(REFACTOR_PROFILE)
        assert names(GENERATE_TESTS_PROFILE) == names(ARCHITECTURE_REVIEW_PROFILE)

    def test_sibling_profile_values_are_unchanged(self) -> None:
        assert EXPLAIN_PROFILE.relationship_depth == 1
        assert EXPLAIN_PROFILE.include_callers is False
        assert DEBUG_PROFILE.relationship_depth == 2
        assert DEBUG_PROFILE.include_callees is True
        assert REFACTOR_PROFILE.relationship_depth == 3
        assert REFACTOR_PROFILE.include_dead_code is True
        assert ARCHITECTURE_REVIEW_PROFILE.max_context_tokens == 8192


# ---------------------------------------------------------------------------
# Test: Pipeline stages
# ---------------------------------------------------------------------------


class TestPipelineStages:
    """The five documented stages run in order over existing components."""

    def test_planner_is_invoked_once_with_the_query(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        mocks["planner"].return_value.build.assert_called_once()

    def test_repository_is_queried(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks, patch.object(
            RepositoryIndex, "find", autospec=True
        ) as find:
            find.return_value = []
            capability.execute(query=QUERY, repository_index=index)

        assert find.call_args.args[1] == QUERY
        mocks["planner"].return_value.build.assert_called_once()


    def test_context_builder_is_configured_from_the_profile(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert isinstance(query, ContextQuery)
        assert query.max_tokens == GENERATE_TESTS_PROFILE.max_context_tokens
        assert query.maximum_depth == GENERATE_TESTS_PROFILE.relationship_depth
        assert query.relationship_expansion is True

    def test_context_builder_receives_the_repository_index(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        assert mocks["builder"].call_args.kwargs["index"] is index

    def test_profile_settings_win_over_plan_values(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        plan = _make_plan(intent="TEST", maximum_depth=0)

        with patched_pipeline(plan=plan) as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.maximum_depth == GENERATE_TESTS_PROFILE.relationship_depth

    def test_package_is_assembled_from_the_context_result(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        package: ContextPackage = result.context_package
        assert isinstance(package, ContextPackage)
        assert package.primary_symbol == PRIMARY
        assert package.supporting_symbols == [SIBLING, FOREIGN]
        assert package.estimated_tokens == 1024
        assert package.relationship_summary.symbol_count == 3
        assert package.relationship_summary.module_count == 2

    def test_serializer_receives_the_assembled_package(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            result = capability.execute(query=QUERY, repository_index=index)

        serialize = mocks["serializer"].create.return_value.serialize
        assert serialize.call_args.kwargs["context_package"] == (
            result.context_package
        )
        assert serialize.call_args.kwargs["messages"] == [
            {"role": "user", "content": QUERY}
        ]

    def test_index_matches_become_selected_symbols(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline(), patch.object(
            RepositoryIndex, "find", autospec=True
        ) as find:
            find.return_value = [_symbol(PRIMARY), _symbol(SIBLING)]
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.selected_symbols == (PRIMARY, SIBLING)



# ---------------------------------------------------------------------------
# Test: Planner intent pinning across vocabularies
# ---------------------------------------------------------------------------


class TestPlannerIntentTranslation:
    """The planner is pinned through the planner's own vocabulary."""

    def test_planner_receives_the_test_intent_override(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["planner"].return_value.build
        assert build.call_args.kwargs["intent_override"] == PLANNER_INTENT_VALUE

    def test_capability_intent_is_never_sent_to_the_planner(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["planner"].return_value.build
        assert CAPABILITY_INTENT_VALUE not in build.call_args.kwargs.values()

    def test_override_token_is_a_real_planner_intent(self) -> None:
        from packages.capabilities.generate_tests import (
            PLANNER_INTENT_FOR_TESTS,
        )

        assert PLANNER_INTENT_FOR_TESTS == Intent.TEST
        assert Intent.detect(["add coverage for the serializer"]) == Intent.TEST

    def test_planner_receives_the_query_and_index(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        build = mocks["planner"].return_value.build
        assert build.call_args.kwargs["user_messages"] == [QUERY]
        assert build.call_args.kwargs["repository_index"] is index

    def test_plan_keeps_the_planner_vocabulary(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline(plan=_make_plan(intent=PLANNER_INTENT_VALUE)):
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.context_plan.intent == PLANNER_INTENT_VALUE

    def test_result_reports_the_capability_vocabulary(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.intent == CAPABILITY_INTENT_VALUE

    def test_the_two_vocabularies_deliberately_diverge(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.intent != result.context_plan.intent

    def test_a_debug_plan_never_leaks_into_the_result(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        plan = _make_plan(intent="DEBUG")

        with patched_pipeline(plan=plan):
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.context_plan.intent == "DEBUG"
        assert result.intent == CAPABILITY_INTENT_VALUE

    @pytest.mark.parametrize(
        ("wording", "planner_would_choose"),
        [
            ("Why is auth.py failing?", "DEBUG"),
            ("Fix the broken retry policy", "DEBUG"),
            ("Implement the gateway retry policy", "IMPLEMENT"),
            ("Explain the serializer factory", "EXPLAIN"),
            ("Rename the retry helper", "REFACTOR"),
            ("Where is should_retry used?", "SEARCH"),
            ("hello", "DEFAULT"),
            ("", "DEFAULT"),
        ],
    )
    def test_wording_cannot_change_the_result_intent(
        self,
        capability: GenerateTestsCapability,
        wording: str,
        planner_would_choose: str,
    ) -> None:
        """The real planner would classify these phrasings differently."""
        index = _empty_index()

        with patched_context_and_serializer():
            result = capability.execute(query=wording, repository_index=index)

        assert result.context_plan.intent == PLANNER_INTENT_VALUE
        assert result.intent == CAPABILITY_INTENT_VALUE

    @pytest.mark.parametrize(
        "wording",
        [
            "Why is auth.py failing?",
            "Implement the gateway retry policy",
            "Explain the serializer factory",
            "hello",
        ],
    )
    def test_override_beats_what_keyword_detection_would_pick(
        self, wording: str
    ) -> None:
        """Control: unpinned planning really does drift by wording."""
        index = _empty_index()
        planner = ContextPlanner()
        unpinned = planner.build(
            user_messages=[wording], repository_index=index
        )
        pinned = planner.build(
            user_messages=[wording],
            repository_index=index,
            intent_override=PLANNER_INTENT_VALUE,
        )

        assert pinned.intent == PLANNER_INTENT_VALUE
        assert unpinned.intent != PLANNER_INTENT_VALUE


# ---------------------------------------------------------------------------
# Test: ContextQuery derivation
# ---------------------------------------------------------------------------


class TestContextQueryDerivation:
    """Every ContextQuery field traces to the profile or the planner."""

    def test_query_text_is_the_original_user_query(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.text == QUERY

    def test_token_budget_comes_from_the_profile(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_tokens == 4096
        assert query.max_tokens != ARCHITECTURE_REVIEW_PROFILE.max_context_tokens

    def test_relationship_depth_comes_from_the_profile(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.maximum_depth == 2
        assert query.maximum_depth != REFACTOR_PROFILE.relationship_depth

    def test_depth_is_never_reused_as_the_candidate_ceiling(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.max_symbols == ContextQuery.__dataclass_fields__[
            "max_symbols"
        ].default
        assert query.max_symbols != GENERATE_TESTS_PROFILE.relationship_depth

    def test_relationship_expansion_follows_the_caller_flag(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        assert query.relationship_expansion is (
            GENERATE_TESTS_PROFILE.include_callers
            or GENERATE_TESTS_PROFILE.include_callees
        )
        assert query.relationship_expansion is True

    def test_query_has_no_symbol_or_module_filter_channel(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        names = {field.name for field in dataclasses.fields(ContextQuery)}

        assert "symbols" not in names
        assert "module_filter" not in names
        assert "keywords" not in names
        assert not hasattr(query, "symbols")
        assert not hasattr(query, "module_filter")

    def test_query_construction_uses_only_supported_fields(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        query = mocks["builder"].return_value.build.call_args.kwargs["query"]
        populated = {
            field.name: getattr(query, field.name)
            for field in dataclasses.fields(ContextQuery)
        }

        assert populated == {
            "text": QUERY,
            "max_symbols": 20,
            "max_modules": 10,
            "max_tokens": 4096,
            "maximum_depth": 2,
            "relationship_expansion": True,
        }


# ---------------------------------------------------------------------------
# Test: Context package assembly
# ---------------------------------------------------------------------------


class TestPackageAssembly:
    """The package is orchestration of builder output, not re-ranking.

    Ranked membership -- one primary, the rest supporting -- and the modules
    those symbols live in are what builder output actually supports. The
    caller and callee lists stay empty, because candidate order is not a
    ``CALLS`` relationship.
    """

    def test_first_candidate_is_the_primary(self, capability: GenerateTestsCapability) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.primary_symbol == PRIMARY

    def test_remaining_candidates_are_supporting_in_rank_order(
        self, capability: GenerateTestsCapability    ) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
                _candidate(FOREIGN, FOREIGN_MODULE, 60),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.supporting_symbols == [SIBLING, FOREIGN]

    def test_supporting_symbols_are_deduplicated(self, capability: GenerateTestsCapability) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
                _candidate(SIBLING, FOREIGN_MODULE, 80),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.supporting_symbols.count(SIBLING) == 1

    def test_rank_order_never_creates_callers_or_callees(
        self, capability: GenerateTestsCapability
    ) -> None:
        """A lower-ranked candidate in the same module is not a callee.

        The primary symbol is the first candidate, so the module-relative rule
        this replaces had nothing before the primary to label a caller and
        everything after it to label a callee. Candidate position is ranking
        output, not a ``CALLS`` edge.
        """
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.primary_symbol == PRIMARY
        assert package.supporting_symbols == [SIBLING]
        assert package.related_callers == []
        assert package.related_callees == []

    def test_same_module_neighbours_stay_supporting_symbols(
        self, capability: GenerateTestsCapability
    ) -> None:
        """Shared-module membership survives, as symbols -- not as edges."""
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, PRIMARY_MODULE, 90),
                _candidate(FOREIGN, PRIMARY_MODULE, 60),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.supporting_symbols == [SIBLING, FOREIGN]
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == [PRIMARY_MODULE]

    def test_no_candidate_order_produces_a_relationship(
        self, capability: GenerateTestsCapability
    ) -> None:
        """Every permutation of the same candidates reports no edges."""
        index = _empty_index()
        candidates = [
            _candidate(PRIMARY, PRIMARY_MODULE, 120),
            _candidate(SIBLING, PRIMARY_MODULE, 90),
            _candidate(FOREIGN, FOREIGN_MODULE, 60),
        ]

        for order in permutations(candidates):
            package = capability._stage_assemble_package(
                _result_with(list(order)), index
            )

            assert package.primary_symbol == order[0].qualified_name
            assert package.supporting_symbols != []
            assert package.related_callers == []
            assert package.related_callees == []
            assert package.relationship_summary.caller_count == 0
            assert package.relationship_summary.callee_count == 0
            assert package.relationship_summary.module_count == 2
            assert package.relationship_summary.symbol_count == 3

    def test_cross_module_candidates_are_not_relationships(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(FOREIGN, FOREIGN_MODULE, 60),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == sorted(
            [PRIMARY_MODULE, FOREIGN_MODULE]
        )

    def test_relationship_summary_counts_match_the_reported_lists(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(SIBLING, PRIMARY_MODULE, 90),
                _candidate(PRIMARY, PRIMARY_MODULE, 60),
                _candidate(FOREIGN, FOREIGN_MODULE, 30),
            ]
        )

        package = capability._stage_assemble_package(result, index)
        summary = package.relationship_summary

        assert summary.caller_count == len(package.related_callers)
        assert summary.callee_count == len(package.related_callees)
        assert summary.module_count == len(package.related_modules)
        assert summary.caller_count == 0
        assert summary.callee_count == 0
        assert summary.module_count == 2
        assert summary.symbol_count == 3


    def test_empty_result_produces_an_empty_package(
        self, capability: GenerateTestsCapability    ) -> None:
        index = _empty_index()

        package = capability._stage_assemble_package(
            _make_empty_context_result(), index
        )

        assert package.primary_symbol == ""
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == []
        assert package.estimated_tokens == 0
        assert package.relationship_summary.symbol_count == 0

    def test_single_symbol_package_has_no_relationships(
        self, capability: GenerateTestsCapability    ) -> None:
        index = _empty_index()
        result = _result_with([_candidate(PRIMARY, PRIMARY_MODULE, 120)])

        package = capability._stage_assemble_package(result, index)

        assert package.primary_symbol == PRIMARY
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.relationship_summary.module_count == 1

    def test_token_estimate_flows_from_the_budget(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        result = _result_with(
            [_candidate(PRIMARY, PRIMARY_MODULE, 120)],
            estimated_tokens=4090,
        )

        package = capability._stage_assemble_package(result, index)

        assert package.estimated_tokens == 4090
        assert package.metadata.estimated_tokens == 4090

    def test_symbol_order_survives_unsorted_candidates(
        self, capability: GenerateTestsCapability    ) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(FOREIGN, FOREIGN_MODULE, 10),
                _candidate(PRIMARY, PRIMARY_MODULE, 200),
                _candidate(SIBLING, PRIMARY_MODULE, 100),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.primary_symbol == FOREIGN
        assert package.supporting_symbols == [PRIMARY, SIBLING]

    def test_related_modules_stay_sorted_and_deduplicated(
        self, capability: GenerateTestsCapability
    ) -> None:
        """The ordering guarantee that survives is the module list's own."""
        index = _empty_index()
        result = _result_with(
            [
                _candidate(FOREIGN, FOREIGN_MODULE, 300),
                _candidate(SIBLING, PRIMARY_MODULE, 200),
                _candidate(PRIMARY, SIBLING_MODULE, 100),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert package.related_modules == sorted(package.related_modules)
        assert len(package.related_modules) == len(set(package.related_modules))
        assert package.related_callers == []
        assert package.related_callees == []

    def test_package_field_types(self, capability: GenerateTestsCapability) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, PRIMARY_MODULE, 120),
                _candidate(SIBLING, SIBLING_MODULE, 60),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert isinstance(package, ContextPackage)
        assert isinstance(package.primary_symbol, str)
        assert isinstance(package.supporting_symbols, list)
        assert isinstance(package.related_callers, list)
        assert isinstance(package.related_callees, list)
        assert isinstance(package.related_modules, list)
        assert isinstance(package.estimated_tokens, int)
        assert isinstance(package.relationship_summary.caller_count, int)
        assert isinstance(package.metadata.estimated_tokens, int)


# ---------------------------------------------------------------------------
# Test: CapabilityResult contract
# ---------------------------------------------------------------------------


class TestCapabilityResultContract:
    """The result matches the shape siblings return."""

    def test_result_is_frozen(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert dataclasses.is_dataclass(CapabilityResult)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.query = "mutated"  # type: ignore[misc]

    def test_field_names_match_the_framework_contract(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        names = {field.name for field in dataclasses.fields(result)}

        assert names == {
            "query",
            "intent",
            "context_plan",
            "context_package",
            "provider_request",
            "selected_symbols",
            "selected_modules",
            "estimated_tokens",
            "execution_time_ms",
            "investigation_report",
        }

    def test_query_is_echoed_verbatim(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.query == QUERY

    def test_no_investigation_report_is_produced(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.investigation_report is None

    def test_selected_symbols_come_from_the_index(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline(), patch.object(
            RepositoryIndex, "find", autospec=True
        ) as find:
            find.return_value = [_symbol(PRIMARY), _symbol(SIBLING)]
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.selected_symbols == (PRIMARY, SIBLING)
        assert result.selected_symbols[0] == PRIMARY

    def test_selected_modules_come_from_the_builder(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.selected_modules == (PRIMARY_MODULE, FOREIGN_MODULE)
        assert isinstance(result.selected_modules, tuple)

    def test_estimated_tokens_are_the_package_estimate(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.estimated_tokens == result.context_package.estimated_tokens

    def test_execution_time_is_measured(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline():
            result = capability.execute(query=QUERY, repository_index=index)

        assert isinstance(result.execution_time_ms, float)
        assert result.execution_time_ms >= 0.0


# ---------------------------------------------------------------------------
# Test: Serialization seam
# ---------------------------------------------------------------------------


class TestSerializationStage:
    """Execution stops at ``ProviderRequest`` creation."""

    def test_openai_serializer_is_used(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        mocks["serializer"].create.assert_called_once_with(ProviderType.openai)

    def test_messages_hold_the_raw_query(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        with patched_pipeline() as mocks:
            capability.execute(query=QUERY, repository_index=index)

        serialize = mocks["serializer"].create.return_value.serialize
        assert serialize.call_args.kwargs["messages"] == [
            {"role": "user", "content": QUERY}
        ]

    def test_query_is_not_rewritten_before_serialization(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        awkward = "  generate  tests   please  "

        with patched_pipeline() as mocks:
            capability.execute(query=awkward, repository_index=index)

        serialize = mocks["serializer"].create.return_value.serialize
        assert serialize.call_args.kwargs["messages"] == [
            {"role": "user", "content": awkward}
        ]

    def test_provider_request_is_returned_untouched(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        request = _make_provider_request()

        with patched_pipeline(provider_request=request):
            result = capability.execute(query=QUERY, repository_index=index)

        assert result.provider_request is request

    def test_no_provider_response_field_exists(self) -> None:
        fields = {field.name for field in dataclasses.fields(ProviderRequest)}

        assert fields == {
            "provider_type",
            "messages",
            "model",
            "kwargs",
        }
        assert "response" not in fields
        assert "completion" not in fields

    def test_real_serializer_produces_a_request(
        self, capability: GenerateTestsCapability
    ) -> None:
        """End to end through the real factory and the real serializer."""
        index = _empty_index()

        result = capability.execute(query=QUERY, repository_index=index)

        assert isinstance(result.provider_request, ProviderRequest)
        assert (
            result.provider_request.provider_type is ProviderType.openai
        )
        assert result.provider_request.messages == [
            {"role": "user", "content": QUERY}
        ]

    def test_factory_is_the_only_serializer_route(self) -> None:
        """The factory creates; the serialization layer registers."""
        source = _source()

        assert "SerializerFactory.create(ProviderType.openai)" in source
        assert "OpenAISerializer" not in source
        # Registration belongs to packages.serializers, not to this capability,
        # so no sibling has to copy a bootstrap import of its own.
        assert "packages.serializers.openai" not in source


# ---------------------------------------------------------------------------
# Test: Serializer availability in a fresh interpreter
# ---------------------------------------------------------------------------


class TestFreshProcessImportPath:
    """The documented import path serializes without caller-side registration."""

    def test_execute_serializes_in_a_fresh_interpreter(self) -> None:
        payload = run_in_fresh_interpreter(
            "generate_tests", "GenerateTestsCapability"
        )

        assert_fresh_execution_is_honest(payload)
        # Serialization really ran: the real serializer injected a repository
        # context message on top of the user message.
        assert "gateway.retry.should_retry" in payload["context"]

    def test_probe_does_not_import_a_serializer_module(self) -> None:
        """Keep the subprocess honest: only the capability path is imported."""
        imported = [
            line.strip()
            for line in FRESH_INTERPRETER_SCRIPT.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

        assert "from packages.capabilities.__MODULE__ import __CLASS__" in imported
        assert not any(".serializers.openai" in line for line in imported)


# ---------------------------------------------------------------------------
# Test: Deterministic execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """The same query and index always produce the same package."""

    def test_package_is_identical_across_runs(self) -> None:
        index = _empty_index()
        capability = GenerateTestsCapability()

        first = capability.execute(query=QUERY, repository_index=index)
        second = capability.execute(query=QUERY, repository_index=index)

        assert first.context_package == second.context_package

    def test_provider_request_is_identical_across_runs(self) -> None:
        index = _empty_index()
        capability = GenerateTestsCapability()

        first = capability.execute(query=QUERY, repository_index=index)
        second = capability.execute(query=QUERY, repository_index=index)

        assert (
            first.provider_request.messages == second.provider_request.messages
        )
        assert first.provider_request.model == second.provider_request.model

    def test_plan_is_identical_across_runs(self) -> None:
        index = _empty_index()
        capability = GenerateTestsCapability()

        first = capability.execute(query=QUERY, repository_index=index)
        second = capability.execute(query=QUERY, repository_index=index)

        assert first.context_plan == second.context_plan

    def test_two_instances_agree(self) -> None:
        index = _empty_index()

        first = GenerateTestsCapability().execute(
            query=QUERY, repository_index=index
        )
        second = GenerateTestsCapability().execute(
            query=QUERY, repository_index=index
        )

        assert first.intent == second.intent
        assert first.context_package == second.context_package



# ---------------------------------------------------------------------------
# Test: Boundary rules
# ---------------------------------------------------------------------------

SOURCE_PATH = (
    Path(__file__).parents[2] / "packages" / "capabilities" / "generate_tests.py"
)


def _source() -> str:
    """Return the capability source without docstrings for boundary scans.

    Docstrings describe what the capability must *not* do, so they mention the
    forbidden activities in prose. Scanning code only keeps these checks
    honest.
    """
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    skip: set[int] = set()
    docstring_nodes = (
        ast.Module,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
    )
    for node in ast.walk(tree):
        if not isinstance(node, docstring_nodes) or not node.body:
            continue
        first = node.body[0]
        value = getattr(first, "value", None)
        if isinstance(first, ast.Expr) and isinstance(value, ast.Constant):
            if isinstance(value.value, str):
                end = first.end_lineno or first.lineno
                skip.update(range(first.lineno, end + 1))
    return "\n".join(
        line
        for number, line in enumerate(source.splitlines(), start=1)
        if number not in skip
    )


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

        for token in (
            "import ast",
            "ast.",
            "tokenize",
            "PythonAst",
            "SymbolExtractor",
        ):
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

    def test_no_filesystem_access(self) -> None:
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

        for token in ("codegen", "mutate", "mutation", "Template(", "jinja"):
            assert token not in source, token

    def test_no_intent_recognition(self) -> None:
        source = _source()

        for token in ("IntentResolver", "KeywordMatcher", "classify", "recognize"):
            assert token not in source, token

    def test_no_llm_calling_or_generation(self) -> None:
        source = _source()

        for token in (
            "chat.completions",
            ".complete(",
            "requests.post",
            "httpx",
            "aiohttp",
            "openai.",
        ):
            assert token not in source, token

    def test_no_verification_or_testing_execution(self) -> None:
        source = _source()

        for token in ("subprocess", "pytest.main", "run_tests", "Verification"):
            assert token not in source, token

    def test_no_planner_reimplementation(self) -> None:
        source = _source()

        for token in ("keywords=", "entity", "stem(", "synonym"):
            assert token not in source, token

    def test_no_query_rewriting(self) -> None:
        source = _source()

        for token in ("lower()", "strip()", "normalize"):
            assert token not in source, token

    def test_no_heuristic_scoring(self) -> None:
        source = _source()

        for token in (
            "score_candidate",
            "_score",
            "confidence",
            "0.9",
            "heuristic",
        ):
            assert token not in source, token

    def test_no_provider_execution(self) -> None:
        source = _source()

        for token in ("async def", "await ", "asyncio", "ProviderRegistry"):
            assert token not in source, token

    def test_capability_is_synchronous(self) -> None:
        assert not asyncio.iscoroutinefunction(GenerateTestsCapability.execute)


    def test_related_modules_are_deduplicated(self, capability: GenerateTestsCapability) -> None:
        index = _empty_index()
        result = _result_with(
            [
                _candidate(PRIMARY, FOREIGN_MODULE, 120),
                _candidate(SIBLING, SIBLING_MODULE, 90),
                _candidate(FOREIGN, FOREIGN_MODULE, 60),
            ]
        )

        package = capability._stage_assemble_package(result, index)

        assert len(package.related_modules) == len(set(package.related_modules))


# ---------------------------------------------------------------------------
# Test: No side effects
# ---------------------------------------------------------------------------


class TestNoSideEffects:
    """The whole pipeline is pure: no provider, no disk, no network."""

    def test_provider_is_never_invoked(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()

        def _fail(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("provider call attempted")

        with (
            patch(
                "packages.providers.factory.create_provider", side_effect=_fail
            ),
            patch("packages.providers.registry.get_registry", side_effect=_fail),
            patched_context_and_serializer(),
        ):
            result = capability.execute(query=QUERY, repository_index=index)

        assert isinstance(result, CapabilityResult)

    def test_files_are_never_written(
        self, capability: GenerateTestsCapability, tmp_path: Path
    ) -> None:
        index = _empty_index()

        def _fail(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("filesystem write attempted")

        target = "packages.capabilities.generate_tests."
        with (
            patch(target + "open", side_effect=_fail, create=True),
            patch(target + "Path", side_effect=_fail, create=True),
            patched_context_and_serializer(),
        ):
            result = capability.execute(query=QUERY, repository_index=index)

        assert isinstance(result, CapabilityResult)
        assert list(tmp_path.iterdir()) == []

    def test_nothing_is_written_to_disk_end_to_end(
        self, capability: GenerateTestsCapability, tmp_path: Path
    ) -> None:
        index = _empty_index()
        before = sorted(p.name for p in tmp_path.iterdir())

        capability.execute(query=QUERY, repository_index=index)
        capability.execute(query="debug", repository_index=index)

        assert sorted(p.name for p in tmp_path.iterdir()) == before

    def test_no_network_libraries_are_imported(self) -> None:
        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])

        for banned in (
            "socket",
            "http",
            "httpx",
            "requests",
            "urllib",
            "aiohttp",
            "subprocess",
        ):
            assert banned not in imported, banned

    def test_repository_index_is_not_mutated(
        self, capability: GenerateTestsCapability
    ) -> None:
        index = _empty_index()
        before_symbols = list(index.symbols())
        before_statistics = dataclasses.replace(index.statistics())

        with patched_context_and_serializer():
            capability.execute(query=QUERY, repository_index=index)

        assert list(index.symbols()) == before_symbols
        assert index.statistics() == before_statistics


# ---------------------------------------------------------------------------
# Test: Dormant delivery
# ---------------------------------------------------------------------------


class TestDormantDelivery:
    """Exported, tested, but not wired into gateway/pipeline/workflows."""

    def test_capability_is_constructible_standalone(self) -> None:
        capability = GenerateTestsCapability()

        assert capability.name == "generate-tests"

    def test_workflows_do_not_reference_the_capability(self) -> None:
        root = Path(__file__).parents[2] / "packages" / "workflows"

        offenders = [
            path.name
            for path in root.rglob("*.py")
            if "generate-tests" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_pipeline_does_not_reference_the_capability(self) -> None:
        root = Path(__file__).parents[2] / "packages" / "pipeline"

        offenders = [
            path.name
            for path in root.rglob("*.py")
            if "generate-tests" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_gateway_does_not_reference_the_capability(self) -> None:
        root = Path(__file__).parents[2] / "apps" / "gateway"

        offenders = [
            path.name
            for path in root.rglob("*.py")
            if "generate-tests" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_controller_does_not_reference_the_capability(self) -> None:
        root = Path(__file__).parents[2] / "packages" / "controller"

        offenders = [
            path.name
            for path in root.rglob("*.py")
            if "generate-tests" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_capability_source_has_no_gateway_imports(self) -> None:
        tree = ast.parse(_source())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)

        assert {module.split(".")[0] for module in imported} <= {
            "__future__",
            "packages",
            "dataclasses",
            "typing",
            "time",
        }
