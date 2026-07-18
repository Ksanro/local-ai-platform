"""Base classes for the Capability Framework v1.

Architecture
------------

The capability framework provides a unified interface for all platform
capabilities.  Each capability implements the ``Capability`` ABC and
registers itself with the ``CapabilityRegistry``.

Public API
----------

.. code-block:: python

    from packages.capabilities.base import Capability, PlannerIntent

    class DebugCapability(Capability):

        @property
        def name(self) -> str:
            return "debug"

        @property
        def intent(self) -> PlannerIntent:
            return PlannerIntent.DEBUG

        def execute(self, query, repository_index):
            ...

Constraints
-----------

- Capabilities are **stateless** (no instance attributes).
- Capabilities orchestrate existing public APIs only.
- Capabilities must not access providers directly, parse repositories,
  implement ranking, planning, or serialization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.capabilities.models import CapabilityResult
    from packages.capabilities.profiles import RetrievalProfile
    from packages.repository.index.models import RepositoryIndex


class PlannerIntent(str, Enum):
    """Planner intent enum.

    Each capability maps to exactly one intent value.  Future capabilities
    (Debug, Review, Refactor, Implement, GenerateTests) will add their own
    intent values here.
    """

    EXPLAIN = "EXPLAIN"
    DEBUG = "DEBUG"
    REVIEW = "REVIEW"
    REFACTOR = "REFACTOR"
    IMPLEMENT = "IMPLEMENT"
    GENERATE_TESTS = "GENERATE_TESTS"


class Capability(ABC):
    """Abstract base class for all capabilities.

    Capabilities are stateless orchestration objects.  They receive a query
    and a repository index, orchestrate existing platform components, and
    return a ``CapabilityResult``.

    Subclasses must implement:

    - ``name`` property – unique string identifier (e.g. ``"explain"``).
    - ``intent`` property – returns the corresponding ``PlannerIntent``.
    - ``profile`` property – returns the ``RetrievalProfile`` for retrieval intent.
    - ``execute()`` method – the orchestration pipeline.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return self.__class__.__name__

    @property
    @abstractmethod
    def intent(self) -> PlannerIntent:
        """Planner intent for this capability.

        Returns:
            The PlannerIntent enum value.
        """
        ...

    @property
    @abstractmethod
    def profile(self) -> RetrievalProfile:
        """Retrieval profile for this capability.

        Returns the immutable ``RetrievalProfile`` that describes what
        repository context this capability needs.

        Returns:
            The RetrieProfile instance.
        """
        ...

    @abstractmethod
    def execute(
        self,
        query: str,
        repository_index: RepositoryIndex,
    ) -> CapabilityResult:
        """Execute the capability pipeline.

        Args:
            query: The user's natural language query.
            repository_index: The repository index to search.

        Returns:
            An immutable ``CapabilityResult``.
        """
        ...
