"""Tests for ``scripts/ingest_session_log``.

Uses the same pattern as ``tests/scripts/test_evaluate_quality_harness.py``
(test_persist_stores_single_run_record, test_persist_preserves_existing_records)
rather than test_quality_history.py — that file only reads already-persisted
memory, it never tests a script that reads external input and persists.
"""

from __future__ import annotations

import json
from pathlib import Path

from packages.engineering_memory import EngineeringMemory
from scripts.ingest_session_log import main

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "session_log_fixture.jsonl"


def _write_jsonl(tmp_path: Path, name: str, records: list[dict]) -> str:
    """Write records as JSONL and return the file path."""
    p = tmp_path / name
    p.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )
    return str(p)


class TestIngestSessionLog:
    """Tests for the ingest_session_log CLI script."""

    def test_ingest_stores_all_fixture_records(self, tmp_path: Path) -> None:
        """Ingesting the fixture stores exactly 10 gateway_session records."""
        storage_path = str(tmp_path / "memory.json")

        exit_code = main(
            [
                "--session-log-path",
                str(FIXTURE_PATH),
                "--storage-path",
                storage_path,
            ]
        )

        assert exit_code == 0
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        assert len(sessions) == 10
        assert all(s.workflow_name == "gateway_session" for s in sessions)

    def test_ingest_preserves_existing_records(self, tmp_path: Path) -> None:
        """Running ingest twice does not overwrite previously stored records.

        Follows the same shape as
        ``test_evaluate_quality_harness.py::test_persist_preserves_existing_records``:
        run the ingest CLI twice, reload, and assert both record sets survive.
        """
        storage_path = str(tmp_path / "memory.json")

        # First ingest: store the full fixture (10 records)
        first_exit = main(
            [
                "--session-log-path",
                str(FIXTURE_PATH),
                "--storage-path",
                storage_path,
            ]
        )

        # Second ingest: store the same fixture again (should be no-ops)
        second_exit = main(
            [
                "--session-log-path",
                str(FIXTURE_PATH),
                "--storage-path",
                storage_path,
            ]
        )

        assert first_exit == 0
        assert second_exit == 0

        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        # Still 10 records — duplicates were not re-added
        assert len(sessions) == 10

    def test_ingest_with_different_input_preserves_both(self, tmp_path: Path) -> None:
        """Ingest two different files; both record sets survive."""
        storage_path = str(tmp_path / "memory.json")

        # First file: 3 records
        first_records = [
            {
                "timestamp": "2026-01-01T00:00:00.000Z",
                "request_id": "first-1",
                "model": "model-a",
                "intent": "EXPLAIN",
                "status": "ok",
            },
            {
                "timestamp": "2026-01-01T00:00:01.000Z",
                "request_id": "first-2",
                "model": "model-a",
                "intent": "EXPLAIN",
                "status": "ok",
            },
            {
                "timestamp": "2026-01-01T00:00:02.000Z",
                "request_id": "first-3",
                "model": "model-a",
                "intent": "DEBUG",
                "status": "error",
                "error": "test error",
            },
        ]
        first_path = _write_jsonl(tmp_path, "first.jsonl", first_records)

        # Second file: 2 records
        second_records = [
            {
                "timestamp": "2026-02-01T00:00:00.000Z",
                "request_id": "second-1",
                "model": "model-b",
                "intent": "IMPLEMENT",
                "status": "ok",
            },
            {
                "timestamp": "2026-02-01T00:00:01.000Z",
                "request_id": "second-2",
                "model": "model-b",
                "intent": "TEST",
                "status": "ok",
            },
        ]
        second_path = _write_jsonl(tmp_path, "second.jsonl", second_records)

        first_exit = main(
            ["--session-log-path", first_path, "--storage-path", storage_path]
        )
        second_exit = main(
            ["--session-log-path", second_path, "--storage-path", storage_path]
        )

        assert first_exit == 0
        assert second_exit == 0

        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        assert len(sessions) == 5
        session_ids = {s.session_id for s in sessions}
        assert "first-1" in session_ids
        assert "first-3" in session_ids
        assert "second-1" in session_ids
        assert "second-2" in session_ids

    def test_json_output_is_valid(self, tmp_path: Path) -> None:
        """--json flag produces valid JSON."""
        storage_path = str(tmp_path / "memory.json")

        import io
        import sys
        captured = io.StringIO()
        try:
            old_stdout = sys.stdout
            sys.stdout = captured
            exit_code = main(
                [
                    "--session-log-path",
                    str(FIXTURE_PATH),
                    "--storage-path",
                    storage_path,
                    "--json",
                ]
            )
        finally:
            sys.stdout = old_stdout

        assert exit_code == 0
        output = captured.getvalue()
        data = json.loads(output)
        assert "total_records" in data
        assert data["total_records"] == 10

    def test_missing_session_log_file_returns_empty(self, tmp_path: Path) -> None:
        """Ingesting a nonexistent file produces no records."""
        storage_path = str(tmp_path / "memory.json")

        exit_code = main(
            [
                "--session-log-path",
                "/nonexistent/sessions.jsonl",
                "--storage-path",
                storage_path,
            ]
        )

        assert exit_code == 0
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        assert len(memory.list_sessions()) == 0

    def test_success_and_failure_counts(self, tmp_path: Path) -> None:
        """Summary correctly counts success vs failure."""
        storage_path = str(tmp_path / "memory.json")

        import io
        import sys
        captured = io.StringIO()
        try:
            old_stdout = sys.stdout
            sys.stdout = captured
            exit_code = main(
                [
                    "--session-log-path",
                    str(FIXTURE_PATH),
                    "--storage-path",
                    storage_path,
                    "--json",
                ]
            )
        finally:
            sys.stdout = old_stdout

        assert exit_code == 0
        data = json.loads(captured.getvalue())
        assert data["success_count"] == 9
        assert data["failure_count"] == 1



