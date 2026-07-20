"""Deterministic score calculation functions.

Each category receives a score between 0.0 and 1.0.
The overall score is a weighted average of all category scores.

Weights are constants. Every formula is documented.
No hidden heuristics.

Architecture
------------

Metrics  -->  Category Score  -->  Weighted Overall Score

Public API
----------

.. code-block:: python

    from packages.evaluation.scoring import (
        calculate_category_score,
        calculate_overall_score,
        CATEGORY_WEIGHTS,
        CATEGORY_DEFINITIONS,
    )

"""

from __future__ import annotations

from packages.evaluation.models import EvaluationMetric, EvaluationScore

__all__ = [
    "CATEGORY_DEFINITIONS",
    "CATEGORY_WEIGHTS",
    "calculate_category_score",
    "calculate_overall_score",
]

# ---------------------------------------------------------------------------
# Category Weights (constants)
# ---------------------------------------------------------------------------

# Category weights define the relative importance of each evaluation
# category in the overall score. These are constants — no hidden
# heuristics, no dynamic adjustment.
#
# Weight distribution:
#   - Context Quality:     0.25 (25%)
#   - Execution Quality:   0.20 (20%)
#   - Engineering Quality: 0.30 (30%)
#   - Performance:         0.10 (10%)
#   - Determinism:         0.15 (15%)
#   - Total:              1.00 (100%)

CATEGORY_WEIGHTS: dict[str, float] = {
    "Context Quality": 0.25,
    "Execution Quality": 0.20,
    "Engineering Quality": 0.30,
    "Performance": 0.10,
    "Determinism": 0.15,
}

# Category definitions map category names to their metric names
# and the scoring thresholds for each metric.

CATEGORY_DEFINITIONS: dict[str, list[str]] = {
    "Context Quality": [
        "context_compression_ratio",
        "context_utilization",
        "selected_symbols_count",
        "selected_modules_count",
    ],
    "Execution Quality": [
        "execution_duration_ms",
        "total_tokens",
        "throughput",
    ],
    "Engineering Quality": [
        "diagnostics_collected",
        "architecture_findings_count",
        "workflow_completeness",
    ],
    "Performance": [
        "throughput",
        "execution_duration_ms",
    ],
    "Determinism": [
        "execution_consistency",
        "identifier_stability",
    ],
}


# ---------------------------------------------------------------------------
# Category Score Calculation
# ---------------------------------------------------------------------------


def calculate_category_score(
    metrics: tuple[EvaluationMetric, ...],
    category_name: str,
    category_metric_names: list[str] | None = None,
) -> float:
    """Calculate a category score from relevant metrics.

    The category score is the weighted average of all relevant metric
    values that belong to this category. Each metric's value is treated
    as its contribution (metrics are pre-normalized to 0.0-1.0).

    Args:
        metrics: All computed evaluation metrics.
        category_name: Name of the category to score.
        category_metric_names: Optional list of metric names for this
            category. If None, uses CATEGORY_DEFINITIONS.

    Returns:
        Score in range [0.0, 1.0].
        Returns 0.0 if no relevant metrics found.
    """
    if category_metric_names is None:
        category_metric_names = CATEGORY_DEFINITIONS.get(category_name, [])

    relevant_metrics = [
        m for m in metrics if m.name in category_metric_names
    ]

    if not relevant_metrics:
        return 0.0

    # Weighted average of metric values
    total_weight = sum(m.weight for m in relevant_metrics)
    if total_weight <= 0:
        return 0.0

    weighted_sum = sum(m.value * m.weight for m in relevant_metrics)
    score = weighted_sum / total_weight

    # Clamp to [0.0, 1.0]
    return min(max(score, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Overall Score Calculation
# ---------------------------------------------------------------------------


def calculate_overall_score(
    scores: tuple[EvaluationScore, ...],
) -> float:
    """Calculate the overall weighted score.

    The overall score is a weighted average of all category scores.
    Each category's weight is defined in CATEGORY_WEIGHTS.

    Formula:
        overall_score = sum(score_i * weight_i) / sum(weight_i)

    for all categories where weight_i > 0.

    Args:
        scores: Tuple of all computed category scores.

    Returns:
        Overall score in range [0.0, 1.0].
        Returns 0.0 if no scores provided.
    """
    if not scores:
        return 0.0

    total_weighted = 0.0
    total_weight = 0.0

    for score_entry in scores:
        weight = CATEGORY_WEIGHTS.get(score_entry.category, 0.0)
        if weight > 0:
            total_weighted += score_entry.score * weight
            total_weight += weight

    if total_weight <= 0:
        return 0.0

    overall = total_weighted / total_weight

    # Clamp to [0.0, 1.0]
    return min(max(overall, 0.0), 1.0)