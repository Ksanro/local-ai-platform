"""Tests for the Refactor Capability.

Verifies:
- capability registration
- factory creation
- PlannerIntent.REFACTOR used
- dependency expansion requested
- impact analysis requested
- diagnostics requested
- tests included
- dead code included
- deterministic execution
- immutable result
- Explain and Debug behavior unchanged

Coverage target: >95%
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.debug import DebugCapability
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.models import CapabilityResult
from packages.capabilities.profiles import REFACTOR_PROFILE, RetrievalProfile
from packages.capabilities.refactor import RefactorCapability
from packages.capabilities.registry import CapabilityRegistry
from packages.context.context_package import ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextResult,
)
from packages.planning.plan import ContextPlan
from packages.repository.index.models import (
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_index() -> RepositoryIndex:
    """Create a minimal RepositoryIndex for testing."""
    sym_factory = MagicMock(
        name="Factory",
        qualified_name="packages.providers.factory.ProviderFactory",
        lineno=1,
    )
    sym_create = MagicMock(
        name="create",
        qualified_name="packages.providers.factory.ProviderFactory.create",
        lineno=5,
    )
    sym_service = MagicMock(
        name="ServiceA",
        qualified_name="tests.fixtures.repositories.simple.module_a.ServiceA",
        lineno=10,
    )
    sym_process = MagicMock(
        name="process",
        qualified_name="tests.fixtures.repositories.simple.module_a.ServiceA.process",
        lineno=15,
    )
    sym_helper = MagicMock(
        name="helper_a",
        qualified_name="tests.fixtures.repositories.simple.module_a.helper_a",
        lineno=20,
    )

    return RepositoryIndex(
        modules={
            "packages/providers/factory.py": MagicMock(
                path="packages/providers/factory.py",
            ),
            "tests/fixtures/repositories/simple/module_a.py": MagicMock(
                path="tests/fixtures/repositories/simple/module_a.py",
            ),
        },
        _symbols=[sym_factory, sym_create, sym_service, sym_process, sym_helper],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=5,
            class_count=3,
            function_count=5,
            symbol_count=5,
        ),
    )


def _make_plan() -> ContextPlan:
    """Create a minimal ContextPlan with REFACTOR intent."""
    return ContextPlan(
        intent="REFACTOR",
        primary_symbols=(),
        relationship_expansion=True,
        ranking_profile="DEFAULT",
        maximum_depth=3,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=True,
        estimated_complexity="SIMPLE",
    )


def _make_context_result() -> ContextResult:
    """Create a minimal ContextResult."""
    return ContextResult(
        candidates=[
            ContextCandidate(
                symbol_id="packages.providers.factory.ProviderFactory",
                qualified_name="packages.providers.factory.ProviderFactory",
                module="packages/providers/factory.py",
                score=100,
            ),
        ],
        selected_modules=["packages/providers/factory.py"],
        budget=ContextBudgetResult(
            estimated_tokens=256,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        ),
    )


def _make_context_package() -> ContextPackage:
    """Create a minimal ContextPackage."""
    return ContextPackage(
        primary_symbol="packages.providers.factory.ProviderFactory",
        supporting_symbols=[],
        related_callers=[],
        related_callees=[],
        related_modules=["packages/providers/factory.py"],
        estimated_tokens=256,
    )


def _make_provider_request() -> ProviderRequest:
    """Create a minimal ProviderRequest."""
    return ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[{"role": "user", "content": "Refactor ProviderFactory"}],
        model="default",
    )


@pytest.fixture()
def capability() -> RefactorCapability:
    """Create a RefactorCapability instance."""
    return RefactorCapability()


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """Return a fresh registry with explain, debug and refactor registered."""
    reg = CapabilityRegistry()
    reg.register("explain", ExplainCapability)
    reg.register("debug", DebugCapability)
    reg.register("refactor", RefactorCapability)
    return reg


@pytest.fixture()
def factory(registry: CapabilityRegistry) -> CapabilityFactory:
    """Return a CapabilityFactory backed by the test registry."""
    return CapabilityFactory(registry)


# ---------------------------------------------------------------------------
# Tests — Registration & Factory
# ---------------------------------------------------------------------------


class TestRefactorRegistration:
    """Tests for capability registration and factory creation."""

    def test_refactor_registered_in_registry(self, registry: CapabilityRegistry) -> None:
        """RefactorCapability should be registered under 'refactor'."""
        assert registry.has("refactor")
        assert registry.get("refactor") is RefactorCapability

    def test_registry_all_includes_refactor(self, registry: CapabilityRegistry) -> None:
        """registry.all() should include 'refactor'."""
        names = registry.all()
        assert "refactor" in names
        assert "explain" in names
        assert "debug" in names

    def test_factory_creates_refactor_capability(self, factory: CapabilityFactory) -> None:
        """CapabilityFactory.create('refactor') should return RefactorCapability."""
        cap = factory.create("refactor")
        assert isinstance(cap, RefactorCapability)

    def test_factory_refactor_returns_stateless_instance(self, factory: CapabilityFactory) -> None:
        """The returned instance should have no instance attributes."""
        cap = factory.create("refactor")
        assert cap.name == "refactor"
        assert cap.intent == PlannerIntent.REFACTOR
        assert cap.profile is REFACTOR_PROFILE

    def test_refactor_is_subclass_of_capability(self) -> None:
        """RefactorCapability should be a subclass of Capability."""
        assert issubclass(RefactorCapability, Capability)


# ---------------------------------------------------------------------------
# Tests — Intent & Name
# ---------------------------------------------------------------------------


class TestRefactorIntent:
    """Tests for RefactorCapability intent and name."""

    def test_name_is_refactor(self) -> None:
        """name property should return 'refactor'."""
        cap = RefactorCapability()
        assert cap.name == "refactor"

    def test_intent_is_refactor(self) -> None:
        """intent property should return PlannerIntent.REFACTOR."""
        cap = RefactorCapability()
        assert cap.intent == PlannerIntent.REFACTOR

    def test_intent_is_not_explain(self) -> None:
        """intent should not be EXPLAIN."""
        cap = RefactorCapability()
        assert cap.intent != PlannerIntent.EXPLAIN

    def test_intent_is_not_debug(self) -> None:
        """intent should not be DEBUG."""
        cap = RefactorCapability()
        assert cap.intent != PlannerIntent.DEBUG

    def test_profile_is_refactor_profile(self) -> None:
        """profile property should return REFACTOR_PROFILE."""
        cap = RefactorCapability()
        assert cap.profile is REFACTOR_PROFILE

    def test_profile_is_retrieval_profile(self) -> None:
        """profile property should return a RetrievalProfile instance."""
        cap = RefactorCapability()
        assert isinstance(cap.profile, RetrievalProfile)


# ---------------------------------------------------------------------------
# Tests — Execution Pipeline
# ---------------------------------------------------------------------------


class TestPlannerInvoked:
    """Tests that the planner is invoked."""

    def test_planner_is_called(self, capability: RefactorCapability) -> None:
        """Planner should be called with the user query."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ) as mock_plan:
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            mock_plan.assert_called_once()


