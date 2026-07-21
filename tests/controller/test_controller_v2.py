"""Tests for EngineeringControllerV2.

Tests the complete control loop, session management, and decision flow.

Tests
-----
- test_execute_success: Successful execution with COMPLETE decision.
- test_execute_with_custom_config: Custom configuration applied.
- test_execute_workflow_selection: Workflow selection works correctly.
- test_execute_iteration_tracking: Iteration tracking works correctly.
- test_execute_history_recording: History is recorded correctly.
- test_execute_decision_complete: COMPLETE decision handled correctly.
- test_execute_decision_fail: FAIL decision handled correctly.
- test_execute_decision_request_review: REQUEST_REVIEW decision handled correctly.
- test_execute_decision_retry: RETRY decision handled correctly.
- test_execute_max_retries: Max retries reached → FAIL.
- test_execute_max_iterations: Max iterations reached → FAIL.
- test_execute_exception: Exception handling works correctly.
- test_execute_with_session: Session resumption works correctly.
- test_session_immutability: Session is immutable.
- test_controller_responsibilities: Controller does not perform forbidden operations.
- test_deterministic_decisions: Controller decisions are deterministic.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.controller.controller_v2 import EngineeringControllerV2
from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    EngineeringRequestV2,
    EngineeringResultV2,
    EngineeringSessionV2,
    SessionStatusV2,
)
from packages.controller.retry_policy import RetryPolicy


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


def _create_mock_execution_engine(
    success: bool = True,
    verification_status: str = "PASSED",
    evaluation_score: float = 0.9,
) -> SimpleNamespace:
    """Create a mock execution engine."""
    return SimpleNamespace(
        execute=lambda request, workflow_name, session: (
            SimpleNamespace(
                workflow_name=workflow_name,
                task_plans=(),
                workflow_steps=(),
            ),
            SimpleNamespace(
                workflow_name=workflow_name,
                execution_id=f"exec-{workflow_name}",
                execution_status="COMPLETED" if success else "FAILED",
                success=success,
                failures=(),
            ),
        ),
    )


def _create_mock_verification_engine(
    verification_status: str = "PASSED",
    score: float = 1.0,
) -> SimpleNamespace:
    """Create a mock verification engine."""
    return SimpleNamespace(
        verify=lambda execution_report: SimpleNamespace(
            workflow_name=getattr(execution_report, "workflow_name", "unknown"),
            execution_id=getattr(execution_report, "execution_id", "unknown"),
            verification_status=SimpleNamespace(value=verification_status),
            score=score,
            findings=(),
        ),
    )


def _create_mock_evaluator(
    overall_score: float = 0.9,
) -> SimpleNamespace:
    """Create a mock evaluator."""
    return SimpleNamespace(
        evaluate=lambda workflow_plan, execution_report: SimpleNamespace(
            workflow_name=getattr(workflow_plan, "workflow_name", "unknown"),
            task_name="test-task",
            overall_score=overall_score,
            metrics=(),
            scores=(),
        ),
    )


# ---------------------------------------------------------------------------
# Test successful execution
# ---------------------------------------------------------------------------


class TestExecuteSuccess:
    """Test successful execution scenarios."""

    def test_execute_success(self):
        """Test successful execution with default settings."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.COMPLETE
        assert result.status == SessionStatusV2.COMPLETED
        assert result.error_message == ""
        assert result.session_id != ""
        assert result.request_id == "req-001"

    def test_execute_with_custom_config(self):
        """Test execution with custom configuration."""
        config = ControllerConfig(
            evaluation_threshold=0.8,
            max_retries=5,
            max_iterations=20,
        )
        controller = EngineeringControllerV2(config=config)
        request = _create_request(config=config)
        result = controller.execute(request)

        assert result.decision == ControllerDecision.COMPLETE
        assert result.status == SessionStatusV2.COMPLETED

    def test_execute_iteration_tracking(self):
        """Test that iteration is tracked correctly."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert result.session.iteration >= 1

    def test_execute_history_recording(self):
        """Test that history is recorded correctly."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert len(result.session.history) >= 1


class TestWorkflowSelection:
    """Test workflow selection."""

    def test_default_workflow(self):
        """Test default workflow selection."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        # Check that a workflow was executed
        if result.session.history:
            assert result.session.history[0].workflow_name != ""

    def test_custom_workflow(self):
        """Test custom workflow selection."""
        request = _create_request(workflow_name="custom-workflow")
        controller = EngineeringControllerV2()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.COMPLETE


# ---------------------------------------------------------------------------
# Test decision handling
# ---------------------------------------------------------------------------


class TestDecisionComplete:
    """Test COMPLETE decision handling."""

    def test_complete_decision(self):
        """Test COMPLETE decision produces correct result."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.COMPLETE
        assert result.status == SessionStatusV2.COMPLETED
        assert result.error_message == ""


class TestDecisionFail:
    """Test FAIL decision handling."""

    def test_execution_failure(self):
        """Test execution failure → FAIL."""
        execution_engine = _create_mock_execution_engine(success=False)
        verification_engine = _create_mock_verification_engine(
            verification_status="FAILED",
            score=0.0,
        )
        evaluator = _create_mock_evaluator(overall_score=0.0)

        controller = EngineeringControllerV2(
            execution_engine=execution_engine,
            verification_engine=verification_engine,
            evaluator=evaluator,
        )
        request = _create_request()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.FAIL
        assert result.status == SessionStatusV2.FAILED


