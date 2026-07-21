"""Tests for Engineering Controller v2 models.

Tests all model classes, their attributes, defaults, and immutability.

Tests
-----
- test_controller_decision_enum: ControllerDecision has all values.
- test_session_status_v2_enum: SessionStatusV2 has all values.
- test_controller_config_defaults: ControllerConfig has correct defaults.
- test_controller_config_custom: ControllerConfig accepts custom values.
- test_controller_report: ControllerReport is immutable with all fields.
- test_engineering_request_v2: EngineeringRequestV2 has all fields.
- test_session_history_entry: SessionHistoryEntry has all fields.
- test_engineering_session_v2_create: Session creation works correctly.
- test_engineering_session_v2_immutability: Session is immutable.
- test_engineering_session_v2_query_methods: Query methods work correctly.
- test_engineering_result_v2: EngineeringResultV2 has all fields.
- test_result_complete: Complete result structure is correct.
- test_result_fail: Fail result structure is correct.
- test_result_review: Review result structure is correct.
"""

from __future__ import annotations

import pytest

from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    ControllerReport,
    EngineeringRequestV2,
    EngineeringResultV2,
    EngineeringSessionV2,
    SessionHistoryEntry,
    SessionStatusV2,
)


class TestControllerDecisionEnum:
    """Test ControllerDecision enum."""

    def test_complete_value(self):
        """Test COMPLETE enum value."""
        assert ControllerDecision.COMPLETE == "COMPLETE"

    def test_retry_value(self):
        """Test RETRY enum value."""
        assert ControllerDecision.RETRY == "RETRY"

    def test_request_review_value(self):
        """Test REQUEST_REVIEW enum value."""
        assert ControllerDecision.REQUEST_REVIEW == "REQUEST_REVIEW"

    def test_fail_value(self):
        """Test FAIL enum value."""
        assert ControllerDecision.FAIL == "FAIL"

    def test_all_values_present(self):
        """Test all enum values are present."""
        values = {d.value for d in ControllerDecision}
        assert values == {"COMPLETE", "RETRY", "REQUEST_REVIEW", "FAIL"}


class TestSessionStatusV2Enum:
    """Test SessionStatusV2 enum."""

    def test_active_value(self):
        """Test ACTIVE enum value."""
        assert SessionStatusV2.ACTIVE == "ACTIVE"

    def test_completed_value(self):
        """Test COMPLETED enum value."""
        assert SessionStatusV2.COMPLETED == "COMPLETED"

    def test_review_required_value(self):
        """Test REVIEW_REQUIRED enum value."""
        assert SessionStatusV2.REVIEW_REQUIRED == "REVIEW_REQUIRED"

    def test_failed_value(self):
        """Test FAILED enum value."""
        assert SessionStatusV2.FAILED == "FAILED"

    def test_cancelled_value(self):
        """Test CANCELLED enum value."""
        assert SessionStatusV2.CANCELLED == "CANCELLED"


