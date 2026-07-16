"""Tests for the serializer registry.

Verifies registration, lookup, duplicate prevention, and cleanup.
"""

from __future__ import annotations

import pytest

from packages.serializers.base import ProviderSerializer
from packages.serializers.registry import (
    get_registry,
    has_serializer,
    register,
    unregister,
)
from packages.serializers.types import ProviderType


class MockSerializer(ProviderSerializer):
    """Mock serializer for testing."""

    @property
    def provider(self) -> ProviderType:
        return ProviderType.openai

    def _serialize(self, context_package, messages):
        from packages.serializers.models import ProviderRequest

        return ProviderRequest(
            provider_type=ProviderType.openai,
            messages=messages,
        )


class MockSerializerB(ProviderSerializer):
    """Second mock serializer for testing."""

    @property
    def provider(self) -> ProviderType:
        return ProviderType.anthropic

    def _serialize(self, context_package, messages):
        from packages.serializers.models import ProviderRequest

        return ProviderRequest(
            provider_type=ProviderType.anthropic,
            messages=messages,
        )


class TestSerializerRegistry:
    """Tests for the serializer registry."""

    def setup_method(self) -> None:
        """Clear the registry before each test."""
        # Clean up any previously registered serializers.
        for pt in list(get_registry().keys()):
            try:
                unregister(pt)
            except KeyError:
                pass

    def test_register_adds_serializer(self) -> None:
        """Verify register adds a serializer to the registry."""
        register(ProviderType.openai, MockSerializer)
        assert has_serializer(ProviderType.openai)

    def test_register_multiple_serializers(self) -> None:
        """Verify register supports multiple serializers."""
        register(ProviderType.openai, MockSerializer)
        register(ProviderType.anthropic, MockSerializerB)
        assert has_serializer(ProviderType.openai)
        assert has_serializer(ProviderType.anthropic)

    def test_get_registry_returns_copy(self) -> None:
        """Verify get_registry returns a copy of the registry."""
        register(ProviderType.openai, MockSerializer)
        registry = get_registry()
        assert ProviderType.openai in registry
        assert registry[ProviderType.openai] is MockSerializer

    def test_get_registry_contains_all_registered(self) -> None:
        """Verify get_registry contains all registered serializers."""
        register(ProviderType.openai, MockSerializer)
        register(ProviderType.anthropic, MockSerializerB)
        registry = get_registry()
        assert ProviderType.openai in registry
        assert ProviderType.anthropic in registry

    def test_has_serializer_returns_false_for_missing(self) -> None:
        """Verify has_serializer returns False for unregistered type."""
        assert not has_serializer(ProviderType.gemini)

    def test_duplicate_registration_raises(self) -> None:
        """Verify duplicate registration raises ValueError."""
        register(ProviderType.openai, MockSerializer)
        with pytest.raises(ValueError, match="already registered"):
            register(ProviderType.openai, MockSerializer)

    def test_duplicate_registration_different_class_raises(self) -> None:
        """Verify duplicate registration with different class also raises."""
        register(ProviderType.openai, MockSerializer)
        with pytest.raises(ValueError, match="already registered"):
            register(ProviderType.openai, MockSerializerB)

    def test_unregister_removes_serializer(self) -> None:
        """Verify unregister removes a serializer."""
        register(ProviderType.openai, MockSerializer)
        assert has_serializer(ProviderType.openai)
        unregister(ProviderType.openai)
        assert not has_serializer(ProviderType.openai)

    def test_unregister_missing_raises(self) -> None:
        """Verify unregister raises KeyError for missing serializer."""
        with pytest.raises(KeyError):
            unregister(ProviderType.gemini)

    def test_registry_is_empty_by_default(self) -> None:
        """Verify registry is empty after cleanup."""
        registry = get_registry()
        assert len(registry) == 0
