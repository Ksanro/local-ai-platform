"""Tests for ControllerDecisionMaker.

Tests all decision rules, edge cases, and deterministic behavior.

Tests
-----
- test_execution_failed: Execution failure → FAIL
- test_verification_failed_retry: Verification failed with retries → RETRY
- test_verification_failed_no_retry: Verification failed, no retries → FAIL
- test_evaluation_above_threshold: Evaluation above threshold → COMPLETE
- test_evaluation_below_review_threshold: Evaluation below review threshold → FAIL
- test_evaluation_between_thresholds: Evaluation between thresholds → REQUEST_REVIEW
- test_no_evaluation_report: No evaluation report → COMPLETE (if verification passed)
- test_deterministic: Same inputs always produce same decision
- test_execution_report_none: None execution report handled
- test_verification_report_none: None verification report handled
- test_evaluation_report_none: None evaluation report handled
- test_custom_thresholds: Custom thresholds work correctly
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    ControllerReport,
)
from packages.controller.decision import ControllerDecisionMaker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution_report(
    success: bool = True,
    execution_status: str = "COMPLETED",
) -> SimpleNamespace:
    """Create a mock execution report."""
    return SimpleNamespace(
        workflow_name="test-workflow",
        execution_id="exec-001",
        success=success,
        execution_status=SimpleNamespace(value=execution_status),
        total_duration_ms=1000,
        step_results=(),
        failures=(),
    )


def _make_verification_report(
    status: str = "PASSED",
    score: float = 1.0,
) -> SimpleNamespace:
    """Create a mock verification report."""
    return SimpleNamespace(
        workflow_name="test-workflow",
        execution_id="exec-001",
        verification_status=SimpleNamespace(value=status),
        score=score,
        findings=(),
    )


def _make_evaluation_report(
    overall_score: float = 0.9,
) -> SimpleNamespace:
    """Create a mock evaluation report."""
    return SimpleNamespace(
        workflow_name="test-workflow",
        task_name="test-task",
        overall_score=overall_score,
        metrics=(),
        scores=(),
    )


# ---------------------------------------------------------------------------
# Test execution failure → FAIL
# ---------------------------------------------------------------------------


class TestExecutionFailure:
    """Test execution failure → FAIL decision."""

    def test_execution_failed(self):
        """Test that execution failure produces FAIL."""
        config = ControllerConfig()
        execution_report = _make_execution_report(success=False)
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.FAIL
        assert "Execution failed" in report.reason

    def test_execution_none_is_not_failure(self):
        """Test that None execution report is not considered failure."""
        config = ControllerConfig()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=None,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        # None execution report → not failure → proceed to verification
        assert report.decision == ControllerDecision.COMPLETE


# ---------------------------------------------------------------------------
# Test verification failed → RETRY or FAIL
# ---------------------------------------------------------------------------


class TestVerificationFailed:
    """Test verification failure → RETRY or FAIL decision."""

    def test_verification_failed_with_retries(self):
        """Test verification failed with retries available → RETRY."""
        config = ControllerConfig(max_retries=3)
        execution_report = _make_execution_report()
        verification_report = _make_verification_report(status="FAILED")
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=1,
            iteration=2,
        )

        assert report.decision == ControllerDecision.RETRY
        assert "retry available" in report.reason

    def test_verification_failed_no_retries(self):
        """Test verification failed with no retries → FAIL."""
        config = ControllerConfig(max_retries=3)
        execution_report = _make_execution_report()
        verification_report = _make_verification_report(status="FAILED")
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=3,
            iteration=4,
        )

        assert report.decision == ControllerDecision.FAIL
        assert "max retries exhausted" in report.reason

    def test_verification_none_is_not_failure(self):
        """Test that None verification report is not considered failure."""
        config = ControllerConfig()
        execution_report = _make_execution_report()
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=None,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        # No verification failure → proceed to evaluation check
        assert report.decision == ControllerDecision.COMPLETE


# ---------------------------------------------------------------------------
# Test evaluation score → COMPLETE, REQUEST_REVIEW, or FAIL
# ---------------------------------------------------------------------------


class TestEvaluationScore:
    """Test evaluation score based decisions."""

    def test_above_threshold_complete(self):
        """Test evaluation above threshold → COMPLETE."""
        config = ControllerConfig(evaluation_threshold=0.7)
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.COMPLETE
        assert "0.900 meets threshold" in report.reason

    def test_below_threshold_request_review(self):
        """Test evaluation below threshold but above review threshold → REQUEST_REVIEW."""
        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.6)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.REQUEST_REVIEW
        assert "below threshold" in report.reason

    def test_below_review_threshold_fail(self):
        """Test evaluation below review threshold → FAIL."""
        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.3)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.FAIL
        assert "below review threshold" in report.reason

    def test_no_evaluation_report_complete(self):
        """Test no evaluation report with passing verification → COMPLETE."""
        config = ControllerConfig()
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=None,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.COMPLETE


# ---------------------------------------------------------------------------
# Test edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exact_threshold(self):
        """Test evaluation exactly at threshold → COMPLETE."""
        config = ControllerConfig(evaluation_threshold=0.7)
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.7)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.COMPLETE

    def test_exact_review_threshold(self):
        """Test evaluation exactly at review threshold → REQUEST_REVIEW."""
        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.5)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.REQUEST_REVIEW

    def test_zero_evaluation_score(self):
        """Test zero evaluation score → FAIL."""
        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.0)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.FAIL

    def test_max_evaluation_score(self):
        """Test maximum evaluation score → COMPLETE."""
        config = ControllerConfig(evaluation_threshold=0.7)
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=1.0)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.COMPLETE


# ---------------------------------------------------------------------------
# Test deterministic behavior
# ---------------------------------------------------------------------------


class TestDeterministicBehavior:
    """Test that decisions are deterministic."""

    def test_same_inputs_same_output(self):
        """Test that same inputs always produce the same decision."""
        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report(overall_score=0.6)

        report1 = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        report2 = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report1.decision == report2.decision
        assert report1.reason == report2.reason
        assert report1.evaluation_score == report2.evaluation_score


# ---------------------------------------------------------------------------
# Test report structure
# ---------------------------------------------------------------------------


class TestReportStructure:
    """Test that ControllerReport has correct structure."""

    def test_report_iteration(self):
        """Test that iteration is recorded."""
        config = ControllerConfig()
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report()

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=5,
        )

        assert report.iteration == 5

    def test_report_retry_count(self):
        """Test that retry_count is recorded."""
        config = ControllerConfig()
        execution_report = _make_execution_report()
        verification_report = _make_verification_report()
        evaluation_report = _make_evaluation_report()

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=2,
            iteration=3,
        )

        assert report.retry_count == 2

    def test_report_scores(self):
        """Test that scores are recorded in report."""
        config = ControllerConfig()
        execution_report = _make_execution_report()
        verification_report = _make_verification_report(score=0.8)
        evaluation_report = _make_evaluation_report(overall_score=0.9)

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.evaluation_score == 0.9
        assert report.verification_score == 0.8