"""Provider registration registry."""

from typing import Type

from packages.providers.base import Provider

_registry: dict[str, Type[Provider]] = {}


def register(name: str, provider_class: Type[Provider]) -> None:
    """Register a provider class by name."""
    _registry[name] = provider_class


def get_registry() -> dict[str, Type[Provider]]:
    """Return the current provider registry."""
    return dict(_registry)


def has_provider(name: str) -> bool:
    """Check if a provider is registered."""
    return name in _registry
