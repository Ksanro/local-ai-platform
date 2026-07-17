"""Tests for the Workspace Dependency Graph.

Verifies graph construction, node uniqueness, edge uniqueness,
dependency traversal, dependent traversal, transitive traversal,
cycle handling, deterministic ordering, and repeated execution.
"""

from __future__ import annotations

from packages.repository.dependencies.builder import DependencyGraphBuilder
from packages.repository.dependencies.graph import WorkspaceDependencyGraph
from packages.repository.dependencies.models import (
    GraphEdgeType,
    NodeType,
    map_relationship_type,
)
from packages.repository.index.models import Relationship, RelationshipType
from packages.repository.symbols.models import SymbolType

from .conftest import _make_edge, _make_index_for_graph, _make_node, _make_symbol

# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


class TestGraphConstruction:
    """Tests for WorkspaceDependencyGraph construction."""

    def test_empty_graph(self) -> None:
        """Verify construction with no nodes or edges."""
        graph = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert graph.node_count() == 0
        assert graph.edge_count() == 0
        assert len(graph.nodes()) == 0
        assert len(graph.edges()) == 0

    def test_graph_with_nodes(self) -> None:
        """Verify construction with nodes."""
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert graph.node_count() == 2
        assert graph.edge_count() == 0

    def test_graph_with_edges(self) -> None:
        """Verify construction with edges."""
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        edge = _make_edge("main.App", "main.helper", GraphEdgeType.CALLS)
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b]),
            edges=frozenset([edge]),
            outgoing={"main.App": [node_b]},
            incoming={"main.helper": [node_a]},
        )
        assert graph.node_count() == 2
        assert graph.edge_count() == 1

    def test_graph_with_all_edge_types(self) -> None:
        """Verify construction with all edge types."""
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.CLASS, "main.Base")
        node_c = _make_node(NodeType.METHOD, "main.App.run")

        edges = [
            _make_edge("main.App", "main.Base", GraphEdgeType.INHERITS),
            _make_edge("main.App", "main.App.run", GraphEdgeType.CONTAINS),
        ]

        outgoing = {
            "main.App": [node_b, node_c],
            "main.Base": [],
            "main.App.run": [],
        }
        incoming = {
            "main.Base": [node_a],
            "main.App.run": [node_a],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )
        assert graph.edge_count() == 2


# ---------------------------------------------------------------------------
# Node uniqueness
# ---------------------------------------------------------------------------


