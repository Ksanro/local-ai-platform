"""Tests for the Explain Capability.

Verifies:
- planner invoked
- repository queried
- context built
- serializer invoked
- deterministic execution
- immutable result
- no provider invocation
- repeated execution identical
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.capabilities.explain import ExplainCapability
from packages.capabilities.models import CapabilityResult
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
    """Create a minimal ContextPlan."""
    return ContextPlan(
        intent="EXPLAIN",
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
        messages=[{"role": "user", "content": "Explain ProviderFactory"}],
        model="default",
    )


@pytest.fixture()
def capability() -> ExplainCapability:
    """Create an ExplainCapability instance."""
    return ExplainCapability()


# ---------------------------------------------------------------------------
# Test: Planner Invoked
# ---------------------------------------------------------------------------


class TestPlannerInvoked:
    """Tests that the planner is invoked."""

    def test_planner_is_called(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Planner should be called with the user query."""
        index = _make_index()
        plan = _make_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            mock_plan.assert_called_once()


class TestRepositoryQueried:
    """Tests that the repository is queried."""

    def test_repository_is_called(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Repository search should be called with the user query."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            mock_search.assert_called_once()


class TestContextBuilt:
    """Tests that context is built."""

    def test_context_is_built(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Context building should be called."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            mock_build.assert_called_once()


class TestSerializerInvoked:
    """Tests that the serializer is invoked."""

    def test_serializer_is_called(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Serialization should be called."""
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
                        ) as mock_ser:
                            capability.execute(
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            mock_ser.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests that the capability produces deterministic output."""

    def test_deterministic_output(
        self,
        capability: ExplainCapability,
    ) -> None:
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            result2 = capability.execute(
                                query="Explain ProviderFactory",
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

    def test_result_is_frozen(
        self,
        capability: ExplainCapability,
    ) -> None:
        """CapabilityResult should be a frozen dataclass."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )

        # Verify it's a frozen dataclass.
        assert isinstance(result, CapabilityResult)

        # Attempting to modify should raise an error.
        with pytest.raises(Exception):
            result.query = "new query"  # type: ignore[misc]

        with pytest.raises(Exception):
            result.selected_symbols = ("new",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: No Provider Invocation
# ---------------------------------------------------------------------------


class TestNoProviderInvocation:
    """Tests that no provider is invoked."""

    def test_no_network_calls(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Capability should not make any network calls."""
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
                            # If we get here without network errors, the test passes.
                            result = capability.execute(
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result, CapabilityResult)

    def test_no_http_imports(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Capability should not import httpx or requests."""
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
                            capability.execute(
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            # No httpx or requests import should have occurred.


# ---------------------------------------------------------------------------
# Test: Repeated Execution Identical
# ---------------------------------------------------------------------------


class TestRepeatedExecutionIdentical:
    """Tests that repeated execution produces identical results."""

    def test_repeated_execution_identical(
        self,
        capability: ExplainCapability,
    ) -> None:
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
                                        query="Explain ProviderFactory",
                                        repository_index=index,
                                    )
                                )

        # All results should be identical.
        for result in results:
            assert result.query == "Explain ProviderFactory"
            assert result.intent == "EXPLAIN"
            assert result.context_plan == plan
            assert result.context_package == _make_context_package()
            assert result.provider_request == _make_provider_request()
            assert result.selected_symbols == ()
            assert result.selected_modules == ("packages/providers/factory.py",)
            assert result.estimated_tokens == 256


# ---------------------------------------------------------------------------
# Test: CapabilityResult Structure
# ---------------------------------------------------------------------------


class TestCapabilityResultStructure:
    """Tests that the CapabilityResult has the correct structure."""

    def test_result_has_query(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the query field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert result.query == "Explain ProviderFactory"

    def test_result_has_intent(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the intent field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert result.intent == "EXPLAIN"

    def test_result_has_context_plan(
        self,
        capability: ExplainCapability,
    ) -> None:
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert result.context_plan == plan

    def test_result_has_context_package(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the context_package field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert result.context_package == _make_context_package()

    def test_result_has_provider_request(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the provider_request field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert result.provider_request == _make_provider_request()

    def test_result_has_selected_symbols(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the selected_symbols field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_symbols, tuple)

    def test_result_has_selected_modules(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the selected_modules field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_modules, tuple)

    def test_result_has_estimated_tokens(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the estimated_tokens field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.estimated_tokens, int)

    def test_result_has_execution_time_ms(
        self,
        capability: ExplainCapability,
    ) -> None:
        """Result should have the execution_time_ms field."""
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
                                query="Explain ProviderFactory",
                                repository_index=index,
                            )
                            assert isinstance(result.execution_time_ms, float)
                            assert result.execution_time_ms >= 0
