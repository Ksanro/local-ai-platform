"""Benchmark framework for the retrieval pipeline.

Provides deterministic benchmarking of the complete retrieval pipeline
without invoking any LLM or network calls.

Architecture
------------

BenchmarkRunner
    ↓
BenchmarkEngine (pipeline execution)
    ↓
Planning → Repository → Ranking → Context → Serializer
    ↓
BenchmarkResult / BenchmarkReport

Usage
-----

.. code-block:: python

    from packages.benchmark import BenchmarkRunner, BenchmarkCase

    runner = BenchmarkRunner()
    case = BenchmarkCase(
        id="explain_provider_factory",
        name="Explain ProviderFactory",
        query="Explain ProviderFactory",
        max_context_tokens=4096,
        planner_intent="EXPLAIN",
    )

    result = runner.run(case, repository_index)
    report = runner.run_multiple(cases, repository_index)

Note: This package is named 'benchmark' for the initial release.
The scope is expected to evolve into a broader 'evaluation' package
that may evaluate retrieval, planners, DSPARK, memory, providers,
routing, and latency. The public API (BenchmarkRunner/BenchmarkCase/
BenchmarkReport) is designed to support this evolution without
breaking changes.

Public API
----------

- BenchmarkRunner — public API for running benchmarks
- BenchmarkCase — input specification
- BenchmarkResult — per-case output
- BenchmarkReport — aggregate output
- BenchmarkEngine — pipeline execution engine
- metrics — scoring functions
"""

from __future__ import annotations

from packages.benchmark.engine import BenchmarkEngine
from packages.benchmark.models import (
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkResult,
)
from packages.benchmark.runner import BenchmarkRunner

__all__ = [
    "BenchmarkCase",
    "BenchmarkEngine",
    "BenchmarkReport",
    "BenchmarkResult",
    "BenchmarkRunner",
]
