"""Base classes for the Execution Planner v1.

Architecture
------------

The execution planner provides a translation layer that converts
``WorkflowPlan`` objects into ``ExecutionPlan`` objects consumable
by coding agents.

Public API
----------

.. code-block:: python

    from packages.execution.base import ExecutionPlannerBase

Constraints
-----------

- The planner is a translation layer only.
- It owns no repository intelligence.
- It owns no workflow logic.
- It owns no task logic.

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.execution.models import ExecutionPlan  # noqa: F401
    from packages.workflows.models import WorkflowPlan  # noqa: F401


class ExecutionPlannerBase(ABC):
    """Abstract base class for execution planners.

    Execution planners convert ``WorkflowPlan`` objects into
    ``ExecutionPlan`` objects.  The public ``plan`` method wraps
    the abstract ``_do_plan`` with the translation lifecycle.

    Subclasses must implement:

    - ``_do_plan()`` method — the actual planning logic.

    Lifecycle
    ---------

    1. ``plan()`` — Convert a ``WorkflowPlan`` to an ``ExecutionPlan``.
    """

    def plan(self, workflow_plan: WorkflowPlan) -> ExecutionPlan:
        """Convert a WorkflowPlan to an ExecutionPlan.

        Args:
            workflow_plan: The workflow plan to convert.

        Returns:
            An immutable ``ExecutionPlan``.
        """
        return self._do_plan(workflow_plan)

    @abstractmethod
    def _do_plan(self, workflow_plan: WorkflowPlan) -> ExecutionPlan:
        """Abstract planning implementation.

        Subclasses must override this method to provide their
        actual planning logic.  The public ``plan()`` method
        wraps this with the translation lifecycle.

        Args:
            workflow_plan: The workflow plan to convert.

        Returns:
            An immutable ``ExecutionPlan``.
        """
        ...
