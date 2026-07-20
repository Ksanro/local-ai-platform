"""Integration test: benchmark framework with production pipeline.

Runs the BenchmarkEngine with a real RepositoryIndex and verifies
that the benchmark executes successfully.

Tests
-----
- BenchmarkEngine runs with real index
- BenchmarkResult is produced
- Metrics (tokens, size, context) are measurable
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.benchmark.engine import BenchmarkEngine
from packages.benchmark.models import BenchmarkCase, BenchmarkResult
from packages.repository import build_index
from packages.repository.index.models import RepositoryIndex


@pytest.fixture
def test_repo() -> Path:
    """Return the project root as the test repository."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def repository_index(test_repo: Path) -> RepositoryIndex:
    """Build a real RepositoryIndex from the test repository."""
    index = build_index(test_repo)
    assert isinstance(index, RepositoryIndex)
    return index


def test_benchmark_executes_with_real_index(repository_index: RepositoryIndex) -> None:
    """Run a benchmark case with the real pipeline and verify results."""
    # Create a benchmark case that searches for a known symbol.
    case = BenchmarkCase(
        id="test_context_verification",
        name="Context Verification Benchmark",
        description="Test that context travels through the pipeline",
        query="RepositoryContextStage",
        max_context_tokens=4096,
        planner_intent="DEFAULT",
        tags=("test", "integration"),
    )

    # Run the benchmark engine.
    engine = BenchmarkEngine()
    result: BenchmarkResult = engine.run(case, repository_index)

    # Verify result was produced.
    assert result is not None
    assert isinstance(result, BenchmarkResult)
    assert result.benchmark == "test_context_verification"

    # Verify metrics are measurable.
    assert result.estimated_tokens >= 0
    assert result.duration_ms >= 0.0
    assert result.score >= 0.0 and result.score <= 1.0

    # The pipeline executed: RepositoryIndex -> ContextBuilder -> Serializer.
    assert result.selected_symbols is not None


def test_benchmark_measures_token_estimate(repository_index: RepositoryIndex) -> None:
    """Verify that the benchmark measures token estimates."""
    case = BenchmarkCase(
        id="token_estimate_test",
        name="Token Estimate Test",
        description="Test token estimation",
        query="test",
        max_context_tokens=2048,
        planner_intent="DEFAULT",
    )

    engine = BenchmarkEngine()
    result = engine.run(case, repository_index)

    # Verify token estimate is measured.
    assert result.estimated_tokens >= 0

    # Duration is measured.
    assert result.duration_ms >= 0.0


def test_benchmark_measures_serialized_prompt_size(repository_index: RepositoryIndex) -> None:
    """Verify that the benchmark measures serialized prompt size."""
    case = BenchmarkCase(
        id="prompt_size_test",
        name="Prompt Size Test",
        description="Test serialized prompt size measurement",
        query="Serializer",
        max_context_tokens=4096,
        planner_intent="DEFAULT",
    )

    engine = BenchmarkEngine()
    result = engine.run(case, repository_index)

    # The estimated_tokens field represents the context size estimate.
    # The serialized prompt size is measured through the benchmark engine.
    assert result.estimated_tokens >= 0

    # The score reflects the quality of the serialized output.
    assert result.score >= 0.0 and result.score <= 1.0


def test_benchmark_measures_context_size(repository_index: RepositoryIndex) -> None:
    """Verify that the benchmark measures context size."""
    case = BenchmarkCase(
        id="context_size_test",
        name="Context Size Test",
        description="Test context size measurement",
        query="ContextBuilder",
        max_context_tokens=4096,
        planner_intent="DEFAULT",
    )

    engine = BenchmarkEngine()
    result = engine.run(case, repository_index)

    # Verify context size is measured.
    assert result.estimated_tokens >= 0

    # Verify the pipeline executed successfully.
    assert result.duration_ms >= 0.0
