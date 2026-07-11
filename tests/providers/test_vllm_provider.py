"""Tests for vLLM provider implementation."""

from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.fixture
def mock_httpx_client() -> Any:
    """Provide a mocked httpx.AsyncClient.

    Patches httpx.AsyncClient at the top-level httpx module so that
    the vllm module still has access to real httpx exception classes
    (httpx.ConnectError, httpx.HTTPStatusError, etc.).
    """
    # Save original reference BEFORE entering patch context
    original_async_client = httpx.AsyncClient
    with patch("httpx.AsyncClient") as MockClient:  # noqa: SIM115
        client_instance = AsyncMock(spec=original_async_client)
        MockClient.return_value = client_instance  # noqa: SIM103
        yield client_instance  # noqa: SIM103


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

    @pytest.mark.asyncio
    async def test_streaming_returns_generator(self, mock_httpx_client: AsyncMock) -> None:
        """Test that streaming returns a dict with generator."""
        client_instance = mock_httpx_client

        async def mock_aiter_lines() -> AsyncGenerator[str, None]:
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant"}}]}'
            yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: [DONE]'

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = AsyncMock(side_effect=mock_aiter_lines)  # noqa: SIM103
        client_instance.stream = AsyncMock(return_value=mock_response)  # noqa: SIM103

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
        mock_response.raise_for_status = MagicMock(side_effect=http_error)
        client_instance.stream = AsyncMock(return_value=mock_response)  # noqa: SIM103

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
        client_instance.stream = AsyncMock(side_effect=httpx.ConnectError("Refused"))  # noqa: SIM103

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


class TestVLLMProviderCreateStreamingResponse:
    """Test create_streaming_response helper method."""

    @pytest.mark.asyncio
    async def test_create_streaming_response_success(self, mock_httpx_client: AsyncMock) -> None:
        """Test creating a StreamingResponse from streaming result."""
        # fixture provides mock but this test doesn't need it
        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()

        async def dummy_generator() -> AsyncGenerator[str, None]:
            yield 'data: {"test": true}\n'

        result: dict[str, Any] = {"generator": dummy_generator, "media_type": "text/event-stream"}

        response = await provider.create_streaming_response(result)

        from fastapi.responses import StreamingResponse

        assert isinstance(response, StreamingResponse)

    @pytest.mark.asyncio
    async def test_create_streaming_response_no_generator(
        self, mock_httpx_client: AsyncMock
    ) -> None:
        """Test create_streaming_response without generator raises error."""
        # fixture provides mock but this test doesn't need it
        from packages.providers.vllm import VLLMProvider

        provider = VLLMProvider()
        result: dict[str, Any] = {"media_type": "text/event-stream"}

        with pytest.raises(ProviderResponseError):
            await provider.create_streaming_response(result)


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
        custom_config = _make_mock_config(
            base_url="http://config-test.local:8000/v1",
            api_key="config-api-key",
            request_timeout=45.0,
            default_model="config-model",
        )
        with patch("packages.providers.vllm.load_config", return_value=custom_config):
            from packages.providers.vllm import _get_vllm_config

            config = _get_vllm_config()
            assert config["VLLM_BASE_URL"] == "http://config-test.local:8000/v1"
            assert config["VLLM_API_KEY"] == "config-api-key"
            assert config["REQUEST_TIMEOUT"] == 45.0
            assert config["DEFAULT_MODEL"] == "config-model"

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
