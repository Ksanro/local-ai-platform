"""Main telemetry collector for the observability framework.

Provides the primary interface for recording events, metrics, and traces.
The collector is completely passive — it never changes platform behaviour.

Architecture
------------

EngineeringTelemetry --> EventRegistry, MetricRegistry, TraceRegistry

Constraints
-----------

- No platform logic.
- No file system operations.
- Optional (disabled by default).
- No global mutable state.

Public API
----------

.. code-block:: python

    from packages.observability import EngineeringTelemetry

    telemetry = EngineeringTelemetry(enabled=True)

    # Record events
    telemetry.record_event("workflow", "plan_generated", workflow_name="bug")

    # Record metrics
    telemetry.record_metric("workflow_duration_ms", 1234.5)

    # Record traces
    telemetry.record_trace(trace)

    # Take snapshot
    snapshot = telemetry.snapshot()

"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from packages.observability.events import EventCategory, EventType
from packages.observability.models import (
    EvaluationTelemetry,
    ExecutionTelemetry,
    Metric,
    ProviderTelemetry,
    SystemSnapshot,
    TelemetryEvent,
    Trace,
    VerificationTelemetry,
    WorkflowTelemetry,
)
from packages.observability.registry import (
    EventRegistry,
    MetricRegistry,
    TraceRegistry,
)

__all__ = [
    "EngineeringTelemetry",
]


# ---------------------------------------------------------------------------
# EngineeringTelemetry
# ---------------------------------------------------------------------------


class EngineeringTelemetry:
    """Main telemetry collector for the observability framework.

    This is the primary interface for recording telemetry data. It is
    completely passive and never changes platform behaviour.

    The collector maintains internal registries for events, metrics, and
    traces. All data is immutable — snapshots return copies.

    Attributes:
        enabled: Whether telemetry is enabled.
        _event_registry: Registry for telemetry events.
        _metric_registry: Registry for metrics.
        _trace_registry: Registry for traces.
        _workflow_telemetry: Workflow telemetry records.
        _execution_telemetry: Execution telemetry records.
        _provider_telemetry: Provider telemetry records.
        _evaluation_telemetry: Evaluation telemetry records.
        _verification_telemetry: Verification telemetry records.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize the telemetry collector.

        Args:
            enabled: Whether to enable telemetry recording.
        """
        self.enabled = enabled
        self._event_registry = EventRegistry()
        self._metric_registry = MetricRegistry()
        self._trace_registry = TraceRegistry()
        self._workflow_telemetry: list[WorkflowTelemetry] = []
        self._execution_telemetry: list[ExecutionTelemetry] = []
        self._provider_telemetry: list[ProviderTelemetry] = []
        self._evaluation_telemetry: list[EvaluationTelemetry] = []
        self._verification_telemetry: list[VerificationTelemetry] = []

    def record_event(
        self,
        category: str,
        event_type: str,
        correlation_id: str = "",
        request_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a telemetry event.

        This is a no-op when telemetry is disabled.

        Args:
            category: Event category (e.g. "workflow", "execution").
            event_type: Event type (e.g. "plan_generated", "step_complete").
            correlation_id: Correlation ID for linking events.
            request_id: Request ID from the gateway.
            metadata: Additional event metadata.

        Raises:
            ValueError: If category or event_type is invalid.
        """
        if not self.enabled:
            return

        # Validate before recording
        from packages.observability.events import validate_event

        if not validate_event(category, event_type):
            raise ValueError(
                f"Invalid event: category={category}, type={event_type}"
            )

        # Create the event
        event = TelemetryEvent(
            event_id=f"evt-{category}-{event_type}-{id(self)}",
            category=category,
            type=event_type,
            correlation_id=correlation_id,
            request_id=request_id,
            metadata=metadata or {},
        )

        # Record in registry
        self._event_registry.add(event)

    def record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a metric.

        This is a no-op when telemetry is disabled.

        Args:
            name: Metric name (e.g. "workflow_duration_ms").
            value: Metric value.
            labels: Key-value labels for the metric.
        """
        if not self.enabled:
            return

        metric = Metric(
            name=name,
            value=value,
            labels=labels or {},
        )

        self._metric_registry.add(metric)

    def record_trace(self, trace: Trace) -> None:
        """Record a trace.

        This is a no-op when telemetry is disabled.

        Args:
            trace: The trace to record.
        """
        if not self.enabled:
            return

        self._trace_registry.add(trace)

    def record_workflow_telemetry(self, telemetry: WorkflowTelemetry) -> None:
        """Record workflow-level telemetry.

        Args:
            telemetry: Workflow telemetry data.
        """
        if not self.enabled:
            return

        self._workflow_telemetry.append(telemetry)

    def record_execution_telemetry(self, telemetry: ExecutionTelemetry) -> None:
        """Record execution-level telemetry.

        Args:
            telemetry: Execution telemetry data.
        """
        if not self.enabled:
            return

        self._execution_telemetry.append(telemetry)

    def record_provider_telemetry(self, telemetry: ProviderTelemetry) -> None:
        """Record provider-level telemetry.

        Args:
            telemetry: Provider telemetry data.
        """
        if not self.enabled:
            return

        self._provider_telemetry.append(telemetry)

    def record_evaluation_telemetry(self, telemetry: EvaluationTelemetry) -> None:
        """Record evaluation-level telemetry.

        Args:
            telemetry: Evaluation telemetry data.
        """
        if not self.enabled:
            return

        self._evaluation_telemetry.append(telemetry)

    def record_verification_telemetry(self, telemetry: VerificationTelemetry) -> None:
        """Record verification-level telemetry.

        Args:
            telemetry: Verification telemetry data.
        """
        if not self.enabled:
            return

        self._verification_telemetry.append(telemetry)

    def snapshot(self) -> SystemSnapshot:
        """Take a complete snapshot of platform state.

        Returns an immutable SystemSnapshot containing all recorded data.
        The snapshot is a point-in-time view — subsequent recordings
        do not affect existing snapshots.

        Returns:
            A complete system snapshot.
        """
        # Sort events by timestamp, then by event_id for determinism
        sorted_events = tuple(
            sorted(
                self._event_registry.all(),
                key=lambda e: (e.timestamp, e.event_id),
            )
        )

        # Sort metrics by timestamp, then by name for determinism
        sorted_metrics = tuple(
            sorted(
                self._metric_registry.all(),
                key=lambda m: (m.timestamp, m.name),
            )
        )

        # Sort traces by started_at, then by trace_id for determinism
        sorted_traces = tuple(
            sorted(
                self._trace_registry.all(),
                key=lambda t: (t.started_at, t.trace_id),
            )
        )

        return SystemSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_count=len(sorted_events),
            metric_count=len(sorted_metrics),
            trace_count=len(sorted_traces),
            events=sorted_events,
            metrics=sorted_metrics,
            traces=sorted_traces,
            workflow_telemetry=tuple(self._workflow_telemetry),
            execution_telemetry=tuple(self._execution_telemetry),
            provider_telemetry=tuple(self._provider_telemetry),
            evaluation_telemetry=tuple(self._evaluation_telemetry),
            verification_telemetry=tuple(self._verification_telemetry),
        )

    def clear(self) -> None:
        """Clear all recorded telemetry data.

        This resets all registries and telemetry records. Use with
        caution — this is a destructive operation.
        """
        self._event_registry.clear()
        self._metric_registry.clear()
        self._trace_registry.clear()
        self._workflow_telemetry.clear()
        self._execution_telemetry.clear()
        self._provider_telemetry.clear()
        self._evaluation_telemetry.clear()
        self._verification_telemetry.clear()

    @property
    def event_count(self) -> int:
        """Get the total number of recorded events."""
        return self._event_registry.count()

    @property
    def metric_count(self) -> int:
        """Get the total number of recorded metrics."""
        return self._metric_registry.count()

    @property
    def trace_count(self) -> int:
        """Get the total number of recorded traces."""
        return self._trace_registry.count()