"""Request Processing Pipeline package.

Provides a pluggable stage-based pipeline for processing incoming
requests. Stages are executed in order, each receiving a mutable
context and returning a result.

Usage::

    from packages.pipeline import PipelineEngine, PipelineRequest
    from packages.pipeline.stages import ProviderStage

    engine = PipelineEngine()
    engine.register(ProviderStage())

    request = PipelineRequest(
        provider_name="vllm",
        model="default",
        messages=[{"role": "user", "content": "Hello"}],
    )
    response = await engine.execute(request)
"""

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import (
    PipelineError,
    PipelineExecutionError,
    StageError,
    UnknownStageError,
)
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineResponse
from packages.pipeline.result import PipelineStageResult

__all__ = [
    "PipelineContext",
    "PipelineEngine",
    "PipelineError",
    "PipelineExecutionError",
    "PipelineRequest",
    "PipelineResponse",
    "PipelineStage",
    "PipelineStageResult",
    "StageError",
    "UnknownStageError",
]
