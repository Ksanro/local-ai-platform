"""Diagnostics Task.

Orchestrates the DiagnosticsEngine to produce repository diagnostics.

Architecture
------------

TaskRequest
    ↓
DiagnosticsTask
    ↓
DiagnosticsEngine
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.diagnostics import DiagnosticsTask

    task = DiagnosticsTask()
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


class DiagnosticsTask(Task):
    """Diagnostics task.

    Responsibilities:
        - Invoke DiagnosticsEngine.
        - Collect diagnostics findings.
        - Produce a TaskPlan describing diagnostics results.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "diagnostics"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "diagnostics"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for diagnostics.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with diagnostics steps.
        """
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        diagnostics = engine.analyze(repository_index=repository_index)

        # Collect diagnostics information
        dead_symbols = diagnostics.dead_symbols
        dependency_cycles = diagnostics.dependency_cycles
        orphan_modules = diagnostics.orphan_modules
        large_modules = diagnostics.large_modules

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Check dead symbols
        steps.append(
            TaskStep(
                order=0,
                title="Check dead symbols",
                description=(
                    f"Found {len(dead_symbols)} dead symbols."
                ),
                required_symbols=(),
                required_modules=(),
            )
        )

        # Step 1: Check dependency cycles
        steps.append(
            TaskStep(
                order=1,
                title="Check dependency cycles",
                description=(
                    f"Found {len(dependency_cycles)} dependency cycles."
                ),
                required_symbols=(),
                required_modules=(),
            )
        )

        # Step 2: Check orphan modules
        steps.append(
            TaskStep(
                order=2,
                title="Check orphan modules",
                description=(
                    f"Found {len(orphan_modules)} orphan modules."
                ),
                required_symbols=(),
                required_modules=(),
            )
        )

        # Step 3: Check large modules
        steps.append(
            TaskStep(
                order=3,
                title="Check large modules",
                description=(
                    f"Found {len(large_modules)} large modules."
                ),
                required_symbols=(),
                required_modules=(),
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
        total_findings = (
            len(dead_symbols)
            + len(dependency_cycles)
            + len(orphan_modules)
            + len(large_modules)
        )
        metrics = TaskMetrics(
            estimated_tokens=total_findings * 50,
            estimated_complexity=TaskComplexity.MEDIUM
            if total_findings > 0
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