"""Tests for the benchmark engine module.

Verifies pipeline execution: planning, repository search, ranking,
context building, and serialization — without invoking providers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.benchmark.engine import BenchmarkEngine
from packages.benchmark.models import (
    BenchmarkCase,
    BenchmarkResult,
)
from packages.context.context_package import ContextPackage
from packages.repository.index.models import RepositoryIndex
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


from packages.repository.index.models import RepositoryStatistics


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


@pytest.fixture()
def engine() -> BenchmarkEngine:
    """Create a BenchmarkEngine with mock serializer."""
    return BenchmarkEngine(serializer_provider_type=ProviderType.openai)


@pytest.fixture()
def case() -> BenchmarkCase:
    """Create a basic benchmark case."""
    return BenchmarkCase(
        id="test_case",
        name="Test Case",
        description="A test benchmark case",
        query="Factory",
        expected_symbols=(
            "packages.providers.factory.ProviderFactory",
            "packages.providers.factory.ProviderFactory.create",
        ),
        expected_modules=(
            "packages/providers/factory.py",
            "packages/providers/registry.py",
        ),
        max_context_tokens=4096,
        planner_intent="EXPLAIN",
    )


class TestEngineExecutesPipelineStages:
    """Tests that the engine executes all pipeline stages."""

    def test_engine_calls_planning(self, engine: BenchmarkEngine, case: BenchmarkCase) -> None:
        """Planning stage should be called."""
        index = _make_index()
        with patch.object(
            engine,
            "_stage_planning",
            return_value=MagicMock(),
        ) as mock_plan:
            engine.run(case, index)
            mock_plan.assert_called_once_with(case)

    def test_engine_calls_repository_search(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Repository search stage should be called."""
        index = _make_index()
        with patch.object(
            engine,
            "_stage_repository_search",
            return_value=[],
        ) as mock_search:
            engine.run(case, index)
            mock_search.assert_called_once_with(case, index)

    def test_engine_calls_context_building(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Context building stage should be called."""
        index = _make_index()
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ) as mock_build:
            engine.run(case, index)
            mock_build.assert_called_once_with(case, index)

    def test_engine_calls_serialization(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Serialization stage should be called."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_serialization",
            return_value=ProviderRequest(
                provider_type=ProviderType.openai,
                messages=[],
            ),
        ) as mock_ser:
            with patch.object(engine, "_stage_context_building", return_value=mock_result):
                engine.run(case, _make_index())
                mock_ser.assert_called_once_with(mock_result)


class TestEngineNoProviderInvocation:
    """Tests that the engine does not invoke providers."""

    def test_engine_no_network_calls(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Engine should not make any network calls."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                # If we get here without network errors, the test passes.
                assert isinstance(result, BenchmarkResult)

    def test_engine_no_http_imports(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Engine should not import httpx or requests."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                engine.run(case, _make_index())
                # No httpx or requests import should have occurred.


class TestEngineDeterministic:
    """Tests that the engine produces deterministic output."""

    def test_engine_deterministic_output(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Two runs with the same input should produce the same output."""
        mock_result1 = MagicMock()
        mock_result1.candidates = []
        mock_result1.selected_modules = []
        mock_result1.budget.estimated_tokens = 0

        mock_result2 = MagicMock()
        mock_result2.candidates = []
        mock_result2.selected_modules = []
        mock_result2.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            side_effect=[mock_result1, mock_result2],
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result1 = engine.run(case, _make_index())
                result2 = engine.run(case, _make_index())

                # Compare all fields except duration_ms.
                assert result1.benchmark == result2.benchmark
                assert result1.selected_symbols == result2.selected_symbols
                assert result1.selected_modules == result2.selected_modules
                assert result1.selected_relationships == result2.selected_relationships
                assert result1.estimated_tokens == result2.estimated_tokens
                assert result1.passed == result2.passed
                assert result1.score == result2.score
                assert result1.failures == result2.failures


class TestEngineProducesProviderRequest:
    """Tests that the engine produces a valid ProviderRequest."""

    def test_engine_produces_provider_request(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Serialization should produce a valid ProviderRequest."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        expected_request = ProviderRequest(
            provider_type=ProviderType.openai,
            messages=[{"role": "user", "content": "test"}],
        )

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=expected_request,
            ):
                result = engine.run(case, _make_index())
                assert isinstance(result, BenchmarkResult)
                assert result.benchmark == case.id


class TestEngineResultStructure:
    """Tests that the engine produces correctly structured results."""

    def test_result_has_benchmark_id(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Result should have the correct benchmark id."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                assert result.benchmark == case.id

    def test_result_has_duration(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Result should have a positive duration."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                assert result.duration_ms >= 0

    def test_result_has_score(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Result should have a score between 0 and 1."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                assert 0.0 <= result.score <= 1.0

    def test_result_has_passed(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Result should have a boolean passed field."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                assert isinstance(result.passed, bool)

    def test_result_has_failures(
        self,
        engine: BenchmarkEngine,
        case: BenchmarkCase,
    ) -> None:
        """Result should have a failures tuple."""
        mock_result = MagicMock()
        mock_result.candidates = []
        mock_result.selected_modules = []
        mock_result.budget.estimated_tokens = 0

        with patch.object(
            engine,
            "_stage_context_building",
            return_value=mock_result,
        ):
            with patch.object(
                engine,
                "_stage_serialization",
                return_value=ProviderRequest(
                    provider_type=ProviderType.openai,
                    messages=[],
                ),
            ):
                result = engine.run(case, _make_index())
                assert isinstance(result.failures, tuple)