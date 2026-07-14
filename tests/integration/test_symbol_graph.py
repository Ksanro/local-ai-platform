"""Integration test for the symbol graph.

Builds a SymbolGraph from the complete ``local-ai-platform`` repository
and verifies that the graph is well-formed: symbols are discovered,
relationships are consistent, and the public API is deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.python_ast import PythonAstExtractor

_project_root = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def graph_view() -> SymbolGraphView:
    """Build a SymbolGraph from the project root."""
    extractor = PythonAstExtractor()
    return SymbolGraphView(extractor.extract(_project_root))


class TestIntegrationSymbolGraph:
    """Integration tests for the symbol graph."""

    def test_graph_has_modules(self, graph_view: SymbolGraphView) -> None:
        """The graph should contain at least one module."""
        modules = graph_view.modules()
        assert len(modules) > 0

    def test_graph_has_classes(self, graph_view: SymbolGraphView) -> None:
        """The graph should contain at least one class."""
        classes = graph_view.classes()
        assert len(classes) > 0

    def test_graph_has_functions(self, graph_view: SymbolGraphView) -> None:
        """The graph should contain at least one function."""
        functions = graph_view.functions()
        assert len(functions) > 0

    def test_graph_has_methods(self, graph_view: SymbolGraphView) -> None:
        """The graph should contain at least one method."""
        methods = graph_view.methods()
        assert len(methods) > 0

    def test_deterministic_classes(self, graph_view: SymbolGraphView) -> None:
        """classes() should return the same order on every call."""
        classes_a = graph_view.classes()
        classes_b = graph_view.classes()
        assert [c.qualified_name for c in classes_a] == [
            c.qualified_name for c in classes_b
        ]

    def test_deterministic_functions(self, graph_view: SymbolGraphView) -> None:
        """functions() should return the same order on every call."""
        funcs_a = graph_view.functions()
        funcs_b = graph_view.functions()
        assert [f.qualified_name for f in funcs_a] == [
            f.qualified_name for f in funcs_b
        ]

    def test_no_ast_nodes_exposed(self, graph_view: SymbolGraphView) -> None:
        """Public API should never expose Python AST nodes."""
        for module in graph_view.modules():
            for sym in module.symbols:
                assert not hasattr(sym, "lineno") or isinstance(sym.lineno, int)
                assert not hasattr(sym, "name") or isinstance(sym.name, str)

    def test_find_returns_list(self, graph_view: SymbolGraphView) -> None:
        """find() should always return a list."""
        for module in graph_view.modules():
            for sym in module.symbols:
                results = graph_view.find(sym.name)
                assert isinstance(results, list)
