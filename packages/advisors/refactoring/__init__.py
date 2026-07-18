"""Refactoring Advisor package.

Provides deterministic refactoring recommendations based on
repository analysis data.

Usage
-----

.. code-block:: python

    from packages.advisors.refactoring.advisor import RefactoringAdvisor
    from packages.advisors.refactoring.config import DEFAULT_CONFIG

    advisor = RefactoringAdvisor()
    report = advisor.analyze(repository_index=index)

    for opp in report.opportunities:
        print(f"{opp.severity}: {opp.title}")
        print(f"  Confidence: {opp.confidence}")
        print(f"  Evidence: {len(opp.evidence)} items")
        for ev in opp.evidence:
            print(f"    - [{ev.type.value}] {ev.message}")

Public API
----------

.. code-block:: python

    from packages.advisors.refactoring.models import (
        EvidenceType,
        RefactoringCategory,
        RefactoringEvidence,
        RefactoringOpportunity,
        RefactoringReport,
        RefactoringSummary,
        RepositoryStatistics,
        Severity,
    )

    from packages.advisors.refactoring.config import (
        RefactoringConfig,
        DEFAULT_CONFIG,
    )

    from packages.advisors.refactoring.confidence import compute_confidence

    from packages.advisors.refactoring.advisor import RefactoringAdvisor
"""

from __future__ import annotations

from packages.advisors.refactoring.advisor import RefactoringAdvisor
from packages.advisors.refactoring.confidence import compute_confidence
from packages.advisors.refactoring.config import DEFAULT_CONFIG, RefactoringConfig
from packages.advisors.refactoring.models import (
    EvidenceType,
    RefactoringCategory,
    RefactoringEvidence,
    RefactoringOpportunity,
    RefactoringReport,
    RefactoringSummary,
    RepositoryStatistics,
    Severity,
)

__all__ = [
    # Models
    "EvidenceType",
    "RefactoringCategory",
    "RefactoringEvidence",
    "RefactoringOpportunity",
    "RefactoringReport",
    "RefactoringSummary",
    "RepositoryStatistics",
    "Severity",
    # Config
    "RefactoringConfig",
    "DEFAULT_CONFIG",
    # Confidence
    "compute_confidence",
    # Advisor
    "RefactoringAdvisor",
]
