"""Base classes for the Task Framework v1.

Architecture
------------

The task framework provides a unified interface for executable development
workflows.  Each task implements the ``Task`` ABC and registers itself
with the ``TaskRegistry``.

Public API
----------

.. code-block:: python

    from packages.tasks.base import Task

    class RefactorTask(Task):

        @property
        def name(self) -> str:
            return "refactor"

        @property
        def capability(self) -> Capability:
            return Capability(name="refactor")

        def plan(self, repository_index, request):
            ...

Constraints
-----------

- Tasks are **stateless** (no instance attributes beyond the ABC).
- Tasks orchestrate existing public APIs only.
- Tasks must not access providers directly, parse repositories,
  implement ranking, planning, or serialization.
- Tasks describe **what should happen**, not **how an LLM performs it**.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex
    from packages.tasks.models import TaskPlan, TaskRequest


class Task(ABC):
    """Abstract base class for all tasks.

    Tasks are stateless orchestration objects.  They receive a repository
    index and a task request, orchestrate existing platform components,
    and return a ``TaskPlan``.

    Subclasses must implement:

    - ``name`` property — unique string identifier (e.g. ``"refactor"``).
    - ``capability`` property — returns the capability name consumed.
    - ``plan()`` method — the planning pipeline.

    Lifecycle
    ---------

    Tasks follow an explicit lifecycle:

    1. ``plan()`` — Produce a ``TaskPlan`` from repository data and request.

    Future lifecycle stages (when needed):

    2. ``validate()`` — Validate the plan against constraints.
    3. ``estimate()`` — Compute execution estimates.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return self.__class__.__name__.lower()

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return self.__class__.__name__.lower()

    def plan(
        self,
        repository_index: RepositoryIndex,
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan from repository data and request.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``TaskPlan``.
        """
        return self._do_plan(repository_index, request)

    @abstractmethod
    def _do_plan(
        self,
        repository_index: RepositoryIndex,
        request: TaskRequest,
    ) -> TaskPlan:
        """Abstract planning implementation.

        Subclasses must override this method to provide their
        actual planning logic.  The public ``plan()`` method
        wraps this with the lifecycle.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``TaskPlan``.
        """
        ...
