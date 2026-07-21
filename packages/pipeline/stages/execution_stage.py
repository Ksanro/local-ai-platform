"""Execution pipeline stage.

Executes a WorkflowPlan through the ExecutionEngine, producing an
ExecutionReport that is consumed by the VerificationStage.

Architecture
------------

PipelineContext
       |
       v
ExecutionStage
       |
       |-- ExecutionEngine    (execute WorkflowPlan)
       |-- ExecutionAdapter   (ProviderExecutionAdapter)
       |
       v
PipelineContext.execution_report

The stage is an orchestration layer only. It never performs repository
analysis, planning, ranking, or serialization.

Constraints
-----------

The stage
- must not call providers directly
- must not parse repositories
- must not perform ranking
- must not serialize
- must not edit source code

The stage only invokes the ExecutionEngine through its public API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from packages.execution.adapter import ProviderExecutionAdapter
from packages.execution.engine import ExecutionEngine
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult

logger = logging.getLogger(__name__)


class ExecutionStage(PipelineStage):
    """Pipeline stage that executes a WorkflowPlan.

    Orchestrates the execution of a WorkflowPlan through the
    ExecutionEngine, producing an ExecutionReport.

    Attributes:
        _engine: The execution engine for step execution.
    """

    def __init__(self, engine: ExecutionEngine | None = None) -> None:
        """Initialize with optional engine.

        Args:
            engine: The ExecutionEngine to use. Defaults to new engine.
        """
        self._engine = engine if engine is not None else ExecutionEngine()

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "execution"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if execution is enabled and has a workflow plan.

        Reads the ``execution_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled or no workflow_plan is present, records a no-op
        result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if execution is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        execution_enabled = context.get_metadata("execution_enabled", True)
        if not execution_enabled:
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"execution_enabled": False},
            )

        # Check if we have a workflow plan.
        if context.workflow_plan is None:
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error="No WorkflowPlan available in context",
            )

        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Execute the WorkflowPlan and produce an ExecutionReport.

        Invokes the ExecutionEngine with the WorkflowPlan from context
        and a ProviderExecutionAdapter. Stores the result in
        ``context.execution_report``.

        On any exception, logs the error and returns a failed result.

        Args:
            context: The pipeline context with workflow plan.

        Returns:
            A PipelineStageResult with the ExecutionReport on success.
        """
        request_id = context.request_id

        try:
            workflow_plan = context.workflow_plan
            if workflow_plan is None:
                raise ValueError("No WorkflowPlan available in context")

            # Create the adapter.
            adapter = ProviderExecutionAdapter()

            # Execute the workflow plan.
            execution_report = self._engine.execute(
                workflow_plan=workflow_plan,
                adapter=adapter,
            )

            # Store in context.
            context.execution_report = execution_report

            # Also store in metadata for downstream access.
            context.set_metadata("execution_report", execution_report)

            logger.info(
                "execution request_id=%s workflow=%s status=%s success=%d steps=%d",
                request_id,
                execution_report.workflow_name,
                execution_report.execution_status.value,
                int(execution_report.success),
                len(execution_report.step_results),
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=execution_report,
            )

        except Exception as exc:
            logger.error(
                "execution request_id=%s error=%s",
                context.request_id,
                exc,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error=str(exc),
                exception=exc,
            )

    async def after(
        self, context: PipelineContext, result: PipelineStageResult
    ) -> PipelineStageResult | None:
        """Log stage completion.

        Args:
            context: The pipeline context.
            result: The result from this stage.

        Returns:
            ``None`` to keep the existing result.
        """
        if result.success:
            report = context.execution_report
            if report is not None:
                logger.info(
                    "execution request_id=%s workflow=%s status=%s success=%d",
                    context.request_id,
                    report.workflow_name,
                    report.execution_status.value,
                    int(report.success),
                )
            else:
                logger.info(
                    "execution request_id=%s status=ok",
                    context.request_id,
                )
        else:
            logger.error(
                "execution request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None