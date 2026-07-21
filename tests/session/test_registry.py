"""Tests for session registry.

Tests cover:
- Register, get, all, remove operations
- Deterministic ordering
- Duplicate registration handling
- Empty registry behavior
"""

from __future__ import annotations

import pytest

from packages.session.models import EngineeringSession, SessionStatus
from packages.session.registry import SessionRegistry


# ---------------------------------------------------------------------------
# SessionRegistry
# ---------------------------------------------------------------------------


class TestSessionRegistry:
    """Tests for SessionRegistry."""

    def test_empty_registry(self) -> None:
        registry = SessionRegistry()
        assert registry.all() == {}

    def test_register_and_get(self) -> None:
        registry = SessionRegistry()
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        registry.register(session)
        result = registry.get("sess-001")
        assert result is not None
        assert result.session_id == "sess-001"

    def test_get_nonexistent(self) -> None:
        registry = SessionRegistry()
        result = registry.get("sess-nonexistent")
        assert result is None

    def test_register_multiple_sessions(self) -> None:
        registry = SessionRegistry()
        session1 = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        session2 = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.PLANNING,
        )
        session3 = EngineeringSession(
            session_id="sess-003",
            request_id="req-003",
            status=SessionStatus.EXECUTING,
        )

        registry.register(session1)
        registry.register(session2)
        registry.register(session3)

        all_sessions = registry.all()
        assert len(all_sessions) == 3
        assert "sess-001" in all_sessions
        assert "sess-002" in all_sessions
        assert "sess-003" in all_sessions

    def test_all_returns_copy(self) -> None:
        registry = SessionRegistry()
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        registry.register(session)

        all_sessions = registry.all()
        all_sessions["sess-999"] = EngineeringSession(
            session_id="sess-999",
            request_id="req-999",
            status=SessionStatus.CREATED,
        )

        # Original registry should be unaffected
        assert len(registry.all()) == 1
        assert "sess-999" not in registry.all()

    def test_duplicate_registration_overwrites(self) -> None:
        registry = SessionRegistry()
        session1 = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        session2 = EngineeringSession(
            session_id="sess-001",
            request_id="req-002",
            status=SessionStatus.PLANNING,
        )

        registry.register(session1)
        registry.register(session2)

        result = registry.get("sess-001")
        assert result is not None
        assert result.status == SessionStatus.PLANNING
        assert result.request_id == "req-002"

    def test_remove_existing(self) -> None:
        registry = SessionRegistry()
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        registry.register(session)

        result = registry.remove("sess-001")
        assert result is True
        assert registry.get("sess-001") is None

    def test_remove_nonexistent(self) -> None:
        registry = SessionRegistry()
        result = registry.remove("sess-nonexistent")
        assert result is False

    def test_remove_then_all(self) -> None:
        registry = SessionRegistry()
        session = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        registry.register(session)
        registry.remove("sess-001")

        assert len(registry.all()) == 0

    def test_multiple_remove(self) -> None:
        registry = SessionRegistry()
        session1 = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        session2 = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.CREATED,
        )

        registry.register(session1)
        registry.register(session2)

        assert registry.remove("sess-001") is True
        assert registry.remove("sess-002") is True
        assert registry.remove("sess-001") is False

        assert len(registry.all()) == 0

    def test_deterministic_ordering(self) -> None:
        registry = SessionRegistry()
        session1 = EngineeringSession(
            session_id="sess-001",
            request_id="req-001",
            status=SessionStatus.CREATED,
        )
        session2 = EngineeringSession(
            session_id="sess-002",
            request_id="req-002",
            status=SessionStatus.CREATED,
        )
        session3 = EngineeringSession(
            session_id="sess-003",
            request_id="req-003",
            status=SessionStatus.CREATED,
        )

        registry.register(session1)
        registry.register(session2)
        registry.register(session3)

        all_sessions = registry.all()
        keys = list(all_sessions.keys())
        assert keys == ["sess-001", "sess-002", "sess-003"]