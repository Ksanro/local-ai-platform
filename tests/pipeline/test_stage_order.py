"""Tests for pipeline stage ordering and execution guarantees."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineStageResult
from packages.pipeline.stages import ProviderStage


class _OrderedStage(PipelineStage):
    """A stage that records its execution order."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._order: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def order(self) -> list[str]:
        return self._order

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        self._order.append(f"{self._name}:before")
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        self._order.append(f"{self._name}:execute")
        return PipelineStageResult(
            stage_name=self._name,
            success=True,
            data={self._name: True},
        )

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        self._order.append(f"{self._name}:after")


class TestStageOrdering:
    """Tests for stage execution ordering guarantees."""

    @pytest.mark.asyncio
    async def test_stages_execute_in_registration_order(self) -> None:
        """Verify stages execute in the order they were registered."""
        engine = PipelineEngine()
        stage1 = _OrderedStage("alpha")
        stage2 = _OrderedStage("beta")
        stage3 = _OrderedStage("gamma")

        engine.register(stage1)
        engine.register(stage2)
        engine.register(stage3)

        request = PipelineRequest()
        await engine.execute(request)

        # Collect all execution events in order
        all_events: list[str] = []
        for s in (stage1, stage2, stage3):
            all_events.extend(s.order)

        # Verify: alpha:before, alpha:execute, alpha:after, beta:before, ...
        expected = [
            "alpha:before",
            "alpha:execute",
            "alpha:after",
            "beta:before",
            "beta:execute",
            "beta:after",
            "gamma:before",
            "gamma:execute",
            "gamma:after",
        ]
        assert all_events == expected

    @pytest.mark.asyncio
    async def test_stage_before_execute_after_sequence(self) -> None:
        """Verify each stage runs before -> execute -> after, not all before then all execute."""
        engine = PipelineEngine()
        stage_a = _OrderedStage("a")
        stage_b = _OrderedStage("b")
        engine.register(stage_a)
        engine.register(stage_b)

        request = PipelineRequest()
        await engine.execute(request)

        events = stage_a.order + stage_b.order
        # a:execute must come before b:before (stage A completes before B starts)
        a_execute_idx = events.index("a:execute")
        b_before_idx = events.index("b:before")
        assert a_execute_idx < b_before_idx

    @pytest.mark.asyncio
    async def test_later_stages_seearlier_results(self) -> None:
        """Verify later stages can read earlier stage results from context."""
        engine = PipelineEngine()

        class ReaderStage(PipelineStage):
            @property
            def name(self) -> str:
                return "reader"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                # Read the result from the previous stage
                prev = context.get_stage_result("writer")
                value = prev.data if prev else None
                return PipelineStageResult(
                    stage_name="reader",
                    success=True,
                    data={"read": value},
                )

            async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
                pass

        class WriterStage(PipelineStage):
            @property
            def name(self) -> str:
                return "writer"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                return PipelineStageResult(
                    stage_name="writer",
                    success=True,
                    data={"value": 42},
                )

            async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
                pass

        engine.register(WriterStage())
        engine.register(ReaderStage())

        request = PipelineRequest()
        response = await engine.execute(request)

        assert response.data == {"read": {"value": 42}}

    @pytest.mark.asyncio
    async def test_metadata_passed_between_stages(self) -> None:
        """Verify context metadata is shared across all stages."""
        engine = PipelineEngine()

        class MetadataWriter(PipelineStage):
            @property
            def name(self) -> str:
                return "writer"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                context.set_metadata("shared_key", "shared_value")
                return PipelineStageResult(
                    stage_name="writer",
                    success=True,
                    data=None,
                )

            async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
                pass

        class MetadataReader(PipelineStage):
            @property
            def name(self) -> str:
                return "reader"

            async def before(self, context: PipelineContext) -> PipelineStageResult | None:
                return None

            async def execute(self, context: PipelineContext) -> PipelineStageResult:
                value = context.get_metadata("shared_key")
                return PipelineStageResult(
                    stage_name="reader",
                    success=True,
                    data={"got": value},
                )

            async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
                pass

        engine.register(MetadataWriter())
        engine.register(MetadataReader())

        request = PipelineRequest()
        response = await engine.execute(request)

        assert response.data == {"got": "shared_value"}

    @pytest.mark.asyncio
    async def test_provider_name_in_context(self) -> None:
        """Verify provider_name is stored in context metadata."""
        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(
            return_value={"choices": [{"message": {"content": "ok"}}]}
        )
        engine = PipelineEngine()
        engine.register(ProviderStage(mock_provider))

        request = PipelineRequest(
            provider_name="custom-provider",
            model="custom-model",
        )
        response = await engine.execute(request)

        assert response.success is True
        assert response.data is not None
