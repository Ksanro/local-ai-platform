"""Provider registration registry.

Maintains a global mapping of provider names to provider classes.
Providers are registered automatically when their module is imported
(e.g. ``packages.providers.vllm`` registers ``"vllm"`` at import time).
"""

from typing import Type

from packages.providers.base import Provider

_registry: dict[str, Type[Provider]] = {}


def register(name: str, provider_class: Type[Provider]) -> None:
    """Register a provider class by name.

    Adds the provider class to the global registry so it can be
    looked up by name via ``create_provider()``.

    Args:
        name: Unique identifier for the provider (e.g. ``"vllm"``).
        provider_class: The provider class to register. Must inherit
            from ``Provider``.
    """
    _registry[name] = provider_class


def get_registry() -> dict[str, Type[Provider]]:
    """Return the current provider registry.

    Returns a shallow copy of the registry dict to prevent
    external mutation.

    Returns:
        A dict mapping provider names to their classes.
    """
    return dict(_registry)


def has_provider(name: str) -> bool:
    """Check if a provider is registered.

    Args:
        name: The provider name to look up.

    Returns:
        ``True`` if the provider is registered, ``False`` otherwise.
    """
    return name in _registry
