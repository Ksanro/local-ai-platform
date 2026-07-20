"""Immutable evaluation model definitions.

Defines the output structures of the evaluation framework. These are the
stable contracts between the evaluator and its consumers.

Architecture
------------

EvaluationMetric  -->  EvaluationScore  -->  EvaluationReport

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider response fields.
- No repository analysis fields.

Public API
----------

.. code-block:: python

    from packages.evaluation.models import (
        EvaluationMetric,
        EvaluationScore,
        EvaluationReport,
    )

    report = EvaluationReport(
        workflow_name="bug-investigation",
        task_name="investigate-bug",
        provider="vllm",
        model="gpt-4",
        started_at="2024-01-01T00:00:00",
        completed_at="2024-01-01T00:00:01",
        metrics=(),
        scores=(),
        overall_score=0.85,
        summary="Good quality execution.",
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "EvaluationMetric",
    "EvaluationReport",
    "EvaluationScore",
]


# ---------------------------------------------------------------------------
# EvaluationMetric
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    """A single deterministic evaluation metric.

    Metrics are computed from structured platform outputs.
    No AI scoring. No LLM judging. No semantic evaluation.

    Attributes:
        name: Unique metric name (e.g. "context_compression_ratio").
        value: Computed metric value.
        weight: Weight in the scoring formula (0.0 to 1.0).
        passed: Whether the metric passed its threshold.
        metadata: Additional context about how the metric was computed.
    """

    name: str
    value: float
    weight: float
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EvaluationScore
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationScore:
    """A scored category with weighted contribution.

    Each category receives a score between 0.0 and 1.0.
    The overall score is a weighted average of all category scores.

    Attributes:
        category: Category name (e.g. "Context Quality").
        score: Normalized score in range [0.0, 1.0].
        maximum: Maximum possible score for this category.
        weight: Weight in the overall score calculation.
    """

    category: str
    score: float
    maximum: float
    weight: float


# ---------------------------------------------------------------------------
# EvaluationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Complete evaluation report for a workflow execution.

    This is the canonical quality artifact for every engineering operation.
    Future Engineering Knowledge Graph versions will persist these reports.

    Attributes:
        workflow_name: The workflow name that was evaluated.
        task_name: The task name that was evaluated.
        provider: Provider name used (e.g. "vllm").
        model: Model name used (e.g. "gpt-4").
        started_at: ISO format timestamp when evaluation started.
        completed_at: ISO format timestamp when evaluation completed.
        metrics: Tuple of all computed evaluation metrics.
        scores: Tuple of all computed category scores.
        overall_score: Weighted overall score (0.0 to 1.0).
        summary: Human-readable evaluation summary.
        metadata: Additional metadata about the evaluation.
    """

    workflow_name: str
    task_name: str
    provider: str
    model: str
    started_at: str
    completed_at: str
    metrics: tuple[EvaluationMetric, ...] = ()
    scores: tuple[EvaluationScore, ...] = ()
    overall_score: float = 0.0
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)