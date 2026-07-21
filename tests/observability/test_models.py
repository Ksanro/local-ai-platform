"""Tests for the observability models.

Tests immutable dataclass models, frozen state, and slot enforcement.
"""

from __future__ import annotations

import copy
import pickle

from dataclasses import FrozenInstanceError

import pytest

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


class TestTelemetryEvent:
    """Tests for TelemetryEvent model."""

    def test_basic_creation(self) -> None:
        """Test basic TelemetryEvent creation."""
        event = TelemetryEvent(
            event_id="evt-001",
            category="workflow",
            type="plan_generated",
            correlation_id="req-001",
            request_id="req-001",
        )

        assert event.event_id == "evt-001"
        assert event.category == "workflow"
        assert event.type == "plan_generated"
        assert event.correlation_id == "req-001"
        assert event.request_id == "req-001"
        assert event.metadata == {}

    def test_with_metadata(self) -> None:
        """Test TelemetryEvent with metadata."""
        event = TelemetryEvent(
            event_id="evt-002",
            category="execution",
            type="step_complete",
            metadata={"workflow_name": "bug-investigation", "step": 1},
        )

        assert event.metadata["workflow_name"] == "bug-investigation"
        assert event.metadata["step"] == 1

    def test_immutability(self) -> None:
        """Test that TelemetryEvent is immutable."""
        event = TelemetryEvent(
            event_id="evt-003",
            category="workflow",
        )

        with pytest.raises(FrozenInstanceError):
            event.category = "modified"  # type: ignore[misc]

    def test_frozen_dataclass(self) -> None:
        """Test that TelemetryEvent is a frozen dataclass."""
        event = TelemetryEvent(event_id="evt-004")

        with pytest.raises(FrozenInstanceError):
            event.event_id = "modified"  # type: ignore[misc]

    def test_hashable(self) -> None:
        """Test that TelemetryEvent is hashable."""
        event = TelemetryEvent(event_id="evt-005")
        assert hash(event) is not None

    def test_equality(self) -> None:
        """Test TelemetryEvent equality."""
        event1 = TelemetryEvent(
            event_id="evt-006",
            category="workflow",
            type="plan_generated",
        )
        event2 = TelemetryEvent(
            event_id="evt-006",
            category="workflow",
            type="plan_generated",
        )

        assert event1 == event2

    def test_not_equal(self) -> None:
        """Test TelemetryEvent inequality."""
        event1 = TelemetryEvent(event_id="evt-007", category="workflow")
        event2 = TelemetryEvent(event_id="evt-008", category="execution")

        assert event1 != event2


class TestTraceStep:
    """Tests for TraceStep model."""

    def test_basic_creation(self) -> None:
        """Test basic TraceStep creation."""
        step = TraceStep(
            step_id="step-1",
            component="workflow_engine",
            action="generate_plan",
        )

        assert step.step_id == "step-1"
        assert step.component == "workflow_engine"
        assert step.action == "generate_plan"
        assert step.duration_ms == 0.0
        assert step.status == "completed"
        assert step.metadata == {}

    def test_with_duration(self) -> None:
        """Test TraceStep with duration."""
        step = TraceStep(
            step_id="step-2",
            component="execution_engine",
            action="execute_step",
            duration_ms=1234.5,
            status="completed",
        )

        assert step.duration_ms == 1234.5

    def test_with_metadata(self) -> None:
        """Test TraceStep with metadata."""
        step = TraceStep(
            step_id="step-3",
            component="provider",
            action="call_api",
            metadata={"provider": "vllm", "model": "gpt-4"},
        )

        assert step.metadata["provider"] == "vllm"

    def test_failed_status(self) -> None:
        """Test TraceStep with failed status."""
        step = TraceStep(
            step_id="step-4",
            component="evaluation",
            action="evaluate",
            status="failed",
        )

        assert step.status == "failed"


class TestTrace:
    """Tests for Trace model."""

    def test_basic_creation(self) -> None:
        """Test basic Trace creation."""
        trace = Trace(
            trace_id="trace-001",
            request_id="req-001",
        )

        assert trace.trace_id == "trace-001"
        assert trace.request_id == "req-001"
        assert trace.steps == ()

    def test_with_steps(self) -> None:
        """Test Trace with steps."""
        step1 = TraceStep(
            step_id="step-1",
            component="workflow_engine",
            action="generate_plan",
        )
        step2 = TraceStep(
            step_id="step-2",
            component="execution_engine",
            action="execute_step",
        )

        trace = Trace(
            trace_id="trace-002",
            request_id="req-001",
            workflow_id="wf-001",
            execution_id="exec-001",
            steps=(step1, step2),
        )

        assert len(trace.steps) == 2
        assert trace.steps[0].component == "workflow_engine"
        assert trace.steps[1].component == "execution_engine"

    def test_with_all_ids(self) -> None:
        """Test Trace with all identifiers."""
        trace = Trace(
            trace_id="trace-003",
            request_id="req-001",
            workflow_id="wf-001",
            execution_id="exec-001",
            evaluation_id="eval-001",
            verification_id="verify-001",
            autonomous_iteration_id="auto-001",
        )

        assert trace.evaluation_id == "eval-001"
        assert trace.verification_id == "verify-001"
        assert trace.autonomous_iteration_id == "auto-001"


