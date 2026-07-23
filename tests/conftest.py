"""Shared test configuration.

Sets ``VLLM_BASE_URL`` to the shared DGX server before any imports
that read it, so all tests can use the real vLLM instance.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# The shared DGX vLLM server used for integration and streaming tests.
_VLLM_BASE_URL = "http://100.106.236.88:8001/v1"

# Set it early — vLLM provider reads it during module initialisation
# (via ``_resolve_config_value`` in ``packages.providers.vllm``).
if "VLLM_BASE_URL" not in os.environ:
    os.environ["VLLM_BASE_URL"] = _VLLM_BASE_URL

# Also ensure the gateway knows which provider to use.
if "DEFAULT_PROVIDER" not in os.environ:
    os.environ["DEFAULT_PROVIDER"] = "vllm"

# Integration tests read DEFAULT_MODEL at module import time.
if "DEFAULT_MODEL" not in os.environ:
    os.environ["DEFAULT_MODEL"] = "qwen36"


@pytest.fixture(autouse=True)
def _ensure_providers_loaded() -> None:
    """Ensure provider modules are imported (triggering auto-registration).

    The conftest sets environment variables before imports, but the actual
    provider registration happens when ``_load_providers()`` is called.
    This autouse fixture guarantees the call runs before any test.
    """
    from packages.providers import _load_providers

    _load_providers()


@pytest.fixture(autouse=True)
def _ensure_serializers_loaded() -> None:
    """Ensure serializer modules are imported and registered.

    Serializers register themselves in the global registry when their
    module is imported. This fixture guarantees that import happens
    before any test runs, so the registry is populated regardless of
    test execution order.
    """
    # Import the module to trigger auto-registration.
    import packages.serializers.openai  # noqa: F401

    # Ensure the serializer is actually registered (re-register if it was
    # unregistered by a previous test).
    from packages.serializers.registry import has_serializer, register
    from packages.serializers.types import ProviderType

    if not has_serializer(ProviderType.openai):
        from packages.serializers.openai import OpenAISerializer

        register(ProviderType.openai, OpenAISerializer)


@pytest.fixture(autouse=True)
def _guard_network_calls(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Prevent unit tests from making real network calls.

    Monkeypatches ``httpx.AsyncClient.send`` to raise an AssertionError
    if any test (outside ``tests/integration/``) attempts to open an
    HTTP connection.  Integration tests are exempt because they live
    under the ``tests/integration/`` directory.
    """
    if "integration" in str(request.node.fspath):
        yield
        return

    async def _blocking_send(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "Unit tests must not make network calls. "
            "Use a mock or stub pipeline instead."
        )

    with patch.object(
        httpx.AsyncClient, "send", _blocking_send
    ):
        yield


@pytest.fixture
def mock_httpx_client() -> Any:
    """Provide a mocked httpx.AsyncClient.

    Patches httpx.AsyncClient at the top-level httpx module so that
    the vllm module still has access to real httpx exception classes
    (httpx.ConnectError, httpx.HTTPStatusError, etc.).

    Returns:
        An AsyncMock that acts as the httpx.AsyncClient instance.
    """
    # Save original reference BEFORE entering patch context
    original_async_client = httpx.AsyncClient
    with patch("httpx.AsyncClient") as MockClient:  # noqa: SIM115
        client_instance = AsyncMock(spec=original_async_client)
        MockClient.return_value = client_instance  # noqa: SIM103
        yield client_instance  # noqa: SIM103
