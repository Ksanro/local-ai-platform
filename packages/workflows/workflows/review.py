"""Review Workflow.

Architecture Review -> Diagnostics -> Review Task

This workflow performs a code review by:
1. Reviewing the architecture
2. Running diagnostics
3. Creating a review task

Public API
----------

.. code-block:: python

    from packages.workflows.workflows.review import ReviewWorkflow

    workflow = ReviewWorkflow()
    plan = workflow.plan(repository_index, request)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.workflows.base import Workflow
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowNode,
    WorkflowPlan,
)

if TYPE_CHECKING:
    from packages.tasks.models import TaskPlan, TaskRequest  # noqa: F401


class ReviewWorkflow(Workflow):
    """Review workflow.

    Tasks:
        Architecture Review -> Diagnostics -> Review

    DAG:
        architecture-review
            down
        diagnostics
            down
        review-task
    """

    @property
    def name(self) -> str:
        return "review"

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return (
            WorkflowNode(
                node_id="architecture-review",
                task=self._get_architecture_review_task(),
                depends_on=(),
            ),
            WorkflowNode(
                node_id="diagnostics",
                task=self._get_diagnostics_task(),
                depends_on=("architecture-review",),
            ),
            WorkflowNode(
                node_id="review-task",
                task=self._get_review_task(),
                depends_on=("diagnostics",),
            ),
        )

    def _get_architecture_review_task(self) -> type:
        """Get the Architecture Review task class.

        Returns:
            The ArchitectureReviewTask class.
        """
        from packages.tasks.architecture_review import ArchitectureReviewTask

        return ArchitectureReviewTask

    def _get_diagnostics_task(self) -> type:
        """Get the Diagnostics task class.

        Returns:
            The DiagnosticsTask class.
        """
        from packages.tasks.diagnostics import DiagnosticsTask

        return DiagnosticsTask

    def _get_review_task(self) -> type:
        """Get the Review task class.

        Returns:
            The ReviewTask class.
        """
        from packages.tasks.review import ReviewTask

        return ReviewTask

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        """Generate a WorkflowPlan for code review.

        Delegates orchestration to the WorkflowEngine.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A WorkflowPlan with architecture review, diagnostics,
            and review task plans.
        """
        from packages.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        return engine.generate_plan(
            workflow=self,
            repository_index=repository_index,
            request=request,
        )

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        """Estimate workflow execution metrics.

        Delegates orchestration to the WorkflowEngine.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            Aggregated WorkflowMetrics.
        """
        plan = self._do_plan(repository_index, request)
        return plan.metrics
