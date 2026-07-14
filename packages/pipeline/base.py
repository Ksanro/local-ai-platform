"""Abstract pipeline stage base class.

Defines the interface that all pipeline stages must satisfy. Stages
are executed in a fixed order, each receiving a mutable context and
returning a result that is recorded in the pipeline response.
"""

from abc import ABC, abstractmethod
from typing import Any

from packages.pipeline.context import PipelineContext
from packages.pipeline.response import PipelineStageResult


class PipelineStage(ABC):
    """Abstract pipeline stage interface.

    All pipeline stages (provider, authentication, memory, etc.)
    must inherit from this class and implement ``name``, ``before``,
    ``execute``, and ``after``.

    Execution model:

    1. ``before()`` — prepare the stage, validate context, early-exit.
    2. ``execute()`` — perform the stage's primary work.
    3. ``after()`` — post-process, clean up, record metrics.

    All methods are async. ``before()`` and ``after()`` may return
    early (returning ``None``) to skip the main ``execute()`` body.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this stage.

        Used for logging, error reporting, and ordering.

        Returns:
            A short lowercase string like ``"provider"`` or ``"auth"``.
        """

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Pre-execution hook.

        Called before ``execute()``. Can validate context, short-circuit
        the stage, or prepare data. If a ``PipelineStageResult`` is
        returned, ``execute()`` is skipped and the result is recorded.

        Args:
            context: The mutable pipeline context.

        Returns:
            A ``PipelineStageResult`` to short-circuit, or ``None`` to
            proceed with ``execute()``.
        """
        return None

    @abstractmethod
    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Execute the stage's primary work.

        This is the core method that performs the stage's responsibility
        (e.g. calling the provider, enriching context, adding memory).

        Args:
            context: The mutable pipeline context containing the request
                and accumulated stage results.

        Returns:
            A ``PipelineStageResult`` with the stage's output.

        Raises:
            StageError: If the stage fails during execution.
        """

    async def after(self, context: PipelineContext, result: PipelineStageResult) -> None:
        """Post-execution hook.

        Called after ``execute()`` (or the short-circuit result from
        ``before()``). Can perform cleanup, record metrics, or modify
        the context.

        Args:
            context: The pipeline context.
            result: The result produced by this stage.
        """
