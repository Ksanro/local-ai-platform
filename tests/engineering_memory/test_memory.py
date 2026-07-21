"""Tests for EngineeringMemory service.

Covers:
- store/load
- deterministic ordering
- duplicate prevention
- query correctness (find_by_workflow, find_successful, find_failed, find_by_module, recent)
"""

from __future__ import annotations

import pytest

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.models import EngineeringSessionRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    session_id: str = "sess-001",
    workflow_name: str = "bug-fix",
    controller_decision: str = "COMPLETE",
    completed_at: str = "2026-07-21T14:55:00+00:00",
    modified_modules: list[str] | None = None,
    iteration_count: int = 1,
    evaluation_score: float | None = None,
) -> EngineeringSessionRecord:
    """Create a test EngineeringSessionRecord."""
    metadata: dict = {"iteration_count": iteration_count}
    if modified_modules:
        metadata["modified_modules"] = modified_modules

    evaluation_report: dict = {}
    if evaluation_score is not None:
        evaluation_report["overall_score"] = evaluation_score

    return EngineeringSessionRecord(
        session_id=session_id,
        workflow_name=workflow_name,
        request_summary=f"Task for {session_id}",
        transaction_id=f"txn-{session_id}",
        execution_report={"status": "COMPLETED"},
        verification_report={"status": "PASSED"},
        evaluation_report=evaluation_report,
        controller_decision=controller_decision,
        completed_at=completed_at,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Store/Load Tests
# ---------------------------------------------------------------------------


class TestStoreLoad:
    """Tests for store and load operations."""

    def test_store_single_record(self):
        """Test storing a single record."""
        memory = EngineeringMemory(in_memory_only=True)
        record = _make_record()

        memory.store(record)
        assert memory.session_count == 1

    def test_store_multiple_records(self):
        """Test storing multiple records."""
        memory = EngineeringMemory(in_memory_only=True)

        for i in range(5):
            record = _make_record(
                session_id=f"sess-00{i+1}",
                completed_at=f"2026-07-21T14:{50+i:02d}:00+00:00",
            )
            memory.store(record)

        assert memory.session_count == 5

    def test_load_empty(self):
        """Test listing sessions when none stored."""
        memory = EngineeringMemory(in_memory_only=True)
        sessions = memory.list_sessions()
        assert sessions == ()
        assert memory.session_count == 0

    def test_load_after_store(self):
        """Test that stored records can be retrieved."""
        memory = EngineeringMemory(in_memory_only=True)
        record = _make_record(session_id="sess-001")

        memory.store(record)
        retrieved = memory.find_session("sess-001")

        assert retrieved is not None
        assert retrieved.session_id == "sess-001"
        assert retrieved.workflow_name == "bug-fix"

    def test_load_nonexistent(self):
        """Test loading a non-existent session."""
        memory = EngineeringMemory(in_memory_only=True)
        result = memory.find_session("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Deterministic Ordering Tests
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering guarantees."""

    def test_list_sessions_sorted_by_id(self):
        """Test that list_sessions returns records sorted by session_id."""
        memory = EngineeringMemory(in_memory_only=True)

        for sid in ["sess-003", "sess-001", "sess-002"]:
            record = _make_record(session_id=sid)
            memory.store(record)

        sessions = memory.list_sessions()
        ids = [r.session_id for r in sessions]
        assert ids == ["sess-001", "sess-002", "sess-003"]

    def test_find_by_workflow_sorted(self):
        """Test that find_by_workflow returns sorted results."""
        memory = EngineeringMemory(in_memory_only=True)

        for sid in ["sess-003", "sess-001", "sess-002"]:
            record = _make_record(session_id=sid, workflow_name="bug-fix")
            memory.store(record)

        results = memory.find_by_workflow("bug-fix")
        ids = [r.session_id for r in results]
        assert ids == ["sess-001", "sess-002", "sess-003"]

    def test_find_successful_sorted(self):
        """Test that find_successful returns sorted results."""
        memory = EngineeringMemory(in_memory_only=True)

        for i in range(3):
            record = _make_record(
                session_id=f"sess-00{i+1}",
                controller_decision="COMPLETE",
            )
            memory.store(record)

        results = memory.find_successful()
        ids = [r.session_id for r in results]
        assert ids == ["sess-001", "sess-002", "sess-003"]

    def test_find_failed_sorted(self):
        """Test that find_failed returns sorted results."""
        memory = EngineeringMemory(in_memory_only=True)

        for i in range(3):
            record = _make_record(
                session_id=f"sess-00{i+1}",
                controller_decision="FAIL",
            )
            memory.store(record)

        results = memory.find_failed()
        ids = [r.session_id for r in results]
        assert ids == ["sess-001", "sess-002", "sess-003"]

    def test_recent_sorted_by_completed_at(self):
        """Test that recent returns records sorted by completed_at descending."""
        memory = EngineeringMemory(in_memory_only=True)

        records = [
            _make_record(
                session_id="sess-001",
                completed_at="2026-07-21T14:50:00+00:00",
            ),
            _make_record(
                session_id="sess-002",
                completed_at="2026-07-21T14:55:00+00:00",
            ),
            _make_record(
                session_id="sess-003",
                completed_at="2026-07-21T14:45:00+00:00",
            ),
        ]
        for record in records:
            memory.store(record)

        recent = memory.recent(limit=2)
        ids = [r.session_id for r in recent]
        # Most recent first
        assert ids == ["sess-002", "sess-001"]


# ---------------------------------------------------------------------------
# Duplicate Prevention Tests
# ---------------------------------------------------------------------------


class TestDuplicatePrevention:
    """Tests for duplicate session prevention."""

    def test_duplicate_store_ignored(self):
        """Test that storing a duplicate session_id is ignored."""
        memory = EngineeringMemory(in_memory_only=True)

        record1 = _make_record(
            session_id="sess-001",
            workflow_name="bug-fix",
            completed_at="2026-07-21T14:50:00+00:00",
        )
        memory.store(record1)

        record2 = _make_record(
            session_id="sess-001",
            workflow_name="feature-add",  # Different workflow
            completed_at="2026-07-21T15:00:00+00:00",  # Different time
        )
        memory.store(record2)

        # Should still have only one session
        assert memory.session_count == 1

        # First record should be preserved
        retrieved = memory.find_session("sess-001")
        assert retrieved.workflow_name == "bug-fix"
        assert retrieved.completed_at == "2026-07-21T14:50:00+00:00"

    def test_has_session(self):
        """Test has_session method."""
        memory = EngineeringMemory(in_memory_only=True)
        record = _make_record(session_id="sess-001")

        assert not memory.has_session("sess-001")
        memory.store(record)
        assert memory.has_session("sess-001")

    def test_store_if_new_returns_true(self):
        """Test store_if_new returns True for new record."""
        memory = EngineeringMemory(in_memory_only=True)
        record = _make_record(session_id="sess-001")

        assert memory.store_if_new(record) is True

    def test_store_if_new_returns_false_for_duplicate(self):
        """Test store_if_new returns False for duplicate."""
        memory = EngineeringMemory(in_memory_only=True)
        record = _make_record(session_id="sess-001")

        memory.store(record)
        assert memory.store_if_new(record) is False

    def test_store_if_new_different_session(self):
        """Test store_if_new allows different session_ids."""
        memory = EngineeringMemory(in_memory_only=True)
        record1 = _make_record(session_id="sess-001")
        record2 = _make_record(session_id="sess-002")

        assert memory.store_if_new(record1) is True
        assert memory.store_if_new(record2) is True
        assert memory.session_count == 2


# ---------------------------------------------------------------------------
# Query Correctness Tests
# ---------------------------------------------------------------------------


class TestQueryCorrectness:
    """Tests for query method correctness."""

    def test_find_by_workflow(self):
        """Test find_by_workflow returns only matching sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(session_id="sess-001", workflow_name="bug-fix"))
        memory.store(_make_record(session_id="sess-002", workflow_name="feature-add"))
        memory.store(_make_record(session_id="sess-003", workflow_name="bug-fix"))

        results = memory.find_by_workflow("bug-fix")
        assert len(results) == 2
        assert all(r.workflow_name == "bug-fix" for r in results)

    def test_find_by_workflow_no_match(self):
        """Test find_by_workflow returns empty when no match."""
        memory = EngineeringMemory(in_memory_only=True)
        memory.store(_make_record(session_id="sess-001", workflow_name="bug-fix"))

        results = memory.find_by_workflow("nonexistent")
        assert results == ()

    def test_find_successful(self):
        """Test find_successful returns only COMPLETE sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(session_id="sess-001", controller_decision="COMPLETE"))
        memory.store(_make_record(session_id="sess-002", controller_decision="FAIL"))
        memory.store(_make_record(session_id="sess-003", controller_decision="COMPLETE"))

        results = memory.find_successful()
        assert len(results) == 2
        assert all(r.controller_decision == "COMPLETE" for r in results)

    def test_find_failed(self):
        """Test find_failed returns only non-COMPLETE sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(session_id="sess-001", controller_decision="COMPLETE"))
        memory.store(_make_record(session_id="sess-002", controller_decision="FAIL"))
        memory.store(_make_record(session_id="sess-003", controller_decision="RETRY"))

        results = memory.find_failed()
        assert len(results) == 2
        for r in results:
            assert r.controller_decision != "COMPLETE"

    def test_find_by_module(self):
        """Test find_by_module returns sessions that modified the module."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            modified_modules=["module_x", "module_y"],
        ))
        memory.store(_make_record(
            session_id="sess-002",
            modified_modules=["module_z"],
        ))
        memory.store(_make_record(
            session_id="sess-003",
            modified_modules=["module_x", "module_w"],
        ))

        results = memory.find_by_module("module_x")
        assert len(results) == 2
        ids = [r.session_id for r in results]
        assert "sess-001" in ids
        assert "sess-003" in ids

    def test_find_by_module_no_match(self):
        """Test find_by_module returns empty when no match."""
        memory = EngineeringMemory(in_memory_only=True)
        memory.store(_make_record(
            session_id="sess-001",
            modified_modules=["module_x"],
        ))

        results = memory.find_by_module("module_z")
        assert results == ()

    def test_recent_limit(self):
        """Test recent respects the limit parameter."""
        memory = EngineeringMemory(in_memory_only=True)

        for i in range(5):
            memory.store(_make_record(
                session_id=f"sess-00{i+1}",
                completed_at=f"2026-07-21T14:{40+i:02d}:00+00:00",
            ))

        recent = memory.recent(limit=3)
        assert len(recent) == 3

    def test_recent_exceeds_total(self):
        """Test recent returns all when limit exceeds total."""
        memory = EngineeringMemory(in_memory_only=True)

        for i in range(3):
            memory.store(_make_record(
                session_id=f"sess-00{i+1}",
                completed_at=f"2026-07-21T14:{40+i:02d}:00+00:00",
            ))

        recent = memory.recent(limit=10)
        assert len(recent) == 3

    def test_clear(self):
        """Test clear removes all sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(session_id="sess-001"))
        memory.store(_make_record(session_id="sess-002"))
        assert memory.session_count == 2

        memory.clear()
        assert memory.session_count == 0
        assert memory.list_sessions() == ()


