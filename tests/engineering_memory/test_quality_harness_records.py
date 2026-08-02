"""Tests for packages.engineering_memory.quality_harness_records.

Verifies EngineeringSessionRecord construction from quality-harness
evaluations, and that the resulting records store/reload correctly through
EngineeringMemory without touching packages.session or packages.controller.
"""

from __future__ import annotations

from pathlib import Path

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.quality_harness_records import (
    COMPARISON_WORKFLOW_NAME,
    WORKFLOW_NAME,
    build_quality_harness_comparison_record,
    build_quality_harness_record,
)
from packages.evaluation.quality_harness_report import (
    evaluate_comparison,
    evaluate_results,
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


class TestBuildQualityHarnessRecord:
    def test_workflow_name_is_quality_harness(self) -> None:
        report = evaluate_results([_result("a", hits=["f1"])])

        record = build_quality_harness_record(report, model="qwen36")

        assert record.workflow_name == WORKFLOW_NAME

    def test_evaluation_report_carries_score_and_totals(self) -> None:
        report = evaluate_results(
            [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=100, seconds=1.5)]
        )

        record = build_quality_harness_record(report, model="qwen36")

        assert record.evaluation_report["total_score"] == 1
        assert record.evaluation_report["total_maximum"] == 2
        assert record.evaluation_report["total_prompt_tokens"] == 100
        assert record.evaluation_report["probes"][0]["missing_facts"] == ("f2",)

    def test_metadata_carries_model_commit_config_and_notes(self) -> None:
        report = evaluate_results([_result("a", hits=["f1"])])

        record = build_quality_harness_record(
            report,
            model="qwen36",
            gateway_commit="abc123",
            config_snapshot={"APP_HISTORY_CAP_TOKENS": "3000"},
            notes="post history-cap tuning",
        )

        assert record.metadata["model"] == "qwen36"
        assert record.metadata["gateway_commit"] == "abc123"
        assert record.metadata["config_snapshot"] == {"APP_HISTORY_CAP_TOKENS": "3000"}
        assert record.metadata["notes"] == "post history-cap tuning"

    def test_controller_decision_is_always_complete(self) -> None:
        report = evaluate_results([_result("a", error="boom")])

        record = build_quality_harness_record(report, model="qwen36")

        assert record.controller_decision == "COMPLETE"

    def test_explicit_session_id_is_used_verbatim(self) -> None:
        report = evaluate_results([_result("a")])

        record = build_quality_harness_record(
            report, model="qwen36", session_id="fixed-id"
        )

        assert record.session_id == "fixed-id"
        assert record.transaction_id == "fixed-id"

    def test_auto_generated_session_ids_are_unique(self) -> None:
        report = evaluate_results([_result("a")])

        first = build_quality_harness_record(report, model="qwen36")
        second = build_quality_harness_record(report, model="qwen36")

        assert first.session_id != second.session_id


class TestBuildQualityHarnessComparisonRecord:
    def test_workflow_name_is_quality_harness_compare(self) -> None:
        comparison = evaluate_comparison(
            {"context": [_result("a", hits=["f1"])], "no_context": [_result("a")]}
        )

        record = build_quality_harness_comparison_record(comparison, model="qwen36")

        assert record.workflow_name == COMPARISON_WORKFLOW_NAME

    def test_evaluation_report_carries_context_delta(self) -> None:
        comparison = evaluate_comparison(
            {
                "context": [_result("a", hits=["f1", "f2"], prompt_tokens=150)],
                "no_context": [
                    _result("a", hits=["f1"], misses=["f2"], prompt_tokens=50)
                ],
            }
        )

        record = build_quality_harness_comparison_record(comparison, model="qwen36")

        assert record.evaluation_report["total_score_delta"] == 1
        assert record.evaluation_report["total_prompt_token_delta"] == 100
        assert record.evaluation_report["deltas"] == [
            {"id": "a", "score_delta": 1, "prompt_token_delta": 100}
        ]
        assert record.evaluation_report["with_context"]["total_score"] == 2
        assert record.evaluation_report["without_context"]["total_score"] == 1


class TestPersistenceRoundTrip:
    def test_single_run_record_stores_and_reloads(self, tmp_path: Path) -> None:
        report = evaluate_results(
            [_result("a", hits=["f1"], misses=["f2"], prompt_tokens=100)]
        )
        record = build_quality_harness_record(
            report, model="qwen36", notes="round trip"
        )
        storage_path = str(tmp_path / "memory.json")

        memory = EngineeringMemory(storage_path=storage_path)
        memory.store(record)

        reloaded = EngineeringMemory(storage_path=storage_path)
        reloaded.reload()
        stored = reloaded.find_session(record.session_id)

        assert stored is not None
        assert stored.workflow_name == WORKFLOW_NAME
        assert stored.evaluation_report["total_score"] == 1
        assert stored.metadata["notes"] == "round trip"

    def test_comparison_record_stores_and_reloads(self, tmp_path: Path) -> None:
        comparison = evaluate_comparison(
            {
                "context": [_result("a", hits=["f1"], prompt_tokens=100)],
                "no_context": [_result("a", misses=["f1"], prompt_tokens=20)],
            }
        )
        record = build_quality_harness_comparison_record(comparison, model="qwen36")
        storage_path = str(tmp_path / "memory.json")

        memory = EngineeringMemory(storage_path=storage_path)
        memory.store(record)

        reloaded = EngineeringMemory(storage_path=storage_path)
        reloaded.reload()
        stored = reloaded.find_session(record.session_id)

        assert stored is not None
        assert stored.workflow_name == COMPARISON_WORKFLOW_NAME
        assert stored.evaluation_report["total_score_delta"] == 1


def test_reexported_from_package() -> None:
    from packages.engineering_memory import build_quality_harness_record as reexported

    assert reexported is build_quality_harness_record
