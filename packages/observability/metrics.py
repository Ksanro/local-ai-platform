"""Metric collection and aggregation for the observability framework.

Provides deterministic metric aggregation without sampling or randomness.
All platform metrics are collected in full.

Architecture
------------

MetricRecord --> MetricAggregator --> EngineeringTelemetry

Constraints
-----------

- No sampling.
- No randomness.
- No file system operations.
- Deterministic ordering.

Public API
----------

.. code-block:: python

    from packages.observability.metrics import (
        MetricAggregator,
        MetricRecord,
        collect_workflow_duration,
        collect_execution_duration,
        collect_provider_latency,
    )

    aggregator = MetricAggregator()
    aggregator.record("workflow_duration_ms", 1234.5)
    stats = aggregator.get_statistics()

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "MetricAggregator",
    "MetricRecord",
    "collect_workflow_duration",
    "collect_execution_duration",
    "collect_provider_latency",
]


# ---------------------------------------------------------------------------
# MetricRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetricRecord:
    """A single metric record with metadata.

    Attributes:
        name: Metric name.
        value: Metric value.
        labels: Key-value labels.
        timestamp: ISO format timestamp.
        source: Source component name.
    """

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""


# ---------------------------------------------------------------------------
# MetricAggregator
# ---------------------------------------------------------------------------


class MetricAggregator:
    """Deterministic metric aggregator.

    Collects metrics without sampling or randomness. All metrics are
    stored and can be queried by name or labels.

    Attributes:
        _records: List of metric records.
    """

    def __init__(self) -> None:
        """Initialize the metric aggregator."""
        self._records: list[MetricRecord] = []

    def record(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        source: str = "",
    ) -> None:
        """Record a metric.

        Args:
            name: Metric name (e.g. "workflow_duration_ms").
            value: Metric value.
            labels: Key-value labels for the metric.
            source: Source component name.
        """
        record = MetricRecord(
            name=name,
            value=value,
            labels=labels or {},
            source=source,
        )
        self._records.append(record)

    def get_records(self, name: str | None = None) -> tuple[MetricRecord, ...]:
        """Get all metric records, optionally filtered by name.

        Args:
            name: Optional metric name to filter by.

        Returns:
            Tuple of metric records in deterministic order.
        """
        if name is None:
            return tuple(self._records)

        return tuple(r for r in self._records if r.name == name)

    def get_latest(self, name: str) -> MetricRecord | None:
        """Get the latest metric record for a given name.

        Args:
            name: Metric name to get the latest record for.

        Returns:
            The latest MetricRecord or None if not found.
        """
        records = self.get_records(name)
        if not records:
            return None
        return records[-1]

    def get_statistics(self, name: str) -> dict[str, Any]:
        """Get aggregate statistics for a metric.

        Args:
            name: Metric name to get statistics for.

        Returns:
            Dictionary with count, sum, min, max, avg values.
        """
        records = self.get_records(name)
        if not records:
            return {
                "count": 0,
                "sum": 0.0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
            }

        values = [r.value for r in records]
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    def clear(self) -> None:
        """Clear all recorded metrics."""
        self._records.clear()

    @property
    def count(self) -> int:
        """Get the total number of recorded metrics."""
        return len(self._records)


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def collect_workflow_duration(
    duration_ms: float,
    workflow_name: str = "",
    workflow_id: str = "",
) -> MetricRecord:
    """Create a workflow duration metric record.

    Args:
        duration_ms: Duration in milliseconds.
        workflow_name: Workflow name.
        workflow_id: Workflow ID.

    Returns:
        A MetricRecord for workflow duration.
    """
    return MetricRecord(
        name="workflow_duration_ms",
        value=duration_ms,
        labels={
            "workflow_name": workflow_name,
            "workflow_id": workflow_id,
        },
        source="workflow_engine",
    )


def collect_execution_duration(
    duration_ms: float,
    workflow_name: str = "",
    execution_id: str = "",
) -> MetricRecord:
    """Create an execution duration metric record.

    Args:
        duration_ms: Duration in milliseconds.
        workflow_name: Workflow name.
        execution_id: Execution ID.

    Returns:
        A MetricRecord for execution duration.
    """
    return MetricRecord(
        name="execution_duration_ms",
        value=duration_ms,
        labels={
            "workflow_name": workflow_name,
            "execution_id": execution_id,
        },
        source="execution_engine",
    )


def collect_provider_latency(
    latency_ms: float,
    provider_name: str = "",
    model: str = "",
) -> MetricRecord:
    """Create a provider latency metric record.

    Args:
        latency_ms: Latency in milliseconds.
        provider_name: Provider name.
        model: Model name.

    Returns:
        A MetricRecord for provider latency.
    """
    return MetricRecord(
        name="provider_latency_ms",
        value=latency_ms,
        labels={
            "provider_name": provider_name,
            "model": model,
        },
        source="provider",
    )


# ---------------------------------------------------------------------------
# Standard Metric Names
# ---------------------------------------------------------------------------

# All standard metric names used by the platform.

METRIC_WORKFLOW_DURATION_MS = "workflow_duration_ms"
METRIC_EXECUTION_DURATION_MS = "execution_duration_ms"
METRIC_PLANNING_DURATION_MS = "planning_duration_ms"
METRIC_REPOSITORY_RETRIEVAL_DURATION_MS = "repository_retrieval_duration_ms"
METRIC_CONTEXT_ASSEMBLY_DURATION_MS = "context_assembly_duration_ms"
METRIC_PROVIDER_LATENCY_MS = "provider_latency_ms"
METRIC_EVALUATION_SCORE = "evaluation_score"
METRIC_VERIFICATION_SCORE = "verification_score"
METRIC_PATCH_COUNT = "patch_count"
METRIC_MODIFICATION_COUNT = "modification_count"
METRIC_SUCCESS_RATE = "success_rate"
METRIC_FAILURE_RATE = "failure_rate"
METRIC_ROLLBACK_COUNT = "rollback_count"
METRIC_ITERATION_COUNT = "iteration_count"
METRIC_THROUGHPUT = "engineering_throughput"