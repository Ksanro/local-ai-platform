"""Repository context pipeline stage.

Assembles repository context for the request by orchestrating the
Context Builder pipeline (Builder -> Ranking -> Budget -> Composer)
and attaching the resulting ContextPackage to the PipelineContext.

Architecture
------------

PipelineContext
       |
       v
RepositoryContextStage
       |
       |-- ContextBuilder   (enumerate & rank symbols)
       |-- RankingEngine    (integrated inside Builder)
       |-- ContextBudget    (integrated inside Builder)
       +-- ContextComposer  (assembles structured package)
       |
       v
PipelineContext.context_package

The stage is provider-agnostic. It never performs inference.

Constraints
-----------

The stage

must not

- call providers
- inspect provider configuration
- access Gateway internals

Serializes only into ``ProviderRequest`` -- never raw JSON or HTTP payloads.

It orchestrates existing Context components only.
"""

from __future__ import annotations

import logging
import time

from packages.context.builder import ContextBuilder
from packages.context.composer import ContextComposer
from packages.context.context_package import ContextPackage
from packages.context.models import ContextQuery
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.openai import OpenAISerializer  # noqa: F401 - auto-registers
from packages.serializers.types import ProviderType

logger = logging.getLogger(__name__)


class RepositoryContextStage(PipelineStage):
    """Pipeline stage that assembles repository context.

    Orchestrates the full context-building pipeline and attaches
    the resulting ContextPackage to the PipelineContext.

    Attributes:
        _index: Read-only repository index for symbol enumeration.
            May be ``None`` if repository scanning is not configured;
            the stage handles this gracefully.
    """

    def __init__(self, index: RepositoryIndex | None = None) -> None:
        """Initialize with an optional repository index.

        Args:
            index: A ``RepositoryIndex`` providing access to
                repository symbols, or ``None`` to disable context
                assembly.
        """
        self._index = index

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "repository_context"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if repository context is enabled.

        Reads the ``context_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled, records a no-op result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if context is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        context_enabled = context.get_metadata("context_enabled", True)
        if not context_enabled:
            context.context_package = None
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={"enabled": False},
            )
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Assemble repository context and attach to context.

        Executes the full context-building pipeline:

        1. Build candidates from the repository index.
        2. Rank candidates against the user query.
        3. Estimate token budget.
        4. Compose the final ContextPackage.

        Stores the ContextPackage in ``context.context_package``.

        On any exception, logs the error, leaves ``context_package``
        as ``None``, and returns a successful result so the pipeline
        continues to the provider stage.

        Args:
            context: The pipeline context with request data.

        Returns:
            A ``PipelineStageResult`` with the ContextPackage on
            success, or a successful result with ``None`` data on
            failure (graceful degradation).
        """
        start_time = time.perf_counter()
        request_id = context.request_id
        context_enabled = context.get_metadata("context_enabled", True)

        try:
            # If no index is available, skip context assembly.
            if self._index is None:
                context.context_package = None
                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data=None,
                )

            # Extract query text from the request.
            # Messages are stored in context.request as provider kwargs.
            query_text = self._extract_query(context)

            # Build context from the repository index.
            # Read the ContextPlan from metadata -- it is the single source
            # of truth for retrieval configuration.  When no plan is present
            # (planning disabled or not yet run), fall back to safe defaults.
            plan = context.get_metadata("context_plan")

            if plan is not None:
                query = ContextQuery(
                    text=query_text,
                    max_symbols=20,
                    max_modules=10,
                    max_tokens=4096,
                    maximum_depth=plan.maximum_depth,
                    relationship_expansion=plan.relationship_expansion,
                )
            else:
                query = ContextQuery(
                    text=query_text,
                    max_symbols=20,
                    max_modules=10,
                    max_tokens=4096,
                )

            builder = ContextBuilder(self._index)
            context_result = builder.build(query)

            # Check if ranking returned no relevant symbols.
            candidates = getattr(context_result, "candidates", [])
            if not candidates:
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "repository_context request_id=%s context_enabled=%s "
                    "context_status=empty reason=no_relevant_symbols "
                    "duration_ms=%.1f",
                    request_id,
                    context_enabled,
                    elapsed_ms,
                )

                # Leave context_package as None -- proceed with unmodified messages.
                context.context_package = None

                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data=None,
                )

            # Compose the final package.
            composer = ContextComposer()
            package = composer.compose(context_result)

            # Serialize the context package into a ProviderRequest.
            # The serializer translates platform models into the
            # provider-specific request format that the Provider
            # layer consumes.
            self._serialize(context, package)

            # Attach the context package to the pipeline context so that
            # downstream stages (and tests) can inspect it directly.
            context.context_package = package

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            symbols_selected = len(package.supporting_symbols)
            modules_selected = len(package.related_modules)
            estimated_tokens = package.estimated_tokens

            logger.info(
                "repository_context request_id=%s context_enabled=%s "
                "context_status=ok symbols_selected=%d modules_selected=%d "
                "estimated_tokens=%d duration_ms=%.1f",
                request_id,
                context_enabled,
                symbols_selected,
                modules_selected,
                estimated_tokens,
                elapsed_ms,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=package,
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "repository_context request_id=%s context_enabled=%s "
                "error=%s duration_ms=%.1f",
                request_id,
                context_enabled,
                exc,
                elapsed_ms,
            )

            # Leave context_package as None -- graceful degradation.
            context.context_package = None

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
            has_package = context.context_package is not None
            logger.info(
                "repository_context request_id=%s status=ok has_package=%s",
                context.request_id,
                has_package,
            )
        else:
            logger.error(
                "repository_context request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None

    @staticmethod
    def _extract_query(context: PipelineContext) -> str:
        """Extract query text from the pipeline context.

        Reads the last user message from the request messages.

        Args:
            context: The pipeline context.

        Returns:
            The query text, or empty string if not found.
        """
        request = context.request
        if not isinstance(request, dict):
            return ""

        messages = request.get("messages", [])
        if not messages:
            return ""

        # Find the last user message.
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    return content.strip()

        # Fallback: join all user message contents.
        user_contents = [
            msg.get("content", "")
            for msg in messages
            if isinstance(msg, dict) and msg.get("role") == "user"
        ]
        return " ".join(user_contents).strip() if user_contents else ""

    @staticmethod
    def _serialize(
        context: PipelineContext,
        context_package: ContextPackage,
    ) -> None:
        """Serialize the context package into a ProviderRequest.

        Looks up the OpenAI serializer via the factory, produces a
        ``ProviderRequest``, and attaches it to the pipeline context
        so downstream stages can consume it.

        Args:
            context: The pipeline context with request data.
            context_package: The assembled context package to serialize.
        """
        request = context.request
        if not isinstance(request, dict):
            return

        messages = request.get("messages", [])
        if not messages:
            return

        # Extract model from the request.
        model = request.get("model", "default")

        try:
            serializer = SerializerFactory.create(ProviderType.openai)
            provider_request = serializer.serialize(
                context_package=context_package,
                messages=messages,
                model=model,
            )
            context.set_metadata("provider_request", provider_request)
        except Exception as exc:
            logger.warning(
                "serialization request_id=%s error=%s",
                context.request_id,
                exc,
            )
            # Leave provider_request unset -- graceful degradation.
