"""Task Factory.

Creates task instances through the registry.

Architecture
------------

The factory delegates all lookup to the ``TaskRegistry``.  It never
hardcodes task classes — the registry owns the mapping.

Public API
----------

.. code-block:: python

    from packages.tasks.factory import TaskFactory
    from packages.tasks.registry import TaskRegistry

    registry = TaskRegistry()
    registry.register("refactor", RefactorTask)

    factory = TaskFactory(registry)
    task = factory.create("refactor")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.tasks.registry import TaskRegistry

if TYPE_CHECKING:
    from packages.tasks.base import Task


class TaskFactory:
    """Factory for creating task instances.

    Responsibilities:
        - Create task instances via the registry.
        - Validate registration before creation.
        - Raise deterministic exceptions for unregistered names.

    The factory never hardcodes task classes.  All lookup goes
    through the registry.
    """

    def __init__(self, registry: TaskRegistry) -> None:
        """Initialize the factory with a registry.

        Args:
            registry: The task registry to use for lookups.
        """
        self._registry = registry

    def create(self, name: str) -> Task:
        """Create a task instance by name.

        Args:
            name: The task name to create.

        Returns:
            An instance of the task class.

        Raises:
            ValueError: If the task name is not registered.
        """
        task_class = self._registry.get(name)
        if task_class is None:
            raise ValueError(
                f"Task '{name}' is not registered. "
                f"Available tasks: {self._registry.all()}"
            )
        return task_class()
