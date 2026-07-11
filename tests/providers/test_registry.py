"""Tests for the provider registry."""

from packages.providers.base import Provider
from packages.providers.registry import get_registry, has_provider, register


class MockProviderA(Provider):
    """Mock provider A for testing."""

    async def health(self) -> dict[str, str]:
        return {"status": "ok"}

    async def chat(self, **kwargs) -> dict[str, list[str]]:
        return {"choices": []}

    async def models(self) -> list[str]:
        return []


class MockProviderB(Provider):
    """Mock provider B for testing."""

    async def health(self) -> dict[str, str]:
        return {"status": "ok"}

    async def chat(self, **kwargs) -> dict[str, list[str]]:
        return {"choices": []}

    async def models(self) -> list[str]:
        return []


def test_register_adds_provider_to_registry() -> None:
    """Verify register adds a provider to the registry."""
    register("provider_a", MockProviderA)
    assert has_provider("provider_a")


def test_register_multiple_providers() -> None:
    """Verify register supports multiple providers."""
    register("provider_a", MockProviderA)
    register("provider_b", MockProviderB)
    assert has_provider("provider_a")
    assert has_provider("provider_b")


def test_get_registry_returns_copy() -> None:
    """Verify get_registry returns a copy of the registry."""
    register("provider_a", MockProviderA)
    registry = get_registry()
    assert "provider_a" in registry
    assert registry["provider_a"] is MockProviderA


def test_get_registry_contains_all_registered() -> None:
    """Verify get_registry contains all registered providers."""
    register("provider_a", MockProviderA)
    register("provider_b", MockProviderB)
    registry = get_registry()
    assert "provider_a" in registry
    assert "provider_b" in registry


def test_has_provider_returns_false_for_missing() -> None:
    """Verify has_provider returns False for unregistered name."""
    assert not has_provider("missing")
