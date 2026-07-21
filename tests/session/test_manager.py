"""Tests for session manager.

Tests cover:
- create() produces CREATED session
- update_status() enforces lifecycle
- attach_artifact() appends to artifacts
- snapshot() produces SessionSnapshot
- close() transitions to COMPLETED
- Invalid status transitions rejected
- Statistics tracking
"""

from __future__ import annotations

import pytest

from packages.session.lifecycle import LifecycleError
from packages.session.manager import SessionManager
from packages.session.models import (
    EngineeringSession,
    SessionArtifact,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class TestSessionManager:
    """Tests for SessionManager."""

    def test_create_session(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-001",
            workflow_name="bug-investigation",
        )
        assert session.session_id == "sess-req-001"
        assert session.request_id == "req-001"
        assert session.status == SessionStatus.CREATED
        assert session.workflow_name == "bug-investigation"

    def test_create_session_with_metadata(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-002",
            workflow_name="feature-implementation",
            metadata={"priority": "high"},
        )
        assert session.metadata == {"priority": "high"}

    def test_update_status_valid(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-003",
            workflow_name="bug-investigation",
        )
        updated = manager.update_status(
            session.session_id,
            SessionStatus.PLANNING,
        )
        assert updated.status == SessionStatus.PLANNING

    def test_update_status_invalid(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-004",
            workflow_name="bug-investigation",
        )
        with pytest.raises(LifecycleError):
            manager.update_status(
                session.session_id,
                SessionStatus.EXECUTING,
            )

    def test_update_status_not_found(self) -> None:
        manager = SessionManager()
        with pytest.raises(ValueError):
            manager.update_status(
                "sess-nonexistent",
                SessionStatus.PLANNING,
            )

    def test_attach_artifact(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-005",
            workflow_name="bug-investigation",
        )
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        manager.attach_artifact(session.session_id, artifact)

        snapshot = manager.snapshot(session.session_id)
        assert len(snapshot.artifacts) == 1
        assert snapshot.artifacts[0].artifact_type == "WorkflowPlan"

    def test_attach_multiple_artifacts(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-006",
            workflow_name="bug-investigation",
        )
        artifact1 = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        artifact2 = SessionArtifact(
            artifact_type="PatchSet",
            artifact_id="patch-001",
        )
        manager.attach_artifact(session.session_id, artifact1)
        manager.attach_artifact(session.session_id, artifact2)

        snapshot = manager.snapshot(session.session_id)
        assert len(snapshot.artifacts) == 2

    def test_attach_artifact_not_found(self) -> None:
        manager = SessionManager()
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        with pytest.raises(ValueError):
            manager.attach_artifact("sess-nonexistent", artifact)

    def test_snapshot(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-007",
            workflow_name="bug-investigation",
        )
        snapshot = manager.snapshot(session.session_id)
        assert snapshot.session == session
        assert snapshot.artifacts == ()
        assert snapshot.statistics.workflows == 0

    def test_snapshot_with_artifacts(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-008",
            workflow_name="bug-investigation",
        )
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        manager.attach_artifact(session.session_id, artifact)

        snapshot = manager.snapshot(session.session_id)
        assert len(snapshot.artifacts) == 1
        assert snapshot.artifacts[0].artifact_id == "plan-001"

    def test_snapshot_not_found(self) -> None:
        manager = SessionManager()
        with pytest.raises(ValueError):
            manager.snapshot("sess-nonexistent")

    def test_close_session(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-009",
            workflow_name="bug-investigation",
        )
        # Transition through the full lifecycle
        manager.update_status(session.session_id, SessionStatus.PLANNING)
        manager.update_status(session.session_id, SessionStatus.EXECUTING)
        manager.update_status(session.session_id, SessionStatus.VERIFYING)

        updated = manager.close(session.session_id)
        assert updated.status == SessionStatus.COMPLETED

    def test_close_from_completed_rejected(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-010",
            workflow_name="bug-investigation",
        )
        manager.update_status(session.session_id, SessionStatus.PLANNING)
        manager.update_status(session.session_id, SessionStatus.EXECUTING)
        manager.update_status(session.session_id, SessionStatus.VERIFYING)
        manager.close(session.session_id)

        with pytest.raises(LifecycleError):
            manager.close(session.session_id)

    def test_close_not_found(self) -> None:
        manager = SessionManager()
        with pytest.raises(ValueError):
            manager.close("sess-nonexistent")

    def test_get_statistics(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-011",
            workflow_name="bug-investigation",
        )
        stats = manager.get_statistics(session.session_id)
        assert stats.workflows == 0
        assert stats.executions == 0

    def test_update_statistics(self) -> None:
        from packages.session.models import SessionStatistics

        manager = SessionManager()
        session = manager.create(
            request_id="req-012",
            workflow_name="bug-investigation",
        )
        new_stats = SessionStatistics(
            workflows=3,
            executions=5,
            evaluations=2,
            patches=4,
            modifications=3,
            verifications=2,
            duration_ms=10000,
        )
        manager.update_statistics(session.session_id, new_stats)
        stats = manager.get_statistics(session.session_id)
        assert stats.workflows == 3
        assert stats.executions == 5
        assert stats.evaluations == 2
        assert stats.patches == 4
        assert stats.modifications == 3
        assert stats.verifications == 2
        assert stats.duration_ms == 10000

    def test_full_lifecycle_with_manager(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-013",
            workflow_name="bug-investigation",
        )
        assert session.status == SessionStatus.CREATED

        session = manager.update_status(
            session.session_id,
            SessionStatus.PLANNING,
        )
        assert session.status == SessionStatus.PLANNING

        session = manager.update_status(
            session.session_id,
            SessionStatus.EXECUTING,
        )
        assert session.status == SessionStatus.EXECUTING

        session = manager.update_status(
            session.session_id,
            SessionStatus.VERIFYING,
        )
        assert session.status == SessionStatus.VERIFYING

        session = manager.close(session.session_id)
        assert session.status == SessionStatus.COMPLETED

    def test_failure_path_via_manager(self) -> None:
        manager = SessionManager()
        session = manager.create(
            request_id="req-014",
            workflow_name="bug-investigation",
        )

        session = manager.update_status(
            session.session_id,
            SessionStatus.FAILED,
        )
        assert session.status == SessionStatus.FAILED

        # Cannot proceed from FAILED
        with pytest.raises(LifecycleError):
            manager.update_status(
                session.session_id,
                SessionStatus.EXECUTING,
            )

    def test_registry_injection(self) -> None:
        from packages.session.registry import SessionRegistry

        registry = SessionRegistry()
        manager = SessionManager(registry=registry)

        session = manager.create(
            request_id="req-015",
            workflow_name="bug-investigation",
        )

        # Session should be in the registry
        result = registry.get(session.session_id)
        assert result is not None
        assert result.session_id == session.session_id

    def test_artifact_not_reflected_in_session(self) -> None:
        """attach_artifact records the artifact but does not modify the session."""
        manager = SessionManager()
        session = manager.create(
            request_id="req-016",
            workflow_name="bug-investigation",
        )
        artifact = SessionArtifact(
            artifact_type="WorkflowPlan",
            artifact_id="plan-001",
        )
        manager.attach_artifact(session.session_id, artifact)

        # The session object itself is unchanged
        assert session.workflow_name == "bug-investigation"

        # But the snapshot reflects the artifact
        snapshot = manager.snapshot(session.session_id)
        assert len(snapshot.artifacts) == 1