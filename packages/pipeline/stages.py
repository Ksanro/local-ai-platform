"""Pipeline stages.

Contains concrete stage implementations. The only built-in stage is
``ProviderStage``, which resolves a provider and calls its ``chat()``
method. Future stages will include authentication, repository context,
memory, prompt optimization, and metrics.
"""

from __future__ import annotations

import logging
import time

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.exceptions import StageError
from packages.pipeline.response import PipelineStageResult
from packages.providers.factory import create_provider
from packages.providers.registry import has_provider

logger = logging.getLogger(__name__)


class ProviderStage(PipelineStage):
    """Pipeline stage that calls the configured provider.

    Resolves the provider by name, calls ``provider.chat()`` with the
    request payload, and returns the result. No other logic — just a
    thin wrapper so the provider call goes through the pipeline.

    Attributes:
        _provider_name: The provider name to use (from request).
    """

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "provider"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Validate that the provider is registered.

        Checks that the provider name (from context metadata) is
        registered before attempting to create it.

        Args:
            context: The pipeline context.

        Returns:
            A failure result if the provider is not registered, or
            ``None`` to proceed with ``execute()``.
        """
        provider_name = context.get_metadata("provider_name", "vllm")
        if not has_provider(provider_name):
            registered = ", ".join(sorted(self._get_registry_keys()))
            return PipelineStageResult(
                stage_name=self.name,
                success=False,
                error=f"Provider '{provider_name}' is not registered. Available: [{registered}]",
            )
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Call the provider's chat method.

        Resolves the provider, builds kwargs from context, and calls
        ``chat()``. Returns the response data on success.

        Args:
            context: The pipeline context with request data.

        Returns:
            A ``PipelineStageResult`` with the provider's response.

        Raises:
            StageError: If the provider call fails.
        """
        provider_name = context.get_metadata("provider_name", "vllm")
        model = context.get_metadata("model", "default")

        logger.info(
            "provider_stage request_id=%s provider=%s model=%s",
            context.request_id,
            provider_name,
            model,
        )

        try:
            provider = create_provider(provider_name)
            kwargs = context.request.copy()
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
            )

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        """Log provider stage completion.

        Args:
            context: The pipeline context.
            result: The result from this stage.
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

    @staticmethod
    def _get_registry_keys() -> list[str]:
        """Get registered provider names.

        Returns:
            A sorted list of registered provider names.
        """
        from packages.providers.registry import get_registry

        return sorted(get_registry().keys())