class TestMetric:
    """Tests for Metric model."""

    def test_basic_creation(self) -> None:
        """Test basic Metric creation."""
        metric = Metric(
            name="workflow_duration_ms",
            value=1234.5,
        )

        assert metric.name == "workflow_duration_ms"
        assert metric.value == 1234.5
        assert metric.labels == {}

    def test_with_labels(self) -> None:
        """Test Metric with labels."""
        metric = Metric(
            name="provider_latency_ms",
            value=567.8,
            labels={"provider_name": "vllm", "model": "gpt-4"},
        )

        assert metric.labels["provider_name"] == "vllm"
        assert metric.labels["model"] == "gpt-4"

    def test_immutability(self) -> None:
        """Test that Metric is immutable."""
        metric = Metric(name="test", value=1.0)

        with pytest.raises(FrozenInstanceError):
            metric.name = "modified"  # type: ignore[misc]

    def test_hashable(self) -> None:
        """Test that Metric is hashable."""
        metric = Metric(name="test", value=1.0)
        assert hash(metric) is not None


class TestWorkflowTelemetry:
    """Tests for WorkflowTelemetry model."""

    def test_basic_creation(self) -> None:
        """Test basic WorkflowTelemetry creation."""
        telemetry = WorkflowTelemetry(
            workflow_name="bug-investigation",
            workflow_id="wf-001",
        )

        assert telemetry.workflow_name == "bug-investigation"
        assert telemetry.workflow_id == "wf-001"
        assert telemetry.duration_ms == 0.0
        assert telemetry.steps_count == 0
        assert telemetry.status == "completed"

    def test_with_values(self) -> None:
        """Test WorkflowTelemetry with values."""
        telemetry = WorkflowTelemetry(
            workflow_name="feature-implementation",
            workflow_id="wf-002",
            duration_ms=5000.0,
            steps_count=5,
            status="completed",
            planning_duration_ms=1000.0,
        )

        assert telemetry.duration_ms == 5000.0
        assert telemetry.steps_count == 5
        assert telemetry.planning_duration_ms == 1000.0


class TestExecutionTelemetry:
    """Tests for ExecutionTelemetry model."""

    def test_basic_creation(self) -> None:
        """Test basic ExecutionTelemetry creation."""
        telemetry = ExecutionTelemetry(
            execution_id="exec-001",
            workflow_name="bug-investigation",
        )

        assert telemetry.execution_id == "exec-001"
        assert telemetry.workflow_name == "bug-investigation"
        assert telemetry.success is True

    def test_with_values(self) -> None:
        """Test ExecutionTelemetry with values."""
        telemetry = ExecutionTelemetry(
            execution_id="exec-002",
            workflow_name="feature-implementation",
            duration_ms=3000.0,
            adapter_name="vllm-adapter",
            steps_count=3,
            success=True,
        )

        assert telemetry.duration_ms == 3000.0
        assert telemetry.adapter_name == "vllm-adapter"
        assert telemetry.steps_count == 3


class TestProviderTelemetry:
    """Tests for ProviderTelemetry model."""

    def test_basic_creation(self) -> None:
        """Test basic ProviderTelemetry creation."""
        telemetry = ProviderTelemetry(
            provider_name="vllm",
            model="gpt-4",
        )

        assert telemetry.provider_name == "vllm"
        assert telemetry.model == "gpt-4"
        assert telemetry.status == "success"

    def test_with_error_status(self) -> None:
        """Test ProviderTelemetry with error status."""
        telemetry = ProviderTelemetry(
            provider_name="openai",
            model="gpt-4",
            latency_ms=2500.0,
            status="error",
            request_id="req-001",
        )

        assert telemetry.latency_ms == 2500.0
        assert telemetry.status == "error"


class TestEvaluationTelemetry:
    """Tests for EvaluationTelemetry model."""

    def test_basic_creation(self) -> None:
        """Test basic EvaluationTelemetry creation."""
        telemetry = EvaluationTelemetry(
            evaluation_id="eval-001",
            workflow_name="bug-investigation",
        )

        assert telemetry.evaluation_id == "eval-001"
        assert telemetry.score == 0.0
        assert telemetry.status == "completed"

    def test_with_values(self) -> None:
        """Test EvaluationTelemetry with values."""
        telemetry = EvaluationTelemetry(
            evaluation_id="eval-002",
            workflow_name="feature-implementation",
            score=0.85,
            metrics_count=5,
            status="completed",
        )

        assert telemetry.score == 0.85
        assert telemetry.metrics_count == 5


