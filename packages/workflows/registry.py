"""Workflow Registry.

Manages registration, lookup, and discovery of workflows.

Architecture
------------

The registry is the single source of truth for workflow registration.
It maintains deterministic ordering using an ordered dict.

Public API
----------

.. code-block:: python

    from packages.workflows.registry import WorkflowRegistry

    registry = WorkflowRegistry()
    registry.register("implement-feature", ImplementFeatureWorkflow)
    workflow_cls = registry.get("implement-feature")
    names = registry.all()

Constraints
-----------

- Stores workflow **classes**, not instances.
- Prevents duplicate registration.
- Returns deterministic ordering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from packages.workflows.base import Workflow  # noqa: F401


class WorkflowRegistry:
    """Registry for workflow classes.

    Responsibilities:
        - Register workflows by name.
        - Prevent duplicate registration.
        - Lookup by name.
        - List registered workflows in deterministic order.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._registry: dict[str, Type["Workflow"]] = {}

    def register(self, name: str, workflow_class: Type["Workflow"]) -> None:
        """Register a workflow class under the given name.

        Args:
            name: Unique identifier for the workflow.
            workflow_class: The workflow class to register.

        Raises:
            ValueError: If a workflow with the same name is already
                registered.
        """
        if name in self._registry:
            raise ValueError(
                f"Workflow '{name}' is already registered. "
                f"Duplicate registration is not allowed."
            )
        self._registry[name] = workflow_class

    def get(self, name: str) -> Type["Workflow"] | None:
        """Lookup a workflow class by name.

        Args:
            name: The workflow name.

        Returns:
            The workflow class, or ``None`` if not found.
        """
        return self._registry.get(name)

    def has(self, name: str) -> bool:
        """Check whether a workflow is registered.

        Args:
            name: The workflow name.

        Returns:
            ``True`` if registered, ``False`` otherwise.
        """
        return name in self._registry

    def all(self) -> list[str]:
        """Return all registered workflow names in deterministic order.

        Returns:
            Sorted list of workflow names.
        """
        return sorted(self._registry.keys())

    def unregister(self, name: str) -> None:
        """Remove a workflow from the registry.

        Args:
            name: The workflow name to remove.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._registry:
            raise KeyError(
                f"Workflow '{name}' is not registered. "
                f"Cannot unregister a non-existent workflow."
            )
        del self._registry[name]
