"""Benchmark runner: public API for running benchmarks.

Provides the BenchmarkRunner class that orchestrates benchmark execution,
determinism checks, and report generation.

Public API
----------

.. code-block:: python

    runner = BenchmarkRunner()

    # Single case
    result = runner.run(case, repository_index)

    # Multiple cases
    report = runner.run_multiple(cases, repository_index)

Architecture
------------

BenchmarkRunner
    ↓
BenchmarkEngine (pipeline execution)
    ↓
BenchmarkResult / BenchmarkReport

Responsibilities
----------------

- Validate inputs before execution.
- Delegate pipeline execution to BenchmarkEngine.
- Run determinism checks (execute twice, compare outputs).
- Aggregate results into BenchmarkReport.
- Sort results deterministically by benchmark id.

Constraints
-----------

- No provider invocation.
- No network calls.
- No LLM calls.
- Pure evaluation only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from packages.benchmark.engine import BenchmarkEngine
from packages.benchmark.models import (
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkResult,
)
from packages.serializers.types import ProviderType

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Public API for running benchmarks.

    Orchestrates benchmark execution with validation, determinism
    checking, and report generation.

    Usage:

    .. code-block:: python

        runner = BenchmarkRunner()

        # Single case
        result = runner.run(case, repository_index)

        # Multiple cases
        report = runner.run_multiple(cases, repository_index)

    Attributes:
        _engine: The benchmark engine used for pipeline execution.
    """

    def __init__(
        self,
        serializer_provider_type: ProviderType = ProviderType.openai,
    ) -> None:
        """Initialize the benchmark runner.

        Args:
            serializer_provider_type: The provider type to use for
                serialization. Defaults to openai.
        """
        self._engine = BenchmarkEngine(
            serializer_provider_type=serializer_provider_type,
        )

    def run(
        self,
        case: BenchmarkCase,
        repository_index: RepositoryIndex,
    ) -> BenchmarkResult:
        """Run a single benchmark case.

        Validates the case, executes the pipeline, and returns the
        benchmark result.

        Args:
            case: The benchmark case specification.
            repository_index: The repository index to benchmark against.

        Returns:
            A BenchmarkResult with scores, selected items, and failures.

        Raises:
            ValueError: If the case is invalid (empty query, missing id).
        """
        self._validate_case(case)

        result = self._engine.run(case, repository_index)

        logger.info(
            "benchmark_run id=%s passed=%s score=%.3f",
            case.id,
            result.passed,
            result.score,
        )

        return result

    def run_multiple(
        self,
        cases: list[BenchmarkCase],
        repository_index: RepositoryIndex,
    ) -> BenchmarkReport:
        """Run multiple benchmark cases and aggregate results.

        Executes each case, runs determinism checks, and produces a
        BenchmarkReport with aggregate statistics.

        Args:
            cases: List of benchmark case specifications.
            repository_index: The repository index to benchmark against.

        Returns:
            A BenchmarkReport with aggregate statistics.

        Raises:
            ValueError: If any case is invalid.
        """
        if not cases:
            raise ValueError("Cannot run benchmark with empty case list")

        # Validate all cases first.
        for case in cases:
            self._validate_case(case)

        # Execute each case.
        results: list[BenchmarkResult] = []
        for case in cases:
            result = self._engine.run(case, repository_index)
            results.append(result)

        # Determinism check: run each case again and compare.
        for i, case in enumerate(cases):
            result1 = results[i]
            result2 = self._engine.run(case, repository_index)

            if not self._deterministic_equal(result1, result2):
                logger.error(
                    "determinism_failure case=%s",
                    case.id,
                )
                # Mark both as failed due to non-determinism.
                results[i] = BenchmarkResult(
                    benchmark=case.id,
                    selected_symbols=result1.selected_symbols,
                    selected_modules=result1.selected_modules,
                    selected_relationships=result1.selected_relationships,
                    estimated_tokens=result1.estimated_tokens,
                    duration_ms=result1.duration_ms,
                    passed=False,
                    score=0.0,
                    failures=("Non-deterministic output detected",),
                )
                results.append(BenchmarkResult(
                    benchmark=case.id,
                    selected_symbols=result2.selected_symbols,
                    selected_modules=result2.selected_modules,
                    selected_relationships=result2.selected_relationships,
                    estimated_tokens=result2.estimated_tokens,
                    duration_ms=result2.duration_ms,
                    passed=False,
                    score=0.0,
                    failures=("Non-deterministic output detected",),
                ))

        # Sort results deterministically by benchmark id.
        results.sort(key=lambda r: r.benchmark)

        # Build report.
        executed = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = executed - passed
        avg_score = sum(r.score for r in results) / executed if executed else 0.0
        avg_duration = (
            sum(r.duration_ms for r in results) / executed if executed else 0.0
        )

        report = BenchmarkReport(
            executed=executed,
            passed=passed,
            failed=failed,
            average_score=round(avg_score, 6),
            average_duration_ms=round(avg_duration, 2),
            results=tuple(results),
        )

        logger.info(
            "benchmark_report executed=%d passed=%d failed=%d avg_score=%.3f",
            executed,
            passed,
            failed,
            avg_score,
        )

        return report

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_case(case: BenchmarkCase) -> None:
        """Validate a benchmark case.

        Args:
            case: The benchmark case to validate.

        Raises:
            ValueError: If the case is invalid.
        """
        if not case.id:
            raise ValueError("Benchmark case id must be non-empty")
        if not case.name:
            raise ValueError("Benchmark case name must be non-empty")
        if not case.query:
            raise ValueError("Benchmark case query must be non-empty")
        if case.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    @staticmethod
    def _deterministic_equal(
        result1: BenchmarkResult,
        result2: BenchmarkResult,
    ) -> bool:
        """Check if two benchmark results are deterministically equal.

        Compares all fields except duration_ms (timing is expected to
        vary between runs).

        Args:
            result1: First result.
            result2: Second result.

        Returns:
            True if results are equal (ignoring timing).
        """
        return (
            result1.benchmark == result2.benchmark
            and result1.selected_symbols == result2.selected_symbols
            and result1.selected_modules == result2.selected_modules
            and result1.selected_relationships == result2.selected_relationships
            and result1.estimated_tokens == result2.estimated_tokens
            and result1.passed == result2.passed
            and result1.score == result2.score
            and result1.failures == result2.failures
        )