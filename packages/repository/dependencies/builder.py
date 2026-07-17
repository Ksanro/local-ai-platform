"""DependencyGraphBuilder — constructs a WorkspaceDependencyGraph from RepositoryIndex.

The builder constructs the graph exclusively from RepositoryIndex data
(symbols and relationships).  No source files are reparsed, no filesystem
access, no AST inspection.

Construction is O(V + E) — single pass over symbols to build nodes,
single pass over relationships to build edges.
"""

from __future__ import annotations

from packages.repository.dependencies.graph import WorkspaceDependencyGraph
from packages.repository.dependencies.models import (
    GraphEdge,
    GraphNode,
    NodeType,
    map_relationship_type,
)
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import SymbolType


class DependencyGraphBuilder:
    """Builds a :class:`WorkspaceDependencyGraph` from a :class:`RepositoryIndex`.

    The builder is stateless between calls — repeated builds of the same
    ``RepositoryIndex`` produce identical ``WorkspaceDependencyGraph``
    instances (deterministic).

    Attributes:
        _node_type_map: Maps SymbolType to NodeType.
    """

    def __init__(self) -> None:
        """Initialise the builder."""
        self._node_type_map: dict[SymbolType, NodeType] = {
            SymbolType.MODULE: NodeType.MODULE,
            SymbolType.CLASS: NodeType.CLASS,
            SymbolType.FUNCTION: NodeType.FUNCTION,
            SymbolType.METHOD: NodeType.METHOD,
        }

    def build(self, repository_index: RepositoryIndex) -> WorkspaceDependencyGraph:
        """Build a :class:`WorkspaceDependencyGraph` from a repository index.

        Extracts nodes from all symbols and edges from all relationships in
        the index.  Nodes are deduplicated by ``qualified_name``.  Edges are
        deduplicated by ``(source, target, edge_type)``.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``WorkspaceDependencyGraph`` containing all nodes and edges.
        """
        # Extract nodes from symbols.
        nodes: dict[str, GraphNode] = {}
        for symbol in repository_index.symbols():
            node_type = self._node_type_map.get(symbol.symbol_type)
            if node_type is None:
                continue
            nodes[symbol.qualified_name] = GraphNode(
                node_type=node_type,
                qualified_name=symbol.qualified_name,
                symbol_type=symbol.symbol_type,
            )

        # Extract edges from relationships.
        edges: set[GraphEdge] = set()
        for rel in repository_index.relationships():
            try:
                edge_type = map_relationship_type(rel.type)
            except ValueError:
                continue

            # Only include edges where both source and target exist as nodes.
            if rel.source not in nodes or rel.target not in nodes:
                continue

            edges.add(GraphEdge(
                source=rel.source,
                target=rel.target,
                edge_type=edge_type,
            ))

        # Build adjacency lists.
        outgoing: dict[str, list[GraphNode]] = {}
        incoming: dict[str, list[GraphNode]] = {}

        for edge in edges:
            # Outgoing (dependencies).
            if edge.source not in outgoing:
                outgoing[edge.source] = []
            target_node = nodes[edge.target]
            if target_node not in outgoing[edge.source]:
                outgoing[edge.source].append(target_node)

            # Incoming (dependents).
            if edge.target not in incoming:
                incoming[edge.target] = []
            source_node = nodes[edge.source]
            if source_node not in incoming[edge.target]:
                incoming[edge.target].append(source_node)

        # Sort adjacency lists for determinism.
        for key in outgoing:
            outgoing[key] = sorted(outgoing[key])
        for key in incoming:
            incoming[key] = sorted(incoming[key])

        return WorkspaceDependencyGraph(
            nodes=frozenset(nodes.values()),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )
