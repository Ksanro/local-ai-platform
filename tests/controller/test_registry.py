"""Tests for operation registry.

Tests OperationRegistry class and all registry operations.
"""

import pytest

from packages.controller.models import OperationType
from packages.controller.registry import OperationRegistry


def dummy_handler(request):
    """Dummy handler function for testing."""
    return {"status": "ok"}


class TestOperationRegistry:
    """Test OperationRegistry class."""

    def test_initial_state(self):
        """Test registry starts empty."""
        registry = OperationRegistry()
        assert registry.operation_count == 0
        assert len(registry) == 0

    def test_register_handler(self):
        """Test registering a handler."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="default-engineering",
        )
        assert registry.operation_count == 1
        assert registry.get_handler(OperationType.EXECUTE) == dummy_handler
        assert registry.get_default_workflow(OperationType.EXECUTE) == "default-engineering"

    def test_duplicate_registration_raises(self):
        """Test that duplicate registration raises ValueError."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="default-workflow",
        )
        with pytest.raises(ValueError, match="already registered"):
            registry.register_handler(
                operation=OperationType.EXECUTE,
                handler=dummy_handler,
                default_workflow="another-workflow",
            )

    def test_unregister_handler(self):
        """Test unregistering a handler."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="default-workflow",
        )
        registry.unregister_handler(OperationType.EXECUTE)
        assert registry.operation_count == 0
        assert registry.get_handler(OperationType.EXECUTE) is None

    def test_unregister_nonexistent_raises(self):
        """Test unregistering non-existent handler raises ValueError."""
        registry = OperationRegistry()
        with pytest.raises(ValueError, match="not registered"):
            registry.unregister_handler(OperationType.EXECUTE)

    def test_get_nonexistent_handler(self):
        """Test getting non-existent handler returns None."""
        registry = OperationRegistry()
        result = registry.get_handler(OperationType.EXECUTE)
        assert result is None

    def test_get_nonexistent_workflow(self):
        """Test getting non-existent workflow returns None."""
        registry = OperationRegistry()
        result = registry.get_default_workflow(OperationType.EXECUTE)
        assert result is None

    def test_list_operations(self):
        """Test listing all registered operations."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        registry.register_handler(
            operation=OperationType.REVIEW,
            handler=dummy_handler,
            default_workflow="workflow2",
        )
        operations = registry.list_operations()
        assert len(operations) == 2
        assert OperationType.EXECUTE in operations
        assert OperationType.REVIEW in operations

    def test_has_operation(self):
        """Test checking if operation is registered."""
        registry = OperationRegistry()
        assert not registry.has_operation(OperationType.EXECUTE)
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        assert registry.has_operation(OperationType.EXECUTE)

    def test_remove_operation(self):
        """Test removing an operation."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        result = registry.remove_operation(OperationType.EXECUTE)
        assert result is True
        assert registry.operation_count == 0

    def test_remove_nonexistent_operation(self):
        """Test removing non-existent operation returns False."""
        registry = OperationRegistry()
        result = registry.remove_operation(OperationType.EXECUTE)
        assert result is False

    def test_clear(self):
        """Test clearing all operations."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        registry.register_handler(
            operation=OperationType.REVIEW,
            handler=dummy_handler,
            default_workflow="workflow2",
        )
        registry.clear()
        assert registry.operation_count == 0

    def test_contains_operator(self):
        """Test 'in' operator support."""
        registry = OperationRegistry()
        assert OperationType.EXECUTE not in registry
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        assert OperationType.EXECUTE in registry

    def test_iteration(self):
        """Test iteration over operations."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        operations = list(registry)
        assert len(operations) == 1
        assert operations[0] == OperationType.EXECUTE


class TestRegistryWithAllOperations:
    """Test registry with all operation types."""

    def test_register_all_operations(self):
        """Test registering all operation types."""
        registry = OperationRegistry()
        for op in OperationType:
            registry.register_handler(
                operation=op,
                handler=dummy_handler,
                default_workflow=f"workflow-{op.value}",
            )
        assert registry.operation_count == 6

    def test_lookup_all_operations(self):
        """Test looking up all registered operations."""
        registry = OperationRegistry()
        for op in OperationType:
            registry.register_handler(
                operation=op,
                handler=dummy_handler,
                default_workflow=f"workflow-{op.value}",
            )
        for op in OperationType:
            assert registry.get_handler(op) == dummy_handler
            assert registry.get_default_workflow(op) == f"workflow-{op.value}"


class TestRegistryEdgeCases:
    """Test registry edge cases."""

    def test_multiple_unregister_same_handler(self):
        """Test that unregistering twice raises error."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        registry.unregister_handler(OperationType.EXECUTE)
        with pytest.raises(ValueError):
            registry.unregister_handler(OperationType.EXECUTE)

    def test_workflow_removed_with_handler(self):
        """Test that workflow mapping is removed with handler."""
        registry = OperationRegistry()
        registry.register_handler(
            operation=OperationType.EXECUTE,
            handler=dummy_handler,
            default_workflow="workflow1",
        )
        assert registry.get_default_workflow(OperationType.EXECUTE) == "workflow1"
        registry.unregister_handler(OperationType.EXECUTE)
        assert registry.get_default_workflow(OperationType.EXECUTE) is None