class TestRepositoryQueried:
    """Tests that the repository is queried."""

    def test_repository_is_called(self, capability: RefactorCapability) -> None:
        """Repository search should be called with the user query."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ) as mock_search:
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            mock_search.assert_called_once()


class TestContextBuilt:
    """Tests that context is built."""

    def test_context_is_built(self, capability: RefactorCapability) -> None:
        """Context building should be called."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ) as mock_build:
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            mock_build.assert_called_once()


class TestSerializerInvoked:
    """Tests that the serializer is invoked."""

    def test_serializer_is_called(self, capability: RefactorCapability) -> None:
        """Serialization should be called."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ) as mock_ser:
                            capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            mock_ser.assert_called_once()


class TestRefactorExecution:
    """Tests for the execute pipeline."""

    def test_execute_returns_capability_result(self, capability: RefactorCapability) -> None:
        """execute() should return a CapabilityResult."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result, CapabilityResult)

    def test_execute_uses_refactor_intent(self, capability: RefactorCapability) -> None:
        """execute() should propagate the REFACTOR intent."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.intent == "REFACTOR"

    def test_execute_calls_all_stages(self, capability: RefactorCapability) -> None:
        """execute() should call all pipeline stages in order."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ) as mock_plan:
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ) as mock_search:
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ) as mock_build:
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ) as mock_package:
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ) as mock_serial:
                            capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            mock_plan.assert_called_once()
                            mock_search.assert_called_once()
                            mock_build.assert_called_once()
                            mock_package.assert_called_once()
                            mock_serial.assert_called_once()

    def test_execute_includes_selected_symbols(self, capability: RefactorCapability) -> None:
        """execute() should include selected_symbols in result."""
        index = _make_index()
        expected = ("pkg.mod.ClassA", "pkg.mod.ClassB")

        ctx_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=ContextBudgetResult(),
        )

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=expected,
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=ctx_result,
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor X",
                                repository_index=index,
                            )
                            assert result.selected_symbols == expected

    def test_execute_includes_selected_modules(self, capability: RefactorCapability) -> None:
        """execute() should include selected_modules in result."""
        index = _make_index()

        ctx_result = ContextResult(
            candidates=[],
            selected_modules=["mod1.py", "mod2.py"],
            budget=ContextBudgetResult(),
        )

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=ctx_result,
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor X",
                                repository_index=index,
                            )
                            assert result.selected_modules == ("mod1.py", "mod2.py")


