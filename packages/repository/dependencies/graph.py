"""WorkspaceDependencyGraph — immutable dependency graph with traversal APIs.

Provides read-only access to the dependency graph derived from a
RepositoryIndex.  All traversal is deterministic — results are sorted
by ``(node_type, qualified_name)`` and deduplicated.

No public method mutates the graph.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from packages.repository.dependencies.models import GraphEdge, GraphEdgeType, GraphNode

if TYPE_CHECKING:
    from collections.abc import Sequence


class WorkspaceDependencyGraph:
    """Immutable dependency graph with deterministic traversal APIs.

    The graph is built exclusively from RepositoryIndex data (symbols and
    relationships).  No source files are reparsed, no filesystem access,
    no AST inspection.

    All public collections are sorted deterministically — by ``(node_type,
    qualified_name)`` first — so consumers never depend on internal
    ordering.

    Attributes:
        _nodes: All graph nodes as a frozenset.
        _edges: All graph edges as a frozenset.
        _outgoing: Adjacency list for outgoing edges (dependencies).
        _incoming: Adjacency list for incoming edges (dependents).
    """

    __slots__ = ("_nodes", "_edges", "_outgoing", "_incoming")

    def __init__(
        self,
        nodes: frozenset[GraphNode],
        edges: frozenset[GraphEdge],
        outgoing: dict[str, list[GraphNode]],
        incoming: dict[str, list[GraphNode]],
    ) -> None:
        """Initialise the graph.

        Args:
            nodes: All graph nodes.
            edges: All graph edges.
            outgoing: Adjacency list mapping qualified_name → sorted direct dependencies.
            incoming: Adjacency list mapping qualified_name → sorted direct dependents.
        """
        self._nodes = nodes
        self._edges = edges
        self._outgoing = outgoing
        self._incoming = incoming

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def nodes(self) -> Sequence[GraphNode]:
        """Return all graph nodes sorted by (node_type, qualified_name).

        Returns:
            Sorted list of ``GraphNode`` instances.
        """
        return sorted(self._nodes)

    def edges(self) -> Sequence[GraphEdge]:
        """Return all graph edges sorted deterministically.

        Returns:
            Sorted list of ``GraphEdge`` instances.
        """
        return sorted(self._edges)

    def node_count(self) -> int:
        """Return the number of nodes in the graph.

        Returns:
            The node count.
        """
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return the number of edges in the graph.

        Returns:
            The edge count.
        """
        return len(self._edges)

    # ------------------------------------------------------------------
    # Direct queries
    # ------------------------------------------------------------------

    def dependencies(self, node: GraphNode) -> Sequence[GraphNode]:
        """Return direct dependencies of a node (outgoing edges).

        Dependencies are nodes that this node points to.

        Args:
            node: The node to query.

        Returns:
            Sorted list of direct dependency ``GraphNode`` instances.
        """
        return self._outgoing.get(node.qualified_name, [])

    def dependents(self, node: GraphNode) -> Sequence[GraphNode]:
        """Return direct dependents of a node (incoming edges).

        Dependents are nodes that point to this node.

        Args:
            node: The node to query.

        Returns:
            Sorted list of direct dependent ``GraphNode`` instances.
        """
        return self._incoming.get(node.qualified_name, [])

    # ------------------------------------------------------------------
    # Transitive queries
    # ------------------------------------------------------------------

    def transitive_dependencies(
        self,
        node: GraphNode,
        depth: int = 1,
    ) -> Sequence[GraphNode]:
        """Return all transitive dependencies of a node.

        Uses BFS traversal with cycle prevention and depth limiting.
        Results are deduplicated and sorted.

        Args:
            node: The node to query.
            depth: Maximum traversal depth.  Defaults to 1 (direct deps only).
                Use ``depth=-1`` for unlimited depth.

        Returns:
            Sorted list of all transitive dependency ``GraphNode`` instances
            (excluding the node itself).
        """
        return self._bfs_traversal(
            start=node,
            adjacency=self._outgoing,
            depth=depth,
            exclude=node.qualified_name,
        )

    def transitive_dependents(
        self,
        node: GraphNode,
        depth: int = 1,
    ) -> Sequence[GraphNode]:
        """Return all transitive dependents of a node.

        Uses BFS traversal on incoming edges with cycle prevention and
        depth limiting.  Results are deduplicated and sorted.

        Args:
            node: The node to query.
            depth: Maximum traversal depth.  Defaults to 1 (direct dependents only).
                Use ``depth=-1`` for unlimited depth.

        Returns:
            Sorted list of all transitive dependent ``GraphNode`` instances
            (excluding the node itself).
        """
        return self._bfs_traversal(
            start=node,
            adjacency=self._incoming,
            depth=depth,
            exclude=node.qualified_name,
        )

    # ------------------------------------------------------------------
    # Containment queries (DEFINES → CONTAINS only)
    # ------------------------------------------------------------------

    def contains(self, node: GraphNode) -> Sequence[GraphNode]:
        """Return direct children of a node via CONTAINS edges.

        Only ``CONTAINS`` edges are traversed — these represent parent →
        child containment (derived from ``DEFINES`` relationships).

        Args:
            node: The parent node.

        Returns:
            Sorted list of child ``GraphNode`` instances.
        """
        return self._filtered_edges(node, GraphEdgeType.CONTAINS, direction="out")

    def contained_by(self, node: GraphNode) -> Sequence[GraphNode]:
        """Return direct parents of a node via CONTAINS edges.

        Only ``CONTAINS`` edges are traversed in reverse — these represent
        parent → child containment (derived from ``DEFINES`` relationships).

        Args:
            node: The child node.

        Returns:
            Sorted list of parent ``GraphNode`` instances.
        """
        return self._filtered_edges(node, GraphEdgeType.CONTAINS, direction="in")

    # ------------------------------------------------------------------
    # Internal traversal
    # ------------------------------------------------------------------

    def _bfs_traversal(
        self,
        start: GraphNode,
        adjacency: dict[str, list[GraphNode]],
        depth: int,
        exclude: str,
    ) -> list[GraphNode]:
        """Perform BFS traversal from a starting node.

        Args:
            start: The starting node.
            adjacency: Adjacency list (outgoing or incoming).
            depth: Maximum depth. -1 for unlimited.
            exclude: Qualified name to exclude from results.

        Returns:
            Sorted, deduplicated list of visited nodes (excluding start).
        """
        visited: set[str] = set()
        queue: deque[tuple[GraphNode, int]] = deque()
        queue.append((start, 0))
        visited.add(start.qualified_name)

        while queue:
            current, current_depth = queue.popleft()

            neighbors = adjacency.get(current.qualified_name, [])
            for neighbor in neighbors:
                if neighbor.qualified_name == exclude:
                    continue
                if neighbor.qualified_name in visited:
                    continue

                new_depth = current_depth + 1

                # Only add to visited and queue if within depth limit.
                if depth == -1 or new_depth <= depth:
                    visited.add(neighbor.qualified_name)
                    queue.append((neighbor, new_depth))

        # Build result from visited set, excluding the start node.
        result: list[GraphNode] = []
        for node_name in visited:
            if node_name != exclude:
                node = self._find_node_by_name(self._nodes, node_name)
                if node is not None:
                    result.append(node)

        return sorted(result)

    @staticmethod
    def _find_node_by_name(
        nodes: frozenset[GraphNode], qualified_name: str
    ) -> GraphNode | None:
        """Find a node by qualified_name in a frozenset.

        Args:
            nodes: The frozenset of nodes.
            qualified_name: The qualified name to find.

        Returns:
            The matching GraphNode, or None.
        """
        for node in nodes:
            if node.qualified_name == qualified_name:
                return node
        return None

    def _filtered_edges(
        self,
        node: GraphNode,
        edge_type: GraphEdgeType,
        direction: str,
    ) -> list[GraphNode]:
        """Filter edges by type and direction.

        Args:
            node: The node to query.
            edge_type: The edge type to filter by.
            direction: ``"out"`` for outgoing, ``"in"`` for incoming.

        Returns:
            Sorted list of connected ``GraphNode`` instances.
        """
        result: set[GraphNode] = set()

        if direction == "out":
            for edge in self._edges:
                if edge.source == node.qualified_name and edge.edge_type == edge_type:
                    node_obj = self._find_node_by_name(self._nodes, edge.target)
                    if node_obj is not None:
                        result.add(node_obj)
        else:
            for edge in self._edges:
                if edge.target == node.qualified_name and edge.edge_type == edge_type:
                    node_obj = self._find_node_by_name(self._nodes, edge.source)
                    if node_obj is not None:
                        result.add(node_obj)

        return sorted(result)

    # ------------------------------------------------------------------
    # Convenience: node lookup
    # ------------------------------------------------------------------

    def find_node(self, qualified_name: str) -> GraphNode | None:
        """Return the node with the given qualified_name, or ``None``.

        Args:
            qualified_name: The fully qualified name to look up.

        Returns:
            The ``GraphNode`` if found, otherwise ``None``.
        """
        return self._find_node_by_name(self._nodes, qualified_name)

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a string representation of the graph."""
        return (
            f"WorkspaceDependencyGraph(nodes={self.node_count()}, "
            f"edges={self.edge_count()})"
        )

    def __eq__(self, other: object) -> bool:
        """Check equality by nodes and edges."""
        if not isinstance(other, WorkspaceDependencyGraph):
            return NotImplemented
        return (
            self._nodes == other._nodes
            and self._edges == other._edges
            and self._outgoing == other._outgoing
            and self._incoming == other._incoming
        )

    def __hash__(self) -> int:
        """Hash by nodes and edges."""
        return hash((self._nodes, self._edges))
