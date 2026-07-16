"""Serializer factory for creating serializer instances.

Provides a ``create`` function that looks up a serializer
class by provider type in the registry and instantiates it.
Raises ``UnknownSerializerError`` for unregistered provider types.

Architecture
------------

SerializerFactory
       |
       v
SerializerRegistry
       |
       v
SerializerClass instance

Mirrors the ProviderFactory design pattern used by the Provider layer.

Public API
----------

.. code-block:: python

    from packages.serializers.factory import SerializerFactory
    from packages.serializers.types import ProviderType

    serializer = SerializerFactory.create(ProviderType.openai)

"""

from __future__ import annotations

from packages.serializers.base import ProviderSerializer
from packages.serializers.exceptions import UnknownSerializerError
from packages.serializers.registry import get_registry
from packages.serializers.types import ProviderType


class SerializerFactory:
    """Factory for creating serializer instances.

    Looks up serializer classes in the global registry and
    instantiates them. The factory is stateless — it creates
    fresh instances on each call.

    Usage:

    .. code-block:: python

        serializer = SerializerFactory.create(ProviderType.openai)

    Raises:
        UnknownSerializerError: If the provider type is not registered.
    """

    @staticmethod
    def create(provider_type: ProviderType) -> ProviderSerializer:
        """Create a serializer instance by provider type.

        Looks up the serializer class in the global registry and
        instantiates it. The serializer must have been registered
        via ``register()`` before this call.

        Args:
            provider_type: The registered provider type
                (e.g. ``ProviderType.openai``).

        Returns:
            A new instance of the requested serializer class.

        Raises:
            UnknownSerializerError: If the provider type is not registered.
        """
        registry = get_registry()
        if provider_type not in registry:
            raise UnknownSerializerError(
                f"Serializer for provider type '{provider_type.value}' is not registered"
            )
        return registry[provider_type]()
