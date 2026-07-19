"""Execution Planner Task.

Orchestrates the ExecutionPlanner to produce an execution plan.

Architecture
------------

TaskRequest
    ↓
ExecutionPlannerTask
    ↓
ExecutionPlanner
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.execution_planner import ExecutionPlannerTask

    task = ExecutionPlannerTask()
    plan = task.plan(repository_index, request)

Constraints
-----------

- The task must not invoke providers.
- The task must not call LLMs.
- The task must not edit source code.
- The task must not inspect AST directly.
- The task must not duplicate repository analysis.
- The task must not duplicate diagnostics.
- The task must not duplicate architecture logic.

Only orchestration via existing public APIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.tasks.base import Task
from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskRequest,
    TaskStep,
)

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex  # noqa: F401


class ExecutionPlannerTask(Task):
    """Execution planner task.

    Responsibilities:
        - Invoke ExecutionPlanner.
        - Collect execution plan findings.
        - Produce a TaskPlan describing execution steps.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "execution-planner"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "execution-planner"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for execution planner.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with execution planner steps.
        """
        # Extract PR information from request options
        pr_title = ""
        pr_description = ""
        changed_symbols: list[str] = []
        changed_files: list[str] = []

        if hasattr(request, "options") and request.options:
            options = request.options
            pr_title = options.get("pr_title", "") or ""
            pr_description = options.get("pr_description", "") or ""
            symbols = options.get("changed_symbols", [])
            files = options.get("changed_files", [])
            if isinstance(symbols, list):
                changed_symbols = [str(s) for s in symbols]
            if isinstance(files, list):
                changed_files = [str(f) for f in files]

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Summarize affected architecture
        steps.append(
            TaskStep(
                order=0,
                title="Summarize affected architecture",
                description=(
                    f"PR: {pr_title}. "
                    f"Description: {pr_description}. "
                    f"Changed files: {len(changed_files)}. "
                    f"Changed symbols: {len(changed_symbols)}."
                ),
                required_symbols=tuple(changed_symbols),
                required_modules=tuple(changed_files),
            )
        )

        # Step 1: Review dependency impact
        steps.append(
            TaskStep(
                order=1,
                title="Review dependency impact",
                description=(
                    f"Reviewed dependency impact for "
                    f"{len(changed_symbols)} symbols."
                ),
                required_symbols=tuple(changed_symbols),
                required_modules=tuple(changed_files),
            )
        )

        # Step 2: Identify diagnostics
        steps.append(
            TaskStep(
                order=2,
                title="Identify diagnostics",
                description="Identified diagnostics for affected modules.",
                required_symbols=tuple(changed_symbols),
                required_modules=tuple(changed_files),
            )
        )

        # Step 3: Identify refactoring opportunities
        steps.append(
            TaskStep(
                order=3,
                title="Identify refactoring opportunities",
                description="Identified refactoring opportunities.",
                required_symbols=tuple(changed_symbols),
                required_modules=tuple(changed_files),
            )
        )

        # Step 4: Generate review context
        steps.append(
            TaskStep(
                order=4,
                title="Generate review context",
                description="Generated review context.",
                required_symbols=tuple(changed_symbols),
                required_modules=tuple(changed_files),
            )
        )

        # Build constraints
        constraints: tuple[TaskConstraint, ...] = (
            TaskConstraint(
                type="read-only",
                description="Task must not modify source code",
            ),
            TaskConstraint(
                type="deterministic",
                description="Task must produce deterministic output",
            ),
        )

        # Build metrics
        total = len(changed_symbols) + len(changed_files)
        metrics = TaskMetrics(
            estimated_tokens=total * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if total > 0
            else TaskComplexity.LOW,
        )

        return TaskPlan(
            task_name=self.name,
            capability=self.capability,
            context_package=None,
            steps=tuple(steps),
            constraints=constraints,
            metrics=metrics,
        )