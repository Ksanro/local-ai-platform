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

Serializer Registration
------------------------

A serializer module registers itself with the global registry on first import
(``packages.serializers.openai`` ends with a ``register()`` call), and the
registry itself never imports serializer modules. This package closes that gap
for the built-ins: importing ``packages.serializers`` -- or any submodule of it,
which is what a capability does to reach ``SerializerFactory`` -- imports every
built-in serializer, so no caller has to import a serializer module just for
the registration side effect.

Importing a package is a one-shot event per interpreter, so this changes no
registry semantics: registration still goes through ``registry.register()``,
duplicate registration still raises ``ValueError``, ``unregister()`` still
removes an entry for good, and ``SerializerFactory.create()`` still raises
``UnknownSerializerError`` for a provider type that has no serializer.

"""

from __future__ import annotations

# Built-in serializer availability. Each serializer module registers itself
# with the registry on first import, and the registry never imports serializer
# modules; importing them here means anything that reaches this package, and
# therefore anything that reaches SerializerFactory, finds the built-ins
# registered. The alias keeps the import side-effect-only.
from packages.serializers import openai as _openai  # noqa: F401
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