class TestVerificationTelemetry:
    """Tests for VerificationTelemetry model."""

    def test_basic_creation(self) -> None:
        """Test basic VerificationTelemetry creation."""
        telemetry = VerificationTelemetry(
            verification_id="verify-001",
            workflow_name="bug-investigation",
        )

        assert telemetry.verification_id == "verify-001"
        assert telemetry.score == 0.0
        assert telemetry.status == "passed"

    def test_with_values(self) -> None:
        """Test VerificationTelemetry with values."""
        telemetry = VerificationTelemetry(
            verification_id="verify-002",
            workflow_name="feature-implementation",
            score=0.95,
            findings_count=2,
            status="passed",
        )

        assert telemetry.score == 0.95
        assert telemetry.findings_count == 2


class TestSystemSnapshot:
    """Tests for SystemSnapshot model."""

    def test_basic_creation(self) -> None:
        """Test basic SystemSnapshot creation."""
        snapshot = SystemSnapshot()

        assert snapshot.event_count == 0
        assert snapshot.metric_count == 0
        assert snapshot.trace_count == 0
        assert snapshot.events == ()
        assert snapshot.metrics == ()
        assert snapshot.traces == ()

    def test_with_data(self) -> None:
        """Test SystemSnapshot with data."""
        event = TelemetryEvent(
            event_id="evt-001",
            category="workflow",
            type="plan_generated",
        )
        metric = Metric(name="duration_ms", value=1234.5)
        trace = Trace(trace_id="trace-001", request_id="req-001")

        workflow_telemetry = WorkflowTelemetry(
            workflow_name="test",
            workflow_id="wf-001",
        )

        snapshot = SystemSnapshot(
            event_count=1,
            metric_count=1,
            trace_count=1,
            events=(event,),
            metrics=(metric,),
            traces=(trace,),
            workflow_telemetry=(workflow_telemetry,),
        )

        assert snapshot.event_count == 1
        assert snapshot.metric_count == 1
        assert snapshot.trace_count == 1
        assert len(snapshot.events) == 1
        assert len(snapshot.metrics) == 1
        assert len(snapshot.traces) == 1
        assert len(snapshot.workflow_telemetry) == 1

    def test_immutability(self) -> None:
        """Test that SystemSnapshot is immutable."""
        snapshot = SystemSnapshot()

        with pytest.raises(FrozenInstanceError):
            snapshot.event_count = 5  # type: ignore[misc]

    def test_hashable(self) -> None:
        """Test that SystemSnapshot is hashable."""
        snapshot = SystemSnapshot()
        assert hash(snapshot) is not None


class TestImmutability:
    """Tests for overall immutability guarantees."""

    def test_all_models_are_frozen(self) -> None:
        """Test that all models use frozen=True."""
        models = [
            TelemetryEvent(event_id="test"),
            TraceStep(step_id="test", component="test", action="test"),
            Trace(trace_id="test", request_id="test"),
            Metric(name="test", value=1.0),
            WorkflowTelemetry(workflow_name="test", workflow_id="test"),
            ExecutionTelemetry(execution_id="test", workflow_name="test"),
            ProviderTelemetry(provider_name="test", model="test"),
            EvaluationTelemetry(evaluation_id="test", workflow_name="test"),
            VerificationTelemetry(verification_id="test", workflow_name="test"),
            SystemSnapshot(),
        ]

        for model in models:
            assert hasattr(model, "__dataclass_fields__")
            # Check that the dataclass is frozen
            assert model.__class__.__dataclass_params__.frozen is True

    def test_all_models_have_slots(self) -> None:
        """Test that all models use slots=True."""
        models = [
            TelemetryEvent(event_id="test"),
            TraceStep(step_id="test", component="test", action="test"),
            Trace(trace_id="test", request_id="test"),
            Metric(name="test", value=1.0),
            WorkflowTelemetry(workflow_name="test", workflow_id="test"),
            ExecutionTelemetry(execution_id="test", workflow_name="test"),
            ProviderTelemetry(provider_name="test", model="test"),
            EvaluationTelemetry(evaluation_id="test", workflow_name="test"),
            VerificationTelemetry(verification_id="test", workflow_name="test"),
            SystemSnapshot(),
        ]

        for model in models:
            # Slots dataclasses don't have __dict__
            assert not hasattr(model, "__dict__")

    def test_pickle_roundtrip(self) -> None:
        """Test that models can be pickled and unpickled."""
        event = TelemetryEvent(
            event_id="evt-001",
            category="workflow",
            type="plan_generated",
            metadata={"key": "value"},
        )

        pickled = pickle.dumps(event)
        unpickled = pickle.loads(pickled)  # noqa: S301

        assert unpickled.event_id == "evt-001"
        assert unpickled.category == "workflow"
        assert unpickled.metadata["key"] == "value"