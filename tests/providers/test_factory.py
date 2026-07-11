"""Tests for the provider factory."""

import pytest

from packages.providers.base import Provider
from packages.providers.exceptions import UnknownProviderError
from packages.providers.factory import create_provider
from packages.providers.registry import register


class MockProvider(Provider):
    """Mock provider for testing."""

    async def health(self) -> dict[str, str]:
        return {"status": "ok"}

    async def chat(self, **kwargs) -> dict[str, list[str]]:
        return {"choices": []}

    async def models(self) -> list[str]:
        return []


def test_create_provider_returns_registered_instance() -> None:
    """Verify create_provider returns an instance of the registered provider."""
    register("mock", MockProvider)
    provider = create_provider("mock")
    assert isinstance(provider, Provider)


def test_create_provider_raises_for_unknown() -> None:
    """Verify create_provider raises UnknownProviderError for unregistered name."""
    with pytest.raises(UnknownProviderError):
        create_provider("unknown")


def test_create_provider_raises_after_removal() -> None:
    """Verify create_provider raises UnknownProviderError after unregister."""
    register("mock2", MockProvider)
    provider = create_provider("mock2")
    assert isinstance(provider, Provider)
