"""Tests for vLLM provider implementation."""

from __future__ import annotations

import importlib
import json
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from typing_extensions import AsyncGenerator, Generator

from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
)
from packages.providers.registry import get_registry, has_provider


@pytest.fixture(autouse=True)
def _clear_vllm_module() -> Generator[None, None, None]:
    """Clear module-level state before and after each test."""
    # Clear before by reloading the module
    if "packages.providers.vllm" in sys.modules:
        importlib.reload(sys.modules["packages.providers.vllm"])

    yield

    # Clear after by reloading the module
    if "packages.providers.vllm" in sys.modules:
        importlib.reload(sys.modules["packages.providers.vllm"])


def _make_mock_config(
    base_url: str = "http://localhost:8000/v1",
    api_key: str = "test-api-key",
    request_timeout: float = 30.0,
    default_model: str = "test-model",
) -> dict[str, Any]:
    """Create a mock config dict."""
    return {
        "providers": {
            "vllm": {
                "base_url": base_url,
                "api_key": api_key,
                "request_timeout": request_timeout,
                "default_model": default_model,
            }
        }
    }


class TestVLLMProviderRegistration:
    """Test vLLM provider registration."""

    def test_vllm_registered(self) -> None:
        """Test that vllm provider is registered."""
        # Import triggers registration
        import packages.providers.vllm  # noqa: F401

        assert has_provider("vllm")
        registry = get_registry()
        assert "vllm" in registry

    def test_vllm_provider_class(self) -> None:
        """Test that registered vllm provider is VLLMProvider class."""
        import packages.providers.vllm  # noqa: F401
        from packages.providers.vllm import VLLMProvider

        registry = get_registry()
        assert registry["vllm"] is VLLMProvider


class TestVLLMProviderHealth:
    """Test vLLM provider health check."""

    @pytest.mark.asyncio
    async def test_health_healthy(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check when vLLM is healthy."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(return_value=MagicMock(status_code=200))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.health()

        assert result["healthy"] is True
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_unhealthy_status(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check when vLLM returns non-200 status."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(return_value=MagicMock(status_code=503))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert result["status_code"] == 503

    @pytest.mark.asyncio
    async def test_health_connect_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check on connection error."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_health_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check on timeout."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert "error" in result


class TestVLLMProviderModels:
    """Test vLLM provider models listing."""

    @pytest.mark.asyncio
    async def test_models_success(self, mock_httpx_client: AsyncMock) -> None:
        """Test successful models listing."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "model-1"},
                {"id": "model-2"},
                {"id": "model-3"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.get = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.models()

        assert result == ["model-1", "model-2", "model-3"]

    @pytest.mark.asyncio
    async def test_models_empty(self, mock_httpx_client: AsyncMock) -> None:
        """Test models listing with no models."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = MagicMock()
        client_instance.get = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.models()

        assert result == []

    @pytest.mark.asyncio
    async def test_models_response_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test models listing with response error."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        http_error = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_response
        )
        client_instance.get = AsyncMock(side_effect=http_error)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderResponseError):
            await provider.models()

    @pytest.mark.asyncio
    async def test_models_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test models listing on timeout."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.models()


class TestVLLMProviderChat:
    """Test vLLM provider chat completion."""

    @pytest.mark.asyncio
    async def test_chat_success(self, mock_httpx_client: AsyncMock) -> None:
        """Test successful chat completion."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        payload: dict[str, Any] = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert result["id"] == "chatcmpl-123"
        assert result["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_strips_leading_empty_think_block(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Non-streaming chat strips an empty leading think block."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "<think>\n\n</think>\n\nHello!",
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.chat(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_preserves_nonempty_think_block(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Non-streaming chat preserves non-empty leading think blocks."""
        client_instance = mock_httpx_client
        content = "<think>real reasoning</think>Final"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.chat(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result["choices"][0]["message"]["content"] == content

    @pytest.mark.asyncio
    async def test_chat_preserves_mid_answer_think_block(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Non-streaming chat preserves think blocks that are not leading."""
        client_instance = mock_httpx_client
        content = "Answer <think></think>"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.chat(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result["choices"][0]["message"]["content"] == content

    @pytest.mark.asyncio
    async def test_chat_forwards_payload_unchanged(self, mock_httpx_client: AsyncMock) -> None:
        """Test that chat payload is forwarded unchanged."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "chatcmpl-456"}
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        payload: dict[str, Any] = {
            "model": "llama-3",
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False,
        }
        result = await provider.chat(**payload)
        assert isinstance(result, dict)

        # Verify the payload was forwarded as-is
        call_args = client_instance.post.call_args
        assert call_args[1]["json"] == payload  # noqa: SIM103

    @pytest.mark.asyncio
    async def test_chat_401_authentication_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test that 401 raises ProviderAuthenticationError."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        http_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        client_instance.post = AsyncMock(side_effect=http_error)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderAuthenticationError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_chat_500_response_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test that 500 raises ProviderResponseError."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        http_error = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_response
        )
        client_instance.post = AsyncMock(side_effect=http_error)  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderResponseError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_chat_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test chat on timeout."""
        client_instance = mock_httpx_client
        client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_chat_connection_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test chat on connection error."""
        client_instance = mock_httpx_client
        client_instance.post = AsyncMock(side_effect=httpx.ConnectError("Refused"))  # noqa: SIM103

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])


