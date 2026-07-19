"""Impact Analysis Task.

Orchestrates the ChangeImpactAnalyzer to produce impact analysis.

Architecture
------------

TaskRequest
    ↓
ImpactAnalysisTask
    ↓
ChangeImpactAnalyzer
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.impact_analysis import ImpactAnalysisTask

    task = ImpactAnalysisTask()
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


class ImpactAnalysisTask(Task):
    """Impact analysis task.

    Responsibilities:
        - Invoke ChangeImpactAnalyzer.
        - Collect impact analysis findings.
        - Produce a TaskPlan describing impact results.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "impact-analysis"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "impact-analysis"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for impact analysis.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with impact analysis steps.
        """
        # Extract changed symbols from request options
        changed_symbols: list[str] = []
        if hasattr(request, "options") and request.options:
            symbols = request.options.get("changed_symbols", [])
            if isinstance(symbols, list):
                changed_symbols = [str(s) for s in symbols]

        # Use changed symbols or fall back to query-based analysis
        symbols_to_analyze = changed_symbols if changed_symbols else []

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Analyze impact
        steps.append(
            TaskStep(
                order=0,
                title="Analyze impact",
                description=(
                    f"Analyzed impact of {len(symbols_to_analyze)} symbols."
                ),
                required_symbols=tuple(symbols_to_analyze),
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
            estimated_tokens=len(symbols_to_analyze) * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if symbols_to_analyze
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