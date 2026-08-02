"""Tests for read-only quality-harness history summaries."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.models import EngineeringSessionRecord
from packages.engineering_memory.quality_harness_records import (
    build_quality_harness_comparison_record,
    build_quality_harness_record,
)
from packages.evaluation.quality_harness_report import (
    evaluate_comparison,
    evaluate_results,
)
from packages.observability.quality_history import (
    QualityHistorySummary,
    load_quality_history,
    summarize_quality_history,
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


def _single_record(
    session_id: str,
    *,
    hits: list[str],
    misses: list[str],
    prompt_tokens: int,
    completed_at: str,
    probe_id: str = "probe",
) -> EngineeringSessionRecord:
    report = evaluate_results(
        [
            _result(
                probe_id,
                hits=hits,
                misses=misses,
                prompt_tokens=prompt_tokens,
            )
        ]
    )
    base = build_quality_harness_record(
        report,
        model="qwen36",
        session_id=session_id,
    )
    return EngineeringSessionRecord(
        **{
            **base.to_dict(),
            "completed_at": completed_at,
        }
    )


def _comparison_record(
    session_id: str,
    *,
    completed_at: str,
    context_hits: list[str],
    no_context_hits: list[str],
    no_context_misses: list[str],
) -> EngineeringSessionRecord:
    comparison = evaluate_comparison(
        {
            "context": [_result("compare", hits=context_hits, prompt_tokens=150)],
            "no_context": [
                _result(
                    "compare",
                    hits=no_context_hits,
                    misses=no_context_misses,
                    prompt_tokens=50,
                )
            ],
        }
    )
    base = build_quality_harness_comparison_record(
        comparison,
        model="qwen36",
        session_id=session_id,
    )
    return EngineeringSessionRecord(
        **{
            **base.to_dict(),
            "completed_at": completed_at,
        }
    )


class TestSummarizeQualityHistory:
    def test_counts_only_quality_harness_workflows(self) -> None:
        records = [
            _single_record(
                "single-1",
                hits=["f1"],
                misses=[],
                prompt_tokens=100,
                completed_at="2026-08-02T10:00:00+00:00",
            ),
            _comparison_record(
                "compare-1",
                completed_at="2026-08-02T11:00:00+00:00",
                context_hits=["f1", "f2"],
                no_context_hits=["f1"],
                no_context_misses=["f2"],
            ),
            EngineeringSessionRecord(
                session_id="other",
                workflow_name="bug-fix",
                request_summary="not quality",
                transaction_id="other",
                completed_at="2026-08-02T12:00:00+00:00",
            ),
        ]

        summary = summarize_quality_history(records)

        assert summary.total_records == 2
        assert summary.quality_harness_runs == 1
        assert summary.quality_harness_compare_runs == 1

    def test_workflow_summary_reports_score_ratios_and_prompt_tokens(self) -> None:
        records = [
            _single_record(
                "low",
                hits=["f1"],
                misses=["f2"],
                prompt_tokens=100,
                completed_at="2026-08-02T10:00:00+00:00",
            ),
            _single_record(
                "high",
                hits=["f1", "f2"],
                misses=[],
                prompt_tokens=300,
                completed_at="2026-08-02T11:00:00+00:00",
            ),
        ]

        summary = summarize_quality_history(records)
        workflow = summary.workflows[0]

        assert workflow.workflow_name == "quality_harness"
        assert workflow.run_count == 2
        assert workflow.latest_session_id == "high"
        assert workflow.best_score_ratio == 1.0
        assert workflow.worst_score_ratio == 0.5
        assert workflow.average_score_ratio == 0.75
        assert workflow.average_prompt_tokens == 200.0

    def test_latest_context_score_delta_comes_from_latest_comparison(self) -> None:
        records = [
            _comparison_record(
                "old",
                completed_at="2026-08-02T10:00:00+00:00",
                context_hits=["f1"],
                no_context_hits=[],
                no_context_misses=["f1"],
            ),
            _comparison_record(
                "new",
                completed_at="2026-08-02T11:00:00+00:00",
                context_hits=["f1", "f2"],
                no_context_hits=[],
                no_context_misses=["f1", "f2"],
            ),
        ]

        summary = summarize_quality_history(records)

        assert summary.latest_context_score_delta == 2

    def test_recent_missing_facts_are_sorted_newest_first_and_limited(self) -> None:
        records = [
            _single_record(
                "old",
                hits=[],
                misses=["old-missing"],
                prompt_tokens=100,
                completed_at="2026-08-02T10:00:00+00:00",
                probe_id="old-probe",
            ),
            _single_record(
                "new",
                hits=[],
                misses=["new-missing"],
                prompt_tokens=100,
                completed_at="2026-08-02T11:00:00+00:00",
                probe_id="new-probe",
            ),
        ]

        summary = summarize_quality_history(records, missing_fact_limit=1)

        assert len(summary.recent_missing_facts) == 1
        assert summary.recent_missing_facts[0].session_id == "new"
        assert summary.recent_missing_facts[0].probe_id == "new-probe"
        assert summary.recent_missing_facts[0].missing_facts == ("new-missing",)

    def test_empty_history_is_zeroed(self) -> None:
        summary = summarize_quality_history([])

        assert summary == QualityHistorySummary(
            total_records=0,
            quality_harness_runs=0,
            quality_harness_compare_runs=0,
            workflows=(),
            latest_context_score_delta=None,
            recent_missing_facts=(),
        )


class TestLoadQualityHistory:
    def test_loads_from_engineering_memory_storage(self, tmp_path: Path) -> None:
        storage_path = str(tmp_path / "memory.json")
        record = _single_record(
            "single",
            hits=["f1"],
            misses=[],
            prompt_tokens=100,
            completed_at="2026-08-02T10:00:00+00:00",
        )
        memory = EngineeringMemory(storage_path=storage_path)
        memory.store(record)

        summary = load_quality_history(storage_path=storage_path)

        assert summary.total_records == 1
        assert summary.workflows[0].latest_session_id == "single"


def test_summary_is_frozen() -> None:
    summary = summarize_quality_history([])

    with pytest.raises(FrozenInstanceError):
        summary.total_records = 10  # type: ignore[misc]


def test_reexported_from_package() -> None:
    from packages.observability import summarize_quality_history as reexported

    assert reexported is summarize_quality_history
