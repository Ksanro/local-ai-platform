"""Confidence computation for refactoring opportunities.

Provides a deterministic formula for computing confidence values
based on category, evidence count, and completeness.

Confidence Formula
------------------

``confidence = base_score * evidence_factor * completeness_factor``

**Base scores by category:**

| Category | Base Score |
|---|---|
| CIRCULAR_DEPENDENCY | 0.95 |
| DEAD_CODE | 0.90 |
| HIGH_COUPLING | 0.80 |
| ORPHAN_MODULE | 0.85 |
| EXCESSIVE_DEPENDENCIES | 0.75 |
| LARGE_MODULE | 0.70 |

**Evidence factor:**

- evidence_count >= 3: 1.0 (strong evidence)
- evidence_count == 2: 0.9 (moderate evidence)
- evidence_count == 1: 0.8 (minimal evidence)
- evidence_count == 0: 0.5 (no evidence — should not occur)

**Completeness factor:**

- 1.0 = all evidence present (complete analysis)
- 0.9 = partial evidence (incomplete analysis)

**Final confidence:**

``clamp(base_score * evidence_factor * completeness_factor, 0.0, 1.0)``

Rounded to 2 decimal places.

Higher confidence means:
- Stronger category signal (higher base score)
- More supporting evidence
- More complete analysis

Usage
-----

.. code-block:: python

    from packages.advisors.refactoring.confidence import compute_confidence
    from packages.advisors.refactoring.models import (
        RefactoringCategory,
        EvidenceType,
    )

    # DEAD_CODE with 3 evidence items, complete analysis
    confidence = compute_confidence(
        category=RefactoringCategory.DEAD_CODE,
        evidence_count=3,
        completeness=1.0,
    )
    # Returns: 0.9

    # LARGE_MODULE with 1 evidence item, partial analysis
    confidence = compute_confidence(
        category=RefactoringCategory.LARGE_MODULE,
        evidence_count=1,
        completeness=0.9,
    )
    # Returns: 0.56
"""

from __future__ import annotations

from packages.advisors.refactoring.models import RefactoringCategory

# Base scores for each category — deterministic, documented values.
_BASE_SCORES: dict[RefactoringCategory, float] = {
    RefactoringCategory.CIRCULAR_DEPENDENCY: 0.95,
    RefactoringCategory.DEAD_CODE: 0.90,
    RefactoringCategory.ORPHAN_MODULE: 0.85,
    RefactoringCategory.HIGH_COUPLING: 0.80,
    RefactoringCategory.EXCESSIVE_DEPENDENCIES: 0.75,
    RefactoringCategory.LARGE_MODULE: 0.70,
}


def compute_confidence(
    category: RefactoringCategory,
    evidence_count: int,
    completeness: float = 1.0,
) -> float:
    """Compute a deterministic confidence value for a refactoring opportunity.

    Confidence Formula
    ------------------
    ``confidence = base_score * evidence_factor * completeness_factor``

    Base scores are determined by the ``category`` parameter.

    Evidence factor:
        - ``evidence_count >= 3``: 1.0 (strong evidence)
        - ``evidence_count == 2``: 0.9 (moderate evidence)
        - ``evidence_count == 1``: 0.8 (minimal evidence)
        - ``evidence_count == 0``: 0.5 (no evidence — should not occur)

    Completeness factor:
        - ``1.0`` = all evidence present (complete analysis)
        - ``0.9`` = partial evidence (incomplete analysis)

    The final value is clamped to ``[0.0, 1.0]`` and rounded to 2 decimal places.

    Args:
        category: The refactoring category.
        evidence_count: Number of evidence items supporting this opportunity.
        completeness: Completeness factor in ``[0.0, 1.0]``.
            ``1.0`` means complete analysis, ``0.9`` means partial.

    Returns:
        A float between 0.0 and 1.0 representing analysis confidence.

    Raises:
        ValueError: If ``completeness`` is not in ``[0.0, 1.0]``.
        ValueError: If ``evidence_count`` is negative.
    """
    if completeness < 0.0 or completeness > 1.0:
        raise ValueError(
            f"compute_confidence: completeness must be in [0.0, 1.0], got {completeness}"
        )

    if evidence_count < 0:
        raise ValueError(
            f"compute_confidence: evidence_count must be >= 0, got {evidence_count}"
        )

    # Get base score for category
    base_score = _BASE_SCORES.get(category, 0.70)

    # Compute evidence factor
    if evidence_count >= 3:
        evidence_factor = 1.0
    elif evidence_count == 2:
        evidence_factor = 0.9
    elif evidence_count == 1:
        evidence_factor = 0.8
    else:
        evidence_factor = 0.5

    # Compute final confidence
    confidence = base_score * evidence_factor * completeness

    # Clamp to [0.0, 1.0] and round to 2 decimal places
    confidence = max(0.0, min(1.0, confidence))
    return round(confidence, 2)
