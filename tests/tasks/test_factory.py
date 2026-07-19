"""Tests for the Task Factory.

Verifies:
- Factory creation
- Task instantiation
- Validation of registration
- Deterministic errors for unregistered names
- Registry delegation
- No hardcoded task classes
"""

from __future__ import annotations

import pytest

from packages.tasks.base import Task
from packages.tasks.factory import TaskFactory
from packages.tasks.models import TaskPlan, TaskRequest
from packages.tasks.registry import TaskRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class SampleTaskA(Task):
    """Sample task A for testing."""

    @property
    def name(self) -> str:
        return "sample_a"

    @property
    def capability(self) -> str:
        return "sample"

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> TaskPlan:
        return TaskPlan(
            task_name="sample_a",
            capability="sample",
            context_package=None,
        )


class SampleTaskB(Task):
    """Sample task B for testing."""

    @property
    def name(self) -> str:
        return "sample_b"

    @property
    def capability(self) -> str:
        return "sample"

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> TaskPlan:
        return TaskPlan(
            task_name="sample_b",
            capability="sample",
            context_package=None,
        )


# ---------------------------------------------------------------------------
# Test: Factory Creation
# ---------------------------------------------------------------------------


class TestFactoryCreation:
    """Tests for factory creation."""

    def test_factory_creation(self) -> None:
        """Factory should be creatable with a registry."""
        registry = TaskRegistry()
        factory = TaskFactory(registry)
        assert factory._registry is registry

    def test_factory_with_empty_registry(self) -> None:
        """Factory should work with an empty registry."""
        registry = TaskRegistry()
        factory = TaskFactory(registry)
        # Should not raise
        assert factory._registry is registry


# ---------------------------------------------------------------------------
# Test: Task Instantiation
# ---------------------------------------------------------------------------


class TestTaskInstantiation:
    """Tests for task instantiation through factory."""

    def test_create_registered_task(self) -> None:
        """Factory should create instances of registered tasks."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        factory = TaskFactory(registry)

        task = factory.create("sample_a")

        assert isinstance(task, Task)
        assert isinstance(task, SampleTaskA)
        assert task.name == "sample_a"

    def test_create_multiple_instances(self) -> None:
        """Factory should create independent instances."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        factory = TaskFactory(registry)

        task1 = factory.create("sample_a")
        task2 = factory.create("sample_a")

        assert task1 is not task2
        assert isinstance(task1, SampleTaskA)
        assert isinstance(task2, SampleTaskA)

    def test_create_different_tasks(self) -> None:
        """Factory should create different task types."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        registry.register("sample_b", SampleTaskB)
        factory = TaskFactory(registry)

        task_a = factory.create("sample_a")
        task_b = factory.create("sample_b")

        assert isinstance(task_a, SampleTaskA)
        assert isinstance(task_b, SampleTaskB)
        assert task_a.name == "sample_a"
        assert task_b.name == "sample_b"


# ---------------------------------------------------------------------------
# Test: Validation of Registration
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for registration validation."""

    def test_create_unregistered_raises(self) -> None:
        """Factory should raise ValueError for unregistered tasks."""
        registry = TaskRegistry()
        factory = TaskFactory(registry)

        with pytest.raises(ValueError, match="not registered"):
            factory.create("nonexistent")

    def test_create_unregistered_shows_available(self) -> None:
        """Error message should show available tasks."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        factory = TaskFactory(registry)

        with pytest.raises(ValueError, match="sample_a"):
            factory.create("nonexistent")

    def test_create_unregistered_shows_empty_when_no_tasks(self) -> None:
        """Error message should show empty list when no tasks registered."""
        registry = TaskRegistry()
        factory = TaskFactory(registry)

        with pytest.raises(ValueError, match="Available tasks: \\[\\]"):
            factory.create("nonexistent")

    def test_create_after_unregister_raises(self) -> None:
        """Factory should raise after task is unregistered."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        factory = TaskFactory(registry)

        # Should work initially
        task = factory.create("sample_a")
        assert isinstance(task, SampleTaskA)

        # Should fail after unregister
        registry.unregister("sample_a")
        with pytest.raises(ValueError, match="not registered"):
            factory.create("sample_a")


# ---------------------------------------------------------------------------
# Test: Deterministic Errors
# ---------------------------------------------------------------------------


class TestDeterministicErrors:
    """Tests for deterministic error messages."""

    def test_error_message_is_deterministic(self) -> None:
        """Error messages should be deterministic."""
        registry = TaskRegistry()
        registry.register("zebra", SampleTaskA)
        registry.register("alpha", SampleTaskB)
        factory = TaskFactory(registry)

        with pytest.raises(ValueError) as exc_info1:
            factory.create("missing")

        with pytest.raises(ValueError) as exc_info2:
            factory.create("missing")

        # Both errors should mention the same available tasks
        assert "zebra" in str(exc_info1.value)
        assert "alpha" in str(exc_info1.value)
        assert "zebra" in str(exc_info2.value)
        assert "alpha" in str(exc_info2.value)

    def test_error_message_ordering(self) -> None:
        """Available tasks in error should be sorted."""
        registry = TaskRegistry()
        registry.register("z_task", SampleTaskA)
        registry.register("a_task", SampleTaskB)
        registry.register("m_task", SampleTaskA)
        factory = TaskFactory(registry)

        with pytest.raises(ValueError) as exc_info:
            factory.create("missing")

        error_msg = str(exc_info.value)
        # Find positions of task names in error message
        a_pos = error_msg.find("a_task")
        m_pos = error_msg.find("m_task")
        z_pos = error_msg.find("z_task")

        assert a_pos < m_pos < z_pos


# ---------------------------------------------------------------------------
# Test: Registry Delegation
# ---------------------------------------------------------------------------


class TestRegistryDelegation:
    """Tests that factory delegates to registry."""

    def test_factory_uses_registry_get(self) -> None:
        """Factory should use registry.get() for lookup."""
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        factory = TaskFactory(registry)

        # The task class comes from the registry
        task = factory.create("sample_a")
        assert task.__class__ is SampleTaskA

    def test_factory_reflects_registry_changes(self) -> None:
        """Factory should reflect registry changes immediately."""
        registry = TaskRegistry()
        factory = TaskFactory(registry)

        # Not registered yet
        with pytest.raises(ValueError):
            factory.create("sample_a")

        # Register and create
        registry.register("sample_a", SampleTaskA)
        task = factory.create("sample_a")
        assert isinstance(task, SampleTaskA)


# ---------------------------------------------------------------------------
# Test: No Hardcoded Task Classes
# ---------------------------------------------------------------------------


class TestNoHardcodedClasses:
    """Tests that factory has no hardcoded task classes."""

    def test_factory_only_uses_registry(self) -> None:
        """Factory should only interact through registry."""
        registry = TaskRegistry()
        # If we register a completely custom task, factory should handle it
        class CustomTask(Task):
            @property
            def name(self) -> str:
                return "custom"

            @property
            def capability(self) -> str:
                return "custom"

            def _do_plan(
                self,
                repository_index: object,
                request: TaskRequest,
            ) -> TaskPlan:
                return TaskPlan(
                    task_name="custom",
                    capability="custom",
                    context_package=None,
                )

        registry.register("custom", CustomTask)
        factory = TaskFactory(registry)

        task = factory.create("custom")
        assert isinstance(task, CustomTask)
        assert task.name == "custom"
