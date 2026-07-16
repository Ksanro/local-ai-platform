"""Tests for the RelationshipRegistry.

Verifies:
- registration and retrieval of extractors
- extraction with multiple extractors
- deduplication
- deterministic ordering
- type filtering
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.relationships.base import RelationshipExtractor, RelationshipType
from packages.repository.relationships.registry import RelationshipRegistry
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType as SymbolRelationshipType,
    Symbol,
    SymbolType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


# ------------------------------------------------------------------
# Test extractors
# ------------------------------------------------------------------


class MockExtractorA(RelationshipExtractor):
    """Mock extractor that produces type A relationships."""

    @property
    def relationship_type(self) -> RelationshipType:
        return RelationshipType.CALLS

    def extract(self, repository_index: RepositoryIndex) -> list[Relationship]:
        return [
            Relationship(
                source="a.caller",
                target="a.callee",
                type=SymbolRelationshipType.CALLS,
            ),
        ]


class MockExtractorB(RelationshipExtractor):
    """Mock extractor that produces type B relationships."""

    @property
    def relationship_type(self) -> RelationshipType:
        return RelationshipType.CALLS

    def extract(self, repository_index: RepositoryIndex) -> list[Relationship]:
        return [
            Relationship(
                source="b.caller",
                target="b.callee",
                type=SymbolRelationshipType.CALLS,
            ),
        ]


class MockDuplicateExtractor(RelationshipExtractor):
    """Mock extractor that produces duplicate relationships."""

    @property
    def relationship_type(self) -> RelationshipType:
        return RelationshipType.CALLS

    def extract(self, repository_index: RepositoryIndex) -> list[Relationship]:
        return [
            Relationship(
                source="a.caller",
                target="a.callee",
                type=SymbolRelationshipType.CALLS,
            ),
        ]


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def registry() -> RelationshipRegistry:
    """Return an empty RelationshipRegistry."""
    return RelationshipRegistry()


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


class TestRegistration:
    """Tests for extractor registration."""

    def test_empty_registry(self, registry: RelationshipRegistry) -> None:
        """New registry should have no extractors."""
        assert len(registry.extractors) == 0

    def test_register_one_extractor(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Should be able to register one extractor."""
        extractor = MockExtractorA()
        registry.register(extractor)
        assert len(registry.extractors) == 1
        assert registry.extractors[0] is extractor

    def test_register_multiple_extractors(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Should be able to register multiple extractors."""
        a = MockExtractorA()
        b = MockExtractorB()
        registry.register(a)
        registry.register(b)
        assert len(registry.extractors) == 2
        assert registry.extractors[0] is a
        assert registry.extractors[1] is b

    def test_duplicate_registration_ignored(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Registering the same extractor twice should be ignored."""
        extractor = MockExtractorA()
        registry.register(extractor)
        registry.register(extractor)
        assert len(registry.extractors) == 1

    def test_different_extractors_same_type(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Different extractors with the same type should both be registered."""
        a = MockExtractorA()
        b = MockExtractorB()
        registry.register(a)
        registry.register(b)
        assert len(registry.extractors) == 2


# ------------------------------------------------------------------
# Extraction
# ------------------------------------------------------------------


class TestExtraction:
    """Tests for relationship extraction."""

    def test_empty_registry_produces_no_relationships(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Empty registry should produce no relationships."""
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(module_count=0, class_count=0, function_count=0, method_count=0, symbol_count=0),
        )
        relationships = registry.extract(index)
        assert relationships == []

    def test_single_extractor(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Single extractor should produce its relationships."""
        registry.register(MockExtractorA())
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(module_count=0, class_count=0, function_count=0, method_count=0, symbol_count=0),
        )
        relationships = registry.extract(index)
        assert len(relationships) == 1
        assert relationships[0].source == "a.caller"
        assert relationships[0].target == "a.callee"

    def test_multiple_extractors(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Multiple extractors should all produce their relationships."""
        registry.register(MockExtractorA())
        registry.register(MockExtractorB())
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(module_count=0, class_count=0, function_count=0, method_count=0, symbol_count=0),
        )
        relationships = registry.extract(index)
        assert len(relationships) == 2

    def test_deduplication(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Duplicate relationships should be deduplicated."""
        registry.register(MockExtractorA())
        registry.register(MockDuplicateExtractor())
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(module_count=0, class_count=0, function_count=0, method_count=0, symbol_count=0),
        )
        relationships = registry.extract(index)
        # Both extractors produce the same relationship, should be deduplicated
        assert len(relationships) == 1

    def test_deterministic_ordering(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Relationships should be sorted by (source, target, type)."""
        registry.register(MockExtractorB())
        registry.register(MockExtractorA())
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(module_count=0, class_count=0, function_count=0, method_count=0, symbol_count=0),
        )
        relationships = registry.extract(index)
        # Should be sorted by source, then target
        sources = [r.source for r in relationships]
        assert sources == sorted(sources)


# ------------------------------------------------------------------
# Type filtering
# ------------------------------------------------------------------


class TestTypeFiltering:
    """Tests for type-based extractor filtering."""

    def test_get_extractors_for_type(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Should return extractors matching a specific type."""
        a = MockExtractorA()
        b = MockExtractorB()
        registry.register(a)
        registry.register(b)

        callers = registry.get_extractors_for_type(RelationshipType.CALLS)
        assert len(callers) == 2

    def test_get_extractors_for_unknown_type(
        self,
        registry: RelationshipRegistry,
    ) -> None:
        """Should return empty list for unknown type."""
        registry.register(MockExtractorA())
        from packages.repository.symbols.models import RelationshipType as RT

        # INHERITS is a valid type but no extractor produces it
        callers = registry.get_extractors_for_type(RT.INHERITS)
        assert callers == []


# ------------------------------------------------------------------
# Extractors property
# ------------------------------------------------------------------


class TestExtractorsProperty:
    """Tests for the extractors property."""

    def test_returns_tuple(self, registry: RelationshipRegistry) -> None:
        """extractors should return a tuple."""
        registry.register(MockExtractorA())
        result = registry.extractors
        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_returns_copy(self, registry: RelationshipRegistry) -> None:
        """extractors should return a copy, not the internal list."""
        extractor = MockExtractorA()
        registry.register(extractor)
        result1 = registry.extractors
        result2 = registry.extractors
        assert result1 is not result2
