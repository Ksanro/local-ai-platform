"""Diagnostics Engine — structured diagnostic issue generation.

Architecture
------------

DiagnosticsEngine produces structured diagnostic issues with:

    identifier    — unique machine-readable ID
    component     — affected platform component
    severity      — INFO, WARNING, ERROR, or CRITICAL
    description   — human-readable explanation
    recommendation — actionable fix guidance

Public API
----------

.. code-block:: python

    from packages.platform.diagnostics import DiagnosticsEngine

    diagnostics = DiagnosticsEngine()
    issue = diagnostics.create_issue(
        identifier="DIAG-001",
        component="workflow_registry",
        severity="WARNING",
        description="Workflow registry has only one entry.",
        recommendation="Register additional workflows for production use.",
    )

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.platform.models import (
    Severity,
    ValidationIssue,
)

if TYPE_CHECKING:
    from packages.platform.models import ValidationIssue as _VI  # noqa: F401

__all__ = [
    "DiagnosticsEngine",
]


# ---------------------------------------------------------------------------
# DiagnosticsEngine
# ---------------------------------------------------------------------------


class DiagnosticsEngine:
    """Produces structured diagnostic issues for platform validation.

    This engine is responsible for creating well-structured
    ValidationIssue instances with consistent identifiers,
    severity levels, and actionable recommendations.

    Usage
    -----

    .. code-block:: python

        from packages.platform.diagnostics import DiagnosticsEngine
        from packages.platform.models import Severity

        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="VALIDATE-001",
            component="workflow_registry",
            severity=Severity.ERROR,
            description="Workflow registry is missing.",
            recommendation="Ensure the bootstrap creates the workflow registry.",
        )

    Attributes
    ----------
    _counter: Internal counter for auto-generating identifiers.
    """

    def __init__(self) -> None:
        """Initialize the diagnostics engine."""
        self._counter: int = 0

    def create_issue(
        self,
        identifier: str,
        component: str,
        severity: str,
        description: str,
        recommendation: str,
    ) -> ValidationIssue:
        """Create a structured validation issue.

        Args:
            identifier: Unique machine-readable identifier.
            component: The platform component that caused the issue.
            severity: Severity level (Severity.INFO, WARNING, ERROR, CRITICAL).
            description: Human-readable description.
            recommendation: Recommended action to resolve.

        Returns:
            A ValidationIssue instance.

        Raises:
            ValueError: If severity is not a valid Severity constant.

        Example
        -------

        .. code-block:: python

            issue = diag.create_issue(
                identifier="VALIDATE-001",
                component="workflow_registry",
                severity=Severity.ERROR,
                description="Registry is empty.",
                recommendation="Register at least one workflow.",
            )
        """
        # Validate severity
        valid_severities = {Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL}
        if severity not in valid_severities:
            raise ValueError(
                f"Invalid severity '{severity}'. "
                f"Must be one of: {valid_severities}"
            )

        return ValidationIssue(
            identifier=identifier,
            component=component,
            severity=severity,
            description=description,
            recommendation=recommendation,
        )

    def next_identifier(self, prefix: str = "DIAG") -> str:
        """Generate the next sequential identifier.

        Auto-increments a counter and returns a formatted identifier.

        Args:
            prefix: Prefix for the identifier (default "DIAG").

        Returns:
            Formatted identifier string (e.g. "DIAG-001").

        Example

        .. code-block:: python

            diag.next_identifier()  # "DIAG-001"
            diag.next_identifier()  # "DIAG-002"
        """
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    def diagnostics(
        self,
        registries: object,
        configuration: object,
        container: object,
    ) -> list[ValidationIssue]:
        """Run all diagnostic checks and return structured issues.

        This is the main entry point for diagnostics. It delegates
        to the PlatformValidator for actual checks and uses
        create_issue() to build structured results.

        Args:
            registries: The platform registries instance.
            configuration: The platform configuration instance.
            container: The dependency container instance.

        Returns:
            List of ValidationIssue instances.

        Example

        .. code-block:: python

            issues = diag.diagnostics(registries, config, container)
            for issue in issues:
                print(f"{issue.severity}: {issue.description}")
        """
        from packages.platform.validator import PlatformValidator

        validator = PlatformValidator()
        report = validator.validate(registries, configuration, container)
        return list(report.issues)