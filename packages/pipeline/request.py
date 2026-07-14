"""Pipeline request model.

Defines the typed request structure that flows through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineRequest:
    """Typed request for pipeline execution.

    Wraps the incoming gateway request with metadata needed by pipeline
    stages. All fields are optional to support partial requests from
    future stages that may add or transform data.

    Attributes:
        provider_name: Name of the provider to use (e.g. ``"vllm"``).
        model: Model identifier.
        messages: List of chat messages.
        stream: Whether to stream the response.
        kwargs: Additional provider parameters (temperature, max_tokens,
            tools, etc.).
        metadata: Free-form dict for pipeline-level metadata.
    """

    provider_name: str = "vllm"
    model: str = "default"
    messages: list[dict[str, Any]] = field(default_factory=list)
    stream: bool = False
    kwargs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_provider_kwargs(self) -> dict[str, Any]:
        """Convert to provider kwargs dict.

        Combines ``messages``, ``model``, ``stream``, and ``kwargs``
        into the shape expected by provider.chat().

        Returns:
            A dict with keys ``messages``, ``model``, ``stream``, and
            any additional keys from ``kwargs``.
        """
        result: dict[str, Any] = {
            "messages": self.messages,
            "model": self.model,
            "stream": self.stream,
        }
        result.update(self.kwargs)
        return result
