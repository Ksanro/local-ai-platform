"""Workflow Graph - DAG validation and traversal.

Deterministic workflow DAG validation, cycle detection, and topological
sorting.  This module owns **all** DAG operations so the WorkflowEngine
can stay purely orchestration-focused.

Architecture
------------

WorkflowEngine
      │
      ▼
WorkflowGraph  ←  DAG validation + topological sort
      │
      ▼
ordered WorkflowNodes

Constraints
-----------

- Purely structural (no repository intelligence).
- Deterministic ordering (stable sort).
- No side effects.

Public API
----------

.. code-block:: python

    from packages.workflows.graph import WorkflowGraph

    graph = WorkflowGraph(nodes=(node_a, node_b, node_c))
    graph.validate()
    ordered = graph.topological_sort()
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.workflows.models import WorkflowNode  # noqa: F401


class WorkflowGraph:
    """Validates and traverses workflow DAGs.

    Responsibilities:
        - Validate node IDs (no duplicates)
        - Validate dependencies (all referenced nodes exist)
        - Detect cycles (no directed cycles allowed)
        - Detect unreachable nodes (all nodes must be reachable from roots)
        - Deterministic topological sort (stable, alphabetical tie-break)

    The graph is immutable after construction.
    """

    def __init__(self, nodes: tuple[WorkflowNode, ...]) -> None:
        """Initialize the workflow graph.

        Args:
            nodes: Tuple of WorkflowNode instances forming the DAG.
        """
        self._nodes = nodes
        self._node_map: dict[str, WorkflowNode] = {node.node_id: node for node in nodes}
        self._adjacency: dict[str, set[str]] = {}
        self._reverse_adjacency: dict[str, set[str]] = {}

        # Build adjacency lists.
        for node in nodes:
            self._adjacency[node.node_id] = set(node.depends_on)
            for dep in node.depends_on:
                self._reverse_adjacency.setdefault(dep, set()).add(node.node_id)

    @property
    def nodes(self) -> tuple[WorkflowNode, ...]:
        """All nodes in the graph."""
        return self._nodes

    @property
    def node_ids(self) -> tuple[str, ...]:
        """All node IDs in deterministic order."""
        return tuple(sorted(self._node_map.keys()))

    def get_node(self, node_id: str) -> WorkflowNode | None:
        """Lookup a node by ID.

        Args:
            node_id: The node identifier.

        Returns:
            The WorkflowNode, or None if not found.
        """
        return self._node_map.get(node_id)

    def get_dependencies(self, node_id: str) -> tuple[str, ...]:
        """Return direct dependencies for a node.

        Args:
            node_id: The node identifier.

        Returns:
            Tuple of dependency node IDs.
        """
        return tuple(sorted(self._adjacency.get(node_id, set())))

    def get_transitive_dependencies(self, node_id: str) -> tuple[str, ...]:
        """Return all transitive dependencies for a node.

        Args:
            node_id: The node identifier.

        Returns:
            Sorted tuple of all transitive dependency node IDs.
        """
        visited: set[str] = set()
        queue: deque[str] = deque(self._adjacency.get(node_id, set()))

        while queue:
            current = queue.popleft()
            if current not in visited:
                visited.add(current)
                for dep in self._adjacency.get(current, set()):
                    if dep not in visited:
                        queue.append(dep)

        return tuple(sorted(visited))

    def validate(self) -> None:
        """Validate the workflow DAG.

        Raises:
            ValueError: If any validation check fails.

        Checks:
            1. Duplicate node IDs
            2. Unknown dependencies
            3. Circular dependencies
            4. Unreachable nodes
        """
        self._check_duplicate_ids()
        self._check_unknown_dependencies()
        self._check_cycles()
        self._check_unreachable_nodes()

    def _check_duplicate_ids(self) -> None:
        """Check for duplicate node IDs."""
        seen: set[str] = set()
        for node in self._nodes:
            if node.node_id in seen:
                raise ValueError(
                    f"Duplicate workflow node ID: '{node.node_id}'. "
                    f"Each node must have a unique ID."
                )
            seen.add(node.node_id)

    def _check_unknown_dependencies(self) -> None:
        """Check that all dependencies reference existing nodes."""
        for node in self._nodes:
            for dep in node.depends_on:
                if dep not in self._node_map:
                    raise ValueError(
                        f"Node '{node.node_id}' depends on unknown node '{dep}'. "
                        f"Available nodes: {self.node_ids}"
                    )

    def _check_cycles(self) -> None:
        """Check for circular dependencies using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {nid: WHITE for nid in self._node_map}

        def visit(node_id: str) -> bool:
            """Returns True if a cycle is detected."""
            color[node_id] = GRAY
            for dep in self._adjacency.get(node_id, set()):
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and visit(dep):
                    return True
            color[node_id] = BLACK
            return False

        for node_id in self.node_ids:
            if color[node_id] == WHITE:
                if visit(node_id):
                    raise ValueError(
                        "Circular dependency detected in workflow. "
                        "Please check the dependency graph for cycles."
                    )

    def _check_unreachable_nodes(self) -> None:
        """Check that all nodes are reachable from root nodes."""
        # Find root nodes (nodes with no dependencies).
        roots: list[str] = []
        has_dependents: set[str] = set()

        for node in self._nodes:
            if not node.depends_on:
                roots.append(node.node_id)
            for dep in node.depends_on:
                has_dependents.add(dep)

        # Nodes that are not depended upon by anyone are "leaf" nodes.
        # All nodes should be reachable from at least one root.
        # We do a BFS from all roots and check coverage.
        visited: set[str] = set()
        queue: deque[str] = deque(roots)

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            # Visit all nodes that depend on current.
            for dependent in self._reverse_adjacency.get(current, set()):
                if dependent not in visited:
                    queue.append(dependent)

        unreachable = set(self._node_map.keys()) - visited
        if unreachable:
            raise ValueError(
                f"Unreachable nodes detected: {sorted(unreachable)}. "
                f"All nodes must be reachable from root nodes."
            )

    def topological_sort(self) -> tuple[WorkflowNode, ...]:
        """Return nodes in deterministic topological order.

        Uses Kahn's algorithm with alphabetical tie-breaking for
        deterministic ordering.

        Returns:
            Tuple of WorkflowNodes in execution order.

        Raises:
            ValueError: If the graph is invalid (calls validate first).
        """
        self.validate()

        # Compute in-degrees.
        in_degree: dict[str, int] = {}
        for node_id in self._node_map:
            in_degree[node_id] = len(self._adjacency.get(node_id, set()))

        # Start with nodes that have no dependencies (in-degree 0).
        # Use sorted() for deterministic ordering.
        queue: list[str] = sorted(
            nid for nid, deg in in_degree.items() if deg == 0
        )

        result: list[str] = []

        while queue:
            # Process the first (alphabetically smallest) node.
            current = queue.pop(0)
            result.append(current)

            # Find all nodes that depend on current.
            dependents = sorted(
                self._reverse_adjacency.get(current, set())
            )

            for dependent in dependents:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # Insert in sorted position.
                    self._insert_sorted(queue, dependent)

        return tuple(self._node_map[nid] for nid in result)

    def _insert_sorted(self, lst: list[str], item: str) -> None:
        """Insert an item into a sorted list maintaining order."""
        lo, hi = 0, len(lst)
        while lo < hi:
            mid = (lo + hi) // 2
            if lst[mid] < item:
                lo = mid + 1
            else:
                hi = mid
        lst.insert(lo, item)

    def get_execution_layers(self) -> tuple[tuple[str, ...], ...]:
        """Return nodes grouped by execution layer.

        Nodes in the same layer have no dependencies on each other
        and can theoretically run in parallel.

        Returns:
            Tuple of layers, each layer is a tuple of node IDs.
        """
        self.validate()

        in_degree: dict[str, int] = {}
        for node_id in self._node_map:
            in_degree[node_id] = len(self._adjacency.get(node_id, set()))

        # Start with root nodes.
        current_layer: list[str] = sorted(
            nid for nid, deg in in_degree.items() if deg == 0
        )

        layers: list[tuple[str, ...]] = []

        while current_layer:
            layers.append(tuple(current_layer))
            next_layer: list[str] = []

            for current in current_layer:
                for dependent in self._reverse_adjacency.get(current, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_layer.append(dependent)

            current_layer = sorted(next_layer)

        return tuple(layers)
