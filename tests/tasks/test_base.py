"""Tests for the Task Framework base.

Verifies:
- Task ABC is abstract
- name property returns class name
- capability property returns capability name
- plan() delegates to _do_plan
- _do_plan is abstract
- Tasks are stateless
- Deterministic naming
"""

from __future__ import annotations

import pytest

from packages.tasks.base import Task
from packages.tasks.models import TaskPlan, TaskRequest, TaskStep

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class ConcreteTask(Task):
    """A concrete task implementation for testing."""

    @property
    def name(self) -> str:
        return "concrete_task"

    @property
    def capability(self) -> str:
        return "test_capability"

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> TaskPlan:
        return TaskPlan(
            task_name="concrete_task",
            capability="test_capability",
            context_package=None,
            steps=(
                TaskStep(
                    order=0,
                    title="Step 1",
                    description="First step",
                ),
            ),
        )


class ConcreteTaskWithDefaultName(Task):
    """A task that uses the default name property."""

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> TaskPlan:
        return TaskPlan(
            task_name="default_name_task",
            capability="default_capability",
            context_package=None,
        )


# ---------------------------------------------------------------------------
# Test: Task ABC
# ---------------------------------------------------------------------------


class TestTaskABC:
    """Tests for the Task ABC."""

    def test_task_is_abstract(self) -> None:
        """Task should be an ABC and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Task()  # type: ignore[abstract]

    def test_concrete_task_instantiation(self) -> None:
        """ConcreteTask should be instantiable."""
        task = ConcreteTask()
        assert isinstance(task, Task)

    def test_concrete_task_name(self) -> None:
        """ConcreteTask should return its overridden name."""
        task = ConcreteTask()
        assert task.name == "concrete_task"

    def test_concrete_task_capability(self) -> None:
        """ConcreteTask should return its overridden capability."""
        task = ConcreteTask()
        assert task.capability == "test_capability"

    def test_default_name_property(self) -> None:
        """Task should use class name lowercase as default."""
        task = ConcreteTaskWithDefaultName()
        # The default name is simply the class name lowercased
        assert task.name == "concretetaskwithdefaultname"

    def test_default_capability_property(self) -> None:
        """Task should use class name lowercase as default capability."""
        task = ConcreteTaskWithDefaultName()
        assert task.capability == "concretetaskwithdefaultname"


# ---------------------------------------------------------------------------
# Test: plan() lifecycle
# ---------------------------------------------------------------------------


class TestPlanLifecycle:
    """Tests for the plan() method lifecycle."""

    def test_plan_delegates_to_do_plan(self) -> None:
        """plan() should delegate to _do_plan."""
        task = ConcreteTask()
        request = TaskRequest(query="Test query")

        # Mock _do_plan to verify it's called
        original_do_plan = task._do_plan
        call_count = 0

        def counting_do_plan(repository_index, request):
            nonlocal call_count
            call_count += 1
            return original_do_plan(repository_index, request)

        task._do_plan = counting_do_plan  # type: ignore[method-assign]
        task.plan(None, request)  # type: ignore[arg-type]

        assert call_count == 1

    def test_plan_returns_task_plan(self) -> None:
        """plan() should return a TaskPlan."""
        task = ConcreteTask()
        request = TaskRequest(query="Test query")
        result = task.plan(None, request)  # type: ignore[arg-type]

        assert isinstance(result, TaskPlan)

    def test_plan_with_repository_index(self) -> None:
        """plan() should accept a repository index."""
        task = ConcreteTask()
        request = TaskRequest(query="Test query")

        # Create a minimal mock index
        _STATS_DICT: dict[str, int] = {
            "module_count": 0,
            "class_count": 0,
            "function_count": 0,
            "method_count": 0,
            "symbol_count": 0,
        }

        class MockIndex:
            modules: dict = {}

            def relationships(self) -> list:
                return []

            def statistics(self) -> object:
                return type("Stats", (), _STATS_DICT)()

        index = MockIndex()
        result = task.plan(index, request)

        assert isinstance(result, TaskPlan)


# ---------------------------------------------------------------------------
# Test: Tasks are stateless
# ---------------------------------------------------------------------------


class TestTaskStatelessness:
    """Tests that tasks are stateless."""

    def test_no_instance_attributes(self) -> None:
        """Tasks should have no instance attributes beyond the ABC."""
        task = ConcreteTask()
        # Tasks should not have __dict__ with user-defined attributes
        # (they use slots or rely on properties only)
        assert not hasattr(task, "_state")
        assert not hasattr(task, "_cache")

    def test_multiple_instances_are_independent(self) -> None:
        """Multiple task instances should be independent."""
        task1 = ConcreteTask()
        task2 = ConcreteTask()

        assert task1.name == task2.name
        assert task1.capability == task2.capability
        assert task1 is not task2


# ---------------------------------------------------------------------------
# Test: _do_plan is abstract
# ---------------------------------------------------------------------------


class TestDoPlanAbstract:
    """Tests for _do_plan abstract method."""

    def test_incomplete_implementation_raises(self) -> None:
        """A task without _do_plan cannot be instantiated."""

        class IncompleteTask(Task):
            @property
            def name(self) -> str:
                return "incomplete"

            @property
            def capability(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError):
            IncompleteTask()  # type: ignore[abstract]
