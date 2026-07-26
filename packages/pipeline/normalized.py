"""Normalized request and response types for the pipeline.

Provides a single, authoritative representation of "the request" that flows
through the entire pipeline, replacing the dual-path ``ProviderRequest |
context.request`` mechanism that caused field-loss bugs.

Architecture
------------

Raw client request
      │
      ▼
NormalizedRequest        (every protocol field, explicitly typed)
      │
      ▼
provider payload         (to_provider_payload – single transform)
      │
      ▼
raw provider response
      │
      ▼
NormalizedResponse       (typed wrapper for response path)

Message Ordering
----------------

1. Client system message(s) (preserved verbatim from input).
2. Repository context system message (injected by RepositoryContextStage).
3. Conversation messages (user/assistant, unchanged).

Serialization Rules
-------------------

- ``from_client(body)`` parses known protocol fields into typed slots;
  anything unrecognized goes into ``extra`` unchanged (never dropped).
- ``to_provider_payload(backend_model)`` emits a dict suitable for the
  provider HTTP call.  Known fields are included when non-None.
  ``stream_options`` is added when ``stream=True``.
  ``extra`` fields are merged back in.
- Fields that are ``None`` are omitted (don't send ``temperature: null``).
- Deterministic: identical input always produces identical output.

Constraints
-----------

- No repository access.
- No filesystem access.
- No source code parsing.
- No provider calls.
- No HTTP.

Public API
----------

.. code-block:: python

    from packages.pipeline.normalized import NormalizedRequest

    nr = NormalizedRequest.from_client(body)
    payload = nr.to_provider_payload(backend_model="vllm-gpt4")

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedRequest:
    """A normalized representation of every protocol field.

    Explicitly typed slots replace the catch-all ``kwargs`` dict that
    caused field-loss bugs in the dual-path ``ProviderRequest`` path.

    Attributes:
        messages: Full, ordered message list with roles preserved.
        model: Client-facing model identifier.
        stream: Whether the caller requested streaming.
        tools: Provider tool definitions (OpenAI format).
        tool_choice: Tool selection directive.
        stop: One or more stop sequences.
        temperature: Sampling temperature.
        top_p: Nucleus sampling threshold.
        max_tokens: Maximum generation tokens.
        frequency_penalty: OpenAI frequency penalty.
        presence_penalty: OpenAI presence penalty.
        extra: Unknown passthrough fields — never dropped.
    """

    messages: list[dict[str, Any]]
    model: str
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    stop: Any | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Class methods — parsing / serializing
    # ------------------------------------------------------------------

    KNOWN_PROTOCOL_FIELDS = frozenset((
        "messages",
        "model",
        "stream",
        "tools",
        "tool_choice",
        "stop",
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
    ))

    @classmethod
    def from_client(cls, body: dict[str, Any]) -> "NormalizedRequest":
        """Parse a raw incoming request body into a ``NormalizedRequest``.

        Known protocol fields are extracted into their typed slots.
        Anything unrecognized is stored in ``extra`` unchanged — an
        unknown field today may be a provider extension tomorrow.

        Args:
            body: The raw request body dict (e.g. from the gateway).

        Returns:
            A new ``NormalizedRequest`` instance.
        """
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        model = body.get("model", "default")
        if not isinstance(model, str):
            model = "default"

        stream = body.get("stream", False)
        if not isinstance(stream, bool):
            stream = False

        tools = body.get("tools")
        if tools is not None and not isinstance(tools, list):
            tools = None

        tool_choice = body.get("tool_choice")

        stop = body.get("stop")

        temperature = body.get("temperature")
        if temperature is not None and not isinstance(temperature, (int, float)):
            temperature = None

        top_p = body.get("top_p")
        if top_p is not None and not isinstance(top_p, (int, float)):
            top_p = None

        max_tokens = body.get("max_tokens")
        if max_tokens is not None and not isinstance(max_tokens, int):
            max_tokens = None

        frequency_penalty = body.get("frequency_penalty")
        if frequency_penalty is not None and not isinstance(frequency_penalty, (int, float)):
            frequency_penalty = None

        presence_penalty = body.get("presence_penalty")
        if presence_penalty is not None and not isinstance(presence_penalty, (int, float)):
            presence_penalty = None

        # Collect unknown fields into extra.
        extra: dict[str, Any] = {}
        for key, value in body.items():
            if key not in cls.KNOWN_PROTOCOL_FIELDS:
                extra[key] = value

        return cls(
            messages=messages,
            model=model,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            extra=extra,
        )

    def to_provider_payload(self, backend_model: str | None = None) -> dict[str, Any]:
        """Emit a provider-ready request dict.

        Every non-None protocol field is included.  ``stream_options``
        is added when ``stream=True``.  The ``model`` field becomes
        ``backend_model`` (if provided).  Unknown ``extra`` fields are
        merged back in so they are never dropped.

        Args:
            backend_model: Backend model identifier to substitute for
                ``model``.  If ``None``, the original ``model`` is used.

        Returns:
            A dict suitable for forwarding to the provider HTTP call.
        """
        model = backend_model if backend_model is not None else self.model

        result: dict[str, Any] = {
            "messages": self.messages,
            "model": model,
        }

        if self.stream:
            result["stream"] = True
            result["stream_options"] = {"include_usage": True}
        else:
            result["stream"] = False

        # Include protocol fields when non-None.
        if self.tools is not None:
            result["tools"] = self.tools

        if self.tool_choice is not None:
            result["tool_choice"] = self.tool_choice

        if self.stop is not None:
            result["stop"] = self.stop

        if self.temperature is not None:
            result["temperature"] = self.temperature

        if self.top_p is not None:
            result["top_p"] = self.top_p

        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens

        if self.frequency_penalty is not None:
            result["frequency_penalty"] = self.frequency_penalty

        if self.presence_penalty is not None:
            result["presence_penalty"] = self.presence_penalty

        # Merge unknown passthrough fields.
        if self.extra:
            result.update(self.extra)

        return result

    def with_messages(self, messages: list[dict[str, Any]]) -> "NormalizedRequest":
        """Return a copy with updated messages (used by RepositoryContextStage)."""
        return self.__class__(
            messages=messages,
            model=self.model,
            stream=self.stream,
            tools=self.tools,
            tool_choice=self.tool_choice,
            stop=self.stop,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            extra=dict(self.extra),
        )


@dataclass(frozen=True)
class NormalizedResponse:
    """A normalized representation of a provider response.

    Typed wrapper over the provider's response (id, model, choices,
    usage) plus a streaming variant that carries the async iterator.

    Attributes:
        id: Provider response ID.
        model: Model that generated the response.
        choices: List of choice dicts (provider-specific shape).
        usage: Usage metadata (prompt_tokens, completion_tokens, etc.).
        _raw: Full raw response passthrough — never dropped.
    """

    id: str | None = None
    model: str | None = None
    choices: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_provider(cls, body: dict[str, Any]) -> "NormalizedResponse":
        """Parse a raw provider response body.

        Args:
            body: The raw response dict from the provider.

        Returns:
            A new ``NormalizedResponse`` instance.
        """
        return cls(
            id=body.get("id"),
            model=body.get("model"),
            choices=body.get("choices", []),
            usage=body.get("usage"),
            _raw=body,
        )

    def to_client_response(self) -> dict[str, Any]:
        """Convert to a client-facing response dict.

        Returns:
            A dict matching the provider response shape.
        """
        result: dict[str, Any] = {
            "id": self.id,
            "model": self.model,
            "choices": self.choices,
        }
        if self.usage is not None:
            result["usage"] = self.usage
        return result