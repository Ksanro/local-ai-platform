"""Operation registry — Manages engineering operation handlers.

Maps operation types to their corresponding handler functions and
default workflow names. Provides registration, lookup, and discovery
capabilities for the controller.

Architecture
------------

OperationRegistry --> Maps OperationType --> Handler Functions

Responsibilities
----------------

- Register operation handlers.
- Lookup handlers by operation type.
- Discover registered operations.
- Provide default workflow mapping.
- Prevent duplicate registrations.

Non-responsibilities
--------------------

- Must NOT execute operations.
- Must NOT process requests.
- Must NOT modify requests.
- Must NOT access file system.
- Must NOT invoke providers.

Public API
----------

.. code-block:: python

    from packages.controller.registry import OperationRegistry

    registry = OperationRegistry()

    # Register a handler
    registry.register_handler(
        operation="execute",
        handler=execute_fn,
        default_workflow="default-engineering",
    )

    # Lookup handler
    handler = registry.get_handler("execute")

    # Get default workflow
    workflow = registry.get_default_workflow("execute")

    # List all operations
    operations = registry.list_operations()

"""

from __future__ import annotations

from typing import Any, Callable, Optional

from packages.controller.models import OperationType

__all__ = [
    "OperationRegistry",
    "OperationHandler",
]

# Type alias for operation handlers
# Handlers take an EngineeringRequest and return an EngineeringResult
OperationHandler = Callable[[Any], Any]


class OperationRegistry:
    """Manages engineering operation handlers and workflow mappings.

    Provides registration, lookup, and discovery of operation handlers.
    Each operation type maps to a handler function and a default workflow.

    The registry is thread-safe and immutable after registration.

    Attributes:
        _handlers: Mapping of operation type to handler function.
        _workflows: Mapping of operation type to default workflow name.
    """

    def __init__(self) -> None:
        """Initialize the operation registry."""
        self._handlers: dict[OperationType, OperationHandler] = {}
        self._workflows: dict[OperationType, str] = {}

    def register_handler(
        self,
        operation: OperationType,
        handler: OperationHandler,
        default_workflow: str,
    ) -> None:
        """Register an operation handler with its default workflow.

        Args:
            operation: The operation type to register.
            handler: The handler function for this operation.
            default_workflow: The default workflow name for this operation.

        Raises:
            ValueError: If the operation is already registered.
        """
        if operation in self._handlers:
            raise ValueError(
                f"Operation '{operation.value}' is already registered. "
                "Use unregister_handler() first if you want to replace it."
            )

        self._handlers[operation] = handler
        self._workflows[operation] = default_workflow

    def unregister_handler(
        self,
        operation: OperationType,
    ) -> None:
        """Unregister an operation handler.

        Args:
            operation: The operation type to unregister.

        Raises:
            ValueError: If the operation is not registered.
        """
        if operation not in self._handlers:
            raise ValueError(
                f"Operation '{operation.value}' is not registered."
            )

        del self._handlers[operation]
        self._workflows.pop(operation, None)

    def get_handler(
        self,
        operation: OperationType,
    ) -> Optional[OperationHandler]:
        """Get the handler for an operation type.

        Args:
            operation: The operation type to lookup.

        Returns:
            The handler function, or None if not registered.
        """
        return self._handlers.get(operation)

    def get_default_workflow(
        self,
        operation: OperationType,
    ) -> Optional[str]:
        """Get the default workflow for an operation type.

        Args:
            operation: The operation type to lookup.

        Returns:
            The default workflow name, or None if not registered.
        """
        return self._workflows.get(operation)

    def list_operations(self) -> tuple[OperationType, ...]:
        """List all registered operations.

        Returns:
            Tuple of registered operation types.
        """
        return tuple(self._handlers.keys())

    def has_operation(
        self,
        operation: OperationType,
    ) -> bool:
        """Check if an operation is registered.

        Args:
            operation: The operation type to check.

        Returns:
            True if the operation is registered, False otherwise.
        """
        return operation in self._handlers

    def remove_operation(
        self,
        operation: OperationType,
    ) -> bool:
        """Remove an operation from the registry.

        Args:
            operation: The operation type to remove.

        Returns:
            True if the operation was removed, False if it wasn't registered.
        """
        if operation in self._handlers:
            del self._handlers[operation]
            self._workflows.pop(operation, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all registered operations."""
        self._handlers.clear()
        self._workflows.clear()

    @property
    def operation_count(self) -> int:
        """Get the number of registered operations.

        Returns:
            The number of registered operations.
        """
        return len(self._handlers)

    def __contains__(self, operation: OperationType) -> bool:
        """Check if an operation is registered (supports 'in' operator).

        Args:
            operation: The operation type to check.

        Returns:
            True if the operation is registered, False otherwise.
        """
        return operation in self._handlers

    def __len__(self) -> int:
        """Get the number of registered operations (supports len() function).

        Returns:
            The number of registered operations.
        """
        return len(self._handlers)

    def __iter__(self):  # type: ignore
        """Iterate over registered operations.

        Yields:
            Registered operation types.
        """
        return iter(self._handlers.keys())