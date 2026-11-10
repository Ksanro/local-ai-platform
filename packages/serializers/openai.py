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

1. Client system message(s) (preserved verbatim from input).
2. Repository context system message (if ContextPackage has data).
3. Primary Symbol section (from ContextPackage).
4. Supporting Symbols section.
5. Related Callers section.
6. Related Callees section.
7. Related Modules section.
8. Conversation messages - user, assistant and tool - copied unchanged,
   in their original order.

Context Quality v2
------------------

The serializer now emits engineering-grade source context:

PRIMARY SYMBOL:
- Qualified name
- Signature (function/class declaration)
- Docstring
- Decorators
- Complete source body
- Source location

SUPPORTING SYMBOLS:
- Qualified name
- Signature
- Docstring
- Short source preview
- Source location

MODULE DESCRIPTIONS:
- Module path
- Purpose description
- Relationship summary

Serialization Rules
-------------------

- Client system messages are preserved in order, placed first.
- Repository context becomes a system message (if ContextPackage has data).
- Platform role message is folded into repository context.
- User and assistant messages are copied unchanged.
- The serializer never modifies user input.
- Deterministic: identical input always produces identical output.
- Chat-template control tags in the repository-context text (``<think>``,
  ``<|im_start|>`` and their families) are escaped before that text joins the
  system message, because the backend's tokenizer parses them as control
  tokens even inside message text. Client messages are not touched.

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

import re
from typing import Any

from packages.context.context_package import ContextPackage
from packages.serializers.base import ProviderSerializer
from packages.serializers.exceptions import SerializationFormatError
from packages.serializers.models import ProviderRequest
from packages.serializers.registry import register
from packages.serializers.types import ProviderType

#: The opening ``<`` of a chat-template control tag: ``<think>``/``</think>``,
#: ``<tool_call>``/``</tool_call>``, ``<tool_response>``/``</tool_response>``, and
#: the ``<|name|>`` family (``<|im_start|>``, ``<|im_end|>``, ``<|endoftext|>``,
#: ``<|file_sep|>`` ...).  On the live Qwen tokenizer each of these is one special
#: token, and a literal one inside message text is parsed as that token, so
#: repository source that merely mentions a tag injects a real control token
#: (measured 2026-11-10, roadmap Phase H).  The gateway has no tokenizer, so the
#: set is a fixed pattern; the ``<|name|>`` alphabet is deliberately broad to cover
#: other chat templates.  Only the ``<`` is matched: the escape is inserted there.
_CHAT_TEMPLATE_TAG_OPEN_RE = re.compile(
    r"<(?=/?(?:think|tool_call|tool_response)>|\|[A-Za-z0-9_.:-]+\|>)"
)

#: What replaces the matched ``<``: the HTML entity, giving ``&lt;think>``,
#: ``&lt;/think>`` and ``&lt;|im_start|>``, which tokenize as ordinary text on the
#: live backend.  Chosen over a backslash form (``<\think>``) by measurement
#: (roadmap Phase H, H2): the backslash form leaked into a quoted answer and left
#: ``debug_vllm_stream_prefix`` at 1/3, where this form scored 3/3 without leaking.
_CHAT_TAG_OPEN_ESCAPE = "&lt;"

#: Prepended to the repository context only when an escape occurred.  It must not
#: contain a raw tag itself.
_CHAT_TAG_LEGEND = (
    "Note: chat-template control tags in the repository text below have their "
    "opening angle bracket written as the HTML entity &lt; so they stay plain "
    "text; read each one as the same tag with an ordinary opening angle bracket."
)


