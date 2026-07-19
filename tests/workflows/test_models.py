"""Tests for the Workflow Engine models.

Verifies:
- Immutable models (frozen dataclasses)
- WorkflowNode creation and defaults
- WorkflowStep creation
- WorkflowMetrics creation and defaults
- WorkflowPlan creation
- Deterministic ordering
- Frozen dataclasses cannot be mutated
"""

from __future__ import annotations

import pytest

from packages.tasks.models import TaskComplexity, TaskConstraint
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowNode,
    WorkflowPlan,
    WorkflowStep,
)

# ---------------------------------------------------------------------------
# Test: WorkflowNode
# ---------------------------------------------------------------------------


class TestWorkflowNode:
    """Tests for WorkflowNode immutable dataclass."""

    def test_node_creation_minimal(self) -> None:
        node = WorkflowNode(
            node_id="architecture",
            task=str,  # type: ignore
        )
        assert node.node_id == "architecture"
        assert node.task is str
        assert node.depends_on == ()
        assert node.parallelizable is False

    def test_node_creation_full(self) -> None:
        node = WorkflowNode(
            node_id="impact",
            task=str,  # type: ignore
            depends_on=("architecture",),
            parallelizable=True,
        )
        assert node.node_id == "impact"
        assert node.task is str
        assert node.depends_on == ("architecture",)
        assert node.parallelizable is True

    def test_node_is_immutable(self) -> None:
        node = WorkflowNode(
            node_id="test",
            task=str,  # type: ignore
        )
        with pytest.raises(AttributeError):
            node.node_id = "new_id"  # type: ignore[misc]

    def test_node_depends_on_is_immutable_tuple(self) -> None:
        node = WorkflowNode(
            node_id="test",
            task=str,  # type: ignore
            depends_on=("a", "b"),
        )
        with pytest.raises(TypeError):
            node.depends_on[0] = "c"  # type: ignore[index]

    def test_node_parallelizable_is_immutable(self) -> None:
        node = WorkflowNode(
            node_id="test",
            task=str,  # type: ignore
            parallelizable=True,
        )
        with pytest.raises(AttributeError):
            node.parallelizable = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: WorkflowStep
# ---------------------------------------------------------------------------


