"""Tests for the telemetry collector.

Tests event collection, metric recording, trace recording, snapshots,
and the disabled state behaviour.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from packages.observability.collector import EngineeringTelemetry
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


class TestEngineeringTelemetryInit:
    """Tests for EngineeringTelemetry initialization."""

    def test_default_disabled(self) -> None:
        """Test that telemetry is disabled by default."""
        telemetry = EngineeringTelemetry()
        assert telemetry.enabled is False

    def test_explicit_enabled(self) -> None:
        """Test enabling telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        assert telemetry.enabled is True

    def test_explicit_disabled(self) -> None:
        """Test explicitly disabling telemetry."""
        telemetry = EngineeringTelemetry(enabled=False)
        assert telemetry.enabled is False

    def test_registries_initialized(self) -> None:
        """Test that registries are initialized."""
        telemetry = EngineeringTelemetry()

        assert isinstance(telemetry._event_registry, EventRegistry)
        assert isinstance(telemetry._metric_registry, MetricRegistry)
        assert isinstance(telemetry._trace_registry, TraceRegistry)


class TestRecordEvent:
    """Tests for record_event method."""

    def test_disabled_noop(self) -> None:
        """Test that record_event is a no-op when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)
        telemetry.record_event("workflow", "plan_generated")
        assert telemetry.event_count == 0

    def test_enabled_records(self) -> None:
        """Test that record_event records when enabled."""
        telemetry = EngineeringTelemetry(enabled=True)
        telemetry.record_event(
            "workflow",
            "plan_generated",
            correlation_id="req-001",
            request_id="req-001",
            metadata={"workflow_name": "test"},
        )
        assert telemetry.event_count == 1

    def test_invalid_category_raises(self) -> None:
        """Test that invalid category raises ValueError."""
        telemetry = EngineeringTelemetry(enabled=True)

        with pytest.raises(ValueError, match="Invalid event"):
            telemetry.record_event("invalid", "some_type")

    def test_invalid_type_raises(self) -> None:
        """Test that invalid event type raises ValueError."""
        telemetry = EngineeringTelemetry(enabled=True)

        with pytest.raises(ValueError, match="Invalid event"):
            telemetry.record_event("workflow", "invalid_type")

    def test_multiple_events(self) -> None:
        """Test recording multiple events."""
        telemetry = EngineeringTelemetry(enabled=True)

        telemetry.record_event("workflow", "plan_generated")
        telemetry.record_event("execution", "step_complete")
        telemetry.record_event("provider", "call")

        assert telemetry.event_count == 3


class TestRecordMetric:
    """Tests for record_metric method."""

    def test_disabled_noop(self) -> None:
        """Test that record_metric is a no-op when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)
        telemetry.record_metric("test_metric", 1.0)
        assert telemetry.metric_count == 0

    def test_enabled_records(self) -> None:
        """Test that record_metric records when enabled."""
        telemetry = EngineeringTelemetry(enabled=True)
        telemetry.record_metric("workflow_duration_ms", 1234.5)
        assert telemetry.metric_count == 1

    def test_with_labels(self) -> None:
        """Test recording metric with labels."""
        telemetry = EngineeringTelemetry(enabled=True)
        telemetry.record_metric(
            "provider_latency_ms",
            567.8,
            labels={"provider": "vllm", "model": "gpt-4"},
        )
        assert telemetry.metric_count == 1

    def test_multiple_metrics(self) -> None:
        """Test recording multiple metrics."""
        telemetry = EngineeringTelemetry(enabled=True)

        telemetry.record_metric("metric_a", 1.0)
        telemetry.record_metric("metric_b", 2.0)
        telemetry.record_metric("metric_a", 3.0)

        assert telemetry.metric_count == 3


