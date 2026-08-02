"""Tests for scripts/quality_history.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.quality_harness_records import (
    build_quality_harness_record,
)
from packages.evaluation.quality_harness_report import evaluate_results
from scripts.quality_history import main


def _result(id: str, **overrides: object) -> dict:  # noqa: A002
    base = {
        "id": id,
        "intent": "SEARCH",
        "hits": [],
        "misses": [],
        "prompt_tokens": 0,
        "seconds": 0.0,
        "error": "",
    }
    base.update(overrides)
    return base


def _store_record(storage_path: str) -> None:
    report = evaluate_results(
        [_result("probe", hits=["f1"], misses=["f2"], prompt_tokens=100)]
    )
    record = build_quality_harness_record(
        report,
        model="qwen36",
        session_id="quality-run",
    )
    memory = EngineeringMemory(storage_path=storage_path)
    memory.store(record)


def test_json_output_contains_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    storage_path = str(tmp_path / "memory.json")
    _store_record(storage_path)

    exit_code = main(["--storage-path", storage_path, "--json"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["total_records"] == 1
    assert out["quality_harness_runs"] == 1
    assert out["workflows"][0]["latest_session_id"] == "quality-run"
    assert out["recent_missing_facts"][0]["probe_id"] == "probe"


def test_table_output_contains_workflow_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage_path = str(tmp_path / "memory.json")
    _store_record(storage_path)

    exit_code = main(["--storage-path", storage_path])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "QUALITY HARNESS HISTORY" in out
    assert "quality_harness" in out
    assert "RECENT MISSING FACTS" in out


def test_empty_storage_outputs_zero_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage_path = str(tmp_path / "missing.json")

    exit_code = main(["--storage-path", storage_path, "--json"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["total_records"] == 0
    assert out["workflows"] == []
