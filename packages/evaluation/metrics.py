"""Deterministic metric computation functions.

Metrics are computed exclusively from structured platform outputs.
No AI scoring. No LLM judging. No semantic evaluation.

Architecture
------------

Platform Output  -->  Metric Computation  -->  EvaluationMetric

All functions are pure, deterministic, and side-effect free.

Public API
----------

.. code-block:: python

    from packages.evaluation.metrics import (
        compute_context_compression_ratio,
        compute_context_utilization,
        compute_execution_duration_ms,
        compute_total_tokens,
        compute_workflow_completeness,
        compute_diagnostics_collected,
        compute_architecture_findings_count,
        compute_execution_consistency,
        compute_identifier_stability,
    )

"""

from __future__ import annotations

from typing import Any

__all__ = [
    # Context Quality
    "compute_context_compression_ratio",
    "compute_context_utilization",
    "compute_selected_symbols_count",
    "compute_selected_modules_count",
    "compute_selected_relationships_count",
    # Execution Quality
    "compute_execution_duration_ms",
    "compute_total_tokens",
    "compute_throughput",
    # Engineering Quality
    "compute_diagnostics_collected",
    "compute_architecture_findings_count",
    "compute_workflow_completeness",
    # Determinism
    "compute_execution_consistency",
    "compute_identifier_stability",
]


# ---------------------------------------------------------------------------
# Context Quality Metrics
# ---------------------------------------------------------------------------


def compute_selected_symbols_count(symbols: tuple[str, ...]) -> float:
    """Compute the count of selected symbols.

    Args:
        symbols: Tuple of selected symbol qualified names.

    Returns:
        Count as a float value.
    """
    return float(len(symbols))


def compute_selected_modules_count(modules: tuple[str, ...]) -> float:
    """Compute the count of selected modules.

    Args:
        modules: Tuple of selected module file paths.

    Returns:
        Count as a float value.
    """
    return float(len(modules))


def compute_selected_relationships_count(
    relationships: tuple[tuple[str, str, str], ...],
) -> float:
    """Compute the count of selected relationships.

    Each relationship is a tuple of (source, target, relationship_type).

    Args:
        relationships: Tuple of relationship tuples.

    Returns:
        Count as a float value.
    """
    return float(len(relationships))


def compute_context_compression_ratio(
    estimated_tokens: int,
    actual_prompt_tokens: int,
) -> float:
    """Compute the context compression ratio.

    Compression ratio = actual_prompt_tokens / estimated_tokens.
    A ratio close to 1.0 means the estimation was accurate.
    A ratio much lower means we overestimated.

    Args:
        estimated_tokens: Estimated token count from the context plan.
        actual_prompt_tokens: Actual prompt token count from provider response.

    Returns:
        Compression ratio in range [0.0, 1.0] or 1.0 if estimated is 0.
    """
    if estimated_tokens <= 0:
        return 1.0
    ratio = actual_prompt_tokens / estimated_tokens
    # Clamp to [0.0, 1.0] — ratios above 1.0 indicate overestimation
    return min(max(ratio, 0.0), 1.0)


def compute_context_utilization(
    estimated_tokens: int,
    actual_prompt_tokens: int,
) -> float:
    """Compute context utilization.

    Utilization = actual_prompt_tokens / estimated_tokens.
    A value close to 1.0 means context was well-sized.
    Values below 0.5 suggest over-estimation.
    Values above 1.0 suggest under-estimation.

    Args:
        estimated_tokens: Estimated token count from the context plan.
        actual_prompt_tokens: Actual prompt token count from provider response.

    Returns:
        Utilization ratio. Values > 1.0 indicate under-estimation.
    """
    if estimated_tokens <= 0:
        return 0.0
    return actual_prompt_tokens / estimated_tokens


# ---------------------------------------------------------------------------
# Execution Quality Metrics
# ---------------------------------------------------------------------------


def compute_execution_duration_ms(
    step_results: tuple[dict[str, Any], ...],
) -> float:
    """Compute total execution duration from step results.

    Each step result dict must have a 'duration_ms' key.

    Args:
        step_results: Tuple of step result dicts with 'duration_ms' key.

    Returns:
        Total duration in milliseconds.
    """
    total = 0.0
    for result in step_results:
        duration = result.get("duration_ms", 0)
        total += float(duration)
    return total


