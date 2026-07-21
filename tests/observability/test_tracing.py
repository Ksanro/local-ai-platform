"""Tests for the tracing module.

Tests trace building, lifecycle, and convenience functions.
"""

from __future__ import annotations

import pytest

from packages.observability.tracing import (
    TraceBuilder,
    add_trace_step,
    complete_trace,
    create_trace,
)


class TestTraceBuilder:
    """Tests for TraceBuilder."""

    def test_basic_creation(self) -> None:
        """Test basic trace builder creation."""
        builder = TraceBuilder(request_id="req-001")
        assert builder.request_id == "req-001"

    def test_default_values(self) -> None:
        """Test default values."""
        builder = TraceBuilder()
        assert builder.request_id == ""
        assert builder.workflow_id == ""
        assert builder.execution_id == ""
        assert builder.evaluation_id == ""
        assert builder.verification_id == ""
        assert builder.autonomous_iteration_id == ""
        assert builder._steps == []

    def test_set_workflow_id(self) -> None:
        """Test setting workflow ID."""
        builder = TraceBuilder()
        result = builder.set_workflow_id("wf-001")
        assert builder.workflow_id == "wf-001"
        assert result is builder  # Returns self for chaining

    def test_set_execution_id(self) -> None:
        """Test setting execution ID."""
        builder = TraceBuilder()
        result = builder.set_execution_id("exec-001")
        assert builder.execution_id == "exec-001"
        assert result is builder

    def test_set_evaluation_id(self) -> None:
        """Test setting evaluation ID."""
        builder = TraceBuilder()
        result = builder.set_evaluation_id("eval-001")
        assert builder.evaluation_id == "eval-001"
        assert result is builder

    def test_set_verification_id(self) -> None:
        """Test setting verification ID."""
        builder = TraceBuilder()
        result = builder.set_verification_id("verify-001")
        assert builder.verification_id == "verify-001"
        assert result is builder

    def test_set_autonomous_iteration_id(self) -> None:
        """Test setting autonomous iteration ID."""
        builder = TraceBuilder()
        result = builder.set_autonomous_iteration_id("auto-001")
        assert builder.autonomous_iteration_id == "auto-001"
        assert result is builder

    def test_add_step(self) -> None:
        """Test adding a trace step."""
        builder = TraceBuilder()
        result = builder.add_step(
            component="workflow_engine",
            action="generate_plan",
            duration_ms=100.0,
        )
        assert builder._steps[0].component == "workflow_engine"
        assert builder._steps[0].action == "generate_plan"
        assert builder._steps[0].duration_ms == 100.0
        assert result is builder

    def test_add_step_with_status(self) -> None:
        """Test adding step with status."""
        builder = TraceBuilder()
        builder.add_step(
            component="execution_engine",
            action="execute_step",
            status="failed",
        )
        assert builder._steps[0].status == "failed"

    def test_add_step_with_metadata(self) -> None:
        """Test adding step with metadata."""
        builder = TraceBuilder()
        builder.add_step(
            component="provider",
            action="call_api",
            metadata={"provider": "vllm"},
        )
        assert builder._steps[0].metadata["provider"] == "vllm"

    def test_method_chaining(self) -> None:
        """Test method chaining."""
        builder = TraceBuilder(request_id="req-001")
        builder.set_workflow_id("wf-001").set_execution_id("exec-001")
        builder.add_step("workflow", "action1").add_step("exec", "action2")

        assert builder.workflow_id == "wf-001"
        assert builder.execution_id == "exec-001"
        assert len(builder._steps) == 2

    def test_build(self) -> None:
        """Test building a trace."""
        builder = TraceBuilder(request_id="req-001")
        builder.set_workflow_id("wf-001")
        builder.add_step("workflow", "generate_plan", duration_ms=100.0)

        trace = builder.build()

        assert trace.request_id == "req-001"
        assert trace.workflow_id == "wf-001"
        assert len(trace.steps) == 1
        assert trace.steps[0].component == "workflow"
        assert trace.trace_id.startswith("trace-")

    def test_build_complete_trace(self) -> None:
        """Test building a complete trace."""
        builder = TraceBuilder(request_id="req-001")
        builder.set_workflow_id("wf-001")
        builder.set_execution_id("exec-001")
        builder.set_evaluation_id("eval-001")
        builder.set_verification_id("verify-001")
        builder.set_autonomous_iteration_id("auto-001")

        builder.add_step("gateway", "receive_request")
        builder.add_step("workflow", "generate_plan", duration_ms=100.0)
        builder.add_step("execution", "execute_step", duration_ms=200.0)
        builder.add_step("evaluation", "evaluate", status="failed")

        trace = builder.build()

        assert trace.request_id == "req-001"
        assert trace.workflow_id == "wf-001"
        assert trace.execution_id == "exec-001"
        assert trace.evaluation_id == "eval-001"
        assert trace.verification_id == "verify-001"
        assert trace.autonomous_iteration_id == "auto-001"
        assert len(trace.steps) == 4
        assert trace.steps[3].status == "failed"


