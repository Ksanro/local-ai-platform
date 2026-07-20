"""Abstract serializer base class.

Defines the interface that all provider serializers must satisfy.
Serializers translate platform models into provider-specific request
formats. They are pure functions: deterministic, no side effects.

Architecture
------------

ContextPackage + User Messages
                |
                v
        ProviderSerializer
                |
                v
          ProviderRequest

Responsibilities
----------------

- Convert ContextPackage and user messages into ProviderRequest.
- Own message formatting rules (ordering, system messages, context).
- Remain stateless and side-effect free.

Constraints
-----------

Serializers must not

- access repositories
- access the filesystem
- parse source code
- inspect AST
- perform ranking
- estimate tokens
- call providers
- perform HTTP
- stream responses

Public API
----------

.. code-block:: python

    class MySerializer(ProviderSerializer):
        @property
        def provider(self) -> ProviderType:
            return ProviderType.my_provider

        def serialize(self, context_package, messages):
            ...

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from packages.context.context_package import ContextPackage
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


class ProviderSerializer(ABC):
    """Abstract serializer interface.

    All provider serializers (OpenAI, Anthropic, etc.) must inherit
    from this class and implement ``provider`` and ``serialize``.

    Serializers are stateless and side-effect free. They transform
    platform models into provider request formats deterministically.

    Attributes:
        None — serializers are intentionally stateless.
    """

    @property
    @abstractmethod
    def provider(self) -> ProviderType:
        """The provider type this serializer targets.

        Returns:
            A ``ProviderType`` enum member.
        """

    def serialize(
        self,
        context_package: ContextPackage | None,
        messages: list[dict[str, Any]],
        model: str = "default",
    ) -> ProviderRequest:
        """Serialize platform models into a provider request.

        Converts a ContextPackage and list of user messages into a
        ProviderRequest formatted for the target provider.

        Ordering:

        1. System message (platform system message, if present).
        2. Repository context (from ContextPackage, if available).
        3. Original user messages (copied unchanged).

        Rules:

        - Exactly one platform system message.
        - Repository context included only when ContextPackage
          contains symbols.
        - User messages copied unchanged — preserve order, roles, content.
        - The serializer never modifies user input.
        - Deterministic: identical input always produces identical output.

        Args:
            context_package: The platform context package, or ``None``
                if no repository context is available.
            messages: List of message dicts with ``role`` and ``content``
                keys, as received from the gateway.
            model: Model identifier for the provider.

        Returns:
            A ``ProviderRequest`` ready for provider consumption.
        """
        return self._serialize(context_package, messages, model)

    @abstractmethod
    def _serialize(
        self,
        context_package: ContextPackage | None,
        messages: list[dict[str, Any]],
        model: str,
    ) -> ProviderRequest:
        """Implement the serialization logic.

        Subclasses must override this method to provide provider-specific
        formatting. The public ``serialize()`` method validates inputs
        and delegates to this method.

        Args:
            context_package: The platform context package, or ``None``.
            messages: List of message dicts.
            model: Model identifier for the provider.

        Returns:
            A formatted ``ProviderRequest``.
        """
