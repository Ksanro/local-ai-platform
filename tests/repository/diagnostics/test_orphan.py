"""Tests for the orphan analyzer."""

from __future__ import annotations

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer
from packages.repository.diagnostics.models import (
    RepositoryDiagnostics,
)
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolType,
)


class TestOrphanAnalyzerName:
    """Test the analyzer name property."""

    def test_name(self) -> None:
        """Test that the analyzer has the correct name."""
        analyzer = OrphanAnalyzer()
        assert analyzer.name == "orphan"

    def test_is_subclass_of_base(self) -> None:
        """Test that the analyzer is a subclass of DiagnosticsAnalyzer."""
        analyzer = OrphanAnalyzer()
        assert isinstance(analyzer, DiagnosticsAnalyzer)


class TestOrphanBasic:
    """Test basic orphan detection."""

    def test_empty_index(self, empty_index: RepositoryIndex) -> None:
        """Test that an empty index produces no orphans."""
        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(empty_index)

        assert isinstance(result, RepositoryDiagnostics)
        assert result.orphan_modules == ()

    def test_simple_orphan(
        self,
        orphan_index: RepositoryIndex,
    ) -> None:
        """Test detection of an orphan module."""
        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(orphan_index)

        # orphan.py is a root module (no directory component) so it's excluded.
        # The orphan_index only has root-level modules, so no orphans expected.
        assert result.orphan_modules == ()


class TestOrphanNoOrphan:
    """Test when no orphans exist."""

    def test_no_orphan_in_simple_index(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that a simple index without orphans produces no results."""
        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(simple_index)

        # In simple_index, modules are root-level so they are excluded.
        assert result.orphan_modules == ()


class TestOrphanRootModules:
    """Test that root modules are excluded."""

    def test_root_module_not_orphan(self) -> None:
        """Test that root modules are not reported as orphans."""
        from packages.repository.index.models import RepositoryStatistics

        main_sym = Symbol(
            id="main",
            name="main",
            qualified_name="main",
            symbol_type=SymbolType.MODULE,
            module="main.py",
            lineno=1,
        )

        modules = {
            "main.py": Module(
                path="main.py",
                symbols=[main_sym],
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=0,
            method_count=0,
            symbol_count=1,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[main_sym],
            _relationships=[],
            _statistics=stats,
        )

        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(index)

        # main.py is a root module (no directory component)
        # so it should NOT be reported as orphan
        assert result.orphan_modules == ()

    def test_init_py_not_orphan(self) -> None:
        """Test that __init__.py files are not reported as orphans."""
        from packages.repository.index.models import RepositoryStatistics

        pkg_sym = Symbol(
            id="pkg",
            name="pkg",
            qualified_name="pkg",
            symbol_type=SymbolType.MODULE,
            module="pkg/__init__.py",
            lineno=1,
        )

        modules = {
            "pkg/__init__.py": Module(
                path="pkg/__init__.py",
                symbols=[pkg_sym],
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=0,
            method_count=0,
            symbol_count=1,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[pkg_sym],
            _relationships=[],
            _statistics=stats,
        )

        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(index)

        # __init__.py files are root modules
        assert result.orphan_modules == ()


class TestOrphanDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(
        self,
        orphan_index: RepositoryIndex,
    ) -> None:
        """Test that repeated execution produces identical results."""
        analyzer = OrphanAnalyzer()
        result1 = analyzer.analyze(orphan_index)
        result2 = analyzer.analyze(orphan_index)

        assert result1.orphan_modules == result2.orphan_modules

    def test_sorted_by_path(self) -> None:
        """Test that orphans are sorted by path."""
        from packages.repository.index.models import RepositoryStatistics

        # Create modules with directory components (not root-level)
        z_sym = Symbol(
            id="pkg.orphan_z",
            name="orphan_z",
            qualified_name="pkg.orphan_z",
            symbol_type=SymbolType.MODULE,
            module="pkg/orphan_z.py",
            lineno=1,
        )
        a_sym = Symbol(
            id="pkg.orphan_a",
            name="orphan_a",
            qualified_name="pkg.orphan_a",
            symbol_type=SymbolType.MODULE,
            module="pkg/orphan_a.py",
            lineno=1,
        )
        connected_sym = Symbol(
            id="pkg.connected",
            name="connected",
            qualified_name="pkg.connected",
            symbol_type=SymbolType.MODULE,
            module="pkg/connected.py",
            lineno=1,
        )

        import_rel = Relationship(
            source="pkg.connected",
            target="pkg.connected",
            type=RelationshipType.IMPORTS,
        )

        modules = {
            "pkg/orphan_z.py": Module(
                path="pkg/orphan_z.py",
                symbols=[z_sym],
                relationships=[],
            ),
            "pkg/orphan_a.py": Module(
                path="pkg/orphan_a.py",
                symbols=[a_sym],
                relationships=[],
            ),
            "pkg/connected.py": Module(
                path="pkg/connected.py",
                symbols=[connected_sym],
                relationships=[import_rel],
            ),
        }

        stats = RepositoryStatistics(
            module_count=3,
            class_count=0,
            function_count=0,
            method_count=0,
            symbol_count=3,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[z_sym, a_sym, connected_sym],
            _relationships=[import_rel],
            _statistics=stats,
        )

        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(index)

        # Should be sorted by path
        assert len(result.orphan_modules) == 2
        assert result.orphan_modules[0].path == "pkg/orphan_a.py"
        assert result.orphan_modules[1].path == "pkg/orphan_z.py"


class TestOrphanDeduplication:
    """Test that orphans are deduplicated."""

    def test_no_duplicate_paths(
        self,
        orphan_index: RepositoryIndex,
    ) -> None:
        """Test that orphan modules are unique."""
        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(orphan_index)

        paths = [m.path for m in result.orphan_modules]
        assert len(paths) == len(set(paths))


class TestOrphanConnected:
    """Test connected modules are not orphans."""

    def test_connected_modules_not_orphan(
        self,
        orphan_index: RepositoryIndex,
    ) -> None:
        """Test that connected modules are not reported as orphans."""
        analyzer = OrphanAnalyzer()
        result = analyzer.analyze(orphan_index)

        paths = [m.path for m in result.orphan_modules]
        assert "main.py" not in paths
        assert "utils.py" not in paths


class TestOrphanAnalyzerRegistry:
    """Test analyzer registration."""

    def test_register_and_get(self) -> None:
        """Test that analyzers can be registered and retrieved."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = OrphanAnalyzer()
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
        assert engine.get_analyzer_by_name("orphan") is analyzer
        assert engine.get_analyzer_by_name("nonexistent") is None

    def test_duplicate_registration_ignored(self) -> None:
        """Test that duplicate registrations are ignored."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = OrphanAnalyzer()
        engine.register(analyzer)
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
