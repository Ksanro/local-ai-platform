"""Immutable telemetry model definitions.

Defines all data structures used by the observability framework. These are
the stable contracts between the telemetry collector and its consumers.

Architecture
------------

TelemetryEvent --> Trace --> SystemSnapshot
     |               |
     v               v
    Metric        TraceStep

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No platform logic fields.

Public API
----------

.. code-block:: python

    from packages.observability.models import (
        TelemetryEvent,
        Trace,
        TraceStep,
        Metric,
        WorkflowTelemetry,
        ExecutionTelemetry,
        ProviderTelemetry,
        EvaluationTelemetry,
        VerificationTelemetry,
        SystemSnapshot,
    )

    event = TelemetryEvent(
        event_id="evt-001",
        timestamp="2024-01-01T00:00:00",
        category="workflow",
        type="plan_generated",
        correlation_id="req-001",
        metadata={"workflow_name": "bug-investigation"},
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "EvaluationTelemetry",
    "ExecutionTelemetry",
    "Metric",
    "ProviderTelemetry",
    "SystemSnapshot",
    "TelemetryEvent",
    "Trace",
    "TraceStep",
    "VerificationTelemetry",
    "WorkflowTelemetry",
]


# ---------------------------------------------------------------------------
# TelemetryEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """An immutable record of a single telemetry event.

    Attributes:
        event_id: Unique event identifier.
        timestamp: ISO format timestamp when the event occurred.
        category: High-level category (e.g. "workflow", "execution").
        type: Specific event type (e.g. "plan_generated", "step_complete").
        correlation_id: Correlation ID linking related events.
        request_id: Request identifier from the gateway.
        metadata: Additional event-specific metadata.
    """

    event_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str = ""
    type: str = ""
    correlation_id: str = ""
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TraceStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TraceStep:
    """A single step in a trace chain.

    Attributes:
        step_id: Unique step identifier.
        component: Component name (e.g. "pipeline", "workflow_engine").
        action: Action performed (e.g. "generate_plan", "execute_step").
        duration_ms: Duration in milliseconds.
        status: Step status ("completed", "failed", "skipped").
        metadata: Additional step metadata.
    """

    step_id: str
    component: str
    action: str
    duration_ms: float = 0.0
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Trace:
    """A complete trace of an engineering execution.

    Traces link all steps from gateway to autonomous iteration.

    Attributes:
        trace_id: Unique trace identifier.
        request_id: Request identifier from the gateway.
        workflow_id: Workflow identifier.
        execution_id: Execution identifier.
        evaluation_id: Evaluation identifier.
        verification_id: Verification identifier.
        autonomous_iteration_id: Autonomous iteration identifier.
        steps: Ordered list of trace steps.
        started_at: ISO format timestamp when tracing started.
        completed_at: ISO format timestamp when tracing completed.
    """

    trace_id: str
    request_id: str = ""
    workflow_id: str = ""
    execution_id: str = ""
    evaluation_id: str = ""
    verification_id: str = ""
    autonomous_iteration_id: str = ""
    steps: tuple[TraceStep, ...] = field(default_factory=tuple)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Metric:
    """A single metric measurement.

    Attributes:
        name: Metric name (e.g. "workflow_duration_ms").
        value: Metric value.
        labels: Key-value labels for the metric.
        timestamp: ISO format timestamp when measured.
    """

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# WorkflowTelemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowTelemetry:
    """Workflow-level telemetry data.

    Attributes:
        workflow_name: Name of the workflow.
        workflow_id: Unique workflow identifier.
        duration_ms: Total workflow duration in milliseconds.
        steps_count: Number of workflow steps.
        status: Workflow status ("completed", "failed", "skipped").
        planning_duration_ms: Planning phase duration.
        metadata: Additional metadata.
    """

    workflow_name: str
    workflow_id: str
    duration_ms: float = 0.0
    steps_count: int = 0
    status: str = "completed"
    planning_duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ExecutionTelemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionTelemetry:
    """Execution-level telemetry data.

    Attributes:
        execution_id: Unique execution identifier.
        workflow_name: Associated workflow name.
        duration_ms: Total execution duration in milliseconds.
        adapter_name: Execution adapter name.
        steps_count: Number of execution steps.
        success: Whether execution succeeded.
        metadata: Additional metadata.
    """

    execution_id: str
    workflow_name: str
    duration_ms: float = 0.0
    adapter_name: str = ""
    steps_count: int = 0
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ProviderTelemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderTelemetry:
    """Provider-level telemetry data.

    Attributes:
        provider_name: Provider name (e.g. "vllm").
        model: Model name used.
        latency_ms: Provider latency in milliseconds.
        status: Provider status ("success", "error", "timeout").
        request_id: Associated request ID.
        metadata: Additional metadata.
    """

    provider_name: str
    model: str
    latency_ms: float = 0.0
    status: str = "success"
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EvaluationTelemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationTelemetry:
    """Evaluation-level telemetry data.

    Attributes:
        evaluation_id: Unique evaluation identifier.
        workflow_name: Associated workflow name.
        score: Evaluation score (0.0 to 1.0).
        metrics_count: Number of evaluation metrics.
        status: Evaluation status ("completed", "failed", "skipped").
        metadata: Additional metadata.
    """

    evaluation_id: str
    workflow_name: str
    score: float = 0.0
    metrics_count: int = 0
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# VerificationTelemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationTelemetry:
    """Verification-level telemetry data.

    Attributes:
        verification_id: Unique verification identifier.
        workflow_name: Associated workflow name.
        score: Verification score (0.0 to 1.0).
        findings_count: Number of verification findings.
        status: Verification status ("passed", "failed", "warning", "skipped").
        metadata: Additional metadata.
    """

    verification_id: str
    workflow_name: str
    score: float = 0.0
    findings_count: int = 0
    status: str = "passed"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SystemSnapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    """A complete snapshot of platform state at a point in time.

    Attributes:
        timestamp: ISO format timestamp when the snapshot was taken.
        event_count: Total number of recorded events.
        metric_count: Total number of recorded metrics.
        trace_count: Total number of recorded traces.
        events: Sorted list of all recorded events.
        metrics: Sorted list of all recorded metrics.
        traces: Sorted list of all recorded traces.
        workflow_telemetry: List of workflow telemetry records.
        execution_telemetry: List of execution telemetry records.
        provider_telemetry: List of provider telemetry records.
        evaluation_telemetry: List of evaluation telemetry records.
        verification_telemetry: List of verification telemetry records.
    """

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_count: int = 0
    metric_count: int = 0
    trace_count: int = 0
    events: tuple[TelemetryEvent, ...] = field(default_factory=tuple)
    metrics: tuple[Metric, ...] = field(default_factory=tuple)
    traces: tuple[Trace, ...] = field(default_factory=tuple)
    workflow_telemetry: tuple[WorkflowTelemetry, ...] = field(default_factory=tuple)
    execution_telemetry: tuple[ExecutionTelemetry, ...] = field(default_factory=tuple)
    provider_telemetry: tuple[ProviderTelemetry, ...] = field(default_factory=tuple)
    evaluation_telemetry: tuple[EvaluationTelemetry, ...] = field(default_factory=tuple)
    verification_telemetry: tuple[VerificationTelemetry, ...] = field(default_factory=tuple)