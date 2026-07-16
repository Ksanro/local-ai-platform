"""OpenAI Chat Completions serializer.

Converts platform models (ContextPackage + User Messages) into
OpenAI Chat Completions request format.

Architecture
------------

ContextPackage + User Messages
                |
                v
        OpenAISerializer
                |
                v
       ProviderRequest (OpenAI format)

Message Ordering
----------------

1. System message (platform system message).
2. Repository context (from ContextPackage symbols, if available).
3. Original user messages (copied unchanged).

Serialization Rules
-------------------

- Exactly one platform system message.
- Repository context included only when ContextPackage contains symbols.
- User messages copied unchanged — preserve order, roles, content.
- The serializer never modifies user input.
- Deterministic: identical input always produces identical output.

Constraints
-----------

- No repository access.
- No filesystem access.
- No source code parsing.
- No token estimation.
- No provider calls.
- No HTTP.

Public API
----------

.. code-block:: python

    from packages.serializers.openai import OpenAISerializer
    from packages.context.package import ContextPackage

    serializer = OpenAISerializer()

    provider_request = serializer.serialize(
        context_package=context_package,
        messages=user_messages,
    )

"""

from __future__ import annotations

from typing import Any

from packages.context.package import ContextPackage
from packages.serializers.base import ProviderSerializer
from packages.serializers.exceptions import SerializationFormatError
from packages.serializers.models import ProviderRequest
from packages.serializers.registry import register
from packages.serializers.types import ProviderType


class OpenAISerializer(ProviderSerializer):
    """Serializer for OpenAI Chat Completions format.

    Converts platform models into OpenAI-compatible request payloads.
    The serializer owns formatting; the provider owns execution.

    Attributes:
        None — the serializer is stateless.
    """

    @property
    def provider(self) -> ProviderType:
        """The provider type this serializer targets.

        Returns:
            ``ProviderType.openai``.
        """
        return ProviderType.openai

    def _serialize(
        self,
        context_package: ContextPackage | None,
        messages: list[dict[str, Any]],
    ) -> ProviderRequest:
        """Serialize into OpenAI Chat Completions format.

        Builds the message list following the ordering rules:

        1. System message (platform system message).
        2. Repository context (if ContextPackage has symbols).
        3. Original user messages (copied unchanged).

        Args:
            context_package: The platform context package, or ``None``.
            messages: List of message dicts with ``role`` and ``content``.

        Returns:
            A ``ProviderRequest`` in OpenAI Chat Completions format.

        Raises:
            SerializationFormatError: If messages are invalid.
        """
        if not messages:
            raise SerializationFormatError(
                "Cannot serialize: messages list is empty"
            )

        # Validate message structure.
        self._validate_messages(messages)

        # Build the message list.
        system_message = self._build_system_message(context_package)
        user_messages = self._extract_user_messages(messages)

        # Assemble: system + repository context + user messages.
        all_messages: list[dict[str, Any]] = []

        if system_message is not None:
            all_messages.append(system_message)

        # Repository context is included only when ContextPackage
        # contains symbols. If no symbols, omit repository context.
        repo_context = self._build_repository_context(context_package)
        if repo_context is not None:
            all_messages.append(repo_context)

        # User messages are copied unchanged.
        all_messages.extend(user_messages)

        return ProviderRequest(
            provider_type=ProviderType.openai,
            messages=all_messages,
        )

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        """Validate message structure.

        Each message must have ``role`` and ``content`` keys.
        Roles must be one of ``system``, ``user``, ``assistant``.

        Args:
            messages: The messages to validate.

        Raises:
            SerializationFormatError: If messages are invalid.
        """
        valid_roles = {"system", "user", "assistant"}
        for i, message in enumerate(messages):
            if not isinstance(message, dict):
                raise SerializationFormatError(
                    f"Message {i} is not a dict: {type(message).__name__}"
                )
            if "role" not in message:
                raise SerializationFormatError(
                    f"Message {i} missing 'role' key"
                )
            if "content" not in message:
                raise SerializationFormatError(
                    f"Message {i} missing 'content' key"
                )
            if message["role"] not in valid_roles:
                raise SerializationFormatError(
                    f"Message {i} has invalid role: '{message['role']}'"
                )

    def _build_system_message(
        self, context_package: ContextPackage | None
    ) -> dict[str, str] | None:
        """Build the platform system message.

        Creates exactly one system message that describes the platform's
        role and capabilities. The system message is always present when
        a ContextPackage is provided.

        Args:
            context_package: The platform context package, or ``None``.

        Returns:
            A system message dict, or ``None`` if no context is available.
        """
        if context_package is None:
            return None

        system_content = (
            "You are a helpful coding assistant with access to a code "
            "repository. Use the provided repository context to answer "
            "the user's question accurately."
        )

        return {
            "role": "system",
            "content": system_content,
        }

    def _build_repository_context(
        self, context_package: ContextPackage | None
    ) -> dict[str, str] | None:
        """Build the repository context message.

        Includes repository context only when ContextPackage contains
        symbols. If no symbols are present, returns ``None`` to omit
        repository context.

        Args:
            context_package: The platform context package, or ``None``.

        Returns:
            A repository context message dict, or ``None``.
        """
        if context_package is None:
            return None

        if not context_package.symbols:
            return None

        # Build repository context from symbols and modules.
        parts: list[str] = []

        if context_package.symbols:
            parts.append("Repository symbols:")
            for symbol in context_package.symbols:
                parts.append(f"  - {symbol}")

        if context_package.modules:
            parts.append("Relevant modules:")
            for module in context_package.modules:
                parts.append(f"  - {module}")

        if context_package.query:
            parts.append(f"\nUser query: {context_package.query}")

        return {
            "role": "user",
            "content": "\n".join(parts),
        }

    @staticmethod
    def _extract_user_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract and return user messages unchanged.

        Copies all user and assistant messages in their original order.
        The serializer never modifies user input.

        Args:
            messages: The full message list from the gateway.

        Returns:
            A new list containing only user and assistant messages,
            in their original order.
        """
        return [
            dict(message)  # shallow copy to avoid mutation
            for message in messages
            if isinstance(message, dict)
            and message.get("role") in ("user", "assistant")
        ]


# Auto-register openai serializer
register(ProviderType.openai, OpenAISerializer)
