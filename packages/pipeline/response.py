"""Pipeline response model.

Defines the typed response structure that flows back from the pipeline.
"""

from __future__ import annotations

from typing import Any

from packages.pipeline.context import PipelineContext, PipelineStageResult


class PipelineResponse:
    """Complete pipeline response.

    Wraps the final result after all stages have executed. Contains
    the response data, per-stage results, and timing information.

    Attributes:
        data: The final response data (from the last stage).
        stage_results: Per-stage results, keyed by stage name.
        success: Whether all stages completed successfully.
        error: Error message if the pipeline failed.
        elapsed: Total wall-clock time (seconds).
        request_id: Unique request identifier.
    """

    def __init__(
        self,
        data: Any = None,
        stage_results: dict[str, PipelineStageResult] | None = None,
        success: bool = True,
        error: str | None = None,
        elapsed: float = 0.0,
        request_id: str = "",
    ) -> None:
        """Initialize a pipeline response.

        Args:
            data: The final response data.
            stage_results: Per-stage results.
            success: Whether the pipeline succeeded.
            error: Error message if failed.
            elapsed: Total elapsed time.
            request_id: Request identifier.
        """
        self.data = data
        self.stage_results = stage_results or {}
        self.success = success
        self.error = error
        self.elapsed = elapsed
        self.request_id = request_id

    @classmethod
    def from_context(cls, context: PipelineContext) -> PipelineResponse:
        """Build a PipelineResponse from a pipeline context.

        Extracts the last stage result as the response data and
        computes elapsed time.

        Args:
            context: The pipeline context after all stages executed.

        Returns:
            A new ``PipelineResponse`` instance.
        """
        results = context.stage_results
        last_result = list(results.values())[-1] if results else None

        if last_result is None:
            return cls(
                data=None,
                stage_results={},
                success=False,
                error="No stages executed",
                elapsed=context.elapsed,
                request_id=context.request_id,
            )

        return cls(
            data=last_result.data,
            stage_results=dict(results),
            success=last_result.success,
            error=last_result.error,
            elapsed=context.elapsed,
            request_id=context.request_id,
        )
