"""Provider factory for creating provider instances."""

from packages.providers.base import Provider
from packages.providers.exceptions import UnknownProviderError
from packages.providers.registry import get_registry


def create_provider(name: str) -> Provider:
    """Create a provider instance by name.

    Raises:
        UnknownProviderError: If the provider is not registered.
    """
    registry = get_registry()
    if name not in registry:
        raise UnknownProviderError(f"Provider '{name}' is not registered")
    return registry[name]()
