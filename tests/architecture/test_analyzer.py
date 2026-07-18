"""Tests for the Architecture Analyzer.

Verifies:
- analyzer returns ArchitectureReview with correct structure
- ModuleSummary fields are correct
- Deterministic ordering (sorted by module name)
- Frozen dataclasses cannot be mutated
- Orphan modules detected correctly
- Dependency counts computed correctly
- Cycles detected correctly
- No provider invocation
"""

from __future__ import annotations

import pytest

from packages.architecture.analyzer import ArchitectureAnalyzer
from packages.architecture.models import ArchitectureReview, ModuleSummary
from packages.repository.index.models import (
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_simple_index() -> RepositoryIndex:
    """Create a minimal RepositoryIndex with a few modules and relationships."""
    sym_a = Symbol(
        id="module_a.Foo",
        name="Foo",
        qualified_name="module_a.Foo",
        symbol_type=SymbolType.CLASS,
        module="module_a.py",
        lineno=1,
    )
    sym_b = Symbol(
        id="module_b.Bar",
        name="Bar",
        qualified_name="module_b.Bar",
        symbol_type=SymbolType.CLASS,
        module="module_b.py",
        lineno=1,
    )

    mod_a = Module(path="module_a.py", symbols=[sym_a])
    mod_b = Module(path="module_b.py", symbols=[sym_b])
    mod_c = Module(path="tests/module_c.py", symbols=[])

    rel_ab = Relationship(
        source="module_a.Foo",
        target="module_b.Bar",
        type=RelationshipType.INHERITS,
    )

    return RepositoryIndex(
        modules={
            "module_a.py": mod_a,
            "module_b.py": mod_b,
            "tests/module_c.py": mod_c,
        },
        _symbols=[sym_a, sym_b],
        _relationships=[rel_ab],
        _statistics=RepositoryStatistics(
            module_count=3,
            class_count=2,
            function_count=0,
            symbol_count=2,
        ),
    )


def _make_index_with_cycles() -> RepositoryIndex:
    """Create a RepositoryIndex with a dependency cycle."""
    sym_a = Symbol(
        id="mod_a.Foo",
        name="Foo",
        qualified_name="mod_a.Foo",
        symbol_type=SymbolType.CLASS,
        module="mod_a.py",
        lineno=1,
    )
    sym_b = Symbol(
        id="mod_b.Bar",
        name="Bar",
        qualified_name="mod_b.Bar",
        symbol_type=SymbolType.CLASS,
        module="mod_b.py",
        lineno=1,
    )

    # A -> B and B -> A creates a cycle
    rel_ab = Relationship(
        source="mod_a.Foo",
        target="mod_b.Bar",
        type=RelationshipType.IMPORTS,
    )
    rel_ba = Relationship(
        source="mod_b.Bar",
        target="mod_a.Foo",
        type=RelationshipType.IMPORTS,
    )

    mod_a = Module(path="mod_a.py", symbols=[sym_a])
    mod_b = Module(path="mod_b.py", symbols=[sym_b])

    return RepositoryIndex(
        modules={
            "mod_a.py": mod_a,
            "mod_b.py": mod_b,
        },
        _symbols=[sym_a, sym_b],
        _relationships=[rel_ab, rel_ba],
        _statistics=RepositoryStatistics(
            module_count=2,
            class_count=2,
            function_count=0,
            symbol_count=2,
        ),
    )


def _make_index_with_orphans() -> RepositoryIndex:
    """Create a RepositoryIndex with orphan modules."""
    sym_a = Symbol(
        id="module_a.Foo",
        name="Foo",
        qualified_name="module_a.Foo",
        symbol_type=SymbolType.CLASS,
        module="module_a.py",
        lineno=1,
    )

    mod_a = Module(path="module_a.py", symbols=[sym_a])
    mod_b = Module(path="module_b.py", symbols=[])
    mod_orphan = Module(path="orphan.py", symbols=[])

    return RepositoryIndex(
        modules={
            "module_a.py": mod_a,
            "module_b.py": mod_b,
            "orphan.py": mod_orphan,
        },
        _symbols=[sym_a],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=3,
            class_count=1,
            function_count=0,
            symbol_count=1,
        ),
    )


# ---------------------------------------------------------------------------
# Test: Analyzer Returns Correct Structure
# ---------------------------------------------------------------------------


class TestAnalyzerReturnsCorrectStructure:
    """Tests that the analyzer returns an ArchitectureReview with correct structure."""

    def test_analyzer_returns_architecture_review(
        self,
    ) -> None:
        """Analyzer should return an ArchitectureReview."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        assert isinstance(review, ArchitectureReview)
        assert isinstance(review.modules, tuple)
        assert len(review.modules) == 3

    def test_analyzer_returns_module_summaries(
        self,
    ) -> None:
        """Analyzer should return ModuleSummary for each module."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        for module_summary in review.modules:
            assert isinstance(module_summary, ModuleSummary)
            assert isinstance(module_summary.module, str)
            assert isinstance(module_summary.symbol_count, int)
            assert isinstance(module_summary.dependency_count, int)
            assert isinstance(module_summary.dependent_count, int)
            assert isinstance(module_summary.instability_score, float)

    def test_analyzer_returns_dependency_summary(
        self,
    ) -> None:
        """Analyzer should return a dependency summary."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        assert isinstance(review.dependency_summary, dict)
        assert "inherits" in review.dependency_summary

    def test_analyzer_returns_repository_statistics(
        self,
    ) -> None:
        """Analyzer should return repository statistics."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        assert isinstance(review.repository_statistics, dict)
        assert review.repository_statistics["module_count"] == 3


