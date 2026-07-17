"""Provider registry fixture for benchmark testing."""

from __future__ import annotations

from typing import Any


class ProviderRegistry:
    """Registry for provider classes.

    Provides a global singleton registry that maps provider names
    to their implementation classes.

    Attributes:
        _providers: Mapping of provider names to classes.
        _defaults: Mapping of provider names to default configs.
    """

    _instance: ProviderRegistry | None = None

    def __init__(self) -> None:
        """Initialize the registry with empty provider maps."""
        self._providers: dict[str, type] = {}
        self._defaults: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_registry(cls) -> ProviderRegistry:
        """Get the singleton registry instance.

        Returns:
            The singleton ProviderRegistry instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, provider_class: type) -> None:
        """Register a provider class with the given name.

        Args:
            name: The provider name.
            provider_class: The provider class to register.

        Raises:
            ValueError: If the name is already registered.
        """
        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered")
        self._providers[name] = provider_class

    def get(self, name: str) -> type | None:
        """Get a registered provider class by name.

        Args:
            name: The provider name.

        Returns:
            The provider class, or None if not found.
        """
        return self._providers.get(name)

    def get_default_config(self, name: str) -> dict[str, Any] | None:
        """Get the default configuration for a provider.

        Args:
            name: The provider name.

        Returns:
            The default config dictionary, or None if not set.
        """
        return self._defaults.get(name)

    def set_default_config(
        self,
        name: str,
        config: dict[str, Any],
    ) -> None:
        """Set default configuration for a provider.

        Args:
            name: The provider name.
            config: The default configuration dictionary.
        """
        self._defaults[name] = config

    def list_providers(self) -> list[str]:
        """List all registered provider names.

        Returns:
            Sorted list of provider names.
        """
        return sorted(self._providers.keys())

    def unregister(self, name: str) -> None:
        """Unregister a provider by name.

        Args:
            name: The provider name to unregister.

        Raises:
            KeyError: If the name is not registered.
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' is not registered")
        del self._providers[name]
        self._defaults.pop(name, None)