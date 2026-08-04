"""Tests for packages.evaluation.quality_harness_report.

Verifies score/maximum recomputation, missing-fact/token/latency pass-through,
and context-delta computation against the real quality_harness.py --json shape.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.evaluation.quality_harness_report import (
    ComparisonReport,
    ContextDelta,
    ProbeEvaluation,
    QualityHarnessReport,
    evaluate_comparison,
    evaluate_results,
)


def _result(
    id: str,  # noqa: A002
    *,
    intent: str = "SEARCH",
    hits: tuple[str, ...] = (),
    misses: tuple[str, ...] = (),
    prompt_tokens: int = 0,
    seconds: float = 0.0,
    style_violations: tuple[str, ...] = (),
    error: str = "",
) -> dict:
    """Build a dict matching scripts/quality_harness.py's QualityResult.__dict__."""
    return {
        "id": id,
        "intent": intent,
        "ok": not error,
        "answer": "some answer",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 10,
        "total_tokens": prompt_tokens + 10,
        "seconds": seconds,
        "hits": list(hits),
        "misses": list(misses),
        "style_violations": list(style_violations),
        "error": error,
        "metadata": {},
    }


class TestEvaluateResults:
    def test_recomputes_score_and_maximum_from_hits_and_misses(self) -> None:
        results = [_result("a", hits=("f1", "f2"), misses=("f3",))]

        report = evaluate_results(results)

        assert report.probes[0].score == 2
        assert report.probes[0].maximum == 3

    def test_missing_facts_pass_through_from_misses(self) -> None:
        results = [_result("a", hits=("f1",), misses=("f2", "f3"))]

        report = evaluate_results(results)

        assert report.probes[0].missing_facts == ("f2", "f3")

    def test_prompt_tokens_and_latency_pass_through(self) -> None:
        results = [_result("a", prompt_tokens=321, seconds=4.5)]

        report = evaluate_results(results)

        assert report.probes[0].prompt_tokens == 321
        assert report.probes[0].seconds == 4.5

    def test_style_violations_pass_through_and_are_counted(self) -> None:
        results = [
            _result("a", style_violations=("reasoning_preamble",)),
            _result("b"),
        ]

        report = evaluate_results(results)

        assert report.probes[0].style_violations == ("reasoning_preamble",)
        assert report.probes[0].style_ok is False
        assert report.probes[1].style_ok is True
        assert report.style_ok_count == 1
        assert report.total_style_violations == 1

    def test_missing_style_violations_field_is_backwards_compatible(self) -> None:
        result = _result("a")
        del result["style_violations"]

        report = evaluate_results([result])

        assert report.probes[0].style_violations == ()
        assert report.style_ok_count == 1

    def test_error_result_has_zero_score_and_carries_error(self) -> None:
        results = [_result("a", error="TimeoutError: boom")]

        report = evaluate_results(results)

        assert report.probes[0].score == 0
        assert report.probes[0].maximum == 0
        assert report.probes[0].error == "TimeoutError: boom"

    def test_totals_sum_across_all_probes(self) -> None:
        results = [
            _result("a", hits=("f1",), misses=("f2",), prompt_tokens=100, seconds=1.0),
            _result("b", hits=("f3", "f4"), misses=(), prompt_tokens=50, seconds=2.5),
        ]

        report = evaluate_results(results)

        assert report.total_score == 3
        assert report.total_maximum == 4
        assert report.total_prompt_tokens == 150
        assert report.total_seconds == 3.5
        assert report.style_ok_count == 2
        assert report.total_style_violations == 0

    def test_empty_input_produces_zeroed_report(self) -> None:
        report = evaluate_results([])

        assert report.probes == ()
        assert report.total_score == 0
        assert report.total_maximum == 0
        assert report.total_prompt_tokens == 0
        assert report.total_seconds == 0.0

    def test_probe_order_is_preserved(self) -> None:
        results = [_result("b"), _result("a"), _result("c")]

        report = evaluate_results(results)

        assert [probe.id for probe in report.probes] == ["b", "a", "c"]


class TestEvaluateComparison:
    def test_positive_delta_when_context_helps(self) -> None:
        payload = {
            "context": [_result("a", hits=("f1", "f2"), prompt_tokens=150)],
            "no_context": [_result("a", hits=("f1",), misses=("f2",), prompt_tokens=50)],
        }

        comparison = evaluate_comparison(payload)

        assert comparison.deltas == (ContextDelta(id="a", score_delta=1, prompt_token_delta=100),)
        assert comparison.total_score_delta == 1
        assert comparison.total_prompt_token_delta == 100

    def test_negative_delta_when_context_hurts(self) -> None:
        payload = {
            "context": [_result("a", hits=(), misses=("f1",), prompt_tokens=200)],
            "no_context": [_result("a", hits=("f1",), prompt_tokens=40)],
        }

        comparison = evaluate_comparison(payload)

        assert comparison.deltas == (ContextDelta(id="a", score_delta=-1, prompt_token_delta=160),)
        assert comparison.total_score_delta == -1

    def test_deltas_matched_by_id_not_position(self) -> None:
        payload = {
            "context": [
                _result("first", hits=("f1",), prompt_tokens=10),
                _result("second", hits=("f1", "f2"), prompt_tokens=20),
            ],
            "no_context": [
                _result("second", hits=("f1",), misses=("f2",), prompt_tokens=15),
                _result("first", hits=(), misses=("f1",), prompt_tokens=5),
            ],
        }

        comparison = evaluate_comparison(payload)

        by_id = {delta.id: delta for delta in comparison.deltas}
        assert by_id["first"].score_delta == 1
        assert by_id["first"].prompt_token_delta == 5
        assert by_id["second"].score_delta == 1
        assert by_id["second"].prompt_token_delta == 5

    def test_with_and_without_context_reports_are_independently_correct(self) -> None:
        payload = {
            "context": [_result("a", hits=("f1", "f2"), prompt_tokens=150, seconds=2.0)],
            "no_context": [
                _result("a", hits=("f1",), misses=("f2",), prompt_tokens=50, seconds=1.0)
            ],
        }

        comparison = evaluate_comparison(payload)

        assert comparison.with_context.total_score == 2
        assert comparison.without_context.total_score == 1
        assert comparison.with_context.total_seconds == 2.0
        assert comparison.without_context.total_seconds == 1.0


class TestImmutability:
    def test_probe_evaluation_is_frozen(self) -> None:
        probe = ProbeEvaluation(
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

    def test_quality_harness_report_is_frozen(self) -> None:
        report = evaluate_results([_result("a")])
        with pytest.raises(FrozenInstanceError):
            report.total_score = 99  # type: ignore[misc]

    def test_comparison_report_is_frozen(self) -> None:
        comparison = evaluate_comparison({"context": [], "no_context": []})
        with pytest.raises(FrozenInstanceError):
            comparison.total_score_delta = 99  # type: ignore[misc]


def test_report_type_reexported_from_package() -> None:
    from packages.evaluation import QualityHarnessReport as ReexportedReport

    assert ReexportedReport is QualityHarnessReport


def test_comparison_report_type_reexported_from_package() -> None:
    from packages.evaluation import ComparisonReport as ReexportedComparisonReport

    assert ReexportedComparisonReport is ComparisonReport
