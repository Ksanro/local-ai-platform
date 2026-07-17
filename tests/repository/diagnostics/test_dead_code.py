"""Tests for the dead code analyzer."""

from __future__ import annotations

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
from packages.repository.diagnostics.models import (
    RepositoryDiagnostics,
)
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Relationship, RelationshipType, SymbolType


class TestDeadCodeAnalyzerName:
    """Test the analyzer name property."""

    def test_name(self) -> None:
        """Test that the analyzer has the correct name."""
        analyzer = DeadCodeAnalyzer()
        assert analyzer.name == "dead_code"

    def test_is_subclass_of_base(self) -> None:
        """Test that the analyzer is a subclass of DiagnosticsAnalyzer."""
        analyzer = DeadCodeAnalyzer()
        assert isinstance(analyzer, DiagnosticsAnalyzer)


class TestDeadCodeBasic:
    """Test basic dead code detection."""

    def test_empty_index(self, empty_index: RepositoryIndex) -> None:
        """Test that an empty index produces no dead symbols."""
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(empty_index)

        assert isinstance(result, RepositoryDiagnostics)
        assert result.dead_symbols == ()

    def test_simple_dead_code(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test detection of dead code in a simple index.

        func_c is never called by any other function.
        """
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(simple_index)

        assert len(result.dead_symbols) == 1
        dead = result.dead_symbols[0]
        assert dead.qualified_name == "module_b.func_c"
        assert dead.symbol_type == SymbolType.FUNCTION
        assert dead.module == "module_b.py"
        assert dead.lineno == 1


class TestDeadCodeEntryPoints:
    """Test that entry points are excluded."""

    def test_module_level_function_not_dead(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that module-level functions are entry points."""
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(simple_index)

        # func_a is module-level — should NOT be dead
        dead_names = [d.qualified_name for d in result.dead_symbols]
        assert "module_a.func_a" not in dead_names

    def test_method_with_no_callers_is_dead(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that methods with no callers are detected."""
        # In simple_index, func_b is called by func_a, so it's not dead.
        # But if a method has no callers, it should be dead.
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(simple_index)

        # func_b is called by func_a, so it's reachable
        dead_names = [d.qualified_name for d in result.dead_symbols]
        assert "module_a.func_b" not in dead_names


class TestDeadCodeAbstractMethods:
    """Test that abstract methods are excluded."""

    def test_abstract_method_not_dead(
        self,
        full_index: RepositoryIndex,
    ) -> None:
        """Test that abstract methods are not reported as dead."""
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(full_index)

        # ClassA.run is abstract — should NOT be dead
        dead_names = [d.qualified_name for d in result.dead_symbols]
        assert "package.core.ClassA.run" not in dead_names


class TestDeadCodeDeterminism:
    """Test deterministic output."""

    def test_repeated_execution_identical(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that repeated execution produces identical results."""
        analyzer = DeadCodeAnalyzer()
        result1 = analyzer.analyze(simple_index)
        result2 = analyzer.analyze(simple_index)

        assert result1.dead_symbols == result2.dead_symbols

    def test_sorted_by_qualified_name(self) -> None:
        """Test that dead symbols are sorted by qualified_name."""
        # Create an index with multiple dead symbols
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol

        dead_func_1 = Symbol(
            id="mod.z_func",
            name="z_func",
            qualified_name="mod.z_func",
            symbol_type=SymbolType.FUNCTION,
            module="mod.py",
            lineno=10,
        )
        dead_func_2 = Symbol(
            id="mod.a_func",
            name="a_func",
            qualified_name="mod.a_func",
            symbol_type=SymbolType.FUNCTION,
            module="mod.py",
            lineno=5,
        )

        modules = {
            "mod.py": Module(
                path="mod.py",
                symbols=[dead_func_1, dead_func_2],
                relationships=[],
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
            _symbols=[dead_func_1, dead_func_2],
            _relationships=[],
            _statistics=stats,
        )

        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(index)

        # Should be sorted by qualified_name
        assert len(result.dead_symbols) == 2
        assert result.dead_symbols[0].qualified_name == "mod.a_func"
        assert result.dead_symbols[1].qualified_name == "mod.z_func"


class TestDeadCodeDeduplication:
    """Test that dead symbols are deduplicated."""

    def test_no_duplicate_symbols(
        self,
        simple_index: RepositoryIndex,
    ) -> None:
        """Test that dead symbols are unique."""
        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(simple_index)

        qnames = [d.qualified_name for d in result.dead_symbols]
        assert len(qnames) == len(set(qnames))


class TestDeadCodeMethod:
    """Test dead method detection."""

    def test_dead_method(self) -> None:
        """Test that dead methods are detected."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol

        cls_sym = Symbol(
            id="pkg.mod.MyClass",
            name="MyClass",
            qualified_name="pkg.mod.MyClass",
            symbol_type=SymbolType.CLASS,
            module="pkg/mod.py",
            lineno=1,
        )
        dead_method = Symbol(
            id="pkg.mod.MyClass.dead_method",
            name="dead_method",
            qualified_name="pkg.mod.MyClass.dead_method",
            symbol_type=SymbolType.METHOD,
            module="pkg/mod.py",
            lineno=5,
        )
        alive_method = Symbol(
            id="pkg.mod.MyClass.alive_method",
            name="alive_method",
            qualified_name="pkg.mod.MyClass.alive_method",
            symbol_type=SymbolType.METHOD,
            module="pkg/mod.py",
            lineno=10,
        )

        call_rel = Relationship(
            source="pkg.mod.MyClass.alive_method",
            target="pkg.mod.MyClass.dead_method",
            type=RelationshipType.CALLS,
        )

        modules = {
            "pkg/mod.py": Module(
                path="pkg/mod.py",
                symbols=[cls_sym, dead_method, alive_method],
                relationships=[call_rel],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=0,
            method_count=2,
            symbol_count=3,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[cls_sym, dead_method, alive_method],
            _relationships=[call_rel],
            _statistics=stats,
        )

        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(index)

        # Both methods are called (alive_method calls dead_method),
        # so neither should be dead.
        assert len(result.dead_symbols) == 0

    def test_method_only_called_by_itself_is_dead(self) -> None:
        """Test that a method only calling itself is dead."""
        from packages.repository.index.models import RepositoryStatistics
        from packages.repository.symbols.models import Module, Symbol

        cls_sym = Symbol(
            id="pkg.mod.MyClass",
            name="MyClass",
            qualified_name="pkg.mod.MyClass",
            symbol_type=SymbolType.CLASS,
            module="pkg/mod.py",
            lineno=1,
        )
        self_calling = Symbol(
            id="pkg.mod.MyClass.self_call",
            name="self_call",
            qualified_name="pkg.mod.MyClass.self_call",
            symbol_type=SymbolType.METHOD,
            module="pkg/mod.py",
            lineno=5,
        )

        # self_call calls itself
        call_rel = Relationship(
            source="pkg.mod.MyClass.self_call",
            target="pkg.mod.MyClass.self_call",
            type=RelationshipType.CALLS,
        )

        modules = {
            "pkg/mod.py": Module(
                path="pkg/mod.py",
                symbols=[cls_sym, self_calling],
                relationships=[call_rel],
            ),
        }

        stats = RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=0,
            method_count=1,
            symbol_count=2,
        )

        index = RepositoryIndex(
            modules=modules,
            _symbols=[cls_sym, self_calling],
            _relationships=[call_rel],
            _statistics=stats,
        )

        analyzer = DeadCodeAnalyzer()
        result = analyzer.analyze(index)

        # self_call is both caller and callee, so it's reachable
        assert len(result.dead_symbols) == 0
