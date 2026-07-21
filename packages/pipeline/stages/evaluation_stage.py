"""Evaluation pipeline stage.

Executes evaluation after self-verification, producing an EvaluationReport
that is the final quality artifact for the engineering execution.

Architecture
------------

PipelineContext
       |
       v
EvaluationStage
       |
       |-- WorkflowEvaluator        (evaluate execution results)
       |
       v
PipelineContext.evaluation_report

The stage is an orchestration layer only. It never edits code, invokes
providers, or parses repositories.

Constraints
-----------

The stage
- must not edit files
- must not generate patches
- must not invoke providers
- must not inspect repositories
- must not execute shell commands
- must not duplicate verification logic

The stage only invokes the WorkflowEvaluator through its public API.
Evaluation must never execute independently — it always follows
VerificationStage.
"""

from __future__ import annotations

import logging

from packages.evaluation.evaluator import WorkflowEvaluator
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult

logger = logging.getLogger(__name__)


class EvaluationStage(PipelineStage):
    """Pipeline stage that performs evaluation.

    Orchestrates evaluation of execution results through the
    WorkflowEvaluator, producing an EvaluationReport.

    Attributes:
        _evaluator: The evaluation engine for metric computation.
    """

    def __init__(self, evaluator: WorkflowEvaluator | None = None) -> None:
        """Initialize with optional evaluator.

        Args:
            evaluator: The WorkflowEvaluator to use. Defaults to new evaluator.
        """
        self._evaluator = evaluator if evaluator is not None else WorkflowEvaluator()

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "evaluation"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if evaluation is enabled and has required reports.

        Reads the ``evaluation_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled or no execution_report is present, records a no-op
        result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if evaluation is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        evaluation_enabled = context.get_metadata("evaluation_enabled", True)
        if not evaluation_enabled:
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"evaluation_enabled": False},
            )

        # Check if we have an execution report.
        if context.execution_report is None:
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error="No ExecutionReport available in context",
            )

        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Execute evaluation and produce an EvaluationReport.

        Invokes the WorkflowEvaluator with the ExecutionReport and
        VerificationReport from context. Stores the result in
        ``context.evaluation_report``.

        On any exception, logs the error and returns a failed result.

        Args:
            context: The pipeline context with execution and verification reports.

        Returns:
            A PipelineStageResult with the EvaluationReport on success.
        """
        request_id = context.request_id

        try:
            execution_report = context.execution_report
            if execution_report is None:
                raise ValueError("No ExecutionReport available in context")

            # Get optional verification report.
            verification_report = context.verification_report

            # Run evaluation.
            # The WorkflowEvaluator expects specific input types.
            # We pass the execution report and relevant context data.
            evaluation_report = self._evaluator.evaluate(
                workflow_plan=context.get_metadata("workflow_plan"),
                execution_report=execution_report,
                capability_result=None,  # CapabilityResult not available in v1
                task_plan=None,  # TaskPlan not directly available
                provider_response=None,  # ProviderResponse not available yet
            )

            # Store in context.
            context.evaluation_report = evaluation_report

            # Also store in metadata for downstream access.
            context.set_metadata("evaluation_report", evaluation_report)

            logger.info(
                "evaluation request_id=%s workflow=%s overall_score=%.3f",
                request_id,
                evaluation_report.workflow_name,
                evaluation_report.overall_score,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=evaluation_report,
            )

        except Exception as exc:
            logger.error(
                "evaluation request_id=%s error=%s",
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
            report = context.evaluation_report
            if report is not None:
                logger.info(
                    "evaluation request_id=%s workflow=%s overall_score=%.3f",
                    context.request_id,
                    report.workflow_name,
                    report.overall_score,
                )
            else:
                logger.info(
                    "evaluation request_id=%s status=ok",
                    context.request_id,
                )
        else:
            logger.error(
                "evaluation request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None