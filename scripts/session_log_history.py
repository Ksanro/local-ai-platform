#!/usr/bin/env python
"""Summarize persisted gateway session-log history from EngineeringMemory.

This is read-only. It loads records written by
``scripts/ingest_session_log.py`` and prints a compact summary
or JSON document.

Usage
-----

.. code-block:: bash

    # Human-readable table:
    python scripts/session_log_history.py

    # JSON output:
    python scripts/session_log_history.py --json

    # Custom storage path:
    python scripts/session_log_history.py --storage-path data/custom_memory.json

    # Show 20 recent records:
    python scripts/session_log_history.py --recent 20

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.engineering_memory import EngineeringMemory  # noqa: E402
from packages.observability.session_log_history import (  # noqa: E402
    SessionLogSummary,
    build_session_log_summary,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storage-path",
        default=None,
        help="Engineering memory storage file path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable table.",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=10,
        help="Number of recent records to show (default: 10).",
    )
    return parser.parse_args(argv)


def _print_table(summary: SessionLogSummary) -> None:
    """Print a human-readable session-log history table."""
    print("\n=== SESSION LOG HISTORY ===")

    print(f"\nTotal records:    {summary.total_records}")
    print(f"Success:          {summary.success_count} "
          f"({summary.success_rate * 100:.1f}%)")
    print(f"Failure:          {summary.failure_count} "
          f"({(1 - summary.success_rate) * 100:.1f}%)")

    if summary.error_breakdown:
        print("\n--- ERROR BREAKDOWN ---")
        for error_prefix, count in sorted(
            summary.error_breakdown.items(), key=lambda x: -x[1]
        ):
            print(f"{error_prefix}: {count}")

    print("\n--- TIMING ---")
    avg_total = (
        f"{summary.avg_total_ms}"
        if summary.avg_total_ms is not None
        else "N/A"
    )
    avg_pw = (
        f"{summary.avg_provider_wait_ms}"
        if summary.avg_provider_wait_ms is not None
        else "N/A"
    )
    print(f"Avg total_ms:         {avg_total}")
    print(f"Avg provider_wait_ms: {avg_pw}")

    if summary.intent_distribution:
        print("\n--- INTENT DISTRIBUTION ---")
        for intent, count in sorted(
            summary.intent_distribution.items(), key=lambda x: -x[1]
        ):
            print(f"{intent}: {count}")

    if summary.model_distribution:
        print("\n--- MODEL DISTRIBUTION ---")
        for model, count in sorted(
            summary.model_distribution.items(), key=lambda x: -x[1]
        ):
            print(f"{model}: {count}")

    print("\n--- HISTORY-CAP RATE ---")
    if summary.history_cap_rate > 0:
        print(f"{summary.history_cap_rate:.2f}")
    else:
        print("0.00 (no history data or no caps applied)")

    if summary.recent_records:
        print(f"\n--- RECENT {len(summary.recent_records)} RECORDS ---")
        print(
            f"{'session_id':<12} {'model':<10} {'intent':<12} "
            f"{'status':<8} {'completed_at'}"
        )
        for rec in summary.recent_records:
            print(
                f"{rec['session_id']:<12} {rec['model']:<10} "
                f"{rec['intent']:<12} {rec['status']:<8} {rec['completed_at']}"
            )

    print("\n=== END ===\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments. Defaults to ``sys.argv[1:]``.

    Returns:
        0 on success, 1 on failure.
    """
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        memory = EngineeringMemory(storage_path=args.storage_path)
        memory.reload()
        summary = build_session_log_summary(memory, recent_limit=args.recent)
    except Exception as exc:
        print(f"Error loading session log history: {exc}", file=sys.stderr)
        return 1

    if args.json:
        # Manually build a JSON-serializable dict since SessionLogSummary
        # uses frozen dataclass with slots.
        result = {
            "total_records": summary.total_records,
            "success_count": summary.success_count,
            "failure_count": summary.failure_count,
            "success_rate": summary.success_rate,
            "error_breakdown": dict(summary.error_breakdown),
            "avg_total_ms": summary.avg_total_ms,
            "avg_provider_wait_ms": summary.avg_provider_wait_ms,
            "intent_distribution": dict(summary.intent_distribution),
            "history_cap_rate": summary.history_cap_rate,
            "model_distribution": dict(summary.model_distribution),
            "recent_records": list(summary.recent_records),
        }
        print(json.dumps(result, indent=2))
        return 0

    _print_table(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
