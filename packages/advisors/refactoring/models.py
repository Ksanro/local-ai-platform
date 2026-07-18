"""Refactoring Advisor models.

Defines the immutable dataclasses that represent refactoring opportunities
discovered through repository analysis. These models form the stable public
contract for the RefactoringAdvisor output.

Architecture
------------

RepositoryIndex
        |
        v
DiagnosticsEngine (dead code, orphans, cycles, large modules)
        |
        v
ArchitectureAnalyzer (coupling, layering, impact)
        |
        v
RefactoringAdvisor (orchestrates all -> RefactoringReport)

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.
- No AI-generated content.
- Deterministic ordering.

Public API
----------

.. code-block:: python

    from packages.advisors.refactoring.models import (
        RefactoringCategory,
        RefactoringOpportunity,
        RefactoringReport,
        RefactoringSummary,
        RepositoryStatistics,
        Severity,
    )

    report = RefactoringReport(
        summary=RefactoringSummary(
            total_opportunities=3,
            high=1,
            medium=1,
            low=1,
            info=0,
        ),
        statistics=RepositoryStatistics(
            modules=50,
            symbols=200,
            relationships=500,
            diagnostics=10,
        ),
        opportunities=(
            RefactoringOpportunity(
                id="HIGH_COUPLING:packages/foo.py",
                category=RefactoringCategory.HIGH_COUPLING,
                severity=Severity.HIGH,
                title="High coupling detected",
                description="This module has above-average connections.",
                affected_symbols=("packages.foo.func",),
                affected_modules=("packages/foo.py",),
                confidence=0.85,
                evidence=(
                    RefactoringEvidence(
                        type=EvidenceType.DEPENDENCY,
                        source="architecture",
                        message="Module has 15 total connections.",
                        reference="packages/foo.py",
                    ),
                ),
            ),
        ),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Priority level for a refactoring opportunity.

    Attributes:
        INFO: Informational, no immediate action needed.
        LOW: Minor improvement recommended.
        MEDIUM: Moderate improvement recommended.
        HIGH: Significant improvement needed.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RefactoringCategory(str, Enum):
    """Category of refactoring opportunity.

    Attributes:
        HIGH_COUPLING: Module has above-average dependency connections.
        LARGE_MODULE: Module exceeds configurable symbol threshold.
        DEAD_CODE: Module or symbol is unreachable.
        ORPHAN_MODULE: Module has zero relationships.
        CIRCULAR_DEPENDENCY: Module is part of a dependency cycle.
        EXCESSIVE_DEPENDENCIES: Module has an excessive number of outgoing relationships.
    """

    HIGH_COUPLING = "HIGH_COUPLING"
    LARGE_MODULE = "LARGE_MODULE"
    DEAD_CODE = "DEAD_CODE"
    ORPHAN_MODULE = "ORPHAN_MODULE"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    EXCESSIVE_DEPENDENCIES = "EXCESSIVE_DEPENDENCIES"


class EvidenceType(str, Enum):
    """Source type of a refactoring evidence item.

    Attributes:
        DIAGNOSTIC: From diagnostics engine analysis.
        DEPENDENCY: From dependency graph analysis.
        IMPACT: From change impact analysis.
        STATISTIC: From repository statistics.
        ARCHITECTURE: From architecture review analysis.
    """

    DIAGNOSTIC = "diagnostic"
    DEPENDENCY = "dependency"
    IMPACT = "impact"
    STATISTIC = "statistic"
    ARCHITECTURE = "architecture"


# ---------------------------------------------------------------------------
# RefactoringEvidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefactoringEvidence:
    """A single piece of evidence supporting a refactoring opportunity.

    Attributes:
        type: The source type of this evidence.
        source: Which public API produced this evidence.
        message: Human-readable description of the evidence.
        reference: Module path or symbol qualified name.
    """

    type: EvidenceType
    source: str
    message: str
    reference: str


# ---------------------------------------------------------------------------
# Evidence sort key helper
# ---------------------------------------------------------------------------


def _evidence_sort_key(ev: RefactoringEvidence) -> tuple[str, str, str, str]:
    """Sort key for ``RefactoringEvidence``.

    Used in ``__post_init__`` to produce deterministic ordering.
    """
    return (ev.type, ev.source, ev.message, ev.reference)


# ---------------------------------------------------------------------------
# RefactoringOpportunity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefactoringOpportunity:
    """A single refactoring opportunity identified in the repository.

    Attributes:
        id: Human-readable stable identifier. Format: ``"{category}:{modules}"``.
        category: The category of this refactoring opportunity.
        severity: Priority level for this opportunity.
        title: Short human-readable title.
        description: Detailed description of the opportunity.
        affected_symbols: Symbol qualified names affected by this opportunity.
        affected_modules: Module paths affected by this opportunity.
        confidence: Deterministic confidence value 0.0-1.0.
        evidence: Tuple of evidence supporting this opportunity.
    """

    id: str
    category: RefactoringCategory
    severity: Severity
    title: str
    description: str
    affected_symbols: tuple[str, ...] = field(default_factory=tuple)
    affected_modules: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    evidence: tuple[RefactoringEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate confidence range and sort affected collections."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"RefactoringOpportunity.confidence must be in [0.0, 1.0], "
                f"got {self.confidence}"
            )

        # Sort affected collections for determinism
        object.__setattr__(self, "affected_symbols", tuple(sorted(self.affected_symbols)))
        object.__setattr__(self, "affected_modules", tuple(sorted(self.affected_modules)))
        object.__setattr__(
            self, "evidence",
            tuple(sorted(self.evidence, key=_evidence_sort_key))
        )


# ---------------------------------------------------------------------------
# RefactoringSummary
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefactoringSummary:
    """Summary statistics for a refactoring report.

    Attributes:
        total_opportunities: Total number of refactoring opportunities.
        high: Count of HIGH severity opportunities.
        medium: Count of MEDIUM severity opportunities.
        low: Count of LOW severity opportunities.
        info: Count of INFO severity opportunities.
    """

    total_opportunities: int
    high: int
    medium: int
    low: int
    info: int


# ---------------------------------------------------------------------------
# RepositoryStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryStatistics:
    """Aggregate repository statistics.

    Attributes:
        modules: Number of modules in the repository.
        symbols: Number of symbols across all modules.
        relationships: Number of relationships across all modules.
        diagnostics: Number of diagnostic findings.
    """

    modules: int = 0
    symbols: int = 0
    relationships: int = 0
    diagnostics: int = 0


# ---------------------------------------------------------------------------
# RefactoringReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefactoringReport:
    """Complete refactoring report for a repository.

    All collections are sorted deterministically — by severity descending,
    then confidence descending, then id ascending — so repeated execution
    produces identical output.

    Attributes:
        summary: Summary statistics of all opportunities.
        statistics: Aggregate repository statistics.
        opportunities: All refactoring opportunities, sorted by priority.
    """

    summary: RefactoringSummary
    statistics: RepositoryStatistics
    opportunities: tuple[RefactoringOpportunity, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Ensure deterministic ordering of opportunities."""
        severity_order = {
            Severity.HIGH: 0,
            Severity.MEDIUM: 1,
            Severity.LOW: 2,
            Severity.INFO: 3,
        }
        sorted_opportunities = sorted(
            self.opportunities,
            key=lambda o: (severity_order.get(o.severity, 4), -o.confidence, o.id),
        )
        object.__setattr__(self, "opportunities", tuple(sorted_opportunities))
