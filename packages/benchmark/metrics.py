"""Scoring metrics for the benchmark framework.

Defines pure, deterministic scoring functions that evaluate retrieval
quality without any side effects.

Scoring Rules
-------------

| Metric | Range | Description |
|--------|-------|-------------|
| Symbol Precision | 0.0–1.0 | Fraction of expected symbols retrieved |
| Module Precision | 0.0–1.0 | Fraction of expected modules retrieved |
| Relationship Precision | 0.0–1.0 | Fraction of expected relationships retrieved |
| Budget Compliance | 0.0–1.0 | Whether estimated tokens fit within budget |

Weights (constants)
-------------------

The overall score is a weighted average:

    40% symbol precision
    20% module precision
    20% relationship precision
    20% budget compliance

These weights are constants — not configurable per-case — to ensure
deterministic, comparable scores across runs.

Constraints
-----------

- All functions are pure: same input always produces same output.
- No filesystem access.
- No LLM calls.
- No network calls.
- No mutation of external state.
"""

from __future__ import annotations

# ------------------------------------------------------------------
# Weights (constants)
# ------------------------------------------------------------------

WEIGHT_SYMBOL_PRECISION: float = 0.40
WEIGHT_MODULE_PRECISION: float = 0.20
WEIGHT_RELATIONSHIP_PRECISION: float = 0.20
WEIGHT_BUDGET_COMPLIANCE: float = 0.20


# ------------------------------------------------------------------
# Precision helpers
# ------------------------------------------------------------------


def _precision(retrieved: set[str], expected: set[str]) -> float:
    """Compute precision: fraction of retrieved items that are expected.

    Precision = |retrieved ∩ expected| / |retrieved|

    If retrieved is empty and expected is empty, returns 1.0 (no false
    positives, no false negatives).
    If retrieved is empty but expected is non-empty, returns 0.0.

    Args:
        retrieved: The set of items retrieved by the pipeline.
        expected: The set of expected items.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if not retrieved:
        return 0.0 if expected else 1.0

    intersection = retrieved & expected
    return len(intersection) / len(retrieved)


def _recall(retrieved: set[str], expected: set[str]) -> float:
    """Compute recall: fraction of expected items that were retrieved.

    Recall = |retrieved ∩ expected| / |expected|

    If expected is empty, returns 1.0 (no false negatives).
    If expected is non-empty and retrieved is empty, returns 0.0.

    Args:
        retrieved: The set of items retrieved by the pipeline.
        expected: The set of expected items.

    Returns:
        Recall score between 0.0 and 1.0.
    """
    if not expected:
        return 1.0

    intersection = retrieved & expected
    return len(intersection) / len(expected)


def _f1(precision: float, recall: float) -> float:
    """Compute F1 score from precision and recall.

    Args:
        precision: Precision score (0.0–1.0).
        recall: Recall score (0.0–1.0).

    Returns:
        F1 score, or 0.0 if both precision and recall are 0.
    """
    if precision == 0.0 and recall == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


# ------------------------------------------------------------------
# Public scoring functions
# ------------------------------------------------------------------


def symbol_precision(retrieved: set[str], expected: set[str]) -> float:
    """Score symbol retrieval quality.

    Uses F1-like scoring: harmonic mean of precision and recall.
    This penalizes both false positives (wrong symbols) and false
    negatives (missing symbols).

    Args:
        retrieved: Set of qualified symbol names retrieved by the pipeline.
        expected: Set of expected qualified symbol names.

    Returns:
        Symbol precision score between 0.0 and 1.0.
    """
    prec = _precision(retrieved, expected)
    rec = _recall(retrieved, expected)
    return _f1(prec, rec)


def module_precision(retrieved: set[str], expected: set[str]) -> float:
    """Score module retrieval quality.

    Uses F1-like scoring for module-level retrieval.

    Args:
        retrieved: Set of module paths retrieved by the pipeline.
        expected: Set of expected module paths.

    Returns:
        Module precision score between 0.0 and 1.0.
    """
    prec = _precision(retrieved, expected)
    rec = _recall(retrieved, expected)
    return _f1(prec, rec)


def relationship_precision(retrieved: set[str], expected: set[str]) -> float:
    """Score relationship retrieval quality.

    Uses F1-like scoring for relationship-level retrieval.

    Args:
        retrieved: Set of relationship identifiers retrieved.
        expected: Set of expected relationship identifiers.

    Returns:
        Relationship precision score between 0.0 and 1.0.
    """
    prec = _precision(retrieved, expected)
    rec = _recall(retrieved, expected)
    return _f1(prec, rec)


def budget_compliance(estimated: int, max_budget: int) -> float:
    """Check whether estimated tokens fit within the budget.

    Returns 1.0 if within budget, 0.0 if over budget.
    This is a hard constraint — not a gradient.

    Args:
        estimated: Estimated token count from the pipeline.
        max_budget: Maximum allowed token count.

    Returns:
        1.0 if estimated <= max_budget, 0.0 otherwise.
    """
    return 1.0 if estimated <= max_budget else 0.0


def overall_score(
    symbol_prec: float,
    module_prec: float,
    rel_prec: float,
    budget: float,
) -> float:
    """Compute the overall benchmark score.

    Weighted average of all metrics:

        40% symbol precision
        20% module precision
        20% relationship precision
        20% budget compliance

    Args:
        symbol_prec: Symbol precision score (0.0–1.0).
        module_prec: Module precision score (0.0–1.0).
        rel_prec: Relationship precision score (0.0–1.0).
        budget: Budget compliance score (0.0 or 1.0).

    Returns:
        Overall score between 0.0 and 1.0.
    """
    score = (
        WEIGHT_SYMBOL_PRECISION * symbol_prec
        + WEIGHT_MODULE_PRECISION * module_prec
        + WEIGHT_RELATIONSHIP_PRECISION * rel_prec
        + WEIGHT_BUDGET_COMPLIANCE * budget
    )
    # Clamp to [0.0, 1.0] to handle floating point drift.
    return max(0.0, min(1.0, score))
