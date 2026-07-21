"""Pipeline stages.

Contains the built-in ProviderStage implementation.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.serializers.models import ProviderRequest

logger = logging.getLogger(__name__)


class ProviderStage(PipelineStage):
    """Pipeline stage that calls the already-resolved provider.

    Consumes the provider from ``context.resolved_model`` which was set
    by ``ModelResolutionStage``.  Does NOT know that routing exists —
    it never calls ``router.resolve()``, ``create_provider()``, or the
    registry.

    If ``context.resolved_model`` is ``None``, returns a failed result.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "provider"

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Call the already-resolved provider's chat method.

        Reads the provider from ``context.resolved_model`` and calls
        ``chat()`` with kwargs from the context.

        Args:
            context: The pipeline context with request data.

        Returns:
            A ``PipelineStageResult`` with the provider's response.
        """
        resolved = context.resolved_model
        if resolved is None:
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error="No resolved model found in context. ModelResolutionStage must run first.",
            )

        provider = resolved.provider
        model = resolved.definition.model
        backend_model = resolved.definition.backend_model or resolved.definition.model

        logger.info(
            "provider_stage request_id=%s provider=%s model=%s backend_model=%s",
            context.request_id,
            resolved.definition.provider,
            model,
            backend_model,
        )

        try:
            # Prefer the serialized ProviderRequest produced by the
            # RepositoryContextStage.  If no ProviderRequest is
            # available, fall back to the raw request dict.
            provider_request = context.get_metadata("provider_request")
            if isinstance(provider_request, ProviderRequest):
                kwargs = provider_request.to_dict()
            else:
                kwargs = context.request.copy()

            # Ensure stream is always forwarded (ProviderRequest does
            # not carry transport concerns).
            kwargs["stream"] = context.request.get("stream", False)

            # Override model with backend_model for the upstream call.
            kwargs["model"] = backend_model

            result = await provider.chat(**kwargs)
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=result,
            )
        except Exception as exc:
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error=str(exc),
                exception=exc,
            )

    async def after(
        self, context: PipelineContext, result: PipelineStageResult
    ) -> PipelineStageResult | None:
        """Log provider stage completion.

        Args:
            context: The pipeline context.
            result: The result from this stage.

        Returns:
            ``None`` to keep the existing result.
        """
        if result.success:
            logger.info(
                "provider_stage request_id=%s status=ok",
                context.request_id,
            )
        else:
            logger.error(
                "provider_stage request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None