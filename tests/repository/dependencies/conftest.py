"""Shared test fixtures for the dependency graph tests.

Provides helper functions to create GraphNode, GraphEdge, and
RepositoryIndex instances for testing.
"""

from __future__ import annotations

from packages.repository.dependencies.models import GraphEdge, GraphEdgeType, GraphNode, NodeType
from packages.repository.index.models import (
    Module,
    Relationship,
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.repository.symbols.models import Symbol, SymbolType


def _make_symbol(
    name: str,
    qualified_name: str,
    symbol_type: SymbolType,
    module: str = "main.py",
    lineno: int = 1,
    decorators: list[str] | None = None,
) -> Symbol:
    """Helper to create a Symbol for testing.

    Args:
        name: Short name.
        qualified_name: Fully qualified name.
        symbol_type: The symbol type.
        module: Source module path.
        lineno: 1-based line number.
        decorators: List of decorator names.

    Returns:
        A Symbol instance.
    """
    return Symbol(
        id=qualified_name,
        name=name,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
        module=module,
        lineno=lineno,
        decorators=decorators or [],
    )


def _make_node(
    node_type: NodeType,
    qualified_name: str,
    symbol_type: SymbolType | None = None,
) -> GraphNode:
    """Helper to create a GraphNode for testing.

    Args:
        node_type: The node category.
        qualified_name: Fully qualified identifier.
        symbol_type: The original SymbolType, if applicable.

    Returns:
        A GraphNode instance.
    """
    return GraphNode(
        node_type=node_type,
        qualified_name=qualified_name,
        symbol_type=symbol_type,
    )


def _make_edge(
    source: str,
    target: str,
    edge_type: GraphEdgeType,
) -> GraphEdge:
    """Helper to create a GraphEdge for testing.

    Args:
        source: Source qualified name.
        target: Target qualified name.
        edge_type: The edge type.

    Returns:
        A GraphEdge instance.
    """
    return GraphEdge(
        source=source,
        target=target,
        edge_type=edge_type,
    )


def _make_index_for_graph(
    symbols: list[Symbol],
    relationships: list[Relationship] | None = None,
) -> RepositoryIndex:
    """Create a RepositoryIndex suitable for graph building.

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
