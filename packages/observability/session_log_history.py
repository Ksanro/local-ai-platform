"""Read-only summaries of persisted gateway session-log history.

This module consumes ``EngineeringMemory`` records written by
``scripts/ingest_session_log.py`` and produces deterministic session-log
summaries. It does not write memory, call providers, inspect the repository,
or replace gateway/session logs.

Correction to plan §3: ``build_session_log_summary`` calls
``memory.find_by_workflow("gateway_session")`` first, sorts the result by
``completed_at`` descending, and then slices to ``recent_limit`` — it does
**not** call ``memory.recent(limit)`` and filter afterward, because
``EngineeringMemory.recent()`` is not workflow-aware and can silently return
fewer than ``limit`` gateway-session rows when other workflow records are
interspersed.

Public API
----------

.. code-block:: python

    from packages.observability.session_log_history import (
        SessionLogSummary,
        build_session_log_summary,
    )

    memory = EngineeringMemory()
    memory.reload()
    summary = build_session_log_summary(memory)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.engineering_memory.memory import EngineeringMemory

__all__ = [
    "SessionLogSummary",
    "build_session_log_summary",
]


@dataclass(frozen=True, slots=True)
class SessionLogSummary:
    """Read-only summary of gateway session-log records in EngineeringMemory.

    Attributes:
        total_records: Total session-log records stored.
        success_count: Records with controller_decision == "COMPLETE".
        failure_count: Records with controller_decision == "FAIL".
        success_rate: success_count / total_records (0.0 if no records).
        error_breakdown: Dict mapping normalized error prefix (first 80 chars)
                         to occurrence count. Only present when failures > 0.
        avg_total_ms: Average timing.total_ms across all records (None if no
                      timing data).
        avg_provider_wait_ms: Average timing.provider_wait_ms across records
                              (None if no provider_wait_ms data).
        intent_distribution: Dict mapping intent name to occurrence count.
        history_cap_rate: Ratio of records where history.cap_applied == True
                          to total records that have history data. 0.0 if no
                          history data present.
        model_distribution: Dict mapping model name to occurrence count.
        recent_records: List of the N most recent record dicts (session_id,
                        model, intent, status, completed_at), sorted by
                        completed_at descending. Default limit=10.
    """

    total_records: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    error_breakdown: dict[str, int] = field(default_factory=dict)
    avg_total_ms: float | None = None
    avg_provider_wait_ms: float | None = None
    intent_distribution: dict[str, int] = field(default_factory=dict)
    history_cap_rate: float = 0.0
    model_distribution: dict[str, int] = field(default_factory=dict)
    recent_records: list[dict[str, Any]] = field(default_factory=list)


def build_session_log_summary(
    memory: EngineeringMemory,
    workflow_name: str = "gateway_session",
    recent_limit: int = 10,
) -> SessionLogSummary:
    """Build a read-only summary of gateway session-log records.

    Uses ``memory.find_by_workflow(workflow_name)`` to filter to session-log
    records only. Does **not** call ``memory.recent(limit)`` because that
    method is not workflow-aware and can silently return fewer than ``limit``
    gateway-session rows when other workflow records are interspersed.

    Args:
        memory: An ``EngineeringMemory`` instance (should already be reloaded).
        workflow_name: The workflow name to filter by (default: "gateway_session").
        recent_limit: Number of recent records to include (default: 10).

    Returns:
        A ``SessionLogSummary`` dataclass instance.
    """
    records = memory.find_by_workflow(workflow_name)
    total = len(records)

    if total == 0:
        return SessionLogSummary()

    success_count = sum(
        1 for r in records if r.controller_decision == "COMPLETE"
    )
    failure_count = total - success_count
    success_rate = round(success_count / total, 6) if total else 0.0

    # --- Error breakdown ---
    error_breakdown: dict[str, int] = {}
    for r in records:
        error_text = (r.metadata or {}).get("error")
        if error_text:
            key = str(error_text)[:80]
            error_breakdown[key] = error_breakdown.get(key, 0) + 1

    # --- Timing averages ---
    total_ms_values: list[float] = []
    provider_wait_ms_values: list[float] = []
    for r in records:
        timing = (r.metadata or {}).get("timing") or {}
        if not isinstance(timing, dict):
            continue
        total_ms = timing.get("total_ms")
        if total_ms is not None:
            try:
                total_ms_values.append(float(total_ms))
            except (TypeError, ValueError):
                pass
        pw = timing.get("provider_wait_ms")
        if pw is not None:
            try:
                provider_wait_ms_values.append(float(pw))
            except (TypeError, ValueError):
                pass

    avg_total_ms = (
        round(sum(total_ms_values) / len(total_ms_values), 1)
        if total_ms_values
        else None
    )
    avg_provider_wait_ms = (
        round(sum(provider_wait_ms_values) / len(provider_wait_ms_values), 1)
        if provider_wait_ms_values
        else None
    )

    # --- Intent distribution ---
    intent_distribution: dict[str, int] = {}
    for r in records:
        intent = (r.metadata or {}).get("intent", "")
        if intent:
            intent_distribution[str(intent)] = intent_distribution.get(str(intent), 0) + 1

    # --- Model distribution ---
    model_distribution: dict[str, int] = {}
    for r in records:
        model = (r.metadata or {}).get("model", "")
        if model:
            model_distribution[str(model)] = model_distribution.get(str(model), 0) + 1

    # --- History cap rate ---
    history_present_count = 0
    cap_applied_count = 0
    for r in records:
        history = (r.metadata or {}).get("history")
        if history and isinstance(history, dict):
            history_present_count += 1
            if history.get("cap_applied") is True:
                cap_applied_count += 1

    history_cap_rate = (
        round(cap_applied_count / history_present_count, 6)
        if history_present_count
        else 0.0
    )

    # --- Recent records: sort by completed_at descending, then slice ---
    # CRITICAL: sort the workflow-filtered result, not memory.recent()
    sorted_records = sorted(
        records, key=lambda r: r.completed_at, reverse=True
    )
    recent_records: list[dict[str, Any]] = []
    for r in sorted_records[:recent_limit]:
        md = r.metadata or {}
        recent_records.append(
            {
                "session_id": r.session_id,
                "model": md.get("model", ""),
                "intent": md.get("intent", ""),
                "status": "ok" if r.controller_decision == "COMPLETE" else "error",
                "completed_at": r.completed_at,
            }
        )

    return SessionLogSummary(
        total_records=total,
        success_count=success_count,
        failure_count=failure_count,
        success_rate=success_rate,
        error_breakdown=error_breakdown,
        avg_total_ms=avg_total_ms,
        avg_provider_wait_ms=avg_provider_wait_ms,
        intent_distribution=intent_distribution,
        history_cap_rate=history_cap_rate,
        model_distribution=model_distribution,
        recent_records=recent_records,
    )



