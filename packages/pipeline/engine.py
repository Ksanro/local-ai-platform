"""Pipeline engine.

Orchestrates registered stages in order, executing each stage's
``before``, ``execute``, and ``after`` hooks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.exceptions import PipelineExecutionError, StageError
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineResponse, PipelineStageResult

logger = logging.getLogger(__name__)


class PipelineEngine:
    """Pipeline execution engine.

    Manages a registry of stages and executes them in order for each
    incoming request. Stages are registered via ``register()`` and
    executed via ``execute()``.

    Execution model:

    1. Create a fresh ``PipelineContext`` for the request.
    2. For each registered stage (in order):
       a. Call ``before(context)`` — may short-circuit.
       b. Call ``execute(context)`` — performs the work.
       c. Call ``after(context, result)`` — post-process.
    3. Build and return a ``PipelineResponse``.

    Attributes:
        _stages: Ordered list of registered pipeline stages.
    """

    def __init__(self) -> None:
        """Initialize the pipeline engine with an empty stage list."""
        self._stages: list[PipelineStage] = []

    def register(self, stage: PipelineStage) -> None:
        """Register a pipeline stage.

        Stages are executed in registration order. To change order,
        unregister and re-register, or rebuild the engine.

        Args:
            stage: The stage instance to register.
        """
        self._stages.append(stage)

    async def execute(self, request: PipelineRequest) -> PipelineResponse:
        """Execute all registered stages for the given request.

        Creates a fresh context, runs each stage in order, and returns
        the final response.

        Args:
            request: The pipeline request to process.

        Returns:
            A ``PipelineResponse`` with results from all stages.

        Raises:
            PipelineExecutionError: If no stages are registered.
        """
        if not self._stages:
            raise PipelineExecutionError("No stages registered in pipeline")

        context = PipelineContext(
            request_id=request.metadata.get("request_id", ""),
            request=request.to_provider_kwargs(),
        )

        # Store provider_name and model in context metadata for logging
        context.set_metadata("provider_name", request.provider_name)
        context.set_metadata("model", request.model)

        response_data: Any = None
        all_results: dict[str, PipelineStageResult] = {}

        for stage in self._stages:
            stage_start = time.perf_counter()
            stage_name = stage.name

            logger.info(
                "pipeline stage=%s request_id=%s",
                stage_name,
                context.request_id,
            )

            try:
                # Before hook
                short_circuit = await stage.before(context)
                if short_circuit is not None:
                    result = short_circuit
                    if not isinstance(result, PipelineStageResult):
                        result = PipelineStageResult(
                            stage_name=stage_name,
                            success=True,
                            data=result,
                        )
                else:
                    # Execute
                    result = await stage.execute(context)

                # After hook
                after_result = await stage.after(context, result)
                if after_result is not None and isinstance(after_result, PipelineStageResult):
                    result = after_result

                # Record result with duration
                result.duration = time.perf_counter() - stage_start
                context.set_stage_result(stage_name, result)
                all_results[stage_name] = result

                if not result.success:
                    logger.error(
                        "pipeline stage=%s request_id=%s error=%s",
                        stage_name,
                        context.request_id,
                        result.error,
                    )
                    # Halt the pipeline on failure — do not run later stages.
                    break

                # Propagate data for next stages
                if result.data is not None:
                    response_data = result.data

            except StageError:
                # Re-raise StageError (already has all info)
                raise
            except Exception as exc:
                elapsed = time.perf_counter() - stage_start
                error_result = PipelineStageResult(
                    stage_name=stage_name,
                    success=False,
                    error=str(exc),
                    duration=elapsed,
                )
                context.set_stage_result(stage_name, error_result)
                all_results[stage_name] = error_result

                logger.error(
                    "pipeline stage=%s request_id=%s error=%s duration=%.3fs",
                    stage_name,
                    context.request_id,
                    exc,
                    elapsed,
                )
                raise StageError(
                    message=f"Stage '{stage_name}' failed: {exc}",
                    stage_name=stage_name,
                    original=exc,
                ) from exc

        # Build final response from context (success/error/data are
        # aggregated across all stages by from_context).
        response = PipelineResponse.from_context(context)

        # Log summary
        logger.info(
            "pipeline request_id=%s provider=%s model=%s duration=%.3fs status=%s",
            context.request_id,
            request.provider_name,
            request.model,
            context.elapsed,
            "ok" if response.success else "error",
        )

        return response
