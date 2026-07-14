"""Tests for the SymbolGraph public API.

Verifies that SymbolGraphView provides correct, sorted, read-only access
to the underlying SymbolGraph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolGraph,
    SymbolType,
)

if TYPE_CHECKING:
    pass


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_symbol(
    name: str,
    qualified_name: str,
    symbol_type: SymbolType,
    module: str = "main",
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


def _make_graph() -> SymbolGraph:
    """Create a minimal SymbolGraph for testing."""
    symbols = [
        _make_symbol("App", "main.App", SymbolType.CLASS, lineno=1),
        _make_symbol("run", "main.App.run", SymbolType.METHOD, lineno=5),
        _make_symbol("helper", "main.helper", SymbolType.FUNCTION, lineno=10),
        _make_symbol("nested", "main.helper.nested", SymbolType.FUNCTION, lineno=12),
    ]
    relationships = [
        Relationship(
            source="main.App",
            target="main.App.run",
            type=RelationshipType.DEFINES,
        ),
        Relationship(
            source="main.helper",
            target="main.helper.nested",
            type=RelationshipType.DEFINES,
        ),
    ]
    module = Module(path="main", symbols=symbols, relationships=relationships)
    return SymbolGraph(modules={"main": module})


@pytest.fixture()
def graph() -> SymbolGraphView:
    """Return a SymbolGraphView over a test graph."""
    return SymbolGraphView(_make_graph())


# ------------------------------------------------------------------
# modules()
# ------------------------------------------------------------------


class TestModules:
    """Tests for the modules() accessor."""

    def test_returns_all_modules(self, graph: SymbolGraphView) -> None:
        """modules() should return all modules."""
        modules = graph.modules()
        assert len(modules) == 1

    def test_modules_sorted_by_path(self, graph: SymbolGraphView) -> None:
        """modules() should be sorted by path."""
        modules = graph.modules()
        paths = [m.path for m in modules]
        assert paths == sorted(paths)

    def test_module_by_path(self, graph: SymbolGraphView) -> None:
        """module() should return the module for a given path."""
        mod = graph.module("main")
        assert mod is not None
        assert mod.path == "main"

    def test_module_not_found(self, graph: SymbolGraphView) -> None:
        """module() should return None for unknown paths."""
        assert graph.module("unknown") is None


# ------------------------------------------------------------------
# classes()
# ------------------------------------------------------------------


class TestClasses:
    """Tests for the classes() accessor."""

    def test_returns_classes(self, graph: SymbolGraphView) -> None:
        """classes() should return all CLASS symbols."""
        classes = graph.classes()
        assert len(classes) == 1
        assert classes[0].name == "App"

    def test_classes_sorted(self, graph: SymbolGraphView) -> None:
        """classes() should be sorted by qualified_name."""
        classes = graph.classes()
        names = [c.qualified_name for c in classes]
        assert names == sorted(names)


# ------------------------------------------------------------------
# functions()
# ------------------------------------------------------------------


class TestFunctions:
    """Tests for the functions() accessor."""

    def test_returns_functions(self, graph: SymbolGraphView) -> None:
        """functions() should return all FUNCTION symbols."""
        functions = graph.functions()
        names = [f.name for f in functions]
        assert "helper" in names
        assert "nested" in names

    def test_excludes_methods(self, graph: SymbolGraphView) -> None:
        """functions() should not include METHOD symbols."""
        functions = graph.functions()
        names = [f.name for f in functions]
        assert "run" not in names

    def test_functions_sorted(self, graph: SymbolGraphView) -> None:
        """functions() should be sorted by qualified_name."""
        functions = graph.functions()
        names = [f.qualified_name for f in functions]
        assert names == sorted(names)


# ------------------------------------------------------------------
# methods()
# ------------------------------------------------------------------


class TestMethods:
    """Tests for the methods() accessor."""

    def test_returns_methods(self, graph: SymbolGraphView) -> None:
        """methods() should return all METHOD symbols."""
        methods = graph.methods()
        assert len(methods) == 1
        assert methods[0].name == "run"

    def test_excludes_functions(self, graph: SymbolGraphView) -> None:
        """methods() should not include FUNCTION symbols."""
        methods = graph.methods()
        names = [m.name for m in methods]
        assert "helper" not in names

    def test_methods_sorted(self, graph: SymbolGraphView) -> None:
        """methods() should be sorted by qualified_name."""
        methods = graph.methods()
        names = [m.qualified_name for m in methods]
        assert names == sorted(names)


# ------------------------------------------------------------------
# find()
# ------------------------------------------------------------------


class TestFind:
    """Tests for the find() accessor."""

    def test_find_by_name(self, graph: SymbolGraphView) -> None:
        """find() should match against the short name."""
        results = graph.find("App")
        assert len(results) == 1
        assert results[0].name == "App"

    def test_find_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """find() should match against the qualified name."""
        results = graph.find("main.App")
        assert len(results) == 1
        assert results[0].qualified_name == "main.App"

    def test_find_no_match(self, graph: SymbolGraphView) -> None:
        """find() should return empty list for no match."""
        results = graph.find("nonexistent")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_always_returns_list(self, graph: SymbolGraphView) -> None:
        """find() always returns a list, never None."""
        results = graph.find("App")
        assert isinstance(results, list)

    def test_find_multiple_matches(self, graph: SymbolGraphView) -> None:
        """find() should return all matching symbols."""
        # "run" matches both name and qualified_name of main.App.run
        results = graph.find("run")
        assert len(results) == 1
        assert results[0].qualified_name == "main.App.run"


# ------------------------------------------------------------------
# children()
# ------------------------------------------------------------------


class TestChildren:
    """Tests for the children() accessor."""

    def test_children_of_class(self, graph: SymbolGraphView) -> None:
        """children() should return nested definitions."""
        app = graph.find("main.App")[0]
        children = graph.children(app)
        names = [c.name for c in children]
        assert "run" in names

    def test_children_of_function(self, graph: SymbolGraphView) -> None:
        """children() should return nested definitions of a function."""
        helper = graph.find("main.helper")[0]
        children = graph.children(helper)
        names = [c.name for c in children]
        assert "nested" in names

    def test_children_of_leaf(self, graph: SymbolGraphView) -> None:
        """children() should return empty list for leaf symbols."""
        nested = graph.find("main.helper.nested")[0]
        children = graph.children(nested)
        assert len(children) == 0

    def test_inherits_not_traversed(self) -> None:
        """INHERITS relationships should not be traversed by children()."""
        # Create a graph with an INHERITS relationship
        symbols = [
            _make_symbol("Child", "pkg.Child", SymbolType.CLASS, lineno=1),
            _make_symbol("Parent", "pkg.Parent", SymbolType.CLASS, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.Child",
                target="pkg.Parent",
                type=RelationshipType.INHERITS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        child = graph.find("pkg.Child")[0]
        children = graph.children(child)
        assert len(children) == 0


# ------------------------------------------------------------------
# parents()
# ------------------------------------------------------------------


class TestParents:
    """Tests for the parents() accessor."""

    def test_parents_of_method(self, graph: SymbolGraphView) -> None:
        """parents() should return the containing class."""
        run = graph.find("main.App.run")[0]
        parents = graph.parents(run)
        assert len(parents) == 1
        assert parents[0].name == "App"

    def test_parents_of_nested_function(self, graph: SymbolGraphView) -> None:
        """parents() should return the containing function."""
        nested = graph.find("main.helper.nested")[0]
        parents = graph.parents(nested)
        assert len(parents) == 1
        assert parents[0].name == "helper"

    def test_parents_of_root(self, graph: SymbolGraphView) -> None:
        """parents() should return empty list for root-level symbols."""
        app = graph.find("main.App")[0]
        parents = graph.parents(app)
        assert len(parents) == 0

    def test_inherits_not_traversed(self) -> None:
        """INHERITS relationships should not be traversed by parents()."""
        symbols = [
            _make_symbol("Child", "pkg.Child", SymbolType.CLASS, lineno=1),
            _make_symbol("Parent", "pkg.Parent", SymbolType.CLASS, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.Child",
                target="pkg.Parent",
                type=RelationshipType.INHERITS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        parent = graph.find("pkg.Parent")[0]
        parents = graph.parents(parent)
        assert len(parents) == 0


# ------------------------------------------------------------------
# imports()
# ------------------------------------------------------------------


class TestImports:
    """Tests for the imports() accessor."""

    def test_empty_imports(self, graph: SymbolGraphView) -> None:
        """imports() should return empty list when no imports."""
        imports = graph.imports("main")
        assert isinstance(imports, list)
        assert len(imports) == 0

    def test_unknown_module(self, graph: SymbolGraphView) -> None:
        """imports() should return empty list for unknown modules."""
        imports = graph.imports("unknown")
        assert isinstance(imports, list)
        assert len(imports) == 0


# ------------------------------------------------------------------
# symbols()
# ------------------------------------------------------------------


class TestAllSymbols:
    """Tests for the symbols() accessor."""

    def test_returns_all_symbols(self, graph: SymbolGraphView) -> None:
        """symbols() should return all symbols."""
        all_syms = graph.symbols()
        assert len(all_syms) == 4

    def test_sorted_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """symbols() should be sorted by qualified_name."""
        all_syms = graph.symbols()
        names = [s.qualified_name for s in all_syms]
        assert names == sorted(names)
