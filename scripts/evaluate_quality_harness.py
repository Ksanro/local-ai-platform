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

from packages.evaluation.quality_harness_report import (  # noqa: E402
    ComparisonReport,
    QualityHarnessReport,
    evaluate_comparison,
    evaluate_results,
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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Evaluate quality-harness JSON output."""
    args = parse_args(argv)
    payload = _read_payload(args.input)

    has_error: bool
    if isinstance(payload, dict) and "context" in payload and "no_context" in payload:
        comparison = evaluate_comparison(payload)
        if args.json:
            print(json.dumps(dataclasses.asdict(comparison), indent=2))
        else:
            _print_comparison_report(comparison)
        has_error = any(
            probe.error
            for probe in comparison.with_context.probes + comparison.without_context.probes
        )
    elif isinstance(payload, list):
        report = evaluate_results(payload)
        if args.json:
            print(json.dumps(dataclasses.asdict(report), indent=2))
        else:
            _print_single_report(report)
        has_error = any(probe.error for probe in report.probes)
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