class TestCreateTrace:
    """Tests for create_trace function."""

    def test_empty_trace(self) -> None:
        """Test creating empty trace."""
        trace = create_trace()
        assert trace.trace_id.startswith("trace-")
        assert trace.request_id == ""
        assert trace.steps == ()

    def test_trace_with_all_ids(self) -> None:
        """Test creating trace with all IDs."""
        trace = create_trace(
            request_id="req-001",
            workflow_id="wf-001",
            execution_id="exec-001",
            evaluation_id="eval-001",
            verification_id="verify-001",
            autonomous_iteration_id="auto-001",
        )

        assert trace.request_id == "req-001"
        assert trace.workflow_id == "wf-001"
        assert trace.execution_id == "exec-001"
        assert trace.evaluation_id == "eval-001"
        assert trace.verification_id == "verify-001"
        assert trace.autonomous_iteration_id == "auto-001"


class TestAddTraceStep:
    """Tests for add_trace_step function."""

    def test_add_step_to_empty_trace(self) -> None:
        """Test adding step to empty trace."""
        trace = create_trace(request_id="req-001")
        new_trace = add_trace_step(
            trace,
            "workflow",
            "generate_plan",
            duration_ms=100.0,
        )

        assert new_trace.trace_id == trace.trace_id
        assert len(new_trace.steps) == 1
        assert new_trace.steps[0].component == "workflow"
        # Original trace unchanged
        assert len(trace.steps) == 0

    def test_add_step_to_trace_with_steps(self) -> None:
        """Test adding step to trace with existing steps."""
        step1 = add_trace_step(
            create_trace(),
            "workflow",
            "action1",
        )
        step2 = add_trace_step(
            step1,
            "execution",
            "action2",
        )

        assert len(step1.steps) == 1
        assert len(step2.steps) == 2
        assert step2.steps[0].component == "workflow"
        assert step2.steps[1].component == "execution"

    def test_immutability(self) -> None:
        """Test that add_trace_step preserves immutability."""
        trace = create_trace()
        new_trace = add_trace_step(trace, "test", "action")

        # Original unchanged
        assert len(trace.steps) == 0
        # New trace has step
        assert len(new_trace.steps) == 1


class TestCompleteTrace:
    """Tests for complete_trace function."""

    def test_complete_empty_trace(self) -> None:
        """Test completing empty trace."""
        trace = create_trace()
        completed = complete_trace(trace)

        assert completed.trace_id == trace.trace_id
        assert completed.steps == trace.steps
        assert completed.completed_at != ""

    def test_complete_trace_with_steps(self) -> None:
        """Test completing trace with steps."""
        trace = add_trace_step(
            create_trace(),
            "workflow",
            "action",
        )
        completed = complete_trace(trace)

        assert len(completed.steps) == 1
        assert completed.trace_id == trace.trace_id


class TestTraceLifecycle:
    """Tests for complete trace lifecycle."""

    def test_full_lifecycle(self) -> None:
        """Test full trace lifecycle."""
        # Start building
        builder = TraceBuilder(request_id="req-001")
        builder.set_workflow_id("wf-001")
        builder.set_execution_id("exec-001")

        # Add steps
        builder.add_step("gateway", "receive_request")
        builder.add_step("pipeline", "process_stages")
        builder.add_step("workflow", "generate_plan", duration_ms=100.0)
        builder.add_step("execution", "execute_step", duration_ms=200.0)

        # Build trace
        trace = builder.build()

        # Verify
        assert trace.request_id == "req-001"
        assert trace.workflow_id == "wf-001"
        assert trace.execution_id == "exec-001"
        assert len(trace.steps) == 4
        assert trace.steps[0].component == "gateway"
        assert trace.steps[3].component == "execution"
        assert trace.steps[2].duration_ms == 100.0
        assert trace.steps[3].duration_ms == 200.0

    def test_failed_step_in_lifecycle(self) -> None:
        """Test lifecycle with failed step."""
        builder = TraceBuilder(request_id="req-001")
        builder.add_step("workflow", "generate_plan")
        builder.add_step(
            "execution",
            "execute_step",
            status="failed",
        )
        builder.add_step("pipeline", "skip_remaining", status="skipped")

        trace = builder.build()

        assert trace.steps[1].status == "failed"
        assert trace.steps[2].status == "skipped"


class TestImmutability:
    """Tests for trace immutability."""

    def test_trace_is_frozen(self) -> None:
        """Test that Trace is frozen."""
        from packages.observability.models import Trace

        trace = Trace(trace_id="test", request_id="test")
        assert trace.__class__.__dataclass_params__.frozen is True

    def test_trace_step_is_frozen(self) -> None:
        """Test that TraceStep is frozen."""
        from packages.observability.models import TraceStep

        step = TraceStep(step_id="test", component="test", action="test")
        assert step.__class__.__dataclass_params__.frozen is True