"""Tests for verification model definitions.

Verifies:
- Immutability (frozen=True, slots=True)
- Default values
- Construction with all fields
- Deterministic output
- Coverage >95%

"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)


# ---------------------------------------------------------------------------
# Test: VerificationStatus
# ---------------------------------------------------------------------------


class TestVerificationStatus:
    """Tests for VerificationStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """All VerificationStatus values must exist."""
        assert VerificationStatus.PASSED == "PASSED"
        assert VerificationStatus.FAILED == "FAILED"
        assert VerificationStatus.WARNING == "WARNING"
        assert VerificationStatus.SKIPPED == "SKIPPED"

    def test_status_values_are_uppercase(self) -> None:
        """All VerificationStatus values must be uppercase."""
        for status in VerificationStatus:
            assert status.value.isupper()

    def test_status_from_string(self) -> None:
        """VerificationStatus must be constructible from string."""
        assert VerificationStatus("PASSED") == VerificationStatus.PASSED
        assert VerificationStatus("FAILED") == VerificationStatus.FAILED
        assert VerificationStatus("WARNING") == VerificationStatus.WARNING
        assert VerificationStatus("SKIPPED") == VerificationStatus.SKIPPED

    def test_status_iteration(self) -> None:
        """VerificationStatus must be iterable."""
        statuses = list(VerificationStatus)
        assert len(statuses) == 4


# ---------------------------------------------------------------------------
# Test: VerificationSeverity
# ---------------------------------------------------------------------------


class TestVerificationSeverity:
    """Tests for VerificationSeverity enum."""

    def test_all_severities_exist(self) -> None:
        """All VerificationSeverity values must exist."""
        assert VerificationSeverity.INFO == "INFO"
        assert VerificationSeverity.LOW == "LOW"
        assert VerificationSeverity.MEDIUM == "MEDIUM"
        assert VerificationSeverity.HIGH == "HIGH"
        assert VerificationSeverity.CRITICAL == "CRITICAL"

    def test_severity_values_are_uppercase(self) -> None:
        """All VerificationSeverity values must be uppercase."""
        for severity in VerificationSeverity:
            assert severity.value.isupper()

    def test_severity_from_string(self) -> None:
        """VerificationSeverity must be constructible from string."""
        assert VerificationSeverity("INFO") == VerificationSeverity.INFO
        assert VerificationSeverity("LOW") == VerificationSeverity.LOW
        assert VerificationSeverity("MEDIUM") == VerificationSeverity.MEDIUM
        assert VerificationSeverity("HIGH") == VerificationSeverity.HIGH
        assert VerificationSeverity("CRITICAL") == VerificationSeverity.CRITICAL

    def test_severity_iteration(self) -> None:
        """VerificationSeverity must be iterable."""
        severities = list(VerificationSeverity)
        assert len(severities) == 5


# ---------------------------------------------------------------------------
# Test: VerificationFinding Immutability
# ---------------------------------------------------------------------------


