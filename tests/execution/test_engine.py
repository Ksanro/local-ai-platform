"""Tests for ExecutionEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from packages.execution.adapter import ExecutionAdapter
from packages.execution.engine import ExecutionEngine
from packages.execution.runtime_models import ExecutionStatus, ExecutionStepResult
from packages.tasks.models import TaskComplexity, TaskMetrics, TaskPlan, TaskStep
from packages.workflows.models import WorkflowMetrics, WorkflowPlan, WorkflowStep

if TYPE_CHECKING:
    from packages.core.context import ContextPackage  # noqa: F401


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_workflow_plan() -> WorkflowPlan:
    """Create a valid WorkflowPlan for testing."""
    steps = (
        WorkflowStep(
            step_id="analyze_step",
            order=0,
            workflow_node="analyze",
            task_name="analyze",
            description="Analyze repository",
        ),
        WorkflowStep(
            step_id="implement_step",
            order=1,
            workflow_node="implement",
            task_name="implement",
            description="Implement feature",
        ),
    )
    task_steps = (
        TaskStep(order=0, title="Step 1", description="First step"),
        TaskStep(order=1, title="Step 2", description="Second step"),
    )
    task_plans = (
        TaskPlan(
            task_name="analyze",
            capability="analysis",
            context_package=None,
            steps=task_steps,
            metrics=TaskMetrics(estimated_tokens=100, estimated_complexity=TaskComplexity.LOW),
        ),
        TaskPlan(
            task_name="implement",
            capability="implementation",
            context_package=None,
            steps=task_steps,
            metrics=TaskMetrics(estimated_tokens=200, estimated_complexity=TaskComplexity.MEDIUM),
        ),
    )
    return WorkflowPlan(
        workflow_name="test_workflow",
        task_plans=task_plans,
        workflow_steps=steps,
        metrics=WorkflowMetrics(estimated_tokens=300, estimated_duration_ms=5000),
    )


@pytest.fixture
def mock_adapter():
    """Create a mock adapter for testing."""
    class MockAdapter(ExecutionAdapter):
        def __init__(self, fail_step: str | None = None):
            self._fail_step = fail_step
            self.call_log: list[tuple[str, str]] = []

        @property
        def name(self) -> str:
            return "MockAdapter"

        @property
        def supported_capabilities(self) -> tuple[str, ...]:
            return ("test",)

        def execute_step(
            self, workflow_step: WorkflowStep, task_plan: TaskPlan
        ) -> ExecutionStepResult:
            self.call_log.append((workflow_step.step_id, task_plan.task_name))
            if workflow_step.step_id == self._fail_step:
                return ExecutionStepResult(
                    step_name=workflow_step.step_id,
                    status=ExecutionStatus.FAILED,
                    started_at="2024-01-01T00:00:00",
                    finished_at="2024-01-01T00:00:01",
                    duration_ms=1000,
                    output_summary=f"Failed: {workflow_step.step_id}",
                )
            return ExecutionStepResult(
                step_name=workflow_step.step_id,
                status=ExecutionStatus.COMPLETED,
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:00:01",
                duration_ms=1000,
                output_summary=f"Completed: {workflow_step.step_id}",
            )

    return MockAdapter


# ---------------------------------------------------------------------------
# Tests: execute() - all steps succeed
# ---------------------------------------------------------------------------


class TestExecuteAllSuccess:
    """Tests for successful execution of all workflow steps."""

    def test_executes_all_workflow_steps(self, valid_workflow_plan, mock_adapter):
        """Engine executes all workflow steps in order."""
        adapter = mock_adapter()
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        assert len(report.step_results) == 2
        assert report.step_results[0].step_name == "analyze_step"
        assert report.step_results[1].step_name == "implement_step"
        assert report.execution_status == ExecutionStatus.COMPLETED
        assert report.success is True

    def test_deterministic_execution_order(self, valid_workflow_plan, mock_adapter):
        """Engine executes steps in deterministic order."""
        adapter = mock_adapter()
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        # Steps should be in the order they appear in workflow_steps
        assert report.step_results[0].step_name == "analyze_step"
        assert report.step_results[1].step_name == "implement_step"

    def test_produces_immutable_report(self, valid_workflow_plan, mock_adapter):
        """Engine produces an immutable report."""
        adapter = mock_adapter()
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        # Report fields should be immutable (frozen dataclass)
        with pytest.raises(Exception):
            report.workflow_name = "changed"  # type: ignore[misc]
        with pytest.raises(Exception):
            report.step_results = ()  # type: ignore[misc]

    def test_execution_session_lifecycle(self, valid_workflow_plan, mock_adapter):
        """Engine creates and completes execution session."""
        adapter = mock_adapter()
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        assert report.workflow_name == "test_workflow"
        assert report.adapter_name == "MockAdapter"
        assert report.execution_status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Tests: execute() - stop on first failure
# ---------------------------------------------------------------------------


class TestExecuteOnFailure:
    """Tests for failure handling."""

    def test_stops_on_first_failure(self, valid_workflow_plan, mock_adapter):
        """Engine stops execution on first failure."""
        adapter = mock_adapter(fail_step="analyze_step")
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        # Should only have the failed step
        assert len(report.step_results) == 1
        assert report.step_results[0].status == ExecutionStatus.FAILED
        assert report.execution_status == ExecutionStatus.FAILED
        assert report.success is False
        assert len(report.failures) == 1

    def test_failure_contains_step_info(self, valid_workflow_plan, mock_adapter):
        """Failure report contains step information."""
        adapter = mock_adapter(fail_step="analyze_step")
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)

        assert "analyze_step" in report.failures[0]


# ---------------------------------------------------------------------------
# Tests: execute() - validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for WorkflowPlan validation."""

    def test_rejects_empty_workflow_name(self, mock_adapter):
        """Engine rejects WorkflowPlan with empty name."""
        plan = WorkflowPlan(
            workflow_name="",
            task_plans=(),
            workflow_steps=(),
        )
        adapter = mock_adapter()
        with pytest.raises(ValueError, match="workflow_name"):
            ExecutionEngine.execute(plan, adapter)

    def test_rejects_empty_workflow_steps(self, mock_adapter):
        """Engine rejects WorkflowPlan with no steps."""
        plan = WorkflowPlan(
            workflow_name="test",
            task_plans=(),
            workflow_steps=(),
        )
        adapter = mock_adapter()
        with pytest.raises(ValueError, match="no workflow steps"):
            ExecutionEngine.execute(plan, adapter)


