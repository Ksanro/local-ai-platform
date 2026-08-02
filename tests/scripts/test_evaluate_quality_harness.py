"""Tests for scripts/evaluate_quality_harness.py.

Invokes the script's main() directly against temp JSON files and stdin,
asserting concrete score/delta values and exit codes rather than just
"ran without error", per TESTING.md's discipline.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from packages.engineering_memory.memory import EngineeringMemory
from scripts.evaluate_quality_harness import main


def _write(tmp_path: Path, name: str, payload: object) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _result(id: str, **overrides: object) -> dict:  # noqa: A002
    base = {
        "id": id,
        "intent": "SEARCH",
        "ok": True,
        "answer": "answer text",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "seconds": 0.0,
        "hits": [],
        "misses": [],
        "error": "",
        "metadata": {},
    }
    base.update(overrides)
    return base


class TestSingleRun:
    def test_json_output_reports_correct_total_score(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = [
            _result("a", hits=["f1"], misses=["f2"], prompt_tokens=100, seconds=1.5),
            _result("b", hits=["f1", "f2"], prompt_tokens=50, seconds=0.5),
        ]
        path = _write(tmp_path, "run.json", payload)

        exit_code = main([path, "--json"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["total_score"] == 3
        assert out["total_maximum"] == 4
        assert out["total_prompt_tokens"] == 150
        assert out["total_seconds"] == 2.0
        assert out["probes"][0]["missing_facts"] == ["f2"]

    def test_table_output_contains_total_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=10)]
        path = _write(tmp_path, "run.json", payload)

        exit_code = main([path])

        out = capsys.readouterr().out
        assert exit_code == 0
        assert "TOTAL" in out
        assert "1/2" in out

    def test_reads_utf8_bom_json_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = [_result("a", hits=["f1"], prompt_tokens=10)]
        path = tmp_path / "bom.json"
        path.write_text(json.dumps(payload), encoding="utf-8-sig")

        exit_code = main([str(path), "--json"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["total_score"] == 1

    def test_probe_error_causes_nonzero_exit(self, tmp_path: Path) -> None:
        payload = [_result("a", ok=False, error="TimeoutError: boom")]
        path = _write(tmp_path, "run.json", payload)

        exit_code = main([path])

        assert exit_code == 1

    def test_reads_from_stdin_dash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = [_result("a", hits=["f1"], prompt_tokens=10)]
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

        exit_code = main(["-", "--json"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["total_score"] == 1


class TestComparisonRun:
    def test_json_output_reports_correct_context_delta(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = {
            "context": [_result("a", hits=["f1", "f2"], prompt_tokens=150)],
            "no_context": [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=50)],
        }
        path = _write(tmp_path, "cmp.json", payload)

        exit_code = main([path, "--json"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["total_score_delta"] == 1
        assert out["total_prompt_token_delta"] == 100
        assert out["deltas"] == [{"id": "a", "score_delta": 1, "prompt_token_delta": 100}]

    def test_table_output_contains_delta_total(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = {
            "context": [_result("a", hits=["f1"], prompt_tokens=100)],
            "no_context": [_result("a", misses=["f1"], prompt_tokens=20)],
        }
        path = _write(tmp_path, "cmp.json", payload)

        exit_code = main([path])

        out = capsys.readouterr().out
        assert exit_code == 0
        assert "WITH CONTEXT" in out
        assert "WITHOUT CONTEXT" in out

    def test_error_in_either_side_causes_nonzero_exit(self, tmp_path: Path) -> None:
        payload = {
            "context": [_result("a", ok=False, error="boom")],
            "no_context": [_result("a")],
        }
        path = _write(tmp_path, "cmp.json", payload)

        exit_code = main([path])

        assert exit_code == 1


def test_invalid_payload_shape_returns_error_exit_code(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.json", {"unexpected": "shape"})

    exit_code = main([path])

    assert exit_code == 2


class TestPersist:
    def test_persist_stores_single_run_record(self, tmp_path: Path) -> None:
        payload = [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=100)]
        run_path = _write(tmp_path, "run.json", payload)
        storage_path = str(tmp_path / "memory.json")

        exit_code = main(
            [
                run_path,
                "--persist",
                "--model",
                "qwen36",
                "--notes",
                "unit test",
                "--storage-path",
                storage_path,
            ]
        )

        assert exit_code == 0
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].workflow_name == "quality_harness"
        assert sessions[0].evaluation_report["total_score"] == 1
        assert sessions[0].metadata["model"] == "qwen36"
        assert sessions[0].metadata["notes"] == "unit test"

    def test_persist_stores_comparison_record(self, tmp_path: Path) -> None:
        payload = {
            "context": [_result("a", hits=["f1", "f2"], prompt_tokens=150)],
            "no_context": [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=50)],
        }
        run_path = _write(tmp_path, "cmp.json", payload)
        storage_path = str(tmp_path / "memory.json")

        exit_code = main(
            [run_path, "--persist", "--model", "qwen36", "--storage-path", storage_path]
        )

        assert exit_code == 0
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].workflow_name == "quality_harness_compare"
        assert sessions[0].evaluation_report["total_score_delta"] == 1

    def test_persist_preserves_existing_records(self, tmp_path: Path) -> None:
        storage_path = str(tmp_path / "memory.json")
        first_payload = [_result("first", hits=["f1"])]
        second_payload = [_result("second", hits=["f2"])]
        first_path = _write(tmp_path, "first.json", first_payload)
        second_path = _write(tmp_path, "second.json", second_payload)

        first_exit = main(
            [first_path, "--persist", "--model", "qwen36", "--storage-path", storage_path]
        )
        second_exit = main(
            [second_path, "--persist", "--model", "qwen36", "--storage-path", storage_path]
        )

        assert first_exit == 0
        assert second_exit == 0
        memory = EngineeringMemory(storage_path=storage_path)
        memory.reload()
        sessions = memory.list_sessions()
        assert len(sessions) == 2
        assert [session.evaluation_report["probes"][0]["id"] for session in sessions] == [
            "first",
            "second",
        ]

    def test_without_persist_flag_nothing_is_stored(self, tmp_path: Path) -> None:
        payload = [_result("a", hits=["f1"])]
        run_path = _write(tmp_path, "run.json", payload)
        storage_path = tmp_path / "memory.json"

        main([run_path])

        assert not storage_path.exists()


class TestQualityRun:
    def test_single_run_prints_quality_run_json_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=100)]
        run_path = _write(tmp_path, "run.json", payload)

        exit_code = main([run_path, "--quality-run", "--model", "qwen36"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["mode"] == "single"
        assert out["model"] == "qwen36"
        assert out["total_score"] == 1
        assert out["probes"][0]["missing_facts"] == ["f2"]
        assert out["probes"][0]["context_score_delta"] is None

    def test_comparison_run_includes_context_delta(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = {
            "context": [_result("a", hits=["f1", "f2"], prompt_tokens=150)],
            "no_context": [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=50)],
        }
        run_path = _write(tmp_path, "cmp.json", payload)

        exit_code = main([run_path, "--quality-run", "--model", "qwen36"])

        out = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert out["mode"] == "compare_context"
        assert out["probes"][0]["context_score_delta"] == 1
        assert out["probes"][0]["context_prompt_token_delta"] == 100

    def test_quality_run_path_writes_file_instead_of_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = [_result("a", hits=["f1"])]
        run_path = _write(tmp_path, "run.json", payload)
        out_path = tmp_path / "summary.json"

        exit_code = main(
            [
                run_path,
                "--quality-run",
                "--model",
                "qwen36",
                "--quality-run-path",
                str(out_path),
            ]
        )

        assert exit_code == 0
        assert capsys.readouterr().out == ""
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written["total_score"] == 1
        assert written["model"] == "qwen36"

    def test_quality_run_path_creates_parent_directories(
        self, tmp_path: Path
    ) -> None:
        payload = [_result("a", hits=["f1"])]
        run_path = _write(tmp_path, "run.json", payload)
        out_path = tmp_path / "nested" / "summaries" / "summary.json"

        exit_code = main(
            [
                run_path,
                "--quality-run",
                "--model",
                "qwen36",
                "--quality-run-path",
                str(out_path),
            ]
        )

        assert exit_code == 0
        assert out_path.exists()

    def test_quality_run_does_not_persist_by_itself(self, tmp_path: Path) -> None:
        payload = [_result("a", hits=["f1"])]
        run_path = _write(tmp_path, "run.json", payload)
        storage_path = tmp_path / "memory.json"

        main([run_path, "--quality-run", "--model", "qwen36"])

        assert not storage_path.exists()
