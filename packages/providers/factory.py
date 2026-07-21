"""Provider factory for creating provider instances.

Provides a ``create_provider`` function that looks up a provider
class by name in the registry and instantiates it. Raises
``UnknownProviderError`` for unregistered provider names.
"""

from __future__ import annotations

from typing import Any

from packages.providers.base import Provider
from packages.providers.exceptions import UnknownProviderError
from packages.providers.registry import get_registry


def create_provider(name: str, **kwargs: Any) -> Provider:
    """Create a provider instance by name.

    Looks up the provider class in the global registry and
    instantiates it with optional configuration overrides.
    The provider must have been registered
    via ``register()`` before this call.

    Args:
        name: The registered name of the provider (e.g. ``"vllm"``).
        **kwargs: Optional configuration overrides passed to the provider
            constructor (e.g. ``base_url``, ``api_key``, ``timeout``).

    Returns:
        A new instance of the requested provider class.

    Raises:
        UnknownProviderError: If the provider name is not registered.
    """
    registry = get_registry()
    if name not in registry:
        raise UnknownProviderError(f"Provider '{name}' is not registered")
    return registry[name](**kwargs)