def escape_chat_template_tags(text: str) -> tuple[str, int]:
    """Escape every chat-template control tag in ``text``.

    Returns the escaped text and how many tags were escaped.  Text without such
    a tag is returned unchanged, including ordinary angle-bracket text such as
    ``a < b``, ``List<int>`` or ``<div>``.
    """
    return _CHAT_TEMPLATE_TAG_OPEN_RE.subn(lambda _m: _CHAT_TAG_OPEN_ESCAPE, text)


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
        model: str = "default",
    ) -> ProviderRequest:
        """Serialize into OpenAI Chat Completions format.

        Builds the message list following the ordering rules:

        1. Client system message(s) (preserved verbatim from input).
        2. Repository context system message (if ContextPackage has data).
        3. Primary Symbol section (if ContextPackage has a primary symbol).
        4. Supporting Symbols section (if ContextPackage has supporting symbols).
        5. Related Callers section (if ContextPackage has callers).
        6. Related Callees section (if ContextPackage has callees).
        7. Related Modules section (if ContextPackage has modules).
        8. Conversation messages - user, assistant and tool - copied
           unchanged, in their original order.

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

        # Extract client system messages (preserve verbatim).
        client_systems = self._extract_client_system_messages(messages)

        # Extract conversation messages (user, assistant and tool).
        conversation_messages = self._extract_conversation_messages(messages)

        # Assemble a SINGLE system message. vLLM's Qwen chat template
        # produces an empty generation when given two system messages, so
        # the client's system prompt and the repository context must be
        # combined into one, client instructions first.
        all_messages: list[dict[str, Any]] = []

        # Build the repository-context text (may fold in the platform message).
        repo_context = self._build_repository_context(context_package)
        repo_context_text = ""
        if repo_context is not None:
            platform_msg = self._build_system_message(context_package)
            if platform_msg and platform_msg["content"]:
                repo_context_text = (
                    platform_msg["content"] + "\n\n" + repo_context["content"]
                )
            else:
                repo_context_text = repo_context["content"]

        # Concatenate all client system messages (preserve order), then the
        # repo context, into one system message.
        client_system_text = "\n\n".join(
            m["content"]
            for m in client_systems
            if isinstance(m.get("content"), str) and m["content"]
        )

        parts = [t for t in (client_system_text, repo_context_text) if t]
        if parts:
            all_messages.append(
                {"role": "system", "content": "\n\n".join(parts)}
            )

        # Conversation messages (user, assistant and tool) last.
        all_messages.extend(conversation_messages)

        return ProviderRequest(
            provider_type=ProviderType.openai,
            messages=all_messages,
            model=model,
        )

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        """Validate message structure.

        Each message must have ``role`` and ``content`` keys, except an
        assistant message carrying ``tool_calls``, which may omit
        ``content``. Roles must be one of ``system``, ``user``,
        ``assistant``, ``tool``.

        Args:
            messages: The messages to validate.

        Raises:
            SerializationFormatError: If messages are invalid.
        """
        valid_roles = {"system", "user", "assistant", "tool"}
        for i, message in enumerate(messages):
            if not isinstance(message, dict):
                raise SerializationFormatError(
                    f"Message {i} is not a dict: {type(message).__name__}"
                )
            if "role" not in message:
                raise SerializationFormatError(
                    f"Message {i} missing 'role' key"
                )
            # An assistant turn that only calls tools may omit ``content``.
            if "content" not in message and not (
                message["role"] == "assistant" and message.get("tool_calls")
            ):
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

        Creates a system message that describes the platform's
        role and capabilities. Returns None if no context is available.

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

        Context Quality v2: emits source code (signatures, docstrings,
        source bodies) alongside symbol names.

        Section ordering:
        1. Primary Symbol (with source)
        2. Supporting Symbols (with signatures and previews)
        3. Related Callers
        4. Related Callees
        5. Related Modules (with descriptions)
        6. Relationship Summary

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

        # --- PRIMARY SYMBOL (Context Quality v2) ---
        if context_package.primary_symbol:
            parts.append(f"Primary symbol: {context_package.primary_symbol}")

            # Emit source-aware context if available.
            primary_ctx = context_package.primary_symbol_context
            if primary_ctx is not None:
                parts.append(f"  Signature: {primary_ctx.signature or 'N/A'}")
                if primary_ctx.decorators:
                    parts.append(
                        f"  Decorators: {', '.join(primary_ctx.decorators)}"
                    )
                if primary_ctx.docstring:
                    parts.append(f"  Docstring:\n    {primary_ctx.docstring}")
                if primary_ctx.location:
                    mod, line, _ = primary_ctx.location
                    parts.append(f"  Location: {mod}:{line}")

                # Source body (complete for primary symbol).
                if primary_ctx.source:
                    parts.append("  Source:")
                    # Indent source lines.
                    for src_line in primary_ctx.source.splitlines():
                        parts.append(f"    {src_line}")

        # --- SUPPORTING SYMBOLS (Context Quality v2) ---
        if context_package.supporting_symbols:
            parts.append("Supporting symbols:")

            # Check if we have source-aware context.
            if context_package.supporting_symbol_contexts:
                for ctx in context_package.supporting_symbol_contexts:
                    parts.append(f"  - {ctx.qualified_name}")
                    if ctx.signature:
                        parts.append(f"    Signature: {ctx.signature}")
                    if ctx.docstring:
                        parts.append(f"    Docstring: {ctx.docstring}")
                    if ctx.decorators:
                        parts.append(
                            f"    Decorators: {', '.join(ctx.decorators)}"
                        )
                    if ctx.location:
                        mod, line, _ = ctx.location
                        parts.append(f"    Location: {mod}:{line}")
                    if ctx.source_preview:
                        parts.append("    Preview:")
                        for src_line in ctx.source_preview.splitlines():
                            parts.append(f"      {src_line}")
            else:
                # Fallback: identifier-only (v1 compatibility).
                for symbol in context_package.supporting_symbols:
                    parts.append(f"  - {symbol}")

        # --- RELATED CALLERS ---
        if context_package.related_callers:
            parts.append("Related callers:")
            for symbol in context_package.related_callers:
                parts.append(f"  - {symbol}")

        # --- RELATED CALLEES ---
        if context_package.related_callees:
            parts.append("Related callees:")
            for symbol in context_package.related_callees:
                parts.append(f"  - {symbol}")

        # --- RELATED MODULES (Context Quality v2) ---
        if context_package.related_modules:
            parts.append("Related modules:")

            # Check if we have module descriptions.
            if context_package.module_descriptions:
                for desc in context_package.module_descriptions:
                    parts.append(
                        f"  - {desc.module_path}: {desc.purpose}"
                    )
                    if desc.relationship_summary:
                        parts.append(
                            f"    Relationship: {desc.relationship_summary}"
                        )
            else:
                # Fallback: identifier-only (v1 compatibility).
                for module in context_package.related_modules:
                    parts.append(f"  - {module}")

        # Relationship Summary (metadata)
        if context_package.relationship_summary.symbol_count > 0:
            summary = context_package.relationship_summary
            parts.append(
                f"Relationship summary: "
                f"{summary.caller_count} callers, "
                f"{summary.callee_count} callees, "
                f"{summary.module_count} modules, "
                f"{summary.symbol_count} symbols"
            )

        # Escape chat-template tags in this gateway-authored text only, before it
        # is combined with the client's system messages.  The legend is added
        # only when something was escaped, so other prompts stay byte-identical.
        content, escaped = escape_chat_template_tags("\n".join(parts))
        if escaped:
            content = _CHAT_TAG_LEGEND + "\n" + content

        return {
            "role": "user",
            "content": content,
        }

    @staticmethod
    def _extract_client_system_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract client system messages unchanged.

        Returns all incoming ``role: "system"`` messages in their
        original order. These carry the client's protocol instructions
        (tool definitions, rules, etc.) and must survive verbatim.

        Args:
            messages: The full message list from the gateway.

        Returns:
            A new list containing only system messages, in order.
        """
        return [
            dict(message)  # shallow copy to avoid mutation
            for message in messages
            if isinstance(message, dict) and message.get("role") == "system"
        ]

    @staticmethod
    def _extract_conversation_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract and return user, assistant and tool messages unchanged.

        Copies all user, assistant and tool messages in their original
        order, so each ``role: "tool"`` result stays directly after the
        assistant ``tool_calls`` turn it answers. System messages are
        excluded (they are handled separately). The serializer never
        modifies user input.

        Args:
            messages: The full message list from the gateway.

        Returns:
            A new list containing only user, assistant and tool messages,
            in their original order.
        """
        return [
            dict(message)  # shallow copy to avoid mutation
            for message in messages
            if isinstance(message, dict)
            and message.get("role") in ("user", "assistant", "tool")
        ]


# Auto-register openai serializer
register(ProviderType.openai, OpenAISerializer)
