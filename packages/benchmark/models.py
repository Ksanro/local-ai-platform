"""Immutable data models for the benchmark framework.

Defines the data structures that flow through the benchmark pipeline:
BenchmarkCase (input), BenchmarkResult (per-case output), and
BenchmarkReport (aggregate output).

All models are immutable (frozen=True, slots=True) and use deterministic
field types (tuples, not lists) for hashability and reproducibility.

Architecture
------------

BenchmarkCase          -- input specification
    ↓
BenchmarkResult        -- per-case output
    ↓
BenchmarkReport        -- aggregate across multiple cases

Constraints
-----------

- All fields are immutable.
- Collections use tuple, not list.
- No mutable default arguments.
- No side effects in property access.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """Specification for a single benchmark case.

    Attributes:
        id: Unique identifier for the benchmark case.
        name: Human-readable name.
        description: Detailed description of what this benchmark tests.
        query: The query text that drives the pipeline.
        expected_symbols: Expected qualified symbol names in the result.
        expected_modules: Expected module paths in the result.
        expected_relationships: Expected relationship pairs (qualified name pairs).
        max_context_tokens: Maximum token budget for the context.
        planner_intent: The expected planner intent (EXPLAIN, DEBUG, IMPLEMENT, etc.).
        tags: Tags for categorizing the benchmark (e.g. "explain", "debug").
    """

    id: str
    name: str
    description: str
    query: str
    expected_symbols: tuple[str, ...] = ()
    expected_modules: tuple[str, ...] = ()
    expected_relationships: tuple[str, ...] = ()
    max_context_tokens: int = 4096
    planner_intent: str = "DEFAULT"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Result for a single benchmark case.

    Attributes:
        benchmark: The benchmark case id.
        selected_symbols: Symbols selected by the pipeline (qualified names).
        selected_modules: Modules selected by the pipeline.
        selected_relationships: Relationships selected by the pipeline.
        estimated_tokens: Estimated token count from the pipeline.
        duration_ms: Total execution time in milliseconds.
        passed: Whether the benchmark passed all checks.
        score: Overall score (0.0 to 1.0).
        failures: List of failure descriptions.
    """

    benchmark: str
    selected_symbols: tuple[str, ...]
    selected_modules: tuple[str, ...]
    selected_relationships: tuple[str, ...]
    estimated_tokens: int
    duration_ms: float
    passed: bool
    score: float
    failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate report across multiple benchmark cases.

    Attributes:
        executed: Number of benchmarks executed.
        passed: Number of benchmarks that passed.
        failed: Number of benchmarks that failed.
        average_score: Average score across all benchmarks.
        average_duration_ms: Average duration across all benchmarks.
        results: Sorted tuple of benchmark results.
    """

    executed: int
    passed: int
    failed: int
    average_score: float
    average_duration_ms: float
    results: tuple[BenchmarkResult, ...] = ()

    def __post_init__(self) -> None:
        """Validate the report invariants."""
        if self.executed < 0:
            raise ValueError("executed must be non-negative")
        if self.passed + self.failed != self.executed:
            raise ValueError("passed + failed must equal executed")
        if not (0.0 <= self.average_score <= 1.0):
            raise ValueError("average_score must be between 0.0 and 1.0")
