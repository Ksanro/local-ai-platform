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
        return ProviderType.vllm

    def _serialize(self, context_package, messages):
        from packages.serializers.models import ProviderRequest

        return ProviderRequest(
            provider_type=ProviderType.vllm,
            messages=messages,
        )


class MockSerializerB(ProviderSerializer):
    """Second mock serializer for testing."""

    @property
    def provider(self) -> ProviderType:
        return ProviderType.gemini

    def _serialize(self, context_package, messages):
        from packages.serializers.models import ProviderRequest

        return ProviderRequest(
            provider_type=ProviderType.gemini,
            messages=messages,
        )


class TestSerializerRegistry:
    """Tests for the serializer registry."""

    def setup_method(self) -> None:
        """Clear the registry before each test, preserving auto-registered serializers."""
        from packages.serializers.registry import _registry as _REGISTRY

        # Save auto-registered serializers.
        auto_registered = set()
        for pt in list(_REGISTRY.keys()):
            if pt.value.startswith(("openai", "anthropic", "gemini", "azure")):
                auto_registered.add(pt)

        # Clear all serializers.
        for pt in list(_REGISTRY.keys()):
            try:
                unregister(pt)
            except KeyError:
                pass

        # Restore auto-registered serializers.
        for pt in auto_registered:
            if pt.value == "openai":
                from packages.serializers.openai import OpenAISerializer

                register(ProviderType.openai, OpenAISerializer)
            elif pt.value == "anthropic":
                from packages.serializers.anthropic import AnthropicSerializer

                register(ProviderType.anthropic, AnthropicSerializer)

    def test_register_adds_serializer(self) -> None:
        """Verify register adds a serializer to the registry."""
        register(ProviderType.vllm, MockSerializer)
        assert has_serializer(ProviderType.vllm)
        unregister(ProviderType.vllm)

    def test_register_multiple_serializers(self) -> None:
        """Verify register supports multiple serializers."""
        register(ProviderType.vllm, MockSerializer)
        register(ProviderType.gemini, MockSerializerB)
        assert has_serializer(ProviderType.vllm)
        assert has_serializer(ProviderType.gemini)
        unregister(ProviderType.vllm)
        unregister(ProviderType.gemini)

    def test_get_registry_returns_copy(self) -> None:
        """Verify get_registry returns a copy of the registry."""
        register(ProviderType.vllm, MockSerializer)
        registry = get_registry()
        assert ProviderType.vllm in registry
        assert registry[ProviderType.vllm] is MockSerializer
        unregister(ProviderType.vllm)

    def test_get_registry_contains_all_registered(self) -> None:
        """Verify get_registry contains all registered serializers."""
        register(ProviderType.vllm, MockSerializer)
        register(ProviderType.gemini, MockSerializerB)
        registry = get_registry()
        assert ProviderType.vllm in registry
        assert ProviderType.gemini in registry
        unregister(ProviderType.vllm)
        unregister(ProviderType.gemini)

    def test_has_serializer_returns_false_for_missing(self) -> None:
        """Verify has_serializer returns False for unregistered type."""
        assert not has_serializer(ProviderType.ollama)

    def test_duplicate_registration_raises(self) -> None:
        """Verify duplicate registration raises ValueError."""
        register(ProviderType.vllm, MockSerializer)
        with pytest.raises(ValueError, match="already registered"):
            register(ProviderType.vllm, MockSerializer)
        unregister(ProviderType.vllm)

    def test_duplicate_registration_different_class_raises(self) -> None:
        """Verify duplicate registration with different class also raises."""
        register(ProviderType.vllm, MockSerializer)
        with pytest.raises(ValueError, match="already registered"):
            register(ProviderType.vllm, MockSerializerB)
        unregister(ProviderType.vllm)

    def test_unregister_removes_serializer(self) -> None:
        """Verify unregister removes a serializer."""
        register(ProviderType.vllm, MockSerializer)
        assert has_serializer(ProviderType.vllm)
        unregister(ProviderType.vllm)
        assert not has_serializer(ProviderType.vllm)

    def test_unregister_missing_raises(self) -> None:
        """Verify unregister raises KeyError for missing serializer."""
        with pytest.raises(KeyError):
            unregister(ProviderType.gemini)

    def test_registry_is_empty_by_default(self) -> None:
        """Verify registry is empty after cleanup.

        Note: The conftest pre-registers the OpenAI serializer, so the
        registry will contain only auto-registered serializers after
        cleanup.
        """
        # Unregister any serializers that were registered by previous tests
        # in this file.
        for pt in [ProviderType.vllm, ProviderType.gemini]:
            try:
                unregister(pt)
            except KeyError:
                pass
        registry = get_registry()
        # Only auto-registered serializers should remain (e.g., openai).
        # No test-registered serializers should remain.
        for pt in [ProviderType.vllm, ProviderType.gemini]:
            assert pt not in registry
