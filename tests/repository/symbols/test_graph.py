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
# callers()
# ------------------------------------------------------------------


class TestCallers:
    """Tests for the callers() accessor."""

    def test_callers_returns_callers_via_calls_relationship(self) -> None:
        """callers() should return symbols that call the given symbol."""
        symbols = [
            _make_symbol("caller", "pkg.caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("callee", "pkg.callee", SymbolType.FUNCTION, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.caller",
                target="pkg.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        callee = graph.find("pkg.callee")[0]
        callers = graph.callers(callee)
        assert len(callers) == 1
        assert callers[0].name == "caller"

    def test_callers_of_leaf_returns_empty(self) -> None:
        """callers() should return empty list for symbols with no callers."""
        symbols = [
            _make_symbol("lonely", "pkg.lonely", SymbolType.FUNCTION, lineno=1),
        ]
        relationships: list[Relationship] = []
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        lonely = graph.find("pkg.lonely")[0]
        callers = graph.callers(lonely)
        assert len(callers) == 0

    def test_callers_only_traverses_calls_not_defines(self) -> None:
        """callers() should only traverse CALLS relationships."""
        symbols = [
            _make_symbol("parent", "pkg.parent", SymbolType.FUNCTION, lineno=1),
            _make_symbol("child", "pkg.parent.child", SymbolType.FUNCTION, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.parent",
                target="pkg.parent.child",
                type=RelationshipType.DEFINES,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        child = graph.find("pkg.parent.child")[0]
        callers = graph.callers(child)
        assert len(callers) == 0

    def test_callers_sorted(self) -> None:
        """callers() should return sorted results."""
        symbols = [
            _make_symbol("z_caller", "pkg.z_caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("a_caller", "pkg.a_caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("m_caller", "pkg.m_caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("target", "pkg.target", SymbolType.FUNCTION, lineno=10),
        ]
        relationships = [
            Relationship(
                source="pkg.z_caller",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.a_caller",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.m_caller",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        target = graph.find("pkg.target")[0]
        callers = graph.callers(target)
        names = [c.name for c in callers]
        assert names == sorted(names)

    def test_callers_cross_module(self) -> None:
        """callers() should find callers across modules."""
        symbols = [
            _make_symbol(
                "caller",
                "mod_a.caller",
                SymbolType.FUNCTION,
                lineno=1,
                module="mod_a.py",
            ),
            _make_symbol(
                "callee",
                "mod_b.callee",
                SymbolType.FUNCTION,
                lineno=5,
                module="mod_b.py",
            ),
        ]
        relationships_a = [
            Relationship(
                source="mod_a.caller",
                target="mod_b.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        relationships_b: list[Relationship] = []
        mod_a_syms = [s for s in symbols if s.module == "mod_a.py"]
        mod_b_syms = [s for s in symbols if s.module == "mod_b.py"]
        module_a = Module(
            path="mod_a.py",
            symbols=mod_a_syms,
            relationships=relationships_a,
        )
        module_b = Module(
            path="mod_b.py",
            symbols=mod_b_syms,
            relationships=relationships_b,
        )
        graph = SymbolGraphView(
            SymbolGraph(
                modules={
                    "mod_a.py": module_a,
                    "mod_b.py": module_b,
                }
            )
        )
        callee = graph.find("mod_b.callee")[0]
        callers = graph.callers(callee)
        assert len(callers) == 1
        assert callers[0].name == "caller"

    def test_multiple_callers(self) -> None:
        """callers() should return all callers of a symbol."""
        symbols = [
            _make_symbol("a", "pkg.a", SymbolType.FUNCTION, lineno=1),
            _make_symbol("b", "pkg.b", SymbolType.FUNCTION, lineno=3),
            _make_symbol("c", "pkg.c", SymbolType.FUNCTION, lineno=5),
            _make_symbol("target", "pkg.target", SymbolType.FUNCTION, lineno=10),
        ]
        relationships = [
            Relationship(
                source="pkg.a",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.b",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.c",
                target="pkg.target",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        target = graph.find("pkg.target")[0]
        callers = graph.callers(target)
        assert len(callers) == 3
        names = {c.name for c in callers}
        assert names == {"a", "b", "c"}

    def test_self_call(self) -> None:
        """callers() should handle self-recursive calls."""
        symbols = [
            _make_symbol("recurse", "pkg.recurse", SymbolType.FUNCTION, lineno=1),
        ]
        relationships = [
            Relationship(
                source="pkg.recurse",
                target="pkg.recurse",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        recurse = graph.find("pkg.recurse")[0]
        callers = graph.callers(recurse)
        assert len(callers) == 1
        assert callers[0].name == "recurse"


# ------------------------------------------------------------------
# callees()
# ------------------------------------------------------------------


class TestCallees:
    """Tests for the callees() accessor."""

    def test_callees_returns_callees_via_calls_relationship(self) -> None:
        """callees() should return symbols that the given symbol calls."""
        symbols = [
            _make_symbol("caller", "pkg.caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("callee", "pkg.callee", SymbolType.FUNCTION, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.caller",
                target="pkg.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        caller = graph.find("pkg.caller")[0]
        callees = graph.callees(caller)
        assert len(callees) == 1
        assert callees[0].name == "callee"

    def test_callees_of_leaf_returns_empty(self) -> None:
        """callees() should return empty list for symbols with no callees."""
        symbols = [
            _make_symbol("lonely", "pkg.lonely", SymbolType.FUNCTION, lineno=1),
        ]
        relationships: list[Relationship] = []
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        lonely = graph.find("pkg.lonely")[0]
        callees = graph.callees(lonely)
        assert len(callees) == 0

    def test_callees_only_traverses_calls_not_defines(self) -> None:
        """callees() should only traverse CALLS relationships."""
        symbols = [
            _make_symbol("parent", "pkg.parent", SymbolType.FUNCTION, lineno=1),
            _make_symbol("child", "pkg.parent.child", SymbolType.FUNCTION, lineno=5),
        ]
        relationships = [
            Relationship(
                source="pkg.parent",
                target="pkg.parent.child",
                type=RelationshipType.DEFINES,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        parent = graph.find("pkg.parent")[0]
        callees = graph.callees(parent)
        assert len(callees) == 0

    def test_callees_sorted(self) -> None:
        """callees() should return sorted results."""
        symbols = [
            _make_symbol("caller", "pkg.caller", SymbolType.FUNCTION, lineno=1),
            _make_symbol("z_callee", "pkg.z_callee", SymbolType.FUNCTION, lineno=3),
            _make_symbol("a_callee", "pkg.a_callee", SymbolType.FUNCTION, lineno=5),
            _make_symbol("m_callee", "pkg.m_callee", SymbolType.FUNCTION, lineno=7),
        ]
        relationships = [
            Relationship(
                source="pkg.caller",
                target="pkg.z_callee",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.caller",
                target="pkg.a_callee",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.caller",
                target="pkg.m_callee",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        caller = graph.find("pkg.caller")[0]
        callees = graph.callees(caller)
        names = [c.name for c in callees]
        assert names == sorted(names)

    def test_callees_cross_module(self) -> None:
        """callees() should find callees across modules."""
        symbols = [
            _make_symbol(
                "caller",
                "mod_a.caller",
                SymbolType.FUNCTION,
                lineno=1,
                module="mod_a.py",
            ),
            _make_symbol(
                "callee",
                "mod_b.callee",
                SymbolType.FUNCTION,
                lineno=5,
                module="mod_b.py",
            ),
        ]
        relationships_a = [
            Relationship(
                source="mod_a.caller",
                target="mod_b.callee",
                type=RelationshipType.CALLS,
            ),
        ]
        relationships_b: list[Relationship] = []
        mod_a_syms = [s for s in symbols if s.module == "mod_a.py"]
        mod_b_syms = [s for s in symbols if s.module == "mod_b.py"]
        module_a = Module(
            path="mod_a.py",
            symbols=mod_a_syms,
            relationships=relationships_a,
        )
        module_b = Module(
            path="mod_b.py",
            symbols=mod_b_syms,
            relationships=relationships_b,
        )
        graph = SymbolGraphView(
            SymbolGraph(
                modules={
                    "mod_a.py": module_a,
                    "mod_b.py": module_b,
                }
            )
        )
        caller = graph.find("mod_a.caller")[0]
        callees = graph.callees(caller)
        assert len(callees) == 1
        assert callees[0].name == "callee"

    def test_multiple_callees(self) -> None:
        """callees() should return all callees of a symbol."""
        symbols = [
            _make_symbol("source", "pkg.source", SymbolType.FUNCTION, lineno=1),
            _make_symbol("a", "pkg.a", SymbolType.FUNCTION, lineno=3),
            _make_symbol("b", "pkg.b", SymbolType.FUNCTION, lineno=5),
            _make_symbol("c", "pkg.c", SymbolType.FUNCTION, lineno=7),
        ]
        relationships = [
            Relationship(
                source="pkg.source",
                target="pkg.a",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.source",
                target="pkg.b",
                type=RelationshipType.CALLS,
            ),
            Relationship(
                source="pkg.source",
                target="pkg.c",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        source = graph.find("pkg.source")[0]
        callees = graph.callees(source)
        assert len(callees) == 3
        names = {c.name for c in callees}
        assert names == {"a", "b", "c"}

    def test_self_call(self) -> None:
        """callees() should handle self-recursive calls."""
        symbols = [
            _make_symbol("recurse", "pkg.recurse", SymbolType.FUNCTION, lineno=1),
        ]
        relationships = [
            Relationship(
                source="pkg.recurse",
                target="pkg.recurse",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        recurse = graph.find("pkg.recurse")[0]
        callees = graph.callees(recurse)
        assert len(callees) == 1
        assert callees[0].name == "recurse"

    def test_callees_ignores_unknown_targets(self) -> None:
        """callees() should skip targets that are not in the symbol index."""
        symbols = [
            _make_symbol("caller", "pkg.caller", SymbolType.FUNCTION, lineno=1),
        ]
        relationships = [
            Relationship(
                source="pkg.caller",
                target="unknown.external",
                type=RelationshipType.CALLS,
            ),
        ]
        module = Module(path="pkg", symbols=symbols, relationships=relationships)
        graph = SymbolGraphView(SymbolGraph(modules={"pkg": module}))
        caller = graph.find("pkg.caller")[0]
        callees = graph.callees(caller)
        assert len(callees) == 0


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