def compute_total_tokens(
    completion_tokens: int,
    prompt_tokens: int,
) -> float:
    """Compute total token count.

    Args:
        completion_tokens: Number of completion tokens.
        prompt_tokens: Number of prompt tokens.

    Returns:
        Total token count.
    """
    return float(completion_tokens + prompt_tokens)


def compute_throughput(
    total_tokens: int,
    total_duration_ms: int,
) -> float:
    """Compute token throughput (tokens per second).

    Args:
        total_tokens: Total number of tokens processed.
        total_duration_ms: Total execution duration in milliseconds.

    Returns:
        Tokens per second. Returns 0.0 if duration is 0.
    """
    if total_duration_ms <= 0:
        return 0.0
    seconds = total_duration_ms / 1000.0
    return float(total_tokens) / seconds


# ---------------------------------------------------------------------------
# Engineering Quality Metrics
# ---------------------------------------------------------------------------


def compute_diagnostics_collected(
    diagnostic_data: dict[str, Any] | None,
) -> float:
    """Compute the count of diagnostics collected.

    Args:
        diagnostic_data: Dictionary containing diagnostic information.
            If None or empty, returns 0.0.

    Returns:
        Count of diagnostics as a float value.
    """
    if not diagnostic_data:
        return 0.0
    # Count top-level diagnostic categories
    return float(len(diagnostic_data))


def compute_architecture_findings_count(
    architecture_data: dict[str, Any] | None,
) -> float:
    """Compute the count of architecture findings.

    Args:
        architecture_data: Dictionary containing architecture findings.
            If None or empty, returns 0.0.

    Returns:
        Count of findings as a float value.
    """
    if not architecture_data:
        return 0.0
    # Count top-level architecture finding categories
    return float(len(architecture_data))


def compute_workflow_completeness(
    executed_steps: int,
    expected_steps: int,
) -> float:
    """Compute workflow completeness ratio.

    Returns a value between 0.0 and 1.0 representing
    what fraction of expected steps were executed.

    Args:
        executed_steps: Number of steps actually executed.
        expected_steps: Number of expected steps.

    Returns:
        Completeness ratio in [0.0, 1.0]. Returns 1.0 if expected is 0.
    """
    if expected_steps <= 0:
        return 1.0
    ratio = executed_steps / expected_steps
    return min(max(ratio, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Determinism Metrics
# ---------------------------------------------------------------------------


def compute_execution_consistency(
    repeated_outputs: tuple[tuple[str, ...], ...],
) -> float:
    """Compute execution consistency across repeated runs.

    Compares tuples of outputs from multiple executions.
    A score of 1.0 means all outputs are identical.
    A score of 0.0 means no outputs match.

    Args:
        repeated_outputs: Tuple of output tuples from repeated executions.
            Each inner tuple represents one execution's outputs.

    Returns:
        Consistency score in [0.0, 1.0].
        Returns 1.0 if fewer than 2 executions provided.
    """
    if len(repeated_outputs) < 2:
        return 1.0

    # Compare all pairs against the first execution
    reference = repeated_outputs[0]
    matches = 0
    total = len(repeated_outputs) - 1

    for output in repeated_outputs[1:]:
        if output == reference:
            matches += 1

    if total == 0:
        return 1.0
    return float(matches) / float(total)


def compute_identifier_stability(
    identifiers: tuple[tuple[str, ...], ...],
) -> float:
    """Compute identifier stability across repeated runs.

    Compares tuples of identifier tuples from multiple executions.
    A score of 1.0 means all identifiers are stable.
    A score of 0.0 means no identifiers match.

    Args:
        identifiers: Tuple of identifier tuples from repeated executions.
            Each inner tuple represents one execution's identifiers.

    Returns:
        Stability score in [0.0, 1.0].
        Returns 1.0 if fewer than 2 executions provided.
    """
    if len(identifiers) < 2:
        return 1.0

    # Compare all pairs against the first execution
    reference = identifiers[0]
    matches = 0
    total = len(identifiers) - 1

    for ids in identifiers[1:]:
        if ids == reference:
            matches += 1

    if total == 0:
        return 1.0
    return float(matches) / float(total)