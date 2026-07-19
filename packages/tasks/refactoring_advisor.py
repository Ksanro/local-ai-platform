"""Refactoring Advisor Task.

Orchestrates the RefactoringAdvisor to produce refactoring opportunities.

Architecture
------------

TaskRequest
    ↓
RefactoringAdvisorTask
    ↓
RefactoringAdvisor
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.refactoring_advisor import RefactoringAdvisorTask

    task = RefactoringAdvisorTask()
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


class RefactoringAdvisorTask(Task):
    """Refactoring advisor task.

    Responsibilities:
        - Invoke RefactoringAdvisor.
        - Collect refactoring opportunities.
        - Produce a TaskPlan describing refactoring opportunities.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "refactoring-advisor"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "refactoring-advisor"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for refactoring advisor.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with refactoring opportunity steps.
        """
        from packages.advisors.refactoring.advisor import RefactoringAdvisor

        advisor = RefactoringAdvisor()
        report = advisor.analyze(repository_index=repository_index)

        # Collect refactoring opportunities
        opportunities = report.opportunities
        opportunity_count = len(opportunities)

        # Collect affected modules from opportunities
        affected_modules_set: set[str] = set()
        affected_symbols_set: set[str] = set()
        for opp in opportunities:
            affected_modules_set.update(opp.affected_modules)
            affected_symbols_set.update(opp.affected_symbols)

        affected_modules = tuple(sorted(affected_modules_set))
        affected_symbols = tuple(sorted(affected_symbols_set))

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Summarize refactoring opportunities
        steps.append(
            TaskStep(
                order=0,
                title="Summarize refactoring opportunities",
                description=(
                    f"Found {opportunity_count} refactoring opportunities."
                ),
                required_symbols=affected_symbols,
                required_modules=affected_modules,
            )
        )

        # Step 1: List opportunities by category
        categories: set[str] = set()
        for opp in opportunities:
            categories.add(opp.category.value)
        steps.append(
            TaskStep(
                order=1,
                title="List opportunities by category",
                description=(
                    f"Opportunities in categories: {', '.join(sorted(categories))}."
                ),
                required_symbols=affected_symbols,
                required_modules=affected_modules,
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
            estimated_tokens=opportunity_count * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if opportunity_count > 0
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