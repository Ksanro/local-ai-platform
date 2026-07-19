"""Bug Investigation Workflow.

Repository Search -> Architecture Review / Diagnostics / Impact Analysis
    -> Cross Reference Engine -> Context Builder -> WorkflowPlan

This workflow investigates a bug by:
1. Searching the repository for affected symbols and modules
2. Reviewing the architecture
3. Running diagnostics
4. Analyzing impact
5. Cross-referencing findings
6. Building context
7. Producing a deterministic WorkflowPlan

Public API
----------

.. code-block:: python

    from packages.workflows.workflows.bug_investigation import (
        BugInvestigationWorkflow,
    )

    workflow = BugInvestigationWorkflow()
    plan = workflow.plan(repository_index, request)

DAG
---

    repository-search
        /       |       \\
       v        v        v
    architecture-review   diagnostics   impact-analysis
        \\         |         /
         v        v        v
       cross-reference
                |
                v
          context-builder
                |
                v
           WorkflowPlan

Constraints
-----------

- Workflows are immutable (nodes tuple is fixed).
- Workflows are stateless (no instance attributes).
- Workflows orchestrate existing public APIs only.
- Workflows must not access providers directly, parse repositories,
  implement ranking, planning, or serialization.
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


class BugInvestigationWorkflow(Workflow):
    """Bug investigation workflow.

    DAG:
        repository-search
            /       |       \\
           v        v        v
        architecture-review   diagnostics   impact-analysis
            \\         |         /
             v        v        v
            cross-reference
                    |
                    v
               context-builder
                    |
                    v
               WorkflowPlan
    """

    @property
    def name(self) -> str:
        return "bug-investigation"

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return (
            # Root node: repository search
            WorkflowNode(
                node_id="repository-search",
                task=self._get_repository_search_task(),
                depends_on=(),
            ),
            # Parallel branches: architecture review, diagnostics, impact analysis
            WorkflowNode(
                node_id="architecture-review",
                task=self._get_architecture_review_task(),
                depends_on=("repository-search",),
            ),
            WorkflowNode(
                node_id="diagnostics",
                task=self._get_diagnostics_task(),
                depends_on=("repository-search",),
            ),
            WorkflowNode(
                node_id="impact-analysis",
                task=self._get_impact_analysis_task(),
                depends_on=("repository-search",),
            ),
            # Convergence: cross-reference engine
            WorkflowNode(
                node_id="cross-reference",
                task=self._get_cross_reference_task(),
                depends_on=(
                    "architecture-review",
                    "diagnostics",
                    "impact-analysis",
                ),
            ),
            # Context builder (final step)
            WorkflowNode(
                node_id="context-builder",
                task=self._get_context_builder_task(),
                depends_on=("cross-reference",),
            ),
        )

    def _get_repository_search_task(self) -> type:
        """Get the Repository Search task class.

        Returns:
            The InvestigateBugTask class.
        """
        from packages.tasks.investigate_bug import InvestigateBugTask

        return InvestigateBugTask

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

    def _get_impact_analysis_task(self) -> type:
        """Get the Impact Analysis task class.

        Returns:
            The ImpactAnalysisTask class.
        """
        from packages.tasks.impact_analysis import ImpactAnalysisTask

        return ImpactAnalysisTask

    def _get_cross_reference_task(self) -> type:
        """Get the Cross Reference task class.

        Returns:
            The ReviewPullRequestTask class (used as convergence node).
        """
        from packages.tasks.review_pull_request import ReviewPullRequestTask

        return ReviewPullRequestTask

    def _get_context_builder_task(self) -> type:
        """Get the Context Builder task class.

        Returns:
            The ContextBuilderTask class.
        """
        from packages.tasks.context_builder import ContextBuilderTask

        return ContextBuilderTask

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        """Generate a WorkflowPlan for bug investigation.

        Delegates orchestration to the WorkflowEngine.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A WorkflowPlan with repository search, architecture review,
            diagnostics, impact analysis, cross-reference, and context
            builder plans.
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
