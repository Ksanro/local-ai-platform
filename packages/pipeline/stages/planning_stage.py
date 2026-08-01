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
from collections.abc import Mapping, Sequence

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.user_messages import select_task_texts, user_message_texts
from packages.planning.intent import Intent, IntentMatch
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
            context_intent = self._context_intent_override(context)
            context_intent_rules = self._context_intent_rules(context)
            intent_match = (
                IntentMatch(context_intent, "context_intent")
                if context_intent is not None
                else Intent.detect_match(messages, custom_rules=context_intent_rules)
            )
            context.set_metadata("planning_user_message_count", len(messages))
            context.set_metadata(
                "planning_last_user_message",
                messages[-1] if messages else "",
            )
            context.set_metadata("planning_matched_keyword", intent_match.keyword)
            if context_intent is not None:
                context.set_metadata("planning_context_intent_override", context_intent)

            # Run the planner.
            plan = self._planner.build(
                user_messages=messages,
                intent_override=intent_match.intent,
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
        return select_task_texts(user_message_texts(messages))

    @staticmethod
    def _context_intent_override(context: PipelineContext) -> str | None:
        """Return a validated explicit context-intent override, if present."""
        raw_intent = context.get_metadata("context_intent")
        if not isinstance(raw_intent, str):
            return None

        intent = raw_intent.strip().upper()
        if intent in Intent._ALL:
            return intent

        context.set_metadata("planning_context_intent_ignored", raw_intent)
        return None

    @staticmethod
    def _context_intent_rules(
        context: PipelineContext,
    ) -> Mapping[str, Sequence[str]] | None:
        """Return user-configured context intent rules, if present."""
        raw_rules = context.get_metadata("context_intent_rules", {})
        if isinstance(raw_rules, Mapping):
            return raw_rules
        return None
