"""Tests for failed session recording.

Covers:
- Failed sessions are stored correctly
- Failed sessions are distinguishable from successful ones
- Failed sessions appear in find_failed()
- Failed sessions do NOT appear in find_successful()
- Failed session reports are preserved
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
    execution_report: dict | None = None,
    verification_report: dict | None = None,
    evaluation_report: dict | None = None,
) -> EngineeringSessionRecord:
    """Create a test EngineeringSessionRecord."""
    metadata: dict = {"iteration_count": iteration_count}
    if modified_modules:
        metadata["modified_modules"] = modified_modules

    eval_report: dict = evaluation_report or {}
    if evaluation_score is not None:
        eval_report["overall_score"] = evaluation_score

    return EngineeringSessionRecord(
        session_id=session_id,
        workflow_name=workflow_name,
        request_summary=f"Task for {session_id}",
        transaction_id=f"txn-{session_id}",
        execution_report=execution_report or {"status": "COMPLETED"},
        verification_report=verification_report or {"status": "PASSED"},
        evaluation_report=eval_report,
        controller_decision=controller_decision,
        completed_at=completed_at,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Failed Session Recording Tests
# ---------------------------------------------------------------------------


class TestFailedSessionRecording:
    """Tests for failed session recording."""

    def test_failed_session_stored(self):
        """Test that failed sessions are stored correctly."""
        memory = EngineeringMemory(in_memory_only=True)

        failed_record = _make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
            completed_at="2026-07-21T14:50:00+00:00",
            execution_report={"status": "FAILED", "error": "timeout"},
            verification_report={"status": "SKIPPED"},
            evaluation_report={"overall_score": 0.0},
        )

        memory.store(failed_record)

        assert memory.session_count == 1
        retrieved = memory.find_session("sess-fail-001")
        assert retrieved is not None
        assert retrieved.controller_decision == "FAIL"
        assert retrieved.execution_report["status"] == "FAILED"

    def test_failed_session_in_find_failed(self):
        """Test that failed sessions appear in find_failed()."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
        ))
        memory.store(_make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
        ))
        memory.store(_make_record(
            session_id="sess-002",
            controller_decision="COMPLETE",
        ))

        failed = memory.find_failed()
        assert len(failed) == 1
        assert failed[0].session_id == "sess-fail-001"

    def test_failed_session_not_in_find_successful(self):
        """Test that failed sessions do NOT appear in find_successful()."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
        ))
        memory.store(_make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
        ))

        successful = memory.find_successful()
        ids = [r.session_id for r in successful]
        assert "sess-fail-001" not in ids
        assert len(successful) == 1
        assert successful[0].session_id == "sess-001"

    def test_failed_session_preserves_reports(self):
        """Test that failed session reports are preserved."""
        memory = EngineeringMemory(in_memory_only=True)

        failed_record = _make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
            execution_report={
                "status": "FAILED",
                "error": "connection_timeout",
                "attempts": 3,
            },
            verification_report={
                "status": "SKIPPED",
                "reason": "execution_failed",
            },
            evaluation_report={
                "overall_score": 0.0,
                "reason": "execution_failed",
            },
        )

        memory.store(failed_record)
        retrieved = memory.find_session("sess-fail-001")

        assert retrieved is not None
        assert retrieved.execution_report["error"] == "connection_timeout"
        assert retrieved.verification_report["status"] == "SKIPPED"
        assert retrieved.evaluation_report["overall_score"] == 0.0

    def test_mixed_successful_and_failed(self):
        """Test storing both successful and failed sessions."""
        memory = EngineeringMemory(in_memory_only=True)

        records = [
            _make_record(session_id="sess-001", controller_decision="COMPLETE"),
            _make_record(session_id="sess-fail-001", controller_decision="FAIL"),
            _make_record(session_id="sess-002", controller_decision="COMPLETE"),
            _make_record(session_id="sess-fail-002", controller_decision="RETRY"),
            _make_record(session_id="sess-003", controller_decision="COMPLETE"),
        ]

        for record in records:
            memory.store(record)

        # Total count
        assert memory.session_count == 5

        # Successful count
        successful = memory.find_successful()
        assert len(successful) == 3

        # Failed count
        failed = memory.find_failed()
        assert len(failed) == 2

        # Verify no overlap
        successful_ids = {r.session_id for r in successful}
        failed_ids = {r.session_id for r in failed}
        assert successful_ids.isdisjoint(failed_ids)

    def test_failed_decision_variants(self):
        """Test that all non-COMPLETE decisions are considered failed."""
        memory = EngineeringMemory(in_memory_only=True)

        decisions = ["FAIL", "RETRY", "REQUEST_REVIEW"]

        for i, decision in enumerate(decisions):
            memory.store(_make_record(
                session_id=f"sess-{decision.lower()}-001",
                controller_decision=decision,
            ))

        failed = memory.find_failed()
        assert len(failed) == 3

        successful = memory.find_successful()
        assert len(successful) == 0

    def test_failed_session_in_recent(self):
        """Test that failed sessions appear in recent results."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:50:00+00:00",
        ))
        memory.store(_make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
            completed_at="2026-07-21T14:55:00+00:00",
        ))

        recent = memory.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].session_id == "sess-fail-001"

    def test_failed_session_module_tracking(self):
        """Test that failed sessions track modified modules."""
        memory = EngineeringMemory(in_memory_only=True)

        failed_record = _make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
            modified_modules=["module_x", "module_y"],
        )

        memory.store(failed_record)

        # Should be findable by module
        by_module = memory.find_by_module("module_x")
        assert len(by_module) == 1
        assert by_module[0].session_id == "sess-fail-001"

        by_module = memory.find_by_module("module_y")
        assert len(by_module) == 1
        assert by_module[0].session_id == "sess-fail-001"

    def test_failed_session_statistics(self):
        """Test that failed sessions are included in statistics."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
            iteration_count=3,
            evaluation_score=0.9,
        ))
        memory.store(_make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
            iteration_count=5,
            evaluation_score=0.3,
        ))

        stats = memory.statistics()

        assert stats.total_sessions == 2
        assert stats.successful_sessions == 1
        assert stats.failed_sessions == 1
        # Average of 0.9 and 0.3
        assert stats.average_evaluation_score == pytest.approx(0.6)
        # Average of 3 and 5
        assert stats.average_iterations == pytest.approx(4.0)

    def test_failed_session_persistence(self):
        """Test that failed sessions are persisted to disk."""
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            from packages.engineering_memory.persistence import MemoryStorage

            storage = MemoryStorage(storage_path=path)

            failed_record = _make_record(
                session_id="sess-fail-001",
                controller_decision="FAIL",
                execution_report={"status": "FAILED"},
            )

            storage.save([failed_record])
            loaded = storage.load()

            assert len(loaded) == 1
            assert loaded[0].controller_decision == "FAIL"
            assert loaded[0].execution_report["status"] == "FAILED"
        finally:
            if path.exists():
                path.unlink()

    def test_failed_session_deterministic_ordering(self):
        """Test that failed sessions are deterministically ordered."""
        memory = EngineeringMemory(in_memory_only=True)

        # Store in random order
        for sid in ["sess-fail-003", "sess-fail-001", "sess-fail-002"]:
            memory.store(_make_record(
                session_id=sid,
                controller_decision="FAIL",
            ))

        failed = memory.find_failed()
        ids = [r.session_id for r in failed]
        assert ids == ["sess-fail-001", "sess-fail-002", "sess-fail-003"]

    def test_failed_session_not_affecting_successful_count(self):
        """Test that failed sessions don't affect successful session count."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-001",
            controller_decision="COMPLETE",
        ))
        memory.store(_make_record(
            session_id="sess-002",
            controller_decision="COMPLETE",
        ))
        memory.store(_make_record(
            session_id="sess-fail-001",
            controller_decision="FAIL",
        ))

        successful = memory.find_successful()
        assert len(successful) == 2

        failed = memory.find_failed()
        assert len(failed) == 1

    def test_failed_session_request_review(self):
        """Test REQUEST_REVIEW is considered a failed session."""
        memory = EngineeringMemory(in_memory_only=True)

        memory.store(_make_record(
            session_id="sess-review-001",
            controller_decision="REQUEST_REVIEW",
        ))

        failed = memory.find_failed()
        assert len(failed) == 1
        assert failed[0].session_id == "sess-review-001"

        successful = memory.find_successful()
        assert len(successful) == 0