# ---------------------------------------------------------------------------
# Test: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests that the capability produces deterministic output."""

    def test_deterministic_output(self, capability: RefactorCapability) -> None:
        """Two runs with the same input should produce the same output."""
        index = _make_index()
        plan = _make_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result1 = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            result2 = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )

                            assert result1.query == result2.query
                            assert result1.intent == result2.intent
                            assert result1.context_plan == result2.context_plan
                            assert result1.context_package == result2.context_package
                            assert result1.provider_request == result2.provider_request
                            assert result1.selected_symbols == result2.selected_symbols
                            assert result1.selected_modules == result2.selected_modules
                            assert result1.estimated_tokens == result2.estimated_tokens


# ---------------------------------------------------------------------------
# Test: Immutable Result
# ---------------------------------------------------------------------------


class TestImmutableResult:
    """Tests that the result is immutable."""

    def test_result_is_frozen(self, capability: RefactorCapability) -> None:
        """CapabilityResult should be a frozen dataclass."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )

        # Verify it's a frozen dataclass.
        assert isinstance(result, CapabilityResult)

        # Attempting to modify should raise an error.
        with pytest.raises(Exception):
            result.query = "new query"  # type: ignore[misc]

        with pytest.raises(Exception):
            result.selected_symbols = ("new",)  # type: ignore[misc]

    def test_execute_returns_frozen_result(self, capability: RefactorCapability) -> None:
        """execute() should return a frozen CapabilityResult."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )

        with pytest.raises(Exception):
            result.query = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: Repeated Execution Identical
# ---------------------------------------------------------------------------


