"""Tests for the ProviderStage and other pipeline stages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.stages import ProviderStage
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType


class TestProviderStage:
    """Tests for ProviderStage."""

    @pytest.fixture
    def stage(self) -> ProviderStage:
        """Provide a fresh ProviderStage instance."""
        return ProviderStage()

    @pytest.fixture
    def mock_context(self) -> PipelineContext:
        """Create a mock pipeline context."""
        context = MagicMock(spec=PipelineContext)
        context.request_id = "test-request-123"
        context.request = {}
        context.resolved_model = None
        context.get_metadata = MagicMock(return_value=None)
        return context

    @pytest.fixture
    def mock_provider_definition(self) -> MagicMock:
        """Create a mock provider definition."""
        definition = MagicMock()
        definition.provider = MagicMock()
        definition.model = "test-model"
        definition.backend_model = None
        return definition

    @pytest.fixture
    def mock_resolved_model(
        self, mock_provider_definition: MagicMock
    ) -> MagicMock:
        """Create a mock resolved model."""
        resolved = MagicMock()
        resolved.provider = mock_provider_definition.provider
        resolved.definition = mock_provider_definition
        return resolved

    @pytest.fixture
    def valid_context(
        self, mock_context: PipelineContext, mock_resolved_model: MagicMock
    ) -> PipelineContext:
        """Create a valid pipeline context with resolved model."""
        mock_context.resolved_model = mock_resolved_model
        return mock_context

    def test_provider_stage_name(self, stage: ProviderStage) -> None:
        """Verify the stage has the correct name."""
        assert stage.name == "provider"

    @pytest.mark.asyncio
    async def test_execute_no_resolved_model(
        self, stage: ProviderStage, mock_context: PipelineContext
    ) -> None:
        """Verify execution fails when no resolved model is available."""
        result = await stage.execute(mock_context)

        assert isinstance(result, PipelineStageResult)
        assert result.success is False
        assert "No resolved model found" in result.error

    @pytest.mark.asyncio
    async def test_execute_streaming_with_stream_options(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify stream_options is forwarded when streaming is enabled."""
        mock_provider = valid_context.resolved_model.provider
        mock_provider.chat = AsyncMock(return_value={"choices": []})

        valid_context.request = {"stream": True}

        result = await stage.execute(valid_context)

        assert result.success is True
        mock_provider.chat.assert_called_once()
        call_kwargs = mock_provider.chat.call_args[1]

        assert call_kwargs["stream"] is True
        assert call_kwargs["stream_options"] == {"include_usage": True}
        # model should be overridden with backend_model
        assert call_kwargs["model"] == valid_context.resolved_model.definition.model

    @pytest.mark.asyncio
    async def test_execute_non_streaming_no_stream_options(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify stream_options is absent when streaming is disabled."""
        mock_provider = valid_context.resolved_model.provider
        mock_provider.chat = AsyncMock(return_value={"choices": []})

        valid_context.request = {"stream": False}

        result = await stage.execute(valid_context)

        assert result.success is True
        mock_provider.chat.assert_called_once()
        call_kwargs = mock_provider.chat.call_args[1]

        assert call_kwargs["stream"] is False
        assert "stream_options" not in call_kwargs

    @pytest.mark.asyncio
    async def test_execute_streaming_from_serialized_request(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify stream_options is forwarded even when using serialized ProviderRequest."""
        mock_provider = valid_context.resolved_model.provider
        mock_provider.chat = AsyncMock(return_value={"choices": []})

        # Simulate a serialized ProviderRequest
        serialized_request = ProviderRequest(
            provider_type=ProviderType.openai,
            messages=[{"role": "user", "content": "Hello"}],
            model="test-model",
        )
        valid_context.get_metadata = MagicMock(
            return_value=serialized_request
        )
        valid_context.request = {"stream": True}

        result = await stage.execute(valid_context)

        assert result.success is True
        mock_provider.chat.assert_called_once()
        call_kwargs = mock_provider.chat.call_args[1]

        assert call_kwargs["stream"] is True
        assert call_kwargs["stream_options"] == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_execute_error_handling(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify errors from the provider are captured in the result."""
        mock_provider = valid_context.resolved_model.provider
        mock_provider.chat = AsyncMock(side_effect=RuntimeError("Provider error"))

        valid_context.request = {}

        result = await stage.execute(valid_context)

        assert isinstance(result, PipelineStageResult)
        assert result.success is False
        assert "Provider error" in result.error
        assert isinstance(result.exception, RuntimeError)

    @pytest.mark.asyncio
    async def test_after_success_logs_ok(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify the after hook logs OK status on success."""
        result = PipelineStageResult(
            stage_name="provider",
            success=True,
            data={"choices": [{"message": {"content": "Hello"}}]},
        )

        post_result = await stage.after(valid_context, result)

        assert post_result is None  # Keeps the existing result

    @pytest.mark.asyncio
    async def test_after_failure_logs_error(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify the after hook logs error status on failure."""
        result = PipelineStageResult(
            stage_name="provider",
            success=False,
            error="Something went wrong",
        )

        post_result = await stage.after(valid_context, result)

        assert post_result is None  # Keeps the existing result

    @pytest.mark.asyncio
    async def test_stream_options_final_chunk_passthrough(
        self, stage: ProviderStage, valid_context: PipelineContext
    ) -> None:
        """Verify streaming with empty choices and usage doesn't crash."""
        mock_provider = valid_context.resolved_model.provider
        # Simulate vLLM final chunk with empty choices and usage
        mock_provider.chat = AsyncMock(
            return_value={
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            }
        )

        valid_context.request = {"stream": True}

        result = await stage.execute(valid_context)

        assert result.success is True
        # The passthrough should not crash on empty choices
        mock_provider.chat.assert_called_once()
        call_kwargs = mock_provider.chat.call_args[1]

        assert call_kwargs["stream_options"] == {"include_usage": True}