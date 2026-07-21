"""Platform Validation Models — immutable dataclasses for health reporting.

Architecture
------------

PlatformValidator produces structured models that describe validation results:

    ValidationIssue     — single finding with identifier, component, severity
    ValidationStatistics — numeric summary of a validation run
    ValidationReport     — complete validation result with issues + statistics
    PlatformHealth       — health snapshot with status and report
    HealthReport         — human-readable health summary

All models use frozen dataclasses with slots=True for immutability.

Public API
----------

.. code-block:: python

    from packages.platform.models import (
        ValidationIssue,
        PlatformHealth,
        ValidationReport,
        HealthReport,
        ValidationStatistics,
        Severity,
    )

    issue = ValidationIssue(
        identifier="VALIDATE-001",
        component="workflow_registry",
        severity=Severity.ERROR,
        description="Workflow registry is missing.",
        recommendation="Ensure the bootstrap creates the workflow registry.",
    )

    stats = ValidationStatistics(
        total_checks=15,
        issues_count=1,
        errors_count=1,
        warnings_count=0,
        critical_count=0,
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "HealthReport",
    "PlatformHealth",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationStatistics",
]


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity:
    """Severity levels for validation issues.

    Attributes:
        INFO: Informational message, no action required.
        WARNING: Non-critical issue that should be investigated.
        ERROR: Issue that affects functionality but platform still operates.
        CRITICAL: Critical issue that prevents platform operation.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# ValidationIssue
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation finding.

    Attributes:
        identifier: Unique machine-readable identifier (e.g. "VALIDATE-001").
        component: The platform component that caused the issue.
        severity: Severity level from the Severity class.
        description: Human-readable description of the issue.
        recommendation: Recommended action to resolve the issue.
    """

    identifier: str
    component: str
    severity: str
    description: str
    recommendation: str


# ---------------------------------------------------------------------------
# ValidationStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationStatistics:
    """Numeric summary of a validation run.

    Attributes:
        total_checks: Total number of validation checks performed.
        issues_count: Total number of issues found (all severities).
        errors_count: Number of ERROR severity issues.
        warnings_count: Number of WARNING severity issues.
        critical_count: Number of CRITICAL severity issues.
    """

    total_checks: int = 0
    issues_count: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    critical_count: int = 0


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Complete validation result with issues and statistics.

    Attributes:
        issues: List of all validation issues found.
        statistics: Numeric summary statistics.
        is_valid: True if no ERROR or CRITICAL issues exist.
    """

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    statistics: ValidationStatistics = field(default_factory=ValidationStatistics)
    is_valid: bool = True

    def __post_init__(self) -> None:
        """Compute derived statistics from issues."""
        errors = sum(1 for i in self.issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        critical = sum(1 for i in self.issues if i.severity == Severity.CRITICAL)
        total = len(self.issues)

        stats = ValidationStatistics(
            total_checks=total + errors + warnings + critical,
            issues_count=total,
            errors_count=errors,
            warnings_count=warnings,
            critical_count=critical,
        )
        # Dataclass slots are frozen, so we need to use object.__setattr__
        # Actually, since this is __post_init__, we can mutate before frozen applies
        object.__setattr__(self, "statistics", stats)
        object.__setattr__(self, "is_valid", errors == 0 and critical == 0)


# ---------------------------------------------------------------------------
# PlatformHealth
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformHealth:
    """Platform health snapshot.

    Attributes:
        status: One of HEALTHY, UNHEALTHY, DEGRADED.
        report: The underlying validation report.
        timestamp: When the health check was performed.
    """

    status: str
    report: ValidationReport
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"


# ---------------------------------------------------------------------------
# HealthReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Human-readable health report.

    Attributes:
        health: The platform health snapshot.
        summary: One-line summary of platform health.
        details: Multi-line detailed health information.
    """

    health: PlatformHealth
    summary: str
    details: str

    def __str__(self) -> str:  # noqa: D105
        return self.details