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


class TestSerializerFactory:
    """Tests for SerializerFactory."""

    def setup_method(self) -> None:
        """Clear the registry before each test."""
        for pt in list(register.__globals__["_registry"].keys()):
            try:
                unregister(pt)
            except KeyError:
                pass

    def test_create_returns_registered_instance(self) -> None:
        """Verify create returns an instance of the registered serializer."""
        register(ProviderType.openai, MockSerializer)
        serializer = SerializerFactory.create(ProviderType.openai)
        assert isinstance(serializer, ProviderSerializer)

    def test_create_raises_for_unknown(self) -> None:
        """Verify create raises UnknownSerializerError for unregistered type."""
        with pytest.raises(UnknownSerializerError):
            SerializerFactory.create(ProviderType.gemini)

    def test_create_returns_fresh_instance(self) -> None:
        """Verify each call returns a new instance."""
        register(ProviderType.openai, MockSerializer)
        s1 = SerializerFactory.create(ProviderType.openai)
        s2 = SerializerFactory.create(ProviderType.openai)
        assert s1 is not s2

    def test_create_with_different_types(self) -> None:
        """Verify create works with different provider types."""
        register(ProviderType.openai, MockSerializer)
        register(ProviderType.anthropic, MockSerializerB)

        s1 = SerializerFactory.create(ProviderType.openai)
        s2 = SerializerFactory.create(ProviderType.anthropic)

        assert s1.provider == ProviderType.openai
        assert s2.provider == ProviderType.anthropic

    def test_create_after_removal_raises(self) -> None:
        """Verify create raises after unregister."""
        register(ProviderType.openai, MockSerializer)
        unregister(ProviderType.openai)
        with pytest.raises(UnknownSerializerError):
            SerializerFactory.create(ProviderType.openai)

    def test_create_produces_correct_provider_type(self) -> None:
        """Verify the created serializer reports the correct provider type."""
        register(ProviderType.openai, MockSerializer)
        serializer = SerializerFactory.create(ProviderType.openai)
        assert serializer.provider == ProviderType.openai
