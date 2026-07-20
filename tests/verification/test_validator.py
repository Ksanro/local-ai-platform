"""Tests for verification report validation.

Verifies:
- Duplicate findings detection
- Invalid score detection
- Invalid status detection
- Invalid statistics detection
- Inconsistent metadata detection
- Empty verification
- Coverage >95%

"""

from __future__ import annotations

import pytest

from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)
from packages.verification.validator import VerificationReportValidator


# ---------------------------------------------------------------------------
# Helper: Create a valid report
# ---------------------------------------------------------------------------


def _create_valid_report(
    findings: tuple[VerificationFinding, ...] = (),
    score: float = 1.0,
    status: VerificationStatus = VerificationStatus.PASSED,
    statistics: VerificationStatistics | None = None,
    metadata: dict[str, object] | None = None,
) -> VerificationReport:
    """Create a valid VerificationReport for testing."""
    if statistics is None:
        statistics = VerificationStatistics(
            executed_rules=len(findings),
            passed_rules=sum(
                1 for f in findings if f.severity == VerificationSeverity.INFO
            ),
            failed_rules=sum(
                1
                for f in findings
                if f.severity in (VerificationSeverity.HIGH, VerificationSeverity.CRITICAL)
            ),
            warnings=sum(
                1
                for f in findings
                if f.severity in (VerificationSeverity.LOW, VerificationSeverity.MEDIUM)
            ),
            duration_ms=100,
        )
    return VerificationReport(
        workflow_name="test",
        execution_id="exec-1",
        verification_status=status,
        findings=findings,
        statistics=statistics,
        score=score,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Test: Valid Report
# ---------------------------------------------------------------------------


class TestValidReport:
    """Tests for valid report validation."""

    def test_valid_report_passes(self) -> None:
        """A valid report should pass validation."""
        report = _create_valid_report()
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True
        assert errors == []

    def test_valid_report_with_findings(self) -> None:
        """A valid report with findings should pass."""
        finding = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        report = _create_valid_report(findings=(finding,))
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True
        assert errors == []

    def test_none_report_fails(self) -> None:
        """None report should fail validation."""
        is_valid, errors = VerificationReportValidator.validate(None)
        assert is_valid is False
        assert "Report cannot be None" in errors[0]


# ---------------------------------------------------------------------------
# Test: Duplicate Findings
# ---------------------------------------------------------------------------


class TestDuplicateFindings:
    """Tests for duplicate findings detection."""

    def test_no_duplicate_findings(self) -> None:
        """No duplicate findings should pass."""
        finding1 = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 1",
            description="Test 1.",
            evidence="Test 1.",
        )
        finding2 = VerificationFinding(
            id="test-002",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 2",
            description="Test 2.",
            evidence="Test 2.",
        )
        report = _create_valid_report(findings=(finding1, finding2))
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_duplicate_findings_detected(self) -> None:
        """Duplicate findings should be detected."""
        finding1 = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 1",
            description="Test 1.",
            evidence="Test 1.",
        )
        finding2 = VerificationFinding(
            id="test-001",  # Same ID
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 2",
            description="Test 2.",
            evidence="Test 2.",
        )
        report = _create_valid_report(findings=(finding1, finding2))
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Duplicate finding ID" in e for e in errors)

    def test_multiple_duplicate_findings(self) -> None:
        """Multiple duplicate findings should all be detected."""
        finding1 = VerificationFinding(
            id="test-001",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 1",
            description="Test 1.",
            evidence="Test 1.",
        )
        finding2 = VerificationFinding(
            id="test-001",  # Same ID
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 2",
            description="Test 2.",
            evidence="Test 2.",
        )
        finding3 = VerificationFinding(
            id="test-001",  # Same ID
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 3",
            description="Test 3.",
            evidence="Test 3.",
        )
        report = _create_valid_report(findings=(finding1, finding2, finding3))
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Duplicate finding ID" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: Invalid Score
# ---------------------------------------------------------------------------


