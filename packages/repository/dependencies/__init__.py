"""Workspace Dependency Graph package.

Provides immutable graph structures built exclusively from RepositoryIndex
data.  The public API is:

    graph = DependencyGraphBuilder().build(repository_index)

Returns a WorkspaceDependencyGraph with deterministic, sorted traversal
APIs for dependency/dependent analysis.
"""

from __future__ import annotations

from packages.repository.dependencies.builder import DependencyGraphBuilder
from packages.repository.dependencies.graph import WorkspaceDependencyGraph
from packages.repository.dependencies.models import GraphEdge, GraphNode, NodeType

__all__ = [
    "DependencyGraphBuilder",
    "GraphEdge",
    "GraphNode",
    "NodeType",
    "WorkspaceDependencyGraph",
]
