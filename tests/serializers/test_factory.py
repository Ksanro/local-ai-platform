"""Tests for the serializer factory.

Verifies creation, lookup, error handling, and factory behavior.
"""

from __future__ import annotations

import pytest

from packages.serializers.base import ProviderSerializer
from packages.serializers.exceptions import UnknownSerializerError
from packages.serializers.factory import SerializerFactory
from packages.serializers.registry import register, unregister
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


class TestSerializerFactory:
    """Tests for SerializerFactory."""

    def setup_method(self) -> None:
        """Clear the registry before each test, preserving auto-registered serializers."""
        # Save auto-registered serializers (those registered before this
        # test file was imported).
        from packages.serializers.registry import _registry as _REGISTRY

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

    def test_create_returns_registered_instance(self) -> None:
        """Verify create returns an instance of the registered serializer."""
        register(ProviderType.vllm, MockSerializer)
        serializer = SerializerFactory.create(ProviderType.vllm)
        assert isinstance(serializer, ProviderSerializer)

    def test_create_raises_for_unknown(self) -> None:
        """Verify create raises UnknownSerializerError for unregistered type."""
        with pytest.raises(UnknownSerializerError):
            SerializerFactory.create(ProviderType.ollama)

    def test_create_returns_fresh_instance(self) -> None:
        """Verify each call returns a new instance."""
        register(ProviderType.vllm, MockSerializer)
        s1 = SerializerFactory.create(ProviderType.vllm)
        s2 = SerializerFactory.create(ProviderType.vllm)
        assert s1 is not s2

    def test_create_with_different_types(self) -> None:
        """Verify create works with different provider types."""
        register(ProviderType.vllm, MockSerializer)
        register(ProviderType.gemini, MockSerializerB)

        s1 = SerializerFactory.create(ProviderType.vllm)
        s2 = SerializerFactory.create(ProviderType.gemini)

        assert s1.provider == ProviderType.vllm
        assert s2.provider == ProviderType.gemini

    def test_create_after_removal_raises(self) -> None:
        """Verify create raises after unregister."""
        register(ProviderType.vllm, MockSerializer)
        unregister(ProviderType.vllm)
        with pytest.raises(UnknownSerializerError):
            SerializerFactory.create(ProviderType.vllm)

    def test_create_produces_correct_provider_type(self) -> None:
        """Verify the created serializer reports the correct provider type."""
        register(ProviderType.vllm, MockSerializer)
        serializer = SerializerFactory.create(ProviderType.vllm)
        assert serializer.provider == ProviderType.vllm
