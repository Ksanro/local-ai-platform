"""Immutable verification model definitions.

Defines the output structures of the Self Verification Framework. These are
the stable contracts between the verifier and its consumers.

Architecture
------------

VerificationStatus --> VerificationFinding --> VerificationReport
                     VerificationStatistics

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No repository analysis fields.
- No provider fields.
- No patch generation.

Public API
----------

.. code-block:: python

    from packages.verification.models import (
        VerificationFinding,
        VerificationReport,
        VerificationSeverity,
        VerificationStatus,
        VerificationStatistics,
    )

    finding = VerificationFinding(
        id="rule-001",
        category="patch-applied",
        severity=VerificationSeverity.INFO,
        title="Patch applied successfully",
        description="All patches were applied without errors.",
        evidence="All patch files show APPLIED status.",
        recommendation=None,
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "VerificationFinding",
    "VerificationReport",
    "VerificationSeverity",
    "VerificationStatus",
    "VerificationStatistics",
]


# ---------------------------------------------------------------------------
# VerificationStatus
# ---------------------------------------------------------------------------


class VerificationStatus(str, Enum):
    """Status of a verification result.

    Attributes:
        PASSED: All verification rules passed.
        FAILED: One or more critical verification rules failed.
        WARNING: One or more non-critical verification rules flagged issues.
        SKIPPED: Verification was skipped due to missing inputs.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# VerificationSeverity
# ---------------------------------------------------------------------------


class VerificationSeverity(str, Enum):
    """Severity level of a verification finding.

    Attributes:
        INFO: Informational finding with no impact.
        LOW: Minor issue that should be noted.
        MEDIUM: Moderate issue that may affect quality.
        HIGH: Significant issue that requires attention.
        CRITICAL: Critical issue that blocks verification.
    """

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# VerificationFinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationFinding:
    """An immutable record of a single verification finding.

    Attributes:
        id: Unique finding identifier (rule_id + index).
        category: Category of the finding (e.g. "patch-applied").
        severity: Severity level of the finding.
        title: Short human-readable title.
        description: Detailed description of the finding.
        evidence: Evidence supporting the finding.
        recommendation: Recommended action (None if not applicable).
    """

    id: str
    category: str
    severity: VerificationSeverity
    title: str
    description: str
    evidence: str
    recommendation: str | None = None


# ---------------------------------------------------------------------------
# VerificationStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationStatistics:
    """Aggregate statistics for a verification run.

    Attributes:
        executed_rules: Number of rules that were executed.
        passed_rules: Number of rules that passed.
        failed_rules: Number of rules that failed.
        warnings: Number of rules that produced warnings.
        duration_ms: Total verification duration in milliseconds.
    """

    executed_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    warnings: int = 0
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# VerificationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Complete verification report for an engineering execution.

    This is the canonical output artifact of the Self Verification Engine.
    It becomes the stable contract consumed by downstream components.

    Attributes:
        workflow_name: The workflow name that was verified.
        execution_id: Unique execution identifier.
        verification_status: Overall verification status.
        findings: Tuple of all verification findings in deterministic order.
        statistics: Verification statistics.
        score: Deterministic verification score (0.0 to 1.0).
        metadata: Additional metadata about the verification.
    """

    workflow_name: str
    execution_id: str
    verification_status: VerificationStatus
    findings: tuple[VerificationFinding, ...] = ()
    statistics: VerificationStatistics = field(
        default_factory=VerificationStatistics
    )
    score: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)