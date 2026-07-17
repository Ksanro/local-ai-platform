"""Tests for the diagnostics engine."""

from __future__ import annotations

from packages.repository.diagnostics.engine import DiagnosticsEngine
from packages.repository.diagnostics.models import RepositoryDiagnostics
from packages.repository.index.models import RepositoryIndex


class TestDiagnosticsEngineBasic:
    """Test basic engine functionality."""

    def test_empty_engine(self) -> None:
        """Test that an engine with no analyzers returns empty diagnostics."""
        engine = DiagnosticsEngine()
        result = engine.analyze(RepositoryIndex())

        assert isinstance(result, RepositoryDiagnostics)
        assert result.dead_symbols == ()
        assert result.dependency_cycles == ()
        assert result.orphan_modules == ()
        assert result.large_modules == ()
        assert result.warnings == ()

    def test_register_analyzer(self) -> None:
        """Test that analyzers can be registered."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer

        engine = DiagnosticsEngine()
        analyzer = DeadCodeAnalyzer()
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
        assert engine.analyzers[0] is analyzer

    def test_multiple_analyzers(self) -> None:
        """Test that multiple analyzers can be registered."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer

        engine = DiagnosticsEngine()
        engine.register(DeadCodeAnalyzer())
        engine.register(OrphanAnalyzer())

        assert len(engine.analyzers) == 2

    def test_duplicate_registration_ignored(self) -> None:
        """Test that duplicate registrations are ignored."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer

        engine = DiagnosticsEngine()
        analyzer = DeadCodeAnalyzer()
        engine.register(analyzer)
        engine.register(analyzer)

        assert len(engine.analyzers) == 1


class TestDiagnosticsEngineComposing:
    """Test that engine composes results from multiple analyzers."""

    def test_composes_dead_code_and_orphan(
        self,
        full_index: RepositoryIndex,
    ) -> None:
        """Test that results from different analyzers are composed."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer

        engine = DiagnosticsEngine()
        engine.register(DeadCodeAnalyzer())
        engine.register(OrphanAnalyzer())

        result = engine.analyze(full_index)

        # Should have both dead code and orphan results
        assert isinstance(result, RepositoryDiagnostics)
        assert len(result.dead_symbols) > 0
        assert len(result.orphan_modules) > 0

    def test_composes_all_analyzers(
        self,
        full_index: RepositoryIndex,
    ) -> None:
        """Test that all analyzers produce results."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.graph_statistics import (
            GraphStatisticsAnalyzer,
        )
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer
        from packages.repository.diagnostics.analyzers.statistics import ModuleStatisticsAnalyzer

        engine = DiagnosticsEngine()
        engine.register(DeadCodeAnalyzer())
        engine.register(OrphanAnalyzer())
        engine.register(ModuleStatisticsAnalyzer())
        engine.register(GraphStatisticsAnalyzer())

        result = engine.analyze(full_index)

        assert isinstance(result, RepositoryDiagnostics)
        # Module statistics should be populated
        assert result.module_statistics.module_count > 0
        # Graph statistics should be populated
        assert result.graph_statistics.connected_components >= 0


class TestDiagnosticsEngineDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(
        self,
        full_index: RepositoryIndex,
    ) -> None:
        """Test that repeated execution produces identical results."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.graph_statistics import (
            GraphStatisticsAnalyzer,
        )
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer
        from packages.repository.diagnostics.analyzers.statistics import ModuleStatisticsAnalyzer

        engine = DiagnosticsEngine()
        engine.register(DeadCodeAnalyzer())
        engine.register(OrphanAnalyzer())
        engine.register(ModuleStatisticsAnalyzer())
        engine.register(GraphStatisticsAnalyzer())

        result1 = engine.analyze(full_index)
        result2 = engine.analyze(full_index)

        assert result1.dead_symbols == result2.dead_symbols
        assert result1.orphan_modules == result2.orphan_modules
        assert result1.module_statistics == result2.module_statistics
        assert result1.graph_statistics == result2.graph_statistics


class TestDiagnosticsEngineGetAnalyzer:
    """Test analyzer retrieval."""

    def test_get_analyzer_by_name(self) -> None:
        """Test that analyzers can be retrieved by name."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer

        engine = DiagnosticsEngine()
        dead_analyzer = DeadCodeAnalyzer()
        orphan_analyzer = OrphanAnalyzer()
        engine.register(dead_analyzer)
        engine.register(orphan_analyzer)

        assert engine.get_analyzer_by_name("dead_code") is dead_analyzer
        assert engine.get_analyzer_by_name("orphan") is orphan_analyzer
        assert engine.get_analyzer_by_name("nonexistent") is None

    def test_get_analyzer_not_found(self) -> None:
        """Test that non-existent analyzers return None."""
        engine = DiagnosticsEngine()
        assert engine.get_analyzer_by_name("nonexistent") is None


class TestDiagnosticsEngineNoMutation:
    """Test that engine does not mutate RepositoryIndex."""

    def test_index_not_mutated(
        self,
        full_index: RepositoryIndex,
    ) -> None:
        """Test that analyzing does not mutate the index."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer

        engine = DiagnosticsEngine()
        engine.register(DeadCodeAnalyzer())

        # Get initial state
        initial_modules = dict(full_index.modules)
        initial_relationships = list(full_index.relationships())

        # Analyze
        engine.analyze(full_index)

        # Check that index was not mutated
        assert dict(full_index.modules) == initial_modules
        assert list(full_index.relationships()) == initial_relationships


class TestDiagnosticsEngineAnalyzerOrder:
    """Test that analyzer order is preserved."""

    def test_analyzers_in_registration_order(self) -> None:
        """Test that analyzers are returned in registration order."""
        from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
        from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer

        engine = DiagnosticsEngine()
        dead = DeadCodeAnalyzer()
        orphan = OrphanAnalyzer()

        engine.register(dead)
        engine.register(orphan)

        assert list(engine.analyzers) == [dead, orphan]

    def test_analyzers_tuple(self) -> None:
        """Test that analyzers property returns a tuple."""
        engine = DiagnosticsEngine()
        assert isinstance(engine.analyzers, tuple)