class TestInvalidScore:
    """Tests for invalid score detection."""

    def test_valid_score(self) -> None:
        """Valid score should pass."""
        report = _create_valid_report(score=0.5)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_score_zero(self) -> None:
        """Score of 0.0 should be valid."""
        report = _create_valid_report(score=0.0)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_score_one(self) -> None:
        """Score of 1.0 should be valid."""
        report = _create_valid_report(score=1.0)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_score_negative(self) -> None:
        """Negative score should be invalid."""
        report = _create_valid_report(score=-0.1)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("range [0.0, 1.0]" in e for e in errors)

    def test_score_above_one(self) -> None:
        """Score above 1.0 should be invalid."""
        report = _create_valid_report(score=1.5)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("range [0.0, 1.0]" in e for e in errors)

    def test_score_none(self) -> None:
        """None score should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            score=None,  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Score is None" in e for e in errors)

    def test_score_string(self) -> None:
        """String score should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            score="invalid",  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("must be a number" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: Invalid Status
# ---------------------------------------------------------------------------


class TestInvalidStatus:
    """Tests for invalid status detection."""

    def test_valid_status(self) -> None:
        """Valid status should pass."""
        report = _create_valid_report(status=VerificationStatus.PASSED)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_invalid_status_string(self) -> None:
        """Invalid status string should be detected."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status="INVALID_STATUS",  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Invalid verification status" in e for e in errors)

    def test_none_status(self) -> None:
        """None status should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=None,  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Verification status is None" in e for e in errors)

    def test_all_valid_statuses(self) -> None:
        """All valid statuses should pass."""
        for status in VerificationStatus:
            report = _create_valid_report(status=status)
            is_valid, errors = VerificationReportValidator.validate(report)
            assert is_valid is True, f"Status {status.value} should be valid"


# ---------------------------------------------------------------------------
# Test: Invalid Statistics
# ---------------------------------------------------------------------------


class TestInvalidStatistics:
    """Tests for invalid statistics detection."""

    def test_valid_statistics(self) -> None:
        """Valid statistics should pass."""
        stats = VerificationStatistics(
            executed_rules=5,
            passed_rules=3,
            failed_rules=1,
            warnings=1,
            duration_ms=100,
        )
        report = _create_valid_report(statistics=stats)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_none_statistics(self) -> None:
        """None statistics should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            statistics=None,  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Statistics is None" in e for e in errors)

    def test_negative_executed_rules(self) -> None:
        """Negative executed_rules should be invalid."""
        stats = VerificationStatistics(
            executed_rules=-1,
            passed_rules=0,
            failed_rules=0,
            warnings=0,
            duration_ms=0,
        )
        report = _create_valid_report(statistics=stats)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("executed_rules must be >= 0" in e for e in errors)

    def test_mismatched_statistics(self) -> None:
        """Mismatched statistics should be detected."""
        stats = VerificationStatistics(
            executed_rules=10,
            passed_rules=3,
            failed_rules=2,
            warnings=1,  # 3 + 2 + 1 = 6 != 10
            duration_ms=100,
        )
        report = _create_valid_report(statistics=stats)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("executed_rules" in e for e in errors)

    def test_negative_duration(self) -> None:
        """Negative duration_ms should be invalid."""
        stats = VerificationStatistics(
            executed_rules=1,
            passed_rules=1,
            failed_rules=0,
            warnings=0,
            duration_ms=-1,
        )
        report = _create_valid_report(statistics=stats)
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("duration_ms must be >= 0" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: Inconsistent Metadata
# ---------------------------------------------------------------------------


class TestInconsistentMetadata:
    """Tests for inconsistent metadata detection."""

    def test_valid_dict_metadata(self) -> None:
        """Dict metadata should pass."""
        report = _create_valid_report(metadata={"key": "value"})
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_none_metadata(self) -> None:
        """None metadata should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            metadata=None,  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Metadata is None" in e for e in errors)

    def test_list_metadata(self) -> None:
        """List metadata should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            metadata=[],  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Metadata must be a dict" in e for e in errors)

    def test_string_metadata(self) -> None:
        """String metadata should be invalid."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status=VerificationStatus.PASSED,
            metadata="invalid",  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert any("Metadata must be a dict" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: Empty Verification
# ---------------------------------------------------------------------------


class TestEmptyVerification:
    """Tests for empty verification scenarios."""

    def test_empty_findings(self) -> None:
        """Empty findings should pass."""
        report = _create_valid_report(findings=())
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True

    def test_empty_findings_no_duplicates(self) -> None:
        """Empty findings should not trigger duplicate detection."""
        report = _create_valid_report(findings=())
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is True
        assert errors == []


# ---------------------------------------------------------------------------
# Test: Multiple Errors
# ---------------------------------------------------------------------------


class TestMultipleErrors:
    """Tests for multiple error detection."""

    def test_multiple_errors_detected(self) -> None:
        """Multiple errors should all be detected."""
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status="INVALID",  # Invalid status
            score=2.0,  # Invalid score
            statistics=None,  # type: ignore  # None statistics
            metadata=[],  # type: ignore  # Invalid metadata
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert len(errors) >= 3  # At least 3 errors

    def test_all_validations_run(self) -> None:
        """All validation rules should run even if some fail."""
        finding1 = VerificationFinding(
            id="dup",
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test",
            description="Test.",
            evidence="Test.",
        )
        finding2 = VerificationFinding(
            id="dup",  # Duplicate
            category="test",
            severity=VerificationSeverity.INFO,
            title="Test 2",
            description="Test 2.",
            evidence="Test 2.",
        )
        stats = VerificationStatistics(
            executed_rules=-1,  # Negative
            passed_rules=0,
            failed_rules=0,
            warnings=0,
            duration_ms=-1,  # Negative
        )
        report = VerificationReport(
            workflow_name="test",
            execution_id="exec-1",
            verification_status="INVALID",
            findings=(finding1, finding2),
            statistics=stats,
            score=2.0,
            metadata=[],  # type: ignore
        )
        is_valid, errors = VerificationReportValidator.validate(report)
        assert is_valid is False
        assert len(errors) >= 5  # Multiple errors expected