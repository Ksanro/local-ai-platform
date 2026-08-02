"""Build `EngineeringSessionRecord` entries from quality-harness evaluations.

Bridges the activated `packages.evaluation.quality_harness_report` slice and
`packages.engineering_memory`'s deterministic session storage, so quality
harness / evaluation runs can be persisted as plain historical records.

This does **not** wire the dormant `packages.session`/`packages.controller`
stack — records are built directly from a `QualityHarnessReport` or
`ComparisonReport`, not from an `EngineeringController` transaction.

Public API
----------

.. code-block:: python

    from packages.engineering_memory.quality_harness_records import (
        build_quality_harness_record,
        build_quality_harness_comparison_record,
    )

    record = build_quality_harness_record(report, model="qwen36")
    memory.store(record)

"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any

from packages.engineering_memory.models import EngineeringSessionRecord
from packages.evaluation.quality_harness_report import (
    ComparisonReport,
    QualityHarnessReport,
)

__all__ = [
    "COMPARISON_WORKFLOW_NAME",
    "WORKFLOW_NAME",
    "build_quality_harness_comparison_record",
    "build_quality_harness_record",
]

WORKFLOW_NAME = "quality_harness"
COMPARISON_WORKFLOW_NAME = "quality_harness_compare"


def _generate_session_id(prefix: str) -> str:
    """Generate a unique, sortable session id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _report_to_dict(report: QualityHarnessReport) -> dict[str, Any]:
    """Serialize a QualityHarnessReport to a plain dict for evaluation_report."""
    return dataclasses.asdict(report)


def _build_metadata(
    *,
    model: str,
    gateway_commit: str,
    config_snapshot: dict[str, Any] | None,
    notes: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "gateway_commit": gateway_commit,
        "config_snapshot": config_snapshot or {},
        "notes": notes,
    }


def build_quality_harness_record(
    report: QualityHarnessReport,
    *,
    model: str,
    gateway_commit: str = "",
    config_snapshot: dict[str, Any] | None = None,
    notes: str = "",
    session_id: str | None = None,
) -> EngineeringSessionRecord:
    """Build a session record for a single quality-harness run.

    Args:
        report: The evaluated quality-harness run.
        model: The model name the run was executed against.
        gateway_commit: Gateway git commit/version tag, if known.
        config_snapshot: Relevant gateway configuration at run time.
        notes: Free-form notes about this run.
        session_id: Explicit session id; auto-generated when omitted.

    Returns:
        An `EngineeringSessionRecord` ready to store via `EngineeringMemory`.
    """
    sid = session_id or _generate_session_id(WORKFLOW_NAME)
    return EngineeringSessionRecord(
        session_id=sid,
        workflow_name=WORKFLOW_NAME,
        request_summary=f"quality harness run against model {model}",
        transaction_id=sid,
        evaluation_report=_report_to_dict(report),
        controller_decision="COMPLETE",
        metadata=_build_metadata(
            model=model,
            gateway_commit=gateway_commit,
            config_snapshot=config_snapshot,
            notes=notes,
        ),
    )


def build_quality_harness_comparison_record(
    comparison: ComparisonReport,
    *,
    model: str,
    gateway_commit: str = "",
    config_snapshot: dict[str, Any] | None = None,
    notes: str = "",
    session_id: str | None = None,
) -> EngineeringSessionRecord:
    """Build a session record for a `--compare-context` quality-harness run.

    Args:
        comparison: The evaluated context-on/context-off comparison run.
        model: The model name the run was executed against.
        gateway_commit: Gateway git commit/version tag, if known.
        config_snapshot: Relevant gateway configuration at run time.
        notes: Free-form notes about this run.
        session_id: Explicit session id; auto-generated when omitted.

    Returns:
        An `EngineeringSessionRecord` ready to store via `EngineeringMemory`.
    """
    sid = session_id or _generate_session_id(COMPARISON_WORKFLOW_NAME)
    return EngineeringSessionRecord(
        session_id=sid,
        workflow_name=COMPARISON_WORKFLOW_NAME,
        request_summary=f"quality harness context comparison against model {model}",
        transaction_id=sid,
        evaluation_report={
            "with_context": _report_to_dict(comparison.with_context),
            "without_context": _report_to_dict(comparison.without_context),
            "deltas": [dataclasses.asdict(delta) for delta in comparison.deltas],
            "total_score_delta": comparison.total_score_delta,
            "total_prompt_token_delta": comparison.total_prompt_token_delta,
        },
        controller_decision="COMPLETE",
        metadata=_build_metadata(
            model=model,
            gateway_commit=gateway_commit,
            config_snapshot=config_snapshot,
            notes=notes,
        ),
    )
