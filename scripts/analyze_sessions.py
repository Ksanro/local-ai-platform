"""Analyze session log files and produce summary statistics.

Reads a JSONL session log and prints a structured summary including:

- Total requests, ok vs error counts
- Intent distribution
- Context status distribution
- Latency percentiles (median, p90)
- Prompt tokens by context status
- Delta-injection effectiveness
- 5 slowest requests
- Error requests

Usage
-----

.. code-block:: bash

    uv run python scripts/analyze_sessions.py logs/sessions.jsonl

Arguments
---------

path
    Path to the JSONL session log file.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


def _load_records(path: str) -> list[dict[str, Any]]:
    """Load and parse all JSONL records from a file.

    Args:
        path: Path to the JSONL file.

    Returns:
        A list of parsed record dicts.

    Raises:
        ValueError: If the file cannot be read or parsed.
    """
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"WARNING: skipping invalid JSON on line {line_no}: {exc}", file=sys.stderr)
    return records


def _percentile(values: list[float], pct: float) -> float:
    """Calculate the ``pct``-th percentile of a list of floats.

    Args:
        values: The values to compute the percentile for.
        pct: The percentile to compute (0-100).

    Returns:
        The computed percentile value, or 0.0 if the list is empty.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return round(d0 + d1, 1)


def _mean(values: list[float] | list[int]) -> float:
    """Compute the mean of a list of numeric values.

    Args:
        values: The values to compute the mean for.

    Returns:
        The mean value, or 0.0 if the list is empty.
    """
    if not values:
        return 0.0
    return statistics.mean(values)


