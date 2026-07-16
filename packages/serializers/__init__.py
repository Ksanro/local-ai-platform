"""Serialization Layer package.

Translates platform models into provider-specific request formats.

Architecture
------------

ContextPackage
       |
       v
Serializer
       |
       v
ProviderRequest
       |
       v
Provider
       |
       v
LLM

The Serialization Layer is a first-class platform component.
It is independent of inference, networking, and provider execution.

Responsibilities
----------------

- Translate platform models (ContextPackage, ChatMessage) into
  provider-specific request payloads (ProviderRequest).
- Own formatting rules (ordering, system messages, context injection).
- Remain pure functions: deterministic, no side effects.

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

Providers must not

- format repository context
- understand ContextPackage
- perform serialization

Public API
----------

.. code-block:: python

    from packages.serializers.factory import SerializerFactory

    serializer = SerializerFactory.create(provider_type="openai")

    provider_request = serializer.serialize(
        context_package=context_package,
        messages=user_messages,
    )

"""

from __future__ import annotations

from packages.serializers.base import ProviderSerializer
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.registry import get_registry
from packages.serializers.types import ProviderType

__all__ = [
    "ProviderSerializer",
    "ProviderRequest",
    "ProviderType",
    "SerializerFactory",
    "get_registry",
]
