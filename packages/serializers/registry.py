"""Serializer registry.

Maintains a global mapping of provider types to serializer classes.
Serializers are registered automatically when their module is imported
(e.g. ``packages.serializers.openai`` registers ``"openai"`` at import time).

Architecture
------------

SerializerRegistry
       |
       v
Global mapping: ProviderType -> SerializerClass

Responsibilities
----------------

- Register serializers by provider type.
- Look up serializers by provider type.
- Prevent duplicate registrations.
- Deterministic behaviour.

Public API
----------

.. code-block:: python

    from packages.serializers.registry import register, get_registry

    register(ProviderType.openai, OpenAISerializer)
    registry = get_registry()

"""

from __future__ import annotations

from typing import Type

from packages.serializers.base import ProviderSerializer
from packages.serializers.types import ProviderType

_registry: dict[ProviderType, Type[ProviderSerializer]] = {}


def register(provider_type: ProviderType, serializer_class: Type[ProviderSerializer]) -> None:
    """Register a serializer class by provider type.

    Adds the serializer class to the global registry so it can be
    looked up by provider type via ``SerializerFactory.create()``.

    Raises:
        ValueError: If a serializer is already registered for this
            provider type.

    Args:
        provider_type: Unique identifier for the serializer
            (e.g. ``ProviderType.openai``).
        serializer_class: The serializer class to register. Must inherit
            from ``ProviderSerializer``.
    """
    if provider_type in _registry:
        raise ValueError(
            f"Serializer already registered for provider type '{provider_type.value}'. "
            f"Existing: {_registry[provider_type].__name__}, "
            f"Attempted: {serializer_class.__name__}"
        )
    _registry[provider_type] = serializer_class


def get_registry() -> dict[ProviderType, Type[ProviderSerializer]]:
    """Return the current serializer registry.

    Returns a shallow copy of the registry dict to prevent
    external mutation.

    Returns:
        A dict mapping provider types to their serializer classes.
    """
    return dict(_registry)


def has_serializer(provider_type: ProviderType) -> bool:
    """Check if a serializer is registered.

    Args:
        provider_type: The provider type to look up.

    Returns:
        ``True`` if a serializer is registered, ``False`` otherwise.
    """
    return provider_type in _registry


def unregister(provider_type: ProviderType) -> None:
    """Remove a serializer from the registry.

    Args:
        provider_type: The provider type to unregister.

    Raises:
        KeyError: If the provider type is not registered.
    """
    del _registry[provider_type]
