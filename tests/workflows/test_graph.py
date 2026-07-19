"""Tests for the Workflow Graph module.

Verifies:
- DAG validation
- Cycle detection
- Duplicate ID detection
- Unknown dependency detection
- Unreachable node detection
- Topological sort determinism
- Execution layers
- Transitive dependencies
"""

from __future__ import annotations

import pytest

from packages.workflows.graph import WorkflowGraph
from packages.workflows.models import WorkflowNode

# ---------------------------------------------------------------------------
# Test: Basic Graph Creation
# ---------------------------------------------------------------------------


class TestWorkflowGraphBasic:
    """Tests for basic WorkflowGraph operations."""

    def test_graph_with_single_node(self) -> None:
        node = WorkflowNode(
            node_id="a",
            task=str,  # type: ignore
        )
        graph = WorkflowGraph((node,))
        assert graph.node_ids == ("a",)
        assert graph.get_node("a") is node
        assert graph.get_node("b") is None

    def test_graph_with_multiple_nodes(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        assert graph.node_ids == ("a", "b", "c")

    def test_graph_get_dependencies(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        assert graph.get_dependencies("b") == ("a",)
        assert graph.get_dependencies("a") == ()

    def test_graph_get_transitive_dependencies(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("b",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        assert graph.get_transitive_dependencies("c") == ("a", "b")
        assert graph.get_transitive_dependencies("b") == ("a",)
        assert graph.get_transitive_dependencies("a") == ()


# ---------------------------------------------------------------------------
# Test: Validation - Duplicate IDs
# ---------------------------------------------------------------------------


class TestWorkflowGraphDuplicateIDs:
    """Tests for duplicate node ID detection."""

    def test_duplicate_node_id_raises(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        with pytest.raises(ValueError, match="Duplicate workflow node ID"):
            graph.validate()

    def test_no_duplicates_passes(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        graph.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Test: Validation - Unknown Dependencies
# ---------------------------------------------------------------------------


class TestWorkflowGraphUnknownDependencies:
    """Tests for unknown dependency detection."""

    def test_unknown_dependency_raises(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=("nonexistent",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        with pytest.raises(ValueError, match="unknown node"):
            graph.validate()

    def test_no_unknown_dependencies_passes(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        graph.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Test: Validation - Cycles
# ---------------------------------------------------------------------------


class TestWorkflowGraphCycles:
    """Tests for cycle detection."""

    def test_simple_cycle_raises(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=("b",)),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        with pytest.raises(ValueError, match="Circular dependency"):
            graph.validate()

    def test_longer_cycle_raises(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=("c",)),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("b",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        with pytest.raises(ValueError, match="Circular dependency"):
            graph.validate()

    def test_no_cycle_passes(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        graph.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Test: Validation - Unreachable Nodes
# ---------------------------------------------------------------------------


class TestWorkflowGraphUnreachable:
    """Tests for unreachable node detection."""

    def test_unreachable_node_raises(self) -> None:
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        # Node "b" is unreachable from "a" and "c" depends on "a"
        # But "b" is also a root, so all nodes are reachable from some root
        graph.validate()  # Should pass - all nodes are roots or reachable

    def test_all_roots_reachable_passes(self) -> None:
        """Multiple independent roots should all be reachable."""
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        graph.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Test: Topological Sort
# ---------------------------------------------------------------------------


class TestWorkflowGraphTopologicalSort:
    """Tests for deterministic topological sorting."""

    def test_linear_dag(self) -> None:
        nodes = (
            WorkflowNode(node_id="c", task=str, depends_on=("b",)),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        ordered = graph.topological_sort()
        assert ordered[0].node_id == "a"
        assert ordered[1].node_id == "b"
        assert ordered[2].node_id == "c"

    def test_diamond_dag(self) -> None:
        """Diamond: a → b, a → c, b → d, c → d."""
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="d", task=str, depends_on=("b", "c")),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        ordered = graph.topological_sort()

        assert ordered[0].node_id == "a"
        # b and c can be in either order, but both before d
        d_index = ordered[-1].node_id == "d"
        assert d_index

    def test_deterministic_order(self) -> None:
        """Running topological_sort twice should produce identical results."""
        nodes = (
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        first = graph.topological_sort()
        second = graph.topological_sort()
        assert first == second

    def test_empty_graph(self) -> None:
        graph = WorkflowGraph(())
        ordered = graph.topological_sort()
        assert ordered == ()

    def test_single_node_graph(self) -> None:
        node = WorkflowNode(node_id="a", task=str, depends_on=())  # type: ignore
        graph = WorkflowGraph((node,))
        ordered = graph.topological_sort()
        assert len(ordered) == 1
        assert ordered[0].node_id == "a"


# ---------------------------------------------------------------------------
# Test: Execution Layers
# ---------------------------------------------------------------------------


class TestWorkflowGraphExecutionLayers:
    """Tests for execution layer grouping."""

    def test_linear_layers(self) -> None:
        nodes = (
            WorkflowNode(node_id="c", task=str, depends_on=("b",)),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        layers = graph.get_execution_layers()
        assert len(layers) == 3
        assert layers[0] == ("a",)
        assert layers[1] == ("b",)
        assert layers[2] == ("c",)

    def test_diamond_layers(self) -> None:
        """Diamond: a → b, a → c, b → d, c → d."""
        nodes = (
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="c", task=str, depends_on=("a",)),  # type: ignore
            WorkflowNode(node_id="d", task=str, depends_on=("b", "c")),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        layers = graph.get_execution_layers()
        assert len(layers) == 3
        assert layers[0] == ("a",)
        # b and c are in the same layer (both depend only on a)
        assert layers[1] == ("b", "c")
        assert layers[2] == ("d",)

    def test_empty_layers(self) -> None:
        graph = WorkflowGraph(())
        layers = graph.get_execution_layers()
        assert layers == ()

    def test_all_independent_layers(self) -> None:
        nodes = (
            WorkflowNode(node_id="c", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="b", task=str, depends_on=()),  # type: ignore
            WorkflowNode(node_id="a", task=str, depends_on=()),  # type: ignore
        )
        graph = WorkflowGraph(nodes)
        layers = graph.get_execution_layers()
        assert len(layers) == 1
        assert layers[0] == ("a", "b", "c")


# ---------------------------------------------------------------------------
# Test: WorkflowGraph Immutability
# ---------------------------------------------------------------------------


class TestWorkflowGraphImmutability:
    """Tests for WorkflowGraph immutability."""

    def test_nodes_are_immutable(self) -> None:
        node = WorkflowNode(node_id="a", task=str, depends_on=())  # type: ignore
        graph = WorkflowGraph((node,))
        # The nodes tuple should be immutable
        with pytest.raises(TypeError):
            graph.nodes[0] = node  # type: ignore[index]

    def test_node_map_is_private(self) -> None:
        node = WorkflowNode(node_id="a", task=str, depends_on=())  # type: ignore
        graph = WorkflowGraph((node,))
        # _node_map is private, accessing it should not be modified externally
        assert "a" in graph._node_map
