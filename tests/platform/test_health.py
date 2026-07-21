"""Tests for PlatformHealthChecker.

Tests cover:
- Health status computation (HEALTHY, DEGRADED, UNHEALTHY)
- Summary generation
- Details generation
- HealthReport creation
- None report handling
"""

from __future__ import annotations

import pytest

from packages.platform.health import PlatformHealthChecker
from packages.platform.models import (
    HealthReport,
    PlatformHealth,
    Severity,
    ValidationIssue,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# Health status computation tests
# ---------------------------------------------------------------------------


class TestHealthStatusComputation:
    """Tests for health status computation."""

    def test_healthy_no_issues(self) -> None:
        report = ValidationReport()
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.HEALTHY

    def test_unhealthy_with_error(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error issue.",
            recommendation="Fix it.",
        )
        report = ValidationReport(issues=(issue,))
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.UNHEALTHY

    def test_unhealthy_with_critical(self) -> None:
        issue = ValidationIssue(
            identifier="CRT-001",
            component="test",
            severity=Severity.CRITICAL,
            description="Critical issue.",
            recommendation="Fix immediately.",
        )
        report = ValidationReport(issues=(issue,))
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.UNHEALTHY

    def test_degraded_with_warning_only(self) -> None:
        issue = ValidationIssue(
            identifier="WRN-001",
            component="test",
            severity=Severity.WARNING,
            description="Warning issue.",
            recommendation="Check it.",
        )
        report = ValidationReport(issues=(issue,))
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.DEGRADED

    def test_degraded_with_multiple_warnings(self) -> None:
        issues = (
            ValidationIssue(
                identifier="WRN-001",
                component="test",
                severity=Severity.WARNING,
                description="Warning 1.",
                recommendation="Fix 1.",
            ),
            ValidationIssue(
                identifier="WRN-002",
                component="test",
                severity=Severity.WARNING,
                description="Warning 2.",
                recommendation="Fix 2.",
            ),
        )
        report = ValidationReport(issues=issues)
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.DEGRADED

    def test_unhealthy_with_error_and_warning(self) -> None:
        issues = (
            ValidationIssue(
                identifier="ERR-001",
                component="test",
                severity=Severity.ERROR,
                description="Error.",
                recommendation="Fix.",
            ),
            ValidationIssue(
                identifier="WRN-001",
                component="test",
                severity=Severity.WARNING,
                description="Warning.",
                recommendation="Check.",
            ),
        )
        report = ValidationReport(issues=issues)
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.UNHEALTHY

    def test_healthy_with_info_only(self) -> None:
        issue = ValidationIssue(
            identifier="INF-001",
            component="test",
            severity=Severity.INFO,
            description="Info message.",
            recommendation="Note it.",
        )
        report = ValidationReport(issues=(issue,))
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.HEALTHY

    def test_healthy_with_info_and_warning(self) -> None:
        issues = (
            ValidationIssue(
                identifier="INF-001",
                component="test",
                severity=Severity.INFO,
                description="Info.",
                recommendation="Note.",
            ),
            ValidationIssue(
                identifier="WRN-001",
                component="test",
                severity=Severity.WARNING,
                description="Warning.",
                recommendation="Check.",
            ),
        )
        report = ValidationReport(issues=issues)
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.status == PlatformHealth.DEGRADED


# ---------------------------------------------------------------------------
# Summary generation tests
# ---------------------------------------------------------------------------


class TestSummaryGeneration:
    """Tests for health summary generation."""

    def test_summary_healthy(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(status=PlatformHealth.HEALTHY, report=report)
        checker = PlatformHealthChecker()
        summary = checker.summary(health)
        assert "HEALTHY" in summary
        assert "All checks passed" in summary

    def test_summary_degraded(self) -> None:
        issue = ValidationIssue(
            identifier="WRN-001",
            component="test",
            severity=Severity.WARNING,
            description="Warning.",
            recommendation="Check.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.DEGRADED, report=report)
        checker = PlatformHealthChecker()
        summary = checker.summary(health)
        assert "DEGRADED" in summary
        assert "1 warning" in summary

    def test_summary_unhealthy(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error.",
            recommendation="Fix.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker()
        summary = checker.summary(health)
        assert "UNHEALTHY" in summary
        assert "1 error" in summary

    def test_summary_unhealthy_with_critical(self) -> None:
        issue = ValidationIssue(
            identifier="CRT-001",
            component="test",
            severity=Severity.CRITICAL,
            description="Critical.",
            recommendation="Fix now.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker()
        summary = checker.summary(health)
        assert "UNHEALTHY" in summary
        assert "1 critical" in summary


# ---------------------------------------------------------------------------
# Details generation tests
# ---------------------------------------------------------------------------


class TestDetailsGeneration:
    """Tests for health details generation."""

    def test_details_empty(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(status=PlatformHealth.HEALTHY, report=report)
        checker = PlatformHealthChecker()
        details = checker.details(health)
        assert "HEALTHY" in details
        assert "Issues: 0" in details

    def test_details_with_issues(self) -> None:
        issues = (
            ValidationIssue(
                identifier="ERR-001",
                component="test",
                severity=Severity.ERROR,
                description="Error issue.",
                recommendation="Fix it.",
            ),
            ValidationIssue(
                identifier="WRN-001",
                component="test",
                severity=Severity.WARNING,
                description="Warning issue.",
                recommendation="Check it.",
            ),
        )
        report = ValidationReport(issues=issues)
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker()
        details = checker.details(health)
        assert "ERROR" in details
        assert "WARNING" in details
        assert "Error issue." in details
        assert "Warning issue." in details
        assert "Fix it." in details

    def test_details_no_recommendations_when_disabled(self) -> None:
        issues = (
            ValidationIssue(
                identifier="ERR-001",
                component="test",
                severity=Severity.ERROR,
                description="Error.",
                recommendation="Fix.",
            ),
        )
        report = ValidationReport(issues=issues)
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker(include_details=False)
        details = checker.details(health)
        assert "ERROR" in details
        assert "->" not in details

    def test_details_includes_total_checks(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(status=PlatformHealth.HEALTHY, report=report)
        checker = PlatformHealthChecker()
        details = checker.details(health)
        assert "Total Checks:" in details


# ---------------------------------------------------------------------------
# HealthReport creation tests
# ---------------------------------------------------------------------------


class TestHealthReportCreation:
    """Tests for HealthReport creation."""

    def test_health_report_healthy(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(status=PlatformHealth.HEALTHY, report=report)
        checker = PlatformHealthChecker()
        health_report = checker.health_report(health)
        assert isinstance(health_report, HealthReport)
        assert health_report.health is health
        assert "HEALTHY" in health_report.summary
        assert "HEALTHY" in health_report.details

    def test_health_report_unhealthy(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error.",
            recommendation="Fix.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker()
        health_report = checker.health_report(health)
        assert health_report.health.status == PlatformHealth.UNHEALTHY
        assert "UNHEALTHY" in health_report.summary

    def test_health_report_str(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(status=PlatformHealth.HEALTHY, report=report)
        checker = PlatformHealthChecker()
        health_report = checker.health_report(health)
        assert str(health_report) == health_report.details


# ---------------------------------------------------------------------------
# None handling tests
# ---------------------------------------------------------------------------


class TestNoneHandling:
    """Tests for None report handling."""

    def test_health_none_report_raises(self) -> None:
        checker = PlatformHealthChecker()
        with pytest.raises(ValueError, match="Cannot compute health from None report"):
            checker.health(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Timestamp tests
# ---------------------------------------------------------------------------


class TestTimestamp:
    """Tests for health timestamp."""

    def test_health_has_timestamp(self) -> None:
        report = ValidationReport()
        checker = PlatformHealthChecker()
        health = checker.health(report)
        assert health.timestamp is not None
        assert hasattr(health.timestamp, "tzinfo")
        assert health.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Include details flag tests
# ---------------------------------------------------------------------------


class TestIncludeDetailsFlag:
    """Tests for include_details flag behavior."""

    def test_include_details_true(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error.",
            recommendation="Fix it.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker(include_details=True)
        details = checker.details(health)
        assert "Fix it." in details

    def test_include_details_false(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error.",
            recommendation="Fix it.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(status=PlatformHealth.UNHEALTHY, report=report)
        checker = PlatformHealthChecker(include_details=False)
        details = checker.details(health)
        assert "Fix it." not in details