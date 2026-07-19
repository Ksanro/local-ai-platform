"""Workflow base classes.

Defines the ``Workflow`` abstract base class that all workflows inherit.
Workflows compose Tasks into deterministic execution graphs.

Architecture
------------

Workflow
    │
    ├── name: str
    ├── workflow_nodes: tuple[WorkflowNode, ...]
    ├── validate()
    ├── plan()
    └── estimate()

    │
    ▼
    WorkflowNode (id, task, depends_on)

Constraints
-----------

- Workflows are **immutable** (nodes tuple is fixed).
- Workflows are **stateless** (no instance attributes beyond the ABC).
- Workflows orchestrate existing public APIs only.
- Workflows must not access providers directly, parse repositories,
  implement ranking, planning, or serialization.

Public API
----------

.. code-block:: python

    from packages.workflows.base import Workflow
    from packages.workflows.models import WorkflowNode

    class MyWorkflow(Workflow):

        @property
        def name(self) -> str:
            return "my-workflow"

        @property
        def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
            return (
                WorkflowNode(
                    node_id="architecture",
                    task=ArchitectureReviewTask,
                    depends_on=(),
                ),
                WorkflowNode(
                    node_id="implementation",
                    task=ImplementationTask,
                    depends_on=("architecture",),
                ),
            )

        def _do_plan(self, repository_index, request):
            ...

        def _do_estimate(self, repository_index, request):
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex  # noqa: F401
    from packages.tasks.models import TaskPlan, TaskRequest  # noqa: F401
    from packages.workflows.models import WorkflowMetrics, WorkflowPlan  # noqa: F401


class Workflow(ABC):
    """Abstract base class for all workflows.

    Workflows are stateless orchestration objects.  They compose Tasks
    into deterministic execution graphs using ``WorkflowNode`` definitions.

    Subclasses must implement:

    - ``name`` property — unique workflow name (e.g. ``"implement-feature"``).
    - ``workflow_nodes`` property — tuple of ``WorkflowNode`` definitions.
    - ``_do_plan()`` method — the planning pipeline.
    - ``_do_estimate()`` method — the estimation pipeline.

    Lifecycle
    ---------

    Workflows follow an explicit lifecycle:

    1. ``validate()`` — Validate the request against workflow constraints.
    2. ``plan()`` — Generate a ``WorkflowPlan`` from repository data and request.
    3. ``estimate()`` — Compute execution estimates.
    """

    @property
    def name(self) -> str:
        """Unique name of this workflow.

        Returns:
            The workflow name string.
        """
        return self.__class__.__name__.lower()

    @property
    @abstractmethod
    def workflow_nodes(self) -> tuple[object, ...]:
        """Execution nodes defining the workflow DAG.

        Returns:
            Tuple of ``WorkflowNode`` instances.
        """
        ...

    def validate(
        self,
        request: object,
    ) -> None:
        """Validate the request against workflow constraints.

        Subclasses may override this method to add custom validation.

        Args:
            request: The task request containing query and context.
        """
        self._validate_request(request)

    def plan(
        self,
        repository_index: object,
        request: object,
    ) -> object:
        """Generate a WorkflowPlan from repository data and request.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``WorkflowPlan``.
        """
        self.validate(request)
        return self._do_plan(repository_index, request)

    def estimate(
        self,
        repository_index: object,
        request: object,
    ) -> object:
        """Compute execution estimates for the workflow.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``WorkflowMetrics``.
        """
        self.validate(request)
        return self._do_estimate(repository_index, request)

    def _validate_request(self, request: object) -> None:
        """Default request validation.

        Subclasses can override to add custom validation logic.

        Args:
            request: The task request to validate.
        """
        if not hasattr(request, "query") or not request.query:
            raise ValueError("Task request query cannot be empty.")

    @abstractmethod
    def _do_plan(
        self,
        repository_index: object,
        request: object,
    ) -> object:
        """Abstract planning implementation.

        Subclasses must override this method to provide their
        actual planning logic.  The public ``plan()`` method
        wraps this with the lifecycle.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``WorkflowPlan``.
        """
        ...

    @abstractmethod
    def _do_estimate(
        self,
        repository_index: object,
        request: object,
    ) -> object:
        """Abstract estimation implementation.

        Subclasses must override this method to provide their
        actual estimation logic.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            An immutable ``WorkflowMetrics``.
        """
        ...
