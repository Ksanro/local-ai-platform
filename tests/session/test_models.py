"""Tests for session models.

Tests cover:
- Immutable models
- Default values
- Frozen state
- Type correctness
- Equality and hashing
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.session.models import (
    EngineeringSession,
    SessionArtifact,
    SessionSnapshot,
    SessionStatistics,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# SessionStatus
# ---------------------------------------------------------------------------


class TestSessionStatus:
    """Tests for SessionStatus."""

    def test_created_value(self) -> None:
        assert SessionStatus.CREATED == "CREATED"

    def test_planning_value(self) -> None:
        assert SessionStatus.PLANNING == "PLANNING"

    def test_executing_value(self) -> None:
        assert SessionStatus.EXECUTING == "EXECUTING"

    def test_verifying_value(self) -> None:
        assert SessionStatus.VERIFYING == "VERIFYING"

    def test_completed_value(self) -> None:
        assert SessionStatus.COMPLETED == "COMPLETED"

    def test_failed_value(self) -> None:
        assert SessionStatus.FAILED == "FAILED"

    def test_cancelled_value(self) -> None:
        assert SessionStatus.CANCELLED == "CANCELLED"


# ---------------------------------------------------------------------------
# EngineeringSession
# ---------------------------------------------------------------------------


class TestEngineeringSession:
    """Tests for EngineeringSession."""

    def test_basic_creation(self) -> None:
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        assert session.session_id == "sess-001"
        assert session.request_id == "req-001"
        assert session.status == SessionStatus.CREATED
        assert session.workflow_name == ""
        assert session.execution_id == ""
        assert session.evaluation_id == ""
        assert session.verification_id == ""
        assert session.metadata == {}

    def test_full_creation(self) -> None:
        session = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.PLANNING,
            workflow_name="bug-investigation",
            execution_id="exec-001",
            evaluation_id="eval-001",
            verification_id="verify-001",
            metadata={"priority": "high"},
        )
        assert session.workflow_name == "bug-investigation"
        assert session.execution_id == "exec-001"
        assert session.evaluation_id == "eval-001"
        assert session.verification_id == "verify-001"
        assert session.metadata == {"priority": "high"}

    def test_immutability(self) -> None:
        session = EngineeringSession(
            session_id="sess-003",
            request_id="req-003",
            status=SessionStatus.CREATED,
        )
        with pytest.raises((TypeError, FrozenInstanceError)):
            session.session_id = "modified"

    def test_equality_with_same_timestamps(self) -> None:
        # Equality works when created_at/updated_at are the same
        from packages.session.models import EngineeringSession
        import packages.session.models as models
        # Patch to use same timestamps
        ts = "2024-01-01T00:00:00+00:00"
        session1 = EngineeringSession(
            session_id="sess-004",
            request_id="req-004",
            status=SessionStatus.CREATED,
            created_at=ts,
            updated_at=ts,
        )
        session2 = EngineeringSession(
            session_id="sess-004",
            request_id="req-004",
            status=SessionStatus.CREATED,
            created_at=ts,
            updated_at=ts,
        )
        assert session1 == session2

    def test_created_at_timestamp(self) -> None:
        session = EngineeringSession(
            session_id="sess-006",
            request_id="req-006",
            status=SessionStatus.CREATED,
        )
        assert session.created_at != ""
        assert "T" in session.created_at

    def test_updated_at_timestamp(self) -> None:
        session = EngineeringSession(
            session_id="sess-007",
            request_id="req-007",
            status=SessionStatus.CREATED,
        )
        assert session.updated_at != ""
        assert "T" in session.updated_at


# ---------------------------------------------------------------------------
# SessionArtifact
# ---------------------------------------------------------------------------


class TestSessionArtifact:
    """Tests for SessionArtifact."""

    def test_basic_creation(self) -> None:
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        assert artifact.artifact_type == "WorkflowPlan"
        assert artifact.artifact_id == "plan-001"
        assert artifact.created_at != ""
        assert artifact.metadata == {}

    def test_full_creation(self) -> None:
        artifact = SessionArtifact(
            artifact_type="PatchSet",
            artifact_id="patch-001",
            metadata={"files_count": 5},
        )
        assert artifact.artifact_type == "PatchSet"
        assert artifact.artifact_id == "patch-001"
        assert artifact.metadata == {"files_count": 5}

    def test_immutability(self) -> None:
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-002",
        )
        with pytest.raises((TypeError, FrozenInstanceError)):
            artifact.artifact_type = "Modified"

    def test_equality_with_same_timestamps(self) -> None:
        ts = "2024-01-01T00:00:00+00:00"
        artifact1 = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-003",
            created_at=ts,
        )
        artifact2 = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-003",
            created_at=ts,
        )
        assert artifact1 == artifact2


# ---------------------------------------------------------------------------
# SessionStatistics
# ---------------------------------------------------------------------------


class TestSessionStatistics:
    """Tests for SessionStatistics."""

    def test_default_values(self) -> None:
        stats = SessionStatistics()
        assert stats.workflows == 0
        assert stats.executions == 0
        assert stats.evaluations == 0
        assert stats.patches == 0
        assert stats.modifications == 0
        assert stats.verifications == 0
        assert stats.duration_ms == 0

    def test_with_values(self) -> None:
        stats = SessionStatistics(
            workflows=3,
            executions=5,
            evaluations=2,
            patches=4,
            modifications=3,
            verifications=2,
            duration_ms=10000,
        )
        assert stats.workflows == 3
        assert stats.executions == 5
        assert stats.evaluations == 2
        assert stats.patches == 4
        assert stats.modifications == 3
        assert stats.verifications == 2
        assert stats.duration_ms == 10000

    def test_immutability(self) -> None:
        stats = SessionStatistics()
        with pytest.raises((TypeError, FrozenInstanceError)):
            stats.workflows = 10

    def test_equality(self) -> None:
        stats1 = SessionStatistics(workflows=1, executions=2)
        stats2 = SessionStatistics(workflows=1, executions=2)
        assert stats1 == stats2

    # Note: SessionStatistics with empty metadata is hashable
    def test_hash(self) -> None:
        stats = SessionStatistics()
        hash(stats)


# ---------------------------------------------------------------------------
# SessionSnapshot
# ---------------------------------------------------------------------------


class TestSessionSnapshot:
    """Tests for SessionSnapshot."""

    def test_basic_creation(self) -> None:
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        snapshot = SessionSnapshot(session=session)
        assert snapshot.session == session
        assert snapshot.artifacts == ()
        assert snapshot.statistics.workflows == 0

    def test_full_creation(self) -> None:
        session = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.EXECUTING,
        )
        artifact1 = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        artifact2 = SessionArtifact(
            artifact_type="PatchSet",
            artifact_id="patch-001",
        )
        stats = SessionStatistics(
            workflows=1,
            executions=1,
            patches=1,
            duration_ms=5000,
        )
        snapshot = SessionSnapshot(
            session=session,
            artifacts=(artifact1, artifact2),
            statistics=stats,
        )
        assert snapshot.session == session
        assert len(snapshot.artifacts) == 2
        assert snapshot.statistics.workflows == 1
        assert snapshot.statistics.duration_ms == 5000

    def test_immutability(self) -> None:
        session = EngineeringSession(
            session_id="sess-003",
            request_id="req-003",
            status=SessionStatus.CREATED,
        )
        snapshot = SessionSnapshot(session=session)
        with pytest.raises((TypeError, FrozenInstanceError)):
            snapshot.session = EngineeringSession(
                session_id="sess-004",
                request_id="req-004",
                status=SessionStatus.CREATED,
            )

    def test_equality_with_same_timestamps(self) -> None:
        ts = "2024-01-01T00:00:00+00:00"
        session = EngineeringSession(
            session_id="sess-005",
            request_id="req-005",
            status=SessionStatus.CREATED,
            created_at=ts,
            updated_at=ts,
        )
        snapshot1 = SessionSnapshot(session=session)
        snapshot2 = SessionSnapshot(session=session)
        assert snapshot1 == snapshot2
