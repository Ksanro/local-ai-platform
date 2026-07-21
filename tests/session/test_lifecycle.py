"""Tests for lifecycle validation.

Tests cover:
- Valid lifecycle transitions
- Invalid transitions
- Terminal state enforcement
- Timestamp updates
- Error messages
"""

from __future__ import annotations

import pytest

from packages.session.lifecycle import (
    LifecycleError,
    validate_transition,
    transition,
)
from packages.session.models import (
    EngineeringSession,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------


class TestValidateTransition:
    """Tests for validate_transition."""

    def test_valid_created_to_planning(self) -> None:
        assert validate_transition(SessionStatus.CREATED, SessionStatus.PLANNING)

    def test_valid_created_to_failed(self) -> None:
        assert validate_transition(SessionStatus.CREATED, SessionStatus.FAILED)

    def test_valid_created_to_cancelled(self) -> None:
        assert validate_transition(SessionStatus.CREATED, SessionStatus.CANCELLED)

    def test_valid_planning_to_executing(self) -> None:
        assert validate_transition(SessionStatus.PLANNING, SessionStatus.EXECUTING)

    def test_valid_planning_to_failed(self) -> None:
        assert validate_transition(SessionStatus.PLANNING, SessionStatus.FAILED)

    def test_valid_executing_to_verifying(self) -> None:
        assert validate_transition(SessionStatus.EXECUTING, SessionStatus.VERIFYING)

    def test_valid_executing_to_failed(self) -> None:
        assert validate_transition(SessionStatus.EXECUTING, SessionStatus.FAILED)

    def test_valid_verifying_to_completed(self) -> None:
        assert validate_transition(SessionStatus.VERIFYING, SessionStatus.COMPLETED)

    def test_valid_verifying_to_failed(self) -> None:
        assert validate_transition(SessionStatus.VERIFYING, SessionStatus.FAILED)

    def test_invalid_completed_to_executing(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.COMPLETED, SessionStatus.EXECUTING)

    def test_invalid_failed_to_planning(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.FAILED, SessionStatus.PLANNING)

    def test_invalid_cancelled_to_anything(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.CANCELLED, SessionStatus.EXECUTING)

    def test_invalid_same_state(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.CREATED, SessionStatus.CREATED)

    def test_invalid_created_to_executing(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.CREATED, SessionStatus.EXECUTING)

    def test_invalid_created_to_completed(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.CREATED, SessionStatus.COMPLETED)

    def test_invalid_planning_to_verifying(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.PLANNING, SessionStatus.VERIFYING)

    def test_invalid_executing_to_planning(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.EXECUTING, SessionStatus.PLANNING)

    def test_invalid_verify_to_executing(self) -> None:
        with pytest.raises(LifecycleError):
            validate_transition(SessionStatus.VERIFYING, SessionStatus.EXECUTING)


# ---------------------------------------------------------------------------
# transition
# ---------------------------------------------------------------------------


class TestTransition:
    """Tests for transition function."""

    def test_valid_transition_updates_status(self) -> None:
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        updated = transition(session, SessionStatus.PLANNING)
        assert updated.status == SessionStatus.PLANNING
        assert updated.session_id == session.session_id
        assert updated.request_id == session.request_id

    def test_valid_transition_updates_timestamp(self) -> None:
        session = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.CREATED,
        )
        original_updated = session.updated_at
        updated = transition(session, SessionStatus.PLANNING)
        # The updated_at should be refreshed
        assert updated.updated_at != original_updated

    def test_valid_transition_preserves_metadata(self) -> None:
        session = EngineeringSession(
            session_id="sess-003",
            request_id="req-003",
            status=SessionStatus.CREATED,
            metadata={"key": "value"},
        )
        updated = transition(session, SessionStatus.PLANNING)
        assert updated.metadata == {"key": "value"}

    def test_valid_transition_preserves_workflow_name(self) -> None:
        session = EngineeringSession(
            session_id="sess-004",
            request_id="req-004",
            status=SessionStatus.CREATED,
            workflow_name="bug-investigation",
        )
        updated = transition(session, SessionStatus.PLANNING)
        assert updated.workflow_name == "bug-investigation"

    def test_valid_transition_preserves_ids(self) -> None:
        session = EngineeringSession(
            session_id="sess-005",
            request_id="req-005",
            status=SessionStatus.CREATED,
            execution_id="exec-001",
            evaluation_id="eval-001",
            verification_id="verify-001",
        )
        updated = transition(session, SessionStatus.PLANNING)
        assert updated.execution_id == "exec-001"
        assert updated.evaluation_id == "eval-001"
        assert updated.verification_id == "verify-001"

    def test_invalid_transition_raises_error(self) -> None:
        session = EngineeringSession(
            session_id="sess-006",
            request_id="req-006",
            status=SessionStatus.COMPLETED,
        )
        with pytest.raises(LifecycleError):
            transition(session, SessionStatus.EXECUTING)

    def test_failed_is_terminal(self) -> None:
        session = EngineeringSession(
            session_id="sess-007",
            request_id="req-007",
            status=SessionStatus.FAILED,
        )
        with pytest.raises(LifecycleError):
            transition(session, SessionStatus.PLANNING)

    def test_cancelled_is_terminal(self) -> None:
        session = EngineeringSession(
            session_id="sess-008",
            request_id="req-008",
            status=SessionStatus.CANCELLED,
        )
        with pytest.raises(LifecycleError):
            transition(session, SessionStatus.EXECUTING)

    def test_full_lifecycle_chain(self) -> None:
        """Test the full valid lifecycle chain."""
        session = EngineeringSession(
            session_id="sess-009",
            request_id="req-009",
            status=SessionStatus.CREATED,
        )

        session = transition(session, SessionStatus.PLANNING)
        assert session.status == SessionStatus.PLANNING

        session = transition(session, SessionStatus.EXECUTING)
        assert session.status == SessionStatus.EXECUTING

        session = transition(session, SessionStatus.VERIFYING)
        assert session.status == SessionStatus.VERIFYING

        session = transition(session, SessionStatus.COMPLETED)
        assert session.status == SessionStatus.COMPLETED

    def test_failure_path(self) -> None:
        """Test the failure path from any state."""
        session = EngineeringSession(
            session_id="sess-010",
            request_id="req-010",
            status=SessionStatus.PLANNING,
        )

        session = transition(session, SessionStatus.FAILED)
        assert session.status == SessionStatus.FAILED

        # Cannot transition from FAILED
        with pytest.raises(LifecycleError):
            transition(session, SessionStatus.EXECUTING)

    def test_cancelled_path(self) -> None:
        """Test the cancelled path from any state."""
        session = EngineeringSession(
            session_id="sess-011",
            request_id="req-011",
            status=SessionStatus.EXECUTING,
        )

        session = transition(session, SessionStatus.CANCELLED)
        assert session.status == SessionStatus.CANCELLED

        # Cannot transition from CANCELLED
        with pytest.raises(LifecycleError):
            transition(session, SessionStatus.VERIFYING)


# ---------------------------------------------------------------------------
# LifecycleError
# ---------------------------------------------------------------------------


class TestLifecycleError:
    """Tests for LifecycleError."""

    def test_error_message(self) -> None:
        error = LifecycleError(SessionStatus.CREATED, SessionStatus.EXECUTING)
        assert "Invalid lifecycle transition" in str(error)
        assert "CREATED" in str(error)
        assert "EXECUTING" in str(error)

    def test_error_attributes(self) -> None:
        error = LifecycleError(SessionStatus.PLANNING, SessionStatus.COMPLETED)
        assert error.current == SessionStatus.PLANNING
        assert error.target == SessionStatus.COMPLETED