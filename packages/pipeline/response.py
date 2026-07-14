"""Pipeline response model.

Defines the typed response structure that flows back from the pipeline.
"""

from __future__ import annotations

from typing import Any

from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult


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

    @property
    def exception(self) -> Exception | None:
        """The exception from the first failing stage, if any.

        Returns:
            The first failing stage's exception, or ``None``.
        """
        for result in self.stage_results.values():
            if not result.success and result.exception is not None:
                return result.exception
        return None

    @classmethod
    def from_context(cls, context: PipelineContext) -> PipelineResponse:
        """Build a PipelineResponse from a pipeline context.

        Computes success across all stages (all must succeed), finds
        the first error message, and takes data from the last successful
        stage that produced non-None data.

        Args:
            context: The pipeline context after all stages executed.

        Returns:
            A new ``PipelineResponse`` instance.
        """
        results = context.stage_results

        if not results:
            return cls(
                data=None,
                stage_results={},
                success=False,
                error="No stages executed",
                elapsed=context.elapsed,
                request_id=context.request_id,
            )

        success = all(r.success for r in results.values())
        error = next(
            (r.error for r in results.values() if not r.success),
            None,
        )

        # Take data from the last successful stage that produced data.
        data = None
        for r in results.values():
            if r.success and r.data is not None:
                data = r.data

        return cls(
            data=data,
            stage_results=dict(results),
            success=success,
            error=error,
            elapsed=context.elapsed,
            request_id=context.request_id,
        )
