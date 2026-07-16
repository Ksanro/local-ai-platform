"""Abstract base class for relationship extractors.

Defines the interface that all relationship extractors must implement.
Extractors are language-independent — they operate on the existing
RepositoryIndex and produce Relationship objects.

No extractor may:

- modify the RepositoryIndex
- perform ranking
- build prompts
- estimate tokens
- access providers
- perform inference
- call LLMs

Only repository metadata is analysed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Relationship, RelationshipType


class RelationshipExtractor(ABC):
    """Abstract base class for relationship extractors.

    Subclasses implement language-independent relationship extraction
    logic.  The ``extract`` method receives a ``RepositoryIndex`` and
    returns a list of ``Relationship`` objects.

    Extractors must be deterministic — repeated extraction on the same
    repository must produce identical relationships, sorted by
    ``(source, target)``.

    Attributes:
        relationship_type: The type of relationships this extractor produces.
    """

    @property
    @abstractmethod
    def relationship_type(self) -> RelationshipType:
        """The type of relationships this extractor produces.

        Returns:
            The relationship type (e.g. ``RelationshipType.CALLS``).
        """
        ...

    @abstractmethod
    def extract(
        self,
        repository_index: RepositoryIndex,
    ) -> list[Relationship]:
        """Extract relationships from a repository index.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A sorted list of ``Relationship`` objects.  Duplicates are
            removed — only unique ``(source, target, type)`` triples are
            returned.
        """
        ...