class TestRecordTrace:
    """Tests for record_trace method."""

    def test_disabled_noop(self) -> None:
        """Test that record_trace is a no-op when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)
        trace = Trace(trace_id="trace-001", request_id="req-001")
        telemetry.record_trace(trace)
        assert telemetry.trace_count == 0

    def test_enabled_records(self) -> None:
        """Test that record_trace records when enabled."""
        telemetry = EngineeringTelemetry(enabled=True)
        trace = Trace(trace_id="trace-001", request_id="req-001")
        telemetry.record_trace(trace)
        assert telemetry.trace_count == 1

    def test_trace_with_steps(self) -> None:
        """Test recording trace with steps."""
        telemetry = EngineeringTelemetry(enabled=True)

        step = TraceStep(
            step_id="step-1",
            component="workflow_engine",
            action="generate_plan",
        )
        trace = Trace(
            trace_id="trace-001",
            request_id="req-001",
            steps=(step,),
        )
        telemetry.record_trace(trace)
        assert telemetry.trace_count == 1


class TestSpecializedTelemetry:
    """Tests for specialized telemetry recording methods."""

    def test_record_workflow_telemetry(self) -> None:
        """Test recording workflow telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        wf = WorkflowTelemetry(
            workflow_name="test",
            workflow_id="wf-001",
            duration_ms=1000.0,
        )
        telemetry.record_workflow_telemetry(wf)
        assert len(telemetry._workflow_telemetry) == 1

    def test_record_workflow_telemetry_disabled(self) -> None:
        """Test that workflow telemetry recording is no-op when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)
        wf = WorkflowTelemetry(
            workflow_name="test",
            workflow_id="wf-001",
        )
        telemetry.record_workflow_telemetry(wf)
        assert len(telemetry._workflow_telemetry) == 0

    def test_record_execution_telemetry(self) -> None:
        """Test recording execution telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        exec_telem = ExecutionTelemetry(
            execution_id="exec-001",
            workflow_name="test",
            duration_ms=500.0,
        )
        telemetry.record_execution_telemetry(exec_telem)
        assert len(telemetry._execution_telemetry) == 1

    def test_record_provider_telemetry(self) -> None:
        """Test recording provider telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        prov = ProviderTelemetry(
            provider_name="vllm",
            model="gpt-4",
            latency_ms=200.0,
        )
        telemetry.record_provider_telemetry(prov)
        assert len(telemetry._provider_telemetry) == 1

    def test_record_evaluation_telemetry(self) -> None:
        """Test recording evaluation telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        eval_telem = EvaluationTelemetry(
            evaluation_id="eval-001",
            workflow_name="test",
            score=0.85,
        )
        telemetry.record_evaluation_telemetry(eval_telem)
        assert len(telemetry._evaluation_telemetry) == 1

    def test_record_verification_telemetry(self) -> None:
        """Test recording verification telemetry."""
        telemetry = EngineeringTelemetry(enabled=True)
        verify_telem = VerificationTelemetry(
            verification_id="verify-001",
            workflow_name="test",
            score=0.95,
        )
        telemetry.record_verification_telemetry(verify_telem)
        assert len(telemetry._verification_telemetry) == 1


class TestSnapshot:
    """Tests for snapshot method."""

    def test_empty_snapshot(self) -> None:
        """Test snapshot with no data."""
        telemetry = EngineeringTelemetry(enabled=True)
        snapshot = telemetry.snapshot()

        assert isinstance(snapshot, SystemSnapshot)
        assert snapshot.event_count == 0
        assert snapshot.metric_count == 0
        assert snapshot.trace_count == 0
        assert snapshot.events == ()
        assert snapshot.metrics == ()
        assert snapshot.traces == ()

    def test_snapshot_with_data(self) -> None:
        """Test snapshot with recorded data."""
        telemetry = EngineeringTelemetry(enabled=True)

        # Record events
        telemetry.record_event("workflow", "plan_generated")
        telemetry.record_event("execution", "step_complete")

        # Record metrics
        telemetry.record_metric("duration_ms", 1234.5)
        telemetry.record_metric("latency_ms", 567.8)

        # Record traces
        trace = Trace(trace_id="trace-001", request_id="req-001")
        telemetry.record_trace(trace)

        snapshot = telemetry.snapshot()

        assert snapshot.event_count == 2
        assert snapshot.metric_count == 2
        assert snapshot.trace_count == 1
        assert len(snapshot.events) == 2
        assert len(snapshot.metrics) == 2
        assert len(snapshot.traces) == 1

    def test_snapshot_deterministic_order(self) -> None:
        """Test that snapshot returns deterministic ordering."""
        telemetry = EngineeringTelemetry(enabled=True)

        # Record multiple events
        telemetry.record_event("workflow", "plan_generated")
        telemetry.record_event("execution", "step_complete")
        telemetry.record_event("provider", "call")

        snapshot1 = telemetry.snapshot()
        snapshot2 = telemetry.snapshot()

        # Both snapshots should have same ordering
        assert len(snapshot1.events) == len(snapshot2.events)
        for e1, e2 in zip(snapshot1.events, snapshot2.events):
            assert e1.event_id == e2.event_id
            assert e1.category == e2.category

    def test_snapshot_isolation(self) -> None:
        """Test that snapshots are isolated from subsequent changes."""
        telemetry = EngineeringTelemetry(enabled=True)

        telemetry.record_event("workflow", "plan_generated")
        snapshot1 = telemetry.snapshot()

        # Record more events
        telemetry.record_event("execution", "step_complete")

        snapshot2 = telemetry.snapshot()

        # snapshot1 should still have only 1 event
        assert snapshot1.event_count == 1
        assert snapshot2.event_count == 2


