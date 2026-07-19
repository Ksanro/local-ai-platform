"""Tests for the ExecutionPlanner.

Verifies:
- Empty workflow handling
- Step flattening from TaskPlan.steps
- Dependency preservation
- Constraint aggregation
- Metric aggregation
- ContextPackage preservation
- Deterministic planning
"""

from __future__ import annotations

from unittest.mock import MagicMock

from packages.execution.planner import ExecutionPlanner
from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskStep,
)
from packages.workflows.models import WorkflowPlan, WorkflowStep

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _make_workflow_plan(
    workflow_name: str = "test_workflow",
    workflow_steps: tuple[WorkflowStep, ...] = (),
    task_plans: tuple[TaskPlan, ...] = (),
    constraints: tuple[TaskConstraint, ...] = (),
    context_package: object = None,
) -> WorkflowPlan:
    """Helper to create a WorkflowPlan for testing."""
    return WorkflowPlan(
        workflow_name=workflow_name,
        task_plans=task_plans,
        workflow_steps=workflow_steps,
        merged_context_package=context_package,
        constraints=constraints,
    )


def _make_task_plan(
    task_name: str = "test_task",
    steps: tuple[TaskStep, ...] = (),
    constraints: tuple[TaskConstraint, ...] = (),
    metrics: TaskMetrics | None = None,
) -> TaskPlan:
    """Helper to create a TaskPlan for testing."""
    return TaskPlan(
        task_name=task_name,
        capability="test-capability",
        context_package=MagicMock(),
        steps=steps,
        constraints=constraints,
        metrics=metrics or TaskMetrics(
            estimated_tokens=100,
            estimated_complexity=TaskComplexity.LOW,
        ),
    )


def _make_workflow_step(
    step_id: str = "test_task",
    order: int = 0,
    description: str = "Test step",
) -> WorkflowStep:
    """Helper to create a WorkflowStep for testing."""
    return WorkflowStep(
        step_id=step_id,
        order=order,
        workflow_node=step_id,
        task_name="test_task",
        description=description,
    )


# ---------------------------------------------------------------------------
# Test: Empty Workflow
# ---------------------------------------------------------------------------


class TestEmptyWorkflow:
    """Tests for empty workflow handling."""

    def test_empty_workflow_steps(self) -> None:
        """Empty workflow_steps should produce empty execution_steps."""
        workflow_plan = _make_workflow_plan(
            workflow_steps=(),
            task_plans=(),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.execution_steps == ()
        assert execution_plan.workflow_name == "test_workflow"
        assert execution_plan.metrics.estimated_tokens == 0

    def test_empty_task_plans(self) -> None:
        """Workflow with no task_plans should produce empty execution_steps."""
        workflow_step = _make_workflow_step(step_id="missing_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(),  # No matching task plan
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.execution_steps == ()

    def test_task_plan_with_no_steps(self) -> None:
        """TaskPlan with no steps should produce no execution_steps."""
        task_plan = _make_task_plan(steps=())
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.execution_steps == ()


# ---------------------------------------------------------------------------
# Test: Step Flattening
# ---------------------------------------------------------------------------


class TestStepFlattening:
    """Tests for step flattening from TaskPlans."""

    def test_single_step_flattening(self) -> None:
        """Single TaskPlan step should be flattened."""
        task_step = TaskStep(
            order=0,
            title="Analyze",
            description="Analyze the codebase",
        )
        task_plan = _make_task_plan(steps=(task_step,))
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert len(execution_plan.execution_steps) == 1
        assert execution_plan.execution_steps[0].title == "Analyze"
        assert execution_plan.execution_steps[0].description == "Analyze the codebase"
        assert execution_plan.execution_steps[0].order == 0

    def test_multi_step_flattening(self) -> None:
        """Multiple TaskPlan steps should be flattened sequentially."""
        steps = (
            TaskStep(order=0, title="First", description="A"),
            TaskStep(order=1, title="Second", description="B"),
            TaskStep(order=2, title="Third", description="C"),
        )
        task_plan = _make_task_plan(steps=steps)
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert len(execution_plan.execution_steps) == 3
        assert execution_plan.execution_steps[0].order == 0
        assert execution_plan.execution_steps[1].order == 1
        assert execution_plan.execution_steps[2].order == 2

    def test_multi_task_flattening(self) -> None:
        """Multiple TaskPlans should be flattened in workflow order."""
        task_plan_a = _make_task_plan(
            task_name="task-a",
            steps=(TaskStep(order=0, title="Task A Step", description="A"),),
        )
        task_plan_b = _make_task_plan(
            task_name="task-b",
            steps=(TaskStep(order=0, title="Task B Step", description="B"),),
        )

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b),
            task_plans=(task_plan_a, task_plan_b),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert len(execution_plan.execution_steps) == 2
        assert execution_plan.execution_steps[0].title == "Task A Step"
        assert execution_plan.execution_steps[1].title == "Task B Step"


# ---------------------------------------------------------------------------
# Test: Dependency Preservation
# ---------------------------------------------------------------------------


class TestDependencyPreservation:
    """Tests for dependency ordering preservation."""

    def test_workflow_order_preserved(self) -> None:
        """Workflow step order should be preserved in execution steps."""
        task_plan_a = _make_task_plan(
            task_name="task-a",
            steps=(TaskStep(order=0, title="A1", description="A"),),
        )
        task_plan_b = _make_task_plan(
            task_name="task-b",
            steps=(TaskStep(order=0, title="B1", description="B"),),
        )
        task_plan_c = _make_task_plan(
            task_name="task-c",
            steps=(TaskStep(order=0, title="C1", description="C"),),
        )

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)
        workflow_step_c = _make_workflow_step(step_id="task-c", order=2)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b, workflow_step_c),
            task_plans=(task_plan_a, task_plan_b, task_plan_c),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        # Verify order is sequential
        assert execution_plan.execution_steps[0].order == 0
        assert execution_plan.execution_steps[1].order == 1
        assert execution_plan.execution_steps[2].order == 2

    def test_required_symbols_preserved(self) -> None:
        """Required symbols from TaskSteps should be preserved."""
        task_step = TaskStep(
            order=0,
            title="Analyze",
            description="Analyze",
            required_symbols=("SymbolA", "SymbolB"),
        )
        task_plan = _make_task_plan(steps=(task_step,))
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.execution_steps[0].required_symbols == (
            "SymbolA",
            "SymbolB",
        )

    def test_required_modules_preserved(self) -> None:
        """Required modules from TaskSteps should be preserved."""
        task_step = TaskStep(
            order=0,
            title="Analyze",
            description="Analyze",
            required_modules=("mod_a.py", "mod_b.py"),
        )
        task_plan = _make_task_plan(steps=(task_step,))
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.execution_steps[0].required_modules == (
            "mod_a.py",
            "mod_b.py",
        )


