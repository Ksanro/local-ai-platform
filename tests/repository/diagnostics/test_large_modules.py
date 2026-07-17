"""Tests for the large module analyzer."""

from __future__ import annotations

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.large_modules import LargeModuleAnalyzer
from packages.repository.index.models import RepositoryIndex


class TestLargeModuleAnalyzerName:
    """Test the analyzer name property."""

    def test_name(self) -> None:
        """Test that the analyzer has the correct name."""
        analyzer = LargeModuleAnalyzer()
        assert analyzer.name == "large_modules"

    def test_is_subclass_of_base(self) -> None:
        """Test that the analyzer is a subclass of DiagnosticsAnalyzer."""
        analyzer = LargeModuleAnalyzer()
        assert isinstance(analyzer, DiagnosticsAnalyzer)


class TestLargeModuleBasic:
    """Test basic large module detection."""

    def test_empty_index(self, empty_index: RepositoryIndex) -> None:
        """Test that an empty index produces no large modules."""
        analyzer = LargeModuleAnalyzer()
        result = analyzer.analyze(empty_index)

        assert result.large_modules == ()

    def test_no_large_modules(self) -> None:
        """Test that small modules are not reported."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        small_sym = Symbol(
            id="pkg.func",
            name="func",
            qualified_name="pkg.func",
            symbol_type=SymbolType.FUNCTION,
            module="pkg.py",
            lineno=1,
        )

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=[small_sym],
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
            _symbols=[small_sym],
            _relationships=[],
            _statistics=stats,
        )

        analyzer = LargeModuleAnalyzer()
        result = analyzer.analyze(index)

        assert result.large_modules == ()

    def test_large_module_detected(self) -> None:
        """Test that large modules are detected."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        # Create a module with 10 symbols (default threshold)
        symbols = [
            Symbol(
                id=f"pkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"pkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="pkg.py",
                lineno=i + 1,
            )
            for i in range(10)
        ]

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=symbols,
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=10,
            method_count=0,
            symbol_count=10,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=stats,
        )

        analyzer = LargeModuleAnalyzer()
        result = analyzer.analyze(index)

        assert len(result.large_modules) == 1
        assert result.large_modules[0].path == "pkg.py"
        assert result.large_modules[0].symbol_count == 10

    def test_threshold_configurable(self) -> None:
        """Test that the threshold is configurable."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        symbols = [
            Symbol(
                id=f"pkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"pkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="pkg.py",
                lineno=i + 1,
            )
            for i in range(5)
        ]

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=symbols,
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=5,
            method_count=0,
            symbol_count=5,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=stats,
        )

        # Default threshold (10) — not large
        analyzer_default = LargeModuleAnalyzer()
        result_default = analyzer_default.analyze(index)
        assert result_default.large_modules == ()

        # Custom threshold (5) — large
        analyzer_custom = LargeModuleAnalyzer(threshold=5)
        result_custom = analyzer_custom.analyze(index)
        assert len(result_custom.large_modules) == 1


class TestLargeModuleDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(self) -> None:
        """Test that repeated execution produces identical results."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        symbols = [
            Symbol(
                id=f"pkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"pkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="pkg.py",
                lineno=i + 1,
            )
            for i in range(15)
        ]

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=symbols,
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=15,
            method_count=0,
            symbol_count=15,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=stats,
        )

        analyzer = LargeModuleAnalyzer()
        result1 = analyzer.analyze(index)
        result2 = analyzer.analyze(index)

        assert result1.large_modules == result2.large_modules

    def test_sorted_by_path(self) -> None:
        """Test that large modules are sorted by path."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        # Create two large modules
        symbols_z = [
            Symbol(
                id=f"zpkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"zpkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="zpkg.py",
                lineno=i + 1,
            )
            for i in range(10)
        ]
        symbols_a = [
            Symbol(
                id=f"apkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"apkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="apkg.py",
                lineno=i + 1,
            )
            for i in range(10)
        ]

        modules = {
            "zpkg.py": Module(
                path="zpkg.py",
                symbols=symbols_z,
                relationships=[],
            ),
            "apkg.py": Module(
                path="apkg.py",
                symbols=symbols_a,
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=2,
            class_count=0,
            function_count=20,
            method_count=0,
            symbol_count=20,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols_z + symbols_a,
            _relationships=[],
            _statistics=stats,
        )

        analyzer = LargeModuleAnalyzer()
        result = analyzer.analyze(index)

        assert len(result.large_modules) == 2
        # Should be sorted by path
        assert result.large_modules[0].path == "apkg.py"
        assert result.large_modules[1].path == "zpkg.py"


class TestLargeModuleDeduplication:
    """Test that large modules are deduplicated."""

    def test_no_duplicate_paths(self) -> None:
        """Test that large module paths are unique."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol, SymbolType

        symbols = [
            Symbol(
                id=f"pkg.func_{i}",
                name=f"func_{i}",
                qualified_name=f"pkg.func_{i}",
                symbol_type=SymbolType.FUNCTION,
                module="pkg.py",
                lineno=i + 1,
            )
            for i in range(10)
        ]

        modules = {
            "pkg.py": Module(
                path="pkg.py",
                symbols=symbols,
                relationships=[],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=10,
            method_count=0,
            symbol_count=10,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=symbols,
            _relationships=[],
            _statistics=stats,
        )

        analyzer = LargeModuleAnalyzer()
        result = analyzer.analyze(index)

        paths = [m.path for m in result.large_modules]
        assert len(paths) == len(set(paths))


class TestLargeModuleAnalyzerRegistry:
    """Test analyzer registration."""

    def test_register_and_get(self) -> None:
        """Test that analyzers can be registered and retrieved."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = LargeModuleAnalyzer()
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
        assert engine.get_analyzer_by_name("large_modules") is analyzer
        assert engine.get_analyzer_by_name("nonexistent") is None

    def test_duplicate_registration_ignored(self) -> None:
        """Test that duplicate registrations are ignored."""
        from packages.repository.diagnostics.engine import DiagnosticsEngine

        engine = DiagnosticsEngine()
        analyzer = LargeModuleAnalyzer()
        engine.register(analyzer)
        engine.register(analyzer)

        assert len(engine.analyzers) == 1
