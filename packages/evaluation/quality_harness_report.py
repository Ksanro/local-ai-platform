"""Deterministic evaluation of `scripts/quality_harness.py --json` output.

Consumes the plain JSON shapes emitted by the quality harness script — a
`list[dict]` for a single run, or `{"context": [...], "no_context": [...]}`
for `--compare-context` — and turns them into structured, immutable reports.

This module has no import dependency on `scripts/quality_harness.py`. It
duck-types the harness's JSON output instead, matching the package's
"consumes only existing public APIs" constraint.

`--json` output from the harness serializes `QualityResult.__dict__`, which
excludes the `score`/`maximum` properties (they are not dataclass fields).
This module recomputes them from `hits`/`misses`.

Public API
----------

.. code-block:: python

    from packages.evaluation.quality_harness_report import (
        evaluate_results,
        evaluate_comparison,
    )

    report = evaluate_results(json.loads(raw_json))
    comparison = evaluate_comparison(json.loads(raw_compare_json))

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ComparisonReport",
    "ContextDelta",
    "ProbeEvaluation",
    "QualityHarnessReport",
    "evaluate_comparison",
    "evaluate_results",
]


# ---------------------------------------------------------------------------
# ProbeEvaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeEvaluation:
    """Evaluation of a single quality-harness probe result.

    Attributes:
        id: Probe identifier.
        intent: Probe intent (e.g. "SEARCH", "DEBUG").
        score: Number of expected facts found (`len(hits)`).
        maximum: Total number of expected facts (`len(hits) + len(misses)`).
        missing_facts: Expected fact labels not found in the answer.
        prompt_tokens: Prompt token cost reported by the gateway.
        seconds: Wall-clock latency of the probe request.
        error: Non-empty if the probe request failed.
    """

    id: str
    intent: str
    score: int
    maximum: int
    missing_facts: tuple[str, ...]
    prompt_tokens: int
    seconds: float
    error: str


# ---------------------------------------------------------------------------
# QualityHarnessReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QualityHarnessReport:
    """Evaluation of a single quality-harness run (one `--json` array).

    Attributes:
        probes: Per-probe evaluations, in input order.
        total_score: Sum of `ProbeEvaluation.score` across all probes.
        total_maximum: Sum of `ProbeEvaluation.maximum` across all probes.
        total_prompt_tokens: Sum of `ProbeEvaluation.prompt_tokens`.
        total_seconds: Sum of `ProbeEvaluation.seconds`.
    """

    probes: tuple[ProbeEvaluation, ...]
    total_score: int
    total_maximum: int
    total_prompt_tokens: int
    total_seconds: float


# ---------------------------------------------------------------------------
# ContextDelta / ComparisonReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContextDelta:
    """Difference between a probe's context-on and context-off results.

    Attributes:
        id: Probe identifier.
        score_delta: `with_context.score - without_context.score`.
        prompt_token_delta: `with_context.prompt_tokens - without_context.prompt_tokens`.
    """

    id: str
    score_delta: int
    prompt_token_delta: int


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Evaluation of a `--compare-context --json` run.

    Attributes:
        with_context: Report for the context-enabled run.
        without_context: Report for the context-disabled run.
        deltas: Per-probe context deltas, matched by id, in `with_context` order.
        total_score_delta: `with_context.total_score - without_context.total_score`.
        total_prompt_token_delta: total prompt token delta, context minus no-context.
    """

    with_context: QualityHarnessReport
    without_context: QualityHarnessReport
    deltas: tuple[ContextDelta, ...]
    total_score_delta: int
    total_prompt_token_delta: int


def _evaluate_probe(result: dict[str, Any]) -> ProbeEvaluation:
    """Evaluate one quality-harness result dict."""
    hits = result.get("hits") or ()
    misses = result.get("misses") or ()
    return ProbeEvaluation(
        id=result["id"],
        intent=result.get("intent", ""),
        score=len(hits),
        maximum=len(hits) + len(misses),
        missing_facts=tuple(misses),
        prompt_tokens=int(result.get("prompt_tokens", 0) or 0),
        seconds=float(result.get("seconds", 0.0) or 0.0),
        error=result.get("error", ""),
    )


def evaluate_results(results: list[dict[str, Any]]) -> QualityHarnessReport:
    """Evaluate a single quality-harness `--json` run.

    Args:
        results: Parsed JSON array from `quality_harness.py --json`
            (a list of `QualityResult.__dict__`-shaped dicts).

    Returns:
        A `QualityHarnessReport` with per-probe evaluations and totals.
    """
    probes = tuple(_evaluate_probe(result) for result in results)
    return QualityHarnessReport(
        probes=probes,
        total_score=sum(probe.score for probe in probes),
        total_maximum=sum(probe.maximum for probe in probes),
        total_prompt_tokens=sum(probe.prompt_tokens for probe in probes),
        total_seconds=sum(probe.seconds for probe in probes),
    )


def evaluate_comparison(payload: dict[str, Any]) -> ComparisonReport:
    """Evaluate a `--compare-context --json` run.

    Args:
        payload: Parsed JSON object with `"context"` and `"no_context"` keys,
            each a list of `QualityResult.__dict__`-shaped dicts, as emitted by
            `quality_harness.py --compare-context --json`.

    Returns:
        A `ComparisonReport` with both sides' reports and per-probe context deltas.
    """
    with_context = evaluate_results(payload["context"])
    without_context = evaluate_results(payload["no_context"])

    without_context_by_id = {probe.id: probe for probe in without_context.probes}
    deltas = tuple(
        ContextDelta(
            id=ctx_probe.id,
            score_delta=ctx_probe.score - without_context_by_id[ctx_probe.id].score,
            prompt_token_delta=(
                ctx_probe.prompt_tokens
                - without_context_by_id[ctx_probe.id].prompt_tokens
            ),
        )
        for ctx_probe in with_context.probes
        if ctx_probe.id in without_context_by_id
    )

    return ComparisonReport(
        with_context=with_context,
        without_context=without_context,
        deltas=deltas,
        total_score_delta=with_context.total_score - without_context.total_score,
        total_prompt_token_delta=(
            with_context.total_prompt_tokens - without_context.total_prompt_tokens
        ),
    )