class TestNodeUniqueness:
    """Tests for node uniqueness in the graph."""

    def test_duplicate_symbols_produce_single_node(self) -> None:
        """Duplicate symbols should produce a single node."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index_for_graph(symbols)
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 1

    def test_different_symbols_produce_different_nodes(self) -> None:
        """Different symbols should produce different nodes."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Helper", "main.Helper", SymbolType.FUNCTION, "main.py"),
        ]
        index = _make_index_for_graph(symbols)
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 2

    def test_no_duplicate_nodes_in_nodes_list(self) -> None:
        """nodes() should not contain duplicates."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        index = _make_index_for_graph(symbols)
        graph = DependencyGraphBuilder().build(index)
        names = [n.qualified_name for n in graph.nodes()]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Edge uniqueness
# ---------------------------------------------------------------------------


class TestEdgeUniqueness:
    """Tests for edge uniqueness in the graph."""

    def test_duplicate_relationships_produce_single_edge(self) -> None:
        """Duplicate relationships should produce a single edge."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)
        graph = DependencyGraphBuilder().build(index)
        assert graph.edge_count() == 1

    def test_no_duplicate_edges_in_edges_list(self) -> None:
        """edges() should not contain duplicates."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)
        graph = DependencyGraphBuilder().build(index)
        edge_keys = [(e.source, e.target, e.edge_type.value) for e in graph.edges()]
        assert len(edge_keys) == len(set(edge_keys))


# ---------------------------------------------------------------------------
# Dependency traversal
# ---------------------------------------------------------------------------


class TestDependencyTraversal:
    """Tests for dependency traversal."""

    def test_direct_dependencies(self) -> None:
        """dependencies() should return direct outgoing edges."""
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        node_c = _make_node(NodeType.FUNCTION, "main.other")

        edges = [
            _make_edge("main.App", "main.helper", GraphEdgeType.CALLS),
            _make_edge("main.App", "main.other", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.App": [node_b, node_c],
            "main.helper": [],
            "main.other": [],
        }
        incoming = {
            "main.helper": [node_a],
            "main.other": [node_a],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        deps = graph.dependencies(node_a)
        assert len(deps) == 2
        assert node_b in deps
        assert node_c in deps

    def test_no_dependencies(self) -> None:
        """dependencies() should return empty list for node with no deps."""
        node = _make_node(NodeType.FUNCTION, "main.helper")
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert len(graph.dependencies(node)) == 0

    def test_dependencies_sorted(self) -> None:
        """dependencies() should return sorted results."""
        node_z = _make_node(NodeType.FUNCTION, "main.z_func")
        node_a = _make_node(NodeType.FUNCTION, "main.a_func")
        node_m = _make_node(NodeType.FUNCTION, "main.m_func")

        edges = [
            _make_edge("main.App", "main.z_func", GraphEdgeType.CALLS),
            _make_edge("main.App", "main.a_func", GraphEdgeType.CALLS),
            _make_edge("main.App", "main.m_func", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.App": [node_a, node_m, node_z],
            "main.z_func": [],
            "main.a_func": [],
            "main.m_func": [],
        }
        incoming = {
            "main.z_func": [_make_node(NodeType.FUNCTION, "main.App")],
            "main.a_func": [_make_node(NodeType.FUNCTION, "main.App")],
            "main.m_func": [_make_node(NodeType.FUNCTION, "main.App")],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_z, node_a, node_m, _make_node(NodeType.FUNCTION, "main.App")]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        app_node = _make_node(NodeType.FUNCTION, "main.App")
        deps = graph.dependencies(app_node)
        qualified_names = [n.qualified_name for n in deps]
        assert qualified_names == sorted(qualified_names)


# ---------------------------------------------------------------------------
# Dependent traversal
# ---------------------------------------------------------------------------


class TestDependentTraversal:
    """Tests for dependent traversal."""

    def test_direct_dependents(self) -> None:
        """dependents() should return direct incoming edges."""
        node_a = _make_node(NodeType.FUNCTION, "main.caller")
        node_b = _make_node(NodeType.FUNCTION, "main.target")
        node_c = _make_node(NodeType.FUNCTION, "main.other_caller")

        edges = [
            _make_edge("main.caller", "main.target", GraphEdgeType.CALLS),
            _make_edge("main.other_caller", "main.target", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.caller": [node_b],
            "main.target": [],
            "main.other_caller": [node_b],
        }
        incoming = {
            "main.target": [node_a, node_c],
            "main.caller": [],
            "main.other_caller": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        dependents = graph.dependents(node_b)
        assert len(dependents) == 2
        assert node_a in dependents
        assert node_c in dependents

    def test_no_dependents(self) -> None:
        """dependents() should return empty list for node with no dependents."""
        node = _make_node(NodeType.FUNCTION, "main.leaf")
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert len(graph.dependents(node)) == 0


# ---------------------------------------------------------------------------
# Transitive traversal
# ---------------------------------------------------------------------------


class TestTransitiveTraversal:
    """Tests for transitive traversal."""

    def test_transitive_dependencies_depth_1(self) -> None:
        """transitive_dependencies with depth=1 should equal direct deps."""
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        node_c = _make_node(NodeType.FUNCTION, "main.other")

        edges = [
            _make_edge("main.App", "main.helper", GraphEdgeType.CALLS),
            _make_edge("main.App", "main.other", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.App": [node_b, node_c],
            "main.helper": [],
            "main.other": [],
        }
        incoming = {
            "main.helper": [node_a],
            "main.other": [node_a],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        deps = graph.transitive_dependencies(node_a, depth=1)
        assert len(deps) == 2

    def test_transitive_dependencies_depth_2(self) -> None:
        """transitive_dependencies with depth=2 should include multi-level deps."""
        # A -> B -> C
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        node_c = _make_node(NodeType.FUNCTION, "main.deep_func")

        edges = [
            _make_edge("main.App", "main.helper", GraphEdgeType.CALLS),
            _make_edge("main.helper", "main.deep_func", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.App": [node_b],
            "main.helper": [node_c],
            "main.deep_func": [],
        }
        incoming = {
            "main.helper": [node_a],
            "main.deep_func": [node_b],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        # Depth 1: only direct deps
        deps1 = graph.transitive_dependencies(node_a, depth=1)
        assert len(deps1) == 1
        assert node_b in deps1
        assert node_c not in deps1

        # Depth 2: includes transitive deps
        deps2 = graph.transitive_dependencies(node_a, depth=2)
        assert len(deps2) == 2
        assert node_b in deps2
        assert node_c in deps2

    def test_transitive_dependencies_unlimited_depth(self) -> None:
        """transitive_dependencies with depth=-1 should traverse all levels."""
        # A -> B -> C -> D
        node_a = _make_node(NodeType.CLASS, "main.App")
        node_b = _make_node(NodeType.FUNCTION, "main.helper")
        node_c = _make_node(NodeType.FUNCTION, "main.deep_func")
        node_d = _make_node(NodeType.FUNCTION, "main.deepest_func")

        edges = [
            _make_edge("main.App", "main.helper", GraphEdgeType.CALLS),
            _make_edge("main.helper", "main.deep_func", GraphEdgeType.CALLS),
            _make_edge("main.deep_func", "main.deepest_func", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.App": [node_b],
            "main.helper": [node_c],
            "main.deep_func": [node_d],
            "main.deepest_func": [],
        }
        incoming = {
            "main.helper": [node_a],
            "main.deep_func": [node_b],
            "main.deepest_func": [node_c],
            "main.App": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c, node_d]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        all_deps = graph.transitive_dependencies(node_a, depth=-1)
        assert len(all_deps) == 3
        assert node_b in all_deps
        assert node_c in all_deps
        assert node_d in all_deps

    def test_transitive_dependents(self) -> None:
        """transitive_dependents should traverse incoming edges."""
        # A -> B -> C (A calls B, B calls C)
        node_a = _make_node(NodeType.FUNCTION, "main.caller")
        node_b = _make_node(NodeType.FUNCTION, "main.intermediate")
        node_c = _make_node(NodeType.FUNCTION, "main.target")

        edges = [
            _make_edge("main.caller", "main.intermediate", GraphEdgeType.CALLS),
            _make_edge("main.intermediate", "main.target", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.caller": [node_b],
            "main.intermediate": [node_c],
            "main.target": [],
        }
        incoming = {
            "main.intermediate": [node_a],
            "main.target": [node_b],
            "main.caller": [],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        trans_deps = graph.transitive_dependents(node_c, depth=-1)
        assert len(trans_deps) == 2
        assert node_b in trans_deps
        assert node_a in trans_deps

    def test_transitive_excludes_start_node(self) -> None:
        """transitive_dependencies should exclude the start node."""
        # Self-referential: A -> A
        node_a = _make_node(NodeType.FUNCTION, "main.self_ref")

        edges = [
            _make_edge("main.self_ref", "main.self_ref", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.self_ref": [node_a],
        }
        incoming = {
            "main.self_ref": [node_a],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        deps = graph.transitive_dependencies(node_a, depth=-1)
        assert len(deps) == 0


# ---------------------------------------------------------------------------
# Cycle handling
# ---------------------------------------------------------------------------


class TestCycleHandling:
    """Tests for cycle handling in traversal."""

    def test_simple_cycle(self) -> None:
        """A -> B -> A should not cause infinite loop."""
        node_a = _make_node(NodeType.FUNCTION, "main.A")
        node_b = _make_node(NodeType.FUNCTION, "main.B")

        edges = [
            _make_edge("main.A", "main.B", GraphEdgeType.CALLS),
            _make_edge("main.B", "main.A", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.A": [node_b],
            "main.B": [node_a],
        }
        incoming = {
            "main.A": [node_b],
            "main.B": [node_a],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        # Should not hang and should return both nodes (but not duplicate)
        deps = graph.transitive_dependencies(node_a, depth=-1)
        assert len(deps) == 1
        assert node_b in deps

    def test_cycle_with_depth_limit(self) -> None:
        """Depth limit should prevent infinite traversal in cycles."""
        node_a = _make_node(NodeType.FUNCTION, "main.A")
        node_b = _make_node(NodeType.FUNCTION, "main.B")

        edges = [
            _make_edge("main.A", "main.B", GraphEdgeType.CALLS),
            _make_edge("main.B", "main.A", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.A": [node_b],
            "main.B": [node_a],
        }
        incoming = {
            "main.A": [node_b],
            "main.B": [node_a],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        # Depth 1: only direct deps
        deps1 = graph.transitive_dependencies(node_a, depth=1)
        assert len(deps1) == 1
        assert node_b in deps1

    def test_no_infinite_loop(self) -> None:
        """Traversal should complete even with complex cycles."""
        # A -> B -> C -> A (3-node cycle)
        node_a = _make_node(NodeType.FUNCTION, "main.A")
        node_b = _make_node(NodeType.FUNCTION, "main.B")
        node_c = _make_node(NodeType.FUNCTION, "main.C")

        edges = [
            _make_edge("main.A", "main.B", GraphEdgeType.CALLS),
            _make_edge("main.B", "main.C", GraphEdgeType.CALLS),
            _make_edge("main.C", "main.A", GraphEdgeType.CALLS),
        ]

        outgoing = {
            "main.A": [node_b],
            "main.B": [node_c],
            "main.C": [node_a],
        }
        incoming = {
            "main.A": [node_c],
            "main.B": [node_a],
            "main.C": [node_b],
        }

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_a, node_b, node_c]),
            edges=frozenset(edges),
            outgoing=outgoing,
            incoming=incoming,
        )

        # Should complete without hanging
        deps = graph.transitive_dependencies(node_a, depth=-1)
        assert len(deps) == 2
        assert node_b in deps
        assert node_c in deps


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ordering."""

    def test_nodes_sorted(self) -> None:
        """nodes() should be sorted by (node_type, qualified_name)."""
        node_func = _make_node(NodeType.FUNCTION, "main.helper")
        node_class = _make_node(NodeType.CLASS, "main.App")

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_func, node_class]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )

        nodes = graph.nodes()
        assert nodes[0] == node_class  # CLASS < FUNCTION alphabetically
        assert nodes[1] == node_func

    def test_edges_sorted(self) -> None:
        """edges() should be sorted by (source, target, edge_type)."""
        edge_b = _make_edge("main.B", "main.C", GraphEdgeType.CALLS)
        edge_a = _make_edge("main.A", "main.B", GraphEdgeType.CALLS)

        graph = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset([edge_b, edge_a]),
            outgoing={},
            incoming={},
        )

        edges = graph.edges()
        assert edges[0] == edge_a
        assert edges[1] == edge_b

    def test_repeated_builds_identical(self) -> None:
        """Repeated builds on the same index should produce equivalent graphs."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App",
                target="main.helper",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)

        graph1 = DependencyGraphBuilder().build(index)
        graph2 = DependencyGraphBuilder().build(index)

        assert graph1 == graph2
        assert graph1.nodes() == graph2.nodes()
        assert graph1.edges() == graph2.edges()
        assert graph1.node_count() == graph2.node_count()
        assert graph1.edge_count() == graph2.edge_count()


# ---------------------------------------------------------------------------
# Repeated execution identical
# ---------------------------------------------------------------------------


class TestRepeatedExecution:
    """Tests for repeated execution producing identical results."""

    def test_graph_equality(self) -> None:
        """Two graphs built from the same index should be equal."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)

        graph1 = DependencyGraphBuilder().build(index)
        graph2 = DependencyGraphBuilder().build(index)

        assert graph1 == graph2

    def test_graph_hash_stability(self) -> None:
        """Graphs built from the same index should have the same hash."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index_for_graph(symbols)

        graph1 = DependencyGraphBuilder().build(index)
        graph2 = DependencyGraphBuilder().build(index)

        assert hash(graph1) == hash(graph2)

    def test_transitive_dependencies_deterministic(self) -> None:
        """transitive_dependencies should produce deterministic results."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App",
                target="main.helper",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)

        graph1 = DependencyGraphBuilder().build(index)
        graph2 = DependencyGraphBuilder().build(index)

        app_node = _make_node(NodeType.CLASS, "main.App")
        deps1 = graph1.transitive_dependencies(app_node, depth=-1)
        deps2 = graph2.transitive_dependencies(app_node, depth=-1)

        assert deps1 == deps2


