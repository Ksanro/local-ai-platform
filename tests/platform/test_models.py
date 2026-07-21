"""Tests for platform models.

Tests cover:
- Severity constants
- ValidationIssue immutability and fields
- ValidationStatistics counts
- ValidationReport is_valid computation
- PlatformHealth status values
- HealthReport summary and details
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from packages.platform.models import (
    HealthReport,
    PlatformHealth,
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStatistics,
)


# ---------------------------------------------------------------------------
# Severity tests
# ---------------------------------------------------------------------------


class TestSeverity:
    """Tests for Severity constants."""

    def test_info_level(self) -> None:
        assert Severity.INFO == "INFO"

    def test_warning_level(self) -> None:
        assert Severity.WARNING == "WARNING"

    def test_error_level(self) -> None:
        assert Severity.ERROR == "ERROR"

    def test_critical_level(self) -> None:
        assert Severity.CRITICAL == "CRITICAL"

    def test_all_levels_distinct(self) -> None:
        levels = {Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL}
        assert len(levels) == 4


# ---------------------------------------------------------------------------
# ValidationIssue tests
# ---------------------------------------------------------------------------


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_create_issue(self) -> None:
        issue = ValidationIssue(
            identifier="VALIDATE-001",
            component="workflow_registry",
            severity=Severity.ERROR,
            description="Workflow registry is missing.",
            recommendation="Ensure the bootstrap creates the workflow registry.",
        )
        assert issue.identifier == "VALIDATE-001"
        assert issue.component == "workflow_registry"
        assert issue.severity == Severity.ERROR
        assert issue.description == "Workflow registry is missing."
        assert issue.recommendation == "Ensure the bootstrap creates the workflow registry."

    def test_issue_is_immutable(self) -> None:
        issue = ValidationIssue(
            identifier="TEST-001",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        with pytest.raises(Exception):
            issue.identifier = "new"  # type: ignore[assignment]

    def test_issue_equality(self) -> None:
        issue1 = ValidationIssue(
            identifier="TEST-001",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        issue2 = ValidationIssue(
            identifier="TEST-001",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        assert issue1 == issue2

    def test_issue_not_equal(self) -> None:
        issue1 = ValidationIssue(
            identifier="TEST-001",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        issue2 = ValidationIssue(
            identifier="TEST-002",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        assert issue1 != issue2

    def test_issue_hashable(self) -> None:
        issue = ValidationIssue(
            identifier="TEST-001",
            component="test",
            severity=Severity.INFO,
            description="Test issue.",
            recommendation="Fix it.",
        )
        assert hash(issue) is not None
        s: set[ValidationIssue] = {issue}
        assert issue in s


# ---------------------------------------------------------------------------
# ValidationStatistics tests
# ---------------------------------------------------------------------------


class TestValidationStatistics:
    """Tests for ValidationStatistics dataclass."""

    def test_default_statistics(self) -> None:
        stats = ValidationStatistics()
        assert stats.total_checks == 0
        assert stats.issues_count == 0
        assert stats.errors_count == 0
        assert stats.warnings_count == 0
        assert stats.critical_count == 0

    def test_custom_statistics(self) -> None:
        stats = ValidationStatistics(
            total_checks=10,
            issues_count=3,
            errors_count=2,
            warnings_count=1,
            critical_count=0,
        )
        assert stats.total_checks == 10
        assert stats.issues_count == 3
        assert stats.errors_count == 2
        assert stats.warnings_count == 1
        assert stats.critical_count == 0

    def test_statistics_is_immutable(self) -> None:
        stats = ValidationStatistics(total_checks=5)
        with pytest.raises(Exception):
            stats.total_checks = 10


# ---------------------------------------------------------------------------
# ValidationReport tests
# ---------------------------------------------------------------------------


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_empty_report(self) -> None:
        report = ValidationReport()
        assert report.issues == ()
        assert report.statistics.issues_count == 0
        assert report.is_valid is True

    def test_report_with_no_issues_is_valid(self) -> None:
        report = ValidationReport(issues=())
        assert report.is_valid is True
        assert report.statistics.issues_count == 0

    def test_report_with_error_is_invalid(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error issue.",
            recommendation="Fix it.",
        )
        report = ValidationReport(issues=(issue,))
        assert report.is_valid is False
        assert report.statistics.errors_count == 1

    def test_report_with_warning_is_valid(self) -> None:
        issue = ValidationIssue(
            identifier="WRN-001",
            component="test",
            severity=Severity.WARNING,
            description="Warning issue.",
            recommendation="Check it.",
        )
        report = ValidationReport(issues=(issue,))
        assert report.is_valid is True
        assert report.statistics.warnings_count == 1

    def test_report_with_critical_is_invalid(self) -> None:
        issue = ValidationIssue(
            identifier="CRT-001",
            component="test",
            severity=Severity.CRITICAL,
            description="Critical issue.",
            recommendation="Fix immediately.",
        )
        report = ValidationReport(issues=(issue,))
        assert report.is_valid is False
        assert report.statistics.critical_count == 1

    def test_report_with_mixed_severities(self) -> None:
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
            ValidationIssue(
                identifier="INF-001",
                component="test",
                severity=Severity.INFO,
                description="Info.",
                recommendation="Note.",
            ),
        )
        report = ValidationReport(issues=issues)
        assert report.is_valid is False
        assert report.statistics.issues_count == 3
        assert report.statistics.errors_count == 1
        assert report.statistics.warnings_count == 1

    def test_report_statistics_auto_computed(self) -> None:
        issues = (
            ValidationIssue(
                identifier="E1",
                component="c",
                severity=Severity.ERROR,
                description="d",
                recommendation="r",
            ),
            ValidationIssue(
                identifier="E2",
                component="c",
                severity=Severity.ERROR,
                description="d",
                recommendation="r",
            ),
            ValidationIssue(
                identifier="W1",
                component="c",
                severity=Severity.WARNING,
                description="d",
                recommendation="r",
            ),
        )
        report = ValidationReport(issues=issues)
        assert report.statistics.errors_count == 2
        assert report.statistics.warnings_count == 1
        assert report.statistics.issues_count == 3

    def test_report_is_immutable(self) -> None:
        report = ValidationReport()
        with pytest.raises(Exception):
            report.issues = ()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PlatformHealth tests
# ---------------------------------------------------------------------------


class TestPlatformHealth:
    """Tests for PlatformHealth dataclass."""

    def test_healthy_status(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        assert health.status == PlatformHealth.HEALTHY
        assert health.report is report
        assert health.timestamp is not None

    def test_unhealthy_status(self) -> None:
        issue = ValidationIssue(
            identifier="ERR-001",
            component="test",
            severity=Severity.ERROR,
            description="Error.",
            recommendation="Fix.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(
            status=PlatformHealth.UNHEALTHY,
            report=report,
        )
        assert health.status == PlatformHealth.UNHEALTHY

    def test_degraded_status(self) -> None:
        issue = ValidationIssue(
            identifier="WRN-001",
            component="test",
            severity=Severity.WARNING,
            description="Warning.",
            recommendation="Check.",
        )
        report = ValidationReport(issues=(issue,))
        health = PlatformHealth(
            status=PlatformHealth.DEGRADED,
            report=report,
        )
        assert health.status == PlatformHealth.DEGRADED

    def test_health_has_timestamp(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        assert isinstance(health.timestamp, datetime)
        assert health.timestamp.tzinfo == timezone.utc

    def test_health_constants(self) -> None:
        assert PlatformHealth.HEALTHY == "HEALTHY"
        assert PlatformHealth.UNHEALTHY == "UNHEALTHY"
        assert PlatformHealth.DEGRADED == "DEGRADED"

    def test_health_is_immutable(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        with pytest.raises(Exception):
            health.status = "NEW"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# HealthReport tests
# ---------------------------------------------------------------------------


class TestHealthReport:
    """Tests for HealthReport dataclass."""

    def test_health_report_creation(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        health_report = HealthReport(
            health=health,
            summary="Platform HEALTHY: All checks passed.",
            details="Platform Health: HEALTHY\nIssues: 0",
        )
        assert health_report.health is health
        assert health_report.summary == "Platform HEALTHY: All checks passed."
        assert "Platform Health: HEALTHY" in health_report.details

    def test_health_report_str(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        health_report = HealthReport(
            health=health,
            summary="Summary.",
            details="Details.",
        )
        assert str(health_report) == "Details."

    def test_health_report_is_immutable(self) -> None:
        report = ValidationReport()
        health = PlatformHealth(
            status=PlatformHealth.HEALTHY,
            report=report,
        )
        health_report = HealthReport(
            health=health,
            summary="Summary.",
            details="Details.",
        )
        with pytest.raises(Exception):
            health_report.summary = "New"  # type: ignore[assignment]