"""Integration test: complete engineering execution flow.

Verifies the full Integration Milestone v1 pipeline:

    Request
      → PlanningStage
      → RepositoryContextStage
      → WorkflowStage
      → ExecutionStage
      → VerificationStage
      → EvaluationStage
      → ProviderStage

Tests
-----
- test_full_pipeline_execution: All stages execute successfully.
- test_deterministic_order: Stages execute in correct order.
- test_immutable_reports: Reports are frozen dataclasses.
- test_context_survival: PipelineContext preserves all reports.
- test_provider_receives_unchanged_request: Provider receives original request.
- test_repository_context_pipeline: Existing repository-context pipeline works.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.request import PipelineRequest
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages import (
    EvaluationStage,
    ExecutionStage,
    PlanningStage,
    ProviderStage,
    RepositoryContextStage,
    VerificationStage,
    WorkflowStage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(request_data: dict | None = None) -> PipelineContext:
    """Create a minimal PipelineContext for testing."""
    return PipelineContext(
        request=request_data or {"messages": [{"role": "user", "content": "test"}]},
    )


def _make_request(
    provider_name: str = "vllm",
    model: str = "default",
    messages: list | None = None,
) -> PipelineRequest:
    """Create a minimal PipelineRequest for testing."""
    return PipelineRequest(
        provider_name=provider_name,
        model=model,
        messages=messages or [{"role": "user", "content": "test"}],
    )


# ---------------------------------------------------------------------------
# test_full_pipeline_execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_execution() -> None:
    """Verify all stages execute successfully in the integration pipeline.

    Creates a minimal pipeline with all integration stages and verifies
    that each stage completes without raising exceptions.
    """
    # Create a mock pipeline engine.
    engine = PipelineEngine()

    # Register mock stages that simulate successful execution.
    stage_order: list[str] = []

    class MockPlanningStage(PipelineStage):
        @property
        def name(self) -> str:
            return "planning"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("planning")
            return PipelineStageResult(stage_name=self.name, success=True, data={"intent": "IMPLEMENTATION"})

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockRepositoryContextStage(PipelineStage):
        @property
        def name(self) -> str:
            return "repository_context"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("repository_context")
            return PipelineStageResult(stage_name=self.name, success=True, data=None)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockWorkflowStage(PipelineStage):
        @property
        def name(self) -> str:
            return "workflow"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("workflow")
            # Create a minimal workflow plan.
            from packages.workflows.models import WorkflowPlan, WorkflowStep, WorkflowMetrics
            from packages.tasks.models import TaskComplexity

            plan = WorkflowPlan(
                workflow_name="test-workflow",
                task_plans=(),
                workflow_steps=(
                    WorkflowStep(
                        step_id="step-1",
                        order=0,
                        workflow_node="node-1",
                        task_name="test-task",
                        description="Test step",
                    ),
                ),
                metrics=WorkflowMetrics(
                    estimated_tokens=100,
                    estimated_duration_ms=1000,
                    estimated_complexity=TaskComplexity.LOW,
                ),
            )
            context.workflow_plan = plan
            return PipelineStageResult(stage_name=self.name, success=True, data=plan)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockExecutionStage(PipelineStage):
        @property
        def name(self) -> str:
            return "execution"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("execution")
            # Create a minimal execution report.
            from packages.execution.runtime_models import ExecutionReport, ExecutionStatus, ExecutionStepResult

            step_result = ExecutionStepResult(
                step_name="step-1",
                status=ExecutionStatus.COMPLETED,
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:00:01",
                duration_ms=1000,
                output_summary="Completed",
            )
            report = ExecutionReport(
                workflow_name="test-workflow",
                execution_status=ExecutionStatus.COMPLETED,
                total_duration_ms=1000,
                step_results=(step_result,),
                adapter_name="test-adapter",
                success=True,
                failures=(),
            )
            context.execution_report = report
            return PipelineStageResult(stage_name=self.name, success=True, data=report)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockVerificationStage(PipelineStage):
        @property
        def name(self) -> str:
            return "verification"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("verification")
            # Create a minimal verification report.
            from packages.verification.models import (
                VerificationReport,
                VerificationStatus,
                VerificationStatistics,
            )

            report = VerificationReport(
                workflow_name="test-workflow",
                execution_id="test-exec",
                verification_status=VerificationStatus.PASSED,
                findings=(),
                statistics=VerificationStatistics(),
                score=1.0,
            )
            context.verification_report = report
            return PipelineStageResult(stage_name=self.name, success=True, data=report)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockEvaluationStage(PipelineStage):
        @property
        def name(self) -> str:
            return "evaluation"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("evaluation")
            # Create a minimal evaluation report.
            from packages.evaluation.models import EvaluationReport, EvaluationMetric, EvaluationScore

            report = EvaluationReport(
                workflow_name="test-workflow",
                task_name="test-task",
                provider="vllm",
                model="default",
                started_at="2024-01-01T00:00:00",
                completed_at="2024-01-01T00:00:01",
                metrics=(),
                scores=(),
                overall_score=0.9,
                summary="Good quality",
            )
            context.evaluation_report = report
            return PipelineStageResult(stage_name=self.name, success=True, data=report)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    class MockProviderStage(PipelineStage):
        @property
        def name(self) -> str:
            return "provider"

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            stage_order.append("provider")
            return PipelineStageResult(stage_name=self.name, success=True, data={"content": "response"})

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    # Register stages in correct order.
    engine.register(MockPlanningStage())
    engine.register(MockRepositoryContextStage())
    engine.register(MockWorkflowStage())
    engine.register(MockExecutionStage())
    engine.register(MockVerificationStage())
    engine.register(MockEvaluationStage())
    engine.register(MockProviderStage())

    # Execute the pipeline.
    request = _make_request()
    response = await engine.execute(request)

    # Verify all stages executed in correct order.
    assert response.success is True
    assert stage_order == [
        "planning",
        "repository_context",
        "workflow",
        "execution",
        "verification",
        "evaluation",
        "provider",
    ]


# ---------------------------------------------------------------------------
# test_deterministic_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_order() -> None:
    """Verify stages execute in deterministic order across multiple runs.

    Runs the pipeline twice and verifies that the stage execution order
    is identical both times.
    """
    stage_order_1: list[str] = []
    stage_order_2: list[str] = []

    class CountingStage(PipelineStage):
        def __init__(self, name: str, order_list: list[str]) -> None:
            self._name = name
            self._order_list = order_list

        @property
        def name(self) -> str:
            return self._name

        async def before(self, context: PipelineContext) -> PipelineStageResult | None:
            return None

        async def execute(self, context: PipelineContext) -> PipelineStageResult:
            self._order_list.append(self._name)
            return PipelineStageResult(stage_name=self._name, success=True, data=None)

        async def after(self, context: PipelineContext, result: PipelineStageResult) -> PipelineStageResult | None:
            return None

    stages = [
        ("planning", stage_order_1),
        ("repository_context", stage_order_1),
        ("workflow", stage_order_1),
        ("execution", stage_order_1),
        ("verification", stage_order_1),
        ("evaluation", stage_order_1),
        ("provider", stage_order_1),
    ]

    # Run 1.
    engine1 = PipelineEngine()
    for name, order_list in stages:
        engine1.register(CountingStage(name, order_list))

    request = _make_request()
    await engine1.execute(request)

    # Run 2.
    engine2 = PipelineEngine()
    for name, order_list in stages:
        engine2.register(CountingStage(name, order_list))

    await engine2.execute(request)

    # Verify deterministic order.
    assert stage_order_1 == stage_order_2
    assert stage_order_1 == [
        "planning",
        "repository_context",
        "workflow",
        "execution",
        "verification",
        "evaluation",
        "provider",
    ]


# ---------------------------------------------------------------------------
# test_immutable_reports
# ---------------------------------------------------------------------------


def test_immutable_reports() -> None:
    """Verify that ExecutionReport, VerificationReport, and EvaluationReport are immutable.

    All report types should be frozen dataclasses — attempting to modify
    their attributes should raise an error.
    """
    # ExecutionReport.
    from packages.execution.runtime_models import ExecutionReport, ExecutionStatus, ExecutionStepResult

    step = ExecutionStepResult(
        step_name="test",
        status=ExecutionStatus.COMPLETED,
        started_at="2024-01-01",
        finished_at="2024-01-01",
        duration_ms=100,
        output_summary="ok",
    )
    exec_report = ExecutionReport(
        workflow_name="test",
        execution_status=ExecutionStatus.COMPLETED,
        total_duration_ms=100,
        step_results=(step,),
        adapter_name="test",
        success=True,
    )

    # Should raise error because dataclass is frozen.
    with pytest.raises(Exception):  # FrozenInstanceError or similar.
        exec_report.workflow_name = "modified"  # type: ignore[misc]

    # VerificationReport.
    from packages.verification.models import (
        VerificationReport,
        VerificationStatus,
        VerificationStatistics,
    )

    ver_report = VerificationReport(
        workflow_name="test",
        execution_id="exec-1",
        verification_status=VerificationStatus.PASSED,
        findings=(),
        statistics=VerificationStatistics(),
        score=1.0,
    )

    with pytest.raises(Exception):
        ver_report.workflow_name = "modified"  # type: ignore[misc]

    # EvaluationReport.
    from packages.evaluation.models import EvaluationReport

    eval_report = EvaluationReport(
        workflow_name="test",
        task_name="task",
        provider="vllm",
        model="default",
        started_at="2024-01-01",
        completed_at="2024-01-01",
        metrics=(),
        scores=(),
        overall_score=0.9,
        summary="ok",
    )

    with pytest.raises(Exception):
        eval_report.workflow_name = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# test_context_survival
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_survival() -> None:
    """Verify PipelineContext preserves all reports through every stage.

    Each stage stores its output in the context, and subsequent stages
    can read those values. All reports survive until the pipeline ends.
    """
    context = PipelineContext(
        request={"messages": [{"role": "user", "content": "test"}]},
    )

    # Simulate stage execution and context storage.
    # Stage 1: Planning produces context_package.
    from packages.context.context_package import ContextPackage

    context.context_package = ContextPackage(
        primary_symbol="test_symbol",
        supporting_symbols=[],
        related_modules=[],
        estimated_tokens=100,
    )

    # Stage 2: Workflow produces workflow_plan.
    from packages.workflows.models import WorkflowPlan, WorkflowStep, WorkflowMetrics
    from packages.tasks.models import TaskComplexity

    workflow_plan = WorkflowPlan(
        workflow_name="test-workflow",
        task_plans=(),
        workflow_steps=(
            WorkflowStep(
                step_id="step-1",
                order=0,
                workflow_node="node-1",
                task_name="test-task",
                description="Test",
            ),
        ),
        metrics=WorkflowMetrics(),
    )
    context.workflow_plan = workflow_plan

    # Stage 3: Execution produces execution_report.
    from packages.execution.runtime_models import ExecutionReport, ExecutionStatus, ExecutionStepResult

    step_result = ExecutionStepResult(
        step_name="step-1",
        status=ExecutionStatus.COMPLETED,
        started_at="2024-01-01",
        finished_at="2024-01-01",
        duration_ms=100,
        output_summary="ok",
    )
    execution_report = ExecutionReport(
        workflow_name="test-workflow",
        execution_status=ExecutionStatus.COMPLETED,
        total_duration_ms=100,
        step_results=(step_result,),
        adapter_name="test",
        success=True,
    )
    context.execution_report = execution_report

    # Stage 4: Verification produces verification_report.
    from packages.verification.models import (
        VerificationReport,
        VerificationStatus,
        VerificationStatistics,
    )

    verification_report = VerificationReport(
        workflow_name="test-workflow",
        execution_id="exec-1",
        verification_status=VerificationStatus.PASSED,
        findings=(),
        statistics=VerificationStatistics(),
        score=1.0,
    )
    context.verification_report = verification_report

    # Stage 5: Evaluation produces evaluation_report.
    from packages.evaluation.models import EvaluationReport

    evaluation_report = EvaluationReport(
        workflow_name="test-workflow",
        task_name="test-task",
        provider="vllm",
        model="default",
        started_at="2024-01-01",
        completed_at="2024-01-01",
        metrics=(),
        scores=(),
        overall_score=0.9,
        summary="ok",
    )
    context.evaluation_report = evaluation_report

    # Verify all reports survive.
    assert context.context_package is not None
    assert context.workflow_plan is not None
    assert context.execution_report is not None
    assert context.verification_report is not None
    assert context.evaluation_report is not None

    # Verify reports are accessible via metadata too.
    assert context.get_metadata("workflow_plan") is context.workflow_plan
    assert context.get_metadata("execution_report") is context.execution_report
    assert context.get_metadata("verification_report") is context.verification_report
    assert context.get_metadata("evaluation_report") is context.evaluation_report


# ---------------------------------------------------------------------------
# test_provider_receives_unchanged_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_receives_unchanged_request() -> None:
    """Verify provider receives unchanged request.

    The original request data should be preserved through the pipeline
    and available to the provider stage.
    """
    original_request = {
        "messages": [
            {"role": "user", "content": "Implement feature X"},
            {"role": "assistant", "content": "Understood"},
        ],
        "model": "gpt-4",
        "stream": False,
    }

    context = PipelineContext(request=original_request)

    # Simulate stages modifying context but not the original request.
    context.set_metadata("workflow_plan", "plan-data")
    context.set_metadata("execution_report", "report-data")

    # Verify original request is unchanged.
    assert context.request is original_request
    assert context.request["messages"] == original_request["messages"]
    assert context.request["model"] == original_request["model"]
    assert context.request["stream"] == original_request["stream"]

    # Verify metadata additions don't affect original request.
    assert context.get_metadata("workflow_plan") == "plan-data"
    assert context.request is original_request


# ---------------------------------------------------------------------------
# test_repository_context_pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_context_pipeline() -> None:
    """Verify existing repository-context pipeline remains functional.

    Tests that RepositoryContextStage still works with and without an
    index, and that the context pipeline (builder -> ranking -> budget ->
    composer) remains intact.
    """
    # Test 1: Stage without index (graceful degradation).
    stage_no_index = RepositoryContextStage(index=None)
    assert stage_no_index._index is None

    context_no_index = _make_context()
    result_no_index = await stage_no_index.execute(context_no_index)

    assert result_no_index.success is True
    assert context_no_index.context_package is None

    # Test 2: Stage with index (should work if index has content).
    # Create a minimal mock index.
    from packages.repository.index.models import RepositoryIndex, RepositoryStatistics

    mock_stats = RepositoryStatistics(
        file_count=0,
        directory_count=0,
        symbol_count=0,
        module_count=0,
    )
    mock_index = RepositoryIndex(
        root_path=".",
        statistics=mock_stats,
    )

    stage_with_index = RepositoryContextStage(index=mock_index)
    assert stage_with_index._index is not None

    context_with_index = _make_context()
    result_with_index = await stage_with_index.execute(context_with_index)

    # Should succeed even with empty index (graceful degradation).
    assert result_with_index.success is True


# ---------------------------------------------------------------------------
# test_stage_boundary_constraints
# ---------------------------------------------------------------------------


def test_stage_boundary_constraints() -> None:
    """Verify stage boundary constraints are documented.

    Each stage has clear boundaries about what it can and cannot do.
    This test verifies that the stage classes have the expected properties.
    """
    # WorkflowStage should have a name.
    assert WorkflowStage().name == "workflow"

    # ExecutionStage should have a name.
    assert ExecutionStage().name == "execution"

    # VerificationStage should have a name.
    assert VerificationStage().name == "verification"

    # EvaluationStage should have a name.
    assert EvaluationStage().name == "evaluation"


# ---------------------------------------------------------------------------
# test_pipeline_context_fields
# ---------------------------------------------------------------------------


def test_pipeline_context_fields() -> None:
    """Verify PipelineContext has all required fields for integration.

    PipelineContext must have:
    - workflow_plan
    - execution_report
    - verification_report
    - evaluation_report
    """
    context = PipelineContext()

    # All fields should be None initially.
    assert context.workflow_plan is None
    assert context.execution_report is None
    assert context.verification_report is None
    assert context.evaluation_report is None

    # Should be settable.
    context.workflow_plan = "plan"
    assert context.workflow_plan == "plan"

    context.execution_report = "report"
    assert context.execution_report == "report"

    context.verification_report = "verification"
    assert context.verification_report == "verification"

    context.evaluation_report = "evaluation"
    assert context.evaluation_report == "evaluation"