"""Tests for ``packages.engineering_memory.session_log_records``."""

from __future__ import annotations

from pathlib import Path

from packages.engineering_memory.session_log_records import (
    WORKFLOW_NAME,
    build_session_log_record,
    read_session_log_lines,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "session_log_fixture.jsonl"


class TestReadSessionLogLines:
    """Tests for ``read_session_log_lines``."""

    def test_reads_all_fixture_lines(self) -> None:
        records = read_session_log_lines(str(FIXTURE_PATH))
        assert len(records) == 10

    def test_returns_empty_list_for_missing_file(self) -> None:
        assert read_session_log_lines("/nonexistent/path.jsonl") == []

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        p.write_text(
            '{"a": 1}\n\n{"a": 2}\n\n',
            encoding="utf-8",
        )
        assert len(read_session_log_lines(str(p))) == 2

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        p.write_text(
            '{"a": 1}\nNOT_JSON\n{"a": 2}\n',
            encoding="utf-8",
        )
        records = read_session_log_lines(str(p))
        assert len(records) == 2
        assert records[0]["a"] == 1
        assert records[1]["a"] == 2


class TestBuildSessionLogRecord:
    """Tests for ``build_session_log_record``."""

    def test_maps_request_id_to_session_id(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[0]
        record = build_session_log_record(raw)
        assert record.session_id == "aaaa-1111"

    def test_generates_uuid_when_request_id_missing(self) -> None:
        raw = {"timestamp": "2026-01-01T00:00:00.000Z", "model": "qwen36"}
        record = build_session_log_record(raw)
        assert record.session_id  # non-empty UUID string
        assert record.session_id != ""

    def test_sets_workflow_name(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[0]
        record = build_session_log_record(raw)
        assert record.workflow_name == WORKFLOW_NAME

    def test_maps_ok_status_to_COMPLETE(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[0]
        record = build_session_log_record(raw)
        assert record.controller_decision == "COMPLETE"

    def test_maps_error_status_to_FAIL(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[8]  # line 9, status=error
        record = build_session_log_record(raw)
        assert record.controller_decision == "FAIL"

    def test_normalizes_z_timestamp(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[0]
        record = build_session_log_record(raw)
        assert record.completed_at == "2026-07-25T10:00:00.000+00:00"

    def test_carrying_full_metadata(self) -> None:
        raw = read_session_log_lines(str(FIXTURE_PATH))[0]
        record = build_session_log_record(raw)
        assert record.metadata["model"] == "qwen36"
        assert record.metadata["intent"] == "EXPLAIN"
        assert record.metadata["context"]["status"] == "assembled"

    def test_defensive_access_for_missing_planning_key(self) -> None:
        # Fixture line 10 (index 9) has no "planning" key
        raw = read_session_log_lines(str(FIXTURE_PATH))[9]
        # Should not raise KeyError
        record = build_session_log_record(raw)
        assert record.metadata["planning"] == {}

    def test_defensive_access_for_missing_history_key(self) -> None:
        # Fixture line 10 (index 9) has no "history" key
        raw = read_session_log_lines(str(FIXTURE_PATH))[9]
        record = build_session_log_record(raw)
        assert record.metadata["history"] == {}

    def test_empty_record_does_not_raise(self) -> None:
        raw = {}
        record = build_session_log_record(raw)
        assert record.workflow_name == WORKFLOW_NAME
        assert record.controller_decision == "FAIL"
        assert record.metadata["model"] == ""
        assert record.metadata["context"] == {}
