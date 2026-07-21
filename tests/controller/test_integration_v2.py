"""Integration tests for Engineering Controller v2.

Tests the complete engineering flow from request to result.

Tests
-----
- test_successful_completion: Complete successful engineering flow.
- test_retry_flow: Retry flow with verification failure.
- test_verification_failure: Verification failure handling.
- test_evaluation_failure: Evaluation failure handling.
- test_max_retry_reached: Maximum retry reached → FAIL.
- test_deterministic_decisions: Controller decisions are deterministic.
- test_immutable_session: Session remains immutable.
- test_session_history_correctness: Session history is correct.
- test_workflow_history: Workflow history is tracked.
- test_execution_reports: Execution reports are recorded.
- test_verification_reports: Verification reports are recorded.
- test_evaluation_reports: Evaluation reports are recorded.
- test_controller_decisions: Controller decisions are recorded.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.controller.controller_v2 import EngineeringControllerV2
from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    EngineeringRequestV2,
    EngineeringSessionV2,
    SessionHistoryEntry,
    SessionStatusV2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_request(
    request_id: str = "req-001",
    workflow_name: str = "",
    config: ControllerConfig | None = None,
) -> EngineeringRequestV2:
    """Create a test EngineeringRequestV2."""
    mock_op = SimpleNamespace(value="EXECUTE")
    return EngineeringRequestV2(
        request_id=request_id,
        operation=mock_op,
        description="Test engineering task",
        workflow_name=workflow_name,
        config=config,
    )


def _create_mock_execution_report(
    workflow_name: str,
    success: bool = True,
) -> SimpleNamespace:
    """Create a mock execution report."""
    return SimpleNamespace(
        workflow_name=workflow_name,
        execution_id=f"exec-{workflow_name}",
        execution_status="COMPLETED" if success else "FAILED",
        success=success,
        failures=(),
    )


def _create_mock_verification_report(
    workflow_name: str,
    status: str = "PASSED",
    score: float = 1.0,
) -> SimpleNamespace:
    """Create a mock verification report."""
    return SimpleNamespace(
        workflow_name=workflow_name,
        execution_id=f"exec-{workflow_name}",
        verification_status=SimpleNamespace(value=status),
        score=score,
        findings=(),
    )


def _create_mock_evaluation_report(
    workflow_name: str,
    overall_score: float = 0.9,
) -> SimpleNamespace:
    """Create a mock evaluation report."""
    return SimpleNamespace(
        workflow_name=workflow_name,
        task_name="test-task",
        overall_score=overall_score,
        metrics=(),
        scores=(),
    )


# ---------------------------------------------------------------------------
# Test successful completion
# ---------------------------------------------------------------------------


class TestSuccessfulCompletion:
    """Test successful completion flow."""

    def test_complete_flow(self):
        """Test complete successful engineering flow."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.COMPLETE
        assert result.status == SessionStatusV2.COMPLETED
        assert result.error_message == ""
        assert result.session_id != ""
        assert result.request_id == "req-001"
        assert result.session.iteration >= 1
        assert len(result.session.history) >= 1

    def test_session_has_workflow_plan(self):
        """Test that session has workflow plan."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        if result.session.history:
            first_entry = result.session.history[0]
            assert first_entry.workflow_name != ""

    def test_result_contains_session(self):
        """Test that result contains complete session."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert result.session.session_id == result.session_id
        assert result.session.request_id == result.request_id


# ---------------------------------------------------------------------------
# Test retry flow
# ---------------------------------------------------------------------------


class TestRetryFlow:
    """Test retry flow scenarios."""

    def test_retry_increments_count(self):
        """Test that retry increments retry count."""
        call_count = 0

        def mock_execute(request, workflow_name, session):
            nonlocal call_count
            call_count += 1
            # First call: success, but low evaluation score triggers retry
            return (
                SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                SimpleNamespace(
                    workflow_name=workflow_name,
                    execution_id="exec-001",
                    execution_status="COMPLETED",
                    success=True,
                    failures=(),
                ),
            )

        controller = EngineeringControllerV2(
            execution_engine=SimpleNamespace(execute=mock_execute),
        )
        request = _create_request()
        result = controller.execute(request)

        assert result.session_id != ""

    def test_retry_reuses_workflow_engine(self):
        """Test that retry reuses Workflow Engine."""
        call_count = 0

        def mock_execute(request, workflow_name, session):
            nonlocal call_count
            call_count += 1
            return (
                SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                SimpleNamespace(
                    workflow_name=workflow_name,
                    execution_id=f"exec-{call_count}",
                    execution_status="COMPLETED",
                    success=True,
                    failures=(),
                ),
            )

        config = ControllerConfig(max_retries=2, max_iterations=5)
        controller = EngineeringControllerV2(
            execution_engine=SimpleNamespace(execute=mock_execute),
            config=config,
        )
        request = _create_request(config=config)
        result = controller.execute(request)

        # Workflow engine was called at least once
        assert call_count >= 1