class TestClear:
    """Tests for clear method."""

    def test_clear_events(self) -> None:
        """Test clearing events."""
        telemetry = EngineeringTelemetry(enabled=True)
        telemetry.record_event("workflow", "plan_generated")
        assert telemetry.event_count == 1

        telemetry.clear()
        assert telemetry.event_count == 0
        assert telemetry.metric_count == 0
        assert telemetry.trace_count == 0

    def test_clear_all_data(self) -> None:
        """Test clearing all telemetry data."""
        telemetry = EngineeringTelemetry(enabled=True)

        telemetry.record_event("workflow", "plan_generated")
        telemetry.record_metric("duration_ms", 1234.5)
        trace = Trace(trace_id="trace-001", request_id="req-001")
        telemetry.record_trace(trace)

        assert telemetry.event_count == 1
        assert telemetry.metric_count == 1
        assert telemetry.trace_count == 1

        telemetry.clear()

        assert telemetry.event_count == 0
        assert telemetry.metric_count == 0
        assert telemetry.trace_count == 0


class TestProperties:
    """Tests for count properties."""

    def test_event_count(self) -> None:
        """Test event_count property."""
        telemetry = EngineeringTelemetry(enabled=True)
        assert telemetry.event_count == 0

        telemetry.record_event("workflow", "plan_generated")
        assert telemetry.event_count == 1

    def test_metric_count(self) -> None:
        """Test metric_count property."""
        telemetry = EngineeringTelemetry(enabled=True)
        assert telemetry.metric_count == 0

        telemetry.record_metric("test", 1.0)
        assert telemetry.metric_count == 1

    def test_trace_count(self) -> None:
        """Test trace_count property."""
        telemetry = EngineeringTelemetry(enabled=True)
        assert telemetry.trace_count == 0

        trace = Trace(trace_id="trace-001", request_id="req-001")
        telemetry.record_trace(trace)
        assert telemetry.trace_count == 1


class TestDisabledBehaviour:
    """Tests for disabled telemetry behaviour."""

    def test_no_exceptions_when_disabled(self) -> None:
        """Test that no exceptions are raised when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)

        # All operations should be no-ops
        telemetry.record_event("workflow", "plan_generated")
        telemetry.record_metric("test", 1.0)
        telemetry.record_trace(
            Trace(trace_id="trace-001", request_id="req-001")
        )
        telemetry.record_workflow_telemetry(
            WorkflowTelemetry(workflow_name="test", workflow_id="wf-001")
        )
        telemetry.record_execution_telemetry(
            ExecutionTelemetry(execution_id="exec-001", workflow_name="test")
        )
        telemetry.record_provider_telemetry(
            ProviderTelemetry(provider_name="vllm", model="gpt-4")
        )
        telemetry.record_evaluation_telemetry(
            EvaluationTelemetry(evaluation_id="eval-001", workflow_name="test")
        )
        telemetry.record_verification_telemetry(
            VerificationTelemetry(verification_id="verify-001", workflow_name="test")
        )

        # All counts should be zero
        assert telemetry.event_count == 0
        assert telemetry.metric_count == 0
        assert telemetry.trace_count == 0

    def test_snapshot_when_disabled(self) -> None:
        """Test that snapshot works when disabled."""
        telemetry = EngineeringTelemetry(enabled=False)
        snapshot = telemetry.snapshot()

        assert isinstance(snapshot, SystemSnapshot)
        assert snapshot.event_count == 0
        assert snapshot.metric_count == 0
        assert snapshot.trace_count == 0