# ---------------------------------------------------------------------------
# Tests: execute() - adapter behavior
# ---------------------------------------------------------------------------


class TestAdapterBehavior:
    """Tests for adapter interaction."""

    def test_adapter_name_property(self, valid_workflow_plan, mock_adapter):
        """Engine uses adapter.name property."""
        adapter = mock_adapter()
        report = ExecutionEngine.execute(valid_workflow_plan, adapter)
        assert report.adapter_name == "MockAdapter"

    def test_adapter_called_once_per_step(self, valid_workflow_plan, mock_adapter):
        """Engine calls adapter once per workflow step."""
        adapter = mock_adapter()
        ExecutionEngine.execute(valid_workflow_plan, adapter)
        assert len(adapter.call_log) == 2

    def test_adapter_receives_correct_step(self, valid_workflow_plan, mock_adapter):
        """Engine passes correct WorkflowStep to adapter."""
        adapter = mock_adapter()
        ExecutionEngine.execute(valid_workflow_plan, adapter)
        assert adapter.call_log[0][0] == "analyze_step"
        assert adapter.call_log[1][0] == "implement_step"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_step_workflow(self, mock_adapter):
        """Engine handles single-step workflow."""
        plan = WorkflowPlan(
            workflow_name="single_step",
            task_plans=(
                TaskPlan(
                    task_name="step1",
                    capability="test",
                    context_package=None,
                    steps=(
                        TaskStep(order=0, title="Step 1", description="First step"),
                    ),
                    metrics=TaskMetrics(
                        estimated_tokens=100,
                        estimated_complexity=TaskComplexity.LOW,
                    ),
                ),
            ),
            workflow_steps=(
                WorkflowStep(
                    step_id="step1",
                    order=0,
                    workflow_node="node1",
                    task_name="step1",
                    description="Single step",
                ),
            ),
        )
        adapter = mock_adapter()
        report = ExecutionEngine.execute(plan, adapter)
        assert len(report.step_results) == 1
        assert report.success is True

    def test_workflow_with_no_matching_task_plan(self, mock_adapter):
        """Engine handles steps with no matching task plan."""
        plan = WorkflowPlan(
            workflow_name="no_match",
            task_plans=(),
            workflow_steps=(
                WorkflowStep(
                    step_id="orphan_step",
                    order=0,
                    workflow_node="orphan",
                    task_name="orphan",
                    description="No matching task",
                ),
            ),
        )
        adapter = mock_adapter()
        report = ExecutionEngine.execute(plan, adapter)
        assert len(report.step_results) == 0
        assert report.execution_status == ExecutionStatus.COMPLETED