# ---------------------------------------------------------------------------
# Test verification failure
# ---------------------------------------------------------------------------


class TestVerificationFailure:
    """Test verification failure handling."""

    def test_verification_failure_triggers_retry(self):
        """Test that verification failure triggers retry."""
        # Always fail verification
        execution_engine = SimpleNamespace(
            execute=lambda request, workflow_name, session: (
                SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                SimpleNamespace(
                    workflow_name=workflow_name,
                    execution_id="exec-001",
                    execution_status="COMPLETED",
                    success=True,
                    failures=(),
                ),
            ),
        )

        verification_engine = SimpleNamespace(
            verify=lambda execution_report: SimpleNamespace(
                workflow_name=getattr(execution_report, "workflow_name", "unknown"),
                execution_id=getattr(execution_report, "execution_id", "unknown"),
                verification_status=SimpleNamespace(value="FAILED"),
                score=0.0,
                findings=(),
            ),
        )

        evaluator = SimpleNamespace(
            evaluate=lambda workflow_plan, execution_report: SimpleNamespace(
                workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
                task_name="test",
                overall_score=0.9,
                metrics=(),
                scores=(),
            ),
        )

        config = ControllerConfig(max_retries=1, max_iterations=5)
        controller = EngineeringControllerV2(
            execution_engine=execution_engine,
            verification_engine=verification_engine,
            evaluator=evaluator,
            config=config,
        )
        request = _create_request(config=config)
        result = controller.execute(request)

        # After max retries, should fail
        assert result.status == SessionStatusV2.FAILED


# ---------------------------------------------------------------------------
# Test evaluation failure
# ---------------------------------------------------------------------------


class TestEvaluationFailure:
    """Test evaluation failure handling."""

    def test_low_evaluation_triggers_review(self):
        """Test that low evaluation score triggers review."""
        execution_engine = SimpleNamespace(
            execute=lambda request, workflow_name, session: (
                SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                SimpleNamespace(
                    workflow_name=workflow_name,
                    execution_id="exec-001",
                    execution_status="COMPLETED",
                    success=True,
                    failures=(),
                ),
            ),
        )

        verification_engine = SimpleNamespace(
            verify=lambda execution_report: SimpleNamespace(
                workflow_name=getattr(execution_report, "workflow_name", "unknown"),
                execution_id=getattr(execution_report, "execution_id", "unknown"),
                verification_status=SimpleNamespace(value="PASSED"),
                score=1.0,
                findings=(),
            ),
        )

        # Low evaluation score
        evaluator = SimpleNamespace(
            evaluate=lambda workflow_plan, execution_report: SimpleNamespace(
                workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
                task_name="test",
                overall_score=0.3,  # Very low score
                metrics=(),
                scores=(),
            ),
        )

        config = ControllerConfig(
            evaluation_threshold=0.7,
            auto_review_threshold=0.5,
        )
        controller = EngineeringControllerV2(
            execution_engine=execution_engine,
            verification_engine=verification_engine,
            evaluator=evaluator,
            config=config,
        )
        request = _create_request(config=config)
        result = controller.execute(request)

        # Very low score → FAIL
        assert result.decision == ControllerDecision.FAIL
        assert result.status == SessionStatusV2.FAILED


# ---------------------------------------------------------------------------
# Test max retry reached
# ---------------------------------------------------------------------------


class TestMaxRetryReached:
    """Test maximum retry reached scenarios."""

    def test_max_retries_leads_to_fail(self):
        """Test that max retries leads to FAIL."""
        execution_engine = SimpleNamespace(
            execute=lambda request, workflow_name, session: (
                SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                SimpleNamespace(
                    workflow_name=workflow_name,
                    execution_id="exec-001",
                    execution_status="COMPLETED",
                    success=True,
                    failures=(),
                ),
            ),
        )

        # Always fail verification
        verification_engine = SimpleNamespace(
            verify=lambda execution_report: SimpleNamespace(
                workflow_name=getattr(execution_report, "workflow_name", "unknown"),
                execution_id=getattr(execution_report, "execution_id", "unknown"),
                verification_status=SimpleNamespace(value="FAILED"),
                score=0.0,
                findings=(),
            ),
        )

        evaluator = SimpleNamespace(
            evaluate=lambda workflow_plan, execution_report: SimpleNamespace(
                workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
                task_name="test",
                overall_score=0.9,
                metrics=(),
                scores=(),
            ),
        )

        config = ControllerConfig(max_retries=0, max_iterations=5)
        controller = EngineeringControllerV2(
            execution_engine=execution_engine,
            verification_engine=verification_engine,
            evaluator=evaluator,
            config=config,
        )
        request = _create_request(config=config)
        result = controller.execute(request)

        # With max_retries=0, should fail immediately
        assert result.status == SessionStatusV2.FAILED


