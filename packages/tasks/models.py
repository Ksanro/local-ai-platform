"""Task Framework models.

Defines the immutable dataclasses that represent executable development
workflows.  These models are the stable public contract for the Task
framework output.

Architecture
------------

TaskRequest  ──►  Task  ──►  TaskPlan
     │                   │
     ▼                   ▼
Repository         Capability
Index

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.
- No AI-generated content.

Public API
----------

.. code-block:: python

    from packages.tasks.models import (
        TaskComplexity,
        TaskConstraint,
        TaskMetrics,
        TaskPlan,
        TaskRequest,
        TaskStep,
    )

    request = TaskRequest(
        query="Refactor ProviderFactory",
        repository_root=".",
    )

    plan = task.plan(
        repository_index=index,
        request=request,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.capabilities.models import CapabilityResult  # noqa: F401

__all__ = [
    "TaskComplexity",
    "TaskConstraint",
    "TaskMetrics",
    "TaskPlan",
    "TaskRequest",
    "TaskStep",
]


# ---------------------------------------------------------------------------
# TaskComplexity
# ---------------------------------------------------------------------------


class TaskComplexity(str, Enum):
    """Estimated complexity of a task execution.

    Attributes:
        LOW: Simple task, minimal effort.
        MEDIUM: Moderate task, requires multiple steps.
        HIGH: Complex task, requires significant effort.
        VERY_HIGH: Very complex task, requires extensive effort.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


# ---------------------------------------------------------------------------
# TaskRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskRequest:
    """Input request for a task execution.

    Attributes:
        query: The user's natural language query.
        user_messages: Optional list of user messages providing context.
        repository_root: Path to the repository root directory.
        constraints: Additional constraint identifiers.
        options: Task-specific configuration options.
    """

    query: str
    repository_root: str = "."
    user_messages: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    options: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TaskConstraint
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskConstraint:
    """A constraint that applies to task execution.

    Attributes:
        type: The constraint type identifier.
        description: Human-readable description of the constraint.
    """

    type: str
    description: str


# ---------------------------------------------------------------------------
# TaskMetrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskMetrics:
    """Estimated metrics for a task execution.

    Attributes:
        estimated_tokens: Estimated token count for the context.
        estimated_complexity: Complexity level of the task.
    """

    estimated_tokens: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW


# ---------------------------------------------------------------------------
# TaskStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskStep:
    """An immutable step in a task execution plan.

    Attributes:
        order: Execution order (0-based, deterministic).
        title: Human-readable step title.
        description: Detailed step description.
        required_symbols: Symbols required for this step.
        required_modules: Modules required for this step.
    """

    order: int
    title: str
    description: str
    required_symbols: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# TaskPlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Complete execution plan for a task.

    Attributes:
        task_name: Unique task identifier.
        capability: The capability consumed by this task.
        context_package: The assembled context package.
        steps: Execution steps in deterministic order.
        constraints: Constraints applicable to this task.
        metrics: Estimated execution metrics.
    """

    task_name: str
    capability: str
    context_package: object  # ContextPackage - avoid circular import
    steps: tuple[TaskStep, ...] = ()
    constraints: tuple[TaskConstraint, ...] = ()
    metrics: TaskMetrics = field(default_factory=TaskMetrics)
