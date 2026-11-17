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
- **Context cost**: repository-context tokens, prompt share, and assembly time
- **Changed-file promotion**: whether the working-tree bonus changed the context
  that was sent, tallied by signal state and by whether the comparison ran
- **File activity**: what the transcripts the gateway was sent show the agent
  reading and modifying, reported as per-record snapshots - never summed into a
  cross-record total - with the state and correlation tokens kept distinct
- **History-shape cap simulation**: what the production history cap would have
  done to each recorded `history.shape` at a list of candidate budgets, walked
  offline from the recorded structure alone and reported with the records it
  could settle kept apart from the ones its bounded detail could not

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


def _preview_text(value: Any, *, fallback: str, limit: int) -> str:
    """Return one record field as printable text, whatever the log held in it.

    A field a writer means to be a string can arrive as ``None`` - a failed
    request with no parseable error body logs ``error: null`` - or as a number, a
    bool or a container. Slicing any of those directly aborts the report halfway
    through a section, and a milestone report that dies on one stray field is
    worse than one that prints a placeholder, so conversion happens before
    truncation.

    Args:
        value: The raw field. ``None`` selects the fallback.
        fallback: Text used when the field is missing or ``None``.
        limit: Maximum number of characters to return.

    Returns:
        Up to ``limit`` characters of ``value`` converted to text deterministically:
        the fallback for ``None``, the ordinary string unchanged for text, and the
        ``str`` form for anything else. Never raises on a well-formed record.
    """
    if value is None:
        text = fallback
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    return text[:limit]


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

    # --- Changed-file promotion (counterfactual, count-only) ---
    _print_changed_file_promotion(records)

    # --- Conversation file activity (per-record snapshots, count-only) ---
    _print_file_activity(records)

    # --- History capping stats ---
    _print_history_capping(records)

    # --- History-shape cap simulation (offline, structure-only) ---
    _print_history_shape_simulation(records)

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
        req_id = _preview_text(r.get("request_id"), fallback="unknown", limit=12)
        latency = r.get("timing", {}).get("total_ms", 0) or 0
        tokens = r.get("usage", {}).get("prompt_tokens") or 0
        completion_tokens = r.get("usage", {}).get("completion_tokens") or 0
        preview = _preview_text(r.get("last_user_message"), fallback="", limit=80)
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
            req_id = _preview_text(r.get("request_id"), fallback="unknown", limit=12)
            error_msg = _preview_text(r.get("error"), fallback="unknown", limit=120)
            preview = _preview_text(r.get("last_user_message"), fallback="", limit=80)
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


def _print_history_capping(records: list[dict[str, Any]]) -> None:
    """Print the history capping analysis section.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("HISTORY CAPPING")
    print("-" * 40)

    cap_enabled_count = 0
    cap_applied_count = 0
    budget_values: list[int] = []
    dropped_count_values: list[int] = []
    tokens_after_values: list[int] = []

    for r in records:
        h = r.get("history", {})
        if h.get("cap_enabled", False):
            cap_enabled_count += 1
        if h.get("cap_applied", False):
            cap_applied_count += 1
        budget = h.get("budget", 0)
        if budget:
            budget_values.append(int(budget))
        dc = h.get("dropped_count", 0)
        ta = h.get("tokens_after", 0)
        tokens_after_values.append(ta)
        if dc and int(dc) > 0:
            dropped_count_values.append(int(dc))

    print(f"  requests with cap enabled:       {cap_enabled_count}")
    print(f"  requests where cap ran:          {cap_applied_count}")
    if budget_values:
        print(f"  median cap budget:               {statistics.median(budget_values):.0f}")
    print(f"  requests where history was dropped: {len(dropped_count_values)}")
    if dropped_count_values:
        print(f"  median dropped_count (when >0):   {statistics.median(dropped_count_values):.0f}")
    if tokens_after_values:
        print(f"  median tokens_after:              {statistics.median(tokens_after_values):.0f}")
    print()


# ---------------------------------------------------------------------------
# History-shape cap simulation (offline, structure-only)
# ---------------------------------------------------------------------------
#
# ``packages/pipeline/history_shape.summarize_history_shape`` records, per
# request, what the inbound message list is made of - the atomic groups
# ``cap_history`` would keep or drop, each priced by the same
# ``_message_token_count`` the cap prices it with, in the same newest-first
# order, bounded to a prefix of that order and with the mass it left out stated
# rather than hidden.  What follows reads that record back and answers the
# question the roadmap item is about - what a budget would have done - without a
# request, a message, or a single character of content.
#
# This is analysis.  Nothing here selects, enables or changes a runtime cap: the
# budgets below are candidates swept offline, and no code path consults them.

#: The budgets the offline sweep simulates.  Stated here rather than read from
#: configuration, because ``APP_HISTORY_CAP_TOKENS`` is set to none of them -
#: capping is off on the live path - and the point of the sweep is to compare
#: candidates against real shapes, not to echo whatever a deployment runs.
HISTORY_CAP_CANDIDATE_BUDGETS: tuple[int, ...] = (16384, 32768, 65536, 98304, 131072)

#: The one summary schema this walk reproduces.  A record that states another is
#: tallied as ``unknown_schema`` rather than simulated: the field meanings, and
#: in particular what the bounded detail counts, are what make the walk faithful,
#: and those are not promised across versions.
SUPPORTED_SHAPE_SCHEMA: str = "history-shape-v2"

#: Status tokens of :data:`SUPPORTED_SHAPE_SCHEMA`.  ``measured`` summaries carry
#: the walk's inputs; ``unavailable`` ones carry neither, and are what keeps an
#: absent measurement from being read as a transcript of zero tokens.
SUPPORTED_SHAPE_MEASURED: str = "measured"
SUPPORTED_SHAPE_UNAVAILABLE: str = "unavailable"

#: The scalar fields the walk consumes.  A ``measured`` summary missing any of
#: them came from a writer this simulation does not agree with, so it is reported
#: as malformed and skipped rather than defaulted to a zero - a missing
#: ``cap_eligible_tokens`` read as ``0`` would say "this history needs no cap".
#: The two partition fields are here because they decide what a bounded detail
#: may be asked: ``omitted_cap_eligible_tokens`` is the difference between "the
#: cut is somewhere the record never wrote" and "nothing left to drop".
SHAPE_WALK_FIELDS: tuple[str, ...] = (
    "message_count",
    "system_message_count",
    "cap_eligible_tokens",
    "recorded_cap_eligible_tokens",
    "omitted_cap_eligible_tokens",
    "group_count",
    "recorded_groups",
    "omitted_messages",
    "orphan_tool_calls",
    "orphan_tool_results",
)

SHAPE_WALK_FLAGS: tuple[str, ...] = ("detail_complete",)

#: The fields of one group entry, prefix entry or reservation alike.
SHAPE_GROUP_FIELDS: tuple[str, ...] = ("ordinal", "message_count", "cap_eligible_tokens")

SHAPE_GROUP_FLAGS: tuple[str, ...] = ("has_system", "has_last_user")

#: The five ways a record's shape can read, covering every record exactly once.
SHAPE_CLASSIFICATIONS: tuple[str, ...] = (
    "measured",
    "no_shape",
    "unavailable",
    "unknown_schema",
    "malformed",
)


def _shape_int(value: Any) -> int | None:
    """Return a shape's integer field, or ``None`` when it is not one.

    ``bool`` is excluded on purpose: ``True`` is an ``int`` to Python and would
    otherwise read as one message, or one token, where the writer meant a flag.

    Args:
        value: The raw field.

    Returns:
        The value as an int, or ``None``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _shape_group_is_walkable(entry: Any) -> bool:
    """Return whether one group entry states what the walk reads off it."""
    if not isinstance(entry, dict):
        return False
    if any(_shape_int(entry.get(key)) is None for key in SHAPE_GROUP_FIELDS):
        return False
    return all(isinstance(entry.get(key), bool) for key in SHAPE_GROUP_FLAGS)


