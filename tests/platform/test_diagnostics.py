"""Tests for DiagnosticsEngine.

Tests cover:
- Issue creation with all severity levels
- Identifier generation
- Invalid severity handling
- Diagnostics method delegation
"""

from __future__ import annotations

import pytest

from packages.platform.diagnostics import DiagnosticsEngine
from packages.platform.models import Severity, ValidationIssue


# ---------------------------------------------------------------------------
# Issue creation tests
# ---------------------------------------------------------------------------


class TestIssueCreation:
    """Tests for ValidationIssue creation."""

    def test_create_info_issue(self) -> None:
        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="DIAG-001",
            component="test",
            severity=Severity.INFO,
            description="Info message.",
            recommendation="Note it.",
        )
        assert isinstance(issue, ValidationIssue)
        assert issue.identifier == "DIAG-001"
        assert issue.component == "test"
        assert issue.severity == Severity.INFO
        assert issue.description == "Info message."
        assert issue.recommendation == "Note it."

    def test_create_warning_issue(self) -> None:
        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="DIAG-001",
            component="test",
            severity=Severity.WARNING,
            description="Warning message.",
            recommendation="Check it.",
        )
        assert issue.severity == Severity.WARNING
        assert issue.description == "Warning message."

    def test_create_error_issue(self) -> None:
        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="DIAG-001",
            component="test",
            severity=Severity.ERROR,
            description="Error message.",
            recommendation="Fix it.",
        )
        assert issue.severity == Severity.ERROR
        assert issue.description == "Error message."

    def test_create_critical_issue(self) -> None:
        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="DIAG-001",
            component="test",
            severity=Severity.CRITICAL,
            description="Critical message.",
            recommendation="Fix immediately.",
        )
        assert issue.severity == Severity.CRITICAL
        assert issue.description == "Critical message."

    def test_create_issue_all_fields(self) -> None:
        diag = DiagnosticsEngine()
        issue = diag.create_issue(
            identifier="TEST-001",
            component="workflow_registry",
            severity=Severity.ERROR,
            description="Workflow registry is missing.",
            recommendation="Ensure the bootstrap creates the workflow registry.",
        )
        assert issue.identifier == "TEST-001"
        assert issue.component == "workflow_registry"
        assert issue.severity == Severity.ERROR
        assert issue.description == "Workflow registry is missing."
        assert issue.recommendation == "Ensure the bootstrap creates the workflow registry."


# ---------------------------------------------------------------------------
# Invalid severity handling tests
# ---------------------------------------------------------------------------


class TestInvalidSeverity:
    """Tests for invalid severity handling."""

    def test_invalid_severity_raises(self) -> None:
        diag = DiagnosticsEngine()
        with pytest.raises(ValueError, match="Invalid severity"):
            diag.create_issue(
                identifier="DIAG-001",
                component="test",
                severity="INVALID",  # type: ignore[arg-type]
                description="Test.",
                recommendation="Test.",
            )

    def test_empty_severity_raises(self) -> None:
        diag = DiagnosticsEngine()
        with pytest.raises(ValueError, match="Invalid severity"):
            diag.create_issue(
                identifier="DIAG-001",
                component="test",
                severity="",  # type: ignore[arg-type]
                description="Test.",
                recommendation="Test.",
            )

    def test_none_severity_raises(self) -> None:
        diag = DiagnosticsEngine()
        with pytest.raises(ValueError, match="Invalid severity"):
            diag.create_issue(
                identifier="DIAG-001",
                component="test",
                severity=None,  # type: ignore[arg-type]
                description="Test.",
                recommendation="Test.",
            )


# ---------------------------------------------------------------------------
# Identifier generation tests
# ---------------------------------------------------------------------------


class TestIdentifierGeneration:
    """Tests for identifier generation."""

    def test_first_identifier(self) -> None:
        diag = DiagnosticsEngine()
        ident = diag.next_identifier()
        assert ident == "DIAG-0001"

    def test_sequential_identifiers(self) -> None:
        diag = DiagnosticsEngine()
        ident1 = diag.next_identifier()
        ident2 = diag.next_identifier()
        ident3 = diag.next_identifier()
        assert ident1 == "DIAG-0001"
        assert ident2 == "DIAG-0002"
        assert ident3 == "DIAG-0003"

    def test_custom_prefix(self) -> None:
        diag = DiagnosticsEngine()
        ident = diag.next_identifier(prefix="VALIDATE")
        assert ident == "VALIDATE-0001"

    def test_custom_prefix_sequential(self) -> None:
        diag = DiagnosticsEngine()
        ident1 = diag.next_identifier(prefix="BOOT")
        ident2 = diag.next_identifier(prefix="BOOT")
        assert ident1 == "BOOT-0001"
        assert ident2 == "BOOT-0002"

    def test_mixed_prefixes(self) -> None:
        diag = DiagnosticsEngine()
        ident1 = diag.next_identifier(prefix="BOOT")
        ident2 = diag.next_identifier(prefix="DEPG")
        ident3 = diag.next_identifier(prefix="BOOT")
        assert ident1 == "BOOT-0001"
        assert ident2 == "DEPG-0002"
        assert ident3 == "BOOT-0003"


# ---------------------------------------------------------------------------
# Multiple issues creation tests
# ---------------------------------------------------------------------------


class TestMultipleIssues:
    """Tests for creating multiple issues."""

    def test_create_multiple_issues(self) -> None:
        diag = DiagnosticsEngine()
        issues = []
        for i in range(5):
            issue = diag.create_issue(
                identifier=diag.next_identifier(),
                component=f"component_{i}",
                severity=Severity.WARNING,
                description=f"Issue {i}.",
                recommendation=f"Fix {i}.",
            )
            issues.append(issue)

        assert len(issues) == 5
        for i, issue in enumerate(issues):
            assert issue.component == f"component_{i}"
            assert issue.description == f"Issue {i}."

    def test_issue_uniqueness(self) -> None:
        diag = DiagnosticsEngine()
        issue1 = diag.create_issue(
            identifier=diag.next_identifier(),
            component="test",
            severity=Severity.ERROR,
            description="First.",
            recommendation="Fix 1.",
        )
        issue2 = diag.create_issue(
            identifier=diag.next_identifier(),
            component="test",
            severity=Severity.ERROR,
            description="Second.",
            recommendation="Fix 2.",
        )
        assert issue1.identifier != issue2.identifier
        assert issue1.recommendation != issue2.recommendation


# ---------------------------------------------------------------------------
# Diagnostics method tests
# ---------------------------------------------------------------------------


class TestDiagnosticsMethod:
    """Tests for the diagnostics() method."""

    def test_diagnostics_delegates_to_validator(self) -> None:
        """The diagnostics() method delegates to PlatformValidator."""
        diag = DiagnosticsEngine()
        # With None inputs, validator will produce issues
        issues = diag.diagnostics(None, None, None)
        # Should return a list (not empty because validator handles None)
        assert isinstance(issues, list)

    def test_diagnostics_returns_validation_issues(self) -> None:
        """The diagnostics() method returns ValidationIssue instances."""
        diag = DiagnosticsEngine()
        issues = diag.diagnostics(None, None, None)
        for issue in issues:
            assert isinstance(issue, ValidationIssue)

    def test_diagnostics_with_valid_inputs(self) -> None:
        """Diagnostics with None inputs still returns issues."""
        diag = DiagnosticsEngine()
        issues = diag.diagnostics(None, None, None)
        # Should contain at least bootstrap and container issues
        assert len(issues) > 0