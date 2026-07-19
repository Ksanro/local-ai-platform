"""Task Registry.

Manages registration, lookup, and discovery of tasks.

Architecture
------------

The registry is the single source of truth for task registration.
It maintains deterministic ordering using an ordered ``dict``.

Public API
----------

.. code-block:: python

    from packages.tasks.registry import TaskRegistry

    registry = TaskRegistry()
    registry.register("refactor", RefactorTask)
    task_cls = registry.get("refactor")
    names = registry.all()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from packages.tasks.base import Task


class TaskRegistry:
    """Registry for task classes.

    Responsibilities:
        - Register tasks by name.
        - Prevent duplicate registration.
        - Lookup by name.
        - List registered tasks in deterministic order.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._registry: dict[str, Type[Task]] = {}

    def register(self, name: str, task_class: Type[Task]) -> None:
        """Register a task class under the given name.

        Args:
            name: Unique identifier for the task.
            task_class: The task class to register.

        Raises:
            ValueError: If a task with the same name is already
                registered.
        """
        if name in self._registry:
            raise ValueError(
                f"Task '{name}' is already registered. "
                f"Duplicate registration is not allowed."
            )
        self._registry[name] = task_class

    def get(self, name: str) -> Type[Task] | None:
        """Lookup a task class by name.

        Args:
            name: The task name.

        Returns:
            The task class, or ``None`` if not found.
        """
        return self._registry.get(name)

    def has(self, name: str) -> bool:
        """Check whether a task is registered.

        Args:
            name: The task name.

        Returns:
            ``True`` if registered, ``False`` otherwise.
        """
        return name in self._registry

    def all(self) -> list[str]:
        """Return all registered task names in deterministic order.

        Returns:
            Sorted list of task names.
        """
        return sorted(self._registry.keys())

    def unregister(self, name: str) -> None:
        """Remove a task from the registry.

        Args:
            name: The task name to remove.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._registry:
            raise KeyError(
                f"Task '{name}' is not registered. "
                f"Cannot unregister a non-existent task."
            )
        del self._registry[name]
