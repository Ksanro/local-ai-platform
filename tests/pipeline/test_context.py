"""Tests for PipelineContext."""

from __future__ import annotations

import time

from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult


class TestPipelineContext:
    """Tests for PipelineContext."""

    def test_default_request_id(self) -> None:
        """Verify default request_id is a non-empty UUID string."""
        ctx = PipelineContext()
        assert ctx.request_id != ""
        assert len(ctx.request_id) == 36  # UUID4 format

    def test_custom_request_id(self) -> None:
        """Verify custom request_id can be set."""
        ctx = PipelineContext(request_id="custom-123")
        assert ctx.request_id == "custom-123"

    def test_default_request_is_empty(self) -> None:
        """Verify default request is an empty dict."""
        ctx = PipelineContext()
        assert ctx.request == {}

    def test_set_and_get_request(self) -> None:
        """Verify request can be set and read."""
        ctx = PipelineContext()
        ctx.request = {"key": "value"}
        assert ctx.request == {"key": "value"}

    def test_default_stage_results_empty(self) -> None:
        """Verify default stage_results is empty."""
        ctx = PipelineContext()
        assert ctx.stage_results == {}

    def test_set_and_get_stage_result(self) -> None:
        """Verify stage results can be set and retrieved."""
        ctx = PipelineContext()
        result = PipelineStageResult(
            stage_name="test",
            success=True,
            data={"answer": 42},
        )
        ctx.set_stage_result("test", result)
        assert ctx.get_stage_result("test") is result
        assert ctx.get_stage_result("nonexistent") is None

    def test_default_metadata_empty(self) -> None:
        """Verify default metadata is empty."""
        ctx = PipelineContext()
        assert ctx.metadata == {}

    def test_set_and_get_metadata(self) -> None:
        """Verify metadata can be set and retrieved."""
        ctx = PipelineContext()
        ctx.set_metadata("key", "value")
        assert ctx.get_metadata("key") == "value"
        assert ctx.get_metadata("missing", "default") == "default"

    def test_get_metadata_missing_returns_none(self) -> None:
        """Verify missing metadata returns None by default."""
        ctx = PipelineContext()
        assert ctx.get_metadata("missing") is None

    def test_elapsed_time_increases(self) -> None:
        """Verify elapsed time increases as time passes."""
        ctx = PipelineContext()
        initial = ctx.elapsed
        time.sleep(0.01)  # 10ms
        final = ctx.elapsed
        assert final > initial

    def test_elapsed_starts_near_zero(self) -> None:
        """Verify elapsed starts near zero."""
        ctx = PipelineContext()
        assert ctx.elapsed >= 0
        assert ctx.elapsed < 1.0  # Should be near zero


class TestContextIntegration:
    """Tests for context usage in realistic scenarios."""

    def test_context_shares_data_between_operations(self) -> None:
        """Verify context accumulates data across multiple operations."""
        ctx = PipelineContext()

        # Simulate stage 1 writing
        ctx.set_stage_result("stage1", PipelineStageResult(
            stage_name="stage1",
            success=True,
            data={"step": 1},
        ))
        ctx.set_metadata("counter", 1)

        # Simulate stage 2 reading and writing
        step1 = ctx.get_stage_result("stage1")
        assert step1 is not None
        assert step1.data == {"step": 1}

        ctx.set_stage_result("stage2", PipelineStageResult(
            stage_name="stage2",
            success=True,
            data={"step": 2},
        ))
        ctx.set_metadata("counter", 2)

        # Both results should be present
        assert len(ctx.stage_results) == 2
        assert "stage1" in ctx.stage_results
        assert "stage2" in ctx.stage_results

    def test_context_preserves_request_data(self) -> None:
        """Verify request data is preserved in context."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            "model": "test-model",
            "stream": False,
            "temperature": 0.7,
        }
        ctx = PipelineContext(request=request_data)
        assert ctx.request == request_data
        assert ctx.request["model"] == "test-model"
        assert ctx.request["stream"] is False