class TestWorkflowStep:
    """Tests for WorkflowStep immutable dataclass."""

    def test_step_creation_minimal(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        assert step.step_id == "step-1"
        assert step.order == 0
        assert step.workflow_node == "architecture"
        assert step.task_name == "architecture-review"
        assert step.description == "Review architecture"

    def test_step_is_immutable(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        with pytest.raises(AttributeError):
            step.step_id = "step-2"  # type: ignore[misc]

    def test_step_order_is_immutable(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        with pytest.raises(AttributeError):
            step.order = 1  # type: ignore[misc]

    def test_step_workflow_node_is_immutable(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        with pytest.raises(AttributeError):
            step.workflow_node = "new-node"  # type: ignore[misc]

    def test_step_task_name_is_immutable(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        with pytest.raises(AttributeError):
            step.task_name = "new-task"  # type: ignore[misc]

    def test_step_description_is_immutable(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        with pytest.raises(AttributeError):
            step.description = "New description"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: WorkflowMetrics
# ---------------------------------------------------------------------------


class TestWorkflowMetrics:
    """Tests for WorkflowMetrics immutable dataclass."""

    def test_metrics_defaults(self) -> None:
        metrics = WorkflowMetrics()
        assert metrics.estimated_tokens == 0
        assert metrics.estimated_duration_ms == 0
        assert metrics.estimated_complexity == TaskComplexity.LOW

    def test_metrics_creation(self) -> None:
        metrics = WorkflowMetrics(
            estimated_tokens=1024,
            estimated_duration_ms=5000,
            estimated_complexity=TaskComplexity.HIGH,
        )
        assert metrics.estimated_tokens == 1024
        assert metrics.estimated_duration_ms == 5000
        assert metrics.estimated_complexity == TaskComplexity.HIGH

    def test_metrics_is_immutable(self) -> None:
        metrics = WorkflowMetrics(estimated_tokens=512)
        with pytest.raises(AttributeError):
            metrics.estimated_tokens = 1024  # type: ignore[misc]

    def test_metrics_duration_is_immutable(self) -> None:
        metrics = WorkflowMetrics(estimated_duration_ms=1000)
        with pytest.raises(AttributeError):
            metrics.estimated_duration_ms = 2000  # type: ignore[misc]

    def test_metrics_complexity_is_immutable(self) -> None:
        metrics = WorkflowMetrics(estimated_complexity=TaskComplexity.MEDIUM)
        with pytest.raises(AttributeError):
            metrics.estimated_complexity = TaskComplexity.HIGH  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: WorkflowPlan
# ---------------------------------------------------------------------------


class TestWorkflowPlan:
    """Tests for WorkflowPlan immutable dataclass."""

    def test_plan_creation_minimal(self) -> None:
        plan = WorkflowPlan(
            workflow_name="test-workflow",
            task_plans=(),
        )
        assert plan.workflow_name == "test-workflow"
        assert plan.task_plans == ()
        assert plan.workflow_steps == ()
        assert plan.merged_context_package is None
        assert plan.metrics.estimated_tokens == 0
        assert plan.constraints == ()

    def test_plan_creation_full(self) -> None:
        step1 = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="architecture",
            task_name="architecture-review",
            description="Review architecture",
        )
        step2 = WorkflowStep(
            step_id="step-2",
            order=1,
            workflow_node="impact",
            task_name="impact-analysis",
            description="Analyze impact",
        )
        constraint = TaskConstraint(
            type="read-only",
            description="Task must not modify source code",
        )
        metrics = WorkflowMetrics(
            estimated_tokens=2048,
            estimated_duration_ms=10000,
            estimated_complexity=TaskComplexity.MEDIUM,
        )

        plan = WorkflowPlan(
            workflow_name="implement-feature",
            task_plans=(),
            workflow_steps=(step1, step2),
            merged_context_package={"key": "value"},
            metrics=metrics,
            constraints=(constraint,),
        )

        assert plan.workflow_name == "implement-feature"
        assert plan.workflow_steps == (step1, step2)
        assert plan.merged_context_package == {"key": "value"}
        assert plan.metrics.estimated_tokens == 2048
        assert len(plan.constraints) == 1
        assert plan.constraints[0].type == "read-only"

    def test_plan_is_immutable(self) -> None:
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
        )
        with pytest.raises(AttributeError):
            plan.workflow_name = "new-name"  # type: ignore[misc]

    def test_plan_task_plans_are_immutable_tuple(self) -> None:
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
        )
        with pytest.raises(TypeError):
            plan.task_plans[0] = "item"  # type: ignore[index]

    def test_plan_workflow_steps_are_immutable_tuple(self) -> None:
        step = WorkflowStep(
            step_id="step-1",
            order=0,
            workflow_node="test",
            task_name="test",
            description="Test",
        )
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
            workflow_steps=(step,),
        )
        with pytest.raises(TypeError):
            plan.workflow_steps[0] = step  # type: ignore[index]

    def test_plan_metrics_are_immutable(self) -> None:
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
        )
        with pytest.raises(AttributeError):
            plan.metrics = WorkflowMetrics()  # type: ignore[misc]

    def test_plan_constraints_are_immutable_tuple(self) -> None:
        constraint = TaskConstraint(
            type="test",
            description="Test",
        )
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
            constraints=(constraint,),
        )
        with pytest.raises(TypeError):
            plan.constraints[0] = constraint  # type: ignore[index]

    def test_plan_empty_defaults(self) -> None:
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
        )
        assert plan.workflow_steps == ()
        assert plan.constraints == ()
