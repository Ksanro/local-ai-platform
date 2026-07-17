"""Tests for the CallExtractor.

Verifies call relationship extraction across multiple scenarios:
- simple function calls
- method calls
- nested calls
- recursive calls
- mutual recursion
- cross-module calls
- unknown symbols
- duplicate calls
- deterministic ordering
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex
from packages.repository.relationships.base import RelationshipType
from packages.repository.relationships.call_extractor import CallExtractor
from packages.repository.symbols.models import (
    Module,
    Relationship,
    Symbol,
    SymbolType,
)
from packages.repository.symbols.models import (
    RelationshipType as SymbolRelationshipType,
)

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


def _make_index(
    symbols: list[Symbol],
    relationships: list[Relationship] | None = None,
    modules: dict[str, Module] | None = None,
) -> RepositoryIndex:
    """Create a RepositoryIndex from symbols and relationships.

    Args:
        symbols: List of Symbol instances.
        relationships: List of Relationship instances.
        modules: Optional modules dict. If None, derived from symbols.

    Returns:
        A RepositoryIndex with modules derived from the symbols.
    """
    mod_map: dict[str, Module] = modules if modules is not None else {}
    if not mod_map:
        for sym in symbols:
            if sym.module not in mod_map:
                mod_map[sym.module] = Module(path=sym.module)
            mod_map[sym.module].symbols.append(sym)

    rels = relationships or []
    for rel in rels:
        if rel.source in mod_map:
            mod_map[rel.source].relationships.append(rel)

    class_count = sum(1 for s in symbols if s.symbol_type == SymbolType.CLASS)
    function_count = sum(
        1 for s in symbols if s.symbol_type == SymbolType.FUNCTION
    )
    method_count = sum(1 for s in symbols if s.symbol_type == SymbolType.METHOD)

    from packages.repository.index.models import RepositoryStatistics

    statistics = RepositoryStatistics(
        module_count=len(mod_map),
        class_count=class_count,
        function_count=function_count,
        method_count=method_count,
        symbol_count=len(symbols),
    )

    return RepositoryIndex(
        modules=mod_map,
        _symbols=symbols,
        _relationships=rels,
        _statistics=statistics,
    )


@pytest.fixture()
def extractor() -> CallExtractor:
    """Return a CallExtractor instance."""
    return CallExtractor()


# ------------------------------------------------------------------
# Relationship type
# ------------------------------------------------------------------


class TestRelationshipType:
    """Tests for the relationship type property."""

    def test_relationship_type_is_calls(self, extractor: CallExtractor) -> None:
        """relationship_type should be RelationshipType.CALLS."""
        assert extractor.relationship_type == RelationshipType.CALLS


# ------------------------------------------------------------------
# Simple function calls
# ------------------------------------------------------------------


class TestSimpleFunctionCalls:
    """Tests for simple function call extraction."""

    def test_simple_function_call(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Simple function calls should be detected."""
        symbols = [
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
            _make_symbol("process", "main.process", SymbolType.FUNCTION, "main.py"),
            _make_symbol("main", "main.main", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def helper() -> str:
    return "hello"

def process(data: str) -> str:
    result = helper()
    return result + data

def main() -> None:
    output = process("test")
    print(output)
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # Should have: main.main -> main.process, process.process -> main.helper
        assert len(relationships) == 2
        sources = [(r.source, r.target) for r in relationships]
        assert ("main.main", "main.process") in sources
        assert ("main.process", "main.helper") in sources

    def test_no_call_no_relationship(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Functions with no calls should produce no relationships."""
        symbols = [
            _make_symbol("standalone", "main.standalone", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="def standalone() -> None:\n    pass\n",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)
        assert len(relationships) == 0


# ------------------------------------------------------------------
# Method calls
# ------------------------------------------------------------------


class TestMethodCalls:
    """Tests for method call extraction."""

    def test_self_method_call(
        self,
        extractor: CallExtractor,
    ) -> None:
        """self.method() calls should be detected."""
        symbols = [
            _make_symbol("Service", "main.Service", SymbolType.CLASS, "main.py"),
            _make_symbol("add", "main.Service.add", SymbolType.METHOD, "main.py"),
            _make_symbol("get_all", "main.Service.get_all", SymbolType.METHOD, "main.py"),
            _make_symbol("process", "main.Service.process", SymbolType.METHOD, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
class Service:
    def add(self, item: str) -> None:
        self.data.append(item)

    def get_all(self) -> list[str]:
        return self.data

    def process(self) -> str:
        return ", ".join(self.get_all())
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # process() should call get_all()
        assert len(relationships) == 1
        assert relationships[0].source == "main.Service.process"
        assert relationships[0].target == "main.Service.get_all"

    def test_method_calling_method_on_attribute(
        self,
        extractor: CallExtractor,
    ) -> None:
        """self.method() calls within a class should be detected."""
        symbols = [
            _make_symbol("Service", "main.Service", SymbolType.CLASS, "main.py"),
            _make_symbol("add", "main.Service.add", SymbolType.METHOD, "main.py"),
            _make_symbol("get_all", "main.Service.get_all", SymbolType.METHOD, "main.py"),
            _make_symbol("process", "main.Service.process", SymbolType.METHOD, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
class Service:
    def add(self, item: str) -> None:
        pass

    def get_all(self) -> list[str]:
        return []

    def process(self) -> str:
        return ", ".join(self.get_all())
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # process() calls self.get_all() — should be detected
        assert len(relationships) >= 1
        sources = [r.source for r in relationships]
        assert "main.Service.process" in sources


# ------------------------------------------------------------------
# Nested calls
# ------------------------------------------------------------------


class TestNestedCalls:
    """Tests for nested call extraction."""

    def test_nested_call(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Calls within calls should be detected."""
        symbols = [
            _make_symbol("inner", "main.inner", SymbolType.FUNCTION, "main.py"),
            _make_symbol("middle", "main.middle", SymbolType.FUNCTION, "main.py"),
            _make_symbol("outer", "main.outer", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def inner() -> str:
    return "inner"

def middle(value: str) -> str:
    return value + "middle"

def outer() -> str:
    result = middle(inner())
    return result
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # In middle(inner()), both middle and inner are called from outer's scope.
        # The AST visitor attributes all calls to the current scope.
        sources = [r.source for r in relationships]
        targets = [r.target for r in relationships]
        assert "main.outer" in sources
        assert "main.middle" in targets
        assert "main.inner" in targets
        # outer is the caller of both
        assert sources.count("main.outer") == 2

    def test_chained_calls(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Chained calls should all be detected."""
        symbols = [
            _make_symbol("inner", "main.inner", SymbolType.FUNCTION, "main.py"),
            _make_symbol("middle", "main.middle", SymbolType.FUNCTION, "main.py"),
            _make_symbol("chained", "main.chained", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def inner() -> str:
    return "inner"

def middle(value: str) -> str:
    return value + "middle"

def chained() -> str:
    return middle(middle(inner()))
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # chained calls middle (twice, deduplicated) and inner.
        # After deduplication: chained->middle, chained->inner
        sources = [r.source for r in relationships]
        targets = [r.target for r in relationships]
        assert "main.chained" in sources
        assert "main.middle" in targets
        assert "main.inner" in targets


# ------------------------------------------------------------------
# Recursive calls
# ------------------------------------------------------------------


class TestRecursiveCalls:
    """Tests for recursive call extraction."""

    def test_simple_recursion(
        self,
        extractor: CallExtractor,
    ) -> None:
        """A function calling itself should be detected."""
        symbols = [
            _make_symbol("factorial", "main.factorial", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        assert len(relationships) == 1
        assert relationships[0].source == "main.factorial"
        assert relationships[0].target == "main.factorial"

    def test_mutual_recursion(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Mutual recursion should be detected."""
        symbols = [
            _make_symbol("is_even", "main.is_even", SymbolType.FUNCTION, "main.py"),
            _make_symbol("is_odd", "main.is_odd", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def is_even(n: int) -> bool:
    if n == 0:
        return True
    return is_odd(n - 1)

def is_odd(n: int) -> bool:
    if n == 0:
        return False
    return is_even(n - 1)
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # is_even calls is_odd, is_odd calls is_even
        assert len(relationships) == 2
        sources = [(r.source, r.target) for r in relationships]
        assert ("main.is_even", "main.is_odd") in sources
        assert ("main.is_odd", "main.is_even") in sources

    def test_nested_recursion(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Nested recursive function should be detected."""
        symbols = [
            _make_symbol(
                "nested_recursive",
                "main.nested_recursive",
                SymbolType.FUNCTION,
                "main.py",
            ),
            _make_symbol(
                "inner_recursive",
                "main.nested_recursive.inner_recursive",
                SymbolType.FUNCTION,
                "main.py",
            ),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def nested_recursive() -> None:
    def inner_recursive(n: int) -> int:
        if n <= 0:
            return 0
        return n + inner_recursive(n - 1)
    result = inner_recursive(5)
    print(result)
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # inner_recursive calls itself (recursive), and nested_recursive calls
        # inner_recursive (from result = inner_recursive(5)).
        assert len(relationships) == 2
        # Find the self-recursive relationship
        self_rel = [r for r in relationships if r.source == r.target]
        assert len(self_rel) == 1
        assert self_rel[0].source == "main.nested_recursive.inner_recursive"


# ------------------------------------------------------------------
# Cross-module calls
# ------------------------------------------------------------------


class TestCrossModuleCalls:
    """Tests for cross-module call extraction."""

    def test_cross_module_function_call(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Calls between different modules should be detected."""
        symbols = [
            _make_symbol(
                "module_a_function",
                "module_a.module_a_function",
                SymbolType.FUNCTION,
                "module_a.py",
            ),
            _make_symbol(
                "module_a_calls_b",
                "module_a.module_a_calls_b",
                SymbolType.FUNCTION,
                "module_a.py",
            ),
            _make_symbol(
                "module_b_function",
                "module_b.module_b_function",
                SymbolType.FUNCTION,
                "module_b.py",
            ),
            _make_symbol(
                "module_b_calls_a",
                "module_b.module_b_calls_a",
                SymbolType.FUNCTION,
                "module_b.py",
            ),
        ]
        modules = {
            "module_a.py": Module(
                path="module_a.py",
                symbols=[s for s in symbols if s.module == "module_a.py"],
                source="""
def module_a_function() -> str:
    return "A"

def module_a_calls_b() -> str:
    return module_b_function()
""",
            ),
            "module_b.py": Module(
                path="module_b.py",
                symbols=[s for s in symbols if s.module == "module_b.py"],
                source="""
def module_b_function() -> str:
    return "B"

def module_b_calls_a() -> str:
    return module_a_function()
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # module_a_calls_b calls module_b_function (cross-module)
        # module_b_calls_a calls module_a_function (cross-module)
        assert len(relationships) == 2
        sources = [(r.source, r.target) for r in relationships]
        assert ("module_a.module_a_calls_b", "module_b.module_b_function") in sources
        assert ("module_b.module_b_calls_a", "module_a.module_a_function") in sources


# ------------------------------------------------------------------
# Unknown symbols
# ------------------------------------------------------------------


class TestUnknownSymbols:
    """Tests for handling of unknown symbols."""

    def test_unknown_call_ignored(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Calls to unknown symbols should be ignored."""
        symbols = [
            _make_symbol("known", "main.known", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def known() -> str:
    return "known"

def uses_unknown() -> str:
    result = some_unknown_function()
    return result
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # uses_unknown is not a known symbol, so no relationship should be created
        assert len(relationships) == 0

    def test_partial_unknown(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Only calls to known symbols should be created."""
        symbols = [
            _make_symbol("known", "main.known", SymbolType.FUNCTION, "main.py"),
            _make_symbol("uses_mixed", "main.uses_mixed", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def known() -> str:
    return "known"

def uses_mixed() -> str:
    a = known()
    b = unknown_call()
    return a + b
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # Only known() call should be created
        assert len(relationships) == 1
        assert relationships[0].source == "main.uses_mixed"
        assert relationships[0].target == "main.known"


# ------------------------------------------------------------------
# Duplicate calls
# ------------------------------------------------------------------


class TestDuplicateCalls:
    """Tests for duplicate call handling."""

    def test_no_duplicate_edges(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Duplicate calls should produce only one edge."""
        symbols = [
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
            _make_symbol("process", "main.process", SymbolType.FUNCTION, "main.py"),
            _make_symbol("main", "main.main", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def helper() -> str:
    return "helper"

def process() -> None:
    a = helper()
    b = helper()
    c = helper()
    print(a, b, c)

def main() -> None:
    process()
    process()
    process()
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # Should have exactly 2 unique edges: main->process, process->helper
        assert len(relationships) == 2
        sources = [(r.source, r.target) for r in relationships]
        assert ("main.main", "main.process") in sources
        assert ("main.process", "main.helper") in sources


# ------------------------------------------------------------------
# Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic output ordering."""

    def test_sorted_by_source_target(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Relationships should be sorted by (source, target)."""
        symbols = [
            _make_symbol("z_func", "main.z_func", SymbolType.FUNCTION, "main.py"),
            _make_symbol("a_func", "main.a_func", SymbolType.FUNCTION, "main.py"),
            _make_symbol("m_func", "main.m_func", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def z_func() -> str:
    return "z"

def a_func() -> str:
    return "a"

def m_func() -> str:
    return "m"

def main() -> None:
    z_func()
    a_func()
    m_func()
""",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)

        # Should be sorted by source, then target
        sources = [r.source for r in relationships]
        targets = [r.target for r in relationships]
        assert sources == sorted(sources)
        # All from main.main, so targets should be sorted
        assert targets == sorted(targets)

    def test_repeated_execution_identical(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Repeated extraction should produce identical results."""
        symbols = [
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
            _make_symbol("process", "main.process", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="""
def helper() -> str:
    return "helper"

def process() -> str:
    return helper()
""",
            ),
        }
        index = _make_index(symbols, modules=modules)

        result1 = extractor.extract(index)
        result2 = extractor.extract(index)
        result3 = extractor.extract(index)

        assert result1 == result2
        assert result2 == result3


# ------------------------------------------------------------------
# Empty / edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_index(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Empty index should produce no relationships."""
        index = _make_index([])
        relationships = extractor.extract(index)
        assert relationships == []

    def test_no_source_code(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Modules without source code should be skipped gracefully."""
        symbols = [
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="",  # Empty source
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)
        assert relationships == []

    def test_syntax_error_in_source(
        self,
        extractor: CallExtractor,
    ) -> None:
        """Modules with syntax errors should be skipped gracefully."""
        symbols = [
            _make_symbol("broken", "main.broken", SymbolType.FUNCTION, "main.py"),
        ]
        modules = {
            "main.py": Module(
                path="main.py",
                symbols=symbols,
                source="def broken() -> None:\n    this is not valid python!!!\n",
            ),
        }
        index = _make_index(symbols, modules=modules)
        relationships = extractor.extract(index)
        assert relationships == []


# ------------------------------------------------------------------
# Integration test — full build pipeline
# ------------------------------------------------------------------


class TestIntegration:
    """Integration tests for the full build pipeline."""

    def test_full_build_with_calls(
        self,
    ) -> None:
        """Full build should include CALLS relationships."""
        fixture_dir = Path(__file__).resolve().parent / "fixtures"
        index = RepositoryIndexBuilder().build(fixture_dir / "simple_calls.py")

        # Verify CALLS relationships exist
        relationships = index.relationships()
        call_rels = [r for r in relationships if r.type == SymbolRelationshipType.CALLS]
        assert len(call_rels) > 0

        # Verify all CALLS relationships have known symbols
        all_symbols = {s.qualified_name for s in index.symbols()}
        for rel in call_rels:
            assert rel.source in all_symbols, f"Unknown caller: {rel.source}"
            assert rel.target in all_symbols, f"Unknown callee: {rel.target}"

    def test_full_build_deterministic(
        self,
    ) -> None:
        """Repeated builds should produce identical CALLS relationships."""
        fixture_dir = Path(__file__).resolve().parent / "fixtures"
        index1 = RepositoryIndexBuilder().build(fixture_dir / "simple_calls.py")
        index2 = RepositoryIndexBuilder().build(fixture_dir / "simple_calls.py")

        rels1 = index1.relationships()
        rels2 = index2.relationships()

        call_rels1 = [r for r in rels1 if r.type == SymbolRelationshipType.CALLS]
        call_rels2 = [r for r in rels2 if r.type == SymbolRelationshipType.CALLS]

        assert call_rels1 == call_rels2
