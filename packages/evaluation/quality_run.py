"""QualityRun — a flat, storage-agnostic summary of one quality-harness run.

Wraps `QualityHarnessReport`/`ComparisonReport` (from
`packages.evaluation.quality_harness_report`) into a single, self-describing
record suitable for printing, diffing, or handing to an arbitrary sink — a
file, a chat message, a future storage layer.

This is deliberately **not** a replacement for
`packages.engineering_memory.EngineeringMemory`: it has no persistence layer,
no query API, and no storage format versioning. It is just a plain model plus
two builder functions.

Public API
----------

.. code-block:: python

    from packages.evaluation.quality_run import build_quality_run

    run = build_quality_run(report, model="qwen36")

"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from packages.evaluation.quality_harness_report import (
    ComparisonReport,
    ProbeEvaluation,
    QualityHarnessReport,
)

__all__ = [
    "Mode",
    "ProbeRun",
    "QualityRun",
    "build_quality_run",
    "build_quality_run_from_comparison",
]

Mode = Literal["single", "compare_context"]


# ---------------------------------------------------------------------------
# ProbeRun
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeRun:
    """One probe's result within a QualityRun.

    Attributes:
        id: Probe identifier.
        intent: Probe intent (e.g. "SEARCH", "DEBUG").
        score: Number of expected facts found.
        maximum: Total number of expected facts.
        missing_facts: Expected fact labels not found in the answer.
        prompt_tokens: Prompt token cost reported by the gateway.
        seconds: Wall-clock latency of the probe request.
        error: Non-empty if the probe request failed.
        context_score_delta: `with_context.score - without_context.score`,
            only set in "compare_context" mode.
        context_prompt_token_delta: prompt-token delta, context minus
            no-context, only set in "compare_context" mode.
    """

    id: str
    intent: str
    score: int
    maximum: int
    missing_facts: tuple[str, ...]
    prompt_tokens: int
    seconds: float
    error: str
    context_score_delta: int | None = None
    context_prompt_token_delta: int | None = None


# ---------------------------------------------------------------------------
# QualityRun
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QualityRun:
    """A single, self-describing summary of one quality-harness run.

    Attributes:
        run_id: Unique identifier for this run.
        created_at: ISO format timestamp when this summary was built.
        model: Model name the run was executed against.
        gateway_commit: Gateway git commit/version tag, if known.
        mode: "single" for a plain run, "compare_context" for `--compare-context`.
        total_score: Sum of per-probe scores.
        total_maximum: Sum of per-probe maximums.
        total_prompt_tokens: Sum of per-probe prompt tokens.
        total_seconds: Sum of per-probe latencies.
        probes: Per-probe rows, in input order.
    """

    run_id: str
    created_at: str
    model: str
    gateway_commit: str
    mode: Mode
    total_score: int
    total_maximum: int
    total_prompt_tokens: int
    total_seconds: float
    probes: tuple[ProbeRun, ...] = field(default_factory=tuple)


def _generate_run_id() -> str:
    """Generate a unique, sortable run id."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"qr-{stamp}-{uuid.uuid4().hex[:8]}"


def _probe_run(
    probe: ProbeEvaluation,
    *,
    context_score_delta: int | None = None,
    context_prompt_token_delta: int | None = None,
) -> ProbeRun:
    return ProbeRun(
        id=probe.id,
        intent=probe.intent,
        score=probe.score,
        maximum=probe.maximum,
        missing_facts=probe.missing_facts,
        prompt_tokens=probe.prompt_tokens,
        seconds=probe.seconds,
        error=probe.error,
        context_score_delta=context_score_delta,
        context_prompt_token_delta=context_prompt_token_delta,
    )


def build_quality_run(
    report: QualityHarnessReport,
    *,
    model: str,
    gateway_commit: str = "",
    run_id: str | None = None,
) -> QualityRun:
    """Build a QualityRun summary from a single quality-harness evaluation.

    Args:
        report: The evaluated quality-harness run.
        model: The model name the run was executed against.
        gateway_commit: Gateway git commit/version tag, if known.
        run_id: Explicit run id; auto-generated when omitted.

    Returns:
        A "single"-mode QualityRun. Per-probe context delta fields are None.
    """
    return QualityRun(
        run_id=run_id or _generate_run_id(),
        created_at=datetime.now(timezone.utc).isoformat(),
        model=model,
        gateway_commit=gateway_commit,
        mode="single",
        total_score=report.total_score,
        total_maximum=report.total_maximum,
        total_prompt_tokens=report.total_prompt_tokens,
        total_seconds=report.total_seconds,
        probes=tuple(_probe_run(probe) for probe in report.probes),
    )


def build_quality_run_from_comparison(
    comparison: ComparisonReport,
    *,
    model: str,
    gateway_commit: str = "",
    run_id: str | None = None,
) -> QualityRun:
    """Build a QualityRun summary from a `--compare-context` evaluation.

    Totals and per-probe base fields come from the context-enabled side;
    each probe additionally carries its context_score_delta and
    context_prompt_token_delta, matched by probe id.

    Args:
        comparison: The evaluated context-on/context-off comparison run.
        model: The model name the run was executed against.
        gateway_commit: Gateway git commit/version tag, if known.
        run_id: Explicit run id; auto-generated when omitted.

    Returns:
        A "compare_context"-mode QualityRun.
    """
    deltas_by_id = {delta.id: delta for delta in comparison.deltas}
    probes = tuple(
        _probe_run(
            probe,
            context_score_delta=(
                deltas_by_id[probe.id].score_delta
                if probe.id in deltas_by_id
                else None
            ),
            context_prompt_token_delta=(
                deltas_by_id[probe.id].prompt_token_delta
                if probe.id in deltas_by_id
                else None
            ),
        )
        for probe in comparison.with_context.probes
    )
    return QualityRun(
        run_id=run_id or _generate_run_id(),
        created_at=datetime.now(timezone.utc).isoformat(),
        model=model,
        gateway_commit=gateway_commit,
        mode="compare_context",
        total_score=comparison.with_context.total_score,
        total_maximum=comparison.with_context.total_maximum,
        total_prompt_tokens=comparison.with_context.total_prompt_tokens,
        total_seconds=comparison.with_context.total_seconds,
        probes=probes,
    )