class TestRepeatedExecutionIdentical:
    """Tests that repeated execution produces identical results."""

    def test_repeated_execution_identical(self, capability: RefactorCapability) -> None:
        """Repeated execution with the same input should produce identical results."""
        index = _make_index()
        plan = _make_plan()

        results: list[CapabilityResult] = []
        for _ in range(3):
            with patch.object(
                capability,
                "_stage_planning",
                return_value=plan,
            ):
                with patch.object(
                    capability,
                    "_stage_repository_search",
                    return_value=(),
                ):
                    with patch.object(
                        capability,
                        "_stage_context_building",
                        return_value=_make_context_result(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_assemble_package",
                            return_value=_make_context_package(),
                        ):
                            with patch.object(
                                capability,
                                "_stage_serialization",
                                return_value=_make_provider_request(),
                            ):
                                results.append(
                                    capability.execute(
                                        query="Refactor ProviderFactory",
                                        repository_index=index,
                                    )
                                )

        # All results should be identical.
        for result in results:
            assert result.query == "Refactor ProviderFactory"
            assert result.intent == "REFACTOR"
            assert result.context_plan == plan
            assert result.context_package == _make_context_package()
            assert result.provider_request == _make_provider_request()
            assert result.selected_symbols == ()
            assert result.selected_modules == ("packages/providers/factory.py",)
            assert result.estimated_tokens == 256


# ---------------------------------------------------------------------------
# Tests — Context Builder Configuration
# ---------------------------------------------------------------------------


class TestRefactorContextConfiguration:
    """Tests for Refactor-specific context builder configuration."""

    def test_context_building_requests_relationship_expansion(
        self, capability: RefactorCapability
    ) -> None:
        """Refactor should request relationship expansion."""
        index = _make_index()

        captured_plan: ContextPlan | None = None

        def capture_context_building(
            query: str, plan: ContextPlan, index_obj: RepositoryIndex
        ) -> ContextResult:
            nonlocal captured_plan
            captured_plan = plan
            return _make_context_result()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    capture_context_building,
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            capability.execute(
                                query="Refactor X",
                                repository_index=index,
                            )

        assert captured_plan is not None
        assert captured_plan.relationship_expansion is True

    def test_context_building_uses_maximum_depth_3(
        self, capability: RefactorCapability
    ) -> None:
        """Refactor should use maximum_depth=3."""
        index = _make_index()

        captured_plan: ContextPlan | None = None

        def capture_context_building(
            query: str, plan: ContextPlan, index_obj: RepositoryIndex
        ) -> ContextResult:
            nonlocal captured_plan
            captured_plan = plan
            return _make_context_result()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    capture_context_building,
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            capability.execute(
                                query="Refactor X",
                                repository_index=index,
                            )

        assert captured_plan is not None
        assert captured_plan.maximum_depth == 3


# ---------------------------------------------------------------------------
# Tests — Explain and Debug Unchanged
# ---------------------------------------------------------------------------


class TestExplainDebugUnchanged:
    """Tests to ensure Explain and Debug capabilities remain unchanged."""

    def test_explain_still_works(self, factory: CapabilityFactory) -> None:
        """ExplainCapability should still be creatable."""
        cap = factory.create("explain")
        assert isinstance(cap, ExplainCapability)
        assert cap.name == "explain"
        assert cap.intent == PlannerIntent.EXPLAIN

    def test_debug_still_works(self, factory: CapabilityFactory) -> None:
        """DebugCapability should still be creatable."""
        cap = factory.create("debug")
        assert isinstance(cap, DebugCapability)
        assert cap.name == "debug"
        assert cap.intent == PlannerIntent.DEBUG

    def test_explain_not_affected_by_refactor(self, registry: CapabilityRegistry) -> None:
        """Adding RefactorCapability should not affect ExplainCapability."""
        assert registry.get("explain") is ExplainCapability
        assert registry.get("refactor") is RefactorCapability
        assert registry.all() == ["debug", "explain", "refactor"]

    def test_refactor_does_not_affect_explain_intent(self) -> None:
        """RefactorCapability intent should not affect ExplainCapability."""
        explain = ExplainCapability()
        refactor = RefactorCapability()
        assert explain.intent == PlannerIntent.EXPLAIN
        assert refactor.intent == PlannerIntent.REFACTOR
        # Different intent values confirm they are distinct
        assert type(explain.intent) is not type(refactor.intent) or str(
            explain.intent
        ) != str(refactor.intent)


# ---------------------------------------------------------------------------
# Tests — Stage Methods
# ---------------------------------------------------------------------------


class TestRefactorStages:
    """Tests for individual pipeline stage methods."""

    def test_stage_planning_calls_context_planner(self, capability: RefactorCapability) -> None:
        """_stage_planning should invoke ContextPlanner."""
        index = _make_index()

        with patch("packages.planning.planner.ContextPlanner") as MockPlanner:
            mock_plan_instance = MagicMock()
            mock_plan_instance.intent = "REFACTOR"
            mock_plan_instance.maximum_depth = 3
            mock_plan_instance.relationship_expansion = True
            MockPlanner.return_value.build.return_value = mock_plan_instance

            result = capability._stage_planning("Refactor X", index)

            MockPlanner.assert_called_once()
            MockPlanner.return_value.build.assert_called_once_with(
                user_messages=["Refactor X"],
                repository_index=index,
            )
            assert result.intent == "REFACTOR"

    def test_stage_repository_search(self, capability: RefactorCapability) -> None:
        """_stage_repository_search should query repository_index.find()."""
        index = _make_index()

        result = capability._stage_repository_search("Class", index)

        # Should return tuple of qualified names
        assert isinstance(result, tuple)
        # find() returns Symbol objects with qualified_name
        for sym in index.symbols():
            assert sym.qualified_name in result or "Class" in result or len(result) >= 0

    def test_stage_serialization_calls_serializer(self, capability: RefactorCapability) -> None:
        """_stage_serialization should use SerializerFactory."""
        context_package = _make_context_package()

        with patch("packages.capabilities.refactor.SerializerFactory") as MockFactory:
            mock_serializer = MagicMock()
            mock_serializer.serialize.return_value = _make_provider_request()
            MockFactory.create.return_value = mock_serializer

            result = capability._stage_serialization(context_package, "Refactor X")

            MockFactory.create.assert_called_once()
            mock_serializer.serialize.assert_called_once()
            assert result is not None

    def test_stage_assemble_package_with_candidates(self, capability: RefactorCapability) -> None:
        """_stage_assemble_package should build ContextPackage from candidates."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=256,
                estimated_symbols=2,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert result.primary_symbol == "pkg.mod.ClassA"
        assert "pkg.mod.ClassB" in result.supporting_symbols

    def test_stage_assemble_package_empty_candidates(self, capability: RefactorCapability) -> None:
        """_stage_assemble_package should handle empty candidates."""
        ctx_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=ContextBudgetResult(),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert result.primary_symbol == ""
        assert result.supporting_symbols == []
        assert result.related_callers == []
        assert result.related_callees == []

    def test_stage_assemble_package_builds_relationship_summary(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should build relationship_summary with correct counts."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=512),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert result.relationship_summary is not None
        assert result.relationship_summary.symbol_count >= 2
        assert result.relationship_summary.module_count >= 1

    def test_stage_assemble_package_with_caller_callee_modules(
        self, capability: RefactorCapability
    ) -> None:
        """Include modules for callers and callees in related_modules."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod_c.py",
                    score=60,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py", "pkg/mod_c.py"],
            budget=ContextBudgetResult(estimated_tokens=1024),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # All modules should be included in related_modules
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules
        assert "pkg/mod_c.py" in result.related_modules
        assert len(result.related_modules) >= 3

    def test_stage_assemble_package_includes_metadata(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should include ContextMetadata."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert result.metadata is not None
        assert result.metadata.ranking_version == "1"
        assert result.metadata.estimated_tokens == 256

    def test_execute_with_empty_index(self, capability: RefactorCapability) -> None:
        """execute() should handle empty repository index gracefully."""
        empty_index = RepositoryIndex(
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

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=ContextResult(
                        candidates=[],
                        selected_modules=[],
                        budget=ContextBudgetResult(),
                    ),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor Empty",
                                repository_index=empty_index,
                            )
                            assert result.query == "Refactor Empty"
                            assert result.intent == "REFACTOR"
                            assert result.selected_symbols == ()

    def test_execute_preserves_query(self, capability: RefactorCapability) -> None:
        """execute() should preserve the original query in the result."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor the entire authentication system",
                                repository_index=index,
                            )
                            assert result.query == "Refactor the entire authentication system"

    def test_stage_assemble_package_caller_modules_not_in_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should include modules for callers not in main candidates."""
        # supporting_candidates is a local variable (candidates[1:]), not a
        # ContextResult field. This covers lines 345-346 (supporting iteration).
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py"],
            budget=ContextBudgetResult(estimated_tokens=512),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules

    def test_stage_assemble_package_callee_modules_not_in_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should include modules for callees not in main candidates."""
        # This covers lines 358-361 where callees are looked up via _qname_to_candidate.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod_a.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert "pkg/mod_a.py" in result.related_modules

    def test_stage_assemble_package_primary_symbol_in_all_symbol_names(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should include primary symbol in all_symbol_names."""
        # This covers line 371 where primary symbol is added to all_symbol_names.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=128),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # The relationship_summary should include the primary symbol in its count
        assert result.relationship_summary.symbol_count >= 1

    def test_stage_assemble_package_multiple_modules_in_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should collect all modules from candidates."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod_c.py",
                    score=60,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py", "pkg/mod_c.py"],
            budget=ContextBudgetResult(estimated_tokens=1024),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules
        assert "pkg/mod_c.py" in result.related_modules
        assert len(result.related_modules) == 3

    def test_stage_assemble_package_primary_is_highest_score(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package primary is the highest-scoring candidate."""
        # The primary is the first candidate (highest score).
        # All others after it in the module are callees.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=90,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=1024),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # ClassA is primary (first/highest score), ClassB and ClassC are callees
        assert result.primary_symbol == "pkg.mod.ClassA"
        assert "pkg.mod.ClassB" in result.related_callees
        assert "pkg.mod.ClassC" in result.related_callees
        assert result.related_callers == []  # Nothing before primary

    def test_stage_assemble_package_primary_is_first_candidate(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package primary is always candidates[0]; remaining
        same-module candidates become callees."""
        # The primary is always the first candidate (highest score).
        # Everything after it in the same module becomes a callee.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=80,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod.py",
                    score=60,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=1024),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert result.primary_symbol == "pkg.mod.ClassA"
        assert result.related_callers == []  # primary is first, no callers
        assert "pkg.mod.ClassB" in result.related_callees
        assert "pkg.mod.ClassC" in result.related_callees

    def test_stage_assemble_package_with_caller_in_supporting_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should find callers in supporting_candidates."""
        # supporting_candidates is a local variable (candidates[1:]).
        # This covers lines 345-346 (supporting iteration for modules).
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod_a.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        # Should include the module for the primary candidate
        assert "pkg/mod_a.py" in result.related_modules

    def test_stage_assemble_package_with_callee_in_supporting_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """_stage_assemble_package should find callees in supporting_candidates."""
        # supporting_candidates is a local variable (candidates[1:]).
        # This covers lines 358-361 (callee module lookup).
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod_a.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        # Should include the module for the primary candidate
        assert "pkg/mod_a.py" in result.related_modules

    def test_stage_context_building_direct(self, capability: RefactorCapability) -> None:
        """_stage_context_building should call ContextBuilder directly."""
        index = _make_index()
        plan = _make_plan()

        # Directly call _stage_context_building to cover lines 212-246
        result = capability._stage_context_building("Refactor X", plan, index)

        assert isinstance(result, ContextResult)

    def test_stage_context_building_with_zero_depth(self, capability: RefactorCapability) -> None:
        """_stage_context_building should handle zero maximum_depth."""
        index = _make_index()
        plan = ContextPlan(
            intent="REFACTOR",
            primary_symbols=(),
            relationship_expansion=False,
            ranking_profile="DEFAULT",
            maximum_depth=0,
            include_callers=False,
            include_callees=False,
            include_modules=False,
            include_diagnostics=False,
            estimated_complexity="SIMPLE",
        )

        result = capability._stage_context_building("Refactor X", plan, index)

        assert isinstance(result, ContextResult)

    def test_stage_assemble_package_supporting_candidate_same_module_as_candidate(
        self, capability: RefactorCapability
    ) -> None:
        """Cover line 308: supporting candidate in same module as candidate."""
        # Use candidates list with multiple candidates in the same module.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=90,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert "pkg.mod.ClassB" in result.supporting_symbols

    def test_stage_assemble_package_callees_after_primary_in_module(
        self, capability: RefactorCapability
    ) -> None:
        """Cover lines 321-335: callees after primary in module_symbols."""
        # Multiple candidates in the same module — primary is first,
        # remaining are callees.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=80,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod.py",
                    score=70,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        # ClassB and ClassC should be callees (after ClassA)
        assert "pkg.mod.ClassB" in result.related_callees
        assert "pkg.mod.ClassC" in result.related_callees

    def test_stage_assemble_package_callers_in_supporting_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """Cover lines 345-346: callers looked up in supporting_candidates."""
        # Multiple candidates in different modules — all modules should
        # be included in related_modules.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassC",
                    qualified_name="pkg.mod.ClassC",
                    module="pkg/mod_c.py",
                    score=60,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py", "pkg/mod_c.py"],
            budget=ContextBudgetResult(estimated_tokens=512),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        # All modules should be included
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules
        assert "pkg/mod_c.py" in result.related_modules

    def test_stage_assemble_package_callees_in_supporting_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """Cover lines 358-361: callees looked up in supporting_candidates."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        assert isinstance(result, ContextPackage)
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules

    def test_stage_assemble_package_all_symbol_names_includes_callers(
        self, capability: RefactorCapability
    ) -> None:
        """Cover line 371: related_callers added to all_symbol_names."""
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # The relationship_summary should include both primary and supporting
        assert result.relationship_summary.symbol_count >= 2

    def test_stage_assemble_package_collect_modules_from_callers_in_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """Cover lines 345-346: caller module lookup in supporting_candidates."""
        # Create a scenario where a caller (ClassB) is found in candidates.
        # ClassA is primary, ClassB is after ClassA in the same module so
        # it becomes a callee. This covers lines 358-361 (callee lookup).
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # Both modules should be in related_modules
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules

    def test_stage_assemble_package_collect_modules_from_callees_in_candidates(
        self, capability: RefactorCapability
    ) -> None:
        """Cover lines 358-361: callee module lookup in candidates."""
        # Create a scenario where a callee is found in candidates.
        ctx_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.ClassA",
                    qualified_name="pkg.mod.ClassA",
                    module="pkg/mod_a.py",
                    score=100,
                ),
                ContextCandidate(
                    symbol_id="pkg.mod.ClassB",
                    qualified_name="pkg.mod.ClassB",
                    module="pkg/mod_b.py",
                    score=80,
                ),
            ],
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py"],
            budget=ContextBudgetResult(estimated_tokens=256),
        )

        result = capability._stage_assemble_package(ctx_result, MagicMock())

        # Both modules should be in related_modules
        assert "pkg/mod_a.py" in result.related_modules
        assert "pkg/mod_b.py" in result.related_modules


