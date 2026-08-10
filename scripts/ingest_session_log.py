#!/usr/bin/env python
"""Ingest gateway session-log JSONL into EngineeringMemory.

Reads session-log records from a JSONL file (typically ``logs/sessions.jsonl``),
builds ``EngineeringSessionRecord`` entries, and persists them to the shared
EngineeringMemory storage file (``data/engineering_memory/memory_v1.json``).

Per-Record Persist Cost
-----------------------

Each call to ``memory.store_if_new()`` that stores a new record invokes
``store()`` → ``MemoryStorage.save()`` (``packages/engineering_memory/persistence.py``),
which rewrites the entire JSON file. Looping ``store_if_new`` over an ingestion
batch therefore means **one full-file rewrite per new record**.

This is acceptable for periodic/manual runs against realistic session counts
(hundreds to low thousands of records). It is **not designed for high-frequency
ingestion** (e.g. streaming thousands of records per minute). For high-throughput
scenarios, batch the ingest calls and use ``MemoryStorage.save()`` once after
accumulating all new records in-memory.

Usage
-----

.. code-block:: bash

    # Ingest the default session log:
    python scripts/ingest_session_log.py

    # Ingest a custom file:
    python scripts/ingest_session_log.py --session-log-path logs/custom.jsonl

    # Use a custom storage path:
    python scripts/ingest_session_log.py --storage-path data/custom_memory.json

Public API
----------

.. code-block:: python

    from scripts.ingest_session_log import main

    exit_code = main(["--session-log-path", "logs/sessions.jsonl"])

"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from packages.engineering_memory import EngineeringMemory
from packages.engineering_memory.session_log_records import (
    WORKFLOW_NAME,
    build_session_log_record,
    read_session_log_lines,
)


def _ingest(session_log_path: str, storage_path: str) -> int:
    """Read session-log lines, build records, reload+store into EngineeringMemory.

    CRITICAL: calls ``memory.reload()`` before storing records to avoid wiping
    previously-ingested records. This matches the pattern in
    ``scripts/evaluate_quality_harness.py:125-133``.

    Args:
        session_log_path: Path to the JSONL session-log file.
        storage_path: Path to the EngineeringMemory storage file.

    Returns:
        Number of new records stored (duplicates are silently skipped).
    """
    memory = EngineeringMemory(storage_path=storage_path)
    memory.reload()  # CRITICAL: load existing records from disk first

    raw_lines = read_session_log_lines(session_log_path)
    new_count = 0
    for raw in raw_lines:
        record = build_session_log_record(raw)
        if memory.store_if_new(record):
            new_count += 1

    return new_count


def _build_summary_json(
    memory: EngineeringMemory, recent_limit: int = 10
) -> dict[str, Any]:
    """Build a JSON-serializable summary of ingested session-log records."""
    records = memory.find_by_workflow(WORKFLOW_NAME)
    total = len(records)
    success = sum(1 for r in records if r.controller_decision == "COMPLETE")
    failure = total - success

    # Sort by completed_at descending for recent records
    sorted_records = sorted(
        records, key=lambda r: r.completed_at, reverse=True
    )
    recent = []
    for r in sorted_records[:recent_limit]:
        md = r.metadata or {}
        recent.append(
            {
                "session_id": r.session_id,
                "model": md.get("model", ""),
                "intent": md.get("intent", ""),
                "status": "ok" if r.controller_decision == "COMPLETE" else "error",
                "completed_at": r.completed_at,
            }
        )

    return {
        "total_records": total,
        "success_count": success,
        "failure_count": failure,
        "recent_records": recent,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments. Defaults to ``sys.argv[1:]``.

    Returns:
        0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description="Ingest gateway session-log records into EngineeringMemory."
    )
    parser.add_argument(
        "--session-log-path",
        default="logs/sessions.jsonl",
        help="Path to the JSONL session-log file (default: logs/sessions.jsonl).",
    )
    parser.add_argument(
        "--storage-path",
        default="data/engineering_memory/memory_v1.json",
        help="Path to the EngineeringMemory storage file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=10,
        help="Number of recent records to show in summary (default: 10).",
    )

    args = parser.parse_args(argv)

    try:
        new_count = _ingest(args.session_log_path, args.storage_path)
    except Exception as exc:
        print(f"Error ingesting session log: {exc}", file=sys.stderr)
        return 1

    memory = EngineeringMemory(storage_path=args.storage_path)
    memory.reload()

    if args.json:
        summary = _build_summary_json(memory, args.recent)
        print(json.dumps(summary, indent=2))
    else:
        summary = _build_summary_json(memory, args.recent)
        print("\n=== SESSION LOG INGESTED ===")
        print(f"New records stored: {new_count}")
        print(f"Total gateway_session records: {summary['total_records']}")
        print(f"  Success: {summary['success_count']}")
        print(f"  Failure: {summary['failure_count']}")
        if summary["recent_records"]:
            print(f"\n--- RECENT {len(summary['recent_records'])} RECORDS ---")
            print(
                f"{'session_id':<12} {'model':<10} {'intent':<12} "
                f"{'status':<8} {'completed_at'}"
            )
            for rec in summary["recent_records"]:
                print(
                    f"{rec['session_id']:<12} {rec['model']:<10} "
                    f"{rec['intent']:<12} {rec['status']:<8} {rec['completed_at']}"
                )
        print("\n=== END ===\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
