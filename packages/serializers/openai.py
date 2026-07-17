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
2. Primary Symbol section (from ContextPackage).
3. Supporting Symbols section.
4. Related Callers section.
5. Related Callees section.
6. Related Modules section.
7. Original user messages (copied unchanged).

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
    from packages.context.context_package import ContextPackage

    serializer = OpenAISerializer()

    provider_request = serializer.serialize(
        context_package=context_package,
        messages=user_messages,
    )

"""

from __future__ import annotations

from typing import Any

from packages.context.context_package import ContextPackage
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
        2. Primary Symbol section (if ContextPackage has a primary symbol).
        3. Supporting Symbols section (if ContextPackage has supporting symbols).
        4. Related Callers section (if ContextPackage has callers).
        5. Related Callees section (if ContextPackage has callees).
        6. Related Modules section (if ContextPackage has modules).
        7. Original user messages (copied unchanged).

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
        # contains structured data.
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
        structured data. If no primary symbol, callers, callees, or
        modules are present, returns ``None`` to omit repository context.

        Section ordering:
        1. Primary Symbol
        2. Supporting Symbols
        3. Related Callers
        4. Related Callees
        5. Related Modules

        Args:
            context_package: The platform context package, or ``None``.

        Returns:
            A repository context message dict, or ``None``.
        """
        if context_package is None:
            return None

        # Check if there's any structured content.
        has_content = (
            context_package.primary_symbol
            or context_package.supporting_symbols
            or context_package.related_callers
            or context_package.related_callees
            or context_package.related_modules
        )
        if not has_content:
            return None

        # Build repository context from structured sections.
        parts: list[str] = []

        # Primary Symbol
        if context_package.primary_symbol:
            parts.append(f"Primary symbol: {context_package.primary_symbol}")

        # Supporting Symbols
        if context_package.supporting_symbols:
            parts.append("Supporting symbols:")
            for symbol in context_package.supporting_symbols:
                parts.append(f"  - {symbol}")

        # Related Callers
        if context_package.related_callers:
            parts.append("Related callers:")
            for symbol in context_package.related_callers:
                parts.append(f"  - {symbol}")

        # Related Callees
        if context_package.related_callees:
            parts.append("Related callees:")
            for symbol in context_package.related_callees:
                parts.append(f"  - {symbol}")

        # Related Modules
        if context_package.related_modules:
            parts.append("Related modules:")
            for module in context_package.related_modules:
                parts.append(f"  - {module}")

        # Relationship Summary (metadata only, no source code)
        if context_package.relationship_summary.symbol_count > 0:
            summary = context_package.relationship_summary
            parts.append(
                f"Relationship summary: "
                f"{summary.caller_count} callers, "
                f"{summary.callee_count} callees, "
                f"{summary.module_count} modules, "
                f"{summary.symbol_count} symbols"
            )

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
