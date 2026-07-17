"""Graph statistics analyzer.

Computes graph-level aggregate statistics from the RepositoryIndex
— connected components, maximum call depth, average degrees.

No filesystem metadata, no AST parsing.

Algorithm:
- Connected components: O(V + E) using BFS on the CALLS graph.
- Maximum call depth: O(V + E) using DFS on the CALLS graph.
- Average degrees: O(E) single pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import (
    GraphStatistics,
    RepositoryDiagnostics,
)
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import RelationshipType, SymbolType

if TYPE_CHECKING:
    pass


class GraphStatisticsAnalyzer(DiagnosticsAnalyzer):
    """Computes graph-level aggregate statistics.

    Computes:
    - connected_components: Number of weakly connected components
      of the CALLS graph only.
    - maximum_call_depth: Maximum call chain depth via CALLS edges.
    - average_out_degree: Average outgoing edges per node.
    - average_in_degree: Average incoming edges per node.

    Complexity: O(V + E) for BFS/DFS traversals.
    """

    @property
    def name(self) -> str:
        """Analyzer name."""
        return "graph_statistics"

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run graph statistics analysis.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with graph statistics.
        """
        relationships = repository_index.relationships()

        # --- Connected components (CALLS graph only) ---
        # We measure behavioral connectivity, not packaging.
        # IMPORTS already has separate diagnostics.
        # INHERITS already has separate diagnostics.
        #
        # All FUNCTION/METHOD symbols are nodes in the CALLS graph.
        # Nodes with no CALLS edges are isolated components.
        calls_graph_undirected: dict[str, set[str]] = {}
        calls_nodes: set[str] = set()

        # Collect all FUNCTION and METHOD symbols as nodes.
        for mod in repository_index.modules_list():
            for sym in mod.symbols:
                if sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                    calls_nodes.add(sym.qualified_name)

        for rel in relationships:
            if rel.type == RelationshipType.CALLS:
                src = rel.source
                tgt = rel.target
                calls_nodes.add(src)
                calls_nodes.add(tgt)
                calls_graph_undirected.setdefault(src, set()).add(tgt)
                calls_graph_undirected.setdefault(tgt, set()).add(src)

        component_count = self._count_connected_components(
            calls_graph_undirected, calls_nodes
        )

        # --- Maximum call depth (DFS on CALLS relationships) ---
        calls_graph_directed: dict[str, set[str]] = {}
        for rel in relationships:
            if rel.type == RelationshipType.CALLS:
                calls_graph_directed.setdefault(rel.source, set()).add(rel.target)

        max_depth = self._compute_max_depth(calls_graph_directed, calls_nodes)

        # --- Average degrees (all relationship types) ---
        all_nodes: set[str] = set()
        directed: dict[str, set[str]] = {}
        in_degree: dict[str, int] = {}

        for rel in relationships:
            src = rel.source
            tgt = rel.target
            all_nodes.add(src)
            all_nodes.add(tgt)

            directed.setdefault(src, set()).add(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1
            if src not in in_degree:
                in_degree[src] = 0

        # Include MODULE-type symbol qualified names as nodes — isolated
        # module symbols (e.g. package roots with no relationships) still
        # count as separate components.
        for mod in repository_index.modules_list():
            for sym in mod.symbols:
                if sym.symbol_type == SymbolType.MODULE:
                    all_nodes.add(sym.qualified_name)

        node_count = len(all_nodes) if len(all_nodes) > 0 else len(calls_nodes)
        if node_count == 0:
            node_count = len(calls_nodes)

        if node_count == 0:
            return RepositoryDiagnostics(
                graph_statistics=GraphStatistics(
                    connected_components=component_count,
                    maximum_call_depth=0,
                    average_out_degree=0.0,
                    average_in_degree=0.0,
                ),
            )

        # --- Average degrees ---
        total_out_degree = sum(len(targets) for targets in directed.values())
        total_in_degree = sum(in_degree.get(n, 0) for n in all_nodes)

        average_out_degree = total_out_degree / node_count if node_count > 0 else 0.0
        average_in_degree = total_in_degree / node_count if node_count > 0 else 0.0

        return RepositoryDiagnostics(
            graph_statistics=GraphStatistics(
                connected_components=component_count,
                maximum_call_depth=max_depth,
                average_out_degree=round(average_out_degree, 4),
                average_in_degree=round(average_in_degree, 4),
            ),
        )

    @staticmethod
    def _count_connected_components(
        adjacency: dict[str, set[str]],
        nodes: set[str],
    ) -> int:
        """Count weakly connected components in the CALLS graph.

        Uses BFS on the undirected CALLS graph.

        Complexity: O(V + E).
        """
        if not nodes:
            return 0

        visited: set[str] = set()
        component_count = 0

        for node in sorted(nodes):
            if node not in visited:
                component_count += 1
                # BFS
                queue: list[str] = [node]
                visited.add(node)
                idx = 0
                while idx < len(queue):
                    current = queue[idx]
                    idx += 1
                    for neighbor in sorted(adjacency.get(current, set())):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

        return component_count

    @staticmethod
    def _compute_max_depth(
        adjacency: dict[str, set[str]],
        nodes: set[str],
    ) -> int:
        """Compute the maximum call chain depth using DFS.

        Handles cycles by tracking the current recursion stack.
        Returns 0 if there are no CALLS edges.

        Complexity: O(V + E).
        """
        if not adjacency:
            return 0

        max_depth = 0
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in nodes}
        memo: dict[str, int] = {}

        def _dfs(node: str) -> int:
            """Return the longest path starting from ``node``."""
            color[node] = GRAY
            longest = 0

            for neighbor in sorted(adjacency.get(node, set())):
                if color.get(neighbor, WHITE) == GRAY:
                    # Cycle detected — skip to avoid infinite recursion.
                    continue
                if color.get(neighbor, WHITE) == WHITE:
                    d = _dfs(neighbor)
                    longest = max(longest, 1 + d)

            color[node] = BLACK
            memo[node] = longest
            return longest

        for node in sorted(nodes):
            if color.get(node, WHITE) == WHITE:
                _dfs(node)

        if memo:
            max_depth = max(memo.values())

        return max_depth
