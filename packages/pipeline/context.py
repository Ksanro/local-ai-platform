"""Pipeline execution context.

Holds mutable state shared across all pipeline stages during a single
request's lifecycle. Each stage can read and write context fields to
pass data between stages.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from packages.pipeline.response import PipelineStageResult


@dataclass
class PipelineContext:
    """Mutable execution context shared across all pipeline stages.

    Created fresh for each incoming request. Stages read from and write
    to this context to pass data between each other.

    Attributes:
        request_id: Unique identifier for this request (from middleware).
        request: The original incoming request payload.
        stage_results: Accumulated results from each executed stage,
            keyed by stage name.
        metadata: Free-form dict for arbitrary stage-to-stage data.
        start_time: perf_counter timestamp when the pipeline started.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request: dict[str, Any] = field(default_factory=dict)
    stage_results: dict[str, PipelineStageResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)

    def get_stage_result(self, stage_name: str) -> PipelineStageResult | None:
        """Get a previously recorded stage result.

        Args:
            stage_name: The name of the stage whose result to retrieve.

        Returns:
            The ``PipelineStageResult`` if the stage was executed,
            or ``None`` if not yet executed.
        """
        return self.stage_results.get(stage_name)

    def set_stage_result(self, stage_name: str, result: PipelineStageResult) -> None:
        """Record a stage result in the context.

        Args:
            stage_name: The name of the stage that produced the result.
            result: The result to record.
        """
        self.stage_results[stage_name] = result

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value by key.

        Args:
            key: The metadata key.
            default: Value to return if the key is not present.

        Returns:
            The metadata value, or ``default`` if not found.
        """
        return self.metadata.get(key, default)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata value.

        Args:
            key: The metadata key.
            value: The value to store.
        """
        self.metadata[key] = value

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since the pipeline started.

        Returns:
            Wall-clock time in seconds since ``start_time``.
        """
        return time.perf_counter() - self.start_time
