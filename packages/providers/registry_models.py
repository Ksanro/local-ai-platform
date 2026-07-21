"""Model registry — parsing, validation, lookup.

Provides ``ModelRegistry`` that parses JSON config, validates entries,
and provides typed lookup by model name.
"""

from __future__ import annotations

import json
import logging

from packages.providers.models import ModelDefinition

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Typed container over ``ModelDefinition``.

    Owns configuration only — no provider instances, no runtime state.

    Attributes:
        _definitions: All parsed model definitions, keyed by model name.
    """

    def __init__(self, definitions: dict[str, ModelDefinition]) -> None:
        """Initialize with a dict of model_name -> ModelDefinition.

        Args:
            definitions: Mapping of model names to definitions.
        """
        self._definitions = definitions

    @property
    def definitions(self) -> list[ModelDefinition]:
        """Get all model definitions as a list.

        Returns:
            List of all ModelDefinition instances.
        """
        return list(self._definitions.values())

    @classmethod
    def from_json(cls, raw: str) -> ModelRegistry:
        """Parse and validate a JSON string into a ModelRegistry.

        Args:
            raw: JSON array string of model definitions.

        Returns:
            A new ModelRegistry instance.

        Raises:
            ValueError: If the JSON is malformed, has duplicates,
                missing required keys, or references an unregistered provider.
        """
        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Malformed JSON: {}".format(exc)) from exc

        # Must be a list
        if not isinstance(data, list):
            raise ValueError("models_config must be a JSON array")

        # Import registry to check provider names
        from packages.providers.registry import get_registry

        registered_providers = set(get_registry().keys())

        definitions: dict[str, ModelDefinition] = {}

        for idx, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise ValueError(
                    "Entry at index {} is not a JSON object".format(idx)
                )

            # Check required keys
            for key in ("model", "provider", "base_url"):
                if key not in entry:
                    raise ValueError(
                        "Missing required key '{}' in entry at index {}".format(key, idx)
                    )

            model = entry["model"]
            provider = entry["provider"]
            base_url = entry["base_url"]

            # Check for duplicate model names
            if model in definitions:
                raise ValueError(
                    "Duplicate model name '{}' at index {}".format(model, idx)
                )

            # Validate provider is registered
            if provider not in registered_providers:
                raise ValueError(
                    "Provider '{}' is not registered. "
                    "Registered providers: {}".format(provider, sorted(registered_providers))
                )

            # Validate context_window
            context_window = entry.get("context_window", 131072)
            if not isinstance(context_window, int) or context_window <= 0:
                raise ValueError(
                    "context_window must be a positive int, "
                    "got {!r} at index {}".format(context_window, idx)
                )

            # Validate max_output_tokens
            max_output_tokens = entry.get("max_output_tokens", 8192)
            if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
                raise ValueError(
                    "max_output_tokens must be a positive int, "
                    "got {!r} at index {}".format(max_output_tokens, idx)
                )

            # Optional fields with defaults
            timeout = entry.get("timeout")
            if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                raise ValueError(
                    "timeout must be a positive number, "
                    "got {!r} at index {}".format(timeout, idx)
                )

            supports_streaming = entry.get("supports_streaming", True)
            supports_tools = entry.get("supports_tools", False)
            supports_reasoning = entry.get("supports_reasoning", False)
            supports_json = entry.get("supports_json", False)
            # Validate backend_model
            backend_model = entry.get("backend_model")
            if backend_model is not None:
                if not isinstance(backend_model, str) or not backend_model:
                    raise ValueError(
                        "backend_model must be a non-empty string, "
                        "got {!r} at index {}".format(backend_model, idx)
                    )

            tokenizer = entry.get("tokenizer")
            api_key = entry.get("api_key")

            definitions[model] = ModelDefinition(
                model=model,
                backend_model=backend_model,
                provider=provider,
                base_url=base_url,
                context_window=context_window,
                max_output_tokens=max_output_tokens,
                tokenizer=tokenizer,
                api_key=api_key,
                timeout=timeout,
                supports_streaming=supports_streaming,
                supports_tools=supports_tools,
                supports_reasoning=supports_reasoning,
                supports_json=supports_json,
            )

        return cls(definitions)

    def get(self, model: str) -> ModelDefinition:
        """Get a model definition by name.

        Args:
            model: The model name to look up.

        Returns:
            The ModelDefinition for the requested model.

        Raises:
            UnknownModelError: If the model is not found.
        """
        if model not in self._definitions:
            from packages.providers.exceptions import UnknownModelError

            available = self.available_models()
            raise UnknownModelError(model, available)
        return self._definitions[model]

    def available_models(self) -> list[str]:
        """Get a sorted list of available model names.

        Returns:
            Sorted list of model names.
        """
        return sorted(self._definitions.keys())
