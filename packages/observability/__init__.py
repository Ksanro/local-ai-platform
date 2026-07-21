"""Engineering Observability & Telemetry Framework v1.

Complete visibility into the platform. NEVER changes platform behaviour.

Architecture
------------

Gateway --> Pipeline --> Workflow Engine --> Execution Engine --> Evaluation
    --> Patch Generator --> Code Modification Engine --> Self Verification
    --> Autonomous Engineering --> EngineeringTelemetry

The framework is completely passive. It observes existing public APIs
without modifying any platform behaviour.

Responsibilities
----------------

- Deterministic collection of telemetry events
- Immutable snapshots of platform state
- Event ordering and correlation IDs
- Execution timing across all components
- Optional and opaque observability

Non-responsibilities
--------------------

- Must NOT change platform behaviour
- Must NOT perform engineering work
- Must NOT call providers directly
- Must NOT perform repository analysis
- Must NOT duplicate component logic
- Must NOT introduce global mutable state

Public API
----------

.. code-block:: python

    from packages.observability import (
        EngineeringTelemetry,
        TelemetryEvent,
        Trace,
        Metric,
        SystemSnapshot,
        WorkflowTelemetry,
        ExecutionTelemetry,
        ProviderTelemetry,
        EvaluationTelemetry,
        VerificationTelemetry,
    )

    telemetry = EngineeringTelemetry()
    telemetry.record_event("workflow", "plan_generated", workflow_name="bug-investigation")
    telemetry.record_metric("workflow_duration_ms", 1234.5)
    telemetry.record_trace(trace)
    snapshot = telemetry.snapshot()

Usage
-----

The framework is optional. Components should check if telemetry is enabled
before recording. When disabled, all recording operations are no-ops.

.. code-block:: python

    from packages.observability import EngineeringTelemetry

    telemetry = EngineeringTelemetry(enabled=False)  # Disabled by default

    # These are all no-ops when disabled
    telemetry.record_event("category", "event_type")
    telemetry.record_metric("metric_name", 1.0)
    telemetry.record_trace(trace)

"""

from __future__ import annotations

from packages.observability.collector import EngineeringTelemetry
from packages.observability.events import EventCategory, EventType
from packages.observability.metrics import MetricAggregator, MetricRecord
from packages.observability.models import (
    EvaluationTelemetry,
    ExecutionTelemetry,
    Metric,
    ProviderTelemetry,
    SystemSnapshot,
    TelemetryEvent,
    Trace,
    TraceStep,
    VerificationTelemetry,
    WorkflowTelemetry,
)
from packages.observability.registry import (
    EventRegistry,
    MetricRegistry,
    TraceRegistry,
)

__all__ = [
    # Collector
    "EngineeringTelemetry",
    # Models
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
    # Events
    "EventCategory",
    "EventType",
    # Metrics
    "MetricAggregator",
    "MetricRecord",
    # Registry
    "EventRegistry",
    "MetricRegistry",
    "TraceRegistry",
]