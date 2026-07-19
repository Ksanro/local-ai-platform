"""Workflow Factory.

Creates workflow instances through the registry.

Architecture
------------

The factory delegates all lookup to the ``WorkflowRegistry``.  It never
hardcodes workflow classes — the registry owns the mapping.

Public API
----------

.. code-block:: python

    from packages.workflows.factory import WorkflowFactory
    from packages.workflows.registry import WorkflowRegistry

    registry = WorkflowRegistry()
    registry.register("implement-feature", ImplementFeatureWorkflow)

    factory = WorkflowFactory(registry)
    workflow = factory.create("implement-feature")

Constraints
-----------

- No hardcoded workflow classes.
- All lookup goes through the registry.
- Deterministic error messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.workflows.registry import WorkflowRegistry

if TYPE_CHECKING:
    from packages.workflows.base import Workflow  # noqa: F401


class WorkflowFactory:
    """Factory for creating workflow instances.

    Responsibilities:
        - Create workflow instances via the registry.
        - Validate registration before creation.
        - Raise deterministic exceptions for unregistered names.

    The factory never hardcodes workflow classes.  All lookup goes
    through the registry.
    """

    def __init__(self, registry: WorkflowRegistry) -> None:
        """Initialize the factory with a registry.

        Args:
            registry: The workflow registry to use for lookups.
        """
        self._registry = registry

    def create(self, name: str) -> Workflow:
        """Create a workflow instance by name.

        Args:
            name: The workflow name to create.

        Returns:
            An instance of the workflow class.

        Raises:
            ValueError: If the workflow name is not registered.
        """
        workflow_class = self._registry.get(name)
        if workflow_class is None:
            raise ValueError(
                f"Workflow '{name}' is not registered. "
                f"Available workflows: {self._registry.all()}"
            )
        return workflow_class()
