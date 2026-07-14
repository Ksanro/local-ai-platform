"""Pipeline stage result model.

Defines the typed result structure that flows back from a single pipeline stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStageResult:
    """Result produced by a single pipeline stage.

    Attributes:
        stage_name: Name of the stage that produced this result.
        success: Whether the stage completed successfully.
        data: The stage's output data.
        error: Error message if the stage failed.
        exception: The original exception, if any.
        duration: Time spent in the stage (seconds).
    """

    stage_name: str
    success: bool
    data: Any = None
    error: str | None = None
    exception: Exception | None = field(default=None, repr=False)
    duration: float = 0.0
