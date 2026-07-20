"""Execution Engine runtime models.

These models represent the runtime state of workflow execution.
They are separate from planning models (models.py) which handle
WorkflowPlan -> ExecutionPlan transformation.

Architecture
------------

WorkflowPlan  -->  ExecutionPlanner  -->  ExecutionPlan
WorkflowPlan  -->  ExecutionEngine  -->  ExecutionReport

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- Adapters are stateless.

Public API
----------

.. code-block:: python

    from packages.execution.runtime_models import (
        ExecutionStatus,
        ExecutionStepResult,
        ExecutionSession,
        ExecutionReport,
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "ExecutionReport",
    "ExecutionSession",
    "ExecutionStepResult",
    "ExecutionStatus",
]


# ---------------------------------------------------------------------------
# ExecutionStatus
# ---------------------------------------------------------------------------


class ExecutionStatus(str, Enum):
    """Status of an execution step or session.

    Attributes:
        PENDING: Step/session has not started yet.
        RUNNING: Step/session is currently executing.
        COMPLETED: Step/session finished successfully.
        FAILED: Step/session failed during execution.
        CANCELLED: Step/session was cancelled.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# ExecutionStepResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionStepResult:
    """Immutable result of executing a single workflow step.

    Attributes:
        step_name: The workflow step name.
        status: Execution status of this step.
        started_at: ISO format timestamp when execution started.
        finished_at: ISO format timestamp when execution finished.
        duration_ms: Duration of execution in milliseconds.
        output_summary: Human-readable summary of the step output.
        metadata: Additional metadata about the step execution.
    """

    step_name: str
    status: ExecutionStatus
    started_at: str
    finished_at: str
    duration_ms: int
    output_summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ExecutionSession
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """Immutable record of a complete workflow execution session.

    Attributes:
        session_id: Unique identifier for this execution session.
        workflow_name: The workflow name that was executed.
        execution_status: Overall status of the execution session.
        started_at: ISO format timestamp when execution started.
        completed_at: ISO format timestamp when execution completed.
        executed_steps: Tuple of step results in execution order.
        metadata: Additional metadata about the session.
    """

    session_id: str
    workflow_name: str
    execution_status: ExecutionStatus
    started_at: str
    completed_at: str
    executed_steps: tuple[ExecutionStepResult, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ExecutionReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Immutable report of a workflow execution.

    Attributes:
        workflow_name: The workflow name.
        execution_status: Overall execution status.
        total_duration_ms: Total execution duration in milliseconds.
        step_results: Tuple of step results in deterministic order.
        adapter_name: Name of the adapter used for execution.
        success: Whether the entire execution succeeded.
        failures: Tuple of failure descriptions (if any).
    """

    workflow_name: str
    execution_status: ExecutionStatus
    total_duration_ms: int
    step_results: tuple[ExecutionStepResult, ...]
    adapter_name: str
    success: bool
    failures: tuple[str, ...] = ()