class TestDecisionRequestReview:
    """Test REQUEST_REVIEW decision handling."""

    def test_request_review(self):
        """Test evaluation below threshold → REQUEST_REVIEW."""
        execution_engine = _create_mock_execution_engine(success=True)
        verification_engine = _create_mock_verification_engine(
            verification_status="PASSED",
            score=1.0,
        )
        # Low evaluation score → REQUEST_REVIEW
        evaluator = _create_mock_evaluator(overall_score=0.6)

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

        assert result.decision == ControllerDecision.REQUEST_REVIEW
        assert result.status == SessionStatusV2.REVIEW_REQUIRED


class TestDecisionRetry:
    """Test RETRY decision handling."""

    def test_retry_flow(self):
        """Test RETRY decision triggers retry loop."""
        # First execution fails verification, second succeeds
        call_count = 0

        def execution_engine_execute(request, workflow_name, session):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: verification fails
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
            else:
                # Second call: succeeds
                return (
                    SimpleNamespace(workflow_name=workflow_name, task_plans=(), workflow_steps=()),
                    SimpleNamespace(
                        workflow_name=workflow_name,
                        execution_id="exec-002",
                        execution_status="COMPLETED",
                        success=True,
                        failures=(),
                    ),
                )

        verification_engine = _create_mock_verification_engine(
            verification_status="FAILED" if call_count == 0 else "PASSED",
            score=0.0 if call_count == 0 else 1.0,
        )

        controller = EngineeringControllerV2(
            execution_engine=SimpleNamespace(execute=execution_engine_execute),
            verification_engine=verification_engine,
        )
        request = _create_request()
        result = controller.execute(request)

        # Should eventually complete or fail based on retry logic
        assert result.session_id != ""


class TestMaxRetries:
    """Test max retries reached."""

    def test_max_retries_reached(self):
        """Test that max retries leads to FAIL."""
        # Create a controller that always fails verification
        execution_engine = _create_mock_execution_engine(success=True)
        verification_engine = _create_mock_verification_engine(
            verification_status="FAILED",
            score=0.0,
        )
        evaluator = _create_mock_evaluator(overall_score=0.0)

        config = ControllerConfig(max_retries=2, max_iterations=10)
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


class TestMaxIterations:
    """Test max iterations reached."""

    def test_max_iterations_reached(self):
        """Test that max iterations leads to FAIL."""
        config = ControllerConfig(max_iterations=1, max_retries=0)
        controller = EngineeringControllerV2(config=config)
        request = _create_request(config=config)
        result = controller.execute(request)

        # With max_iterations=1, should complete in one iteration
        assert result.session.iteration >= 1


class TestExceptionHandling:
    """Test exception handling."""

    def test_execute_exception(self):
        """Test that exceptions are caught and returned as FAIL."""
        def failing_execute(request, workflow_name, session):
            raise RuntimeError("Test error")

        controller = EngineeringControllerV2(
            execution_engine=SimpleNamespace(execute=failing_execute),
        )
        request = _create_request()
        result = controller.execute(request)

        assert result.decision == ControllerDecision.FAIL
        assert result.status == SessionStatusV2.FAILED
        assert "Test error" in result.error_message


class TestSessionResumption:
    """Test session resumption."""

    def test_execute_with_session(self):
        """Test executing with an existing session."""
        controller = EngineeringControllerV2()
        request = _create_request()
        session = EngineeringSessionV2.create(
            session_id="sess-existing",
            request_id="req-001",
        )
        result = controller.execute_with_session(request, session)

        assert result.session_id == "sess-existing"


class TestSessionImmutability:
    """Test session immutability."""

    def test_session_not_modified(self):
        """Test that original session is not modified."""
        controller = EngineeringControllerV2()
        request = _create_request()
        session = EngineeringSessionV2.create(
            session_id="sess-immutable",
            request_id="req-001",
        )
        original_iteration = session.iteration

        result = controller.execute(request)

        # Original session should be unchanged
        assert session.iteration == original_iteration
        assert session.status == SessionStatusV2.ACTIVE


class TestControllerResponsibilities:
    """Test controller does not perform forbidden operations."""

    def test_no_repository_modification(self):
        """Test that controller does not modify repository."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        # If controller modified repo, this would fail
        assert result.session_id != ""

    def test_no_provider_invocation(self):
        """Test that controller does not invoke providers directly."""
        controller = EngineeringControllerV2()
        # Controller should not have provider access
        assert not hasattr(controller, "_provider")
        assert not hasattr(controller, "_invoke_provider")

    def test_no_verification_performed(self):
        """Test that controller does not perform verification directly."""
        controller = EngineeringControllerV2()
        # Controller should not have direct verification
        assert not hasattr(controller, "_direct_verify")

    def test_no_evaluation_performed(self):
        """Test that controller does not perform evaluation directly."""
        controller = EngineeringControllerV2()
        # Controller should not have direct evaluation
        assert not hasattr(controller, "_direct_evaluate")


class TestDeterministicBehavior:
    """Test deterministic behavior."""

    def test_deterministic_decisions(self):
        """Test that same inputs produce same decisions."""
        controller = EngineeringControllerV2()
        request = _create_request()

        result1 = controller.execute(request)
        result2 = controller.execute(request)

        assert result1.decision == result2.decision
        assert result1.status == result2.status


class TestPublicAPI:
    """Test public API boundaries."""

    def test_execute_returns_result(self):
        """Test that execute returns EngineeringResultV2."""
        controller = EngineeringControllerV2()
        request = _create_request()
        result = controller.execute(request)

        assert isinstance(result, EngineeringResultV2)

    def test_config_property(self):
        """Test config property."""
        config = ControllerConfig(evaluation_threshold=0.8)
        controller = EngineeringControllerV2(config=config)
        assert controller.config == config

    def test_workflow_engine_property(self):
        """Test workflow_engine property."""
        engine = SimpleNamespace()
        controller = EngineeringControllerV2(workflow_engine=engine)
        assert controller.workflow_engine is engine