class TestVerificationFindingImmutability:
    """Tests for VerificationFinding immutability."""

    def test_model_is_frozen(self) -> None:
        """VerificationFinding should be immutable."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test finding",
            description="A test finding.",
            evidence="Test evidence.",
        )
        with pytest.raises(FrozenInstanceError):
            finding.id = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """VerificationFinding should use slots."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test finding",
            description="A test finding.",
            evidence="Test evidence.",
        )
        assert not hasattr(finding, "__dict__")

    def test_model_cannot_add_arbitrary_attributes(self) -> None:
        """VerificationFinding should not allow arbitrary attribute addition."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test finding",
            description="A test finding.",
            evidence="Test evidence.",
        )
        with pytest.raises(FrozenInstanceError):
            finding.extra_field = "extra"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: VerificationFinding Construction
# ---------------------------------------------------------------------------


class TestVerificationFindingConstruction:
    """Tests for VerificationFinding construction."""

    def test_minimal_construction(self) -> None:
        """VerificationFinding should accept required fields only."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test finding",
            description="A test finding.",
            evidence="Test evidence.",
        )
        assert finding.id == "test-001"
        assert finding.category == "test"
        assert finding.severity == VerificationSeverity.INFO
        assert finding.title == "Test finding"
        assert finding.description == "A test finding."
        assert finding.evidence == "Test evidence."
        assert finding.recommendation is None

    def test_full_construction(self) -> None:
        """VerificationFinding should accept all fields."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.HIGH,
            title="Critical finding",
            description="A critical issue found.",
            evidence="Evidence of the issue.",
            recommendation="Fix this immediately.",
        )
        assert finding.id == "test-001"
        assert finding.category == "test"
        assert finding.severity == VerificationSeverity.HIGH
        assert finding.title == "Critical finding"
        assert finding.description == "A critical issue found."
        assert finding.evidence == "Evidence of the issue."
        assert finding.recommendation == "Fix this immediately."

    def test_recommendation_defaults_to_none(self) -> None:
        """recommendation should default to None."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        assert finding.recommendation is None
        assert isinstance(finding.recommendation, type(None))


# ---------------------------------------------------------------------------
# Test: VerificationStatistics Immutability
# ---------------------------------------------------------------------------


class TestVerificationStatisticsImmutability:
    """Tests for VerificationStatistics immutability."""

    def test_model_is_frozen(self) -> None:
        """VerificationStatistics should be immutable."""
        stats = VerificationStatistics(
            executed_rules=5,
            passed_rules=4,
            failed_rules=1,
            warnings=0,
            duration_ms=100,
        )
        with pytest.raises(FrozenInstanceError):
            stats.executed_rules = 6  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """VerificationStatistics should use slots."""
        stats = VerificationStatistics(
            executed_rules=5,
            passed_rules=4,
            failed_rules=1,
            warnings=0,
            duration_ms=100,
        )
        assert not hasattr(stats, "__dict__")


# ---------------------------------------------------------------------------
# Test: VerificationStatistics Construction
# ---------------------------------------------------------------------------


class TestVerificationStatisticsConstruction:
    """Tests for VerificationStatistics construction."""

    def test_default_values(self) -> None:
        """VerificationStatistics should have correct default values."""
        stats = VerificationStatistics()
        assert stats.executed_rules == 0
        assert stats.passed_rules == 0
        assert stats.failed_rules == 0
        assert stats.warnings == 0
        assert stats.duration_ms == 0

    def test_full_construction(self) -> None:
        """VerificationStatistics should accept all fields."""
        stats = VerificationStatistics(
            executed_rules=10,
            passed_rules=7,
            failed_rules=2,
            warnings=1,
            duration_ms=250,
        )
        assert stats.executed_rules == 10
        assert stats.passed_rules == 7
        assert stats.failed_rules == 2
        assert stats.warnings == 1
        assert stats.duration_ms == 250


# ---------------------------------------------------------------------------
# Test: VerificationReport Immutability
# ---------------------------------------------------------------------------


class TestVerificationReportImmutability:
    """Tests for VerificationReport immutability."""

    def test_model_is_frozen(self) -> None:
        """VerificationReport should be immutable."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-123",
            verification_status=VerificationStatus.PASSED,
        )
        with pytest.raises(FrozenInstanceError):
            report.workflow_name = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """VerificationReport should use slots."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-123",
            verification_status=VerificationStatus.PASSED,
        )
        assert not hasattr(report, "__dict__")


# ---------------------------------------------------------------------------
# Test: VerificationReport Construction
# ---------------------------------------------------------------------------


