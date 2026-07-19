"""Review Pull Request Task.

Orchestrates repository search for a pull request review.

Architecture
------------

TaskRequest
    ↓
ReviewPullRequestTask
    ↓
RepositoryIndex + TaskRequest
    ↓
TaskPlan

The task identifies affected symbols and modules from the request,
then produces a TaskPlan that describes the review scope.

Public API
----------

.. code-block:: python

    from packages.tasks.review_pull_request import ReviewPullRequestTask

    task = ReviewPullRequestTask()
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

__all__ = [
    "ReviewPullRequestTask",
]


class ReviewPullRequestTask(Task):
    """Repository search task for pull request review.

    Responsibilities:
        - Identify affected symbols from changed_symbols in request options.
        - Identify affected modules from changed_files in request options.
        - Produce a TaskPlan describing the review scope.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "review-pull-request"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "pull-request-review"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for repository search.

        Extracts affected symbols and modules from the request options,
        validates them against the repository index, and produces a
        TaskPlan describing the review scope.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with review scope steps.
        """
        # Extract changed symbols and files from request options
        changed_symbols: list[str] = []
        changed_files: list[str] = []

        if hasattr(request, "options") and request.options:
            options = request.options
            symbols = options.get("changed_symbols", [])
            files = options.get("changed_files", [])
            if isinstance(symbols, list):
                changed_symbols = [str(s) for s in symbols]
            if isinstance(files, list):
                changed_files = [str(f) for f in files]

        # Validate affected symbols against the repository index
        affected_symbols: list[str] = []
        for sym_name in changed_symbols:
            found = repository_index.find(sym_name)
            if found:
                affected_symbols.append(sym_name)

        # Validate affected files against the repository index
        affected_modules: list[str] = []
        for file_path in changed_files:
            module = repository_index.find_module(file_path)
            if module is not None:
                affected_modules.append(file_path)

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Identify affected symbols
        steps.append(
            TaskStep(
                order=0,
                title="Identify affected symbols",
                description=(
                    f"Identified {len(affected_symbols)} affected symbols "
                    f"from {len(changed_symbols)} changed symbols in the repository."
                ),
                required_symbols=tuple(affected_symbols),
                required_modules=(),
            )
        )

        # Step 1: Identify affected modules
        steps.append(
            TaskStep(
                order=1,
                title="Identify affected modules",
                description=(
                    f"Identified {len(affected_modules)} affected modules "
                    f"from {len(changed_files)} changed files in the repository."
                ),
                required_symbols=(),
                required_modules=tuple(affected_modules),
            )
        )

        # Step 2: Build review scope summary
        steps.append(
            TaskStep(
                order=2,
                title="Build review scope summary",
                description=(
                    f"PR: {request.query}. "
                    f"Affected symbols: {len(affected_symbols)}. "
                    f"Affected modules: {len(affected_modules)}. "
                    f"Total changed files: {len(changed_files)}."
                ),
                required_symbols=tuple(affected_symbols),
                required_modules=tuple(affected_modules),
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
            estimated_tokens=len(affected_symbols) * 50
            + len(affected_modules) * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if affected_symbols or affected_modules
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
