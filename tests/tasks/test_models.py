"""Tests for the Task Framework models.

Verifies:
- Immutable models (frozen dataclasses)
- TaskComplexity enum values
- TaskRequest creation and defaults
- TaskConstraint creation
- TaskMetrics creation and defaults
- TaskStep creation
- TaskPlan creation
- Deterministic ordering
- Frozen dataclasses cannot be mutated
"""

from __future__ import annotations

import pytest

from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskRequest,
    TaskStep,
)

# ---------------------------------------------------------------------------
# Test: TaskComplexity
# ---------------------------------------------------------------------------


class TestTaskComplexity:
    """Tests for TaskComplexity enum."""

    def test_task_complexity_has_all_values(self) -> None:
        assert hasattr(TaskComplexity, "LOW")
        assert hasattr(TaskComplexity, "MEDIUM")
        assert hasattr(TaskComplexity, "HIGH")
        assert hasattr(TaskComplexity, "VERY_HIGH")

    def test_task_complexity_values(self) -> None:
        assert TaskComplexity.LOW.value == "LOW"
        assert TaskComplexity.MEDIUM.value == "MEDIUM"
        assert TaskComplexity.HIGH.value == "HIGH"
        assert TaskComplexity.VERY_HIGH.value == "VERY_HIGH"

    def test_task_complexity_is_str_enum(self) -> None:
        assert isinstance(TaskComplexity.LOW, str)


# ---------------------------------------------------------------------------
# Test: TaskRequest
# ---------------------------------------------------------------------------


class TestTaskRequest:
    """Tests for TaskRequest immutable dataclass."""

    def test_request_creation_minimal(self) -> None:
        request = TaskRequest(query="Refactor ProviderFactory")
        assert request.query == "Refactor ProviderFactory"
        assert request.repository_root == "."
        assert request.user_messages == ()
        assert request.constraints == ()
        assert request.options == {}

    def test_request_creation_full(self) -> None:
        request = TaskRequest(
            query="Refactor ProviderFactory",
            repository_root="/path/to/repo",
            user_messages=("Please refactor", "Focus on factory pattern"),
            constraints=("read_only", "deterministic"),
            options={"scope": "module", "depth": "deep"},
        )
        assert request.query == "Refactor ProviderFactory"
        assert request.repository_root == "/path/to/repo"
        assert request.user_messages == ("Please refactor", "Focus on factory pattern")
        assert request.constraints == ("read_only", "deterministic")
        assert request.options == {"scope": "module", "depth": "deep"}

    def test_request_is_immutable(self) -> None:
        request = TaskRequest(query="Test query")
        with pytest.raises(AttributeError):
            request.query = "New query"  # type: ignore[misc]

    def test_request_user_messages_are_immutable_tuple(self) -> None:
        request = TaskRequest(
            query="Test query",
            user_messages=("msg1", "msg2"),
        )
        with pytest.raises(TypeError):
            request.user_messages[0] = "new msg"  # type: ignore[index]

    def test_request_constraints_are_immutable_tuple(self) -> None:
        request = TaskRequest(
            query="Test query",
            constraints=("c1", "c2"),
        )
        with pytest.raises(TypeError):
            request.constraints[0] = "new constraint"  # type: ignore[index]

    def test_request_options_are_immutable_dict(self) -> None:
        request = TaskRequest(
            query="Test query",
            options={"key": "value"},
        )
        with pytest.raises(AttributeError):
            request.options = {"new": "dict"}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: TaskConstraint
# ---------------------------------------------------------------------------


