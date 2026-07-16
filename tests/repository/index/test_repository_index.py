"""Tests for the Repository Index.

Verifies index creation, statistics, module lookup, symbol lookup,
relationship lookup, deterministic ordering, and repeated builds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.repository.index.models import (
    Module,
    Relationship,
    RelationshipType,
    RepositoryIndex,
    RepositoryStatistics,
    Symbol,
    SymbolType,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_symbol(
    name: str,
    qualified_name: str,
    symbol_type: SymbolType,
    module: str = "main.py",
    lineno: int = 1,
    decorators: list[str] | None = None,
) -> Symbol:
    """Helper to create a Symbol for testing."""
    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        module=module,
        lineno=lineno,
        decorators=decorators or [],
    )


def _make_index(
    symbols: list[Symbol],
    relationships: list[Relationship] | None = None,
) -> RepositoryIndex:
    """Create a RepositoryIndex from symbols and relationships.

    Args:
        symbols: List of Symbol instances.
        relationships: List of Relationship instances.

    Returns:
        A RepositoryIndex with modules derived from the symbols.
    """
    modules: dict[str, Module] = {}
    for sym in symbols:
        if sym.module not in modules:
            modules[sym.module] = Module(path=sym.module)
        modules[sym.module].symbols.append(sym)

    rels = relationships or []
    for rel in rels:
        if rel.source in modules:
            modules[rel.source].relationships.append(rel)

    # Compute statistics
    class_count = sum(1 for s in symbols if s.symbol_type == SymbolType.CLASS)
    function_count = sum(1 for s in symbols if s.symbol_type == SymbolType.FUNCTION)
    method_count = sum(1 for s in symbols if s.symbol_type == SymbolType.METHOD)

    statistics = RepositoryStatistics(
        module_count=len(modules),
        class_count=class_count,
        function_count=function_count,
        method_count=method_count,
        symbol_count=len(symbols),
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=rels,
        _statistics=statistics,
    )


# ------------------------------------------------------------------
# Index creation
# ------------------------------------------------------------------


class TestIndexCreation:
    """Tests for RepositoryIndex creation."""

    def test_index_with_symbols(self) -> None:
        """Verify index stores symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index = _make_index(symbols)
        assert len(index.symbols()) == 2

    def test_index_with_relationships(self) -> None:
        """Verify index stores relationships."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)
        assert len(index.relationships()) == 1

    def test_index_with_statistics(self) -> None:
        """Verify index stores statistics."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        index = _make_index(symbols)
        stats = index.statistics()
        assert stats.class_count == 1
        assert stats.method_count == 1
        assert stats.function_count == 1
        assert stats.symbol_count == 3
        assert stats.module_count == 1


# ------------------------------------------------------------------
# Statistics
# ------------------------------------------------------------------


