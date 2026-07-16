"""Relationship extractor registry.

Maintains a collection of registered relationship extractors and
executes them in a deterministic order.

The registry is the single extension point — new extractors are
registered here and the builder delegates to the registry for
relationship extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.index.models import RepositoryIndex
from packages.repository.relationships.base import RelationshipExtractor
from packages.repository.symbols.models import Relationship, RelationshipType

if TYPE_CHECKING:
    from collections.abc import Sequence


class RelationshipRegistry:
    """Registry of relationship extractors.

    Maintains a ordered list of extractors.  When ``extract()`` is
    called, each registered extractor is invoked in registration order
    and the results are merged and deduplicated.

    Attributes:
        _extractors: Ordered list of registered extractors.
    """

    def __init__(self) -> None:
        """Initialise the registry with no extractors."""
        self._extractors: list[RelationshipExtractor] = []

    def register(self, extractor: RelationshipExtractor) -> None:
        """Register a relationship extractor.

        Extractors are stored in registration order.  Duplicate
        registrations (same extractor instance) are ignored.

        Args:
            extractor: The extractor to register.
        """
        if extractor not in self._extractors:
            self._extractors.append(extractor)

    def extract(
        self,
        repository_index: RepositoryIndex,
    ) -> list[Relationship]:
        """Extract relationships from all registered extractors.

        Each extractor is invoked in registration order.  Results are
        merged and deduplicated — only unique ``(source, target, type)``
        triples are returned.  The final list is sorted by
        ``(source, target, type)`` for deterministic output.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A sorted, deduplicated list of ``Relationship`` objects.
        """
        all_relationships: list[Relationship] = []

        for extractor in self._extractors:
            relationships = extractor.extract(repository_index)
            all_relationships.extend(relationships)

        # Deduplicate by (source, target, type) triple.
        seen: set[tuple[str, str, str]] = set()
        unique: list[Relationship] = []
        for rel in all_relationships:
            key = (rel.source, rel.target, rel.type.value)
            if key not in seen:
                seen.add(key)
                unique.append(rel)

        return sorted(unique, key=lambda r: (r.source, r.target, r.type.value))

    def get_extractors_for_type(
        self,
        relationship_type: RelationshipType,
    ) -> Sequence[RelationshipExtractor]:
        """Return extractors that produce a specific relationship type.

        Args:
            relationship_type: The relationship type to filter by.

        Returns:
            List of extractors whose ``relationship_type`` matches.
        """
        return [
            ext for ext in self._extractors
            if ext.relationship_type == relationship_type
        ]

    @property
    def extractors(self) -> Sequence[RelationshipExtractor]:
        """Return all registered extractors.

        Returns:
            Ordered list of registered extractors.
        """
        return tuple(self._extractors)
