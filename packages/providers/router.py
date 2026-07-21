"""Model router — instance ownership and resolution.

Owns provider instances and consults ``ModelRegistry`` for configuration.
"""

from __future__ import annotations

import logging
from typing import Any

from packages.providers.factory import create_provider
from packages.providers.models import ModelDefinition, ResolvedModel
from packages.providers.registry_models import ModelRegistry

logger = logging.getLogger(__name__)


class ModelRouter:
    """Owns provider instances; consults ``ModelRegistry`` for configuration.

    Creates one provider instance per unique ``(provider, base_url, api_key, timeout)``
    tuple at startup. Two models on the same backend share one instance.

    Attributes:
        registry: The model registry providing configuration.
        _providers: Dict of backend key -> provider instance.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        """Initialize with a ModelRegistry.

        Creates one provider instance per unique backend tuple at startup.

        Args:
            registry: The model registry providing configuration.
        """
        self.registry = registry
        self._providers: dict[str, Any] = {}
        self._create_providers()

    def _create_providers(self) -> None:
        """Create provider instances for all unique backend tuples."""
        # Collect unique (provider_name, base_url, api_key, timeout) tuples
        backend_keys: dict[str, dict[str, Any]] = {}
        for definition in self.registry.definitions:
            key = (
                definition.provider,
                definition.base_url,
                definition.api_key,
                definition.timeout,
            )
            key_str = f"{key[0]}|{key[1]}|{str(key[2])}|{str(key[3])}"
            if key_str not in backend_keys:
                backend_keys[key_str] = {
                    "provider_name": key[0],
                    "base_url": key[1],
                    "api_key": key[2],
                    "timeout": key[3],
                }

        # Create one provider per unique backend
        for key_str, config in backend_keys.items():
            provider = create_provider(
                config["provider_name"],
                base_url=config["base_url"],
                api_key=config["api_key"],
                timeout=config["timeout"],
            )
            self._providers[key_str] = provider

    def resolve(self, model: str) -> ResolvedModel:
        """Resolve a model string to configuration and provider.

        Args:
            model: The model name to resolve.

        Returns:
            A ResolvedModel with definition and provider.

        Raises:
            UnknownModelError: If the model is not found.
        """
        definition = self.registry.get(model)
        # Find the provider for this definition's backend
        config_key = (
            definition.provider,
            definition.base_url,
            definition.api_key,
            definition.timeout,
        )
        config_str = f"{config_key[0]}|{config_key[1]}|{str(config_key[2])}|{str(config_key[3])}"
        provider = self._providers[config_str]
        return ResolvedModel(definition=definition, provider=provider)

    def available_models(self) -> list[str]:
        """Get a sorted list of available model names.

        Returns:
            Sorted list of model names from the registry.
        """
        return self.registry.available_models()

    async def close_all(self) -> None:
        """Close all owned provider instances exactly once."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()
        self._providers.clear()


class FallbackModelRouter:
    """Single-provider fallback router for empty models_config.

    Creates a single provider from default_provider + env config,
    and resolves any model string to it with a synthesized ModelDefinition.
    """

    def __init__(self, default_provider_name: str) -> None:
        """Initialize with a default provider name.

        Args:
            default_provider_name: The provider name to use for all requests.
        """
        self._default_provider_name = default_provider_name
        self._provider: Any | None = None
        self._model_definitions: dict[str, ModelDefinition] = {}

    def _ensure_provider(self) -> Any:
        """Lazy-create the single provider instance."""
        if self._provider is None:
            self._provider = create_provider(self._default_provider_name)
        return self._provider

    def resolve(self, model: str) -> ResolvedModel:
        """Resolve any model string to the single provider.

        Args:
            model: The model name (any string is accepted in fallback mode).

        Returns:
            A ResolvedModel with synthesized ModelDefinition and the single provider.
        """
        provider = self._ensure_provider()

        # Synthesize ModelDefinition for this model
        if model not in self._model_definitions:
            self._model_definitions[model] = ModelDefinition(
                model=model,
                provider=self._default_provider_name,
                base_url="",  # Fallback doesn't need base_url for routing
            )

        return ResolvedModel(definition=self._model_definitions[model], provider=provider)

    def available_models(self) -> list[str]:
        """Return empty list — fallback mode doesn't restrict model names."""
        return []

    async def close_all(self) -> None:
        """Close the single provider if it exists."""
        if self._provider is not None:
            if hasattr(self._provider, "close"):
                await self._provider.close()
            self._provider = None
