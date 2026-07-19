"""Tests for the Workflow Registry.

Verifies:
- Registration and lookup
- Duplicate detection
- Unregister
- Deterministic ordering
- Empty registry handling
"""

from __future__ import annotations

import pytest

from packages.tasks.models import TaskRequest
from packages.workflows.base import Workflow
from packages.workflows.models import WorkflowMetrics, WorkflowNode, WorkflowPlan
from packages.workflows.registry import WorkflowRegistry


# Test fixture workflow
class TestWorkflowA(Workflow):
    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return ()

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        return WorkflowPlan(workflow_name=self.name, task_plans=())

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        return WorkflowMetrics()


class TestWorkflowB(Workflow):
    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return ()

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        return WorkflowPlan(workflow_name=self.name, task_plans=())

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        return WorkflowMetrics()


class TestWorkflowC(Workflow):
    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return ()

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        return WorkflowPlan(workflow_name=self.name, task_plans=())

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        return WorkflowMetrics()


# ---------------------------------------------------------------------------
# Test: Empty Registry
# ---------------------------------------------------------------------------


class TestEmptyRegistry:
    """Tests for empty registry behavior."""

    def test_empty_registry_all(self) -> None:
        registry = WorkflowRegistry()
        assert registry.all() == []

    def test_empty_registry_get(self) -> None:
        registry = WorkflowRegistry()
        assert registry.get("nonexistent") is None

    def test_empty_registry_has(self) -> None:
        registry = WorkflowRegistry()
        assert registry.has("nonexistent") is False


# ---------------------------------------------------------------------------
# Test: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for workflow registration."""

    def test_register_single(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        assert registry.has("workflow-a")
        assert registry.get("workflow-a") is TestWorkflowA

    def test_register_multiple(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        registry.register("workflow-b", TestWorkflowB)
        registry.register("workflow-c", TestWorkflowC)

        assert registry.has("workflow-a")
        assert registry.has("workflow-b")
        assert registry.has("workflow-c")

    def test_register_returns_nothing(self) -> None:
        registry = WorkflowRegistry()
        result = registry.register("workflow-a", TestWorkflowA)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Duplicate Detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate registration detection."""

    def test_duplicate_registration_raises(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("workflow-a", TestWorkflowB)

    def test_different_names_allowed(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        registry.register("workflow-b", TestWorkflowB)  # Different name

        assert registry.has("workflow-a")
        assert registry.has("workflow-b")


# ---------------------------------------------------------------------------
# Test: Lookup
# ---------------------------------------------------------------------------


class TestLookup:
    """Tests for workflow lookup."""

    def test_get_existing(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)

        result = registry.get("workflow-a")
        assert result is TestWorkflowA

    def test_get_nonexistent(self) -> None:
        registry = WorkflowRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_has_existing(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        assert registry.has("workflow-a") is True

    def test_has_nonexistent(self) -> None:
        registry = WorkflowRegistry()
        assert registry.has("nonexistent") is False


# ---------------------------------------------------------------------------
# Test: Unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    """Tests for workflow unregistration."""

    def test_unregister_existing(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        registry.unregister("workflow-a")

        assert registry.has("workflow-a") is False
        assert registry.get("workflow-a") is None

    def test_unregister_nonexistent_raises(self) -> None:
        registry = WorkflowRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("nonexistent")

    def test_unregister_updates_all(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        registry.register("workflow-b", TestWorkflowB)

        registry.unregister("workflow-a")

        assert registry.has("workflow-a") is False
        assert registry.has("workflow-b") is True
        assert registry.all() == ["workflow-b"]


# ---------------------------------------------------------------------------
# Test: Deterministic Ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering of registered workflows."""

    def test_all_returns_sorted(self) -> None:
        registry = WorkflowRegistry()
        registry.register("z-workflow", TestWorkflowC)
        registry.register("a-workflow", TestWorkflowA)
        registry.register("m-workflow", TestWorkflowB)

        all_workflows = registry.all()
        assert all_workflows == ["a-workflow", "m-workflow", "z-workflow"]

    def test_all_preserves_insertion_order_for_same_prefix(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-1", TestWorkflowA)
        registry.register("workflow-2", TestWorkflowB)
        registry.register("workflow-3", TestWorkflowC)

        all_workflows = registry.all()
        assert all_workflows == ["workflow-1", "workflow-2", "workflow-3"]


# ---------------------------------------------------------------------------
# Test: Registry Stores Classes Not Instances
# ---------------------------------------------------------------------------


class TestStoresClasses:
    """Tests that registry stores classes, not instances."""

    def test_stores_class(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)

        result = registry.get("workflow-a")
        assert result is TestWorkflowA
        assert isinstance(result, type)

    def test_can_instantiate_retrieved_class(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)

        workflow_cls = registry.get("workflow-a")
        instance = workflow_cls()

        assert isinstance(instance, TestWorkflowA)
        assert isinstance(instance, Workflow)
