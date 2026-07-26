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
- **Timing breakdown**: pipeline_ms vs provider_wait_ms
- **Latency-by-prompt-size buckets** with Pearson correlation
- **Context cost**: tokens added and assembly time

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


# ---------------------------------------------------------------------------
# Additional helpers for attribution analysis
# ---------------------------------------------------------------------------


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two lists.

    Args:
        x: First list of values.
        y: Second list of values (same length as *x*).

    Returns:
        The Pearson r coefficient in [-1, 1], or 0.0 if lists are empty
        or variance is zero.
    """
    n = len(x)
    if n < 2:
        return 0.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_x2 = sum(v * v for v in x)
    sum_y2 = sum(v * v for v in y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    numerator = n * sum_xy - sum_x * sum_y
    denom = math.sqrt(
        (n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)
    )
    if denom == 0:
        return 0.0
    return numerator / denom


def _bucket_key(tokens: int) -> str:
    """Return the bucket string for a prompt-token count.

    Args:
        tokens: Number of prompt tokens.

    Returns:
        A bucket label such as ``<10k``, ``10-30k``, ``30-60k``, or ``>60k``.
    """
    if tokens < 10_000:
        return "<10k"
    elif tokens < 30_000:
        return "10-30k"
    elif tokens < 60_000:
        return "30-60k"
    else:
        return ">60k"


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

    # --- Timing breakdown: pipeline vs provider ---
    _print_timing_breakdown(records)

    # --- Latency-by-prompt-size buckets + correlation ---
    _print_latency_buckets(records)

    # --- Context cost ---
    _print_context_cost(records)

    # --- 5 slowest requests (with attribution) ---
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
        completion_tokens = r.get("usage", {}).get("completion_tokens") or 0
        preview = r.get("last_user_message", "")[:80]
        t = r.get("timing", {})
        pipeline_ms = t.get("pipeline_ms")
        provider_wait = t.get("provider_wait_ms")
        ctx_status = r.get("context", {}).get("status", "unknown")

        detail = (
            f"  {i:>1}. id={req_id}  latency={latency:.0f}ms  "
            f"prompt_tokens={tokens}  completion_tokens={completion_tokens}"
        )
        if pipeline_ms is not None:
            detail += (
                f"  pipeline_ms={float(pipeline_ms):.0f}"
                f"  provider_wait_ms={float(provider_wait or 0):.0f}"
            )
        detail += f"  context={ctx_status}"
        print(detail)
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


def _print_timing_breakdown(records: list[dict[str, Any]]) -> None:
    """Print the timing breakdown section.

    Shows pipeline_ms vs provider_wait_ms for every record that has
    those fields.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("TIMING BREAKDOWN: pipeline vs provider")
    print("-" * 40)

    has_pipeline = False
    for r in records:
        t = r.get("timing", {})
        if t.get("pipeline_ms") is not None or t.get("provider_wait_ms") is not None:
            has_pipeline = True
            break

    if not has_pipeline:
        print("  No timing breakdown data available (pipeline_ms / provider_wait_ms).")
        print("  This is expected for session logs generated before this feature.")
        print()
        return

    pipeline_values: list[float] = []
    provider_values: list[float] = []
    for r in records:
        t = r.get("timing", {})
        pm = t.get("pipeline_ms")
        pw = t.get("provider_wait_ms")
        if pm is not None:
            pipeline_values.append(float(pm))
        if pw is not None:
            provider_values.append(float(pw))

    if pipeline_values:
        print("  Pipeline overhead (our code):")
        print(f"    Median:  {statistics.median(pipeline_values):.1f} ms")
        print(f"    Mean:    {_mean(pipeline_values):.1f} ms")
    if provider_values:
        print("  Provider wait (vLLM):")
        print(f"    Median:  {statistics.median(provider_values):.1f} ms")
        print(f"    Mean:    {_mean(provider_values):.1f} ms")

    # Stages breakdown (if available)
    for r in records:
        t = r.get("timing", {})
        stages = t.get("stages")
        if stages:
            print()
            print("  Stage durations (sample):")
            for stage, dur in sorted(stages.items(), key=lambda x: -x[1]):
                print(f"    {stage:>25}  {dur:.1f} ms")
            break

    print()


