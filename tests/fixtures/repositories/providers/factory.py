"""Provider factory fixture for benchmark testing."""

from __future__ import annotations

from typing import Any

from tests.fixtures.repositories.providers.base import ProviderBase
from tests.fixtures.repositories.providers.registry import ProviderRegistry


class ProviderFactory:
    """Factory for creating provider instances.

    Looks up provider classes in the registry and instantiates them.
    The factory is stateless — it creates fresh instances on each call.

    Attributes:
        _registry: The provider registry used for lookups.
    """

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        """Initialize the factory.

        Args:
            registry: Optional custom registry. Defaults to the global registry.
        """
        self._registry = registry or ProviderRegistry.get_registry()

    def create(self, provider_name: str, **kwargs: Any) -> ProviderBase:
        """Create a provider instance by name.

        Looks up the provider class in the registry and
        instantiates it with the given arguments.

        Args:
            provider_name: The registered provider name.
            **kwargs: Arguments to pass to the provider constructor.

        Returns:
            A new instance of the requested provider.

        Raises:
            KeyError: If the provider name is not registered.
        """
        provider_class = self._registry.get(provider_name)
        if provider_class is None:
            raise KeyError(
                f"Provider '{provider_name}' is not registered. "
                f"Available providers: {list(self._registry._providers.keys())}"
            )
        return provider_class(**kwargs)

    def register(self, name: str, provider_class: type[ProviderBase]) -> None:
        """Register a provider class with the factory.

        Args:
            name: The provider name to register.
            provider_class: The provider class to register.
        """
        self._registry.register(name, provider_class)

    def _resolve_config(self, provider_name: str, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve configuration for a provider.

        Merges global defaults with provider-specific settings.

        Args:
            provider_name: The provider name.
            config: The configuration to resolve.

        Returns:
            The resolved configuration dictionary.
        """
        defaults = self._registry.get_default_config(provider_name)
        if defaults:
            resolved = {**defaults, **config}
        else:
            resolved = config
        return resolved