# ---------------------------------------------------------------------------
# Test: Constraint Aggregation
# ---------------------------------------------------------------------------


class TestConstraintAggregation:
    """Tests for constraint aggregation."""

    def test_workflow_constraints_aggregated(self) -> None:
        """Workflow-level constraints should be aggregated."""
        constraint = TaskConstraint(
            type="read-only",
            description="Must not modify source code",
        )
        workflow_plan = _make_workflow_plan(constraints=(constraint,))

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert len(execution_plan.constraints) == 1
        assert "Must not modify source code" in execution_plan.constraints

    def test_task_constraints_aggregated(self) -> None:
        """Task-level constraints should be aggregated."""
        constraint = TaskConstraint(
            type="timeout",
            description="Must complete within 30s",
        )
        task_plan = _make_task_plan(constraints=(constraint,))
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert "Must complete within 30s" in execution_plan.constraints

    def test_duplicate_constraints_deduplicated(self) -> None:
        """Duplicate constraints should be deduplicated."""
        constraint = TaskConstraint(
            type="read-only",
            description="Must not modify source code",
        )
        task_plan = _make_task_plan(constraints=(constraint,))
        workflow_plan = _make_workflow_plan(
            constraints=(constraint,),
            task_plans=(task_plan,),
        )
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(task_plan,),
            constraints=(constraint,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        # Should have only one unique constraint
        count = sum(1 for c in execution_plan.constraints if c == "Must not modify source code")
        assert count == 1


# ---------------------------------------------------------------------------
# Test: Metric Aggregation
# ---------------------------------------------------------------------------


class TestMetricAggregation:
    """Tests for metric aggregation."""

    def test_tokens_summed(self) -> None:
        """Token counts should be summed across tasks."""
        metrics_a = TaskMetrics(estimated_tokens=100, estimated_complexity=TaskComplexity.LOW)
        metrics_b = TaskMetrics(estimated_tokens=200, estimated_complexity=TaskComplexity.LOW)

        task_plan_a = _make_task_plan(task_name="task-a", metrics=metrics_a)
        task_plan_b = _make_task_plan(task_name="task-b", metrics=metrics_b)

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b),
            task_plans=(task_plan_a, task_plan_b),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.metrics.estimated_tokens == 300

    def test_duration_is_zero(self) -> None:
        """Duration should be zero since TaskMetrics has no duration field."""
        metrics_a = TaskMetrics(
            estimated_tokens=100,
            estimated_complexity=TaskComplexity.LOW,
        )
        metrics_b = TaskMetrics(
            estimated_tokens=100,
            estimated_complexity=TaskComplexity.LOW,
        )

        task_plan_a = _make_task_plan(task_name="task-a", metrics=metrics_a)
        task_plan_b = _make_task_plan(task_name="task-b", metrics=metrics_b)

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b),
            task_plans=(task_plan_a, task_plan_b),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        # TaskMetrics has no estimated_duration_ms, so it stays 0
        assert execution_plan.metrics.estimated_duration_ms == 0

    def test_max_complexity(self) -> None:
        """Max complexity should be selected across tasks."""
        metrics_low = TaskMetrics(estimated_complexity=TaskComplexity.LOW)
        metrics_high = TaskMetrics(estimated_complexity=TaskComplexity.HIGH)

        task_plan_a = _make_task_plan(task_name="task-a", metrics=metrics_low)
        task_plan_b = _make_task_plan(task_name="task-b", metrics=metrics_high)

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b),
            task_plans=(task_plan_a, task_plan_b),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.metrics.estimated_complexity == TaskComplexity.HIGH