def _shape_is_walkable(shape: dict[str, Any]) -> bool:
    """Return whether a ``measured`` summary states every field the walk needs.

    Args:
        shape: The candidate summary, already known to be a dict carrying the
            supported schema and status.

    Returns:
        ``False`` when any consumed field is missing or is not the kind of value
        the walk can add, compare or subtract, and ``False`` when the summary's
        own ``recorded + omitted == cap_eligible_tokens`` partition does not
        hold.  That equation is what the walk reads a truncated detail by, so a
        summary that breaks it is a disagreeing writer rather than an awkward
        transcript, and it is reported as malformed rather than clamped into
        agreement.  An empty ``groups`` list is not malformed - it is a summary
        whose whole detail was left out by the bound, which is a real and
        reportable state.
    """
    if any(_shape_int(shape.get(key)) is None for key in SHAPE_WALK_FIELDS):
        return False
    if any(not isinstance(shape.get(key), bool) for key in SHAPE_WALK_FLAGS):
        return False
    recorded_eligible = int(shape["recorded_cap_eligible_tokens"])
    omitted_eligible = int(shape["omitted_cap_eligible_tokens"])
    if recorded_eligible < 0 or omitted_eligible < 0:
        return False
    if recorded_eligible + omitted_eligible != int(shape["cap_eligible_tokens"]):
        return False
    if "groups" not in shape or "last_user_group" not in shape:
        return False
    groups = shape["groups"]
    if not isinstance(groups, list) or shape["recorded_groups"] != len(groups):
        return False
    if not all(_shape_group_is_walkable(entry) for entry in groups):
        return False
    reserved = shape["last_user_group"]
    return reserved is None or _shape_group_is_walkable(reserved)