class TestVLLMProviderStreaming:
    """Test vLLM provider streaming."""

    async def _stream_events(
        self,
        mock_httpx_client: AsyncMock,
        lines: list[str],
    ) -> list[str]:
        """Run a mocked streaming call and return emitted SSE events."""
        client_instance = mock_httpx_client

        async def mock_aiter_lines() -> AsyncGenerator[str, None]:
            for line in lines:
                yield line

        mock_response = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = Mock(side_effect=mock_aiter_lines)  # noqa: SIM103
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result = await provider.chat(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )

        events: list[str] = []
        async for event in result["generator"]():
            events.append(event)
        return events

    def _event_content(self, event: str) -> str:
        """Extract first delta content from one emitted SSE event."""
        data = event.removeprefix("data: ").strip()
        parsed = json.loads(data)
        return parsed["choices"][0]["delta"]["content"]

    @pytest.mark.asyncio
    async def test_streaming_returns_generator(self, mock_httpx_client: AsyncMock) -> None:
        """Test that streaming returns a dict with generator."""
        client_instance = mock_httpx_client

        async def mock_aiter_lines() -> AsyncGenerator[str, None]:
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant"}}]}'
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: [DONE]'

        mock_response = MagicMock()
        # Explicitly set __aenter__/__aexit__ to avoid MagicMock creating
        # coroutine wrappers for the async context manager protocol.
        mock_response.__aenter__ = Mock(return_value=mock_response)
        mock_response.__aexit__ = Mock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        # Use regular Mock (not AsyncMock) for aiter_lines – calling it
        # returns the async generator directly, not a coroutine.
        mock_response.aiter_lines = Mock(side_effect=mock_aiter_lines)  # noqa: SIM103
        # Use regular Mock (not AsyncMock) to avoid coroutine warnings –
        # the code uses ``async with client.stream(...)`` so the result must
        # be an awaitable async-context-manager, not a bare coroutine.
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        payload: dict[str, Any] = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert "generator" in result
        assert "media_type" in result
        assert result["media_type"] == "text/event-stream"
        assert callable(result["generator"])

    @pytest.mark.asyncio
    async def test_streaming_error_handling(self, mock_httpx_client: AsyncMock) -> None:
        """Test streaming error handling."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        http_error = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        # Explicitly set __aenter__/__aexit__ to avoid MagicMock creating
        # coroutine wrappers for the async context manager protocol.
        mock_response.__aenter__ = Mock(return_value=mock_response)
        mock_response.__aexit__ = Mock(return_value=None)
        # Use regular Mock (not AsyncMock) – MagicMock creates coroutine
        # wrappers by default; plain Mock avoids the RuntimeWarning.
        mock_response.raise_for_status = Mock(side_effect=http_error)
        # Use regular Mock (not AsyncMock) to avoid coroutine warnings.
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        payload: dict[str, Any] = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert "generator" in result

        # Consume the generator to verify error event
        events: list[str] = []
        async for event in result["generator"]():  # noqa: B007
            events.append(event)

        # Should have an error event
        error_found = any('"error"' in event for event in events)
        assert error_found is True

    @pytest.mark.asyncio
    async def test_streaming_connection_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test streaming connection error."""
        client_instance = mock_httpx_client
        # Use regular Mock (not AsyncMock) to avoid coroutine warnings.
        client_instance.stream = Mock(side_effect=httpx.ConnectError("Refused"))  # noqa: F821

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        payload: dict[str, Any] = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert "generator" in result

        # Consume generator to get error event
        events: list[str] = []
        async for event in result["generator"]():  # noqa: B007
            events.append(event)

        error_found = any('"error"' in event for event in events)
        assert error_found is True

    @pytest.mark.asyncio
    async def test_streaming_strips_leading_empty_think_block_one_delta(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming strips a leading empty think block from one delta."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                (
                    'data: {"choices":[{"delta":{"content":'
                    '"<think>\\n\\n</think>\\n\\nHello"}}]}'
                ),
                "data: [DONE]",
            ],
        )

        assert self._event_content(events[0]) == "Hello"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_strips_data_prefix_without_space(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming accepts SSE data prefix with no following space."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                (
                    'data:{"choices":[{"delta":{"content":'
                    '"<think>\\n\\n</think>\\n\\nHello"}}]}'
                ),
                "data:[DONE]",
            ],
        )

        assert self._event_content(events[0]) == "Hello"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_strips_leading_empty_think_block_split_deltas(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming strips an empty think block split across initial deltas."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                'data: {"choices":[{"delta":{"content":"<think>\\n"}}]}',
                'data: {"choices":[{"delta":{"content":"\\n</think>\\n\\nHel"}}]}',
                'data: {"choices":[{"delta":{"content":"lo"}}]}',
                "data: [DONE]",
            ],
        )

        assert self._event_content(events[0]) == "Hel"
        assert self._event_content(events[1]) == ""
        assert self._event_content(events[2]) == "lo"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_preserves_nonempty_think_block(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming preserves non-empty leading think blocks."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                'data: {"choices":[{"delta":{"content":"<think>real"}}]}',
                'data: {"choices":[{"delta":{"content":" reasoning</think>Final"}}]}',
                "data: [DONE]",
            ],
        )

        assert self._event_content(events[0]) == "<think>real"
        assert self._event_content(events[1]) == " reasoning</think>Final"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_preserves_mid_answer_think_block(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming preserves think blocks that are not leading."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                'data: {"choices":[{"delta":{"content":"Answer <think></think>"}}]}',
                "data: [DONE]",
            ],
        )

        assert self._event_content(events[0]) == "Answer <think></think>"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_forwards_role_only_delta_before_sanitizing(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming forwards non-content deltas and still strips later prefix."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                (
                    'data: {"choices":[{"delta":{"content":'
                    '"<think>\\n\\n</think>\\n\\nHello"}}]}'
                ),
                "data: [DONE]",
            ],
        )

        first = json.loads(events[0].removeprefix("data: ").strip())
        assert first["choices"][0]["delta"] == {"role": "assistant"}
        assert self._event_content(events[1]) == "Hello"
        assert events[-1] == "data: [DONE]\n\n"


