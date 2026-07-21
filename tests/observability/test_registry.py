"""Tests for the registry module.

Tests event, metric, and trace registries with deterministic ordering.
"""

from __future__ import annotations

import pytest

from packages.observability.models import (
    Metric,
    TelemetryEvent,
    Trace,
    TraceStep,
)
from packages.observability.registry import (
    EventRegistry,
    MetricRegistry,
    TraceRegistry,
)


class TestEventRegistry:
    """Tests for EventRegistry."""

    def test_empty_registry(self) -> None:
        """Test empty registry."""
        registry = EventRegistry()
        assert registry.count() == 0
        assert registry.all() == ()

    def test_add_event(self) -> None:
        """Test adding an event."""
        registry = EventRegistry()
        event = TelemetryEvent(
            event_id="evt-001",
            category="workflow",
            type="plan_generated",
        )
        registry.add(event)
        assert registry.count() == 1

    def test_add_multiple_events(self) -> None:
        """Test adding multiple events."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001", category="workflow"))
        registry.add(TelemetryEvent(event_id="evt-002", category="execution"))
        registry.add(TelemetryEvent(event_id="evt-003", category="provider"))

        assert registry.count() == 3

    def test_all_returns_all_events(self) -> None:
        """Test that all() returns all events."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001", category="workflow"))
        registry.add(TelemetryEvent(event_id="evt-002", category="execution"))

        all_events = registry.all()
        assert len(all_events) == 2

    def test_by_category(self) -> None:
        """Test filtering by category."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001", category="workflow"))
        registry.add(TelemetryEvent(event_id="evt-002", category="execution"))
        registry.add(TelemetryEvent(event_id="evt-003", category="workflow"))

        workflow_events = registry.by_category("workflow")
        assert len(workflow_events) == 2
        assert all(e.category == "workflow" for e in workflow_events)

    def test_by_type(self) -> None:
        """Test filtering by type."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001", type="plan_generated"))
        registry.add(TelemetryEvent(event_id="evt-002", type="step_complete"))
        registry.add(TelemetryEvent(event_id="evt-003", type="plan_generated"))

        plan_events = registry.by_type("plan_generated")
        assert len(plan_events) == 2

    def test_by_correlation_id(self) -> None:
        """Test filtering by correlation ID."""
        registry = EventRegistry()
        registry.add(
            TelemetryEvent(
                event_id="evt-001",
                correlation_id="req-001",
            )
        )
        registry.add(
            TelemetryEvent(
                event_id="evt-002",
                correlation_id="req-002",
            )
        )
        registry.add(
            TelemetryEvent(
                event_id="evt-003",
                correlation_id="req-001",
            )
        )

        req001_events = registry.by_correlation_id("req-001")
        assert len(req001_events) == 2

    def test_by_request_id(self) -> None:
        """Test filtering by request ID."""
        registry = EventRegistry()
        registry.add(
            TelemetryEvent(
                event_id="evt-001",
                request_id="req-001",
            )
        )
        registry.add(
            TelemetryEvent(
                event_id="evt-002",
                request_id="req-002",
            )
        )

        req001_events = registry.by_request_id("req-001")
        assert len(req001_events) == 1
        assert req001_events[0].request_id == "req-001"

    def test_clear(self) -> None:
        """Test clearing all events."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001"))
        registry.add(TelemetryEvent(event_id="evt-002"))

        assert registry.count() == 2
        registry.clear()
        assert registry.count() == 0
        assert registry.all() == ()

    def test_insertion_order_preserved(self) -> None:
        """Test that insertion order is preserved."""
        registry = EventRegistry()
        registry.add(TelemetryEvent(event_id="evt-001"))
        registry.add(TelemetryEvent(event_id="evt-002"))
        registry.add(TelemetryEvent(event_id="evt-003"))

        all_events = registry.all()
        assert all_events[0].event_id == "evt-001"
        assert all_events[1].event_id == "evt-002"
        assert all_events[2].event_id == "evt-003"


class TestMetricRegistry:
    """Tests for MetricRegistry."""

    def test_empty_registry(self) -> None:
        """Test empty registry."""
        registry = MetricRegistry()
        assert registry.count() == 0

    def test_add_metric(self) -> None:
        """Test adding a metric."""
        registry = MetricRegistry()
        registry.add(Metric(name="duration_ms", value=1234.5))
        assert registry.count() == 1

    def test_add_multiple_metrics(self) -> None:
        """Test adding multiple metrics."""
        registry = MetricRegistry()
        registry.add(Metric(name="metric_a", value=1.0))
        registry.add(Metric(name="metric_b", value=2.0))
        registry.add(Metric(name="metric_a", value=3.0))

        assert registry.count() == 3

    def test_by_name(self) -> None:
        """Test filtering by name."""
        registry = MetricRegistry()
        registry.add(Metric(name="duration", value=100.0))
        registry.add(Metric(name="latency", value=200.0))
        registry.add(Metric(name="duration", value=300.0))

        duration_metrics = registry.by_name("duration")
        assert len(duration_metrics) == 2
        assert all(m.name == "duration" for m in duration_metrics)

    def test_by_label(self) -> None:
        """Test filtering by label."""
        registry = MetricRegistry()
        registry.add(
            Metric(
                name="latency",
                value=100.0,
                labels={"provider": "vllm"},
            )
        )
        registry.add(
            Metric(
                name="latency",
                value=200.0,
                labels={"provider": "openai"},
            )
        )

        vllm_metrics = registry.by_label("provider", "vllm")
        assert len(vllm_metrics) == 1
        assert vllm_metrics[0].labels["provider"] == "vllm"

    def test_all_returns_all_metrics(self) -> None:
        """Test that all() returns all metrics."""
        registry = MetricRegistry()
        registry.add(Metric(name="metric_a", value=1.0))
        registry.add(Metric(name="metric_b", value=2.0))

        all_metrics = registry.all()
        assert len(all_metrics) == 2

    def test_clear(self) -> None:
        """Test clearing all metrics."""
        registry = MetricRegistry()
        registry.add(Metric(name="metric_a", value=1.0))
        registry.add(Metric(name="metric_b", value=2.0))

        registry.clear()
        assert registry.count() == 0

    def test_insertion_order_preserved(self) -> None:
        """Test that insertion order is preserved."""
        registry = MetricRegistry()
        registry.add(Metric(name="metric_a", value=1.0))
        registry.add(Metric(name="metric_b", value=2.0))
        registry.add(Metric(name="metric_c", value=3.0))

        all_metrics = registry.all()
        assert all_metrics[0].name == "metric_a"
        assert all_metrics[1].name == "metric_b"
        assert all_metrics[2].name == "metric_c"


class TestTraceRegistry:
    """Tests for TraceRegistry."""

    def test_empty_registry(self) -> None:
        """Test empty registry."""
        registry = TraceRegistry()
        assert registry.count() == 0

    def test_add_trace(self) -> None:
        """Test adding a trace."""
        registry = TraceRegistry()
        trace = Trace(trace_id="trace-001", request_id="req-001")
        registry.add(trace)
        assert registry.count() == 1

    def test_add_multiple_traces(self) -> None:
        """Test adding multiple traces."""
        registry = TraceRegistry()
        registry.add(Trace(trace_id="trace-001", request_id="req-001"))
        registry.add(Trace(trace_id="trace-002", request_id="req-002"))
        registry.add(Trace(trace_id="trace-003", request_id="req-001"))

        assert registry.count() == 3

    def test_by_request_id(self) -> None:
        """Test filtering by request ID."""
        registry = TraceRegistry()
        registry.add(Trace(trace_id="trace-001", request_id="req-001"))
        registry.add(Trace(trace_id="trace-002", request_id="req-002"))
        registry.add(Trace(trace_id="trace-003", request_id="req-001"))

        req001_traces = registry.by_request_id("req-001")
        assert len(req001_traces) == 2

    def test_by_workflow_id(self) -> None:
        """Test filtering by workflow ID."""
        registry = TraceRegistry()
        registry.add(
            Trace(trace_id="trace-001", request_id="req-001", workflow_id="wf-001")
        )
        registry.add(
            Trace(trace_id="trace-002", request_id="req-002", workflow_id="wf-002")
        )
        registry.add(
            Trace(trace_id="trace-003", request_id="req-003", workflow_id="wf-001")
        )

        wf001_traces = registry.by_workflow_id("wf-001")
        assert len(wf001_traces) == 2

    def test_by_execution_id(self) -> None:
        """Test filtering by execution ID."""
        registry = TraceRegistry()
        registry.add(
            Trace(trace_id="trace-001", request_id="req-001", execution_id="exec-001")
        )
        registry.add(
            Trace(trace_id="trace-002", request_id="req-002", execution_id="exec-002")
        )

        exec001_traces = registry.by_execution_id("exec-001")
        assert len(exec001_traces) == 1
        assert exec001_traces[0].execution_id == "exec-001"

    def test_all_returns_all_traces(self) -> None:
        """Test that all() returns all traces."""
        registry = TraceRegistry()
        registry.add(Trace(trace_id="trace-001", request_id="req-001"))
        registry.add(Trace(trace_id="trace-002", request_id="req-002"))

        all_traces = registry.all()
        assert len(all_traces) == 2

    def test_clear(self) -> None:
        """Test clearing all traces."""
        registry = TraceRegistry()
        registry.add(Trace(trace_id="trace-001", request_id="req-001"))
        registry.add(Trace(trace_id="trace-002", request_id="req-002"))

        registry.clear()
        assert registry.count() == 0

    def test_insertion_order_preserved(self) -> None:
        """Test that insertion order is preserved."""
        registry = TraceRegistry()
        registry.add(Trace(trace_id="trace-001", request_id="req-001"))
        registry.add(Trace(trace_id="trace-002", request_id="req-002"))
        registry.add(Trace(trace_id="trace-003", request_id="req-003"))

        all_traces = registry.all()
        assert all_traces[0].trace_id == "trace-001"
        assert all_traces[1].trace_id == "trace-002"
        assert all_traces[2].trace_id == "trace-003"


class TestRegistryIntegration:
    """Integration tests for registries."""

    def test_all_registries_together(self) -> None:
        """Test all registries working together."""
        event_registry = EventRegistry()
        metric_registry = MetricRegistry()
        trace_registry = TraceRegistry()

        # Add data
        event_registry.add(
            TelemetryEvent(
                event_id="evt-001",
                category="workflow",
                type="plan_generated",
                correlation_id="req-001",
            )
        )
        metric_registry.add(
            Metric(
                name="duration_ms",
                value=1234.5,
                labels={"component": "workflow"},
            )
        )
        trace_registry.add(
            Trace(
                trace_id="trace-001",
                request_id="req-001",
                workflow_id="wf-001",
                steps=(
                    TraceStep(
                        step_id="step-1",
                        component="workflow",
                        action="generate_plan",
                    ),
                ),
            )
        )

        # Verify counts
        assert event_registry.count() == 1
        assert metric_registry.count() == 1
        assert trace_registry.count() == 1

        # Verify filtering
        assert len(event_registry.by_category("workflow")) == 1
        assert len(metric_registry.by_name("duration_ms")) == 1
        assert len(trace_registry.by_request_id("req-001")) == 1

    def test_registry_isolation(self) -> None:
        """Test that registries are independent."""
        event_registry = EventRegistry()
        metric_registry = MetricRegistry()

        event_registry.add(
            TelemetryEvent(event_id="evt-001", category="workflow")
        )

        assert event_registry.count() == 1
        assert metric_registry.count() == 0