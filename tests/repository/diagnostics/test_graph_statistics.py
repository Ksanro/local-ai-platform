"""Tests for the graph statistics analyzer."""

from __future__ import annotations

import pytest

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.graph_statistics import GraphStatisticsAnalyzer
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolType,
)


class TestGraphStatisticsAnalyzerName:
    """Test the analyzer name property."""

    def test_name(self) -> None:
        """Test that the analyzer has the correct name."""
        analyzer = GraphStatisticsAnalyzer()
        assert analyzer.name == "graph_statistics"

    def test_is_subclass_of_base(self) -> None:
        """Test that the analyzer is a subclass of DiagnosticsAnalyzer."""
        analyzer = GraphStatisticsAnalyzer()
        assert isinstance(analyzer, DiagnosticsAnalyzer)


class TestGraphStatisticsBasic:
    """Test basic graph statistics."""

    def test_empty_index(self, empty_index: RepositoryIndex) -> None:
        """Test that an empty index produces zero statistics."""
        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(empty_index)

        stats = result.graph_statistics
        assert stats.connected_components == 0
        assert stats.maximum_call_depth == 0
        assert stats.average_out_degree == 0.0
        assert stats.average_in_degree == 0.0

    def test_simple_index(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test statistics for a simple index."""
        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(simple_index)

        stats = result.graph_statistics
        # 3 nodes (func_a, func_b, func_c), 1 CALLS edge
        # func_a and func_b are connected, func_c is isolated = 2 components
        assert stats.connected_components == 2
        assert stats.maximum_call_depth == 1  # func_a -> func_b
        # average_out_degree = 1 edge / 2 nodes in relationships = 0.5
        assert stats.average_out_degree == pytest.approx(0.5)
        assert stats.average_in_degree == pytest.approx(0.5)


class TestGraphStatisticsComponents:
    """Test connected components calculation (CALLS graph only)."""

    def test_multiple_components(self) -> None:
        """Test that multiple components are counted correctly."""
        from packages.repository.index.models import RepositoryStatistics

        func_a = Symbol(
            id="pkg.func_a",
            name="func_a",
            qualified_name="pkg.func_a",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=1,
        )
        func_b = Symbol(
            id="pkg.func_b",
            name="func_b",
            qualified_name="pkg.func_b",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=5,
        )
        func_c = Symbol(
            id="pkg.func_c",
            name="func_c",
            qualified_name="pkg.func_c",
            symbol_type=SymbolType.FUNCTION,
            module="pkg2.py",
            lineno=1,
        )

        call_a_b = Relationship(
            source="pkg.func_a",
            target="pkg.func_b",
            type=RelationshipType.CALLS,
        )

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=[func_a, func_b],
                relationships=[call_a_b],
            ),
            "pkg2.py": Module(
                path="pkg2.py",
                symbols=[func_c],
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=2,
            class_count=0,
            function_count=3,
            method_count=0,
            symbol_count=3,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[func_a, func_b, func_c],
            _relationships=[call_a_b],
            _statistics=stats,
        )

        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(index)

        # func_a and func_b are connected via CALLS, func_c is isolated
        assert result.graph_statistics.connected_components == 2

    def test_single_component(self) -> None:
        """Test that a fully connected CALLS graph has one component."""
        from packages.repository.index.models import RepositoryStatistics

        func_a = Symbol(
            id="pkg.func_a",
            name="func_a",
            qualified_name="pkg.func_a",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=1,
        )
        func_b = Symbol(
            id="pkg.func_b",
            name="func_b",
            qualified_name="pkg.func_b",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=5,
        )

        call_a_b = Relationship(
            source="pkg.func_a",
            target="pkg.func_b",
            type=RelationshipType.CALLS,
        )
        call_b_a = Relationship(
            source="pkg.func_b",
            target="pkg.func_a",
            type=RelationshipType.CALLS,
        )

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=[func_a, func_b],
                relationships=[call_a_b, call_b_a],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=2,
            method_count=0,
            symbol_count=2,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[func_a, func_b],
            _relationships=[call_a_b, call_b_a],
            _statistics=stats,
        )

        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(index)

        assert result.graph_statistics.connected_components == 1


class TestGraphStatisticsDepth:
    """Test maximum call depth calculation."""

    def test_call_chain_depth(self) -> None:
        """Test that call chain depth is calculated correctly."""
        from packages.repository.index.models import RepositoryStatistics

        func_a = Symbol(
            id="pkg.func_a",
            name="func_a",
            qualified_name="pkg.func_a",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=1,
        )
        func_b = Symbol(
            id="pkg.func_b",
            name="func_b",
            qualified_name="pkg.func_b",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=5,
        )
        func_c = Symbol(
            id="pkg.func_c",
            name="func_c",
            qualified_name="pkg.func_c",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=10,
        )

        call_a_b = Relationship(
            source="pkg.func_a",
            target="pkg.func_b",
            type=RelationshipType.CALLS,
        )
        call_b_c = Relationship(
            source="pkg.func_b",
            target="pkg.func_c",
            type=RelationshipType.CALLS,
        )

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=[func_a, func_b, func_c],
                relationships=[call_a_b, call_b_c],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=3,
            method_count=0,
            symbol_count=3,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[func_a, func_b, func_c],
            _relationships=[call_a_b, call_b_c],
            _statistics=stats,
        )

        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(index)

        # func_a -> func_b -> func_c = depth 2
        assert result.graph_statistics.maximum_call_depth == 2

    def test_no_calls_no_depth(self) -> None:
        """Test that no CALLS relationships produce depth 0."""
        from packages.repository.index.models import RepositoryStatistics

        func_a = Symbol(
            id="pkg.func_a",
            name="func_a",
            qualified_name="pkg.func_a",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=1,
        )

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=[func_a],
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=1,
            method_count=0,
            symbol_count=1,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[func_a],
            _relationships=[],
            _statistics=stats,
        )

        analyzer = GraphStatisticsAnalyzer()
        result = analyzer.analyze(index)

        assert result.graph_statistics.maximum_call_depth == 0


class TestGraphStatisticsDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that repeated execution produces identical results."""
        analyzer = GraphStatisticsAnalyzer()
        result1 = analyzer.analyze(simple_index)
        result2 = analyzer.analyze(simple_index)

        assert result1.graph_statistics == result2.graph_statistics


class TestGraphStatisticsAnalyzerRegistry:
    """Test analyzer registration."""

    def test_register_and_get(self) -> None:
        """Test that analyzers can be registered and retrieved."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = GraphStatisticsAnalyzer()
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
        assert engine.get_analyzer_by_name("graph_statistics") is analyzer
        assert engine.get_analyzer_by_name("nonexistent") is None

    def test_duplicate_registration_ignored(self) -> None:
        """Test that duplicate registrations are ignored."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = GraphStatisticsAnalyzer()
        engine.register(analyzer)
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
