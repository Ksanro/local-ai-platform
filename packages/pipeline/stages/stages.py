"""Pipeline stages.

Contains the built-in ProviderStage implementation.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.normalized import NormalizedRequest
from packages.pipeline.result import PipelineStageResult

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

        Reads the normalized request from ``context.normalized_request``
        and calls ``chat()`` with a single, deterministic provider payload
        produced by ``NormalizedRequest.to_provider_payload()``.

        There is **no dual-path** logic.  The provider payload is built
        once from the normalized request.

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
        # Use the backend model from the resolved definition, or override
        # with context.backend_model if explicitly set.
        # Only accept real strings — MagicMock children would pass
        # `is not None` but would corrupt the payload.
        _dbm = resolved.definition.backend_model
        backend_model: str | None = (
            _dbm if isinstance(_dbm, str) else None
        )
        if backend_model is None:
            backend_model = model

        logger.info(
            "provider_stage request_id=%s provider=%s model=%s backend_model=%s",
            context.request_id,
            resolved.definition.provider,
            model,
            backend_model,
        )

        try:
            # Single-path: build provider payload from the normalized request.
            nr = context.normalized_request
            if isinstance(nr, NormalizedRequest):
                kwargs = nr.to_provider_payload(backend_model)
            else:
                # Fallback for tests that don't set normalized_request.
                # Build payload from context.request + explicit overrides.
                kwargs = dict(context.request)
                # Override model with backend_model.
                kwargs["model"] = backend_model
                # Ensure stream is forwarded.
                kwargs["stream"] = kwargs.get("stream", False)
                if kwargs["stream"]:
                    kwargs["stream_options"] = {"include_usage": True}

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
