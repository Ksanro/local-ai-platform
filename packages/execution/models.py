"""Execution Planner models.

Defines the immutable dataclasses that represent execution planning
structures consumed by coding agents.  These models are the stable
public contract for the Execution Planner output.

Architecture
------------

WorkflowPlan  -->  ExecutionPlanner  -->  ExecutionPlan
                                              |
                                              v
                                      ProviderSerializer
                                              |
                                              v
                                             LLM

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.
- No repository analysis fields.
- No workflow logic duplication.
- No task logic duplication.

Public API
----------

.. code-block:: python

    from packages.execution.models import (
        ExecutionStep,
        ExecutionMetrics,
        ExecutionPlan,
    )

    step = ExecutionStep(
        order=0,
        title="Analyze repository",
        description="Examine the repository structure",
    )

    plan = ExecutionPlan(
        workflow_name="implement_feature",
        objective="Add new feature",
        execution_steps=(step,),
        context_package=None,
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.tasks.models import TaskComplexity

if TYPE_CHECKING:
    from packages.workflows.models import WorkflowMetrics  # noqa: F401

__all__ = [
    "ExecutionMetrics",
    "ExecutionPlan",
    "ExecutionStep",
]


# ---------------------------------------------------------------------------
# ExecutionStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    """An immutable step in an execution plan.

    Attributes:
        order: Execution order (0-based, deterministic).
        title: Human-readable step title.
        description: Detailed step description.
        required_symbols: Symbols required for this step.
        required_modules: Modules required for this step.
        constraints: Constraints applicable to this step.
    """

    order: int
    title: str
    description: str
    required_symbols: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# ExecutionMetrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionMetrics:
    """Estimated metrics for an execution plan.

    Derived from WorkflowMetrics. No duplicated calculations.

    Attributes:
        estimated_tokens: Total estimated token count.
        estimated_duration_ms: Total estimated duration in milliseconds.
        estimated_complexity: Overall complexity level.
    """

    estimated_tokens: int = 0
    estimated_duration_ms: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW


# ---------------------------------------------------------------------------
# ExecutionPlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Complete execution plan for a workflow.

    Attributes:
        workflow_name: The workflow name.
        objective: The workflow objective.
        execution_steps: Ordered execution steps.
        context_package: The merged context package from the workflow.
        metrics: Aggregated execution metrics.
        constraints: Aggregated constraints from all tasks.
        validation_requirements: Requirements that must be validated.
    """

    workflow_name: str
    objective: str
    execution_steps: tuple[ExecutionStep, ...] = ()
    context_package: object = None  # ContextPackage - avoid circular import
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    constraints: tuple[str, ...] = ()
    validation_requirements: tuple[str, ...] = ()
