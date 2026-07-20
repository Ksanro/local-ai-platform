"""Tests for ExecutionAdapter and ProviderExecutionAdapter."""

from __future__ import annotations

import pytest

from packages.execution.adapter import ExecutionAdapter, ProviderExecutionAdapter
from packages.execution.runtime_models import ExecutionStatus, ExecutionStepResult
from packages.tasks.models import TaskComplexity, TaskMetrics, TaskPlan, TaskStep
from packages.workflows.models import WorkflowStep

# ---------------------------------------------------------------------------
# ExecutionAdapter (ABC)
# ---------------------------------------------------------------------------


class TestExecutionAdapter:
    """Tests for the ExecutionAdapter abstract base class."""

    def test_name_default_is_class_name(self):
        """Default name property returns class name."""

        class TestAdapter(ExecutionAdapter):
            def execute_step(self, workflow_step, task_plan):
                return ExecutionStepResult(
                    step_name="test",
                    status=ExecutionStatus.COMPLETED,
                    started_at="",
                    finished_at="",
                    duration_ms=0,
                    output_summary="",
                )

        adapter = TestAdapter()
        assert adapter.name == "TestAdapter"

    def test_supported_capabilities_default_empty(self):
        """Default supported_capabilities returns empty tuple."""

        class TestAdapter(ExecutionAdapter):
            def execute_step(self, workflow_step, task_plan):
                return ExecutionStepResult(
                    step_name="test",
                    status=ExecutionStatus.COMPLETED,
                    started_at="",
                    finished_at="",
                    duration_ms=0,
                    output_summary="",
                )

        adapter = TestAdapter()
        assert adapter.supported_capabilities == ()

    def test_cannot_instantiate_abstract(self):
        """Cannot instantiate ExecutionAdapter directly."""
        with pytest.raises(TypeError):
            ExecutionAdapter()  # type: ignore[abstract]

    def test_abstract_execute_step(self):
        """execute_step is abstract and must be implemented."""

        class IncompleteAdapter(ExecutionAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ProviderExecutionAdapter
# ---------------------------------------------------------------------------


class TestProviderExecutionAdapter:
    """Tests for ProviderExecutionAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a ProviderExecutionAdapter instance."""
        return ProviderExecutionAdapter()

    @pytest.fixture
    def workflow_step(self):
        """Create a test WorkflowStep."""
        return WorkflowStep(
            step_id="test_step",
            order=0,
            workflow_node="test_node",
            task_name="test_task",
            description="Test step description",
        )

    @pytest.fixture
    def task_plan(self):
        """Create a test TaskPlan."""
        return TaskPlan(
            task_name="test_task",
            capability="test_capability",
            context_package=None,
            steps=(
                TaskStep(order=0, title="Step 1", description="First step"),
            ),
            metrics=TaskMetrics(estimated_tokens=100, estimated_complexity=TaskComplexity.LOW),
        )

    def test_name_property(self, adapter):
        """Adapter name is 'ProviderExecutionAdapter'."""
        assert adapter.name == "ProviderExecutionAdapter"

    def test_supported_capabilities(self, adapter):
        """Adapter supports 'provider_execution' capability."""
        assert adapter.supported_capabilities == ("provider_execution",)

    def test_delegates_to_provider(self, adapter, workflow_step, task_plan):
        """Adapter delegates to Provider infrastructure."""
        result = adapter.execute_step(workflow_step, task_plan)

        # Check that the result contains the step info
        assert result.step_name == "test_step"
        assert result.status == ExecutionStatus.COMPLETED
        assert "test_step" in result.output_summary
        assert "test_task" in result.output_summary
        assert "test_capability" in result.output_summary

    def test_does_not_duplicate_provider_logic(self, adapter, workflow_step, task_plan):
        """Adapter does not implement provider logic."""
        result = adapter.execute_step(workflow_step, task_plan)

        # The adapter should not call Provider.chat(), Provider.health(), etc.
        # It should only construct an ExecutionStepResult from the inputs.
        assert isinstance(result, ExecutionStepResult)
        assert result.metadata["task_name"] == "test_task"
        assert result.metadata["capability"] == "test_capability"
        assert result.metadata["step_order"] == 0

    def test_deterministic_behavior(self, adapter, workflow_step, task_plan):
        """Adapter produces deterministic results."""
        result1 = adapter.execute_step(workflow_step, task_plan)
        result2 = adapter.execute_step(workflow_step, task_plan)

        assert result1.step_name == result2.step_name
        assert result1.status == result2.status
        assert result1.output_summary == result2.output_summary
        assert result1.metadata == result2.metadata

    def test_stateless(self, adapter, workflow_step, task_plan):
        """Adapter is stateless (no internal state mutation)."""
        result1 = adapter.execute_step(workflow_step, task_plan)
        result2 = adapter.execute_step(workflow_step, task_plan)
        result3 = adapter.execute_step(workflow_step, task_plan)

        assert result1 == result2
        assert result2 == result3

    def test_returns_immutable_result(self, adapter, workflow_step, task_plan):
        """Adapter returns immutable ExecutionStepResult."""
        result = adapter.execute_step(workflow_step, task_plan)

        with pytest.raises(Exception):
            result.step_name = "changed"
        with pytest.raises(Exception):
            result.status = ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Adapter Interoperability
# ---------------------------------------------------------------------------


class TestAdapterInteroperability:
    """Tests for adapter interchangeability."""

    def test_custom_adapter_works(self):
        """Custom adapters work with the engine interface."""

        class CustomAdapter(ExecutionAdapter):
            @property
            def name(self) -> str:
                return "CustomAdapter"

            @property
            def supported_capabilities(self) -> tuple[str, ...]:
                return ("custom",)

            def execute_step(self, workflow_step, task_plan):
                return ExecutionStepResult(
                    step_name=workflow_step.step_id,
                    status=ExecutionStatus.COMPLETED,
                    started_at="2024-01-01T00:00:00",
                    finished_at="2024-01-01T00:00:01",
                    duration_ms=500,
                    output_summary="Custom adapter result",
                )

        adapter = CustomAdapter()
        assert adapter.name == "CustomAdapter"
        assert adapter.supported_capabilities == ("custom",)

    def test_adapter_name_overridden(self):
        """Adapter can override name property."""

        class NamedAdapter(ExecutionAdapter):
            @property
            def name(self) -> str:
                return "MyCustomName"

            def execute_step(self, workflow_step, task_plan):
                return ExecutionStepResult(
                    step_name="test",
                    status=ExecutionStatus.COMPLETED,
                    started_at="",
                    finished_at="",
                    duration_ms=0,
                    output_summary="",
                )

        adapter = NamedAdapter()
        assert adapter.name == "MyCustomName"