def classify_history_shape(record: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Read one session record's ``history.shape`` into a simulation verdict.

    Args:
        record: One session log record.

    Returns:
        ``(classification, shape)``.  The classification is one of
        :data:`SHAPE_CLASSIFICATIONS`, and the shape is returned only for
        ``"measured"``, so a caller cannot simulate a record this function said
        it could not.  A record written before the summary existed is
        ``"no_shape"`` - the key is absent rather than null - which is the normal
        case for every log that predates ``APP_HISTORY_SHAPE_LOG_ENABLED``.
    """
    history = record.get("history")
    if not isinstance(history, dict) or "shape" not in history:
        return "no_shape", None
    shape = history["shape"]
    if not isinstance(shape, dict):
        return "malformed", None
    schema = shape.get("schema")
    if not isinstance(schema, str):
        return "malformed", None
    if schema != SUPPORTED_SHAPE_SCHEMA:
        return "unknown_schema", None
    status = shape.get("status")
    if status == SUPPORTED_SHAPE_UNAVAILABLE:
        return "unavailable", None
    if status != SUPPORTED_SHAPE_MEASURED:
        return "malformed", None
    if not _shape_is_walkable(shape):
        return "malformed", None
    return "measured", shape


def _omitted_non_system_messages(shape: dict[str, Any]) -> int:
    """How many messages the bounded detail left out are not system text.

    Both figures this divides are exact over the whole message list:
    ``omitted_messages`` states how many messages the bound hid, and
    ``system_message_count`` minus the system messages the detail did write -
    the prefix's own ``has_system`` groups, plus a reserved group sitting outside
    that prefix - states how many of them are system text.  What remains is the
    count of hidden messages that ``cap_history`` would price against a budget,
    and so the only ones that could make a group it never saw a candidate.

    Args:
        shape: A summary that :func:`classify_history_shape` returned as usable.

    Returns:
        ``0`` when every omitted message is system text, which is the case in
        which a bounded detail hides nothing the cap is allowed to drop.
    """
    groups = shape["groups"]
    reserved = shape["last_user_group"]
    recorded_ordinals = {int(entry["ordinal"]) for entry in groups}
    recorded_system = sum(
        int(entry["message_count"]) for entry in groups if entry["has_system"]
    )
    if (
        reserved is not None
        and reserved["has_system"]
        and int(reserved["ordinal"]) not in recorded_ordinals
    ):
        recorded_system += int(reserved["message_count"])
    omitted_system = max(0, int(shape["system_message_count"]) - recorded_system)
    return max(0, int(shape["omitted_messages"]) - omitted_system)


def simulate_cap_from_shape(shape: dict[str, Any], budget: int) -> dict[str, Any]:
    """Walk one recorded shape at one budget, as ``cap_history`` walks it.

    The rule is the production rule restated in the summary's own fields:

    - the totals are exact over the whole message list, so
      ``cap_eligible_tokens <= budget`` proves the cap is a no-op (rule 6)
      whatever the detail bound left out;
    - otherwise the protected group is *reserved* - kept whole, and charged its
      own ``cap_eligible_tokens`` against the budget before any other group is
      considered, because only the protected message inside it is free (rule 2);
    - every other group is walked by ascending ``ordinal``, the newest-first
      order ``cap_history`` sorts its candidates into by maximum index (rule 3),
      stopping at the first group that does not fit;
    - a group marked ``has_system`` is not a step of that walk: capping keeps
      system messages whatever the budget says and charges them nothing, so an
      old system message is neither dropped by a cut nor able to cause one
      (rule 1);
    - ``last_user_group`` repeats rather than replaces the prefix's own entry for
      that group, so it is reserved once and skipped by the walk, and it is not a
      member of ``groups`` (rule 5).

    Args:
        shape: A summary :func:`classify_history_shape` returned as usable.
        budget: The candidate ``max_history_tokens`` to simulate.

    Returns:
        A result dict.  ``outcome`` is ``"capped"``, ``"unchanged"`` or
        ``"indeterminate"`` and ``exact`` says whether the record proves the
        answer.  A result is exact only when the totals prove that no cap would
        run, the recorded prefix proves where it stops, or the totals prove that
        nothing outside the prefix could be dropped even though the detail is
        short.  When every recorded group fits and eligible history is still
        outstanding, the cut lies in the part that was never written: the result
        is ``indeterminate`` with both drop figures ``None``, because the omitted
        groups are not assumed uniform and no cut point is interpolated.  A
        bounded detail that hid no eligible tokens is settled - the cap keeps
        system text at any budget - unless it also hid a zero-cost non-system
        group while the reservation had already spent the budget, in which case
        the record cannot say which unseen group the cap would stop at.
    """
    eligible_total = int(shape["cap_eligible_tokens"])
    groups = shape["groups"]
    reserved = shape["last_user_group"]
    reserved_tokens = int(reserved["cap_eligible_tokens"]) if reserved else 0
    result: dict[str, Any] = {
        "budget": budget,
        "eligible_tokens": eligible_total,
        "reserved_tokens": reserved_tokens,
        "detail_complete": bool(shape["detail_complete"]),
        "protected_position_without_user": bool(
            reserved is not None and shape.get("last_user_distance") is None
        ),
    }

    if eligible_total <= budget:
        result.update(
            {
                "outcome": "unchanged",
                "exact": True,
                "reason": "within_budget",
                "dropped_messages": 0,
                "dropped_cap_eligible_tokens": 0,
                # Nothing left, so everything chargeable is still there: read
                # ``charged_tokens`` as "cap-eligible tokens that survive", the
                # same figure the capped branch reports.
                "charged_tokens": eligible_total,
                "cut_ordinal": None,
            }
        )
        return result

    # The reservation is spent before the walk gets what is left of the budget,
    # and it is spent even when it is more than the budget: the group is atomic,
    # so a cap that cannot fit it still cannot split it.
    kept: set[int] = set()
    charged = reserved_tokens
    if reserved is not None:
        kept.add(int(reserved["ordinal"]))

    # System groups leave the walk and come back at the end, charged nothing,
    # exactly as the cap keeps them.  An ordinal already reserved is not also a
    # system step, so a protected position landing on a system message buys
    # nothing twice.
    system = {
        int(entry["ordinal"])
        for entry in groups
        if entry["has_system"] and int(entry["ordinal"]) not in kept
    }

    cut_ordinal: int | None = None
    for entry in groups:
        ordinal = int(entry["ordinal"])
        if ordinal in kept or ordinal in system:
            continue
        cost = int(entry["cap_eligible_tokens"])
        if charged + cost <= budget:
            charged += cost
            kept.add(ordinal)
        else:
            cut_ordinal = ordinal
            break

    if cut_ordinal is None:
        # The walk ran out of recorded groups without stopping.  What that means
        # depends on the one thing a bounded detail always states: the
        # cap-eligible mass it left out.
        if int(shape["omitted_cap_eligible_tokens"]) == 0:
            # Nothing chargeable is outstanding, so every group the bound hid is
            # worth zero to a budget.  That is true of a system group, which the
            # cap keeps at any budget, and of a non-system group whose messages all
            # estimate to nothing - an empty assistant turn, say - which the cap
            # asks the same question of as any other candidate.  Reaching this
            # point with no cut already means ``charged`` equals the whole
            # eligible total, which is more than the budget - so with the
            # partition validated the question is never whether an unseen group
            # fits, only whether it is a candidate at all.
            if _omitted_non_system_messages(shape) == 0:
                # It is not: every hidden message is system text, so this is
                # ``cap_history``'s own no-op.  With nothing left it is allowed to
                # drop, it returns the list untouched even when the reservation alone
                # exceeds the budget.  That holds whether or not ``detail_complete``
                # says the whole list was written out - a transcript can omit only
                # system groups and still be incomplete.
                result.update(
                    {
                        "outcome": "unchanged",
                        "exact": True,
                        "reason": "nothing_chargeable",
                        "dropped_messages": 0,
                        "dropped_cap_eligible_tokens": 0,
                        "charged_tokens": charged,
                        "cut_ordinal": None,
                        "kept_groups": int(shape["group_count"]),
                        "dropped_groups": 0,
                    }
                )
                return result
            # A zero-cost candidate is hidden beyond the detail and the reservation
            # has already spent the budget, so the cap would stop at the newest of
            # those unseen groups and this record cannot say which one.
            result.update(
                {
                    "outcome": "indeterminate",
                    "exact": False,
                    "reason": "zero_cost_candidate_unseen",
                    "dropped_messages": None,
                    "dropped_cap_eligible_tokens": None,
                    "charged_tokens": charged,
                    "cut_ordinal": None,
                }
            )
            return result
        # Chargeable history is still outstanding, so the cut lies inside the
        # groups the bound left out and this record says nothing about where.
        # ``charged`` is how far the recorded detail reaches: every smaller budget
        # is exact on this record, and that is the only claim a larger one gets.
        result.update(
            {
                "outcome": "indeterminate",
                "exact": False,
                "reason": "detail_short_by_bound",
                "dropped_messages": None,
                "dropped_cap_eligible_tokens": None,
                "charged_tokens": charged,
                "cut_ordinal": None,
            }
        )
        return result

    # Older than the cut everything goes, so what stays is the recorded groups the
    # walk reached, the reserved group wherever it sits, and every system message
    # - including the ones in groups too old to have been recorded, whose count
    # is exact at the top level.  Ordinals decide it and the groups partition the
    # list, so no message is counted twice.
    kept_ordinals = kept | system
    kept_messages = sum(
        int(entry["message_count"])
        for entry in groups
        if int(entry["ordinal"]) in kept_ordinals
    )
    reserved_recorded = reserved is not None and any(
        int(entry["ordinal"]) == int(reserved["ordinal"]) for entry in groups
    )
    if reserved is not None and not reserved_recorded:
        kept_messages += int(reserved["message_count"])
    recorded_system = sum(int(entry["message_count"]) for entry in groups if entry["has_system"])
    omitted_system = max(0, int(shape["system_message_count"]) - recorded_system)
    if reserved is not None and not reserved_recorded and reserved["has_system"]:
        omitted_system = max(0, omitted_system - int(reserved["message_count"]))
    kept_messages += omitted_system

    result.update(
        {
            "outcome": "capped",
            "exact": True,
            "reason": "first_group_does_not_fit",
            "dropped_messages": max(0, int(shape["message_count"]) - kept_messages),
            "dropped_cap_eligible_tokens": max(0, eligible_total - charged),
            "charged_tokens": charged,
            "cut_ordinal": cut_ordinal,
            "kept_groups": len(kept_ordinals),
            "dropped_groups": max(0, int(shape["group_count"]) - len(kept_ordinals)),
        }
    )
    return result


def history_shape_records(
    records: list[dict[str, Any]],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Split a session log into shape classifications and usable summaries.

    Args:
        records: Session log record dicts, as read from JSONL.

    Returns:
        ``(tally, shapes)``, where the tally covers every record exactly once and
        ``shapes`` holds the summary of each ``measured`` record, in file order.
    """
    tally = {kind: 0 for kind in SHAPE_CLASSIFICATIONS}
    shapes: list[dict[str, Any]] = []
    for record in records:
        kind, shape = classify_history_shape(record)
        tally[kind] += 1
        if shape is not None:
            shapes.append(shape)
    return tally, shapes


def history_cap_simulation_summary(
    records: list[dict[str, Any]],
    budgets: tuple[int, ...] = HISTORY_CAP_CANDIDATE_BUDGETS,
) -> dict[str, Any]:
    """Simulate the production history cap over recorded shapes, at each budget.

    Args:
        records: Session log record dicts, as read from JSONL.
        budgets: The candidate ``max_history_tokens`` to sweep.

    Returns:
        A record tally covering every input record, and one entry per budget.
        Each budget entry keeps ``exact`` and ``indeterminate`` apart and every
        figure inside it names its own denominator: ``usable`` is the sweep's
        whole, ``exact`` divides by it, and the drop distributions divide by
        ``capped`` alone.  Indeterminate records enter no percentile and no rate.
    """
    tally, shapes = history_shape_records(records)

    # Readings of the same shapes that no budget can change: what the summaries
    # say about pairing, about the protected position, and about how far their own
    # detail reached.
    orphan_records = sum(
        1
        for shape in shapes
        if int(shape["orphan_tool_calls"]) > 0 or int(shape["orphan_tool_results"]) > 0
    )
    bounded_records = sum(1 for shape in shapes if not shape["detail_complete"])
    no_user_protected_records = sum(
        1
        for shape in shapes
        if shape["last_user_group"] is not None and shape.get("last_user_distance") is None
    )
    nothing_protected_records = sum(1 for shape in shapes if shape["last_user_group"] is None)

    by_budget: list[dict[str, Any]] = []
    for budget in budgets:
        results = [simulate_cap_from_shape(shape, budget) for shape in shapes]
        exact = [r for r in results if r["exact"]]
        capped = [r for r in results if r["outcome"] == "capped"]
        unchanged = [r for r in results if r["outcome"] == "unchanged"]
        indeterminate = [r for r in results if r["outcome"] == "indeterminate"]
        messages_dropped = [float(r["dropped_messages"]) for r in capped]
        tokens_dropped = [float(r["dropped_cap_eligible_tokens"]) for r in capped]
        coverage = [float(r["charged_tokens"]) for r in indeterminate]
        reserved_values = [r["reserved_tokens"] for r in results]
        by_budget.append(
            {
                "budget": budget,
                "usable": len(results),
                "exact": len(exact),
                "indeterminate": len(indeterminate),
                "capped": len(capped),
                "unchanged": len(unchanged),
                # A cap that cannot help at all: the reservation is the only
                # chargeable history the record holds.
                "nothing_chargeable": sum(
                    1 for r in results if r.get("reason") == "nothing_chargeable"
                ),
                "rate_capped": (len(capped) / len(exact)) if exact else 0.0,
                "messages_dropped": {
                    "n": len(messages_dropped),
                    "p50": _percentile(messages_dropped, 50),
                    "p90": _percentile(messages_dropped, 90),
                    "max": max(messages_dropped) if messages_dropped else 0.0,
                },
                "tokens_dropped": {
                    "n": len(tokens_dropped),
                    "p50": _percentile(tokens_dropped, 50),
                    "p90": _percentile(tokens_dropped, 90),
                    "max": max(tokens_dropped) if tokens_dropped else 0.0,
                },
                "indeterminate_coverage": {
                    "n": len(coverage),
                    "p50": _percentile(coverage, 50),
                    "p90": _percentile(coverage, 90),
                    "max": max(coverage) if coverage else 0.0,
                },
                # The reservation is stated by every summary and needs no detail
                # bound to read, so these divide by usable rather than by exact.
                "protected_over_budget": sum(1 for v in reserved_values if v > budget),
                "protected_at_budget": sum(1 for v in reserved_values if v == budget),
                "capped_with_orphans": sum(
                    1
                    for result, shape in zip(results, shapes)
                    if result["outcome"] == "capped"
                    and (
                        int(shape["orphan_tool_calls"]) > 0
                        or int(shape["orphan_tool_results"]) > 0
                    )
                ),
            }
        )

    return {
        "records": len(records),
        "tally": tally,
        "usable": len(shapes),
        "orphan_records": orphan_records,
        "orphan_tool_calls": sum(int(shape["orphan_tool_calls"]) for shape in shapes),
        "orphan_tool_results": sum(int(shape["orphan_tool_results"]) for shape in shapes),
        "bounded_records": bounded_records,
        "complete_records": len(shapes) - bounded_records,
        "no_user_protected_records": no_user_protected_records,
        "nothing_protected_records": nothing_protected_records,
        "budgets": by_budget,
    }


def _print_history_shape_simulation(records: list[dict[str, Any]]) -> None:
    """Print the history-shape cap simulation section.

    Every number here comes from
    :func:`history_cap_simulation_summary`; this function only formats it.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("HISTORY-SHAPE CAP SIMULATION")
    print("-" * 40)

    summary = history_cap_simulation_summary(records)
    tally = summary["tally"]
    excluded = sum(tally[key] for key in SHAPE_CLASSIFICATIONS if key != "measured")
    print(f"  records:                      {summary['records']}")
    print(f"  usable measured shapes:       {summary['usable']}")
    for key, label in (
        ("no_shape", "no history.shape"),
        ("unavailable", "shape status unavailable"),
        ("unknown_schema", "unknown shape schema"),
        ("malformed", "malformed shape"),
    ):
        print(f"    {label:<26}{tally[key]:>6}  (excluded below)")
    if summary["records"] != summary["usable"] + excluded:
        print("    NOTE: the classifications do not cover every record.")
    print()
    print(f"  shapes with complete detail:      {summary['complete_records']}")
    print(f"  shapes left short by the bound:   {summary['bounded_records']}")
    print(
        f"  protected position, no user:      {summary['no_user_protected_records']}"
        "  (fallback index)"
    )
    print(f"  nothing to protect at all:        {summary['nothing_protected_records']}")
    print(
        f"  records with orphans:             {summary['orphan_records']}"
        f"  (calls {summary['orphan_tool_calls']},"
        f" results {summary['orphan_tool_results']})"
    )
    print()
    print("  candidate budget sweep - simulated offline; no cap is chosen or enabled")
    header = (
        f"  {'budget':>8} {'usable':>7} {'exact':>6} {'indet':>6}"
        f" {'capped':>7} {'unchanged':>10} {'nochg':>6} {'prot>':>6} {'prot=':>6}"
        f" {'orphan':>7}"
    )
    print(header)
    print(
        f"  {'-' * 8} {'-' * 7} {'-' * 6} {'-' * 6} {'-' * 7} {'-' * 10} {'-' * 6}"
        f" {'-' * 6} {'-' * 6} {'-' * 7}"
    )
    for entry in summary["budgets"]:
        print(
            f"  {entry['budget']:>8} {entry['usable']:>7} {entry['exact']:>6}"
            f" {entry['indeterminate']:>6} {entry['capped']:>7} {entry['unchanged']:>10}"
            f" {entry['nothing_chargeable']:>6} {entry['protected_over_budget']:>6}"
            f" {entry['protected_at_budget']:>6} {entry['capped_with_orphans']:>7}"
        )
    print()
    print("  what an exact cap would have dropped (exact capped records only)")
    print(
        f"  {'budget':>8} {'n':>6} {'msg p50':>8} {'p90':>7} {'max':>7}"
        f" {'tok p50':>9} {'p90':>8} {'max':>9}"
    )
    print(f"  {'-' * 8} {'-' * 6} {'-' * 8} {'-' * 7} {'-' * 7} {'-' * 9} {'-' * 8} {'-' * 9}")
    for entry in summary["budgets"]:
        msgs = entry["messages_dropped"]
        toks = entry["tokens_dropped"]
        print(
            f"  {entry['budget']:>8} {msgs['n']:>6} {msgs['p50']:>8.0f} {msgs['p90']:>7.0f}"
            f" {msgs['max']:>7.0f} {toks['p50']:>9.0f} {toks['p90']:>8.0f} {toks['max']:>9.0f}"
        )
    print()
    print("  indeterminate records: every group the detail recorded fit, and the")
    print("  summary still states eligible history outstanding, so the cut is not")
    print("  in the record.  How far the recorded detail reaches for those:")
    print(f"  {'budget':>8} {'n':>6} {'covered p50':>12} {'p90':>10} {'max':>10}")
    for entry in summary["budgets"]:
        cov = entry["indeterminate_coverage"]
        print(
            f"  {entry['budget']:>8} {cov['n']:>6} {cov['p50']:>12.0f}"
            f" {cov['p90']:>10.0f} {cov['max']:>10.0f}"
        )
    print()
    print("  Denominators: usable = exact + indeterminate.  Percentiles and the")
    print("  capped rate use exact records only, and never an indeterminate one;")
    print("  the exact column divides by usable.  A budget is exact where the")
    print("  totals prove no cap would run, the recorded groups prove where it")
    print("  stops, or the recorded eligible partition proves everything the")
    print("  detail left out is system text the cap keeps anyway - so a record")
    print("  short only because an old system message fell past the bound settles")
    print("  as unchanged, not as unknown.  Where a hidden group would cost nothing")
    print("  and still be a candidate the cap stops at, the record says it does not")
    print("  know.  Omitted groups are not assumed uniform and no cut is")
    print("  interpolated.  prot> and prot= count every usable record, because the")
    print("  protected group's reservation needs no detail bound to read.  nochg is")
    print("  the part of unchanged with nothing chargeable outside the protected")
    print("  group - a budget that cannot drop anything.  This section reads no")
    print("  message content and prints no path, tool name, argument, id or hash.")
    print()


def _print_context_cost(records: list[dict[str, Any]]) -> None:
    """Print the context cost attribution section.

    Reports direct ``context.estimated_tokens`` values written by the
    repository-context stage. Also reports repository-context assembly
    time and, when available, a rough assembled-vs-baseline prompt delta.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("CONTEXT COST")
    print("-" * 40)

    # Gather prompt_tokens by context status and direct context estimates.
    assembled_tokens: list[int] = []
    empty_tokens: list[int] = []
    disabled_tokens: list[int] = []
    context_tokens: list[int] = []
    context_prompt_pct: list[float] = []
    context_budget_pct: list[float] = []
    context_budgets: list[int] = []
    repo_ms_values: list[float] = []
    by_intent: dict[str, dict[str, list[float]]] = {}

    for r in records:
        t = r.get("timing", {})
        u = r.get("usage", {})
        ctx = r.get("context", {})
        pt = u.get("prompt_tokens")
        status = ctx.get("status", "disabled")
        est = ctx.get("estimated_tokens")
        budget = ctx.get("max_tokens")
        if est is not None:
            est_int = int(est)
            if est_int > 0:
                intent = str(r.get("intent", "DEFAULT") or "DEFAULT").upper()
                intent_stats = by_intent.setdefault(
                    intent,
                    {
                        "estimated": [],
                        "budget": [],
                        "budget_pct": [],
                        "prompt_pct": [],
                    },
                )
                intent_stats["estimated"].append(float(est_int))
                context_tokens.append(est_int)
                if pt:
                    prompt_pct = (est_int / int(pt)) * 100
                    context_prompt_pct.append(prompt_pct)
                    intent_stats["prompt_pct"].append(prompt_pct)
                if budget:
                    budget_int = int(budget)
                    context_budgets.append(budget_int)
                    budget_pct = (est_int / budget_int) * 100
                    context_budget_pct.append(budget_pct)
                    intent_stats["budget"].append(float(budget_int))
                    intent_stats["budget_pct"].append(budget_pct)
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

    if context_tokens:
        print("  Direct repository context estimate:")
        print(
            f"    Median:  {statistics.median(context_tokens):.0f} tokens"
        )
        print(f"    Mean:    {_mean(context_tokens):.0f} tokens")
        print(f"    Min:     {min(context_tokens):.0f} tokens")
        print(f"    Max:     {max(context_tokens):.0f} tokens")
        print(f"    n:       {len(context_tokens)}")
        if context_prompt_pct:
            print(
                f"    Median share of prompt: "
                f"{statistics.median(context_prompt_pct):.1f}%"
            )
        if context_budgets:
            print(
                f"    Median configured budget: "
                f"{statistics.median(context_budgets):.0f} tokens"
            )
        if context_budget_pct:
            print(
                f"    Median budget utilization: "
                f"{statistics.median(context_budget_pct):.1f}%"
            )
        if by_intent:
            print()
            print("  By intent:")
            print(
                "    "
                f"{'intent':<12}{'n':>4}{'est_med':>10}{'budget_med':>12}"
                f"{'util_med':>11}{'prompt_med':>12}"
            )
            for intent in sorted(by_intent):
                stats = by_intent[intent]
                estimated = stats["estimated"]
                budgets = stats["budget"]
                budget_pct = stats["budget_pct"]
                prompt_pct = stats["prompt_pct"]
                budget_med = statistics.median(budgets) if budgets else 0.0
                util_med = statistics.median(budget_pct) if budget_pct else 0.0
                prompt_med = statistics.median(prompt_pct) if prompt_pct else 0.0
                print(
                    "    "
                    f"{intent:<12}{len(estimated):>4}"
                    f"{statistics.median(estimated):>10.0f}"
                    f"{budget_med:>12.0f}"
                    f"{util_med:>10.1f}%"
                    f"{prompt_med:>11.1f}%"
                )
    else:
        print("  Direct repository context estimate: no context token data.")
    print()

    if assembled_tokens and (empty_tokens or disabled_tokens):
        baseline = empty_tokens if empty_tokens else disabled_tokens
        print("  Prompt-token comparison by context status:")
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
        print("  Prompt-token comparison by context status:")
        print(
            f"    Assembled turns:     "
            f"median={statistics.median(assembled_tokens):.0f}  "
            f"mean={_mean(assembled_tokens):.0f}  "
            f"n={len(assembled_tokens)}"
        )
        print("    Baseline:            no empty/disabled turns available")
    print()

    if repo_ms_values:
        print("  Assembly time (repository_context_ms):")
        print(f"    Median:  {statistics.median(repo_ms_values):.1f} ms")
        print(f"    Mean:    {_mean(repo_ms_values):.1f} ms")
    else:
        print("  Assembly time: no per-stage data available.")
    print()


#: The changed-file promotion fields as ``apps/gateway/session_log.py`` writes
#: them.  A record without ``changed_files_signal`` predates the counterfactual
#: measurement and is reported separately instead of reading as a zero.
_PROMOTION_FIELDS = (
    "changed_files_count",
    "changed_symbols_selected",
    "changed_primary_promoted",
    "changed_symbols_promoted",
    "changed_context_differs",
    "changed_baseline_status",
    "changed_files_signal",
)

#: The baseline states a record can carry.  ``failed`` and an absent state both
#: mean the comparison was never made, so neither can be read either way.
#: ``not_sampled`` is the state roadmap B4 added: the bonus fired and the second
#: build was not asked for, which is a request that was never compared - not one
#: whose comparison found no difference.
_BASELINE_STATES = ("none", "built", "skipped_no_bonus", "not_sampled", "failed")
#: The states a counterfactual field is a reading under, and therefore the only
#: records the promotion counts and their rate divide by.  ``none`` is inert
#: rather than unmeasured - nothing was there to compare - so it is counted in
#: neither the numerator nor this denominator, while ``not_sampled`` and
#: ``failed`` land in ``unmeasured``.
_BASELINE_MEASURED = ("built", "skipped_no_bonus")


def changed_file_promotion_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the count-only changed-file promotion fields of a session log.

    The fields say whether the working-tree bonus *changed* the context that was
    sent - the stage re-ranked the same request without the bonus and compared
    the two composed packages - so the verdicts are read off
    ``changed_context_differs`` and ``changed_baseline_status``, not off whether
    changed files happened to exist.  Since roadmap B4 that second build is
    opt-in, so an ordinary enabled request states ``not_sampled`` and belongs in
    neither verdict:

    - ``proved``: ``changed_files_signal`` is ``ok``, at least one file was
      modified, the comparison was ``built``, and the sent context differs;
    - ``inert``: the signal is ``ok``, at least one sent symbol carried the
      bonus, the comparison was made or was provably unnecessary, and nothing
      differs;
    - ``unmeasured``: the comparison ``failed``, was never sampled, or the record
      never stated the comparison fields.  It is reported on its own line and
      counted in neither verdict, because an unmeasurable request looks exactly
      like a zero only when nobody separates them.

    Args:
        records: Session log record dicts, as read from JSONL.

    Returns:
        Counts and rates keyed by signal and baseline state.  The two kinds of
        field get two denominators, because only one kind is a measurement on
        every record.  ``with_changed_files``, ``symbols_selected``,
        ``by_signal`` and ``by_baseline_status`` are directly observable and are
        read off every fielded record: a request states what the signal saw and
        what the ranking selected whether or not anyone asked for a comparison.
        ``primary_promoted``, ``symbols_promoted`` and ``rate_primary_promoted``
        need a counterfactual, so they are read off the ``"measured"`` records
        only - the ones whose comparison was ``built`` or was provably
        unnecessary (``skipped_no_bonus``) under an ``ok`` signal - and that
        count is the denominator the printed rate names.  Counting the
        placeholder ``False`` and ``0`` of a ``not_sampled`` or ``failed`` record
        alongside real measurements would report a request nobody compared as a
        measured no-change and pull the rate below what the run observed.
        Records written before the promotion fields existed are tallied in
        ``"before_fields"`` and excluded from every denominator, so old logs can
        neither inflate nor deflate a rate.
    """
    fielded: list[dict[str, Any]] = []
    before_fields = 0
    incomplete = 0
    by_signal = {"ok": 0, "off": 0, "unavailable": 0, "unknown": 0}
    by_status = {state: 0 for state in _BASELINE_STATES}
    by_status["unknown"] = 0

    for record in records:
        context = record.get("context") or {}
        if "changed_files_signal" not in context:
            before_fields += 1
            continue
        if any(key not in context for key in _PROMOTION_FIELDS):
            # A record that states the signal but not every field means a
            # partially deployed writer.  It still counts as a zero elsewhere,
            # so the tally says so rather than looking clean.
            incomplete += 1
        fielded.append(context)
        state = str(context.get("changed_files_signal", ""))
        by_signal[state if state in by_signal else "unknown"] += 1
        baseline = str(context.get("changed_baseline_status", "") or "")
        by_status[baseline if baseline in by_status else "unknown"] += 1

    def _count(context: dict[str, Any], key: str) -> int:
        try:
            return int(context.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _status(context: dict[str, Any]) -> str:
        return str(context.get("changed_baseline_status", "") or "")

    def _differs(context: dict[str, Any]) -> bool:
        return context.get("changed_context_differs") is True

    def _flag(context: dict[str, Any], key: str) -> bool:
        return context.get(key) is True

    # Directly observable: what the signal read and what the ranking selected.
    # Both are stated by every record that reached the stage, whichever way the
    # comparison setting went, so these read across all fielded records.
    dirty = [c for c in fielded if _count(c, "changed_files_count") > 0]
    unmeasured = [c for c in fielded if _status(c) not in _BASELINE_MEASURED + ("none",)]
    # Counterfactual: only a record whose comparison was made - or that proved it
    # unnecessary - can say what the bonus did to the context it sent.  A
    # `not_sampled` or `failed` record states `False` and `0` as placeholders, so
    # it enters neither of the promotion counts below nor their denominator.
    usable = [
        c
        for c in fielded
        if str(c.get("changed_files_signal")) == "ok" and _status(c) in _BASELINE_MEASURED
    ]
    primary_promoted = [c for c in usable if _flag(c, "changed_primary_promoted")]
    proved = [
        c
        for c in usable
        if _count(c, "changed_files_count") >= 1
        and _status(c) == "built"
        and _differs(c)
    ]
    proved_primary = [c for c in proved if _flag(c, "changed_primary_promoted")]
    proved_membership = [c for c in proved if _count(c, "changed_symbols_promoted") > 0]
    proved_reorder_only = [
        c
        for c in proved
        if not _flag(c, "changed_primary_promoted")
        and _count(c, "changed_symbols_promoted") == 0
    ]
    inert = [
        c
        for c in usable
        if _count(c, "changed_symbols_selected") > 0 and not _differs(c)
    ]

    return {
        "records": len(records),
        "with_fields": len(fielded),
        "before_fields": before_fields,
        "incomplete_fields": incomplete,
        "by_signal": by_signal,
        "by_baseline_status": by_status,
        "with_changed_files": len(dirty),
        "measured": len(usable),
        "primary_promoted": len(primary_promoted),
        "symbols_promoted": sum(_count(c, "changed_symbols_promoted") for c in usable),
        "symbols_selected": sum(_count(c, "changed_symbols_selected") for c in fielded),
        "proved": len(proved),
        "proved_primary": len(proved_primary),
        "proved_membership": len(proved_membership),
        "proved_reorder_only": len(proved_reorder_only),
        "present_but_inert": len(inert),
        "unmeasured": len(unmeasured),
        "rate_with_changed_files": (len(dirty) / len(fielded)) if fielded else 0.0,
        # "How often did the bonus move the primary, of the requests that were
        # compared" - never of every request, including the ones nobody compared.
        "rate_primary_promoted": (len(primary_promoted) / len(usable)) if usable else 0.0,
    }


def _print_changed_file_promotion(records: list[dict[str, Any]]) -> None:
    """Print the changed-file promotion section.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("CHANGED-FILE PROMOTION")
    print("-" * 40)

    summary = changed_file_promotion_summary(records)
    if summary["with_fields"] == 0:
        print(f"  records:                {summary['records']}")
        print(f"  predating the fields:   {summary['before_fields']}")
        print("  No record states the promotion fields.")
        print()
        return

    by_signal = summary["by_signal"]
    by_status = summary["by_baseline_status"]
    print(f"  records:                {summary['records']}")
    print(f"  stating the fields:     {summary['with_fields']}")
    print(f"  predating the fields:   {summary['before_fields']} (excluded below)")
    if summary["incomplete_fields"]:
        print(f"  missing a field:        {summary['incomplete_fields']} (read as zero)")
    print()
    print("  changed_files_signal:")
    for state in ("ok", "off", "unavailable", "unknown"):
        if by_signal[state]:
            print(f"    {state:<18}{by_signal[state]:>6}")
    print("  changed_baseline_status:")
    for state in ("built", "skipped_no_bonus", "not_sampled", "none", "failed", "unknown"):
        if by_status[state]:
            print(f"    {state:<18}{by_status[state]:>6}")
    print()
    print("  what the bonus did to the context that was sent:")
    print(
        f"    changed_files_count > 0:      {summary['with_changed_files']:>6} "
        f"({summary['rate_with_changed_files']:.1%} of fielded)"
    )
    print(
        f"    changed_primary_promoted:     {summary['primary_promoted']:>6} "
        f"({summary['rate_primary_promoted']:.1%} of {summary['measured']} measured)"
    )
    print(
        f"    sum changed_symbols_promoted: {summary['symbols_promoted']:>6} "
        f"(of {summary['measured']} measured)"
    )
    print(
        f"    sum changed_symbols_selected: {summary['symbols_selected']:>6} "
        f"(of {summary['with_fields']} fielded)"
    )
    print(
        "    measured = comparison built or provably unnecessary; fielded = every"
        " record stating the fields"
    )
    print()
    print(
        "    proves a change (signal=ok, count>=1, baseline built, context differs): "
        f"{summary['proved']}"
    )
    print(f"        primary changed:          {summary['proved_primary']:>6}")
    print(f"        membership changed:       {summary['proved_membership']:>6}")
    print(f"        reorder only:             {summary['proved_reorder_only']:>6}")
    print(
        "    present but inert (bonus selected, context identical): "
        f"{summary['present_but_inert']}"
    )
    print(
        "    unmeasured (comparison failed, not sampled, or fields absent): "
        f"{summary['unmeasured']}"
    )
    print()


#: The activity section exactly as ``packages.pipeline.file_activity`` defines it
#: and ``apps/gateway/session_log.py`` writes it under ``context.file_activity``:
#: two state tokens and fifteen counters, in schema order.  This tuple is the
#: whole allowlist - a key outside it is never read, never typed and never
#: printed, which is what keeps this section count-only.
_FILE_ACTIVITY_FIELDS = (
    "state",
    "correlation",
    "files_read",
    "files_modified",
    "files_touched",
    "read_attempts",
    "reads_failed",
    "reads_unknown",
    "modification_attempts",
    "modifications_not_modified",
    "modifications_unknown",
    "context_files_touched",
    "touched_without_context",
    "changed_files_touched",
    "paths_rejected",
    "other_events",
    "events_beyond_bound",
)

#: The fifteen counters, which are the only numbers the section reports.
_FILE_ACTIVITY_COUNTERS = _FILE_ACTIVITY_FIELDS[2:]

#: Every state token :class:`~packages.pipeline.file_activity.FileActivityCounts`
#: can carry, in the order the distributions print.  An unrecognized string is
#: tallied as ``unknown`` rather than dropped, because a record that states a
#: token this script has never seen is a fact about the writer, not noise.
_FILE_ACTIVITY_STATE_VALUES = ("measured", "none", "partial", "unavailable", "unknown")
_FILE_ACTIVITY_CORRELATION_VALUES = (
    "measured",
    "no_prior_context",
    "tracker_miss",
    "unavailable",
    "unknown",
)

#: The states whose counters are a reading of what the transcript showed.
#: ``none`` belongs here on purpose: a transcript that held nothing recognizable
#: is a *measured zero*, the answer a client that sends no envelopes produces.
#: ``unavailable`` is excluded because there the measurement never ran, and
#: ``partial`` is included but reported as a floor, because a bound kept events
#: out of it.  None of the three is the changed-file signal's own ``none``,
#: which means the ranking feature was switched off.
_ACTIVITY_STATES = ("measured", "partial", "none")

#: The correlation states that make ``context_files_touched`` and
#: ``touched_without_context`` readings rather than placeholders.
#: ``no_prior_context`` is a real zero - the conversation was remembered and had
#: never been supplied a file - while ``tracker_miss`` means supplied-context
#: lineage has a gap in it, so its zeros are not measurements.
_CORRELATION_STATES = ("measured", "no_prior_context")

#: The pair that partitions ``files_touched`` and therefore needs a usable
#: lineage, as opposed to the other thirteen counters, which the transcript
#: alone decides.
_CORRELATION_COUNTERS = ("context_files_touched", "touched_without_context")


def _classify_file_activity(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Sort one record's activity section into a coverage case.

    Four cases, kept apart because they mean different things to a reader:
    ``before`` - the record states no ``file_activity`` at all and so predates
    roadmap C1; ``incomplete`` - an object is there but a required key is not,
    which is what a partially deployed writer produces; ``malformed`` - the
    object, or a value inside it, has a type this analysis cannot read; and
    ``valid`` - a complete section whose every value is usable.

    A token outside the documented sets is *not* malformed: it is a string of a
    readable type, and it lands in the ``unknown`` bucket of its distribution.
    Malformed means an unreadable type - a section that is not a mapping, a state
    token that is not a string, or a counter that is a bool, a float or negative.

    Args:
        record: One session log record dict.

    Returns:
        The case name, and the section itself when it is complete.
    """
    context = record.get("context")
    if not isinstance(context, dict) or "file_activity" not in context:
        return "before", {}
    section = context["file_activity"]
    if not isinstance(section, dict):
        return "malformed", {}
    if any(key not in section for key in _FILE_ACTIVITY_FIELDS):
        return "incomplete", {}
    for key in ("state", "correlation"):
        if not isinstance(section[key], str):
            return "malformed", {}
    for key in _FILE_ACTIVITY_COUNTERS:
        value = section[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return "malformed", {}
    return "valid", section


def file_activity_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the count-only file-activity sections of a session log.

    Every number describing what a client's transcript showed is a *snapshot*:
    ``packages.pipeline.file_activity`` recomputes all fifteen counters from the
    complete transcript the request carried, and a Cline client re-sends its whole
    conversation on every turn.  A file read once and then carried by fourteen
    later requests therefore states ``files_read=1`` fourteen times over, so this
    function reports per-record snapshot statistics - how many records can answer,
    how many answered above zero, and the median and maximum a single record
    reached - and deliberately reports **no cross-record sum**.  Adding the column
    would count early activity once per later turn, which is the bug the snapshot
    model replaced.

    Records are separated, never merged: one that states no ``file_activity``
    predates roadmap C1 and cannot enter any statistic; one whose object or values
    are unreadable is reported as incomplete or malformed rather than read as a
    zero; a ``state=unavailable`` record is excluded from the activity statistics
    because it measured nothing; and ``tracker_miss`` and ``unavailable``
    correlation states are excluded from the two correlation counters, whose zeros
    there describe a lineage gap.  ``state=none`` is kept and is a measured zero,
    and ``state=partial`` is kept with its values labelled floors.

    Only :data:`_FILE_ACTIVITY_FIELDS` is ever read from a section.  Unknown nested
    keys are ignored rather than enumerated, so a writer that started storing a
    path or a result body could not make this report leak it.

    Args:
        records: Session log record dicts, as read from JSONL.

    Returns:
        A deterministic, JSON-compatible summary: coverage counts, the two state
        distributions, and one per-record snapshot block per counter.  ``median``
        and ``max`` are ``None`` when no record is eligible, so "nothing could
        answer" never prints as a measured zero.
    """
    by_state = {value: 0 for value in _FILE_ACTIVITY_STATE_VALUES}
    by_correlation = {value: 0 for value in _FILE_ACTIVITY_CORRELATION_VALUES}
    seen: dict[str, list[int]] = {field: [] for field in _FILE_ACTIVITY_COUNTERS}
    before_fields = 0
    incomplete_fields = 0
    malformed_fields = 0
    valid_records = 0

    for record in records:
        kind, section = _classify_file_activity(record)
        if kind == "before":
            before_fields += 1
            continue
        if kind == "incomplete":
            incomplete_fields += 1
            continue
        if kind == "malformed":
            malformed_fields += 1
            continue
        valid_records += 1

        state = str(section["state"])
        correlation = str(section["correlation"])
        by_state[state if state in by_state else "unknown"] += 1
        by_correlation[correlation if correlation in by_correlation else "unknown"] += 1

        # A transcript that was never read cannot say what it contained, so the
        # correlation pair needs both readings usable, not only its own.
        activity_usable = state in _ACTIVITY_STATES
        correlation_usable = activity_usable and correlation in _CORRELATION_STATES
        for field in _FILE_ACTIVITY_COUNTERS:
            usable = correlation_usable if field in _CORRELATION_COUNTERS else activity_usable
            if usable:
                seen[field].append(int(section[field]))

    snapshots: dict[str, Any] = {}
    for field in _FILE_ACTIVITY_COUNTERS:
        values = seen[field]
        snapshots[field] = {
            "kind": "correlation" if field in _CORRELATION_COUNTERS else "activity",
            "eligible_records": len(values),
            "nonzero_records": sum(1 for value in values if value > 0),
            "median": float(statistics.median(values)) if values else None,
            "max": max(values) if values else None,
        }

    return {
        "records": len(records),
        "with_fields": incomplete_fields + malformed_fields + valid_records,
        "before_fields": before_fields,
        "incomplete_fields": incomplete_fields,
        "malformed_fields": malformed_fields,
        "valid_fields": valid_records,
        "by_state": by_state,
        "by_correlation": by_correlation,
        "snapshots": snapshots,
    }


def _print_file_activity(records: list[dict[str, Any]]) -> None:
    """Print the conversation file-activity section.

    Args:
        records: A list of session log record dicts.
    """
    print("-" * 40)
    print("FILE ACTIVITY")
    print("-" * 40)

    summary = file_activity_summary(records)
    print(f"  records:                {summary['records']}")
    print(f"  stating file_activity:  {summary['with_fields']}")
    if summary["with_fields"] == 0:
        print(f"  predating C1:           {summary['before_fields']}")
        print("  No record states the file-activity fields.")
        print()
        return

    print(f"  predating C1:           {summary['before_fields']} (excluded below)")
    if summary["incomplete_fields"]:
        print(f"  missing a field:        {summary['incomplete_fields']} (excluded below)")
    if summary["malformed_fields"]:
        print(f"  unusable field types:   {summary['malformed_fields']} (excluded below)")
    print(f"  read as snapshots:      {summary['valid_fields']}")
    print()
    print("  These counters are transcript snapshots, recomputed from each")
    print("  request's complete transcript.  A Cline client re-sends its whole")
    print("  conversation every turn, so they are NOT per-turn deltas and are")
    print("  never summed across records: every statistic below is per-record.")
    print()

    print("  state - was the transcript read?")
    for value in _FILE_ACTIVITY_STATE_VALUES:
        if summary["by_state"][value]:
            print(f"    {value:<20}{summary['by_state'][value]:>6}")
    print("  correlation - is the pair a measurement?")
    for value in _FILE_ACTIVITY_CORRELATION_VALUES:
        if summary["by_correlation"][value]:
            print(f"    {value:<20}{summary['by_correlation'][value]:>6}")
    print()

    print("  per-record snapshot statistics (eligible = records that can answer):")
    for field in _FILE_ACTIVITY_COUNTERS:
        stats = summary["snapshots"][field]
        kind = "corr" if stats["kind"] == "correlation" else "act "
        median = stats["median"]
        high = stats["max"]
        median_text = "-" if median is None else f"{median:.1f}"
        max_text = "-" if high is None else str(high)
        print(
            f"    {kind} {field:<27}"
            f"eligible={stats['eligible_records']:>5}  "
            f"nonzero={stats['nonzero_records']:>5}  "
            f"median={median_text:>6}  "
            f"max={max_text:>5}"
        )
    print()
    print("  notes:")
    print("    state=none is a measured zero - the transcript held nothing")
    print("    recognizable - and is not state=unavailable, where the measurement")
    print("    never ran; neither is the changed-file ranking feature's own")
    print("    changed_files_signal=off, which only says that feature was off.")
    print("    state=partial values are floors: a bound kept events unread.")
    print("    correlation=tracker_miss and correlation=unavailable zeros are")
    print("    excluded from the two corr counters, which report a lineage gap.")
    print("    No path, module, symbol, result body, envelope text or unknown")
    print("    nested key is read from a record or printed here.")
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


