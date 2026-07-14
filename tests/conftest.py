"""Shared test configuration.

Sets ``VLLM_BASE_URL`` to the shared DGX server before any imports
that read it, so all tests can use the real vLLM instance.
"""

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# The shared DGX vLLM server used for integration and streaming tests.
_VLLM_BASE_URL = "http://100.106.236.88:8000/v1"

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
