r"""Evaluate `scripts/quality_harness.py --json` output.

Reads the JSON emitted by the quality harness (a single run, or a
`--compare-context` run) and prints a structured evaluation: score, missing
facts, prompt-token cost, latency, and — in comparison mode — the context
delta per probe.

This is a thin CLI over `packages.evaluation.quality_harness_report`; it does
not run probes itself.

Usage
-----

.. code-block:: powershell

    .\uv.exe run python scripts\quality_harness.py --json > run.json
    .\uv.exe run python scripts\evaluate_quality_harness.py run.json

    .\uv.exe run python scripts\quality_harness.py --compare-context --json |
        .\uv.exe run python scripts\evaluate_quality_harness.py -

    .\uv.exe run python scripts\evaluate_quality_harness.py run.json --json

    .\uv.exe run python scripts\evaluate_quality_harness.py run.json ^
        --persist --model qwen36 --notes "post history-cap tuning"

    .\uv.exe run python scripts\evaluate_quality_harness.py run.json ^
        --quality-run --model qwen36 --quality-run-path run_summary.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Allow running as a standalone script (`python scripts\evaluate_quality_harness.py`)
# without the repo root already on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.engineering_memory.memory import EngineeringMemory  # noqa: E402
from packages.engineering_memory.models import EngineeringSessionRecord  # noqa: E402
from packages.engineering_memory.quality_harness_records import (  # noqa: E402
    build_quality_harness_comparison_record,
    build_quality_harness_record,
)
from packages.evaluation.quality_harness_report import (  # noqa: E402
    ComparisonReport,
    QualityHarnessReport,
    evaluate_comparison,
    evaluate_results,
)
from packages.evaluation.quality_run import (  # noqa: E402
    QualityRun,
    build_quality_run,
    build_quality_run_from_comparison,
)


def _read_payload(path: str) -> object:
    """Read and parse JSON from a file path, or stdin if `path` is "-"."""
    if path == "-":
        return json.loads(sys.stdin.read())
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _print_single_report(report: QualityHarnessReport) -> None:
    """Print a compact table for a single-run evaluation."""
    print("\n" + "=" * 90)
    print(f"{'id':<28}{'score':>8}{'ptok':>9}{'sec':>8}  missing")
    print("-" * 90)
    for probe in report.probes:
        score = f"{probe.score}/{probe.maximum}"
        missing = ", ".join(probe.missing_facts) if probe.missing_facts else "-"
        if probe.error:
            missing = probe.error
        print(
            f"{probe.id:<28}{score:>8}{probe.prompt_tokens:>9}"
            f"{probe.seconds:>8.1f}  {missing[:40]}"
        )
    print("-" * 90)
    print(
        f"{'TOTAL':<28}{f'{report.total_score}/{report.total_maximum}':>8}"
        f"{report.total_prompt_tokens:>9}{report.total_seconds:>8.1f}"
    )
    print("=" * 90)


def _print_comparison_report(comparison: ComparisonReport) -> None:
    """Print a compact table for a `--compare-context` evaluation."""
    print("\n" + "=" * 90)
    print(f"{'id':<28}{'dscore':>8}{'dptok':>9}")
    print("-" * 90)
    for delta in comparison.deltas:
        print(f"{delta.id:<28}{delta.score_delta:>8}{delta.prompt_token_delta:>9}")
    print("-" * 90)
    print(
        f"{'TOTAL':<28}{comparison.total_score_delta:>8}"
        f"{comparison.total_prompt_token_delta:>9}"
    )
    print("=" * 90)
    print("\nWITH CONTEXT")
    _print_single_report(comparison.with_context)
    print("\nWITHOUT CONTEXT")
    _print_single_report(comparison.without_context)


def _emit_quality_run(run: QualityRun, *, path: str | None) -> None:
    """Print a QualityRun as JSON, or write it to `path` when given."""
    content = json.dumps(dataclasses.asdict(run), indent=2)
    if path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"\nWrote QualityRun {run.run_id} to {path}", file=sys.stderr)
    else:
        print(content)


def _persist(record: EngineeringSessionRecord, *, storage_path: str | None) -> None:
    """Store an EngineeringSessionRecord and print a confirmation."""
    memory = EngineeringMemory(storage_path=storage_path)
    memory.reload()
    memory.store(record)
    print(
        f"\nPersisted session {record.session_id} to {memory.storage_path}",
        file=sys.stderr,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        help="path to quality-harness --json output, or '-' for stdin",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the evaluation as JSON"
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="store the evaluation as a deterministic engineering-memory record",
    )
    parser.add_argument(
        "--model", default="", help="model name tag for the persisted record"
    )
    parser.add_argument(
        "--gateway-commit",
        default="",
        help="gateway git commit/version tag for the persisted record",
    )
    parser.add_argument(
        "--notes", default="", help="free-form notes for the persisted record"
    )
    parser.add_argument(
        "--storage-path",
        default=None,
        help="override the engineering-memory storage file path",
    )
    parser.add_argument(
        "--quality-run",
        action="store_true",
        help=(
            "emit a QualityRun summary (JSON) instead of the raw evaluation "
            "report"
        ),
    )
    parser.add_argument(
        "--quality-run-path",
        default=None,
        help="write the QualityRun JSON to this file instead of stdout",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Evaluate quality-harness JSON output."""
    args = parse_args(argv)
    payload = _read_payload(args.input)

    has_error: bool
    if isinstance(payload, dict) and "context" in payload and "no_context" in payload:
        comparison = evaluate_comparison(payload)
        if args.quality_run:
            run = build_quality_run_from_comparison(
                comparison, model=args.model, gateway_commit=args.gateway_commit
            )
            _emit_quality_run(run, path=args.quality_run_path)
        elif args.json:
            print(json.dumps(dataclasses.asdict(comparison), indent=2))
        else:
            _print_comparison_report(comparison)
        has_error = any(
            probe.error
            for probe in comparison.with_context.probes + comparison.without_context.probes
        )
        if args.persist:
            record = build_quality_harness_comparison_record(
                comparison,
                model=args.model,
                gateway_commit=args.gateway_commit,
                notes=args.notes,
            )
            _persist(record, storage_path=args.storage_path)
    elif isinstance(payload, list):
        report = evaluate_results(payload)
        if args.quality_run:
            run = build_quality_run(
                report, model=args.model, gateway_commit=args.gateway_commit
            )
            _emit_quality_run(run, path=args.quality_run_path)
        elif args.json:
            print(json.dumps(dataclasses.asdict(report), indent=2))
        else:
            _print_single_report(report)
        has_error = any(probe.error for probe in report.probes)
        if args.persist:
            record = build_quality_harness_record(
                report,
                model=args.model,
                gateway_commit=args.gateway_commit,
                notes=args.notes,
            )
            _persist(record, storage_path=args.storage_path)
    else:
        print(
            "ERROR: input must be a quality-harness JSON array or "
            "compare-context object",
            file=sys.stderr,
        )
        return 2

    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
