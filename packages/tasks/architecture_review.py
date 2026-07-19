"""Architecture Review Task.

Orchestrates the ArchitectureAnalyzer to produce an architecture review.

Architecture
------------

TaskRequest
    ↓
ArchitectureReviewTask
    ↓
ArchitectureAnalyzer
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.architecture_review import ArchitectureReviewTask

    task = ArchitectureReviewTask()
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


class ArchitectureReviewTask(Task):
    """Architecture review task.

    Responsibilities:
        - Invoke ArchitectureAnalyzer.
        - Collect architecture findings.
        - Produce a TaskPlan describing the architecture.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "architecture-review"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "architecture-review"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for architecture review.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with architecture review steps.
        """
        from packages.architecture.analyzer import ArchitectureAnalyzer

        analyzer = ArchitectureAnalyzer()
        review = analyzer.analyze(repository_index=repository_index)

        # Collect module information
        modules = review.modules
        module_names = tuple(m.module for m in modules) if modules else ()

        # Collect dependency cycles
        dependency_cycles = review.dependency_cycles

        # Collect layering violations
        layering_violations = review.layering_violations

        # Collect orphan modules
        orphan_modules = review.orphan_modules

        # Collect high coupling modules
        high_coupling_modules = review.high_coupling_modules

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Analyze modules
        steps.append(
            TaskStep(
                order=0,
                title="Analyze modules",
                description=(
                    f"Analyzed {len(module_names)} modules in the repository."
                ),
                required_symbols=(),
                required_modules=module_names,
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

        # Step 2: Check layering violations
        steps.append(
            TaskStep(
                order=2,
                title="Check layering violations",
                description=(
                    f"Found {len(layering_violations)} layering violations."
                ),
                required_symbols=(),
                required_modules=(),
            )
        )

        # Step 3: Check orphan modules
        steps.append(
            TaskStep(
                order=3,
                title="Check orphan modules",
                description=(
                    f"Found {len(orphan_modules)} orphan modules."
                ),
                required_symbols=(),
                required_modules=(),
            )
        )

        # Step 4: Check high coupling modules
        steps.append(
            TaskStep(
                order=4,
                title="Check high coupling modules",
                description=(
                    f"Found {len(high_coupling_modules)} high coupling modules."
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
        metrics = TaskMetrics(
            estimated_tokens=len(module_names) * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if module_names
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