"""Provider type enumeration.

Defines the set of supported provider types that serializers can target.
Each provider type corresponds to a distinct request format.
"""

from __future__ import annotations

from enum import Enum


class ProviderType(str, Enum):
    """Enum of supported provider types.

    Each member maps to a distinct provider request format.
    New providers are added as new enum members.

    Attributes:
        openai: OpenAI Chat Completions format.
        anthropic: Anthropic Messages API format.
        vllm: vLLM OpenAI-compatible format (same as openai).
        gemini: Google Gemini format.
        ollama: Ollama format.
        lm_studio: LM Studio format.
    """

    openai = "openai"
    anthropic = "anthropic"
    vllm = "vllm"
    gemini = "gemini"
    ollama = "ollama"
    lm_studio = "lm_studio"