class TestControllerConfig:
    """Test ControllerConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = ControllerConfig()
        assert config.evaluation_threshold == 0.7
        assert config.max_retries == 3
        assert config.max_iterations == 10
        assert config.verification_required is True
        assert config.auto_review_threshold == 0.5

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ControllerConfig(
            evaluation_threshold=0.8,
            max_retries=5,
            max_iterations=20,
            verification_required=False,
            auto_review_threshold=0.4,
        )
        assert config.evaluation_threshold == 0.8
        assert config.max_retries == 5
        assert config.max_iterations == 20
        assert config.verification_required is False
        assert config.auto_review_threshold == 0.4

    def test_immutability(self):
        """Test that ControllerConfig is immutable."""
        config = ControllerConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.evaluation_threshold = 0.9


class TestControllerReport:
    """Test ControllerReport."""

    def test_basic_report(self):
        """Test basic report creation."""
        report = ControllerReport(
            decision=ControllerDecision.COMPLETE,
            reason="All checks passed",
            iteration=1,
            retry_count=0,
        )
        assert report.decision == ControllerDecision.COMPLETE
        assert report.reason == "All checks passed"
        assert report.iteration == 1
        assert report.retry_count == 0
        assert report.evaluation_score is None
        assert report.verification_score is None
        assert report.created_at != ""

    def test_report_with_scores(self):
        """Test report with evaluation and verification scores."""
        report = ControllerReport(
            decision=ControllerDecision.COMPLETE,
            reason="Score 0.9 meets threshold",
            iteration=2,
            retry_count=1,
            evaluation_score=0.9,
            verification_score=1.0,
        )
        assert report.evaluation_score == 0.9
        assert report.verification_score == 1.0

    def test_immutability(self):
        """Test that ControllerReport is immutable."""
        report = ControllerReport(
            decision=ControllerDecision.COMPLETE,
            reason="Test",
            iteration=1,
            retry_count=0,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            report.reason = "Modified"


class TestEngineeringRequestV2:
    """Test EngineeringRequestV2."""

    def test_required_fields(self):
        """Test required fields."""
        from types import SimpleNamespace

        mock_op = SimpleNamespace(value="EXECUTE")
        request = EngineeringRequestV2(
            request_id="req-001",
            operation=mock_op,
            description="Test description",
        )
        assert request.request_id == "req-001"
        assert request.description == "Test description"
        assert request.workspace_path == ""
        assert request.workflow_name == ""
        assert request.context == {}
        assert request.metadata == {}
        assert request.config is None

    def test_all_fields(self):
        """Test all fields."""
        from packages.controller.models_v2 import ControllerConfig
        from types import SimpleNamespace

        mock_op = SimpleNamespace(value="EXECUTE")
        config = ControllerConfig(max_retries=5)
        request = EngineeringRequestV2(
            request_id="req-001",
            operation=mock_op,
            description="Test description",
            workspace_path="/path/to/workspace",
            workflow_name="test-workflow",
            context={"key": "value"},
            metadata={"meta": "data"},
            config=config,
        )
        assert request.workspace_path == "/path/to/workspace"
        assert request.workflow_name == "test-workflow"
        assert request.context == {"key": "value"}
        assert request.metadata == {"meta": "data"}
        assert request.config == config

    def test_immutability(self):
        """Test that EngineeringRequestV2 is immutable."""
        from types import SimpleNamespace

        mock_op = SimpleNamespace(value="EXECUTE")
        request = EngineeringRequestV2(
            request_id="req-001",
            operation=mock_op,
            description="Test",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            request.request_id = "modified"


class TestSessionHistoryEntry:
    """Test SessionHistoryEntry."""

    def test_minimal_entry(self):
        """Test minimal history entry."""
        entry = SessionHistoryEntry(
            iteration=1,
            workflow_name="test-workflow",
        )
        assert entry.iteration == 1
        assert entry.workflow_name == "test-workflow"
        assert entry.workflow_plan is None
        assert entry.execution_report is None
        assert entry.verification_report is None
        assert entry.evaluation_report is None
        assert entry.controller_report is None
        assert entry.created_at != ""

    def test_full_entry(self):
        """Test full history entry with all fields."""
        from types import SimpleNamespace

        report = ControllerReport(
            decision=ControllerDecision.COMPLETE,
            reason="Test",
            iteration=1,
            retry_count=0,
        )
        entry = SessionHistoryEntry(
            iteration=1,
            workflow_name="test-workflow",
            workflow_plan=SimpleNamespace(workflow_name="test"),
            execution_report=SimpleNamespace(success=True),
            verification_report=SimpleNamespace(score=1.0),
            evaluation_report=SimpleNamespace(overall_score=0.9),
            controller_report=report,
        )
        assert entry.workflow_plan is not None
        assert entry.execution_report is not None
        assert entry.verification_report is not None
        assert entry.evaluation_report is not None
        assert entry.controller_report is not None

    def test_immutability(self):
        """Test that SessionHistoryEntry is immutable."""
        entry = SessionHistoryEntry(
            iteration=1,
            workflow_name="test",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.workflow_name = "modified"


class TestEngineeringSessionV2:
    """Test EngineeringSessionV2."""

    def test_create_default(self):
        """Test session creation with defaults."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        assert session.session_id == "sess-001"
        assert session.request_id == "req-001"
        assert session.status == SessionStatusV2.ACTIVE
        assert session.iteration == 0
        assert session.max_iterations == 10
        assert session.retry_count == 0
        assert session.max_retries == 3
        assert session.history == ()
        assert session.metadata == {}

    def test_create_with_custom_config(self):
        """Test session creation with custom config."""
        config = ControllerConfig(
            max_iterations=20,
            max_retries=5,
        )
        session = EngineeringSessionV2.create(
            session_id="sess-002",
            request_id="req-002",
            config=config,
        )
        assert session.max_iterations == 20
        assert session.max_retries == 5

    def test_with_iteration(self):
        """Test updating iteration."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        new_session = session.with_iteration(5)
        assert new_session.iteration == 5
        assert session.iteration == 0  # Original unchanged

    def test_with_retry_count(self):
        """Test updating retry count."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        new_session = session.with_retry_count(2)
        assert new_session.retry_count == 2
        assert session.retry_count == 0  # Original unchanged

    def test_with_status(self):
        """Test updating status."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        new_session = session.with_status(SessionStatusV2.COMPLETED)
        assert new_session.status == SessionStatusV2.COMPLETED
        assert session.status == SessionStatusV2.ACTIVE  # Original unchanged

    def test_append_history(self):
        """Test appending history entry."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        entry = SessionHistoryEntry(
            iteration=1,
            workflow_name="test-workflow",
        )
        new_session = session.append_history(entry)
        assert len(new_session.history) == 1
        assert new_session.history[0].workflow_name == "test-workflow"
        assert session.history == ()  # Original unchanged

    def test_workflow_history_property(self):
        """Test workflow_history property."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        entry1 = SessionHistoryEntry(iteration=1, workflow_name="wf-1")
        entry2 = SessionHistoryEntry(iteration=2, workflow_name="wf-2")
        session = session.append_history(entry1)
        session = session.append_history(entry2)
        assert session.workflow_history == ("wf-1", "wf-2")

    def test_snapshot(self):
        """Test snapshot returns self."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        assert session.snapshot() is session

    def test_immutability(self):
        """Test that EngineeringSessionV2 is immutable."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            session.session_id = "modified"


class TestEngineeringResultV2:
    """Test EngineeringResultV2."""

    def test_complete_result(self):
        """Test COMPLETE result structure."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        result = EngineeringResultV2(
            request_id="req-001",
            session_id="sess-001",
            decision=ControllerDecision.COMPLETE,
            status=SessionStatusV2.COMPLETED,
            session=session,
            error_message="",
        )
        assert result.decision == ControllerDecision.COMPLETE
        assert result.status == SessionStatusV2.COMPLETED
        assert result.error_message == ""

    def test_fail_result(self):
        """Test FAIL result structure."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        result = EngineeringResultV2(
            request_id="req-001",
            session_id="sess-001",
            decision=ControllerDecision.FAIL,
            status=SessionStatusV2.FAILED,
            session=session,
            error_message="Execution failed",
        )
        assert result.decision == ControllerDecision.FAIL
        assert result.status == SessionStatusV2.FAILED
        assert result.error_message == "Execution failed"

    def test_review_result(self):
        """Test REQUEST_REVIEW result structure."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        result = EngineeringResultV2(
            request_id="req-001",
            session_id="sess-001",
            decision=ControllerDecision.REQUEST_REVIEW,
            status=SessionStatusV2.REVIEW_REQUIRED,
            session=session,
            error_message="Low evaluation score",
        )
        assert result.decision == ControllerDecision.REQUEST_REVIEW
        assert result.status == SessionStatusV2.REVIEW_REQUIRED

    def test_immutability(self):
        """Test that EngineeringResultV2 is immutable."""
        session = EngineeringSessionV2.create(
            session_id="sess-001",
            request_id="req-001",
        )
        result = EngineeringResultV2(
            request_id="req-001",
            session_id="sess-001",
            decision=ControllerDecision.COMPLETE,
            status=SessionStatusV2.COMPLETED,
            session=session,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.request_id = "modified"