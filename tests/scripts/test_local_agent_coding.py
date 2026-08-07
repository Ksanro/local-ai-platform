"""Tests for scripts/local_agent_coding.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.local_agent_coding import TASKS, main


def test_task_catalog_has_fixed_first_local_coding_task() -> None:
    """The initial task should stay stable enough for agent-to-agent comparison."""
    task = TASKS[0]

    assert task.id == "style_preamble_cleanup"
    assert "scripts/quality_harness.py" in task.expected_files
    assert "packages/providers/vllm.py" in task.expected_files
    assert [step.role for step in task.workflow] == ["plan", "code", "review", "coordinate"]
    assert "Do not activate dormant" in task.workflow[1].prompt


def test_list_outputs_task_ids(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["list"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "style_preamble_cleanup" in out
    assert "Reduce Reasoning Preamble Chatter" in out


def test_show_outputs_verbatim_task_block(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["show", "style_preamble_cleanup"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "WORKFLOW" in out
    assert "plan: Cline with qwen3.6 27B dense" in out
    assert "code: Claude extension with local qwen3.6 35B A3B" in out
    assert "SUCCESS" in out


def test_show_json_outputs_verification_displays(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["show", "style_preamble_cleanup", "--json"])

    out = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert out["id"] == "style_preamble_cleanup"
    assert out["workflow"][0]["role"] == "plan"
    assert out["verification"][0]["display"].startswith(".\\uv.exe run python -m pytest")
    assert out["verification"][0]["argv"][0] == ".\\uv.exe"


def test_step_outputs_role_specific_prompt(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["step", "style_preamble_cleanup", "code"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Claude extension with local qwen3.6 35B A3B" in out
    assert "PROMPT" in out
    assert ".\\uv.exe run python -m pytest" in out


def test_step_can_append_handoff_notes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    notes = tmp_path / "plan.md"
    notes.write_text("Cline says: use the quality harness prompt.", encoding="utf-8")

    exit_code = main(
        [
            "step",
            "style_preamble_cleanup",
            "code",
            "--notes-file",
            str(notes),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Handoff notes from the previous step:" in out
    assert "Cline says: use the quality harness prompt." in out


def test_verify_dry_run_prints_commands_without_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["verify", "style_preamble_cleanup", "--dry-run"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert ".\\uv.exe run python -m pytest" in out
    assert ".\\uv.exe run python -m ruff check" in out


def test_unknown_task_exits_with_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown task"):
        main(["show", "missing"])