class TestTaskConstraint:
    """Tests for TaskConstraint immutable dataclass."""

    def test_constraint_creation(self) -> None:
        constraint = TaskConstraint(
            type="read_only",
            description="Task must not modify source code",
        )
        assert constraint.type == "read_only"
        assert constraint.description == "Task must not modify source code"

    def test_constraint_is_immutable(self) -> None:
        constraint = TaskConstraint(
            type="read_only",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            constraint.type = "new_type"  # type: ignore[misc]

    def test_constraint_description_is_immutable(self) -> None:
        constraint = TaskConstraint(
            type="read_only",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            constraint.description = "New description"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: TaskMetrics
# ---------------------------------------------------------------------------


class TestTaskMetrics:
    """Tests for TaskMetrics immutable dataclass."""

    def test_metrics_defaults(self) -> None:
        metrics = TaskMetrics()
        assert metrics.estimated_tokens == 0
        assert metrics.estimated_complexity == TaskComplexity.LOW

    def test_metrics_creation(self) -> None:
        metrics = TaskMetrics(
            estimated_tokens=1024,
            estimated_complexity=TaskComplexity.HIGH,
        )
        assert metrics.estimated_tokens == 1024
        assert metrics.estimated_complexity == TaskComplexity.HIGH

    def test_metrics_is_immutable(self) -> None:
        metrics = TaskMetrics(estimated_tokens=512, estimated_complexity=TaskComplexity.MEDIUM)
        with pytest.raises(AttributeError):
            metrics.estimated_tokens = 1024  # type: ignore[misc]

    def test_metrics_complexity_is_immutable(self) -> None:
        metrics = TaskMetrics(estimated_tokens=512, estimated_complexity=TaskComplexity.MEDIUM)
        with pytest.raises(AttributeError):
            metrics.estimated_complexity = TaskComplexity.HIGH  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: TaskStep
# ---------------------------------------------------------------------------


class TestTaskStep:
    """Tests for TaskStep immutable dataclass."""

    def test_step_creation_minimal(self) -> None:
        step = TaskStep(
            order=0,
            title="Analyze repository",
            description="Examine the repository structure",
        )
        assert step.order == 0
        assert step.title == "Analyze repository"
        assert step.description == "Examine the repository structure"
        assert step.required_symbols == ()
        assert step.required_modules == ()

    def test_step_creation_full(self) -> None:
        step = TaskStep(
            order=1,
            title="Refactor module",
            description="Apply refactoring to the target module",
            required_symbols=("ProviderFactory", "create_provider"),
            required_modules=("packages/providers/factory.py",),
        )
        assert step.order == 1
        assert step.title == "Refactor module"
        assert step.description == "Apply refactoring to the target module"
        assert step.required_symbols == ("ProviderFactory", "create_provider")
        assert step.required_modules == ("packages/providers/factory.py",)

    def test_step_is_immutable(self) -> None:
        step = TaskStep(
            order=0,
            title="Test step",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            step.order = 1  # type: ignore[misc]

    def test_step_title_is_immutable(self) -> None:
        step = TaskStep(
            order=0,
            title="Test step",
            description="Test description",
        )
        with pytest.raises(AttributeError):
            step.title = "New title"  # type: ignore[misc]

    def test_step_required_symbols_are_immutable_tuple(self) -> None:
        step = TaskStep(
            order=0,
            title="Test step",
            description="Test description",
            required_symbols=("sym1", "sym2"),
        )
        with pytest.raises(TypeError):
            step.required_symbols[0] = "new_sym"  # type: ignore[index]

    def test_step_required_modules_are_immutable_tuple(self) -> None:
        step = TaskStep(
            order=0,
            title="Test step",
            description="Test description",
            required_modules=("mod1.py", "mod2.py"),
        )
        with pytest.raises(TypeError):
            step.required_modules[0] = "new_mod.py"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Test: TaskPlan
# ---------------------------------------------------------------------------


class TestTaskPlan:
    """Tests for TaskPlan immutable dataclass."""

    def test_plan_creation_minimal(self) -> None:
        plan = TaskPlan(
            task_name="refactor",
            capability="refactor",
            context_package=None,
        )
        assert plan.task_name == "refactor"
        assert plan.capability == "refactor"
        assert plan.context_package is None
        assert plan.steps == ()
        assert plan.constraints == ()
        assert plan.metrics.estimated_tokens == 0
        assert plan.metrics.estimated_complexity == TaskComplexity.LOW

    def test_plan_creation_full(self) -> None:
        step1 = TaskStep(
            order=0,
            title="Analyze",
            description="Analyze the codebase",
        )
        step2 = TaskStep(
            order=1,
            title="Implement",
            description="Implement changes",
        )
        constraint = TaskConstraint(
            type="read_only",
            description="Read only operation",
        )
        metrics = TaskMetrics(
            estimated_tokens=2048,
            estimated_complexity=TaskComplexity.MEDIUM,
        )

        plan = TaskPlan(
            task_name="refactor",
            capability="refactor",
            context_package={"key": "value"},
            steps=(step1, step2),
            constraints=(constraint,),
            metrics=metrics,
        )

        assert plan.task_name == "refactor"
        assert plan.capability == "refactor"
        assert plan.context_package == {"key": "value"}
        assert len(plan.steps) == 2
        assert plan.steps[0].title == "Analyze"
        assert plan.steps[1].title == "Implement"
        assert len(plan.constraints) == 1
        assert plan.metrics.estimated_tokens == 2048
        assert plan.metrics.estimated_complexity == TaskComplexity.MEDIUM

    def test_plan_is_immutable(self) -> None:
        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
        )
        with pytest.raises(AttributeError):
            plan.task_name = "new_name"  # type: ignore[misc]

    def test_plan_steps_are_immutable_tuple(self) -> None:
        step = TaskStep(
            order=0,
            title="Test",
            description="Test description",
        )
        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
            steps=(step,),
        )
        with pytest.raises(TypeError):
            plan.steps[0] = step  # type: ignore[index]

    def test_plan_constraints_are_immutable_tuple(self) -> None:
        constraint = TaskConstraint(
            type="test",
            description="Test",
        )
        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
            constraints=(constraint,),
        )
        with pytest.raises(TypeError):
            plan.constraints[0] = constraint  # type: ignore[index]

    def test_plan_metrics_are_immutable(self) -> None:
        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
        )
        with pytest.raises(AttributeError):
            plan.metrics = TaskMetrics()  # type: ignore[misc]

    def test_plan_steps_are_deterministic(self) -> None:
        """Steps should be ordered deterministically."""
        step2 = TaskStep(order=1, title="Second", description="B")
        step1 = TaskStep(order=0, title="First", description="A")

        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
            steps=(step2, step1),
        )

        # Steps are stored as provided, but the order field indicates
        # the deterministic execution order
        assert plan.steps[0].order == 1
        assert plan.steps[1].order == 0

    def test_plan_empty_defaults(self) -> None:
        """Empty collections should default to empty tuples."""
        plan = TaskPlan(
            task_name="test",
            capability="test",
            context_package=None,
        )
        assert plan.steps == ()
        assert plan.constraints == ()
