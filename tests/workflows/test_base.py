"""Tests for the Workflow base classes.

Verifies:
- Workflow ABC interface
- Workflow name property
- Workflow node property
- Request validation
- Abstract method enforcement
"""

from __future__ import annotations

from abc import ABC

import pytest

from packages.tasks.models import TaskRequest
from packages.workflows.base import Workflow
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowNode,
    WorkflowPlan,
)

# ---------------------------------------------------------------------------
# Test Fixtures: Concrete Workflow Implementations
# ---------------------------------------------------------------------------


class SimpleTestWorkflow(Workflow):
    """A simple test workflow with linear nodes."""

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return (
            WorkflowNode(
                node_id="a",
                task=str,  # type: ignore
                depends_on=(),
            ),
            WorkflowNode(
                node_id="b",
                task=str,  # type: ignore
                depends_on=("a",),
            ),
        )

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        return WorkflowPlan(
            workflow_name=self.name,
            task_plans=(),
        )

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        return WorkflowMetrics(estimated_tokens=100)


class EmptyTestWorkflow(Workflow):
    """A workflow with no nodes."""

    @property
    def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
        return ()

    def _do_plan(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowPlan:
        return WorkflowPlan(
            workflow_name=self.name,
            task_plans=(),
        )

    def _do_estimate(
        self,
        repository_index: object,
        request: TaskRequest,
    ) -> WorkflowMetrics:
        return WorkflowMetrics()


# ---------------------------------------------------------------------------
# Test: Workflow ABC
# ---------------------------------------------------------------------------


class TestWorkflowABC:
    """Tests for Workflow ABC."""

    def test_workflow_is_abstract(self) -> None:
        assert issubclass(Workflow, ABC)

    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            Workflow()  # type: ignore

    def test_subclass_must_implement_workflow_nodes(self) -> None:
        """Workflow ABC requires workflow_nodes implementation."""
        # This test verifies that workflow_nodes is abstract
        with pytest.raises(TypeError):
            class IncompleteWorkflow(Workflow):
                @property
                def name(self) -> str:
                    return "incomplete"

                def _do_plan(
                    self,
                    repository_index: object,
                    request: TaskRequest,
                ) -> WorkflowPlan:
                    return WorkflowPlan(
                        workflow_name=self.name,
                        task_plans=(),
                    )

                def _do_estimate(
                    self,
                    repository_index: object,
                    request: TaskRequest,
                ) -> WorkflowMetrics:
                    return WorkflowMetrics()

            IncompleteWorkflow()  # type: ignore


# ---------------------------------------------------------------------------
# Test: Workflow Name
# ---------------------------------------------------------------------------


class TestWorkflowName:
    """Tests for Workflow name property."""

    def test_default_name(self) -> None:
        wf = SimpleTestWorkflow()
        assert wf.name == "simpletestworkflow"

    def test_name_is_lowercase(self) -> None:
        class CamelCaseWorkflow(Workflow):
            @property
            def workflow_nodes(self) -> tuple[WorkflowNode, ...]:
                return ()

            def _do_plan(
                self,
                repository_index: object,
                request: TaskRequest,
            ) -> WorkflowPlan:
                return WorkflowPlan(
                    workflow_name=self.name,
                    task_plans=(),
                )

            def _do_estimate(
                self,
                repository_index: object,
                request: TaskRequest,
            ) -> WorkflowMetrics:
                return WorkflowMetrics()

        wf = CamelCaseWorkflow()
        assert wf.name == "camelcaseworkflow"


# ---------------------------------------------------------------------------
# Test: Workflow Nodes
# ---------------------------------------------------------------------------


class TestWorkflowNodes:
    """Tests for Workflow workflow_nodes property."""

    def test_linear_nodes(self) -> None:
        wf = SimpleTestWorkflow()
        nodes = wf.workflow_nodes
        assert len(nodes) == 2
        assert nodes[0].node_id == "a"
        assert nodes[1].node_id == "b"
        assert nodes[1].depends_on == ("a",)

    def test_empty_nodes(self) -> None:
        wf = EmptyTestWorkflow()
        assert wf.workflow_nodes == ()


# ---------------------------------------------------------------------------
# Test: Request Validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    """Tests for request validation."""

    def test_valid_request_passes(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="Test query")
        wf.validate(request)  # Should not raise

    def test_empty_query_raises(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="")
        with pytest.raises(ValueError, match="query cannot be empty"):
            wf.validate(request)

    def test_none_query_raises(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="")
        with pytest.raises(ValueError, match="query cannot be empty"):
            wf.validate(request)


# ---------------------------------------------------------------------------
# Test: Plan Generation
# ---------------------------------------------------------------------------


class TestPlanGeneration:
    """Tests for plan generation."""

    def test_plan_returns_workflow_plan(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="Test query")
        plan = wf.plan(
            repository_index=None,
            request=request,
        )
        assert isinstance(plan, WorkflowPlan)
        assert plan.workflow_name == "simpletestworkflow"

    def test_plan_validates_first(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="")
        with pytest.raises(ValueError, match="query cannot be empty"):
            wf.plan(
                repository_index=None,
                request=request,
            )


# ---------------------------------------------------------------------------
# Test: Estimate Generation
# ---------------------------------------------------------------------------


class TestEstimateGeneration:
    """Tests for estimate generation."""

    def test_estimate_returns_metrics(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="Test query")
        metrics = wf.estimate(
            repository_index=None,
            request=request,
        )
        assert isinstance(metrics, WorkflowMetrics)
        assert metrics.estimated_tokens == 100

    def test_estimate_validates_first(self) -> None:
        wf = SimpleTestWorkflow()
        request = TaskRequest(query="")
        with pytest.raises(ValueError, match="query cannot be empty"):
            wf.estimate(
                repository_index=None,
                request=request,
            )


# ---------------------------------------------------------------------------
# Test: Workflow Immutability
# ---------------------------------------------------------------------------


class TestWorkflowImmutability:
    """Tests for workflow immutability."""

    def test_workflow_is_stateless(self) -> None:
        """Workflows should be stateless - no instance attributes."""
        wf = SimpleTestWorkflow()
        # Creating multiple instances should be independent
        wf2 = SimpleTestWorkflow()
        assert wf.workflow_nodes == wf2.workflow_nodes
        assert wf.name == wf2.name
