"""Tests for OpenAI-compatible provider implementation."""

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
def _clear_openai_module() -> Generator[None, None, None]:
    """Clear module-level state before and after each test."""
    if "packages.providers.openai" in sys.modules:
        importlib.reload(sys.modules["packages.providers.openai"])

    yield

    if "packages.providers.openai" in sys.modules:
        importlib.reload(sys.modules["packages.providers.openai"])


class TestOpenAIProviderRegistration:
    """Test OpenAI provider registration."""

    def test_openai_registered(self) -> None:
        """Test that openai provider is registered."""
        import packages.providers.openai  # noqa: F401

        assert has_provider("openai")
        registry = get_registry()
        assert "openai" in registry

    def test_openai_provider_class(self) -> None:
        """Test that registered openai provider is OpenAIProvider class."""
        import packages.providers.openai  # noqa: F401
        from packages.providers.openai import OpenAIProvider

        registry = get_registry()
        assert registry["openai"] is OpenAIProvider


class TestOpenAIProviderHealth:
    """Test OpenAI provider health check."""

    @pytest.mark.asyncio
    async def test_health_healthy(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check when provider is healthy."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(return_value=MagicMock(status_code=200))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        result = await provider.health()

        assert result["healthy"] is True
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_unhealthy_status(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check when provider returns non-200 status."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(return_value=MagicMock(status_code=503))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert result["status_code"] == 503

    @pytest.mark.asyncio
    async def test_health_connect_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check on connection error."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_health_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test health check on timeout."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        result = await provider.health()

        assert result["healthy"] is False
        assert "error" in result


class TestOpenAIProviderModels:
    """Test OpenAI provider models listing."""

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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(ProviderResponseError):
            await provider.models()

    @pytest.mark.asyncio
    async def test_models_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test models listing on timeout."""
        client_instance = mock_httpx_client
        client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.models()


class TestOpenAIProviderChat:
    """Test OpenAI provider chat completion."""

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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        payload: dict[str, Any] = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert result["id"] == "chatcmpl-123"
        assert result["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_passes_response_unchanged(self, mock_httpx_client: AsyncMock) -> None:
        """Non-streaming chat passes responses through unchanged (no sanitization)."""
        client_instance = mock_httpx_client
        # Response contains a think block — provider should NOT strip it
        content = "<think></think>Hello!"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        result = await provider.chat(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
        )

        # Content passed through unchanged — no think-block stripping
        assert result["choices"][0]["message"]["content"] == content

    @pytest.mark.asyncio
    async def test_chat_forwards_payload_unchanged(self, mock_httpx_client: AsyncMock) -> None:
        """Test that chat payload is forwarded unchanged."""
        client_instance = mock_httpx_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "chatcmpl-456"}
        mock_response.raise_for_status = MagicMock()
        client_instance.post = AsyncMock(return_value=mock_response)  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(ProviderResponseError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_chat_timeout(self, mock_httpx_client: AsyncMock) -> None:
        """Test chat on timeout."""
        client_instance = mock_httpx_client
        client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_chat_connection_error(self, mock_httpx_client: AsyncMock) -> None:
        """Test chat on connection error."""
        client_instance = mock_httpx_client
        client_instance.post = AsyncMock(side_effect=httpx.ConnectError("Refused"))  # noqa: SIM103

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        with pytest.raises(ProviderConnectionError):
            await provider.chat(model="test", messages=[{"role": "user", "content": "Hi"}])


class TestOpenAIProviderStreaming:
    """Test OpenAI provider streaming."""

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

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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
        data_str = event.removeprefix("data: ").strip()
        parsed = json.loads(data_str)
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
        mock_response.__aenter__ = Mock(return_value=mock_response)
        mock_response.__aexit__ = Mock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = Mock(side_effect=mock_aiter_lines)  # noqa: SIM103
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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
        mock_response.__aenter__ = Mock(return_value=mock_response)
        mock_response.__aexit__ = Mock(return_value=None)
        mock_response.raise_for_status = Mock(side_effect=http_error)
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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
        client_instance.stream = Mock(side_effect=httpx.ConnectError("Refused"))  # noqa: F821

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
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
    async def test_streaming_passes_content_unchanged(
        self,
        mock_httpx_client: AsyncMock,
    ) -> None:
        """Streaming passes deltas through unchanged (no sanitization)."""
        events = await self._stream_events(
            mock_httpx_client,
            [
                (
                    'data: {"choices":[{"delta":{"content":'
                    '"<think></think>Hello"}}]}'
                ),
                "data: [DONE]",
            ],
        )

        # Content passed through unchanged — no think-block stripping
        assert self._event_content(events[0]) == "<think></think>Hello"
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_forwards_payload(self, mock_httpx_client: AsyncMock) -> None:
        """Test that streaming forwards the payload correctly."""
        client_instance = mock_httpx_client

        async def mock_aiter_lines() -> AsyncGenerator[str, None]:
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hi"}}]}'
            yield 'data: [DONE]'

        mock_response = MagicMock()
        mock_response.__aenter__ = Mock(return_value=mock_response)
        mock_response.__aexit__ = Mock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = Mock(side_effect=mock_aiter_lines)  # noqa: SIM103
        client_instance.stream = Mock(return_value=mock_response)  # noqa: F821

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        payload: dict[str, Any] = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
            "temperature": 0.5,
        }
        result = await provider.chat(**payload)

        assert isinstance(result, dict)
        assert "generator" in result

        # Consume the generator to trigger the lazy stream call
        events: list[str] = []
        async for event in result["generator"]():  # noqa: B007
            events.append(event)

        # Verify the payload was forwarded (stream called with correct args)
        call_args = client_instance.stream.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/chat/completions"
        assert call_args[1]["json"]["model"] == "gpt-4"  # noqa: SIM103
        assert call_args[1]["json"]["temperature"] == 0.5  # noqa: SIM103


class TestOpenAIProviderClose:
    """Test OpenAI provider close method."""

    @pytest.mark.asyncio
    async def test_close_client(self, mock_httpx_client: AsyncMock) -> None:
        """Test that close closes the httpx client."""
        client_instance = mock_httpx_client

        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        # Access client to create it
        provider._get_client()

        await provider.close()

        assert provider._client is None
        client_instance.aclose.assert_called_once()


class TestOpenAIProviderConfig:
    """Test OpenAI provider configuration loading."""

    def test_config_uses_explicit_kwargs(self) -> None:
        """Test that explicit kwargs override environment."""
        import os

        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "http://env.local:8000/v1",
                "OPENAI_API_KEY": "env-key",
            },
            clear=True,
        ):
            from packages.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                base_url="http://explicit.local:9000/v1",
                api_key="explicit-key",
                timeout=120.0,
            )
            assert provider._config["base_url"] == "http://explicit.local:9000/v1"
            assert provider._config["api_key"] == "explicit-key"
            assert provider._config["timeout"] == 120.0

    def test_config_falls_back_to_env(self) -> None:
        """Test that env vars are used when no explicit kwargs given."""
        import os

        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "http://env.local:8000/v1",
                "OPENAI_API_KEY": "env-key",
                "REQUEST_TIMEOUT": "90",
            },
            clear=True,
        ):
            from packages.providers.openai import OpenAIProvider

            provider = OpenAIProvider()
            assert provider._config["base_url"] == "http://env.local:8000/v1"
            assert provider._config["api_key"] == "env-key"
            assert provider._config["timeout"] == 90.0

    def test_config_defaults_when_no_env(self) -> None:
        """Test hardcoded defaults when no env vars and no kwargs."""
        import os

        with patch.dict(os.environ, {}, clear=True):
            from packages.providers.openai import OpenAIProvider

            provider = OpenAIProvider()
            assert provider._config["base_url"] == "http://localhost:8000/v1"
            assert provider._config["api_key"] == "empty"
            assert provider._config["timeout"] == 60.0
