"""Tests for the pipeline engine and ProviderStage."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext, PipelineStageResult
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineExecutionError, StageError
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineResponse
from packages.pipeline.stages import ProviderStage


class _TrackingStage(PipelineStage):
    """A test stage that records execution order and modifies context."""

    def __init__(self, name: str = "test") -> None:
        """Initialize with a name."""
        self._name = name
        self.before_called = False
        self.execute_called = False
        self.after_called = False
        self.call_order: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        self.before_called = True
        self.call_order.append("before")
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        self.execute_called = True
        self.call_order.append("execute")
        context.set_metadata(f"{self._name}_executed", True)
        return PipelineStageResult(
            stage_name=self._name,
            success=True,
            data={f"{self._name}_result": True},
        )

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        self.after_called = True
        self.call_order.append("after")


class _ShortCircuitStage(PipelineStage):
    """A stage that short-circuits via before()."""

    def __init__(self, name: str = "shortcircuit") -> None:
        self._name = name
        self.before_called = False
        self.execute_called = False

    @property
    def name(self) -> str:
        return self._name

    async def before(self, context: PipelineContext) -> PipelineStageResult:
        self.before_called = True
        return PipelineStageResult(
            stage_name=self._name,
            success=True,
            data={"short_circuited": True},
        )

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        # Should not be called when before short-circuits
        raise RuntimeError("execute() should not be called after short-circuit")

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        pass


class _FailingStage(PipelineStage):
    """A stage that raises an exception."""

    def __init__(self, name: str = "failing", error_msg: str = "boom") -> None:
        self._name = name
        self._error_msg = error_msg

    @property
    def name(self) -> str:
        return self._name

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        raise RuntimeError(self._error_msg)

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        pass


class TestPipelineEngine:
    """Tests for PipelineEngine."""

    @pytest.mark.asyncio
    async def test_execute_no_stages_raises(self) -> None:
        """Verify execute raises PipelineExecutionError with no stages."""
        engine = PipelineEngine()
        request = PipelineRequest()
        with pytest.raises(PipelineExecutionError, match="No stages"):
            await engine.execute(request)

    @pytest.mark.asyncio
    async def test_execute_single_stage(self) -> None:
        """Verify single stage executes and returns response."""
        engine = PipelineEngine()
        stage = _TrackingStage(name="single")
        engine.register(stage)

        request = PipelineRequest(
            provider_name="vllm",
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
        )
        response = await engine.execute(request)

        assert isinstance(response, PipelineResponse)
        assert response.success is True
        assert response.data == {"single_result": True}
        assert "single" in response.stage_results
        assert stage.before_called is True
        assert stage.execute_called is True
        assert stage.after_called is True

    @pytest.mark.asyncio
    async def test_execute_multiple_stages_in_order(self) -> None:
        """Verify multiple stages execute in registration order."""
        engine = PipelineEngine()
        stage_a = _TrackingStage(name="stage_a")
        stage_b = _TrackingStage(name="stage_b")
        engine.register(stage_a)
        engine.register(stage_b)

        request = PipelineRequest()
        response = await engine.execute(request)

        assert response.success is True
        assert stage_a.call_order == ["before", "execute", "after"]
        assert stage_b.call_order == ["before", "execute", "after"]

        # Verify stage_b's data is the final response (last stage wins)
        assert response.data == {"stage_b_result": True}

    @pytest.mark.asyncio
    async def test_execute_short_circuit(self) -> None:
        """Verify before() short-circuit skips execute()."""
        engine = PipelineEngine()
        sc_stage = _ShortCircuitStage(name="sc")
        track_stage = _TrackingStage(name="track")
        engine.register(sc_stage)
        engine.register(track_stage)

        request = PipelineRequest()
        response = await engine.execute(request)

        # Short-circuit stage: before() ran, execute() was skipped
        assert sc_stage.before_called is True
        assert sc_stage.execute_called is False

        # Track stage still runs normally
        assert track_stage.execute_called is True

        # Last stage's data is the final response
        assert response.data == {"track_result": True}

    @pytest.mark.asyncio
    async def test_execute_stage_failure_propagates(self) -> None:
        """Verify a failing stage raises StageError."""
        engine = PipelineEngine()
        good = _TrackingStage(name="good")
        bad = _FailingStage(name="bad", error_msg="kaboom")
        engine.register(good)
        engine.register(bad)

        request = PipelineRequest()
        with pytest.raises(StageError) as exc_info:
            await engine.execute(request)

        assert "bad" in str(exc_info.value.stage_name)
        assert "kaboom" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_id_propagation(self) -> None:
        """Verify request_id flows from request to response."""
        engine = PipelineEngine()
        engine.register(_TrackingStage(name="test"))

        request = PipelineRequest(
            metadata={"request_id": "req-123"},
        )
        response = await engine.execute(request)

        assert response.request_id == "req-123"

    @pytest.mark.asyncio
    async def test_metadata_propagation(self) -> None:
        """Verify context metadata is set from request."""
        engine = PipelineEngine()
        engine.register(_TrackingStage(name="test"))

        request = PipelineRequest(
            provider_name="custom",
            model="my-model",
            metadata={"custom_key": "custom_value"},
        )
        response = await engine.execute(request)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_elapsed_time_tracked(self) -> None:
        """Verify elapsed time is tracked in response."""
        engine = PipelineEngine()
        engine.register(_TrackingStage(name="test"))

        request = PipelineRequest()
        response = await engine.execute(request)

        assert response.elapsed >= 0

    @pytest.mark.asyncio
    async def test_stage_results_all_recorded(self) -> None:
        """Verify all stage results are in the response."""
        engine = PipelineEngine()
        engine.register(_TrackingStage(name="first"))
        engine.register(_TrackingStage(name="second"))

        request = PipelineRequest()
        response = await engine.execute(request)

        assert "first" in response.stage_results
        assert "second" in response.stage_results
        assert len(response.stage_results) == 2


class TestProviderStage:
    """Tests for ProviderStage."""

    @pytest.mark.asyncio
    async def test_provider_stage_success(self) -> None:
        """Verify ProviderStage returns provider response on success."""
        stage = ProviderStage()

        mock_result = {"choices": [{"message": {"content": "Hello"}}]}

        with patch("packages.pipeline.stages.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.chat = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_provider

            context = PipelineContext(
                request_id="test-1",
                request={"messages": [], "model": "test", "stream": False},
            )
            context.set_metadata("provider_name", "vllm")
            context.set_metadata("model", "test-model")

            result = await stage.execute(context)

            assert result.success is True
            assert result.data == mock_result
            assert result.stage_name == "provider"

    @pytest.mark.asyncio
    async def test_provider_stage_before_unregistered_provider(self) -> None:
        """Verify before() returns failure for unregistered provider."""
        stage = ProviderStage()

        context = PipelineContext()
        context.set_metadata("provider_name", "nonexistent")

        result = await stage.before(context)

        assert result is not None
        assert result.success is False
        assert "nonexistent" in result.error

    @pytest.mark.asyncio
    async def test_provider_stage_propagates_provider_error(self) -> None:
        """Verify provider errors are wrapped in StageError."""
        from packages.providers.exceptions import ProviderConnectionError

        stage = ProviderStage()

        with patch("packages.pipeline.stages.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.chat = AsyncMock(side_effect=ProviderConnectionError("unreachable"))
            mock_create.return_value = mock_provider

            context = PipelineContext(
                request_id="test-2",
                request={"messages": [], "model": "test", "stream": False},
            )
            context.set_metadata("provider_name", "vllm")
            context.set_metadata("model", "test-model")

            result = await stage.execute(context)

            assert result.success is False
            assert "unreachable" in result.error

    @pytest.mark.asyncio
    async def test_provider_stage_streaming(self) -> None:
        """Verify ProviderStage handles streaming responses."""
        stage = ProviderStage()

        mock_generator = AsyncMock()
        mock_result = {
            "generator": mock_generator,
            "media_type": "text/event-stream",
        }

        with patch("packages.pipeline.stages.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.chat = AsyncMock(return_value=mock_result)
            mock_create.return_value = mock_provider

            context = PipelineContext(
                request_id="test-3",
                request={"messages": [], "model": "test", "stream": True},
            )
            context.set_metadata("provider_name", "vllm")
            context.set_metadata("model", "test-model")

            result = await stage.execute(context)

            assert result.success is True
            assert result.data["generator"] is mock_generator
            assert result.data["media_type"] == "text/event-stream"

    @pytest.mark.asyncio
    async def test_provider_stage_full_pipeline(self) -> None:
        """Verify ProviderStage works end-to-end in a pipeline."""
        engine = PipelineEngine()
        engine.register(ProviderStage())

        with patch("packages.pipeline.stages.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.chat = AsyncMock(
                return_value={"choices": [{"message": {"content": "Hi"}}]}
            )
            mock_create.return_value = mock_provider

            request = PipelineRequest(
                provider_name="vllm",
                model="test-model",
                messages=[{"role": "user", "content": "Hello"}],
            )
            response = await engine.execute(request)

            assert response.success is True
            assert "choices" in response.data
