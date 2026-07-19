"""Tests for the Workflow Factory.

Verifies:
- Factory creation
- Workflow creation by name
- Unregistered name handling
- Deterministic error messages
- Registry integration
"""

from __future__ import annotations

import pytest

from packages.tasks.models import TaskRequest
from packages.workflows.base import Workflow
from packages.workflows.factory import WorkflowFactory
from packages.workflows.models import WorkflowMetrics, WorkflowNode, WorkflowPlan
from packages.workflows.registry import WorkflowRegistry


# Test fixture workflows
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


# ---------------------------------------------------------------------------
# Test: Factory Creation
# ---------------------------------------------------------------------------


class TestFactoryCreation:
    """Tests for factory initialization."""

    def test_factory_with_registry(self) -> None:
        registry = WorkflowRegistry()
        factory = WorkflowFactory(registry)
        assert factory._registry is registry

    def test_factory_with_empty_registry(self) -> None:
        registry = WorkflowRegistry()
        factory = WorkflowFactory(registry)
        assert factory._registry is registry


# ---------------------------------------------------------------------------
# Test: Workflow Creation
# ---------------------------------------------------------------------------


class TestWorkflowCreation:
    """Tests for workflow instance creation."""

    def test_create_registered_workflow(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        factory = WorkflowFactory(registry)

        workflow = factory.create("workflow-a")

        assert isinstance(workflow, TestWorkflowA)
        assert isinstance(workflow, Workflow)

    def test_create_multiple_workflows(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        registry.register("workflow-b", TestWorkflowB)
        factory = WorkflowFactory(registry)

        wa = factory.create("workflow-a")
        wb = factory.create("workflow-b")

        assert isinstance(wa, TestWorkflowA)
        assert isinstance(wb, TestWorkflowB)

    def test_create_returns_new_instance(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        factory = WorkflowFactory(registry)

        instance1 = factory.create("workflow-a")
        instance2 = factory.create("workflow-a")

        assert instance1 is not instance2
        assert isinstance(instance1, TestWorkflowA)
        assert isinstance(instance2, TestWorkflowA)

    def test_create_returns_stateless_instance(self) -> None:
        """Workflows should be stateless."""
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        factory = WorkflowFactory(registry)

        instance1 = factory.create("workflow-a")
        instance2 = factory.create("workflow-a")

        # Both instances should have identical properties
        assert instance1.name == instance2.name
        assert instance1.workflow_nodes == instance2.workflow_nodes


# ---------------------------------------------------------------------------
# Test: Unregistered Name Handling
# ---------------------------------------------------------------------------


class TestUnregisteredName:
    """Tests for unregistered name error handling."""

    def test_create_unregistered_raises(self) -> None:
        registry = WorkflowRegistry()
        factory = WorkflowFactory(registry)

        with pytest.raises(ValueError, match="not registered"):
            factory.create("nonexistent")

    def test_create_unregistered_shows_available(self) -> None:
        registry = WorkflowRegistry()
        registry.register("workflow-a", TestWorkflowA)
        factory = WorkflowFactory(registry)

        with pytest.raises(ValueError) as exc_info:
            factory.create("missing-workflow")

        error_msg = str(exc_info.value)
        assert "workflow-a" in error_msg

    def test_create_unregistered_shows_sorted_list(self) -> None:
        registry = WorkflowRegistry()
        registry.register("z-workflow", TestWorkflowB)
        registry.register("a-workflow", TestWorkflowA)
        factory = WorkflowFactory(registry)

        with pytest.raises(ValueError) as exc_info:
            factory.create("missing")

        error_msg = str(exc_info.value)
        # Verify sorted order in error message
        assert "a-workflow" in error_msg
        assert "z-workflow" in error_msg
        assert error_msg.index("a-workflow") < error_msg.index("z-workflow")

    def test_create_unregistered_empty_registry(self) -> None:
        registry = WorkflowRegistry()
        factory = WorkflowFactory(registry)

        with pytest.raises(ValueError, match="not registered"):
            factory.create("nonexistent")


# ---------------------------------------------------------------------------
# Test: Factory Never Hardcodes Classes
# ---------------------------------------------------------------------------


class TestFactoryNoHardcoding:
    """Tests that factory only uses registry."""

    def test_factory_uses_only_registry(self) -> None:
        """Factory should not have any hardcoded workflow classes."""
        registry = WorkflowRegistry()
        registry.register("custom", TestWorkflowA)
        factory = WorkflowFactory(registry)

        workflow = factory.create("custom")
        assert isinstance(workflow, TestWorkflowA)

    def test_factory_fails_for_unknown(self) -> None:
        """Factory should fail for anything not in registry."""
        registry = WorkflowRegistry()
        factory = WorkflowFactory(registry)

        with pytest.raises(ValueError):
            factory.create("anything")


# ---------------------------------------------------------------------------
# Test: Factory with Multiple Registrations
# ---------------------------------------------------------------------------


class TestFactoryMultipleRegistrations:
    """Tests for factory with multiple workflow registrations."""

    def test_create_different_workflows(self) -> None:
        registry = WorkflowRegistry()
        registry.register("a", TestWorkflowA)
        registry.register("b", TestWorkflowB)
        factory = WorkflowFactory(registry)

        wa = factory.create("a")
        wb = factory.create("b")

        assert type(wa) is TestWorkflowA
        assert type(wb) is TestWorkflowB

    def test_create_same_workflow_multiple_times(self) -> None:
        registry = WorkflowRegistry()
        registry.register("a", TestWorkflowA)
        factory = WorkflowFactory(registry)

        instances = [factory.create("a") for _ in range(5)]

        for instance in instances:
            assert isinstance(instance, TestWorkflowA)

        # All should be different instances
        for i in range(len(instances)):
            for j in range(i + 1, len(instances)):
                assert instances[i] is not instances[j]
