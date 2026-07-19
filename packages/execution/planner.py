"""ExecutionPlanner implementation.

Transforms a WorkflowPlan into a deterministic ExecutionPlan
consumable by coding agents.

Architecture
------------

WorkflowPlan  -->  ExecutionPlanner  -->  ExecutionPlan
                                              |
                                              v
                                      ProviderSerializer
                                              |
                                              v
                                             LLM

Constraints
-----------

- Consumes only public Workflow APIs.
- Never performs repository analysis.
- Never invokes providers.
- Never edits source code.
- Never duplicates Workflow or Task logic.

Public API
----------

.. code-block:: python

    from packages.execution.planner import ExecutionPlanner
    from packages.workflows.models import WorkflowPlan

    workflow_plan = WorkflowPlan(
        workflow_name="implement_feature",
        task_plans=(),
    )

    execution_plan = ExecutionPlanner.plan(workflow_plan)

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.execution.models import ExecutionMetrics, ExecutionPlan, ExecutionStep
from packages.tasks.models import TaskComplexity, TaskPlan

if TYPE_CHECKING:
    from packages.workflows.models import WorkflowPlan  # noqa: F401


class ExecutionPlanner:
    """Converts a WorkflowPlan into a deterministic ExecutionPlan.

    ExecutionPlanner is a translation layer.  It owns no repository
    intelligence, no workflow logic, and no task logic.

    Responsibilities:
        - Consume WorkflowPlan
        - Flatten TaskPlans into ordered ExecutionSteps
        - Preserve dependency ordering
        - Aggregate constraints
        - Preserve ContextPackage
        - Aggregate metrics
        - Generate validation requirements
    """

    @classmethod
    def plan(cls, workflow_plan: WorkflowPlan) -> ExecutionPlan:
        """Convert a WorkflowPlan into a deterministic ExecutionPlan.

        This is the main entry point for the ExecutionPlanner.  It
        flattens all TaskPlan steps from the workflow into a single
        ordered list of ExecutionSteps.

        Args:
            workflow_plan: The workflow plan to convert.

        Returns:
            An immutable ``ExecutionPlan``.
        """
        execution_steps = cls._flatten_task_plans(workflow_plan)
        constraints = cls._aggregate_constraints(workflow_plan)
        metrics = cls._aggregate_metrics(workflow_plan)
        validation_requirements = cls._generate_validation_requirements(
            workflow_plan,
            execution_steps,
        )

        return ExecutionPlan(
            workflow_name=workflow_plan.workflow_name,
            objective=cls._extract_objective(workflow_plan),
            execution_steps=execution_steps,
            context_package=workflow_plan.merged_context_package,
            metrics=metrics,
            constraints=constraints,
            validation_requirements=validation_requirements,
        )

    @classmethod
    def _flatten_task_plans(cls, workflow_plan: WorkflowPlan) -> tuple[ExecutionStep, ...]:
        """Flatten all TaskPlan steps into ordered ExecutionSteps.

        Iterates through workflow_steps in order, then through each
        TaskPlan.step in order, converting them to ExecutionSteps.

        Args:
            workflow_plan: The workflow plan to flatten.

        Returns:
            A tuple of ExecutionSteps in deterministic order.
        """
        steps: list[ExecutionStep] = []
        order_counter = 0

        for workflow_step in workflow_plan.workflow_steps:
            # Find the corresponding task plan for this workflow step
            task_plan = cls._find_task_plan(workflow_plan, workflow_step.step_id)

            if task_plan is None:
                continue

            # Flatten each step from this task plan
            for task_step in task_plan.steps:
                execution_step = ExecutionStep(
                    order=order_counter,
                    title=task_step.title,
                    description=task_step.description,
                    required_symbols=task_step.required_symbols,
                    required_modules=task_step.required_modules,
                    constraints=(),  # aggregated separately
                )
                steps.append(execution_step)
                order_counter += 1

        return tuple(steps)

    @classmethod
    def _find_task_plan(cls, workflow_plan: WorkflowPlan, step_id: str) -> TaskPlan | None:
        """Find the TaskPlan corresponding to a workflow step.

        Args:
            workflow_plan: The workflow plan.
            step_id: The workflow step ID to find.

        Returns:
            The matching TaskPlan or None.
        """
        result: TaskPlan | None = None

        for task_plan in workflow_plan.task_plans:
            if task_plan.task_name == step_id or step_id in task_plan.task_name:
                result = task_plan
                break

        return result

    @classmethod
    def _aggregate_constraints(
        cls,
        workflow_plan: WorkflowPlan,
    ) -> tuple[str, ...]:
        """Aggregate constraints from all TaskPlans.

        Extracts constraint descriptions from all task plans and
        deduplicates them.

        Args:
            workflow_plan: The workflow plan.

        Returns:
            A tuple of unique constraint strings.
        """
        constraints: set[str] = set()

        # Add workflow-level constraints
        for constraint in workflow_plan.constraints:
            constraints.add(constraint.description)

        # Add constraints from each task plan
        for task_plan in workflow_plan.task_plans:
            for constraint in task_plan.constraints:
                constraints.add(constraint.description)

        return tuple(sorted(constraints))

    @classmethod
    def _aggregate_metrics(cls, workflow_plan: WorkflowPlan) -> ExecutionMetrics:
        """Aggregate metrics from the WorkflowPlan.

        Derives ExecutionMetrics from TaskMetrics:
        - estimated_tokens: sum from all task plans
        - estimated_duration_ms: derived (0, not available in TaskMetrics)
        - estimated_complexity: max complexity across all tasks

        Args:
            workflow_plan: The workflow plan.

        Returns:
            An ExecutionMetrics instance.
        """
        total_tokens = 0
        max_complexity = TaskComplexity.LOW
        max_complexity_value = 0  # Numeric comparison for complexity

        for task_plan in workflow_plan.task_plans:
            total_tokens += task_plan.metrics.estimated_tokens

            # Use numeric comparison for complexity levels
            complexity_map = {
                TaskComplexity.LOW: 0,
                TaskComplexity.MEDIUM: 1,
                TaskComplexity.HIGH: 2,
                TaskComplexity.VERY_HIGH: 3,
            }
            current_value = complexity_map.get(
                task_plan.metrics.estimated_complexity,
                0,
            )
            if current_value > max_complexity_value:
                max_complexity_value = current_value
                max_complexity = task_plan.metrics.estimated_complexity

        return ExecutionMetrics(
            estimated_tokens=total_tokens,
            estimated_duration_ms=0,
            estimated_complexity=max_complexity,
        )

    @classmethod
    def _generate_validation_requirements(
        cls,
        workflow_plan: WorkflowPlan,
        execution_steps: tuple[ExecutionStep, ...],
    ) -> tuple[str, ...]:
        """Generate validation requirements from the workflow plan.

        Creates a list of requirements that must be validated before
        execution, including dependency ordering, context existence,
        and constraint satisfaction.

        Args:
            workflow_plan: The workflow plan.
            execution_steps: The generated execution steps.

        Returns:
            A tuple of validation requirement strings.
        """
        requirements: list[str] = []

        # Dependency ordering requirement
        requirements.append(
            "validate_dependency_ordering",
        )

        # Context existence requirement
        if workflow_plan.merged_context_package is not None:
            requirements.append(
                "validate_context_exists",
            )

        # Constraint satisfaction requirement
        if workflow_plan.constraints:
            requirements.append(
                "validate_constraints_satisfied",
            )

        # Deterministic ordering requirement
        requirements.append(
            "validate_deterministic_ordering",
        )

        return tuple(requirements)

    @staticmethod
    def _extract_objective(workflow_plan: WorkflowPlan) -> str:
        """Extract the objective from the workflow plan.

        Derives a human-readable objective string from the workflow
        plan's name and structure.

        Args:
            workflow_plan: The workflow plan.

        Returns:
            A human-readable objective string.
        """
        return f"Execute workflow: {workflow_plan.workflow_name}"