class TestVerificationReportConstruction:
    """Tests for VerificationReport construction."""

    def test_minimal_construction(self) -> None:
        """VerificationReport should accept required fields only."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-123",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.workflow_name == "test"
        assert report.execution_id == "exec-123"
        assert report.verification_status == VerificationStatus.PASSED
        assert report.findings == ()
        assert report.statistics.executed_rules == 0
        assert report.score == 0.0
        assert report.metadata == {}

    def test_full_construction(self) -> None:
        """VerificationReport should accept all fields."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        stats = VerificationStatistics(
            executed_rules=1,
            passed_rules=1,
            failed_rules=0,
            warnings=0,
            duration_ms=50,
        )
        report = VerificationReport(
            workflow_name="implement_feature",
            execution_id="exec-456",
            verification_status=VerificationStatus.PASSED,
            findings=(finding,),
            statistics=stats,
            score=0.95,
            metadata={"engine": "SelfVerificationEngine"},
        )
        assert report.workflow_name == "implement_feature"
        assert report.execution_id == "exec-456"
        assert report.verification_status == VerificationStatus.PASSED
        assert len(report.findings) == 1
        assert report.statistics.executed_rules == 1
        assert report.score == 0.95
        assert report.metadata == {"engine": "SelfVerificationEngine"}

    def test_findings_defaults_to_empty_tuple(self) -> None:
        """findings should default to empty tuple."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="test",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.findings == ()
        assert isinstance(report.findings, tuple)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """metadata should default to empty dict."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="test",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.metadata == {}
        assert isinstance(report.metadata, dict)

    def test_score_defaults_to_zero(self) -> None:
        """score should default to 0.0."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="test",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.score == 0.0
        assert isinstance(report.score, float)


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_finding(self) -> None:
        """Same inputs should produce identical VerificationFindings."""
        f1 = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        f2 = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        assert f1.id == f2.id
        assert f1.category == f2.category
        assert f1.severity == f2.severity

    def test_deterministic_report(self) -> None:
        """Same inputs should produce identical VerificationReports."""
        r1 = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
        )
        r2 = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
        )
        assert r1.workflow_name == r2.workflow_name
        assert r1.execution_id == r2.execution_id
        assert r1.verification_status == r2.verification_status


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_id(self) -> None:
        """VerificationFinding should handle empty ID."""
        finding = VerificationFinding(
            id="",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        assert finding.id == ""

    def test_empty_category(self) -> None:
        """VerificationFinding should handle empty category."""
        finding = VerificationFinding(
            id="test-001",
            category="",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        assert finding.category == ""

    def test_empty_title(self) -> None:
        """VerificationFinding should handle empty title."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="",
            description="Test.",
            evidence="Test.",
        )
        assert finding.title == ""

    def test_unicode_description(self) -> None:
        """VerificationFinding should handle unicode in description."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test with unicode: \u4f60\u597d \ud83c\udf0d",
            evidence="Test.",
        )
        assert "\u4f60\u597d" in finding.description

    def test_long_evidence(self) -> None:
        """VerificationFinding should handle long evidence."""
        evidence = "x" * 10000
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence=evidence,
        )
        assert finding.evidence == evidence
        assert len(finding.evidence) == 10000

    def test_all_severities(self) -> None:
        """VerificationFinding should handle all severity types."""
        for severity in VerificationSeverity:
            finding = VerificationFinding(
                id="test-001",
                category="test",
                severity=severity,
                title="Test",
                description="Test.",
                evidence="Test.",
            )
            assert finding.severity == severity

    def test_all_statuses(self) -> None:
        """VerificationReport should handle all status types."""
        for status in VerificationStatus:
            report = VerificationReport(
                workflow_name="test",
                execution_id="test",
                verification_status=status,
            )
            assert report.verification_status == status

    def test_empty_workflow_name(self) -> None:
        """VerificationReport should handle empty workflow name."""
        report = VerificationReport(
            workflow_name="",
            execution_id="test",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.workflow_name == ""

    def test_empty_execution_id(self) -> None:
        """VerificationReport should handle empty execution ID."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="",
            verification_status=VerificationStatus.PASSED,
        )
        assert report.execution_id == ""