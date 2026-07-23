"""Planning pipeline stage.

Integrates the ContextPlanner as a pipeline stage. This stage is
inserted before RepositoryContextStage in the pipeline.

Architecture
------------

PipelineContext
    ↓
PlanningStage
    ↓
    Produces: ContextPlan → stored in metadata["context_plan"]
    ↓
RepositoryContextStage (consumes ContextPlan)
    ↓
SerializerStage

Constraints
-----------

The stage
- must not access providers
- must not parse source files
- must not modify RepositoryIndex
- must not modify ContextBuilder

The stage only produces a ContextPlan and stores it in metadata.

Single source of truth
----------------------

ContextPlan is the single source of truth for retrieval configuration.
Components such as RepositoryContextStage, RankingEngine, BudgetEstimator,
and Serializer must consume the ContextPlan rather than introducing
independent decision logic.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.planning.planner import ContextPlanner

logger = logging.getLogger(__name__)


class PlanningStage(PipelineStage):
    """Pipeline stage that runs the context planner.

    Orchestrates intent detection and rule matching, then stores
    the resulting ContextPlan in PipelineContext.metadata["context_plan"].

    Attributes:
        _planner: The ContextPlanner instance to use.
    """

    def __init__(self, planner: ContextPlanner | None = None) -> None:
        """Initialize with an optional planner.

        Args:
            planner: The ContextPlanner to use. Defaults to ContextPlanner().
        """
        self._planner = planner if planner is not None else ContextPlanner()

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "planning"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if planning is enabled.

        Reads the ``planning_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled, records a no-op result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if planning is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        planning_enabled = context.get_metadata("planning_enabled", True)
        if not planning_enabled:
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"planning_enabled": False},
            )
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Run the context planner.

        Extracts user messages from the request, runs the planner,
        and stores the resulting ContextPlan in metadata.

        On any exception, logs the error and returns a successful
        result so the pipeline continues gracefully.

        Args:
            context: The pipeline context with request data.

        Returns:
            A PipelineStageResult with the ContextPlan on success.
        """
        try:
            # Extract user messages from the request.
            messages = self._extract_messages(context)

            # Run the planner.
            plan = self._planner.build(
                user_messages=messages,
            )

            # Store in metadata for downstream stages.
            context.set_metadata("context_plan", plan)

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=plan,
            )

        except Exception as exc:
            logger.error(
                "planning request_id=%s error=%s",
                context.request_id,
                exc,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=None,
                error=str(exc),
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
            plan = context.get_metadata("context_plan")
            if plan is not None:
                logger.info(
                    "planning request_id=%s intent=%s profile=%s",
                    context.request_id,
                    plan.intent,
                    plan.ranking_profile,
                )
            else:
                logger.info(
                    "planning request_id=%s status=ok",
                    context.request_id,
                )
        else:
            logger.error(
                "planning request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None

    @staticmethod
    def _extract_messages(context: PipelineContext) -> list[str]:
        """Extract user messages from the pipeline context.

        Reads the ``messages`` field from the request and returns
        only user-role messages.

        Args:
            context: The pipeline context.

        Returns:
            List of user message strings.
        """
        request = context.request
        if not isinstance(request, dict):
            return []

        messages = request.get("messages", [])
        if not messages:
            return []

        # Extract only user messages.
        user_messages: list[str] = []
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    user_messages.append(content.strip())

        return user_messages