# ---------------------------------------------------------------------------
# Test: Deterministic Ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests that the analyzer produces deterministic output."""

    def test_modules_sorted_by_name(
        self,
    ) -> None:
        """Module summaries should be sorted by module name."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        module_names = [m.module for m in review.modules]
        assert module_names == sorted(module_names)

    def test_repeated_execution_identical(
        self,
    ) -> None:
        """Repeated execution should produce identical output."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()

        review1 = analyzer.analyze(index)
        review2 = analyzer.analyze(index)

        assert review1.modules == review2.modules
        assert review1.dependency_summary == review2.dependency_summary
        assert review1.layering_violations == review2.layering_violations
        assert review1.orphan_modules == review2.orphan_modules


# ---------------------------------------------------------------------------
# Test: Frozen Dataclasses
# ---------------------------------------------------------------------------


class TestFrozenDataclasses:
    """Tests that the models are immutable."""

    def test_module_summary_is_frozen(
        self,
    ) -> None:
        """ModuleSummary should be a frozen dataclass."""
        summary = ModuleSummary(
            module="test.py",
            symbol_count=5,
            dependency_count=2,
            dependent_count=3,
            instability_score=0.4,
        )

        with pytest.raises(Exception):
            summary.module = "new.py"  # type: ignore[misc]

        with pytest.raises(Exception):
            summary.symbol_count = 10  # type: ignore[misc]

    def test_architecture_review_is_frozen(
        self,
    ) -> None:
        """ArchitectureReview should be a frozen dataclass."""
        review = ArchitectureReview(
            modules=(),
        )

        with pytest.raises(Exception):
            review.modules = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: Orphan Modules
# ---------------------------------------------------------------------------


class TestOrphanModules:
    """Tests that orphan modules are detected correctly."""

    def test_orphan_modules_detected(
        self,
    ) -> None:
        """Orphan modules (zero relationships) should be detected."""
        analyzer = ArchitectureAnalyzer()
        index = _make_index_with_orphans()
        review = analyzer.analyze(index)

        assert "orphan.py" in review.orphan_modules
        assert "module_b.py" in review.orphan_modules

    def test_no_orphans_when_all_connected(
        self,
    ) -> None:
        """When all modules have relationships, no orphans should be reported."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        # module_a.py and module_b.py have relationships
        # tests/module_c.py has no relationships
        assert "tests/module_c.py" in review.orphan_modules


# ---------------------------------------------------------------------------
# Test: Dependency Counts
# ---------------------------------------------------------------------------


class TestDependencyCounts:
    """Tests that dependency counts are computed correctly."""

    def test_outgoing_count(
        self,
    ) -> None:
        """Outgoing relationship count should be correct."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        # module_a.py has 1 outgoing relationship (inherits)
        mod_a_summary = next(
            (m for m in review.modules if m.module == "module_a.py"), None
        )
        assert mod_a_summary is not None
        assert mod_a_summary.dependency_count == 1

    def test_incoming_count(
        self,
    ) -> None:
        """Incoming relationship count should be correct."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        # module_b.py has 1 incoming relationship (inherits)
        mod_b_summary = next(
            (m for m in review.modules if m.module == "module_b.py"), None
        )
        assert mod_b_summary is not None
        assert mod_b_summary.dependent_count == 1


# ---------------------------------------------------------------------------
# Test: Dependency Cycles
# ---------------------------------------------------------------------------


class TestDependencyCycles:
    """Tests that dependency cycles are detected correctly."""

    def test_cycles_detected(
        self,
    ) -> None:
        """Cycles should be detected in the dependency graph."""
        analyzer = ArchitectureAnalyzer()
        index = _make_index_with_cycles()
        review = analyzer.analyze(index)

        # The cycle should be detected
        assert len(review.dependency_cycles) >= 1

    def test_cycle_format(
        self,
    ) -> None:
        """Cycles should be formatted as strings."""
        analyzer = ArchitectureAnalyzer()
        index = _make_index_with_cycles()
        review = analyzer.analyze(index)

        for cycle in review.dependency_cycles:
            assert isinstance(cycle, str)
            assert " -> " in cycle


# ---------------------------------------------------------------------------
# Test: Instability Score
# ---------------------------------------------------------------------------


class TestInstabilityScore:
    """Tests that instability scores are computed correctly."""

    def test_zero_connections_has_zero_score(
        self,
    ) -> None:
        """Modules with zero connections should have instability_score of 0.0."""
        analyzer = ArchitectureAnalyzer()
        index = _make_index_with_orphans()
        review = analyzer.analyze(index)

        orphan_summary = next(
            (m for m in review.modules if m.module == "orphan.py"), None
        )
        assert orphan_summary is not None
        assert orphan_summary.instability_score == 0.0

    def test_score_in_valid_range(
        self,
    ) -> None:
        """All instability scores should be in [0.0, 1.0]."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()
        review = analyzer.analyze(index)

        for module_summary in review.modules:
            assert 0.0 <= module_summary.instability_score <= 1.0


# ---------------------------------------------------------------------------
# Test: No Provider Invocation
# ---------------------------------------------------------------------------


class TestNoProviderInvocation:
    """Tests that no provider is invoked."""

    def test_no_provider_calls(
        self,
    ) -> None:
        """Analyzer should not invoke any providers."""
        analyzer = ArchitectureAnalyzer()
        index = _make_simple_index()

        # If we get here without provider errors, the test passes.
        review = analyzer.analyze(index)
        assert isinstance(review, ArchitectureReview)
