"""Refactor Workflow.

Impact Analysis -> Refactoring Advisor -> Refactor Task

This workflow performs refactoring by:
1. Analyzing impact
2. Getting refactoring advice
3. Creating a refactor task

Public API
----------

.. code-block:: python

    from packages.workflows.workflows.refactor import RefactorWorkflow

    workflow = RefactorWorkflow()
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


class RefactorWorkflow(Workflow):
    """Refactor workflow.

    Tasks:
        Impact Analysis -> Refactoring Advisor -> Refactor

    DAG:
        impact-analysis
            down
        refactoring-advisor
            down
        refactor-task
    """

    @property
    def name(self) -> str:
        return "refactor"

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return (
            WorkflowNode(
                node_id="impact-analysis",
                task=self._get_impact_analysis_task(),
                depends_on=(),
            ),
            WorkflowNode(
                node_id="refactoring-advisor",
                task=self._get_refactoring_advisor_task(),
                depends_on=("impact-analysis",),
            ),
            WorkflowNode(
                node_id="refactor-task",
                task=self._get_refactor_task(),
                depends_on=("refactoring-advisor",),
            ),
        )

    def _get_impact_analysis_task(self) -> type:
        """Get the Impact Analysis task class.

        Returns:
            The ImpactAnalysisTask class.
        """
        from packages.tasks.impact_analysis import ImpactAnalysisTask

        return ImpactAnalysisTask

    def _get_refactoring_advisor_task(self) -> type:
        """Get the Refactoring Advisor task class.

        Returns:
            The RefactoringAdvisorTask class.
        """
        from packages.tasks.refactoring_advisor import RefactoringAdvisorTask

        return RefactoringAdvisorTask

    def _get_refactor_task(self) -> type:
        """Get the Refactor task class.

        Returns:
            The RefactorTask class.
        """
        from packages.tasks.refactor import RefactorTask

        return RefactorTask

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        """Generate a WorkflowPlan for refactoring.

        Delegates orchestration to the WorkflowEngine.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A WorkflowPlan with impact analysis, refactoring advisor,
            and refactor task plans.
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
