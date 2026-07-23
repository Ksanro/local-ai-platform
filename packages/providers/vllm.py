"""vLLM (OpenAI-compatible) provider implementation."""

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from packages.config import load_config
from packages.providers.base import Provider
from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
)
from packages.providers.registry import register

logger = logging.getLogger(__name__)


def _get_vllm_config(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Load vLLM configuration from config file or environment variables.

    Reads the ``providers.vllm`` section from the config file and
    resolves each value by checking the corresponding environment
    variable first. Environment variables take precedence.

    When explicit parameters are provided, they override the
    environment-derived values.

    Args:
        base_url: Explicit base URL override.
        api_key: Explicit API key override.
        timeout: Explicit timeout override.

    Returns:
        A dict with keys ``VLLM_BASE_URL``, ``VLLM_API_KEY``,
        ``REQUEST_TIMEOUT``, and ``DEFAULT_MODEL``.
    """
    config = load_config()
    providers_config = config.get("providers", {})
    vllm_config = providers_config.get("vllm", {})

    # Resolve base_url: explicit > env > default
    if base_url is not None:
        resolved_base_url = base_url
    else:
        resolved_base_url = _resolve_config_value(
            "VLLM_BASE_URL",
            vllm_config.get("base_url", "http://localhost:8000/v1"),
        )

    # Resolve api_key: explicit > env > default
    if api_key is not None:
        resolved_api_key = api_key
    else:
        resolved_api_key = _resolve_config_value(
            "VLLM_API_KEY",
            vllm_config.get("api_key", "empty"),
        )

    # Resolve timeout: explicit > env > default
    if timeout is not None:
        resolved_timeout = timeout
    else:
        resolved_timeout = _resolve_config_value(
            "REQUEST_TIMEOUT",
            vllm_config.get("request_timeout", 60.0),
        )

    return {
        "VLLM_BASE_URL": resolved_base_url,
        "VLLM_API_KEY": resolved_api_key,
        "REQUEST_TIMEOUT": resolved_timeout,
        "DEFAULT_MODEL": _resolve_config_value(
            "DEFAULT_MODEL",
            vllm_config.get("default_model", "default-model"),
        ),
    }


def _resolve_config_value(key: str, default: Any) -> Any:
    """Resolve a config value from environment variable or config file.

    Environment variables take precedence over config file values.
    """
    env_value = os.environ.get(key)
    if env_value is not None:
        # Convert to appropriate type
        if isinstance(default, float):
            return float(env_value)
        if isinstance(default, int):
            return int(env_value)
        if isinstance(default, bool):
            return env_value.lower() in ("true", "1", "yes")
        return env_value
    return default


class VLLMProvider(Provider):
    """vLLM provider that proxies OpenAI-compatible requests."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the vLLM provider with optional explicit config.

        When explicit values are provided they override environment-derived
        config. When all values are ``None``, config is loaded from the
        environment as before.

        Args:
            base_url: Explicit base URL for the vLLM backend.
            api_key: Explicit API key for authentication.
            timeout: Explicit request timeout in seconds.
        """
        self._client: httpx.AsyncClient | None = None
        self._config = _get_vllm_config(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client. Uses a singleton pattern.

        Creates the client on first call with base URL, API key,
        and timeout from config. Subsequent calls return the same
        instance.

        Returns:
            The httpx async client instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config["VLLM_BASE_URL"],
                headers={
                    "Authorization": f"Bearer {self._config['VLLM_API_KEY']}",
                    "Content-Type": "application/json",
                },
                timeout=self._config["REQUEST_TIMEOUT"],
            )
        return self._client

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client exists, creating if needed."""
        client = self._get_client()
        if client is None:
            raise ProviderConnectionError("vLLM client not initialized")
        return client

    async def health(self) -> dict[str, Any]:
        """Check vLLM health via /models endpoint."""
        client = await self._ensure_client()
        try:
            response = await client.get("/models")
            if response.status_code == 200:
                return {"healthy": True, "status": "ok"}
            return {"healthy": False, "status": "unhealthy", "status_code": response.status_code}
        except httpx.ConnectError as exc:
            logger.error("vLLM health check failed: %s", exc)
            return {"healthy": False, "error": str(exc)}
        except httpx.TimeoutException as exc:
            logger.error("vLLM health check timeout: %s", exc)
            return {"healthy": False, "error": str(exc)}
        except Exception as exc:
            logger.error("vLLM health check error: %s", exc)
            return {"healthy": False, "error": str(exc)}

    async def models(self) -> list[str]:
        """List available vLLM models."""
        client = await self._ensure_client()
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
            raise ProviderConnectionError("Timeout while listing models") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(f"Connection failed while listing models: {exc}") from exc

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        """Forward chat completion request to vLLM.

        If stream=True is passed, returns a dict with generator and media_type.
        Otherwise returns the parsed JSON response as a dict.
        """
        client = await self._ensure_client()
        is_stream = kwargs.get("stream", False)

        try:
            if is_stream:
                return await self._stream_chat(client, kwargs)
            else:
                response = await client.post("/chat/completions", json=kwargs)
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                raise ProviderAuthenticationError(
                    f"vLLM authentication failed: {exc.response.status_code} {exc.response.text}"
                ) from exc
            raise ProviderResponseError(
                f"vLLM request failed: {status_code} {exc.response.text}",
                status_code=status_code,
                body=exc.response.text,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderConnectionError("vLLM request timed out") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(f"Connection to vLLM failed: {exc}") from exc

    async def _stream_chat(
        self, client: httpx.AsyncClient, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle streaming chat completions.

        Returns a StreamingResponse for the gateway to send to the client.
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
                        if line:
                            if line.startswith("data: "):
                                yield line + "\n\n"
                            elif line.strip():
                                yield f"data: {line}\n\n"
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                error_data: dict[str, Any] = {
                    "error": {
                        "message": exc.response.text,
                        "type": "http_error",
                        "code": status_code,
                    }
                }
                error_event = f"data: {self._json_encode(error_data)}\n\n"
                yield error_event
            except Exception as exc:
                error_data2: dict[str, Any] = {
                    "error": {
                        "message": str(exc),
                        "type": "request_error",
                        "code": 500,
                    }
                }
                error_event = f"data: {self._json_encode(error_data2)}\n\n"
                yield error_event

        return {
            "generator": event_generator,
            "media_type": "text/event-stream",
        }

    @staticmethod
    def _json_encode(data: Any) -> str:
        """Encode data to JSON string."""
        return json.dumps(data)

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Auto-register vllm provider
register("vllm", VLLMProvider)
