"""Model resolution stage.

Resolves the requested model to a provider instance before context
assembly, because ``context_window`` is needed later for token-budgeting.
"""

from __future__ import annotations

import logging

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.providers.router import ModelRouter

logger = logging.getLogger(__name__)


class ModelResolutionStage(PipelineStage):
    """Pipeline stage that resolves model → provider before context assembly.

    Reads the requested model from the pipeline request, falling back to
    ``settings.default_model``, then calls ``router.resolve(model)`` and
    stores the result on ``context.resolved_model``.

    On ``UnknownModelError``, returns a **failed** result (does not raise).
    """

    def __init__(self, router: ModelRouter) -> None:
        """Initialize with the model router.

        Args:
            router: The ModelRouter to use for resolution.
        """
        self._router = router

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "model_resolution"

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Resolve the model and store on context.

        Args:
            context: The pipeline context with request data.

        Returns:
            A success result with the resolved model stored on context,
            or a failed result if resolution fails.
        """
        # Read the requested model from the request, falling back to
        # settings.default_model.
        request_model = context.request.get("model")
        if not request_model:
            from packages.config import load_config

            settings = load_config()
            request_model = settings.get("gateway", {}).get("default_model", "default")

        try:
            resolved = self._router.resolve(request_model)
            # Store on typed field, not in metadata dict.
            context.resolved_model = resolved

            logger.info(
                "model_resolution request_id=%s model=%s provider=%s context_window=%s",
                context.request_id,
                resolved.definition.model,
                resolved.definition.provider,
                resolved.definition.context_window,
            )

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=resolved,
            )
        except Exception as exc:
            # UnknownModelError or any other — return a failed result.
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error=str(exc),
                exception=exc,
            )

    async def after(
        self, context: PipelineContext, result: PipelineStageResult
    ) -> PipelineStageResult | None:
        """Log resolution outcome.

        Args:
            context: The pipeline context.
            result: The result from this stage.

        Returns:
            ``None`` to keep the existing result.
        """
        if result.success:
            logger.info(
                "model_resolution request_id=%s model=%s status=ok",
                context.request_id,
                result.data.definition.model if result.data is not None else "?",
            )
        else:
            logger.error(
                "model_resolution request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None
