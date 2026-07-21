"""Deterministic tracing for the observability framework.

Provides complete trace lifecycle management across the entire platform.
Every engineering execution must be traceable from Gateway to Autonomous
Iteration.

Architecture
------------

TraceLifecycle --> TraceBuilder --> EngineeringTelemetry

Trace Lifecycle:
    1. Gateway creates request_id
    2. Pipeline propagates request_id through stages
    3. Workflow Engine creates workflow_id
    4. Execution Engine creates execution_id per step
    5. Evaluation creates evaluation_id
    6. Verification creates verification_id
    7. Autonomous Engine creates autonomous_iteration_id

Constraints
-----------

- No sampling.
- No randomness.
- No file system operations.
- Deterministic ordering.

Public API
----------

.. code-block:: python

    from packages.observability.tracing import (
        TraceBuilder,
        create_trace,
        add_trace_step,
        complete_trace,
    )

    builder = TraceBuilder(request_id="req-001")
    builder.add_step("workflow_engine", "generate_plan")
    trace = builder.build()

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from packages.observability.models import Trace, TraceStep

__all__ = [
    "TraceBuilder",
    "add_trace_step",
    "complete_trace",
    "create_trace",
]


# ---------------------------------------------------------------------------
# TraceBuilder
# ---------------------------------------------------------------------------


class TraceBuilder:
    """Builder for creating complete traces.

    Provides a fluent interface for building traces step by step.
    Each step is added in order and the final trace is immutable.

    Attributes:
        request_id: Request ID from the gateway.
        workflow_id: Workflow identifier.
        execution_id: Execution identifier.
        evaluation_id: Evaluation identifier.
        verification_id: Verification identifier.
        autonomous_iteration_id: Autonomous iteration identifier.
        _steps: List of trace steps being built.
        _started_at: ISO format timestamp when tracing started.
    """

    def __init__(self, request_id: str = "") -> None:
        """Initialize the trace builder.

        Args:
            request_id: Request ID from the gateway.
        """
        self.request_id = request_id
        self.workflow_id = ""
        self.execution_id = ""
        self.evaluation_id = ""
        self.verification_id = ""
        self.autonomous_iteration_id = ""
        self._steps: list[TraceStep] = []
        self._started_at = datetime.now(timezone.utc).isoformat()

    def set_workflow_id(self, workflow_id: str) -> TraceBuilder:
        """Set the workflow ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            Self for method chaining.
        """
        self.workflow_id = workflow_id
        return self

    def set_execution_id(self, execution_id: str) -> TraceBuilder:
        """Set the execution ID.

        Args:
            execution_id: Execution identifier.

        Returns:
            Self for method chaining.
        """
        self.execution_id = execution_id
        return self

    def set_evaluation_id(self, evaluation_id: str) -> TraceBuilder:
        """Set the evaluation ID.

        Args:
            evaluation_id: Evaluation identifier.

        Returns:
            Self for method chaining.
        """
        self.evaluation_id = evaluation_id
        return self

    def set_verification_id(self, verification_id: str) -> TraceBuilder:
        """Set the verification ID.

        Args:
            verification_id: Verification identifier.

        Returns:
            Self for method chaining.
        """
        self.verification_id = verification_id
        return self

    def set_autonomous_iteration_id(
        self, autonomous_iteration_id: str
    ) -> TraceBuilder:
        """Set the autonomous iteration ID.

        Args:
            autonomous_iteration_id: Autonomous iteration identifier.

        Returns:
            Self for method chaining.
        """
        self.autonomous_iteration_id = autonomous_iteration_id
        return self

    def add_step(
        self,
        component: str,
        action: str,
        duration_ms: float = 0.0,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> TraceBuilder:
        """Add a trace step.

        Args:
            component: Component name (e.g. "workflow_engine").
            action: Action performed (e.g. "generate_plan").
            duration_ms: Duration in milliseconds.
            status: Step status ("completed", "failed", "skipped").
            metadata: Additional step metadata.

        Returns:
            Self for method chaining.
        """
        step_id = f"step-{len(self._steps) + 1}"
        step = TraceStep(
            step_id=step_id,
            component=component,
            action=action,
            duration_ms=duration_ms,
            status=status,
            metadata=metadata or {},
        )
        self._steps.append(step)
        return self

    def build(self) -> Trace:
        """Build the final trace.

        Returns:
            An immutable Trace with all recorded steps.
        """
        return Trace(
            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
            request_id=self.request_id,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            evaluation_id=self.evaluation_id,
            verification_id=self.verification_id,
            autonomous_iteration_id=self.autonomous_iteration_id,
            steps=tuple(self._steps),
            started_at=self._started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def create_trace(
    request_id: str = "",
    workflow_id: str = "",
    execution_id: str = "",
    evaluation_id: str = "",
    verification_id: str = "",
    autonomous_iteration_id: str = "",
) -> Trace:
    """Create a complete trace with all identifiers.

    This is a convenience function for creating traces with all
    identifiers set at once.

    Args:
        request_id: Request ID from the gateway.
        workflow_id: Workflow identifier.
        execution_id: Execution identifier.
        evaluation_id: Evaluation identifier.
        verification_id: Verification identifier.
        autonomous_iteration_id: Autonomous iteration identifier.

    Returns:
        A Trace with all identifiers set but no steps.
    """
    return Trace(
        trace_id=f"trace-{uuid.uuid4().hex[:8]}",
        request_id=request_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        evaluation_id=evaluation_id,
        verification_id=verification_id,
        autonomous_iteration_id=autonomous_iteration_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


def add_trace_step(
    trace: Trace,
    component: str,
    action: str,
    duration_ms: float = 0.0,
    status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> Trace:
    """Add a step to an existing trace.

    Returns a new Trace with the additional step. The original
    trace is unchanged (immutability).

    Args:
        trace: The existing trace.
        component: Component name.
        action: Action performed.
        duration_ms: Duration in milliseconds.
        status: Step status.
        metadata: Additional step metadata.

    Returns:
        A new Trace with the additional step.
    """
    step_id = f"step-{len(trace.steps) + 1}"
    step = TraceStep(
        step_id=step_id,
        component=component,
        action=action,
        duration_ms=duration_ms,
        status=status,
        metadata=metadata or {},
    )
    return Trace(
        trace_id=trace.trace_id,
        request_id=trace.request_id,
        workflow_id=trace.workflow_id,
        execution_id=trace.execution_id,
        evaluation_id=trace.evaluation_id,
        verification_id=trace.verification_id,
        autonomous_iteration_id=trace.autonomous_iteration_id,
        steps=trace.steps + (step,),
        started_at=trace.started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


def complete_trace(trace: Trace) -> Trace:
    """Mark a trace as completed with the current timestamp.

    Returns a new Trace with the completed_at timestamp set.

    Args:
        trace: The trace to complete.

    Returns:
        A new Trace with completed_at set.
    """
    return Trace(
        trace_id=trace.trace_id,
        request_id=trace.request_id,
        workflow_id=trace.workflow_id,
        execution_id=trace.execution_id,
        evaluation_id=trace.evaluation_id,
        verification_id=trace.verification_id,
        autonomous_iteration_id=trace.autonomous_iteration_id,
        steps=trace.steps,
        started_at=trace.started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )