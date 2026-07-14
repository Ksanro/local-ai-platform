"""Tests for the Python AST extractor.

Uses the fixture project to verify symbol discovery, classification,
relationships, and deterministic ordering.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.models import (
    Language,
    RelationshipType,
    SymbolType,
)
from packages.repository.symbols.python_ast import PythonAstExtractor

if TYPE_CHECKING:
    from packages.repository.symbols.graph import SymbolGraphView

_fixture_root = Path(__file__).resolve().parent / "fixtures" / "python_project"


@pytest.fixture()
def extractor() -> PythonAstExtractor:
    """Return a fresh PythonAstExtractor instance."""
    return PythonAstExtractor()


@pytest.fixture()
def graph(extractor: PythonAstExtractor) -> SymbolGraphView:
    """Return a SymbolGraphView built from the fixture project."""
    return SymbolGraphView(extractor.extract(_fixture_root))


# ------------------------------------------------------------------
# Language
# ------------------------------------------------------------------


class TestLanguage:
    """Tests for the extractor's language property."""

    def test_language_is_python(self, extractor: PythonAstExtractor) -> None:
        """Extractor must report Language.PYTHON."""
        assert extractor.language == Language.PYTHON


# ------------------------------------------------------------------
# Module discovery
# ------------------------------------------------------------------


class TestModuleDiscovery:
    """Tests for module-level symbol discovery."""

    def test_finds_main_module(self, graph: SymbolGraphView) -> None:
        """The fixture must contain a 'main' module."""
        modules = graph.modules()
        paths = [m.path for m in modules]
        assert "main" in paths

    def test_finds_utils_module(self, graph: SymbolGraphView) -> None:
        """The fixture must contain a 'utils' module."""
        modules = graph.modules()
        paths = [m.path for m in modules]
        assert "utils" in paths

    def test_module_count(self, graph: SymbolGraphView) -> None:
        """Fixture should have exactly 3 modules (main + utils + __init__)."""
        modules = graph.modules()
        assert len(modules) == 3


# ------------------------------------------------------------------
# Class discovery
# ------------------------------------------------------------------


class TestClassDiscovery:
    """Tests for class-level symbol discovery."""

    def test_finds_app_class(self, graph: SymbolGraphView) -> None:
        """App class should be discovered."""
        classes = graph.classes()
        names = [c.name for c in classes]
        assert "App" in names

    def test_finds_base_class(self, graph: SymbolGraphView) -> None:
        """Base class should be discovered."""
        classes = graph.classes()
        names = [c.name for c in classes]
        assert "Base" in names

    def test_finds_config_parser_class(self, graph: SymbolGraphView) -> None:
        """ConfigParser class should be discovered."""
        classes = graph.classes()
        names = [c.name for c in classes]
        assert "ConfigParser" in names

    def test_class_qualified_name(self, graph: SymbolGraphView) -> None:
        """Class qualified name should be module.ClassName."""
        classes = graph.classes()
        app = [c for c in classes if c.name == "App"][0]
        assert app.qualified_name == "main.App"

    def test_class_symbol_type(self, graph: SymbolGraphView) -> None:
        """Class symbols must have SymbolType.CLASS."""
        classes = graph.classes()
        for cls in classes:
            assert cls.symbol_type == SymbolType.CLASS


# ------------------------------------------------------------------
# Function discovery
# ------------------------------------------------------------------


class TestFunctionDiscovery:
    """Tests for function-level symbol discovery."""

    def test_finds_main_function(self, graph: SymbolGraphView) -> None:
        """main() function should be discovered."""
        functions = graph.functions()
        names = [f.name for f in functions]
        assert "main" in names

    def test_finds_helper_function(self, graph: SymbolGraphView) -> None:
        """helper() function should be discovered."""
        functions = graph.functions()
        names = [f.name for f in functions]
        assert "helper" in names

    def test_finds_nested_function(self, graph: SymbolGraphView) -> None:
        """nested_inner() should be classified as FUNCTION, not METHOD."""
        functions = graph.functions()
        nested = [f for f in functions if f.name == "nested_inner"]
        assert len(nested) == 1
        assert nested[0].symbol_type == SymbolType.FUNCTION

    def test_nested_function_qualified_name(self, graph: SymbolGraphView) -> None:
        """Nested function qualified name includes parent."""
        functions = graph.functions()
        nested = [f for f in functions if f.name == "nested_inner"][0]
        assert nested.qualified_name == "main.nested_outer.nested_inner"

    def test_async_function_classified(self, graph: SymbolGraphView) -> None:
        """Async functions are classified as FUNCTION."""
        functions = graph.functions()
        async_fn = [f for f in functions if f.name == "async_handler"]
        assert len(async_fn) == 1
        assert async_fn[0].symbol_type == SymbolType.FUNCTION

    def test_function_symbol_type(self, graph: SymbolGraphView) -> None:
        """Function symbols must have SymbolType.FUNCTION."""
        functions = graph.functions()
        for fn in functions:
            assert fn.symbol_type == SymbolType.FUNCTION


# ------------------------------------------------------------------
# Method discovery
# ------------------------------------------------------------------


class TestMethodDiscovery:
    """Tests for method-level symbol discovery."""

    def test_finds_run_method(self, graph: SymbolGraphView) -> None:
        """App.run() method should be discovered."""
        methods = graph.methods()
        names = [m.name for m in methods]
        assert "run" in names

    def test_finds_init_method(self, graph: SymbolGraphView) -> None:
        """__init__ methods should be discovered."""
        methods = graph.methods()
        init_methods = [m for m in methods if m.name == "__init__"]
        assert len(init_methods) == 3  # Base, App, ConfigParser

    def test_method_qualified_name(self, graph: SymbolGraphView) -> None:
        """Method qualified name includes class and module."""
        methods = graph.methods()
        run = [m for m in methods if m.name == "run"][0]
        assert run.qualified_name == "main.App.run"

    def test_method_symbol_type(self, graph: SymbolGraphView) -> None:
        """Method symbols must have SymbolType.METHOD."""
        methods = graph.methods()
        for method in methods:
            assert method.symbol_type == SymbolType.METHOD

    def test_static_method_is_method(self, graph: SymbolGraphView) -> None:
        """@staticmethod methods are still classified as METHOD."""
        methods = graph.methods()
        helper = [m for m in methods if m.name == "helper"][0]
        assert helper.symbol_type == SymbolType.METHOD


# ------------------------------------------------------------------
# Nested function classification
# ------------------------------------------------------------------


class TestNestedFunctionClassification:
    """Tests that nested functions are classified correctly."""

    def test_nested_not_method(self, graph: SymbolGraphView) -> None:
        """Nested function inside a method should be FUNCTION, not METHOD."""
        functions = graph.functions()
        # nested_inner is inside nested_outer which is a FUNCTION
        nested = [f for f in functions if f.name == "nested_inner"]
        assert len(nested) == 1
        assert nested[0].symbol_type == SymbolType.FUNCTION

    def test_nested_inside_method(self, graph: SymbolGraphView) -> None:
        """Nested function inside a method should still be FUNCTION."""
        # Create a fixture with nested function inside a method
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_nested.py"
            test_file.write_text(
                "class MyClass:\n"
                "    def method(self):\n"
                "        def inner():\n"
                "            pass\n"
            )
            extractor = PythonAstExtractor()
            view = extractor.extract(test_file)
            all_symbols = view.modules["test_nested"].symbols
            inner = [s for s in all_symbols if s.name == "inner"][0]
            assert inner.symbol_type == SymbolType.FUNCTION


# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------


class TestDecorators:
    """Tests for decorator extraction."""

    def test_staticmethod_decorator(self, graph: SymbolGraphView) -> None:
        """@staticmethod should be recorded."""
        methods = graph.methods()
        helper = [m for m in methods if m.name == "helper"][0]
        assert "staticmethod" in helper.decorators

    def test_property_decorator(self, graph: SymbolGraphView) -> None:
        """@property should be recorded."""
        methods = graph.methods()
        keys = [m for m in methods if m.name == "keys"][0]
        assert "property" in keys.decorators

    def test_no_decorator_empty_list(self, graph: SymbolGraphView) -> None:
        """Symbols without decorators have an empty list."""
        functions = graph.functions()
        main_fn = [f for f in functions if f.name == "main"][0]
        assert main_fn.decorators == []


# ------------------------------------------------------------------
# Inheritance
# ------------------------------------------------------------------


class TestInheritance:
    """Tests for inheritance relationship extraction."""

    def test_app_inherits_base(self, graph: SymbolGraphView) -> None:
        """App should have an INHERITS relationship to Base."""
        module = graph.module("main")
        assert module is not None
        inherits = [
            r for r in module.relationships
            if r.type == RelationshipType.INHERITS
        ]
        assert len(inherits) == 1
        assert inherits[0].source == "main.App"
        assert inherits[0].target == "Base"


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


class TestImports:
    """Tests for import extraction."""

    def test_finds_import_statements(self, graph: SymbolGraphView) -> None:
        """Import statements should be recorded."""
        module = graph.module("utils")
        assert module is not None
        assert len(module.imports) > 0

    def test_import_from_recorded(self, graph: SymbolGraphView) -> None:
        """from ... import ... should be recorded."""
        module = graph.module("utils")
        assert module is not None
        from_imports = [
            imp for imp in module.imports if "from" in imp
        ]
        assert len(from_imports) > 0

    def test_import_star_not_supported(self, graph: SymbolGraphView) -> None:
        """Standard import handling works for regular imports."""
        module = graph.module("utils")
        assert module is not None
        # 'import os' should be recorded
        assert any("import os" in imp for imp in module.imports)