# ---------------------------------------------------------------------------
# Containment queries
# ---------------------------------------------------------------------------


class TestContainmentQueries:
    """Tests for contains and contained_by queries."""

    def test_contains_returns_children(self) -> None:
        """contains() should return direct children via CONTAINS edges."""
        node_class = _make_node(NodeType.CLASS, "main.App")
        node_method = _make_node(NodeType.METHOD, "main.App.run")
        node_attr = _make_node(NodeType.FUNCTION, "main.App.process")

        edges = [
            _make_edge("main.App", "main.App.run", GraphEdgeType.CONTAINS),
            _make_edge("main.App", "main.App.process", GraphEdgeType.CONTAINS),
        ]

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_class, node_method, node_attr]),
            edges=frozenset(edges),
            outgoing={"main.App": [node_method, node_attr]},
            incoming={
                "main.App.run": [node_class],
                "main.App.process": [node_class],
                "main.App": [],
            },
        )

        children = graph.contains(node_class)
        assert len(children) == 2
        assert node_method in children
        assert node_attr in children

    def test_contained_by_returns_parents(self) -> None:
        """contained_by() should return direct parents via CONTAINS edges."""
        node_class = _make_node(NodeType.CLASS, "main.App")
        node_method = _make_node(NodeType.METHOD, "main.App.run")

        edges = [
            _make_edge("main.App", "main.App.run", GraphEdgeType.CONTAINS),
        ]

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_class, node_method]),
            edges=frozenset(edges),
            outgoing={"main.App": [node_method]},
            incoming={"main.App.run": [node_class], "main.App": []},
        )

        parent = graph.contained_by(node_method)
        assert len(parent) == 1
        assert node_class in parent

    def test_contains_only_contains_edges(self) -> None:
        """contains() should only traverse CONTAINS edges, not CALLS."""
        node_class = _make_node(NodeType.CLASS, "main.App")
        node_helper = _make_node(NodeType.FUNCTION, "main.helper")

        edges = [
            _make_edge("main.App", "main.helper", GraphEdgeType.CALLS),
        ]

        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node_class, node_helper]),
            edges=frozenset(edges),
            outgoing={"main.App": [node_helper]},
            incoming={"main.helper": [node_class], "main.App": []},
        )

        children = graph.contains(node_class)
        assert len(children) == 0


