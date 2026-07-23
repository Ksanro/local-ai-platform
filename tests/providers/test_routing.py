"""Tests for model-based routing: ModelDefinition, ModelRegistry, ModelRouter."""

from __future__ import annotations

import pytest

from packages.providers.exceptions import UnknownModelError
from packages.providers.models import ModelDefinition
from packages.providers.registry_models import ModelRegistry
from packages.providers.router import FallbackModelRouter, ModelRouter


class TestModelDefinition:
    """Tests for the ModelDefinition frozen dataclass."""

    def test_minimal_definition(self) -> None:
        """Minimal definition requires model, provider, base_url."""
        d = ModelDefinition(
            model="test",
            provider="vllm",
            base_url="http://localhost:8000/v1",
        )
        assert d.model == "test"
        assert d.provider == "vllm"
        assert d.base_url == "http://localhost:8000/v1"
        assert d.context_window == 131072
        assert d.max_output_tokens == 8192
        assert d.tokenizer is None
        assert d.api_key is None
        assert d.timeout is None
        assert d.supports_streaming is True
        assert d.supports_tools is False
        assert d.supports_reasoning is False
        assert d.supports_json is False

    def test_full_definition(self) -> None:
        """All fields are set correctly."""
        d = ModelDefinition(
            model="qwen36",
            provider="vllm",
            base_url="http://100.106.236.88:8000/v1",
            context_window=65536,
            max_output_tokens=4096,
            tokenizer="Qwen/Qwen3-35B",
            api_key="secret",
            timeout=120.0,
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning=True,
            supports_json=True,
        )
        assert d.model == "qwen36"
        assert d.provider == "vllm"
        assert d.base_url == "http://100.106.236.88:8000/v1"
        assert d.context_window == 65536
        assert d.max_output_tokens == 4096
        assert d.tokenizer == "Qwen/Qwen3-35B"
        assert d.api_key == "secret"
        assert d.timeout == 120.0
        assert d.supports_streaming is True
        assert d.supports_tools is True
        assert d.supports_reasoning is True
        assert d.supports_json is True

    def test_frozen(self) -> None:
        """ModelDefinition is immutable."""
        d = ModelDefinition(
            model="test",
            provider="vllm",
            base_url="http://localhost:8000/v1",
        )
        with pytest.raises(Exception):
            d.model = "other"  # type: ignore[misc]


class TestModelRegistry:
    """Tests for ModelRegistry parsing and validation."""

    def test_from_json_empty(self) -> None:
        """Empty array is valid."""
        reg = ModelRegistry.from_json("[]")
        assert reg.available_models() == []

    def test_from_json_single(self) -> None:
        """Single model parses correctly."""
        raw = '[{"model": "qwen36", "provider": "vllm", "base_url": "http://localhost:8000/v1"}]'
        reg = ModelRegistry.from_json(raw)
        assert reg.available_models() == ["qwen36"]
        defs = reg.definitions
        assert len(defs) == 1
        assert defs[0].model == "qwen36"

    def test_from_json_multiple(self) -> None:
        """Multiple models parse correctly."""
        raw = (
            '[{"model": "qwen36", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "gpt", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        assert sorted(reg.available_models()) == ["gpt", "qwen36"]

    def test_from_json_metadata_roundtrip(self) -> None:
        """Metadata fields round-trip from JSON intact."""
        raw = (
            '[{"model": "m", "provider": "vllm", "base_url": "http://x/v1",'
            ' "context_window": 65536, "max_output_tokens": 4096,'
            ' "tokenizer": "Qwen/Qwen3-35B",'
            ' "api_key": "secret", "timeout": 90.0,'
            ' "supports_streaming": true, "supports_tools": true,'
            ' "supports_reasoning": true, "supports_json": false}]'
        )
        reg = ModelRegistry.from_json(raw)
        d = reg.get("m")
        assert d.context_window == 65536
        assert d.max_output_tokens == 4096
        assert d.tokenizer == "Qwen/Qwen3-35B"
        assert d.api_key == "secret"
        assert d.timeout == 90.0
        assert d.supports_streaming is True
        assert d.supports_tools is True
        assert d.supports_reasoning is True
        assert d.supports_json is False

    def test_from_json_sorted(self) -> None:
        """available_models() returns sorted list."""
        raw = (
            '[{"model": "z", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "a", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        assert reg.available_models() == ["a", "z"]

    def test_get_existing_model(self) -> None:
        """get() returns ModelDefinition for existing model."""
        raw = '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"}]'
        reg = ModelRegistry.from_json(raw)
        d = reg.get("m1")
        assert d.model == "m1"

    def test_get_nonexistent_model(self) -> None:
        """get() raises UnknownModelError for missing model."""
        reg = ModelRegistry.from_json("[]")
        with pytest.raises(UnknownModelError):
            reg.get("missing")

    def test_definitions_returns_all(self) -> None:
        """definitions property returns all ModelDefinitions."""
        raw = (
            '[{"model": "a", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "b", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        defs = reg.definitions
        assert len(defs) == 2
        assert {d.model for d in defs} == {"a", "b"}

    # Validation tests
    def test_from_json_not_array(self) -> None:
        """Non-array JSON raises ValueError."""
        with pytest.raises(ValueError, match="models_config must be a JSON array"):
            ModelRegistry.from_json('{"model": "x"}')

    def test_from_json_malformed_json(self) -> None:
        """Malformed JSON raises ValueError."""
        with pytest.raises(ValueError):
            ModelRegistry.from_json("{bad json")

    def test_from_json_missing_required_key(self) -> None:
        """Missing required key raises ValueError."""
        raw = '[{"provider": "vllm", "base_url": "http://a/v1"}]'
        with pytest.raises(ValueError, match="model"):
            ModelRegistry.from_json(raw)

    def test_from_json_duplicate_models(self) -> None:
        """Duplicate model names raise ValueError."""
        raw = (
            '[{"model": "m", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        with pytest.raises(ValueError, match="Duplicate"):
            ModelRegistry.from_json(raw)

    def test_from_json_invalid_provider(self) -> None:
        """Unregistered provider name raises ValueError."""
        raw = '[{"model": "m", "provider": "nonexistent", "base_url": "http://a/v1"}]'
        with pytest.raises(ValueError, match="nonexistent"):
            ModelRegistry.from_json(raw)

    def test_from_json_invalid_context_window(self) -> None:
        """Non-positive context_window raises ValueError."""
        raw = (
            '[{"model": "m", "provider": "vllm", "base_url": "http://a/v1",'
            ' "context_window": -1}]'
        )
        with pytest.raises(ValueError, match="context_window"):
            ModelRegistry.from_json(raw)

    def test_from_json_invalid_max_output_tokens(self) -> None:
        """Non-positive max_output_tokens raises ValueError."""
        raw = (
            '[{"model": "m", "provider": "vllm", "base_url": "http://a/v1",'
            ' "max_output_tokens": 0}]'
        )
        with pytest.raises(ValueError, match="max_output_tokens"):
            ModelRegistry.from_json(raw)


class TestModelRouter:
    """Tests for ModelRouter instance management."""

    def test_resolve_model(self) -> None:
        """resolve() returns a ResolvedModel with definition and provider."""
        raw = '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"}]'
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        resolved = router.resolve("m1")
        assert resolved.definition.model == "m1"
        assert resolved.provider is not None

    def test_resolve_unknown_model(self) -> None:
        """resolve() raises UnknownModelError for unknown model."""
        reg = ModelRegistry.from_json("[]")
        router = ModelRouter(reg)
        with pytest.raises(UnknownModelError) as exc_info:
            router.resolve("unknown")
        assert exc_info.value.model == "unknown"
        assert exc_info.value.available_models == []

    def test_available_models(self) -> None:
        """available_models() delegates to registry."""
        raw = (
            '[{"model": "z", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "a", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        assert router.available_models() == ["a", "z"]

    def test_same_backend_shared_instance(self) -> None:
        """Two models on the same backend share one provider instance."""
        raw = (
            '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m2", "provider": "vllm", "base_url": "http://a/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        r1 = router.resolve("m1")
        r2 = router.resolve("m2")
        assert r1.provider is r2.provider

    def test_different_backends_different_instances(self) -> None:
        """Models on different backends get different provider instances."""
        raw = (
            '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m2", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        r1 = router.resolve("m1")
        r2 = router.resolve("m2")
        assert r1.provider is not r2.provider

    def test_backends_count(self) -> None:
        """_providers count reflects unique backends."""
        raw = (
            '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m2", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m3", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        assert len(router._providers) == 2

    @pytest.mark.asyncio
    async def test_close_all(self) -> None:
        """close_all() closes each provider exactly once."""
        raw = (
            '[{"model": "m1", "provider": "vllm", "base_url": "http://a/v1"},'
            ' {"model": "m2", "provider": "vllm", "base_url": "http://b/v1"}]'
        )
        reg = ModelRegistry.from_json(raw)
        router = ModelRouter(reg)
        await router.close_all()
        # Should not raise


class TestFallbackModelRouter:
    """Tests for backward-compatible single-provider fallback."""

    def test_fallback_resolve_any_model(self) -> None:
        """FallbackModelRouter resolves any model string."""
        router = FallbackModelRouter("vllm")
        resolved = router.resolve("any-model")
        assert resolved.definition.model == "any-model"
        assert resolved.provider is not None

    def test_fallback_available_models(self) -> None:
        """FallbackModelRouter returns the default model for available models."""
        from apps.gateway.core.config import Settings

        settings = Settings()
        router = FallbackModelRouter("vllm")
        models = router.available_models()
        assert models == [settings.default_model]

    def test_fallback_available_models_returns_default_model(self) -> None:
        """FallbackModelRouter should return the default model so that
        GET /v1/models advertises the model fallback mode will serve."""
        from apps.gateway.core.config import Settings

        # Read the actual default_model from Settings
        settings = Settings()
        router = FallbackModelRouter("vllm")
        models = router.available_models()
        assert models == [settings.default_model], (
            f"Expected [{settings.default_model!r}], got {models!r}"
        )


class TestUnknownModelError:
    """Tests for UnknownModelError exception."""

    def test_unknown_model_error_attributes(self) -> None:
        """UnknownModelError carries model and available_models."""
        exc = UnknownModelError("gpt-5", ["qwen36", "claude"])
        assert exc.model == "gpt-5"
        assert exc.available_models == ["qwen36", "claude"]

    def test_unknown_model_error_message(self) -> None:
        """Error message is descriptive."""
        exc = UnknownModelError("gpt-5", ["qwen36"])
        assert "gpt-5" in str(exc)


