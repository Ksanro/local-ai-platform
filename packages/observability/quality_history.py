"""Read-only summaries of persisted quality-harness history.

This module consumes `EngineeringMemory` records written by
`scripts/evaluate_quality_harness.py --persist` and produces deterministic
quality-history summaries. It does not write memory, call providers, inspect
the repository, or replace gateway/session logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from packages.engineering_memory.memory import EngineeringMemory
from packages.engineering_memory.models import EngineeringSessionRecord
from packages.engineering_memory.quality_harness_records import (
    COMPARISON_WORKFLOW_NAME,
    WORKFLOW_NAME,
)

__all__ = [
    "QualityHistorySummary",
    "RecentMissingFacts",
    "WorkflowQualitySummary",
    "load_quality_history",
    "summarize_quality_history",
]


@dataclass(frozen=True, slots=True)
class RecentMissingFacts:
    """Recent missing facts for one probe in one stored run."""

    session_id: str
    completed_at: str
    workflow_name: str
    probe_id: str
    missing_facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowQualitySummary:
    """Aggregate history for one quality-harness workflow."""

    workflow_name: str
    run_count: int
    latest_session_id: str
    latest_completed_at: str
    best_score_ratio: float
    worst_score_ratio: float
    average_score_ratio: float
    average_prompt_tokens: float


@dataclass(frozen=True, slots=True)
class QualityHistorySummary:
    """Read-only summary of persisted quality-harness runs."""

    total_records: int
    quality_harness_runs: int
    quality_harness_compare_runs: int
    workflows: tuple[WorkflowQualitySummary, ...]
    latest_context_score_delta: int | None
    recent_missing_facts: tuple[RecentMissingFacts, ...]


def _score_ratio(report: dict) -> float:
    maximum = int(report.get("total_maximum", 0) or 0)
    if maximum <= 0:
        return 0.0
    return int(report.get("total_score", 0) or 0) / maximum


def _prompt_tokens(report: dict) -> int:
    return int(report.get("total_prompt_tokens", 0) or 0)


def _base_report(record: EngineeringSessionRecord) -> dict:
    report = record.evaluation_report
    if record.workflow_name == COMPARISON_WORKFLOW_NAME:
        with_context = report.get("with_context", {})
        return with_context if isinstance(with_context, dict) else {}
    return report if isinstance(report, dict) else {}


def _latest(records: list[EngineeringSessionRecord]) -> EngineeringSessionRecord:
    return sorted(records, key=lambda r: (r.completed_at, r.session_id))[-1]


def _workflow_summary(
    workflow_name: str,
    records: list[EngineeringSessionRecord],
) -> WorkflowQualitySummary:
    ratios = [_score_ratio(_base_report(record)) for record in records]
    prompt_tokens = [_prompt_tokens(_base_report(record)) for record in records]
    latest = _latest(records)
    return WorkflowQualitySummary(
        workflow_name=workflow_name,
        run_count=len(records),
        latest_session_id=latest.session_id,
        latest_completed_at=latest.completed_at,
        best_score_ratio=round(max(ratios), 6) if ratios else 0.0,
        worst_score_ratio=round(min(ratios), 6) if ratios else 0.0,
        average_score_ratio=round(sum(ratios) / len(ratios), 6) if ratios else 0.0,
        average_prompt_tokens=round(sum(prompt_tokens) / len(prompt_tokens), 6)
        if prompt_tokens
        else 0.0,
    )


def _missing_facts(
    records: list[EngineeringSessionRecord],
    *,
    limit: int,
) -> tuple[RecentMissingFacts, ...]:
    rows: list[RecentMissingFacts] = []
    for record in sorted(records, key=lambda r: (r.completed_at, r.session_id), reverse=True):
        report = _base_report(record)
        probes = report.get("probes", [])
        if not isinstance(probes, (list, tuple)):
            continue
        for probe in probes:
            if not isinstance(probe, dict):
                continue
            missing = probe.get("missing_facts", ())
            if not missing:
                continue
            rows.append(
                RecentMissingFacts(
                    session_id=record.session_id,
                    completed_at=record.completed_at,
                    workflow_name=record.workflow_name,
                    probe_id=str(probe.get("id", "")),
                    missing_facts=tuple(str(item) for item in missing),
                )
            )
            if len(rows) >= limit:
                return tuple(rows)
    return tuple(rows)


def _latest_context_score_delta(records: list[EngineeringSessionRecord]) -> int | None:
    compare_records = [
        record for record in records if record.workflow_name == COMPARISON_WORKFLOW_NAME
    ]
    if not compare_records:
        return None
    latest = _latest(compare_records)
    value = latest.evaluation_report.get("total_score_delta")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def summarize_quality_history(
    records: Iterable[EngineeringSessionRecord],
    *,
    missing_fact_limit: int = 20,
) -> QualityHistorySummary:
    """Summarize persisted quality-harness records.

    Args:
        records: Engineering memory records to summarize.
        missing_fact_limit: Maximum recent missing-fact rows to include.

    Returns:
        A deterministic, read-only summary. Non-quality-harness records are
        ignored.
    """
    quality_records = [
        record
        for record in records
        if record.workflow_name in {WORKFLOW_NAME, COMPARISON_WORKFLOW_NAME}
    ]
    by_workflow = {
        workflow_name: [
            record for record in quality_records if record.workflow_name == workflow_name
        ]
        for workflow_name in (WORKFLOW_NAME, COMPARISON_WORKFLOW_NAME)
    }
    workflows = tuple(
        _workflow_summary(workflow_name, workflow_records)
        for workflow_name, workflow_records in by_workflow.items()
        if workflow_records
    )
    return QualityHistorySummary(
        total_records=len(quality_records),
        quality_harness_runs=len(by_workflow[WORKFLOW_NAME]),
        quality_harness_compare_runs=len(by_workflow[COMPARISON_WORKFLOW_NAME]),
        workflows=workflows,
        latest_context_score_delta=_latest_context_score_delta(quality_records),
        recent_missing_facts=_missing_facts(
            quality_records,
            limit=max(0, missing_fact_limit),
        ),
    )


def load_quality_history(
    *,
    storage_path: str | None = None,
    missing_fact_limit: int = 20,
) -> QualityHistorySummary:
    """Load EngineeringMemory from disk and summarize quality-harness history."""
    memory = EngineeringMemory(storage_path=storage_path)
    memory.reload()
    return summarize_quality_history(
        memory.list_sessions(),
        missing_fact_limit=missing_fact_limit,
    )