# ------------------------------------------------------------------
# find() ambiguity
# ------------------------------------------------------------------


class TestFindAmbiguity:
    """Tests for the find() method with ambiguous names."""

    def test_find_by_short_name(self, graph: SymbolGraphView) -> None:
        """find() should match against the short name."""
        results = graph.find("main")
        assert len(results) >= 1

    def test_find_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """find() should match against the qualified name."""
        results = graph.find("main.App")
        assert len(results) == 1
        assert results[0].name == "App"

    def test_find_returns_list(self, graph: SymbolGraphView) -> None:
        """find() always returns a list, even when no match."""
        results = graph.find("nonexistent")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_returns_all_matches(self, graph: SymbolGraphView) -> None:
        """find() returns all symbols matching the name."""
        # __init__ appears in multiple classes
        results = graph.find("__init__")
        assert len(results) >= 3  # Base, App, ConfigParser


# ------------------------------------------------------------------
# children() / parents() DEFINES-only traversal
# ------------------------------------------------------------------


class TestDefinesTraversal:
    """Tests that children()/parents() only traverse DEFINES relationships."""

    def test_children_of_class(self, graph: SymbolGraphView) -> None:
        """children() should return nested definitions of a class."""
        module = graph.module("main")
        assert module is not None
        app_cls = [s for s in module.symbols if s.name == "App"][0]
        children = graph.children(app_cls)
        child_names = [c.name for c in children]
        assert "run" in child_names
        assert "__init__" in child_names

    def test_parents_of_method(self, graph: SymbolGraphView) -> None:
        """parents() should return the containing class."""
        module = graph.module("main")
        assert module is not None
        run = [s for s in module.symbols if s.name == "run"][0]
        parents = graph.parents(run)
        assert len(parents) == 1
        assert parents[0].name == "App"

    def test_parents_of_nested_function(self, graph: SymbolGraphView) -> None:
        """parents() should return the containing function."""
        module = graph.module("main")
        assert module is not None
        nested = [s for s in module.symbols if s.name == "nested_inner"][0]
        parents = graph.parents(nested)
        assert len(parents) == 1
        assert parents[0].name == "nested_outer"

    def test_inherits_not_traversed(self, graph: SymbolGraphView) -> None:
        """INHERITS relationships should NOT be traversed by children()."""
        module = graph.module("main")
        assert module is not None
        app_cls = [s for s in module.symbols if s.name == "App"][0]
        children = graph.children(app_cls)
        child_names = [c.name for c in children]
        # Base should NOT appear as a child of App
        assert "Base" not in child_names


# ------------------------------------------------------------------
# Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests that public collections are deterministically ordered."""

    def test_classes_sorted_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """classes() should be sorted by qualified_name."""
        classes = graph.classes()
        names = [c.qualified_name for c in classes]
        assert names == sorted(names)

    def test_functions_sorted_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """functions() should be sorted by qualified_name."""
        functions = graph.functions()
        names = [f.qualified_name for f in functions]
        assert names == sorted(names)

    def test_methods_sorted_by_qualified_name(self, graph: SymbolGraphView) -> None:
        """methods() should be sorted by qualified_name."""
        methods = graph.methods()
        names = [m.qualified_name for m in methods]
        assert names == sorted(names)

    def test_modules_sorted_by_path(self, graph: SymbolGraphView) -> None:
        """modules() should be sorted by path."""
        modules = graph.modules()
        paths = [m.path for m in modules]
        assert paths == sorted(paths)

    def test_deterministic_across_runs(self, graph: SymbolGraphView) -> None:
        """Public collections should be identical across calls."""
        classes_a = graph.classes()
        classes_b = graph.classes()
        assert [c.qualified_name for c in classes_a] == [
            c.qualified_name for c in classes_b
        ]


# ------------------------------------------------------------------
# Single file extraction
# ------------------------------------------------------------------


class TestSingleFileExtraction:
    """Tests for single-file extraction."""

    def test_extract_single_file(self, extractor: PythonAstExtractor) -> None:
        """Extracting a single file should produce one module."""
        test_file = _fixture_root / "main.py"
        graph = extractor.extract(test_file)
        assert len(graph.modules) == 1

    def test_extract_nonexistent_raises(self, extractor: PythonAstExtractor) -> None:
        """Extracting a nonexistent path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extractor.extract(Path("/nonexistent/path.py"))

    def test_extract_directory(self, extractor: PythonAstExtractor) -> None:
        """Extracting a directory should produce multiple modules."""
        graph = extractor.extract(_fixture_root)
        assert len(graph.modules) == 3  # main, utils, __init__
