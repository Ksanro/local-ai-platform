"""Shared test configuration.

Provides fixtures and utilities used across the test suite.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest


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


