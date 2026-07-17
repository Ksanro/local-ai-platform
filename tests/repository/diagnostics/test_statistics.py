"""Tests for the module statistics analyzer."""

from __future__ import annotations

import pytest

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.statistics import ModuleStatisticsAnalyzer
from packages.repository.index.models import RepositoryIndex


class TestModuleStatisticsAnalyzerName:
    """Test the analyzer name property."""

    def test_name(self) -> None:
        """Test that the analyzer has the correct name."""
        analyzer = ModuleStatisticsAnalyzer()
        assert analyzer.name == "module_statistics"

    def test_is_subclass_of_base(self) -> None:
        """Test that the analyzer is a subclass of DiagnosticsAnalyzer."""
        analyzer = ModuleStatisticsAnalyzer()
        assert isinstance(analyzer, DiagnosticsAnalyzer)


class TestModuleStatisticsBasic:
    """Test basic module statistics."""

    def test_empty_index(self, empty_index: RepositoryIndex) -> None:
        """Test that an empty index produces zero statistics."""
        analyzer = ModuleStatisticsAnalyzer()
        result = analyzer.analyze(empty_index)

        stats = result.module_statistics
        assert stats.module_count == 0
        assert stats.average_symbols == 0.0
        assert stats.largest_module == ""
        assert stats.largest_module_symbol_count == 0
        assert stats.largest_call_graph == ""
        assert stats.largest_call_graph_size == 0
        assert stats.average_relationships == 0.0
        assert stats.relationship_density == 0.0

    def test_simple_index(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test statistics for a simple index."""
        analyzer = ModuleStatisticsAnalyzer()
        result = analyzer.analyze(simple_index)

        stats = result.module_statistics
        assert stats.module_count == 2
        assert stats.largest_module_symbol_count == 2  # module_a.py has 2 symbols
        assert stats.average_symbols == pytest.approx(1.5)


class TestModuleStatisticsDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that repeated execution produces identical results."""
        analyzer = ModuleStatisticsAnalyzer()
        result1 = analyzer.analyze(simple_index)
        result2 = analyzer.analyze(simple_index)

        assert result1.module_statistics == result2.module_statistics


class TestModuleStatisticsAnalyzerRegistry:
    """Test analyzer registration."""

    def test_register_and_get(self) -> None:
        """Test that analyzers can be registered and retrieved."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = ModuleStatisticsAnalyzer()
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
        assert engine.get_analyzer_by_name("module_statistics") is analyzer
        assert engine.get_analyzer_by_name("nonexistent") is None

    def test_duplicate_registration_ignored(self) -> None:
        """Test that duplicate registrations are ignored."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = ModuleStatisticsAnalyzer()
        engine.register(analyzer)
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