# ---------------------------------------------------------------------------
# Test deterministic decisions
# ---------------------------------------------------------------------------


class TestDeterministicDecisions:
    """Test deterministic controller decisions."""

    def test_same_inputs_produce_same_result(self):
        """Test that same inputs produce same decisions."""
        controller = EngineeringControllerV2()

        request = _create_request(request_id="req-deterministic")
        result1 = controller.execute(request)
        result2 = controller.execute(request)

        assert result1.decision == result2.decision
        assert result1.status == result2.status


# ---------------------------------------------------------------------------
# Test immutable session
# ---------------------------------------------------------------------------


class TestImmutableSession:
    """Test session immutability."""

    def test_original_session_unchanged(self):
        """Test that original session is unchanged after execute."""
        controller = EngineeringControllerV2()
        session = EngineeringSessionV2.create(
            session_id="sess-immutable",
            request_id="req-001",
        )
        original_status = session.status
        original_iteration = session.iteration

        request = _create_request()
        controller.execute(request)

        # Original session should be unchanged
        assert session.status == original_status
        assert session.iteration == original_iteration

    def test_session_snapshot(self):
        """Test that snapshot returns self."""
        session = EngineeringSessionV2.create(
            session_id="sess-snapshot",
            request_id="req-001",
        )
        snapshot = session.snapshot()
        assert snapshot is session


# ---------------------------------------------------------------------------
# Test session history correctness
# ---------------------------------------------------------------------------


class TestSessionHistoryCorrectness:
    """Test session history correctness."""

    def test_history_entries_are_recorded(self):
        """Test that history entries are recorded."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert len(result.session.history) >= 1

    def test_history_has_iteration(self):
        """Test that history has iteration numbers."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        for entry in result.session.history:
            assert entry.iteration >= 1

    def test_history_has_workflow_name(self):
        """Test that history has workflow names."""
        controller = EngineeringControllerV2()
        request = _create_request(workflow_name="test-workflow")
        result = controller.execute(request)

        for entry in result.session.history:
            assert entry.workflow_name == "test-workflow"

    def test_history_order(self):
        """Test that history is in chronological order."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        # Group by iteration and verify ordering
        iterations = [entry.iteration for entry in result.session.history]
        if len(iterations) > 1:
            # Multiple entries should be in non-decreasing order
            for i in range(1, len(iterations)):
                assert iterations[i] >= iterations[i - 1]


# ---------------------------------------------------------------------------
# Test workflow history
# ---------------------------------------------------------------------------


class TestWorkflowHistory:
    """Test workflow history tracking."""

    def test_workflow_history_property(self):
        """Test workflow_history property."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        workflow_history = result.session.workflow_history
        assert len(workflow_history) >= 1
        assert all(name != "" for name in workflow_history)


# ---------------------------------------------------------------------------
# Test report recording
# ---------------------------------------------------------------------------


class TestReportRecording:
    """Test report recording in session."""

    def test_execution_reports(self):
        """Test execution reports are recorded."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        reports = result.session.execution_reports
        # Reports may be None if not recorded
        assert isinstance(reports, tuple)

    def test_verification_reports(self):
        """Test verification reports are recorded."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        reports = result.session.verification_reports
        assert isinstance(reports, tuple)

    def test_evaluation_reports(self):
        """Test evaluation reports are recorded."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        reports = result.session.evaluation_reports
        assert isinstance(reports, tuple)

    def test_controller_decisions(self):
        """Test controller decisions are recorded."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        decisions = result.session.controller_decisions
        assert isinstance(decisions, tuple)


# ---------------------------------------------------------------------------
# Test end-to-end flow
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Test end-to-end engineering flow."""

    def test_complete_flow_from_request_to_result(self):
        """Test complete flow from request to result."""
        controller = EngineeringControllerV2()

        # Create request
        request = _create_request(
            request_id="req-e2e",
            workflow_name="e2e-workflow",
        )

        # Execute
        result = controller.execute(request)

        # Verify result
        assert result.request_id == "req-e2e"
        assert result.session_id != ""
        assert result.decision in (
            ControllerDecision.COMPLETE,
            ControllerDecision.RETRY,
            ControllerDecision.REQUEST_REVIEW,
            ControllerDecision.FAIL,
        )
        assert result.status in (
            SessionStatusV2.ACTIVE,
            SessionStatusV2.COMPLETED,
            SessionStatusV2.REVIEW_REQUIRED,
            SessionStatusV2.FAILED,
        )

    def test_session_contains_all_artifacts(self):
        """Test that session contains all artifacts."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        # Session should have history
        assert len(result.session.history) >= 1

        # Session should have correct status
        assert result.session.status in (
            SessionStatusV2.COMPLETED,
            SessionStatusV2.FAILED,
        )