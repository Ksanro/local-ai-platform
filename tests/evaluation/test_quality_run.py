"""Tests for packages.evaluation.quality_run.

Verifies QualityRun/ProbeRun construction from both single-run and
--compare-context evaluations, including context-delta attachment and
mode/run-id behavior.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.evaluation.quality_harness_report import (
    evaluate_comparison,
    evaluate_results,
)
from packages.evaluation.quality_run import (
    ProbeRun,
    QualityRun,
    build_quality_run,
    build_quality_run_from_comparison,
)


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


class TestBuildQualityRun:
    def test_mode_is_single(self) -> None:
        report = evaluate_results([_result("a", hits=["f1"])])

        run = build_quality_run(report, model="qwen36")

        assert run.mode == "single"

    def test_totals_and_model_carried_through(self) -> None:
        report = evaluate_results(
            [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=100, seconds=1.5)]
        )

        run = build_quality_run(report, model="qwen36", gateway_commit="abc123")

        assert run.model == "qwen36"
        assert run.gateway_commit == "abc123"
        assert run.total_score == 1
        assert run.total_maximum == 2
        assert run.total_prompt_tokens == 100
        assert run.total_seconds == 1.5

    def test_probe_row_fields_carried_through(self) -> None:
        report = evaluate_results(
            [
                _result(
                    "a",
                    hits=["f1"],
                    misses=["f2"],
                    prompt_tokens=100,
                    seconds=1.5,
                    style_violations=["reasoning_preamble"],
                )
            ]
        )

        run = build_quality_run(report, model="qwen36")
        probe = run.probes[0]

        assert probe.id == "a"
        assert probe.intent == "SEARCH"
        assert probe.score == 1
        assert probe.maximum == 2
        assert probe.missing_facts == ("f2",)
        assert probe.style_violations == ("reasoning_preamble",)
        assert probe.prompt_tokens == 100
        assert probe.seconds == 1.5
        assert probe.error == ""
        assert run.style_ok_count == 0
        assert run.total_style_violations == 1

    def test_context_delta_fields_are_none_in_single_mode(self) -> None:
        report = evaluate_results([_result("a", hits=["f1"])])

        run = build_quality_run(report, model="qwen36")

        assert run.probes[0].context_score_delta is None
        assert run.probes[0].context_prompt_token_delta is None

    def test_probe_error_carried_through(self) -> None:
        report = evaluate_results([_result("a", error="TimeoutError: boom")])

        run = build_quality_run(report, model="qwen36")

        assert run.probes[0].error == "TimeoutError: boom"

    def test_explicit_run_id_is_used_verbatim(self) -> None:
        report = evaluate_results([_result("a")])

        run = build_quality_run(report, model="qwen36", run_id="fixed-id")

        assert run.run_id == "fixed-id"

    def test_auto_generated_run_ids_are_unique(self) -> None:
        report = evaluate_results([_result("a")])

        first = build_quality_run(report, model="qwen36")
        second = build_quality_run(report, model="qwen36")

        assert first.run_id != second.run_id


class TestBuildQualityRunFromComparison:
    def test_mode_is_compare_context(self) -> None:
        comparison = evaluate_comparison(
            {"context": [_result("a", hits=["f1"])], "no_context": [_result("a")]}
        )

        run = build_quality_run_from_comparison(comparison, model="qwen36")

        assert run.mode == "compare_context"

    def test_totals_come_from_with_context_side(self) -> None:
        comparison = evaluate_comparison(
            {
                "context": [_result("a", hits=["f1", "f2"], prompt_tokens=150)],
                "no_context": [
                    _result("a", hits=["f1"], misses=["f2"], prompt_tokens=50)
                ],
            }
        )

        run = build_quality_run_from_comparison(comparison, model="qwen36")

        assert run.total_score == 2
        assert run.total_maximum == 2
        assert run.total_prompt_tokens == 150

    def test_context_delta_fields_populated_and_matched_by_id(self) -> None:
        comparison = evaluate_comparison(
            {
                "context": [
                    _result("first", hits=["f1"], prompt_tokens=10),
                    _result("second", hits=["f1", "f2"], prompt_tokens=20),
                ],
                "no_context": [
                    _result("second", hits=["f1"], misses=["f2"], prompt_tokens=15),
                    _result("first", misses=["f1"], prompt_tokens=5),
                ],
            }
        )

        run = build_quality_run_from_comparison(comparison, model="qwen36")
        by_id = {probe.id: probe for probe in run.probes}

        assert by_id["first"].context_score_delta == 1
        assert by_id["first"].context_prompt_token_delta == 5
        assert by_id["second"].context_score_delta == 1
        assert by_id["second"].context_prompt_token_delta == 5

    def test_negative_context_delta_when_context_hurts(self) -> None:
        comparison = evaluate_comparison(
            {
                "context": [_result("a", misses=["f1"], prompt_tokens=200)],
                "no_context": [_result("a", hits=["f1"], prompt_tokens=40)],
            }
        )

        run = build_quality_run_from_comparison(comparison, model="qwen36")

        assert run.probes[0].context_score_delta == -1
        assert run.probes[0].context_prompt_token_delta == 160


class TestImmutability:
    def test_probe_run_is_frozen(self) -> None:
        probe = ProbeRun(
            id="a",
            intent="SEARCH",
            score=1,
            maximum=2,
            missing_facts=("f2",),
            style_violations=(),
            prompt_tokens=10,
            seconds=1.0,
            error="",
        )
        with pytest.raises(FrozenInstanceError):
            probe.score = 5  # type: ignore[misc]

    def test_quality_run_is_frozen(self) -> None:
        report = evaluate_results([_result("a")])
        run = build_quality_run(report, model="qwen36")
        with pytest.raises(FrozenInstanceError):
            run.total_score = 99  # type: ignore[misc]


def test_reexported_from_package() -> None:
    from packages.evaluation import QualityRun as ReexportedQualityRun

    assert ReexportedQualityRun is QualityRun