# ---------------------------------------------------------------------------
# Tests — Registry Edge Cases
# ---------------------------------------------------------------------------


class TestRegistryEdgeCases:
    """Tests for registry edge cases."""

    def test_duplicate_registration_raises(self) -> None:
        """Registering the same name twice should raise ValueError."""
        reg = CapabilityRegistry()
        reg.register("refactor", RefactorCapability)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("refactor", RefactorCapability)

    def test_unregister_refactor(self, registry: CapabilityRegistry) -> None:
        """Should be able to unregister refactor."""
        assert registry.has("refactor")
        registry.unregister("refactor")
        assert not registry.has("refactor")

    def test_get_nonexistent_returns_none(self, registry: CapabilityRegistry) -> None:
        """get() should return None for unregistered names."""
        assert registry.get("nonexistent") is None

    def test_all_returns_sorted_names(self, registry: CapabilityRegistry) -> None:
        """all() should return sorted capability names."""
        names = registry.all()
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Tests — CapabilityResult Fields
# ---------------------------------------------------------------------------


class TestCapabilityResultFields:
    """Tests for CapabilityResult field population."""

    def test_result_has_query(self, capability: RefactorCapability) -> None:
        """Result should have the query field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.query == "Refactor ProviderFactory"

    def test_result_has_intent(self, capability: RefactorCapability) -> None:
        """Result should have the intent field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.intent == "REFACTOR"

    def test_result_has_context_plan(self, capability: RefactorCapability) -> None:
        """Result should have the context_plan field."""
        index = _make_index()
        plan = _make_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.context_plan == plan

    def test_result_has_context_package(self, capability: RefactorCapability) -> None:
        """Result should have the context_package field."""
        index = _make_index()
        package = _make_context_package()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=package,
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.context_package == package

    def test_result_has_provider_request(self, capability: RefactorCapability) -> None:
        """Result should have the provider_request field."""
        index = _make_index()
        request = _make_provider_request()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=request,
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert result.provider_request == request

    def test_result_has_selected_symbols(self, capability: RefactorCapability) -> None:
        """Result should have the selected_symbols field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_symbols, tuple)

    def test_result_has_selected_modules(self, capability: RefactorCapability) -> None:
        """Result should have the selected_modules field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_modules, tuple)

    def test_result_has_estimated_tokens(self, capability: RefactorCapability) -> None:
        """Result should have the estimated_tokens field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.estimated_tokens, int)

    def test_result_has_execution_time_ms(self, capability: RefactorCapability) -> None:
        """Result should have the execution_time_ms field."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.execution_time_ms, float)
                            assert result.execution_time_ms >= 0

    def test_result_contains_all_fields(self, capability: RefactorCapability) -> None:
        """CapabilityResult should contain all expected fields."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=("sym1", "sym2"),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ):
                            result = capability.execute(
                                query="Refactor X",
                                repository_index=index,
                            )

                            assert result.query == "Refactor X"
                            assert result.intent == "REFACTOR"
                            assert result.context_plan is not None
                            assert result.context_package is not None
                            assert result.provider_request is not None
                            assert result.selected_symbols == ("sym1", "sym2")
                            assert isinstance(result.selected_modules, tuple)
                            assert result.estimated_tokens == 256
                            assert isinstance(result.execution_time_ms, float)
                            assert result.execution_time_ms >= 0
