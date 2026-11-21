"""Tests for the real-Cline A/B runner (``scripts/cline_ab.py``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.cline_ab import (
    ClineRun,
    answer_key_paths,
    build_record,
    main,
    parse_cline_events,
    prompt_for,
    summarize,
    unexpected_changes,
)
from scripts.quality_harness import QualityProbe, fact, turn

PROBE = QualityProbe(
    id="p1",
    intent="SEARCH",
    prompt="Where is X?",
    expect=(fact("apps/x.py"), fact("_extract_x")),
)


def _tool_event(name: str) -> str:
    return json.dumps(
        {
            "type": "agent_event",
            "event": {"type": "content_start", "contentType": "tool", "toolName": name},
        }
    )


def _result(**overrides: object) -> str:
    record: dict[str, object] = {
        "type": "run_result",
        "finishReason": "completed",
        "iterations": 3,
        "aggregateUsage": {"inputTokens": 1200, "outputTokens": 80},
        "durationMs": 4567,
        "text": "It is `_extract_x` in apps/x.py.",
    }
    record.update(overrides)
    return json.dumps(record)


def test_single_turn_prompt_is_unchanged() -> None:
    assert prompt_for(PROBE) == "Where is X?"


def test_history_is_folded_before_the_current_request() -> None:
    probe = QualityProbe(
        id="m",
        intent="EXPLAIN",
        prompt="And the second?",
        expect=(),
        history=(turn("user", "first question"), turn("assistant", "first answer")),
    )

    text = prompt_for(probe)

    assert text.index("[user]: first question") < text.index("[assistant]: first answer")
    assert text.endswith("Current request:\nAnd the second?")


def test_parse_counts_tool_starts_and_reads_the_result() -> None:
    stdout = "\n".join(
        [
            "not json",
            _tool_event("read_files"),
            _tool_event("read_files"),
            _tool_event("run_commands"),
            json.dumps(
                {"type": "agent_event", "event": {"type": "content_end", "contentType": "tool"}}
            ),
            _result(),
        ]
    )

    run = parse_cline_events(stdout)

    assert run == ClineRun(
        answer="It is `_extract_x` in apps/x.py.",
        finish="completed",
        iterations=3,
        input_tokens=1200,
        output_tokens=80,
        duration_s=4.6,
        tools={"read_files": 2, "run_commands": 1},
    )


def test_parse_falls_back_to_usage_when_aggregate_is_absent() -> None:
    run = parse_cline_events(
        _result(aggregateUsage=None, usage={"inputTokens": 7, "outputTokens": 2})
    )

    assert run is not None
    assert (run.input_tokens, run.output_tokens) == (7, 2)


def test_parse_without_run_result_is_none() -> None:
    assert parse_cline_events(_tool_event("read_files")) is None


def test_record_scores_the_answer_against_the_probe_facts() -> None:
    run = parse_cline_events(_result(text="See apps/x.py only."))

    record = build_record("gateway", PROBE, run, wall_s=5.0)

    assert record["hits"] == ["apps/x.py"]
    assert record["misses"] == ["_extract_x"]
    assert (record["score"], record["max"]) == (1, 2)
    assert record["error"] == ""


def test_missing_run_result_is_an_error_scoring_zero() -> None:
    record = build_record("direct", PROBE, None)

    assert record["error"] == "no run_result"
    assert record["score"] == 0
    assert record["max"] == 2


def test_explicit_error_is_kept_when_there_is_no_result() -> None:
    assert build_record("direct", PROBE, None, error="timeout")["error"] == "timeout"


def test_answer_key_paths_match_both_markers_only() -> None:
    tracked = [
        "scripts/quality_harness.py",
        "tests/scripts/test_probe_replay.py",
        "packages/evaluation/quality_harness_report.py",
        "apps/gateway/main.py",
        "docs/live-gateway-runbook.md",
    ]

    assert answer_key_paths(tracked) == tracked[:3]


def test_unexpected_changes_ignore_plain_deletions() -> None:
    porcelain = " D scripts/quality_harness.py\n M apps/gateway/main.py\n?? new.txt\n"

    assert unexpected_changes(porcelain) == [" M apps/gateway/main.py", "?? new.txt"]


def _row(arm: str, probe_id: str, score: int, **values: object) -> dict[str, object]:
    row: dict[str, object] = {
        "arm": arm,
        "id": probe_id,
        "score": score,
        "max": 2,
        "error": "",
        "finish": "completed",
        "iterations": 2,
        "tool_calls": 2,
        "input_tokens": 1000,
        "output_tokens": 100,
        "duration_s": 10.0,
        "tools": {"read_files": 2},
    }
    row.update(values)
    return row


def test_summary_totals_each_arm_and_pairs_probes() -> None:
    records = [
        _row("gateway", "a", 2),
        _row("direct", "a", 1, iterations=6, error="timeout"),
        _row("gateway", "b", 2, input_tokens=3000),
    ]

    lines = summarize(records)

    assert "== gateway (2 runs)" in lines
    assert "facts            4/4" in lines
    assert "== direct (1 runs)" in lines
    assert any(line.startswith("errors           1") for line in lines)
    pair = next(line for line in lines if line.startswith("a "))
    assert "2/2 i 2" in pair and "1/2 i 6" in pair and pair.endswith("ERR")
    assert next(line for line in lines if line.startswith("b ")).endswith("| -")


def test_main_summarize_reads_a_run_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(json.dumps(_row("gateway", "a", 1)) + "\n\n", encoding="utf-8")

    assert main(["--summarize", str(path)]) == 0
    assert "facts            1/2" in capsys.readouterr().out


def test_main_requires_out_without_summarize() -> None:
    with pytest.raises(SystemExit):
        main([])
