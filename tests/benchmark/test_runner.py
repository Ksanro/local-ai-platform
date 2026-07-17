"""Tests for the benchmark runner module.

Verifies the public BenchmarkRunner API: validation, determinism checks,
report generation, and multiple benchmark execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.benchmark import BenchmarkCase, BenchmarkResult, BenchmarkRunner
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.serializers.types import ProviderType


def _make_index() -> RepositoryIndex:
    """Create a minimal RepositoryIndex for testing."""
    sym_factory = MagicMock(
        name="Factory",
        qualified_name="packages.providers.factory.ProviderFactory",
        lineno=1,
    )
    return RepositoryIndex(
        modules={
            "packages/providers/factory.py": MagicMock(
                path="packages/providers/factory.py",
            ),
        },
        _symbols=[sym_factory],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=2,
            class_count=2,
            function_count=2,
            symbol_count=2,
        ),
    )


def _make_case(
    id: str = "test",
    name: str = "Test",
    query: str = "Factory",
    max_context_tokens: int = 4096,
) -> BenchmarkCase:
    """Create a basic benchmark case."""
    return BenchmarkCase(
        id=id,
        name=name,
        description="A test case",
        query=query,
        max_context_tokens=max_context_tokens,
    )


def patch_engine(
    runner: BenchmarkRunner,
    results: list[BenchmarkResult],
):
    """Patch the engine's run method to return pre-built results.

    run_multiple calls engine.run 2N times: N for initial runs,
    then N for determinism checks.  We provide each result twice
    interleaved: [r0, r1, ..., r0, r1, ...] so that both the
    initial run and the determinism check get the same values.

    Returns a context manager for use with `with` statement.
    """
    # Interleave: [r0, r1, ..., r0, r1, ...]
    interleaved = results + list(results)
    call_count = 0

    def mock_run(*args: object, **kwargs: object) -> BenchmarkResult:
        nonlocal call_count
        if call_count < len(interleaved):
            result = interleaved[call_count]
            call_count += 1
            return result
        # Return a default result if called more times than expected.
        return BenchmarkResult(
            benchmark="default",
            selected_symbols=(),
            selected_modules=(),
            selected_relationships=(),
            estimated_tokens=0,
            duration_ms=0.0,
            passed=True,
            score=1.0,
            failures=(),
        )

    return patch.object(runner._engine, "run", side_effect=mock_run)


class TestRunnerValidation:
    """Tests for input validation."""

    def test_runner_validates_empty_id(self) -> None:
        """Runner should reject case with empty id."""
        runner = BenchmarkRunner()
        case = _make_case(id="")
        with pytest.raises(ValueError, match="id must be non-empty"):
            runner.run(case, _make_index())

    def test_runner_validates_empty_name(self) -> None:
        """Runner should reject case with empty name."""
        runner = BenchmarkRunner()
        case = _make_case(name="")
        with pytest.raises(ValueError, match="name must be non-empty"):
            runner.run(case, _make_index())

    def test_runner_validates_empty_query(self) -> None:
        """Runner should reject case with empty query."""
        runner = BenchmarkRunner()
        case = _make_case(query="")
        with pytest.raises(ValueError, match="query must be non-empty"):
            runner.run(case, _make_index())

    def test_runner_validates_negative_budget(self) -> None:
        """Runner should reject case with negative max_context_tokens."""
        runner = BenchmarkRunner()
        case = _make_case(max_context_tokens=-1)
        with pytest.raises(ValueError, match="positive"):
            runner.run(case, _make_index())

    def test_runner_validates_zero_budget(self) -> None:
        """Runner should reject case with zero max_context_tokens."""
        runner = BenchmarkRunner()
        case = _make_case(max_context_tokens=0)
        with pytest.raises(ValueError, match="positive"):
            runner.run(case, _make_index())


class TestRunnerDeterminism:
    """Tests for determinism checking."""

    def test_runner_detects_non_determinism(self) -> None:
        """Runner should detect and report non-deterministic output."""
        runner = BenchmarkRunner()
        case = _make_case()

        # First run returns sym1, determinism check returns sym2.
        # We need 4 results: [initial_run, det_check_1, det_check_2, ...]
        # For a single case: initial_run=case, det_check=case (2 calls).
        # But run_multiple calls engine.run N + N = 2N times.
        # For 1 case: 2 calls for initial + 2 calls for determinism = 4 calls.
        initial_result = BenchmarkResult(
            benchmark=case.id,
            selected_symbols=("sym1",),
            selected_modules=("mod1",),
            selected_relationships=(),
            estimated_tokens=100,
            duration_ms=10.0,
            passed=True,
            score=0.5,
            failures=(),
        )
        det_check_result = BenchmarkResult(
            benchmark=case.id,
            selected_symbols=("sym2",),  # Different!
            selected_modules=("mod1",),
            selected_relationships=(),
            estimated_tokens=100,
            duration_ms=10.0,
            passed=True,
            score=0.5,
            failures=(),
        )

        # 4 calls: initial(1) + det_check(2) + initial(3) + det_check(4)
        # Wait — run_multiple does:
        #   for i, case in enumerate(cases):
        #       result1 = self._engine.run(case, ...)  -> call 1
        #       result2 = self._engine.run(case, ...)   -> call 2
        # So for 1 case: 2 calls.
        with patch.object(runner._engine, "run") as mock_run:
            mock_run.side_effect = [initial_result, det_check_result]
            report = runner.run_multiple([case], _make_index())
            # Both should be marked as failed due to non-determinism.
            assert report.executed == 2
            assert report.passed == 0
            assert report.failed == 2
            for r in report.results:
                assert r.passed is False
                assert "Non-deterministic" in r.failures[0]

    def test_runner_passes_determinism_check(self) -> None:
        """Runner should pass determinism check when outputs are identical."""
        runner = BenchmarkRunner()
        case = _make_case()

        result = BenchmarkResult(
            benchmark=case.id,
            selected_symbols=("sym1",),
            selected_modules=("mod1",),
            selected_relationships=(),
            estimated_tokens=100,
            duration_ms=10.0,
            passed=True,
            score=0.5,
            failures=(),
        )

        # Same result for both runs.
        with patch.object(runner._engine, "run") as mock_run:
            mock_run.side_effect = [result, result]
            report = runner.run_multiple([case], _make_index())
            assert report.executed == 1
            assert report.passed == 1
            assert report.failed == 0
            assert report.results[0].passed is True


class TestRunnerReportGeneration:
    """Tests for report generation."""

    def test_runner_generates_report(self) -> None:
        """Runner should generate a report for multiple cases."""
        runner = BenchmarkRunner()
        cases = [_make_case(id="a"), _make_case(id="b")]

        result_a = BenchmarkResult(
            benchmark="a",
            selected_symbols=("sym1",),
            selected_modules=("mod1",),
            selected_relationships=(),
            estimated_tokens=100,
            duration_ms=10.0,
            passed=True,
            score=0.8,
            failures=(),
        )
        result_b = BenchmarkResult(
            benchmark="b",
            selected_symbols=("sym2",),
            selected_modules=("mod2",),
            selected_relationships=(),
            estimated_tokens=200,
            duration_ms=20.0,
            passed=False,
            score=0.3,
            failures=("Test failure",),
        )

        with patch_engine(runner, [result_a, result_b]):
            report = runner.run_multiple(cases, _make_index())

            assert report.executed == 2
            assert report.passed == 1
            assert report.failed == 1
            assert report.average_score == pytest.approx(0.55)
            assert report.average_duration_ms == pytest.approx(15.0)
            # Results should be sorted by benchmark id.
            assert report.results[0].benchmark == "a"
            assert report.results[1].benchmark == "b"

    def test_runner_empty_report(self) -> None:
        """Runner should raise ValueError for empty case list."""
        runner = BenchmarkRunner()
        with pytest.raises(ValueError, match="empty"):
            runner.run_multiple([], _make_index())

    def test_runner_sorted_results(self) -> None:
        """Runner should sort results by benchmark id."""
        runner = BenchmarkRunner()
        cases = [
            _make_case(id="z"),
            _make_case(id="a"),
            _make_case(id="m"),
        ]

        results = [
            BenchmarkResult(
                benchmark=c.id,
                selected_symbols=(),
                selected_modules=(),
                selected_relationships=(),
                estimated_tokens=0,
                duration_ms=0.0,
                passed=True,
                score=1.0,
                failures=(),
            )
            for c in cases
        ]

        with patch_engine(runner, results):
            report = runner.run_multiple(cases, _make_index())
            ids = [r.benchmark for r in report.results]
            assert ids == sorted(ids)


class TestRunnerSingleCase:
    """Tests for single case execution."""

    def test_runner_returns_result(self) -> None:
        """Runner should return a BenchmarkResult for single case."""
        runner = BenchmarkRunner()
        case = _make_case()

        with patch_engine(runner, [
            BenchmarkResult(
                benchmark=case.id,
                selected_symbols=("sym1",),
                selected_modules=("mod1",),
                selected_relationships=(),
                estimated_tokens=100,
                duration_ms=10.0,
                passed=True,
                score=0.8,
                failures=(),
            ),
        ]):
            result = runner.run(case, _make_index())
            assert isinstance(result, BenchmarkResult)
            assert result.benchmark == case.id
            assert result.passed is True
            assert result.score == pytest.approx(0.8)


class TestRunnerMultipleBenchmarks:
    """Tests for multiple benchmark execution."""

    def test_runner_executes_multiple(self) -> None:
        """Runner should execute all cases."""
        runner = BenchmarkRunner()
        cases = [_make_case(id="a"), _make_case(id="b"), _make_case(id="c")]

        results = [
            BenchmarkResult(
                benchmark=c.id,
                selected_symbols=(),
                selected_modules=(),
                selected_relationships=(),
                estimated_tokens=0,
                duration_ms=0.0,
                passed=True,
                score=1.0,
                failures=(),
            )
            for c in cases
        ]

        with patch_engine(runner, results):
            report = runner.run_multiple(cases, _make_index())
            assert report.executed == 3
            assert report.passed == 3
            assert report.failed == 0

    def test_runner_all_failures(self) -> None:
        """Runner should correctly report all failures."""
        runner = BenchmarkRunner()
        cases = [_make_case(id="fail1"), _make_case(id="fail2")]

        results = [
            BenchmarkResult(
                benchmark=c.id,
                selected_symbols=(),
                selected_modules=(),
                selected_relationships=(),
                estimated_tokens=0,
                duration_ms=0.0,
                passed=False,
                score=0.0,
                failures=("Failure reason",),
            )
            for c in cases
        ]

        with patch_engine(runner, results):
            report = runner.run_multiple(cases, _make_index())
            assert report.executed == 2
            assert report.passed == 0
            assert report.failed == 2
            assert report.average_score == pytest.approx(0.0)


class TestRunnerProviderType:
    """Tests for provider type configuration."""

    def test_runner_default_provider(self) -> None:
        """Runner should use openai as default provider."""
        runner = BenchmarkRunner()
        assert runner._engine._serializer_provider_type == ProviderType.openai

    def test_runner_custom_provider(self) -> None:
        """Runner should accept custom provider type."""
        runner = BenchmarkRunner(serializer_provider_type=ProviderType.anthropic)
        assert runner._engine._serializer_provider_type == ProviderType.anthropic
