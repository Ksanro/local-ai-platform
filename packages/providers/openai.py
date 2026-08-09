"""Generic OpenAI-compatible provider implementation.

Implements the standard OpenAI Chat Completions protocol without
vLLM-specific response cleanup (think-block stripping, etc.).

Supports two configuration modes:

1. **Explicit kwargs** (recommended): the router or factory passes
   ``base_url``, ``api_key``, and ``timeout`` directly.

2. **Environment-variable fallback**: when all constructor arguments are
   ``None``, the provider reads ``OPENAI_BASE_URL``, ``OPENAI_API_KEY``,
   and ``REQUEST_TIMEOUT`` from the environment.  This provides parity
   with ``VLLMProvider`` and ensures ``APP_DEFAULT_PROVIDER=openai``
   works correctly in ``FallbackModelRouter`` mode.

Responses are passed through unchanged – no think-block stripping or
other vLLM-specific sanitization is applied.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from packages.providers.base import Provider
from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
)
from packages.providers.registry import register

logger = logging.getLogger(__name__)


def _get_openai_config(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Load OpenAI-compatible configuration from environment variables.

    When explicit parameters are provided they override the environment
    values.  When all parameters are ``None`` the provider falls back
    to environment variables (``OPENAI_BASE_URL``, ``OPENAI_API_KEY``,
    ``REQUEST_TIMEOUT``) for parity with ``VLLMProvider``.

    Args:
        base_url: Explicit base URL override.
        api_key: Explicit API key override.
        timeout: Explicit timeout override.

    Returns:
        A dict with keys ``base_url``, ``api_key``, and ``timeout``.
    """
    resolved_base_url = (
        base_url
        if base_url is not None
        else os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
    )

    resolved_api_key = (
        api_key
        if api_key is not None
        else os.environ.get("OPENAI_API_KEY", "empty")
    )

    if timeout is not None:
        resolved_timeout: float = timeout
    else:
        env_timeout = os.environ.get("REQUEST_TIMEOUT")
        if env_timeout is not None:
            resolved_timeout = float(env_timeout)
        else:
            resolved_timeout = 60.0

    return {
        "base_url": resolved_base_url,
        "api_key": resolved_api_key,
        "timeout": resolved_timeout,
    }


class OpenAIProvider(Provider):
    """Generic OpenAI-compatible provider.

    Speaks the standard OpenAI Chat Completions protocol without
    vLLM-specific response sanitization.  Responses are passed
    through unchanged.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the OpenAI-compatible provider.

        When explicit values are provided they take priority.  When all
        values are ``None`` configuration is loaded from environment
        variables (``OPENAI_BASE_URL``, ``OPENAI_API_KEY``,
        ``REQUEST_TIMEOUT``).

        Args:
            base_url: Base URL for the OpenAI-compatible backend.
            api_key: API key for authentication.
            timeout: Request timeout in seconds.
        """
        self._client: httpx.AsyncClient | None = None
        self._config = _get_openai_config(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client.

        Creates the client on first call with the configured base URL,
        API key, and timeout.  Subsequent calls return the same
        instance.

        Returns:
            The httpx async client instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config["base_url"],
                headers={
                    "Authorization": f"Bearer {self._config['api_key']}",
                    "Content-Type": "application/json",
                },
                timeout=self._config["timeout"],
            )
        return self._client

    async def health(self) -> dict[str, Any]:
        """Check provider health via GET /models."""
        client = self._get_client()
        try:
            response = await client.get("/models")
            if response.status_code == 200:
                return {"healthy": True, "status": "ok"}
            return {
                "healthy": False,
                "status": "unhealthy",
                "status_code": response.status_code,
            }
        except httpx.ConnectError as exc:
            logger.error("OpenAI provider health check failed: %s", exc)
            return {"healthy": False, "error": str(exc)}
        except httpx.TimeoutException as exc:
            logger.error("OpenAI provider health check timeout: %s", exc)
            return {"healthy": False, "error": str(exc)}
        except Exception as exc:
            logger.error("OpenAI provider health check error: %s", exc)
            return {"healthy": False, "error": str(exc)}

    async def models(self) -> list[str]:
        """List available models via GET /models.

        Parses the standard OpenAI model-list response shape
        ``{"data": [{"id": "..."}]}`` and returns a list of model
        identifier strings.
        """
        client = self._get_client()
        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            model_ids: list[str] = []
            if "data" in data:
                for model in data["data"]:
                    if "id" in model:
                        model_ids.append(model["id"])
            return model_ids
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(
                f"Failed to list models: {exc.response.status_code} {exc.response.text}",
                status_code=exc.response.status_code,
                body=exc.response.text,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderConnectionError(
                "Timeout while listing models"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(
                f"Connection failed while listing models: {exc}"
            ) from exc

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        """Forward chat completion request to the OpenAI-compatible backend.

        If ``stream=True`` is passed, returns a dict with ``generator``
        and ``media_type``.  Otherwise returns the parsed JSON response
        as a dict, passed through unchanged (no sanitization).
        """
        client = self._get_client()
        is_stream = kwargs.get("stream", False)

        try:
            if is_stream:
                return await self._stream_chat(client, kwargs)
            else:
                response = await client.post("/chat/completions", json=kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                raise ProviderAuthenticationError(
                    f"Authentication failed: {exc.response.status_code} {exc.response.text}"
                ) from exc
            raise ProviderResponseError(
                f"Request failed: {status_code} {exc.response.text}",
                status_code=status_code,
                body=exc.response.text,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderConnectionError("Request timed out") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(
                f"Connection failed: {exc}"
            ) from exc

    async def _stream_chat(
        self, client: httpx.AsyncClient, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle streaming chat completions.

        Returns a StreamingResponse for the gateway to send to the
        client.  Deltas are passed through unchanged (no sanitization).
        """

        async def event_generator() -> AsyncIterator[str]:
            """Generate SSE events from the streaming response."""
            try:
                async with client.stream(
                    "POST",
                    "/chat/completions",
                    json=kwargs,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        data = (
                            line.removeprefix("data:").strip()
                            if line.startswith("data:")
                            else line.strip()
                        )
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            continue
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            yield f"data: {data}\n\n"
                            continue
                        if not isinstance(parsed, dict):
                            yield f"data: {data}\n\n"
                            continue
                        yield f"data: {json.dumps(parsed)}\n\n"
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                error_data: dict[str, Any] = {
                    "error": {
                        "message": exc.response.text,
                        "type": "http_error",
                        "code": status_code,
                    }
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            except Exception as exc:
                error_data2: dict[str, Any] = {
                    "error": {
                        "message": str(exc),
                        "type": "request_error",
                        "code": 500,
                    }
                }
                yield f"data: {json.dumps(error_data2)}\n\n"

        return {
            "generator": event_generator,
            "media_type": "text/event-stream",
        }

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Auto-register openai provider
register("openai", OpenAIProvider)
