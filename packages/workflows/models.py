"""Workflow Engine models.

Defines the immutable dataclasses that represent workflow orchestration
structures.  These models are the stable public contract for the Workflow
Engine output.

Architecture
------------

WorkflowNode  ──►  WorkflowGraph  ──►  WorkflowPlan
     │
     ▼
    Task

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.
- No repository analysis fields.

Public API
----------

.. code-block:: python

    from packages.workflows.models import (
        WorkflowNode,
        WorkflowPlan,
        WorkflowStep,
        WorkflowMetrics,
    )

    node = WorkflowNode(
        node_id="architecture",
        task=ArchitectureReviewTask,
        depends_on=(),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.tasks.models import TaskComplexity, TaskConstraint

if TYPE_CHECKING:
    from packages.tasks.models import TaskPlan  # noqa: F401

__all__ = [
    "WorkflowMetrics",
    "WorkflowNode",
    "WorkflowPlan",
    "WorkflowStep",
]


# ---------------------------------------------------------------------------
# WorkflowNode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """A node in the workflow DAG.

    Attributes:
        node_id: Unique identifier within the workflow.
        task: The task class to execute.
        depends_on: Tuple of node_ids this node depends on.
        parallelizable: Whether this node can run in parallel (future DSPARK).
    """

    node_id: str
    task: type  # type[Task] - avoid circular import
    depends_on: tuple[str, ...] = ()
    parallelizable: bool = False


# ---------------------------------------------------------------------------
# WorkflowStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """An immutable step in a workflow execution plan.

    Attributes:
        step_id: Unique step identifier.
        order: Execution order (0-based, deterministic).
        workflow_node: References WorkflowNode.node_id.
        task_name: The task name.
        description: Human-readable step description.
    """

    step_id: str
    order: int
    workflow_node: str
    task_name: str
    description: str


# ---------------------------------------------------------------------------
# WorkflowMetrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowMetrics:
    """Estimated metrics for a workflow execution.

    Aggregated from TaskMetrics across all workflow tasks.

    Attributes:
        estimated_tokens: Total estimated token count.
        estimated_duration_ms: Total estimated duration in milliseconds.
        estimated_complexity: Overall complexity level.
    """

    estimated_tokens: int = 0
    estimated_duration_ms: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW


# ---------------------------------------------------------------------------
# WorkflowPlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Complete execution plan for a workflow.

    Attributes:
        workflow_name: The workflow name.
        task_plans: Execution plans for each task.
        workflow_steps: Ordered workflow steps.
        merged_context_package: Merged context from all tasks.
        metrics: Aggregated workflow metrics.
        constraints: Aggregated constraints from all tasks.
    """

    workflow_name: str
    task_plans: tuple  # tuple[TaskPlan, ...] - avoid circular import
    workflow_steps: tuple[WorkflowStep, ...] = ()
    merged_context_package: object = None  # ContextPackage - avoid circular import
    metrics: WorkflowMetrics = field(default_factory=WorkflowMetrics)
    constraints: tuple[TaskConstraint, ...] = ()
