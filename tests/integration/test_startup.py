"""Integration test: application startup with RepositoryIndex.

Verifies that the application builds a RepositoryIndex during startup
and wires it into the pipeline.

Tests
-----
- startup builds index
- index is passed to RepositoryContextStage
- repository metrics are logged
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the lifespan function directly.
from apps.gateway.main import lifespan
from packages.repository.index.models import RepositoryIndex


@pytest.mark.asyncio
async def test_startup_builds_repository_index() -> None:
    """Verify that startup builds a RepositoryIndex from the repository path."""
    from apps.gateway.main import create_app

    # Use the project's own tests directory as a test repository.
    test_repo = Path(__file__).resolve().parent.parent

    with patch(
        "apps.gateway.main.get_settings"
    ) as mock_settings:
        mock_settings.return_value.repository_path = str(test_repo)
        mock_settings.return_value.default_provider = "vllm"
        mock_settings.return_value.repository_context_enabled = True
        mock_settings.return_value.log_level = "WARNING"

        app = create_app()

    # Trigger the lifespan to execute startup logic.
    startup_done = False
    async with lifespan(app):
        startup_done = True

    assert startup_done is True

    # Verify the pipeline was created.
    assert hasattr(app.state, "pipeline")
    pipeline = app.state.pipeline

    # Verify the pipeline has stages registered.
    assert hasattr(pipeline, "_stages")
    assert len(pipeline._stages) > 0

    # Check that RepositoryContextStage received a real index.
    from packages.pipeline.stages.repository_context import RepositoryContextStage

    repo_stage = None
    for stage in pipeline._stages:
        if isinstance(stage, RepositoryContextStage):
            repo_stage = stage
            break

    assert repo_stage is not None
    assert repo_stage._index is not None
    assert isinstance(repo_stage._index, RepositoryIndex)

    # Verify the index has content.
    index = repo_stage._index
    stats = index.statistics()
    assert stats.module_count >= 0
    assert stats.symbol_count >= 0


@pytest.mark.asyncio
async def test_startup_logs_repository_metrics() -> None:
    """Verify that startup logs repository metrics."""
    from apps.gateway.main import create_app

    test_repo = Path(__file__).resolve().parent.parent

    # Capture log records.
    log_records: list[logging.LogRecord] = []

    class LogCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    handler = LogCapture()
    logger = logging.getLogger("apps.gateway.main")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        with patch(
            "apps.gateway.main.get_settings"
        ) as mock_settings:
            mock_settings.return_value.repository_path = str(test_repo)
            mock_settings.return_value.default_provider = "vllm"
            mock_settings.return_value.repository_context_enabled = True
            mock_settings.return_value.log_level = "WARNING"

            app = create_app()

        startup_done = False
        async with lifespan(app):
            startup_done = True

        assert startup_done is True

        # Find the repository_index log record.
        found = False
        for record in log_records:
            msg = str(record.msg)
            if "repository_index" in msg and "files=" in msg:
                found = True
                # Verify expected metric fields are present.
                assert "files=" in msg
                assert "modules=" in msg
                assert "symbols=" in msg
                assert "relationships=" in msg
                assert "duration_ms=" in msg
                break

        assert found is True, "Expected repository_index metrics log not found"

    finally:
        logger.removeHandler(handler)