def _print_latency_buckets(records: list[dict[str, Any]]) -> None:
    """Print the latency-by-prompt-size bucket table.

    Buckets: ``<10k``, ``10-30k``, ``30-60k``, ``>60k`` prompt tokens.
    Shows median and p90 total latency and median provider_wait_ms per bucket.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("LATENCY BY PROMPT SIZE")
    print("-" * 40)

    # Bucket data: key -> list of (total_ms, provider_wait_ms)
    buckets: dict[str, list[tuple[float, float]]] = {}
    for r in records:
        t = r.get("timing", {})
        u = r.get("usage", {})
        pt = u.get("prompt_tokens")
        tm = t.get("total_ms")
        pw = t.get("provider_wait_ms")
        if pt is None or tm is None:
            continue
        pt_int = int(pt)
        key = _bucket_key(pt_int)
        buckets.setdefault(key, []).append(
            (float(tm), float(pw) if pw is not None else 0.0)
        )

    if not buckets:
        print("  No data available.")
        print()
        return

    bucket_order = ["<10k", "10-30k", "30-60k", ">60k"]
    print(f"  {'Bucket':<10} {'n':>4} {'median_ms':>10} {'p90_ms':>10} {'median_provider_ms':>16}")
    print(f"  {'-' * 10} {'-' * 4} {'-' * 10} {'-' * 10} {'-' * 16}")
    for key in bucket_order:
        items = buckets.get(key, [])
        if not items:
            continue
        total_latencies = [x[0] for x in items]
        provider_lats = [x[1] for x in items]
        print(
            f"  {key:<10} {len(items):>4} "
            f"{_percentile(total_latencies, 50):>10.1f} "
            f"{_percentile(total_latencies, 90):>10.1f} "
            f"{_percentile(provider_lats, 50):>16.1f}"
        )
    print()

    # --- Pearson correlation ---
    print("CORRELATION COEFFICIENTS")
    print("-" * 40)

    paired_total: list[tuple[float, float]] = []
    paired_provider: list[tuple[float, float]] = []
    for r in records:
        t = r.get("timing", {})
        u = r.get("usage", {})
        pt = u.get("prompt_tokens")
        tm = t.get("total_ms")
        pw = t.get("provider_wait_ms")
        if pt is not None and tm is not None:
            paired_total.append((float(pt), float(tm)))
        if pt is not None and pw is not None:
            paired_provider.append((float(pt), float(pw)))

    if paired_total:
        xt, yt = zip(*paired_total)
        r_total = _pearson(list(xt), list(yt))
        print(f"  prompt_tokens vs total_ms:          r={r_total:.4f}")
    if paired_provider:
        xp, yp = zip(*paired_provider)
        r_provider = _pearson(list(xp), list(yp))
        print(f"  prompt_tokens vs provider_wait_ms:  r={r_provider:.4f}")
    print()


def _print_context_cost(records: list[dict[str, Any]]) -> None:
    """Print the context cost attribution section.

    Compares ``prompt_tokens`` on ``assembled`` vs ``empty``/``disabled``
    turns of similar conversation depth to estimate tokens added by
    context, and reports ``repository_context_ms`` assembly time.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("CONTEXT COST")
    print("-" * 40)

    # Gather prompt_tokens by context status
    assembled_tokens: list[int] = []
    empty_tokens: list[int] = []
    disabled_tokens: list[int] = []
    repo_ms_values: list[float] = []

    for r in records:
        t = r.get("timing", {})
        u = r.get("usage", {})
        ctx = r.get("context", {})
        pt = u.get("prompt_tokens")
        status = ctx.get("status", "disabled")
        if pt is not None:
            if status == "assembled":
                assembled_tokens.append(int(pt))
            elif status == "empty":
                empty_tokens.append(int(pt))
            elif status == "disabled":
                disabled_tokens.append(int(pt))
        stages = t.get("stages", {})
        rctx = stages.get("repository_context_ms")
        if rctx is not None:
            repo_ms_values.append(float(rctx))

    if assembled_tokens and (empty_tokens or disabled_tokens):
        baseline = empty_tokens if empty_tokens else disabled_tokens
        print("  Tokens added by context:")
        print(
            f"    Assembled turns:     "
            f"median={statistics.median(assembled_tokens):.0f}  "
            f"mean={_mean(assembled_tokens):.0f}  "
            f"n={len(assembled_tokens)}"
        )
        print(
            f"    Empty/disabled turns: "
            f"median={statistics.median(baseline):.0f}  "
            f"mean={_mean(baseline):.0f}  "
            f"n={len(baseline)}"
        )
        implied = [a - b for a, b in zip(assembled_tokens, baseline[:len(assembled_tokens)])]
        if implied:
            print(
                f"    Implied delta:       "
                f"~{statistics.median(implied):.0f} tokens (median)"
            )
    elif assembled_tokens:
        print("  Tokens added by context:")
        print(
            f"    Assembled turns:     "
            f"median={statistics.median(assembled_tokens):.0f}  "
            f"mean={_mean(assembled_tokens):.0f}  "
            f"n={len(assembled_tokens)}"
        )
    print()

    if repo_ms_values:
        print("  Assembly time (repository_context_ms):")
        print(f"    Median:  {statistics.median(repo_ms_values):.1f} ms")
        print(f"    Mean:    {_mean(repo_ms_values):.1f} ms")
    else:
        print("  Assembly time: no per-stage data available.")
    print()


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


