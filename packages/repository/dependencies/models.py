"""Data models for the Workspace Dependency Graph.

Defines immutable node and edge types that represent the canonical
dependency structure derived from a RepositoryIndex.

No source files are reparsed.  No filesystem access.  No AST inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from packages.repository.symbols.models import RelationshipType as SymbolRelationshipType
from packages.repository.symbols.models import SymbolType


class NodeType(str, Enum):
    """Category of a graph node.

    Maps directly from SymbolType — no new categories are invented.
    """

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class GraphEdgeType(str, Enum):
    """Type of edge in the dependency graph.

    Maps from RelationshipType semantics without duplication:

    - ``DEFINES`` → ``CONTAINS`` (parent → child containment)
    - ``IMPORTS`` → ``IMPORTS`` (module/symbol import reference)
    - ``INHERITS`` → ``INHERITS`` (class inheritance)
    - ``CALLS`` → ``CALLS`` (function/method call)
    """

    CONTAINS = "contains"
    IMPORTS = "imports"
    INHERITS = "inherits"
    CALLS = "calls"


# ---------------------------------------------------------------------------
# GraphNode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A single node in the dependency graph.

    Attributes:
        node_type: The category of the node (MODULE, CLASS, FUNCTION, METHOD).
        qualified_name: Fully qualified identifier — unique within the graph.
        symbol_type: The original SymbolType, if this node represents a symbol.
    """

    node_type: NodeType
    qualified_name: str
    symbol_type: SymbolType | None = None

    def __lt__(self, other: GraphNode) -> bool:
        """Support deterministic ordering by (node_type, qualified_name).

        Args:
            other: Another GraphNode to compare against.

        Returns:
            True if this node should precede other.
        """
        if self.node_type == other.node_type:
            return self.qualified_name < other.qualified_name
        return self.node_type.value < other.node_type.value


# ---------------------------------------------------------------------------
# GraphEdge
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A directed edge between two graph nodes.

    Attributes:
        source: The qualified_name of the source node.
        target: The qualified_name of the target node.
        edge_type: The kind of relationship.
    """

    source: str
    target: str
    edge_type: GraphEdgeType

    def __lt__(self, other: GraphEdge) -> bool:
        """Support deterministic ordering."""
        if self.source != other.source:
            return self.source < other.source
        if self.target != other.target:
            return self.target < other.target
        return self.edge_type.value < other.edge_type.value


# ---------------------------------------------------------------------------
# Relationship type mapping
# ---------------------------------------------------------------------------

_RELATIONSHIP_TYPE_MAP: dict[SymbolRelationshipType, GraphEdgeType] = {
    SymbolRelationshipType.DEFINES: GraphEdgeType.CONTAINS,
    SymbolRelationshipType.IMPORTS: GraphEdgeType.IMPORTS,
    SymbolRelationshipType.INHERITS: GraphEdgeType.INHERITS,
    SymbolRelationshipType.CALLS: GraphEdgeType.CALLS,
}


def map_relationship_type(
    rel_type: SymbolRelationshipType,
) -> GraphEdgeType:
    """Map a SymbolRelationshipType to a GraphEdgeType.

    Args:
        rel_type: The source relationship type.

    Returns:
        The corresponding graph edge type.

    Raises:
        ValueError: If the relationship type is not mappable.
    """
    mapped = _RELATIONSHIP_TYPE_MAP.get(rel_type)
    if mapped is None:
        raise ValueError(
            f"Cannot map RelationshipType.{rel_type.value} to GraphEdgeType"
        )
    return mapped