class TestVLLMProviderClose:
    """Test vLLM provider close method."""

    @pytest.mark.asyncio
    async def test_close_client(self, mock_httpx_client: AsyncMock) -> None:
        """Test that close closes the httpx client."""
        client_instance = mock_httpx_client

        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        # Access client to create it
        await provider._ensure_client()

        await provider.close()

        assert provider._client is None
        client_instance.aclose.assert_called_once()


class TestVLLMProviderConfig:
    """Test vLLM provider configuration loading."""

    def test_config_loads_from_file(self) -> None:
        """Test that config is loaded from config file."""
        import os

        # Clear env vars so the config file value takes precedence.
        saved = {}
        for key in ("VLLM_BASE_URL", "DEFAULT_MODEL", "VLLM_API_KEY", "REQUEST_TIMEOUT"):
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        try:
            custom_config = _make_mock_config(
                base_url="http://config-test.local:8000/v1",
                api_key="config-api-key",
                request_timeout=45.0,
                default_model="config-model",
            )
            with patch(
                "packages.providers.vllm.load_config", return_value=custom_config
            ):
                from packages.providers.vllm import _get_vllm_config

                config = _get_vllm_config()
                assert config["VLLM_BASE_URL"] == "http://config-test.local:8000/v1"
                assert config["VLLM_API_KEY"] == "config-api-key"
                assert config["REQUEST_TIMEOUT"] == 45.0
                assert config["DEFAULT_MODEL"] == "config-model"
        finally:
            for key, val in saved.items():
                os.environ[key] = val

    def test_env_overrides_config(self) -> None:
        """Test that environment variables override config file values."""
        import os

        custom_config = _make_mock_config()
        with patch("packages.providers.vllm.load_config", return_value=custom_config):
            with patch.dict(
                os.environ,
                {
                    "VLLM_BASE_URL": "http://override.local:9000/v1",
                    "VLLM_API_KEY": "env-api-key",
                },
                clear=True,
            ):
                from packages.providers.vllm import _get_vllm_config

                config = _get_vllm_config()
                assert config["VLLM_BASE_URL"] == "http://override.local:9000/v1"
                assert config["VLLM_API_KEY"] == "env-api-key"
                # Non-overridden values should come from config file
                assert config["REQUEST_TIMEOUT"] == 30.0

    def test_config_with_float_conversion(self) -> None:
        """Test that config values are properly typed when from config file."""
        custom_config: dict[str, Any] = {
            "providers": {
                "vllm": {
                    "base_url": "http://test.local:8080/v1",
                    "api_key": "test-key",
                    "request_timeout": 45.5,
                    "default_model": "test-model",
                }
            }
        }
        with patch("packages.providers.vllm.load_config", return_value=custom_config):
            import os

            # Clear env vars to test config file parsing
            with patch.dict(os.environ, {}, clear=True):
                from packages.providers.vllm import _get_vllm_config

                config = _get_vllm_config()
                assert config["REQUEST_TIMEOUT"] == 45.5
                assert isinstance(config["REQUEST_TIMEOUT"], float)
