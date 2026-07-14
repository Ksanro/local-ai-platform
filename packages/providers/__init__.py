"""Provider abstraction package."""

# Import provider modules to trigger auto-registration at import time.
import packages.providers.vllm  # noqa: F401

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
