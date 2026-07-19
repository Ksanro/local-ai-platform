"""Context Builder Task.

Orchestrates the ContextBuilder to produce context for the review.

Architecture
------------

TaskRequest
    ↓
ContextBuilderTask
    ↓
ContextBuilder
    ↓
TaskPlan

Public API
----------

.. code-block:: python

    from packages.tasks.context_builder import ContextBuilderTask

    task = ContextBuilderTask()
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


class ContextBuilderTask(Task):
    """Context builder task.

    Responsibilities:
        - Invoke ContextBuilder.
        - Collect context findings.
        - Produce a TaskPlan describing context results.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "context-builder"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "context-builder"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for context builder.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with context builder steps.
        """
        from packages.context.builder import ContextBuilder
        from packages.context.models import ContextQuery

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

        # Build query text from PR information
        query_parts: list[str] = []
        if pr_title:
            query_parts.append(pr_title)
        if pr_description:
            query_parts.append(pr_description)
        if changed_symbols:
            query_parts.extend(changed_symbols)
        if changed_files:
            query_parts.extend(changed_files)

        query_text = " ".join(query_parts) if query_parts else request.query

        # Build context query
        context_query = ContextQuery(
            text=query_text,
            max_symbols=50,
            max_modules=10,
            max_tokens=10000,
            relationship_expansion=False,
        )

        # Build context
        builder = ContextBuilder(index=repository_index)
        result = builder.build(query=context_query)

        # Collect context information
        candidates = result.candidates
        selected_modules = result.selected_modules
        candidate_count = len(candidates)
        module_count = len(selected_modules)

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Build context from candidates
        steps.append(
            TaskStep(
                order=0,
                title="Build context from candidates",
                description=(
                    f"Built context from {candidate_count} candidates "
                    f"across {module_count} modules."
                ),
                required_symbols=tuple(c.qualified_name for c in candidates),
                required_modules=tuple(selected_modules),
            )
        )

        # Step 1: Summarize context
        steps.append(
            TaskStep(
                order=1,
                title="Summarize context",
                description=(
                    f"Context summary: {candidate_count} candidates, "
                    f"{module_count} modules."
                ),
                required_symbols=tuple(c.qualified_name for c in candidates),
                required_modules=tuple(selected_modules),
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
            estimated_tokens=candidate_count * 50,
            estimated_complexity=TaskComplexity.MEDIUM
            if candidate_count > 0
            else TaskComplexity.LOW,
        )

        return TaskPlan(
            task_name=self.name,
            capability=self.capability,
            context_package=result,
            steps=tuple(steps),
            constraints=constraints,
            metrics=metrics,
        )