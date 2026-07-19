"""Implement Feature Workflow.

Architecture Review -> Impact Analysis -> Implementation Task

This workflow implements a new feature by:
1. Reviewing the architecture
2. Analyzing impact
3. Creating an implementation task

Public API
----------

.. code-block:: python

    from packages.workflows.workflows.implement_feature import (
        ImplementFeatureWorkflow,
    )

    workflow = ImplementFeatureWorkflow()
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


class ImplementFeatureWorkflow(Workflow):
    """Implement Feature workflow.

    Tasks:
        Architecture Review -> Impact Analysis -> Implementation

    DAG:
        architecture-review
            down
        impact-analysis
            down
        implementation-task
    """

    @property
    def name(self) -> str:
        return "implement-feature"

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return (
            WorkflowNode(
                node_id="architecture-review",
                task=self._get_architecture_review_task(),
                depends_on=(),
            ),
            WorkflowNode(
                node_id="impact-analysis",
                task=self._get_impact_analysis_task(),
                depends_on=("architecture-review",),
            ),
            WorkflowNode(
                node_id="implementation-task",
                task=self._get_implementation_task(),
                depends_on=("impact-analysis",),
            ),
        )

    def _get_architecture_review_task(self) -> type:
        """Get the Architecture Review task class.

        Returns:
            The ArchitectureReviewTask class.
        """
        from packages.tasks.architecture_review import ArchitectureReviewTask

        return ArchitectureReviewTask

    def _get_impact_analysis_task(self) -> type:
        """Get the Impact Analysis task class.

        Returns:
            The ImpactAnalysisTask class.
        """
        from packages.tasks.impact_analysis import ImpactAnalysisTask

        return ImpactAnalysisTask

    def _get_implementation_task(self) -> type:
        """Get the Implementation task class.

        Returns:
            The ImplementationTask class.
        """
        from packages.tasks.implementation import ImplementationTask

        return ImplementationTask

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        """Generate a WorkflowPlan for feature implementation.

        Delegates orchestration to the WorkflowEngine.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A WorkflowPlan with architecture review, impact analysis,
            and implementation task plans.
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
