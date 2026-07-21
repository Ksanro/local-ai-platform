"""Tests for session persistence.

Tests cover:
- save() writes to disk
- load() reconstructs session
- snapshot() returns deterministic JSON
- Non-existent session returns None
- Metadata-only persistence
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.session.models import EngineeringSession, SessionStatus
from packages.session.persistence import SessionPersistence


# ---------------------------------------------------------------------------
# SessionPersistence
# ---------------------------------------------------------------------------


class TestSessionPersistence:
    """Tests for SessionPersistence."""

    def test_save_and_load(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-001",
                request_id="req-001",
                status=SessionStatus.CREATED,
                workflow_name="bug-investigation",
                metadata={"priority": "high"},
            )

            path = persistence.save(session)
            assert path.exists()

            loaded = persistence.load("sess-001")
            assert loaded is not None
            assert loaded.session_id == session.session_id
            assert loaded.request_id == session.request_id
            assert loaded.status == session.status
            assert loaded.workflow_name == session.workflow_name
            assert loaded.metadata == session.metadata

    def test_load_nonexistent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            loaded = persistence.load("sess-nonexistent")
            assert loaded is None

    def test_snapshot_deterministic(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-002",
                request_id="req-002",
                status=SessionStatus.PLANNING,
                workflow_name="feature-implementation",
                metadata={"key": "value"},
            )

            snapshot1 = persistence.snapshot(session)
            snapshot2 = persistence.snapshot(session)

            # Deterministic output
            assert snapshot1 == snapshot2

            # Valid JSON
            data = json.loads(snapshot1)
            assert data["session_id"] == "sess-002"
            assert data["status"] == "PLANNING"

    def test_snapshot_contains_only_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-003",
                request_id="req-003",
                status=SessionStatus.CREATED,
                workflow_name="bug-investigation",
                metadata={"test": True},
            )

            snapshot = persistence.snapshot(session)
            data = json.loads(snapshot)

            # Should contain session metadata
            assert "session_id" in data
            assert "request_id" in data
            assert "status" in data
            assert "created_at" in data
            assert "updated_at" in data
            assert "workflow_name" in data
            assert "metadata" in data

            # Should NOT contain runtime objects
            assert "providers" not in data
            assert "repository" not in data

    def test_save_overwrites(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session1 = EngineeringSession(
                session_id="sess-004",
                request_id="req-004",
                status=SessionStatus.CREATED,
                workflow_name="workflow-a",
            )
            session2 = EngineeringSession(
                session_id="sess-004",
                request_id="req-005",
                status=SessionStatus.PLANNING,
                workflow_name="workflow-b",
            )

            persistence.save(session1)
            persistence.save(session2)

            loaded = persistence.load("sess-004")
            assert loaded is not None
            assert loaded.status == SessionStatus.PLANNING
            assert loaded.workflow_name == "workflow-b"

    def test_save_multiple_sessions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))

            session1 = EngineeringSession(
                session_id="sess-005",
                request_id="req-005",
                status=SessionStatus.CREATED,
                workflow_name="workflow-a",
            )
            session2 = EngineeringSession(
                session_id="sess-006",
                request_id="req-006",
                status=SessionStatus.PLANNING,
                workflow_name="workflow-b",
            )

            persistence.save(session1)
            persistence.save(session2)

            loaded1 = persistence.load("sess-005")
            loaded2 = persistence.load("sess-006")

            assert loaded1 is not None
            assert loaded2 is not None
            assert loaded1.workflow_name == "workflow-a"
            assert loaded2.workflow_name == "workflow-b"

    def test_load_preserves_all_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-007",
                request_id="req-007",
                status=SessionStatus.EXECUTING,
                workflow_name="full-test",
                execution_id="exec-001",
                evaluation_id="eval-001",
                verification_id="verify-001",
                metadata={"full": True},
            )

            persistence.save(session)
            loaded = persistence.load("sess-007")

            assert loaded is not None
            assert loaded.session_id == session.session_id
            assert loaded.request_id == session.request_id
            assert loaded.status == session.status
            assert loaded.workflow_name == session.workflow_name
            assert loaded.execution_id == session.execution_id
            assert loaded.evaluation_id == session.evaluation_id
            assert loaded.verification_id == session.verification_id
            assert loaded.metadata == session.metadata

    def test_string_base_dir_conversion(self) -> None:
        with TemporaryDirectory() as tmpdir:
            # Should accept string path and convert to Path
            persistence = SessionPersistence(tmpdir)
            session = EngineeringSession(
                session_id="sess-008",
                request_id="req-008",
                status=SessionStatus.CREATED,
            )

            path = persistence.save(session)
            assert path.exists()

    def test_empty_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-009",
                request_id="req-009",
                status=SessionStatus.CREATED,
            )

            persistence.save(session)
            loaded = persistence.load("sess-009")

            assert loaded is not None
            assert loaded.metadata == {}

    def test_json_sorted_keys(self) -> None:
        with TemporaryDirectory() as tmpdir:
            persistence = SessionPersistence(Path(tmpdir))
            session = EngineeringSession(
                session_id="sess-010",
                request_id="req-010",
                status=SessionStatus.CREATED,
                workflow_name="test",
            )

            path = persistence.save(session)
            content = path.read_text()
            data = json.loads(content)

            # Keys should be sorted alphabetically
            keys = list(data.keys())
            assert keys == sorted(keys)