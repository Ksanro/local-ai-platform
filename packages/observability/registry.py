"""Deterministic registries for the observability framework.

Provides registries for events, metrics, and traces with deterministic
ordering. All registries maintain insertion order and support
deterministic iteration.

Architecture
------------

EventRegistry --> Sorted event storage
MetricRegistry --> Sorted metric storage
TraceRegistry --> Sorted trace storage

Constraints
-----------

- Deterministic ordering.
- No sampling.
- No randomness.
- No file system operations.

Public API
----------

.. code-block:: python

    from packages.observability.registry import (
        EventRegistry,
        MetricRegistry,
        TraceRegistry,
    )

    registry = EventRegistry()
    registry.add(event)
    events = registry.all()

"""

from __future__ import annotations

from typing import Any

from packages.observability.models import (
    Metric,
    TelemetryEvent,
    Trace,
)

__all__ = [
    "EventRegistry",
    "MetricRegistry",
    "TraceRegistry",
]


# ---------------------------------------------------------------------------
# EventRegistry
# ---------------------------------------------------------------------------


class EventRegistry:
    """Registry for telemetry events with deterministic ordering.

    Events are stored in insertion order and can be retrieved in
    that order or filtered by category, type, or correlation ID.

    Attributes:
        _events: List of recorded events in insertion order.
    """

    def __init__(self) -> None:
        """Initialize the event registry."""
        self._events: list[TelemetryEvent] = []

    def add(self, event: TelemetryEvent) -> None:
        """Add an event to the registry.

        Args:
            event: The event to add.
        """
        self._events.append(event)

    def all(self) -> tuple[TelemetryEvent, ...]:
        """Get all events in insertion order.

        Returns:
            Tuple of all events.
        """
        return tuple(self._events)

    def by_category(self, category: str) -> tuple[TelemetryEvent, ...]:
        """Get events filtered by category.

        Args:
            category: Event category to filter by.

        Returns:
            Tuple of events matching the category.
        """
        return tuple(e for e in self._events if e.category == category)

    def by_type(self, event_type: str) -> tuple[TelemetryEvent, ...]:
        """Get events filtered by type.

        Args:
            event_type: Event type to filter by.

        Returns:
            Tuple of events matching the type.
        """
        return tuple(e for e in self._events if e.type == event_type)

    def by_correlation_id(
        self, correlation_id: str
    ) -> tuple[TelemetryEvent, ...]:
        """Get events filtered by correlation ID.

        Args:
            correlation_id: Correlation ID to filter by.

        Returns:
            Tuple of events matching the correlation ID.
        """
        return tuple(
            e for e in self._events if e.correlation_id == correlation_id
        )

    def by_request_id(self, request_id: str) -> tuple[TelemetryEvent, ...]:
        """Get events filtered by request ID.

        Args:
            request_id: Request ID to filter by.

        Returns:
            Tuple of events matching the request ID.
        """
        return tuple(e for e in self._events if e.request_id == request_id)

    def count(self) -> int:
        """Get the total number of events."""
        return len(self._events)

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()


# ---------------------------------------------------------------------------
# MetricRegistry
# ---------------------------------------------------------------------------


class MetricRegistry:
    """Registry for metrics with deterministic ordering.

    Metrics are stored in insertion order and can be retrieved in
    that order or filtered by name or labels.

    Attributes:
        _metrics: List of recorded metrics in insertion order.
    """

    def __init__(self) -> None:
        """Initialize the metric registry."""
        self._metrics: list[Metric] = []

    def add(self, metric: Metric) -> None:
        """Add a metric to the registry.

        Args:
            metric: The metric to add.
        """
        self._metrics.append(metric)

    def all(self) -> tuple[Metric, ...]:
        """Get all metrics in insertion order.

        Returns:
            Tuple of all metrics.
        """
        return tuple(self._metrics)

    def by_name(self, name: str) -> tuple[Metric, ...]:
        """Get metrics filtered by name.

        Args:
            name: Metric name to filter by.

        Returns:
            Tuple of metrics matching the name.
        """
        return tuple(m for m in self._metrics if m.name == name)

    def by_label(
        self, key: str, value: str
    ) -> tuple[Metric, ...]:
        """Get metrics filtered by label key-value pair.

        Args:
            key: Label key to filter by.
            value: Label value to filter by.

        Returns:
            Tuple of metrics matching the label.
        """
        return tuple(
            m for m in self._metrics if m.labels.get(key) == value
        )

    def count(self) -> int:
        """Get the total number of metrics."""
        return len(self._metrics)

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()


# ---------------------------------------------------------------------------
# TraceRegistry
# ---------------------------------------------------------------------------


class TraceRegistry:
    """Registry for traces with deterministic ordering.

    Traces are stored in insertion order and can be retrieved in
    that order or filtered by various identifiers.

    Attributes:
        _traces: List of recorded traces in insertion order.
    """

    def __init__(self) -> None:
        """Initialize the trace registry."""
        self._traces: list[Trace] = []

    def add(self, trace: Trace) -> None:
        """Add a trace to the registry.

        Args:
            trace: The trace to add.
        """
        self._traces.append(trace)

    def all(self) -> tuple[Trace, ...]:
        """Get all traces in insertion order.

        Returns:
            Tuple of all traces.
        """
        return tuple(self._traces)

    def by_request_id(self, request_id: str) -> tuple[Trace, ...]:
        """Get traces filtered by request ID.

        Args:
            request_id: Request ID to filter by.

        Returns:
            Tuple of traces matching the request ID.
        """
        return tuple(
            t for t in self._traces if t.request_id == request_id
        )

    def by_workflow_id(self, workflow_id: str) -> tuple[Trace, ...]:
        """Get traces filtered by workflow ID.

        Args:
            workflow_id: Workflow ID to filter by.

        Returns:
            Tuple of traces matching the workflow ID.
        """
        return tuple(
            t for t in self._traces if t.workflow_id == workflow_id
        )

    def by_execution_id(
        self, execution_id: str
    ) -> tuple[Trace, ...]:
        """Get traces filtered by execution ID.

        Args:
            execution_id: Execution ID to filter by.

        Returns:
            Tuple of traces matching the execution ID.
        """
        return tuple(
            t for t in self._traces if t.execution_id == execution_id
        )

    def count(self) -> int:
        """Get the total number of traces."""
        return len(self._traces)

    def clear(self) -> None:
        """Clear all traces."""
        self._traces.clear()