def analyze(records: list[dict[str, Any]]) -> None:
    """Print analysis summary for the given records.

    Args:
        records: A list of session log record dicts.
    """
    total = len(records)
    if total == 0:
        print("No records found.")
        return

    # --- Basic counts ---
    ok_count = sum(1 for r in records if r.get("status") == "ok")
    error_count = total - ok_count

    print("=" * 60)
    print("SESSION LOG ANALYSIS")
    print("=" * 60)
    print()
    print(f"Total requests:  {total}")
    print(f"  OK:            {ok_count}")
    print(f"  Error:         {error_count}")
    print()

    # --- Intent distribution ---
    intents: dict[str, int] = {}
    for r in records:
        intent = r.get("intent", "DEFAULT")
        intents[intent] = intents.get(intent, 0) + 1

    print("-" * 40)
    print("INTENT DISTRIBUTION")
    print("-" * 40)
    for intent in sorted(intents, key=lambda k: -intents[k]):
        count = intents[intent]
        pct = round(100.0 * count / total, 1)
        print(f"  {intent:<15} {count:>5}  ({pct}%)")

    if intents.get("DEFAULT", 0) == total:
        print()
        print("  NOTE: All requests have intent=DEFAULT. Intent detection may")
        print("        not be firing (check PlanningStage).")
    print()

    # --- Context status distribution ---
    context_statuses: dict[str, int] = {}
    for r in records:
        ctx = r.get("context", {})
        status = ctx.get("status", "disabled")
        context_statuses[status] = context_statuses.get(status, 0) + 1

    print("-" * 40)
    print("CONTEXT STATUS DISTRIBUTION")
    print("-" * 40)
    for status in sorted(context_statuses, key=lambda k: -context_statuses[k]):
        count = context_statuses[status]
        pct = round(100.0 * count / total, 1)
        print(f"  {status:<20} {count:>5}  ({pct}%)")
    print()

    # --- Timing ---
    total_latencies = [
        r.get("timing", {}).get("total_ms", 0)
        for r in records
        if r.get("timing", {}).get("total_ms") is not None
    ]
    ttfts = [
        r.get("timing", {}).get("ttft_ms")
        for r in records
        if r.get("timing", {}).get("ttft_ms") is not None
    ]
    ttfts = [t for t in ttfts if t is not None]

    print("-" * 40)
    print("LATENCY (ms)")
    print("-" * 40)
    if total_latencies:
        print("  Total latency:")
        print(f"    Median:     {_percentile(total_latencies, 50):.1f}")
        print(f"    P90:        {_percentile(total_latencies, 90):.1f}")
        print(f"    Mean:       {_mean(total_latencies):.1f}")
        print(f"    Min:        {min(total_latencies):.1f}")
        print(f"    Max:        {max(total_latencies):.1f}")
    else:
        print("  No latency data available.")

    if ttfts:
        print("  TTFT (time to first token):")
        print(f"    Median:     {_percentile(ttfts, 50):.1f}")
        print(f"    P90:        {_percentile(ttfts, 90):.1f}")
        print(f"    Mean:       {_mean(ttfts):.1f}")
    else:
        print("  No TTFT data available (non-streaming requests).")
    print()

    # --- Prompt tokens ---
    prompt_tokens_list = [
        r.get("usage", {}).get("prompt_tokens")
        for r in records
        if r.get("usage", {}).get("prompt_tokens") is not None
    ]
    prompt_tokens_list = [t for t in prompt_tokens_list if t is not None]

    print("-" * 40)
    print("PROMPT TOKENS")
    print("-" * 40)
    if prompt_tokens_list:
        print("  Overall:")
        print(f"    Median:  {statistics.median(prompt_tokens_list):.0f}")
        print(f"    Mean:    {_mean(prompt_tokens_list):.0f}")
        print(f"    Min:     {min(prompt_tokens_list):.0f}")
        print(f"    Max:     {max(prompt_tokens_list):.0f}")

        # Split by context status
        print()
        print("  By context status:")
        status_tokens: dict[str, list[int]] = {}
        for r in records:
            ctx = r.get("context", {})
            status = ctx.get("status", "disabled")
            tokens = r.get("usage", {}).get("prompt_tokens")
            if tokens is not None:
                status_tokens.setdefault(status, []).append(tokens)

        for status in sorted(status_tokens):
            vals = status_tokens[status]
            if vals:
                med = statistics.median(vals)
                avg = _mean(vals)
                n = len(vals)
                print(
                    f"    {status:<20} "
                    f"median={med:.0f}  "
                    f"mean={avg:.0f}  "
                    f"n={n}"
                )
    else:
        print("  No prompt token data available.")
    print()

    # --- Delta injection effectiveness ---
    # Group by conversation_key to compute per-conversation stats.
    conversations: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        key = r.get("conversation_key", "__new__")
        conversations.setdefault(key, []).append(r)

    suppression_ratios: list[float] = []
    for key, turns in conversations.items():
        if len(turns) <= 1:
            continue
        for turn in turns:
            ctx = turn.get("context", {})
            new = ctx.get("symbols_new", 0)
            suppressed = ctx.get("symbols_suppressed", 0)
            denominator = new + suppressed
            if denominator > 0:
                suppression_ratios.append(suppressed / denominator)

    print("-" * 40)
    print("DELTA INJECTION EFFECTIVENESS")
    print("-" * 40)
    if suppression_ratios:
        print(f"  Conversations with >1 turn: {len(conversations)}")
        print(f"  Mean suppression ratio:     {_mean(suppression_ratios):.3f}")
        print(f"  Median suppression ratio:   {statistics.median(suppression_ratios):.3f}")
        print(f"  Min:                        {min(suppression_ratios):.3f}")
        print(f"  Max:                        {max(suppression_ratios):.3f}")
        print()
        print("  (A ratio of 0.8 means 80% of selected symbols were suppressed")
        print("   because they were already in the conversation window.)")
    else:
        print("  No multi-turn conversation data available.")
    print()

    # --- Turns per conversation ---
    print("-" * 40)
    print("TURNS PER CONVERSATION")
    print("-" * 40)
    turn_counts = [len(turns) for turns in conversations.values()]
    if turn_counts:
        print(f"  Total conversations:  {len(conversations)}")
        print(f"  Median turns:         {statistics.median(turn_counts)}")
        print(f"  Max turns:            {max(turn_counts)}")
        print(f"  Min turns:            {min(turn_counts)}")
    print()

    # --- 5 slowest requests ---
    print("-" * 40)
    print("5 SLOWEST REQUESTS")
    print("-" * 40)
    sorted_by_latency = sorted(
        records,
        key=lambda r: (r.get("timing", {}).get("total_ms") or 0),
        reverse=True,
    )
    for i, r in enumerate(sorted_by_latency[:5], start=1):
        req_id = r.get("request_id", "unknown")[:12]
        latency = r.get("timing", {}).get("total_ms", 0) or 0
        tokens = r.get("usage", {}).get("prompt_tokens") or 0
        preview = r.get("last_user_message", "")[:80]
        print(f"  {i:>1}. id={req_id}  latency={latency:.0f}ms  prompt_tokens={tokens}")
        print(f"     msg: {preview}")
    print()

    # --- Error requests ---
    error_records = [r for r in records if r.get("status") == "error"]
    if error_records:
        print("-" * 40)
        print("ERROR REQUESTS")
        print("-" * 40)
        for r in error_records:
            req_id = r.get("request_id", "unknown")[:12]
            error_msg = r.get("error", "unknown")[:120]
            preview = r.get("last_user_message", "")[:80]
            print(f"  id={req_id}  error={error_msg}")
            print(f"     msg: {preview}")
        print()
    else:
        print("-" * 40)
        print("No error requests found.")
        print()

    print("=" * 60)
    print("END OF REPORT")
    print("=" * 60)


def main() -> None:
    """CLI entry point for the session log analyzer."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <session_log.jsonl>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    records = _load_records(path)
    analyze(records)


if __name__ == "__main__":
    main()
