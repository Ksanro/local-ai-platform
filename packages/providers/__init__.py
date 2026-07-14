"""Provider abstraction package."""

from packages.providers.base import Provider
from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderResponseError,
    UnknownProviderError,
)
from packages.providers.factory import create_provider
from packages.providers.registry import register


def _load_providers() -> None:
    """Import provider modules to trigger auto-registration.

    Each provider module (e.g. ``packages.providers.vllm``) registers
    itself in the global registry as a side effect of being imported.
    Call this function once at application startup to ensure all
    available providers are registered.
    """
    import packages.providers.vllm  # noqa: F401


__all__ = [
    "Provider",
    "create_provider",
    "register",
    "ProviderError",
    "UnknownProviderError",
    "ProviderConnectionError",
    "ProviderAuthenticationError",
    "ProviderResponseError",
]
