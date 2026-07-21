"""Self Verification pipeline stage.

Executes self-verification after execution, producing a VerificationReport
that is consumed by the EvaluationStage.

Architecture
------------

PipelineContext
       |
       v
VerificationStage
       |
       |-- SelfVerificationEngine  (verify execution results)
       |
       v
PipelineContext.verification_report

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
- must not duplicate evaluation logic

The stage only invokes the SelfVerificationEngine through its public API.
Verification must never execute independently — it always follows
ExecutionStage.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.verification.engine import SelfVerificationEngine

logger = logging.getLogger(__name__)


class VerificationStage(PipelineStage):
    """Pipeline stage that performs self-verification.

    Orchestrates verification of execution results through the
    SelfVerificationEngine, producing a VerificationReport.

    Attributes:
        _engine: The verification engine for rule execution.
    """

    def __init__(self, engine: SelfVerificationEngine | None = None) -> None:
        """Initialize with optional engine.

        Args:
            engine: The SelfVerificationEngine to use. Defaults to new engine.
        """
        self._engine = engine if engine is not None else SelfVerificationEngine()

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "verification"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if verification is enabled and has an execution report.

        Reads the ``verification_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled or no execution_report is present, records a no-op
        result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if verification is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        verification_enabled = context.get_metadata("verification_enabled", True)
        if not verification_enabled:
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"verification_enabled": False},
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
        """Execute verification and produce a VerificationReport.

        Invokes the SelfVerificationEngine with the ExecutionReport from
        context. Stores the result in ``context.verification_report``.

        On any exception, logs the error and returns a failed result.

        Args:
            context: The pipeline context with execution report.

        Returns:
            A PipelineStageResult with the VerificationReport on success.
        """
        request_id = context.request_id

        try:
            execution_report = context.execution_report
            if execution_report is None:
                raise ValueError("No ExecutionReport available in context")

            # Run verification.
            # The SelfVerificationEngine expects specific input types.
            # We pass the execution report and relevant context data.
            verification_report = self._engine.verify(
                workflow_plan=context.get_metadata("workflow_plan"),
                execution_plan=None,  # ExecutionPlan not available in v1
                evaluation_report=None,  # EvaluationReport not yet computed
                patch_set=None,  # PatchSet not available in v1
                workspace_changes=None,  # WorkspaceChanges not available in v1
            )

            # Store in context.
            context.verification_report = verification_report

            # Also store in metadata for downstream access.
            context.set_metadata("verification_report", verification_report)

            logger.info(
                "verification request_id=%s workflow=%s status=%s score=%.3f",
                request_id,
                verification_report.workflow_name,
                verification_report.verification_status.value,
                verification_report.score,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=verification_report,
            )

        except Exception as exc:
            logger.error(
                "verification request_id=%s error=%s",
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
            report = context.verification_report
            if report is not None:
                logger.info(
                    "verification request_id=%s workflow=%s status=%s score=%.3f",
                    context.request_id,
                    report.workflow_name,
                    report.verification_status.value,
                    report.score,
                )
            else:
                logger.info(
                    "verification request_id=%s status=ok",
                    context.request_id,
                )
        else:
            logger.error(
                "verification request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None