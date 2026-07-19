"""Tests for the Task Registry.

Verifies:
- Registration
- Duplicate detection
- Lookup
- Enumeration
- Unregistration
- Deterministic ordering
- Empty registry behavior
"""

from __future__ import annotations

import pytest

from packages.tasks.base import Task
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
# Test: Empty Registry
# ---------------------------------------------------------------------------


class TestEmptyRegistry:
    """Tests for empty registry behavior."""

    def test_registry_is_empty_on_creation(self) -> None:
        registry = TaskRegistry()
        assert registry.all() == []

    def test_get_returns_none_for_unregistered(self) -> None:
        registry = TaskRegistry()
        assert registry.get("nonexistent") is None

    def test_has_returns_false_for_unregistered(self) -> None:
        registry = TaskRegistry()
        assert registry.has("nonexistent") is False


# ---------------------------------------------------------------------------
# Test: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for task registration."""

    def test_register_single_task(self) -> None:
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        assert registry.has("sample_a")
        assert registry.get("sample_a") is SampleTaskA

    def test_register_multiple_tasks(self) -> None:
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        registry.register("sample_b", SampleTaskB)
        assert registry.has("sample_a")
        assert registry.has("sample_b")
        assert registry.get("sample_a") is SampleTaskA
        assert registry.get("sample_b") is SampleTaskB

    def test_register_preserves_class(self) -> None:
        registry = TaskRegistry()
        registry.register("sample_a", SampleTaskA)
        cls = registry.get("sample_a")
        assert cls is SampleTaskA
        assert issubclass(cls, Task)

    def test_all_returns_sorted_names(self) -> None:
        registry = TaskRegistry()
        registry.register("zebra", SampleTaskA)
        registry.register("alpha", SampleTaskB)
        registry.register("middle", SampleTaskA)

        names = registry.all()
        assert names == ["alpha", "middle", "zebra"]


# ---------------------------------------------------------------------------
# Test: Duplicate Detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate registration detection."""

    def test_duplicate_registration_raises(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("sample", SampleTaskB)

    def test_duplicate_registration_with_same_class(self) -> None:
        """Even registering the same class under the same name should raise."""
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("sample", SampleTaskA)  # type: ignore[arg-type]

    def test_different_names_do_not_conflict(self) -> None:
        registry = TaskRegistry()
        registry.register("task_a", SampleTaskA)
        registry.register("task_b", SampleTaskB)
        # Should not raise
        assert registry.has("task_a")
        assert registry.has("task_b")


# ---------------------------------------------------------------------------
# Test: Lookup
# ---------------------------------------------------------------------------


class TestLookup:
    """Tests for task lookup."""

    def test_get_existing_task(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)
        assert registry.get("sample") is SampleTaskA

    def test_get_nonexistent_task(self) -> None:
        registry = TaskRegistry()
        assert registry.get("nonexistent") is None

    def test_has_existing_task(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)
        assert registry.has("sample") is True

    def test_has_nonexistent_task(self) -> None:
        registry = TaskRegistry()
        assert registry.has("nonexistent") is False


# ---------------------------------------------------------------------------
# Test: Unregistration
# ---------------------------------------------------------------------------


class TestUnregistration:
    """Tests for task unregistration."""

    def test_unregister_existing(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)
        registry.unregister("sample")
        assert registry.has("sample") is False
        assert registry.get("sample") is None

    def test_unregister_existing_removes_from_all(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)
        registry.unregister("sample")
        assert "sample" not in registry.all()

    def test_unregister_nonexistent_raises(self) -> None:
        registry = TaskRegistry()
        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("nonexistent")

    def test_unregister_twice_raises(self) -> None:
        registry = TaskRegistry()
        registry.register("sample", SampleTaskA)
        registry.unregister("sample")

        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("sample")


# ---------------------------------------------------------------------------
# Test: Deterministic Ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering."""

    def test_all_returns_deterministic_order(self) -> None:
        """Repeated calls to all() should return the same order."""
        registry = TaskRegistry()
        registry.register("z_task", SampleTaskA)
        registry.register("a_task", SampleTaskB)
        registry.register("m_task", SampleTaskA)

        order1 = registry.all()
        order2 = registry.all()

        assert order1 == order2
        assert order1 == ["a_task", "m_task", "z_task"]

    def test_ordering_independent_of_registration_order(self) -> None:
        """Registration order should not affect all() output."""
        registry1 = TaskRegistry()
        registry1.register("z", SampleTaskA)
        registry1.register("a", SampleTaskB)
        registry1.register("m", SampleTaskA)

        registry2 = TaskRegistry()
        registry2.register("a", SampleTaskB)
        registry2.register("m", SampleTaskA)
        registry2.register("z", SampleTaskA)

        assert registry1.all() == registry2.all()