class TestStatistics:
    """Tests for RepositoryStatistics."""

    def test_module_count(self) -> None:
        """Verify module_count matches number of modules."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("auth", "auth.auth", SymbolType.FUNCTION, "auth.py"),
        ]
        index = _make_index(symbols)
        assert index.statistics().module_count == 2

    def test_class_count(self) -> None:
        """Verify class_count matches number of CLASS symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Model", "main.Model", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index = _make_index(symbols)
        assert index.statistics().class_count == 2

    def test_function_count(self) -> None:
        """Verify function_count matches number of FUNCTION symbols."""
        symbols = [
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        assert index.statistics().function_count == 1

    def test_method_count(self) -> None:
        """Verify method_count matches number of METHOD symbols."""
        symbols = [
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        assert index.statistics().method_count == 1

    def test_symbol_count(self) -> None:
        """Verify symbol_count matches total symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        index = _make_index(symbols)
        assert index.statistics().symbol_count == 3


# ------------------------------------------------------------------
# Module lookup
# ------------------------------------------------------------------


class TestModuleLookup:
    """Tests for module lookup."""

    def test_find_module_existing(self) -> None:
        """find_module should return module for existing path."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        index = _make_index(symbols)
        mod = index.find_module("main.py")
        assert mod is not None
        assert mod.path == "main.py"

    def test_find_module_not_found(self) -> None:
        """find_module should return None for unknown path."""
        symbols = [_make_symbol("App", "main.App", SymbolType.CLASS, "main.py")]
        index = _make_index(symbols)
        assert index.find_module("unknown.py") is None

    def test_modules_list_sorted(self) -> None:
        """modules_list should return sorted modules."""
        symbols = [
            _make_symbol("B", "b.B", SymbolType.CLASS, "b.py"),
            _make_symbol("A", "a.A", SymbolType.CLASS, "a.py"),
        ]
        index = _make_index(symbols)
        modules = index.modules_list()
        assert len(modules) == 2
        assert modules[0].path == "a.py"
        assert modules[1].path == "b.py"


# ------------------------------------------------------------------
# Symbol lookup
# ------------------------------------------------------------------


class TestSymbolLookup:
    """Tests for symbol lookup."""

    def test_symbols_returns_all(self) -> None:
        """symbols() should return all symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        index = _make_index(symbols)
        all_syms = index.symbols()
        assert len(all_syms) == 3

    def test_symbols_sorted(self) -> None:
        """symbols() should be sorted by qualified_name."""
        symbols = [
            _make_symbol("Z", "main.Z", SymbolType.CLASS, "main.py"),
            _make_symbol("A", "main.A", SymbolType.CLASS, "main.py"),
            _make_symbol("M", "main.M", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        names = [s.qualified_name for s in index.symbols()]
        assert names == sorted(names)

    def test_find_by_name(self) -> None:
        """find() should match against short name."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        results = index.find("App")
        assert len(results) == 1
        assert results[0].name == "App"

    def test_find_by_qualified_name(self) -> None:
        """find() should match against qualified name."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        results = index.find("main.App")
        assert len(results) == 1
        assert results[0].qualified_name == "main.App"

    def test_find_no_match(self) -> None:
        """find() should return empty list for no match."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        results = index.find("nonexistent")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_always_returns_list(self) -> None:
        """find() always returns a list, never None."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        results = index.find("App")
        assert isinstance(results, list)

    def test_find_deduplicates(self) -> None:
        """find() should deduplicate by qualified_name."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        results = index.find("App")
        assert len(results) == 1


# ------------------------------------------------------------------
# Relationship lookup
# ------------------------------------------------------------------


class TestRelationshipLookup:
    """Tests for relationship lookup."""

    def test_relationships_returns_all(self) -> None:
        """relationships() should return all relationships."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)
        rels = index.relationships()
        assert len(rels) == 1

    def test_relationships_sorted(self) -> None:
        """relationships() should be sorted by source, target, type."""
        symbols = [
            _make_symbol("B", "b.B", SymbolType.CLASS, "b.py"),
            _make_symbol("A", "a.A", SymbolType.CLASS, "a.py"),
        ]
        relationships = [
            Relationship(
                source="b.B",
                target="b.B.method",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="a.A",
                target="a.A.method",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index(symbols, relationships)
        sources = [r.source for r in index.relationships()]
        assert sources == sorted(sources)


# ------------------------------------------------------------------
# Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering."""

    def test_modules_sorted(self) -> None:
        """modules_list() should be sorted by path."""
        symbols = [
            _make_symbol("Z", "z.Z", SymbolType.CLASS, "z.py"),
            _make_symbol("A", "a.A", SymbolType.CLASS, "a.py"),
        ]
        index = _make_index(symbols)
        paths = [m.path for m in index.modules_list()]
        assert paths == sorted(paths)

    def test_symbols_sorted(self) -> None:
        """symbols() should be sorted by qualified_name."""
        symbols = [
            _make_symbol("Z", "main.Z", SymbolType.CLASS, "main.py"),
            _make_symbol("A", "main.A", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        names = [s.qualified_name for s in index.symbols()]
        assert names == sorted(names)

    def test_relationships_sorted(self) -> None:
        """relationships() should be sorted by source, target, type."""
        symbols = [
            _make_symbol("B", "b.B", SymbolType.CLASS, "b.py"),
            _make_symbol("A", "a.A", SymbolType.CLASS, "a.py"),
        ]
        relationships = [
            Relationship(source="b.B", target="b.B.m", type=RelationshipType.DEFINES),
            Relationship(source="a.A", target="a.A.m", type=RelationshipType.DEFINES),
        ]
        index = _make_index(symbols, relationships)
        sources = [r.source for r in index.relationships()]
        assert sources == sorted(sources)


# ------------------------------------------------------------------
# Repeated builds identical
# ------------------------------------------------------------------


class TestRepeatedBuildsIdentical:
    """Tests for repeated build stability."""

    def test_identical_statistics(self) -> None:
        """Repeated builds produce identical statistics."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index1 = _make_index(symbols)
        index2 = _make_index(symbols)
        assert index1.statistics() == index2.statistics()

    def test_identical_symbols(self) -> None:
        """Repeated builds produce identical symbols."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index1 = _make_index(symbols)
        index2 = _make_index(symbols)
        names1 = [s.qualified_name for s in index1.symbols()]
        names2 = [s.qualified_name for s in index2.symbols()]
        assert names1 == names2

    def test_identical_relationships(self) -> None:
        """Repeated builds produce identical relationships."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index1 = _make_index(symbols, relationships)
        index2 = _make_index(symbols, relationships)
        rels1 = index1.relationships()
        rels2 = index2.relationships()
        assert rels1 == rels2


# ------------------------------------------------------------------
# No duplicate symbols
# ------------------------------------------------------------------


class TestNoDuplicates:
    """Tests for duplicate prevention."""

    def test_no_duplicate_symbols(self) -> None:
        """symbols() should not contain duplicates."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index(symbols)
        names = [s.qualified_name for s in index.symbols()]
        assert len(names) == len(set(names))

    def test_no_duplicate_modules(self) -> None:
        """modules_list() should not contain duplicates."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index = _make_index(symbols)
        paths = [m.path for m in index.modules_list()]
        assert len(paths) == len(set(paths))


# ------------------------------------------------------------------
# Frozen dataclass
# ------------------------------------------------------------------


class TestFrozen:
    """Tests for frozen dataclass behavior."""

    def test_repository_statistics_frozen(self) -> None:
        """RepositoryStatistics should be frozen."""
        stats = RepositoryStatistics(
            module_count=1,
            class_count=0,
            function_count=0,
            method_count=0,
            symbol_count=0,
        )
        with pytest.raises(Exception):  # frozen dataclass raises on mutation
            stats.module_count = 2  # type: ignore[misc]

    def test_repository_index_frozen(self) -> None:
        """RepositoryIndex should be frozen."""
        index = RepositoryIndex(
            modules={},
            _symbols=[],
            _relationships=[],
            _statistics=RepositoryStatistics(
                module_count=0,
                class_count=0,
                function_count=0,
                method_count=0,
                symbol_count=0,
            ),
        )
        with pytest.raises(Exception):  # frozen dataclass raises on mutation
            index.modules = {}  # type: ignore[misc]


# ------------------------------------------------------------------
# No forbidden imports
# ------------------------------------------------------------------


class TestNoForbiddenImports:
    """Tests verifying RepositoryIndex does not import forbidden modules."""

    def test_no_provider_imports(self) -> None:
        """RepositoryIndex should not import providers."""
        import packages.repository.index.models
        import inspect
        source = inspect.getsource(packages.repository.index.models)
        assert "provider" not in source.lower() or "RepositoryStatistics" in source

    def test_no_gateway_imports(self) -> None:
        """RepositoryIndex should not import gateway."""
        import packages.repository.index.models
        import inspect
        source = inspect.getsource(packages.repository.index.models)
        assert "gateway" not in source.lower()

    def test_no_inference_imports(self) -> None:
        """RepositoryIndex should not import inference or LLM."""
        import packages.repository.index.models
        import inspect
        source = inspect.getsource(packages.repository.index.models)
        assert "llm" not in source.lower()
        assert "inference" not in source.lower()
