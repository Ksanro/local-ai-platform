"""Pipeline layer exceptions.

Defines a hierarchy of exceptions for failure modes in the request
processing pipeline (stage errors, execution errors, unknown stages).
"""


class PipelineError(Exception):
    """Base pipeline error.

    All pipeline-specific exceptions inherit from this class
    so they can be caught collectively.
    """


class StageError(PipelineError):
    """Raised when a pipeline stage fails during execution.

    Wraps the original exception from a stage's ``execute`` method.
    """

    def __init__(self, message: str, stage_name: str, original: Exception | None = None) -> None:
        """Initialize a stage error.

        Args:
            message: Human-readable error description.
            stage_name: Name of the stage that failed.
            original: The original exception that caused the failure.
        """
        super().__init__(message)
        self.stage_name = stage_name
        self.original = original


class UnknownStageError(PipelineError):
    """Raised when a stage name is not registered in the pipeline."""


class PipelineExecutionError(PipelineError):
    """Raised when the pipeline cannot execute.

    Covers cases like an empty stage list or missing request context.
    """
