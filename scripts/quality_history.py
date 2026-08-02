"""Summarize persisted quality-harness history from EngineeringMemory.

This is read-only. It loads records written by
`scripts/evaluate_quality_harness.py --persist` and prints a compact summary
or JSON document.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.observability.quality_history import load_quality_history  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storage-path",
        default=None,
        help="engineering-memory storage file path",
    )
    parser.add_argument(
        "--missing-fact-limit",
        type=int,
        default=20,
        help="maximum recent missing-fact rows to include",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Print a read-only quality history summary."""
    args = parse_args(argv)
    summary = load_quality_history(
        storage_path=args.storage_path,
        missing_fact_limit=args.missing_fact_limit,
    )
    if args.json:
        print(json.dumps(dataclasses.asdict(summary), indent=2))
        return 0

    print("\n" + "=" * 88)
    print("QUALITY HARNESS HISTORY")
    print("-" * 88)
    print(f"records: {summary.total_records}")
    print(f"single runs: {summary.quality_harness_runs}")
    print(f"compare runs: {summary.quality_harness_compare_runs}")
    print(f"latest context score delta: {summary.latest_context_score_delta}")
    print("-" * 88)
    print(f"{'workflow':<28}{'runs':>6}{'avg':>9}{'best':>9}{'worst':>9}{'avg ptok':>11}")
    for workflow in summary.workflows:
        print(
            f"{workflow.workflow_name:<28}{workflow.run_count:>6}"
            f"{workflow.average_score_ratio:>9.3f}"
            f"{workflow.best_score_ratio:>9.3f}"
            f"{workflow.worst_score_ratio:>9.3f}"
            f"{workflow.average_prompt_tokens:>11.1f}"
        )
    if summary.recent_missing_facts:
        print("-" * 88)
        print("RECENT MISSING FACTS")
        for row in summary.recent_missing_facts:
            missing = ", ".join(row.missing_facts)
            print(f"{row.completed_at} {row.probe_id}: {missing}")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
