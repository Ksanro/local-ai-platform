"""Platform Health Checker — deterministic health status computation.

Architecture
------------

PlatformHealthChecker computes a deterministic health status from
a ValidationReport. It never performs validation itself — it only
consumes ValidationReport instances from PlatformValidator.

    PlatformHealthChecker
        │
        ├── health() — compute PlatformHealth from validation
        ├── summary() — one-line health summary
        └── details() — multi-line health details

Public API
----------

.. code-block:: python

    from packages.platform.health import PlatformHealthChecker

    checker = PlatformHealthChecker()
    health = checker.health(report)
    print(checker.summary(health))

"""

from __future__ import annotations

from datetime import datetime, timezone

from packages.platform.models import (
    HealthReport,
    PlatformHealth,
    Severity,
    ValidationReport,
)

__all__ = [
    "PlatformHealthChecker",
]


# ---------------------------------------------------------------------------
# PlatformHealthChecker
# ---------------------------------------------------------------------------


class PlatformHealthChecker:
    """Computes deterministic platform health from validation reports.

    This checker takes a ValidationReport and computes a health status
    of HEALTHY, DEGRADED, or UNHEALTHY based on the issues present.

    Health Status Rules
    -------------------
    - HEALTHY: No issues at all
    - DEGRADED: Only WARNING-level issues (no ERROR or CRITICAL)
    - UNHEALTHY: Any ERROR or CRITICAL issues

    Usage
    -----

    .. code-block:: python

        from packages.platform.health import PlatformHealthChecker
        from packages.platform.validator import PlatformValidator

        validator = PlatformValidator()
        checker = PlatformHealthChecker()

        report = validator.validate(registries, config, container)
        health = checker.health(report)

        if health.status == PlatformHealth.HEALTHY:
            print("Platform is fully operational")

    Attributes
    ----------
    _include_details: Whether to include detailed information in reports.
    """

    def __init__(self, include_details: bool = True) -> None:
        """Initialize the health checker.

        Args:
            include_details: Whether to include detailed information.
                Defaults to True.
        """
        self._include_details = include_details

    def health(
        self,
        report: ValidationReport,
    ) -> PlatformHealth:
        """Compute platform health from a validation report.

        Args:
            report: The validation report to analyze.

        Returns:
            PlatformHealth with computed status.

        Raises:
            ValueError: If report is None.

        Example
        -------

        .. code-block:: python

            report = validator.validate(registries, config, container)
            health = checker.health(report)
            assert health.status in ("HEALTHY", "DEGRADED", "UNHEALTHY")
        """
        if report is None:
            raise ValueError("Cannot compute health from None report.")

        status = self._compute_status(report)
        return PlatformHealth(
            status=status,
            report=report,
            timestamp=datetime.now(timezone.utc),
        )

    def summary(
        self,
        health: PlatformHealth,
    ) -> str:
        """Generate a one-line health summary.

        Args:
            health: The platform health snapshot.

        Returns:
            One-line summary string.

        Example
        -------

        .. code-block:: python

            health = checker.health(report)
            print(checker.summary(health))
            # "Platform HEALTHY: All checks passed."
        """
        stats = health.report.statistics

        if health.status == PlatformHealth.HEALTHY:
            return "Platform HEALTHY: All checks passed."
        elif health.status == PlatformHealth.DEGRADED:
            return (
                f"Platform DEGRADED: {stats.warnings_count} warning(s), "
                f"{stats.issues_count} total issue(s)."
            )
        else:
            return (
                f"Platform UNHEALTHY: {stats.errors_count} error(s), "
                f"{stats.critical_count} critical, "
                f"{stats.warnings_count} warning(s), "
                f"{stats.issues_count} total issue(s)."
            )

    def details(
        self,
        health: PlatformHealth,
    ) -> str:
        """Generate multi-line health details.

        Args:
            health: The platform health snapshot.

        Returns:
            Multi-line detailed health report.

        Example
        -------

        .. code-block:: python

            health = checker.health(report)
            print(checker.details(health))
        """
        lines: list[str] = []
        stats = health.report.statistics

        lines.append(f"Platform Health: {health.status}")
        lines.append(f"Total Checks: {stats.total_checks}")
        lines.append(f"Issues: {stats.issues_count}")

        if stats.issues_count > 0:
            lines.append("")
            lines.append("Issues by Severity:")

            for sev_name in ("CRITICAL", "ERROR", "WARNING", "INFO"):
                count = sum(
                    1 for i in health.report.issues if i.severity == sev_name
                )
                if count > 0:
                    lines.append(f"  {sev_name}: {count}")

            lines.append("")
            lines.append("Issue Details:")
            for issue in health.report.issues:
                lines.append(f"  [{issue.severity}] {issue.component}: {issue.description}")
                if self._include_details and issue.recommendation:
                    lines.append(f"    -> {issue.recommendation}")

        return "\n".join(lines)

    def health_report(
        self,
        health: PlatformHealth,
    ) -> HealthReport:
        """Generate a complete HealthReport from platform health.

        Args:
            health: The platform health snapshot.

        Returns:
            A HealthReport with health, summary, and details.

        Example
        -------

        .. code-block:: python

            health = checker.health(report)
            report = checker.health_report(health)
            print(report.summary)
            print(report.details)
        """
        return HealthReport(
            health=health,
            summary=self.summary(health),
            details=self.details(health),
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _compute_status(
        self,
        report: ValidationReport,
    ) -> str:
        """Compute health status from a validation report.

        Rules:
        - No issues → HEALTHY
        - Only WARNING → DEGRADED
        - ERROR or CRITICAL → UNHEALTHY

        Args:
            report: The validation report.

        Returns:
            One of HEALTHY, DEGRADED, UNHEALTHY.
        """
        has_critical = any(
            i.severity in (Severity.ERROR, Severity.CRITICAL)
            for i in report.issues
        )
        has_warnings = any(i.severity == Severity.WARNING for i in report.issues)

        if has_critical:
            return PlatformHealth.UNHEALTHY
        elif has_warnings:
            return PlatformHealth.DEGRADED
        else:
            return PlatformHealth.HEALTHY