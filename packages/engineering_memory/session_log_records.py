"""Build `EngineeringSessionRecord` entries from gateway session-log files.

Bridges the live gateway session log (`logs/sessions.jsonl`) and
`packages.engineering_memory`'s deterministic session storage, so gateway
requests can be persisted as plain historical records.

This does **not** wire the dormant `packages.session`/`packages.controller`
stack — records are built directly from session-log JSONL lines, not from an
`EngineeringController` transaction.

Public API
----------

.. code-block:: python

    from packages.engineering_memory.session_log_records import (
        read_session_log_lines,
        build_session_log_record,
    )

    for raw in read_session_log_lines("logs/sessions.jsonl"):
        record = build_session_log_record(raw)
        memory.store(record)

"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from packages.engineering_memory.models import EngineeringSessionRecord

__all__ = [
    "WORKFLOW_NAME",
    "read_session_log_lines",
    "build_session_log_record",
]

WORKFLOW_NAME = "gateway_session"


def read_session_log_lines(path: str) -> list[dict[str, Any]]:
    """Read a JSONL file, yielding one parsed dict per line.

    Skips blank lines and lines that fail JSON parsing.
    Returns a list of parsed session-log record dicts.

    Args:
        path: Path to the JSONL session-log file.

    Returns:
        List of parsed record dicts. Returns an empty list if the file
        does not exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return records


def build_session_log_record(raw: dict[str, Any]) -> EngineeringSessionRecord:
    """Build an EngineeringSessionRecord from a single session-log JSONL record.

    Maps session-log fields to EngineeringSessionRecord fields:
      - session_id: raw["request_id"] (fallback: generated UUID)
      - workflow_name: WORKFLOW_NAME ("gateway_session")
      - request_summary: f"{model} / {intent} / {status}" (deterministic, short)
      - transaction_id: raw["conversation_key"] or ""
      - controller_decision: "COMPLETE" if status=="ok", "FAIL" if status=="error"
      - completed_at: raw["timestamp"] normalized to +00:00 suffix
      - metadata: all other session-log fields (model, backend_model, intent,
                  context, planning, usage, timing, history, error,
                  answer_preview, conversation_key, stream, n_messages,
                  last_user_message)
      - execution_report: {} (default)
      - verification_report: {} (default)
      - evaluation_report: {} (default)

    Uses ``.get(key, default)`` for all nested sub-dicts (context, planning,
    timing, history) so that older or hand-written fixture records that omit
    optional keys do not raise ``KeyError``.

    Args:
        raw: A parsed session-log JSONL line dict.

    Returns:
        An ``EngineeringSessionRecord`` ready to store via ``EngineeringMemory``.
    """
    # --- session_id: use request_id, fallback to UUID ---
    request_id = raw.get("request_id") or ""
    session_id = request_id if request_id else str(uuid.uuid4())

    # --- derived fields ---
    model = raw.get("model", "")
    intent = raw.get("intent", "")
    status = raw.get("status", "")

    request_summary = f"{model} / {intent} / {status}"
    transaction_id = raw.get("conversation_key") or ""

    controller_decision = "COMPLETE" if status == "ok" else "FAIL"

    # Normalize Z-suffixed timestamps to +00:00 for consistent sorting.
    timestamp = raw.get("timestamp", "")
    completed_at = timestamp.replace("Z", "+00:00") if timestamp else ""

    # --- metadata: carry the full session-log payload ---
    metadata: dict[str, Any] = {
        "model": model,
        "backend_model": raw.get("backend_model", ""),
        "intent": intent,
        "stream": raw.get("stream", False),
        "n_messages": raw.get("n_messages", 0),
        "last_user_message": raw.get("last_user_message", ""),
        "context": raw.get("context") or {},
        "planning": raw.get("planning") or {},
        "usage": raw.get("usage") or {},
        "timing": raw.get("timing") or {},
        "history": raw.get("history") or {},
        "error": raw.get("error"),
        "answer_preview": raw.get("answer_preview", ""),
        "conversation_key": raw.get("conversation_key", ""),
    }

    return EngineeringSessionRecord(
        session_id=session_id,
        workflow_name=WORKFLOW_NAME,
        request_summary=request_summary,
        transaction_id=transaction_id,
        execution_report={},
        verification_report={},
        evaluation_report={},
        controller_decision=controller_decision,
        completed_at=completed_at,
        metadata=metadata,
    )