# ---------------------------------------------------------------------------
# Node lookup
# ---------------------------------------------------------------------------


class TestNodeLookup:
    """Tests for find_node."""

    def test_find_node_existing(self) -> None:
        """find_node() should return node for existing qualified_name."""
        node = _make_node(NodeType.CLASS, "main.App")
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        found = graph.find_node("main.App")
        assert found is not None
        assert found.qualified_name == "main.App"

    def test_find_node_not_found(self) -> None:
        """find_node() should return None for unknown qualified_name."""
        node = _make_node(NodeType.CLASS, "main.App")
        graph = WorkspaceDependencyGraph(
            nodes=frozenset([node]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert graph.find_node("main.Unknown") is None


# ---------------------------------------------------------------------------
# Graph representation
# ---------------------------------------------------------------------------


class TestGraphRepresentation:
    """Tests for graph representation methods."""

    def test_repr(self) -> None:
        """__repr__ should return a meaningful string."""
        graph = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        repr_str = repr(graph)
        assert "WorkspaceDependencyGraph" in repr_str
        assert "nodes=0" in repr_str

    def test_eq(self) -> None:
        """__eq__ should compare nodes and edges."""
        graph1 = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        graph2 = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert graph1 == graph2

    def test_eq_different_graphs(self) -> None:
        """__eq__ should return False for different graphs."""
        node = _make_node(NodeType.CLASS, "main.App")
        graph1 = WorkspaceDependencyGraph(
            nodes=frozenset([node]),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        graph2 = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert graph1 != graph2

    def test_hash(self) -> None:
        """__hash__ should return an integer."""
        graph = WorkspaceDependencyGraph(
            nodes=frozenset(),
            edges=frozenset(),
            outgoing={},
            incoming={},
        )
        assert isinstance(hash(graph), int)


# ---------------------------------------------------------------------------
# Relationship type mapping
# ---------------------------------------------------------------------------


class TestRelationshipTypeMapping:
    """Tests for RelationshipType to GraphEdgeType mapping."""

    def test_defines_to_contains(self) -> None:
        """DEFINES should map to CONTAINS."""
        assert map_relationship_type(RelationshipType.DEFINES) == GraphEdgeType.CONTAINS

    def test_imports_to_imports(self) -> None:
        """IMPORTS should map to IMPORTS."""
        assert map_relationship_type(RelationshipType.IMPORTS) == GraphEdgeType.IMPORTS

    def test_inherits_to_inherits(self) -> None:
        """INHERITS should map to INHERITS."""
        assert map_relationship_type(RelationshipType.INHERITS) == GraphEdgeType.INHERITS

    def test_calls_to_calls(self) -> None:
        """CALLS should map to CALLS."""
        assert map_relationship_type(RelationshipType.CALLS) == GraphEdgeType.CALLS


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------


class TestBuilderConstruction:
    """Tests for DependencyGraphBuilder construction."""

    def test_empty_index(self) -> None:
        """Building from an empty index should produce an empty graph."""
        index = _make_index_for_graph([])
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 0
        assert graph.edge_count() == 0

    def test_single_symbol(self) -> None:
        """Building from a single symbol should produce one node."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index_for_graph(symbols)
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 1
        assert graph.edge_count() == 0

    def test_symbol_with_relationship(self) -> None:
        """Building from symbols with relationships should produce edges."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 2
        assert graph.edge_count() == 1

    def test_multiple_relationship_types(self) -> None:
        """Building with multiple relationship types should produce correct edges."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("Base", "main.Base", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
            _make_symbol("helper", "main.helper", SymbolType.FUNCTION, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.Base",
                type=RelationshipType.INHERITS,
            ),
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
            Relationship(
                source="main.App",
                target="main.helper",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)
        graph = DependencyGraphBuilder().build(index)
        assert graph.node_count() == 4
        assert graph.edge_count() == 3

    def test_no_repository_index_mutation(self) -> None:
        """Building a graph should not mutate the RepositoryIndex."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
            _make_symbol("run", "main.App.run", SymbolType.METHOD, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="main.App.run",
                type=RelationshipType.DEFINES,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)

        # Capture original state
        original_symbols = list(index.symbols())
        original_rels = list(index.relationships())

        _ = DependencyGraphBuilder().build(index)

        # Verify index unchanged
        assert list(index.symbols()) == original_symbols
        assert list(index.relationships()) == original_rels

    def test_builder_stateless(self) -> None:
        """Multiple builds should not affect each other."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        index = _make_index_for_graph(symbols)

        builder = DependencyGraphBuilder()
        graph1 = builder.build(index)
        graph2 = builder.build(index)

        assert graph1 == graph2

    def test_edge_only_when_both_nodes_exist(self) -> None:
        """Edges should only be created when both source and target exist as nodes."""
        symbols = [
            _make_symbol("App", "main.App", SymbolType.CLASS, "main.py"),
        ]
        relationships = [
            Relationship(
                source="main.App",
                target="nonexistent.Symbol",
                type=RelationshipType.CALLS,
            ),
        ]
        index = _make_index_for_graph(symbols, relationships)
        graph = DependencyGraphBuilder().build(index)
        assert graph.edge_count() == 0
        assert graph.node_count() == 1
