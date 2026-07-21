"""Model definition dataclasses.

Defines the configuration records for model routing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """Configuration record for a single model.

    Attributes:
        model: Required — routing key, unique within the registry.
        provider: Required — registered provider name.
        base_url: Required — base URL of the backend.
        context_window: Size of the context window in tokens.
        max_output_tokens: Maximum number of output tokens.
        tokenizer: Metadata only — tokenizer identifier.
        api_key: Optional API key for this model.
        timeout: Optional request timeout in seconds.
        supports_streaming: Whether streaming is supported.
        supports_tools: Whether tool use is supported.
        supports_reasoning: Whether reasoning is supported.
        supports_json: Whether JSON mode is supported.
    """

    model: str
    provider: str
    base_url: str
    context_window: int = 131072
    max_output_tokens: int = 8192
    tokenizer: str | None = None
    api_key: str | None = None
    timeout: float | None = None
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_reasoning: bool = False
    supports_json: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """Result of resolving a model string to configuration and provider.

    Attributes:
        definition: The model configuration.
        provider: The provider instance to use for this model.
    """

    definition: ModelDefinition
    provider: "Provider"  # type: ignore[name-defined]  # noqa: F821
