"""Workflow Engine.

Orchestrates task planning in deterministic order.

Architecture
------------

WorkflowEngine owns orchestration only.

It never:
- performs repository analysis
- performs planning itself
- invokes providers
- edits source code
- duplicates Task logic
- duplicates Capability logic

WorkflowEngine consumes only public Task APIs.

Public API
----------

.. code-block:: python

    from packages.workflows.engine import WorkflowEngine
    from packages.workflows.models import WorkflowPlan

    engine = WorkflowEngine()

    plan: WorkflowPlan = engine.generate_plan(
        workflow=workflow,
        repository_index=repository_index,
        request=request,
    )

Constraints
-----------

- Purely orchestration-focused.
- No repository intelligence.
- No planning logic.
- No provider execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.context.context_merger import ContextPackageMerger
from packages.workflows.graph import WorkflowGraph
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowPlan,
    WorkflowStep,
)

if TYPE_CHECKING:
    from packages.tasks.models import TaskPlan, TaskRequest  # noqa: F401
    from packages.workflows.base import Workflow  # noqa: F401


class WorkflowEngine:
    """Orchestrates task planning in deterministic order.

    Responsibilities:
        - Validate workflow
        - Generate TaskPlan for each task
        - Invoke tasks in deterministic order
        - Aggregate TaskPlans
        - Merge ContextPackages
        - Aggregate WorkflowMetrics
        - Aggregate TaskConstraints

    The engine never performs repository analysis, planning, or invokes
    providers.  It orchestrates existing Tasks.

    The engine is stateless and thread-safe.
    """

    def __init__(self) -> None:
        """Initialize the workflow engine."""
        self._merger = ContextPackageMerger()

    def generate_plan(
        self,
        workflow: object,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        """Generate a WorkflowPlan for the given workflow.

        Args:
            workflow: The workflow instance to execute.
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A ``WorkflowPlan`` with aggregated task plans.

        The generation process:
            1. Build the workflow DAG.
            2. Validate the DAG.
            3. Topologically sort nodes.
            4. Generate TaskPlan for each node.
            5. Merge ContextPackages.
            6. Aggregate metrics and constraints.
        """
        # Build and validate the workflow graph.
        nodes = workflow.workflow_nodes  # type: ignore[attr-defined]
        graph = WorkflowGraph(nodes)
        graph.validate()

        # Get deterministic execution order.
        ordered_nodes = graph.topological_sort()

        # Generate TaskPlans for each node.
        task_plans: list[object] = []
        workflow_steps: list[WorkflowStep] = []

        for order, node in enumerate(ordered_nodes):
            # Generate TaskPlan by invoking the task.
            task_instance = node.task()  # type: ignore[union-attr]
            task_plan = task_instance.plan(  # type: ignore[union-attr]
                repository_index,
                request,
            )
            task_plans.append(task_plan)

            # Create workflow step.
            step_id = f"step-{node.node_id}"
            step = WorkflowStep(
                step_id=step_id,
                order=order,
                workflow_node=node.node_id,
                task_name=(
                    node.task().name
                    if hasattr(node.task(), "name")
                    else node.task.__name__  # type: ignore[union-attr]
                    if hasattr(node.task, "__name__")
                    else str(node.task)
                ),  # type: ignore[union-attr]
                description=f"Execute {node.node_id}",
            )
            workflow_steps.append(step)

        # Merge ContextPackages.
        context_packages = [
            tp.context_package
            for tp in task_plans
            if hasattr(tp, "context_package") and tp.context_package is not None
        ]

        merged_package = self._merger.merge(context_packages) if context_packages else None

        # Aggregate metrics.
        metrics = self._aggregate_metrics(task_plans)

        # Aggregate constraints.
        constraints = self._aggregate_constraints(task_plans)

        # Get workflow name.
        workflow_name = workflow.name if hasattr(workflow, 'name') else workflow.__class__.__name__  # type: ignore[attr-defined]

        return WorkflowPlan(
            workflow_name=workflow_name,
            task_plans=tuple(task_plans),
            workflow_steps=tuple(workflow_steps),
            merged_context_package=merged_package,
            metrics=metrics,
            constraints=constraints,
        )

    def _aggregate_metrics(
        self,
        task_plans: list[object],
    ) -> WorkflowMetrics:
        """Aggregate metrics from TaskPlans.

        Args:
            task_plans: List of TaskPlan objects.

        Returns:
            Aggregated WorkflowMetrics.
        """
        total_tokens = 0
        total_duration = 0
        max_complexity_order = 0

        complexity_order = {
            "LOW": 0,
            "MEDIUM": 1,
            "HIGH": 2,
            "VERY_HIGH": 3,
        }

        for tp in task_plans:
            if hasattr(tp, "metrics") and tp.metrics is not None:
                metrics = tp.metrics
                if hasattr(metrics, "estimated_tokens"):
                    total_tokens += metrics.estimated_tokens or 0
                if hasattr(metrics, "estimated_duration_ms"):
                    total_duration += metrics.estimated_duration_ms or 0
                if hasattr(metrics, "estimated_complexity"):
                    complexity = metrics.estimated_complexity
                    order = complexity_order.get(
                        complexity.value if hasattr(complexity, 'value') else str(complexity),
                        0,
                    )
                    max_complexity_order = max(max_complexity_order, order)

        # Map back to TaskComplexity.
        complexity_map = {
            0: "LOW",
            1: "MEDIUM",
            2: "HIGH",
            3: "VERY_HIGH",
        }

        from packages.tasks.models import TaskComplexity

        complexity_str = complexity_map.get(max_complexity_order, "LOW")
        try:
            complexity = TaskComplexity(complexity_str)
        except ValueError:
            complexity = TaskComplexity.LOW

        return WorkflowMetrics(
            estimated_tokens=total_tokens,
            estimated_duration_ms=total_duration,
            estimated_complexity=complexity,
        )

    def _aggregate_constraints(
        self,
        task_plans: list[object],
    ) -> tuple[object, ...]:
        """Aggregate constraints from TaskPlans.

        Args:
            task_plans: List of TaskPlan objects.

        Returns:
            Tuple of TaskConstraint objects.
        """
        all_constraints: list[object] = []

        for tp in task_plans:
            if hasattr(tp, "constraints") and tp.constraints:
                all_constraints.extend(tp.constraints)

        # Deduplicate by (type, description).
        seen: set[tuple[str, str]] = set()
        unique_constraints: list[object] = []

        for constraint in all_constraints:
            if hasattr(constraint, "type") and hasattr(constraint, "description"):
                key = (constraint.type, constraint.description)
                if key not in seen:
                    seen.add(key)
                    unique_constraints.append(constraint)

        return tuple(unique_constraints)

    def estimate(
        self,
        workflow: object,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        """Estimate workflow execution metrics.

        Args:
            workflow: The workflow instance to estimate.
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            Aggregated WorkflowMetrics.
        """
        plan = self.generate_plan(workflow, repository_index, request)
        return plan.metrics
