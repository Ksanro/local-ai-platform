"""Tests for the Execution Planner models.

Verifies:
- Immutable models (frozen dataclasses)
- ExecutionStep creation and defaults
- ExecutionMetrics creation and defaults
- ExecutionPlan creation and defaults
- Deterministic ordering
- Frozen dataclasses cannot be mutated
"""

from __future__ import annotations

import pytest

from packages.execution.models import (
    ExecutionMetrics,
    ExecutionPlan,
    ExecutionStep,
)
from packages.tasks.models import TaskComplexity

# ---------------------------------------------------------------------------
# Test: ExecutionStep
# ---------------------------------------------------------------------------


class TestExecutionStep:
    """Tests for ExecutionStep immutable dataclass."""

    def test_step_creation_minimal(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Analyze repository",
            description="Examine the repository structure",
        )
        assert step.order == 0
        assert step.title == "Analyze repository"
        assert step.description == "Examine the repository structure"
        assert step.required_symbols == ()
        assert step.required_modules == ()
        assert step.constraints == ()

    def test_step_creation_full(self) -> None:
        step = ExecutionStep(
            order=1,
            title="Refactor module",
            description="Apply refactoring to the target module",
            required_symbols=("ProviderFactory", "create_provider"),
            required_modules=("packages/providers/factory.py",),
            constraints=("read_only", "deterministic"),
        )
        assert step.order == 1
        assert step.title == "Refactor module"
        assert step.description == "Apply refactoring to the target module"
        assert step.required_symbols == ("ProviderFactory", "create_provider")
        assert step.required_modules == ("packages/providers/factory.py",)
        assert step.constraints == ("read_only", "deterministic")

    def test_step_is_immutable(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            step.order = 1  # type: ignore[misc]

    def test_step_title_is_immutable(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            step.title = "New title"  # type: ignore[misc]

    def test_step_description_is_immutable(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            step.description = "New description"  # type: ignore[misc]

    def test_step_required_symbols_are_immutable_tuple(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
            required_symbols=("sym1", "sym2"),
        )
        with pytest.raises(TypeError):
            step.required_symbols[0] = "new_sym"  # type: ignore[index]

    def test_step_required_modules_are_immutable_tuple(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
            required_modules=("mod1.py", "mod2.py"),
        )
        with pytest.raises(TypeError):
            step.required_modules[0] = "new_mod.py"  # type: ignore[index]

    def test_step_constraints_are_immutable_tuple(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test step",
            description="Test description",
            constraints=("c1", "c2"),
        )
        with pytest.raises(TypeError):
            step.constraints[0] = "new_constraint"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Test: ExecutionMetrics
# ---------------------------------------------------------------------------


class TestExecutionMetrics:
    """Tests for ExecutionMetrics immutable dataclass."""

    def test_metrics_defaults(self) -> None:
        metrics = ExecutionMetrics()
        assert metrics.estimated_tokens == 0
        assert metrics.estimated_duration_ms == 0
        assert metrics.estimated_complexity == TaskComplexity.LOW

    def test_metrics_creation(self) -> None:
        metrics = ExecutionMetrics(
            estimated_tokens=1024,
            estimated_duration_ms=5000,
            estimated_complexity=TaskComplexity.HIGH,
        )
        assert metrics.estimated_tokens == 1024
        assert metrics.estimated_duration_ms == 5000
        assert metrics.estimated_complexity == TaskComplexity.HIGH

    def test_metrics_is_immutable(self) -> None:
        metrics = ExecutionMetrics(estimated_tokens=512)
        with pytest.raises(AttributeError):
            metrics.estimated_tokens = 1024  # type: ignore[misc]

    def test_metrics_duration_is_immutable(self) -> None:
        metrics = ExecutionMetrics(estimated_duration_ms=1000)
        with pytest.raises(AttributeError):
            metrics.estimated_duration_ms = 2000  # type: ignore[misc]

    def test_metrics_complexity_is_immutable(self) -> None:
        metrics = ExecutionMetrics(estimated_complexity=TaskComplexity.MEDIUM)
        with pytest.raises(AttributeError):
            metrics.estimated_complexity = TaskComplexity.HIGH  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: ExecutionPlan
# ---------------------------------------------------------------------------


class TestExecutionPlan:
    """Tests for ExecutionPlan immutable dataclass."""

    def test_plan_creation_minimal(self) -> None:
        plan = ExecutionPlan(
            workflow_name="implement_feature",
            objective="Add new feature",
        )
        assert plan.workflow_name == "implement_feature"
        assert plan.objective == "Add new feature"
        assert plan.execution_steps == ()
        assert plan.context_package is None
        assert plan.metrics.estimated_tokens == 0
        assert plan.constraints == ()
        assert plan.validation_requirements == ()

    def test_plan_creation_full(self) -> None:
        step1 = ExecutionStep(
            order=0,
            title="Analyze",
            description="Analyze the codebase",
        )
        step2 = ExecutionStep(
            order=1,
            title="Implement",
            description="Implement changes",
        )
        metrics = ExecutionMetrics(
            estimated_tokens=2048,
            estimated_duration_ms=10000,
            estimated_complexity=TaskComplexity.MEDIUM,
        )

        plan = ExecutionPlan(
            workflow_name="implement_feature",
            objective="Add new feature",
            execution_steps=(step1, step2),
            context_package={"key": "value"},
            metrics=metrics,
            constraints=("read_only", "deterministic"),
            validation_requirements=("validate_dependency_ordering",),
        )

        assert plan.workflow_name == "implement_feature"
        assert plan.objective == "Add new feature"
        assert len(plan.execution_steps) == 2
        assert plan.execution_steps[0].title == "Analyze"
        assert plan.execution_steps[1].title == "Implement"
        assert plan.context_package == {"key": "value"}
        assert plan.metrics.estimated_tokens == 2048
        assert len(plan.constraints) == 2
        assert len(plan.validation_requirements) == 1

    def test_plan_is_immutable(self) -> None:
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test objective",
        )
        with pytest.raises(AttributeError):
            plan.workflow_name = "new_name"  # type: ignore[misc]

    def test_plan_objective_is_immutable(self) -> None:
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test objective",
        )
        with pytest.raises(AttributeError):
            plan.objective = "New objective"  # type: ignore[misc]

    def test_plan_execution_steps_are_immutable_tuple(self) -> None:
        step = ExecutionStep(
            order=0,
            title="Test",
            description="Test description",
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=(step,),
        )
        with pytest.raises(TypeError):
            plan.execution_steps[0] = step  # type: ignore[index]

    def test_plan_metrics_are_immutable(self) -> None:
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )
        with pytest.raises(AttributeError):
            plan.metrics = ExecutionMetrics()  # type: ignore[misc]

    def test_plan_constraints_are_immutable_tuple(self) -> None:
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            constraints=("c1", "c2"),
        )
        with pytest.raises(TypeError):
            plan.constraints[0] = "new"  # type: ignore[index]

    def test_plan_validation_requirements_are_immutable_tuple(self) -> None:
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            validation_requirements=("validate_ordering",),
        )
        with pytest.raises(TypeError):
            plan.validation_requirements[0] = "new"  # type: ignore[index]

    def test_plan_steps_are_deterministic(self) -> None:
        """Steps should maintain deterministic order."""
        step2 = ExecutionStep(order=1, title="Second", description="B")
        step1 = ExecutionStep(order=0, title="First", description="A")

        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=(step2, step1),
        )

        # Steps are stored as provided, but the order field indicates
        # the deterministic execution order
        assert plan.execution_steps[0].order == 1
        assert plan.execution_steps[1].order == 0

    def test_plan_empty_defaults(self) -> None:
        """Empty collections should default to empty tuples."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )
        assert plan.execution_steps == ()
        assert plan.constraints == ()
        assert plan.validation_requirements == ()
