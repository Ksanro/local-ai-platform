"""Tests for ``packages.observability.session_log_history``."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.engineering_memory import EngineeringMemory
from packages.engineering_memory.session_log_records import (
    build_session_log_record,
    read_session_log_lines,
)
from packages.observability.session_log_history import (
    SessionLogSummary,
    build_session_log_summary,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "session_log_fixture.jsonl"


@pytest.fixture()
def _memory_with_gateway_sessions(tmp_path: Path) -> EngineeringMemory:
    """Seed an EngineeringMemory with all 10 fixture session-log records."""
    storage_path = str(tmp_path / "memory.json")
    memory = EngineeringMemory(storage_path=storage_path)
    memory.reload()
    for raw in read_session_log_lines(str(FIXTURE_PATH)):
        memory.store(build_session_log_record(raw))
    memory.reload()
    return memory


class TestBuildSessionLogSummary:
    """Tests for ``build_session_log_summary``."""

    def test_empty_memory_returns_zero_summary(self, tmp_path: Path) -> None:
        storage_path = str(tmp_path / "memory.json")
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        summary = build_session_log_summary(memory)
        assert summary.total_records == 0
        assert summary.success_count == 0
        assert summary.failure_count == 0
        assert summary.success_rate == 0.0
        assert summary.recent_records == []

    def test_counts_all_records(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert summary.total_records == 10

    def test_counts_success_and_failure(
        self, _memory_with_gateway_sessions: EngineeringMemory
    ) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert summary.success_count == 9
        assert summary.failure_count == 1

    def test_success_rate(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert abs(summary.success_rate - 0.9) < 0.001

    def test_error_breakdown(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert len(summary.error_breakdown) == 1
        assert "Provider connection failed" in summary.error_breakdown

    def test_avg_total_ms(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert summary.avg_total_ms is not None
        # (3200+4100+5000+6000+4500+800+8000+3500+200+7000) / 10 = 4230.0
        assert abs(summary.avg_total_ms - 4230.0) < 1.0

    def test_avg_provider_wait_ms(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert summary.avg_provider_wait_ms is not None

    def test_intent_distribution(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert "EXPLAIN" in summary.intent_distribution
        assert summary.intent_distribution["EXPLAIN"] == 2

    def test_model_distribution(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert "qwen36" in summary.model_distribution
        assert summary.model_distribution["qwen36"] == 10

    def test_recent_records_sorted_descending(
        self, _memory_with_gateway_sessions: EngineeringMemory
    ) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert len(summary.recent_records) == 10
        # Most recent should be last in fixture (gggg-aaaa, timestamp 10:06)
        assert summary.recent_records[0]["session_id"] == "gggg-aaaa"

    def test_recent_limit(self, _memory_with_gateway_sessions: EngineeringMemory) -> None:
        summary = build_session_log_summary(
            _memory_with_gateway_sessions, recent_limit=3
        )
        assert len(summary.recent_records) == 3

    def test_history_cap_rate_zero_when_no_history(
        self, _memory_with_gateway_sessions: EngineeringMemory
    ) -> None:
        summary = build_session_log_summary(_memory_with_gateway_sessions)
        assert summary.history_cap_rate == 0.0

    def test_workflow_filtering_isolates_gateway_session(self, tmp_path: Path) -> None:
        """Verify find_by_workflow filters correctly — not memory.recent()."""
        storage_path = str(tmp_path / "memory.json")
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()

        # Store a quality_harness record (different workflow)
        from packages.engineering_memory.models import EngineeringSessionRecord
        memory.store(
            EngineeringSessionRecord(
                session_id="quality-1",
                workflow_name="quality_harness",
                request_summary="quality run",
                transaction_id="quality-1",
                evaluation_report={},
                controller_decision="COMPLETE",
                completed_at="2026-08-01T00:00:00+00:00",
            )
        )

        # Store gateway session records
        for raw in read_session_log_lines(str(FIXTURE_PATH)):
            memory.store(build_session_log_record(raw))

        memory.reload()

        summary = build_session_log_summary(memory)
        assert summary.total_records == 10  # only gateway_session, not quality_harness


class TestSessionLogSummaryDataclass:
    """Tests for SessionLogSummary dataclass properties."""

    def test_frozen(self) -> None:
        with pytest.raises(Exception):
            s = SessionLogSummary()
            s.total_records = 1  # type: ignore

    def test_default_values(self) -> None:
        s = SessionLogSummary()
        assert s.total_records == 0
        assert s.success_rate == 0.0
        assert s.error_breakdown == {}
        assert s.recent_records == []