# ---------------------------------------------------------------------------
# Test: ContextPackage Preservation
# ---------------------------------------------------------------------------


class TestContextPreservation:
    """Tests for context package preservation."""

    def test_context_package_preserved(self) -> None:
        """Context package should be preserved from workflow plan."""
        context = {"key": "value", "data": "test"}
        workflow_plan = _make_workflow_plan(context_package=context)
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(),
            context_package=context,
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.context_package == context

    def test_none_context_preserved(self) -> None:
        """None context should be preserved as None."""
        workflow_plan = _make_workflow_plan(context_package=None)
        workflow_step = _make_workflow_step(step_id="test_task", order=0)
        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step,),
            task_plans=(),
            context_package=None,
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.context_package is None


# ---------------------------------------------------------------------------
# Test: Deterministic Planning
# ---------------------------------------------------------------------------


class TestDeterministicPlanning:
    """Tests for deterministic planning."""

    def test_deterministic_output(self) -> None:
        """Multiple calls should produce identical plans."""
        task_plan_a = _make_task_plan(
            task_name="task-a",
            steps=(
                TaskStep(order=0, title="A1", description="A"),
            ),
        )
        task_plan_b = _make_task_plan(
            task_name="task-b",
            steps=(
                TaskStep(order=0, title="B1", description="B"),
            ),
        )

        workflow_step_a = _make_workflow_step(step_id="task-a", order=0)
        workflow_step_b = _make_workflow_step(step_id="task-b", order=1)

        workflow_plan = _make_workflow_plan(
            workflow_steps=(workflow_step_a, workflow_step_b),
            task_plans=(task_plan_a, task_plan_b),
        )

        plan1 = ExecutionPlanner.plan(workflow_plan)
        plan2 = ExecutionPlanner.plan(workflow_plan)

        assert len(plan1.execution_steps) == len(plan2.execution_steps)
        for i in range(len(plan1.execution_steps)):
            assert plan1.execution_steps[i].order == plan2.execution_steps[i].order
            assert plan1.execution_steps[i].title == plan2.execution_steps[i].title
            assert plan1.execution_steps[i].description == plan2.execution_steps[i].description

    def test_workflow_name_preserved(self) -> None:
        """Workflow name should be preserved."""
        workflow_plan = _make_workflow_plan()
        workflow_plan = _make_workflow_plan(
            workflow_name="custom_workflow",
            workflow_steps=(),
            task_plans=(),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.workflow_name == "custom_workflow"

    def test_objective_generated(self) -> None:
        """Objective should be generated from workflow name."""
        workflow_plan = _make_workflow_plan(
            workflow_name="implement_feature",
            workflow_steps=(),
            task_plans=(),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert execution_plan.objective == "Execute workflow: implement_feature"


# ---------------------------------------------------------------------------
# Test: Validation Requirements
# ---------------------------------------------------------------------------


class TestValidationRequirements:
    """Tests for validation requirements generation."""

    def test_dependency_ordering_required(self) -> None:
        """Dependency ordering validation should always be required."""
        workflow_plan = _make_workflow_plan()
        workflow_plan = _make_workflow_plan(
            workflow_steps=(),
            task_plans=(),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert "validate_dependency_ordering" in execution_plan.validation_requirements

    def test_context_validation_when_present(self) -> None:
        """Context validation should be required when context exists."""
        workflow_plan = _make_workflow_plan(context_package={"key": "value"})
        workflow_plan = _make_workflow_plan(
            workflow_steps=(),
            task_plans=(),
            context_package={"key": "value"},
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert "validate_context_exists" in execution_plan.validation_requirements

    def test_constraints_validation_when_present(self) -> None:
        """Constraints validation should be required when constraints exist."""
        constraint = TaskConstraint(type="read-only", description="Test")
        workflow_plan = _make_workflow_plan(constraints=(constraint,))
        workflow_plan = _make_workflow_plan(
            workflow_steps=(),
            task_plans=(),
            constraints=(constraint,),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert "validate_constraints_satisfied" in execution_plan.validation_requirements

    def test_deterministic_ordering_required(self) -> None:
        """Deterministic ordering should always be required."""
        workflow_plan = _make_workflow_plan()
        workflow_plan = _make_workflow_plan(
            workflow_steps=(),
            task_plans=(),
        )

        execution_plan = ExecutionPlanner.plan(workflow_plan)

        assert "validate_deterministic_ordering" in execution_plan.validation_requirements