# ---------------------------------------------------------------------------
# Statistics Tests
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for statistics computation."""

    def test_empty_statistics(self):
        """Test statistics with no sessions."""
        memory = EngineeringMemory(in_memory_only=True)
        stats = memory.statistics()

        assert stats.total_sessions == 0
        assert stats.successful_sessions == 0
        assert stats.failed_sessions == 0
        assert stats.average_evaluation_score == 0.0
        assert stats.average_iterations == 0.0
        assert stats.workflow_usage == {}

    def test_statistics_with_sessions(self):
        """Test statistics with multiple sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        # Successful session with score
        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
            iteration_count=3,
            evaluation_score=0.9,
        ))

        # Failed session
        memory.store(_make_record(
            session_id="sess-002",
            controller_decision="FAIL",
            iteration_count=2,
            evaluation_score=0.5,
        ))

        # Successful session without score
        memory.store(_make_record(
            session_id="sess-003",
            controller_decision="COMPLETE",
            iteration_count=1,
        ))

        stats = memory.statistics()

        assert stats.total_sessions == 3
        assert stats.successful_sessions == 2
        assert stats.failed_sessions == 1
        # Average of 0.9 and 0.5 (only sessions with scores)
        assert stats.average_evaluation_score == pytest.approx(0.7)
        # Average of 3, 2, 1
        assert stats.average_iterations == pytest.approx(2.0)
        assert stats.workflow_usage == {
            "bug-fix": 3,
        }

    def test_workflow_usage(self):
        """Test workflow_usage counts."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            workflow_name="bug-fix",
        ))
        memory.store(_make_record(
            session_id="sess-002",
            workflow_name="feature-add",
        ))
        memory.store(_make_record(
            session_id="sess-003",
            workflow_name="bug-fix",
        ))

        stats = memory.statistics()
        assert stats.workflow_usage == {
            "bug-fix": 2,
            "feature-add": 1,
        }

    def test_statistics_deterministic(self):
        """Test that statistics are deterministic across calls."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
            iteration_count=3,
            evaluation_score=0.9,
        ))

        stats1 = memory.statistics()
        stats2 = memory.statistics()

        assert stats1.total_sessions == stats2.total_sessions
        assert stats1.successful_sessions == stats2.successful_sessions
        assert stats1.average_evaluation_score == stats2.average_evaluation_score
        assert stats1.workflow_usage == stats2.workflow_usage