"""Provider factory for creating provider instances.

Provides a ``create_provider`` function that looks up a provider
class by name in the registry and instantiates it. Raises
``UnknownProviderError`` for unregistered provider names.
"""

from packages.providers.base import Provider
from packages.providers.exceptions import UnknownProviderError
from packages.providers.registry import get_registry


def create_provider(name: str) -> Provider:
    """Create a provider instance by name.

    Looks up the provider class in the global registry and
    instantiates it. The provider must have been registered
    via ``register()`` before this call.

    Args:
        name: The registered name of the provider (e.g. ``"vllm"``).

    Returns:
        A new instance of the requested provider class.

    Raises:
        UnknownProviderError: If the provider name is not registered.
    """
    registry = get_registry()
    if name not in registry:
        raise UnknownProviderError(f"Provider '{name}' is not registered")
    return registry[name]()
