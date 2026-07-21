"""Immutable autonomous engineering model definitions.

Defines the output structures and input contracts for the Autonomous
Engineering Framework. These are the stable contracts between the
autonomous engine and its consumers.

Architecture
------------

EngineeringGoal --> AutonomousEngine --> FinalEngineeringReport
                       |
                       v
                 AutonomousIteration
                       |
                       v
                 AutonomousState

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No file system operations.
- No repository analysis fields.
- No provider fields.
- No patch generation.

Public API
----------

.. code-block:: python

    from packages.autonomous.models import (
        EngineeringGoal,
        AutonomousIteration,
        AutonomousState,
        AutonomousStatistics,
        FinalEngineeringReport,
    )

    goal = EngineeringGoal(
        id="goal-001",
        objective="Implement feature X",
        max_iterations=10,
    )

    state = AutonomousState(current_iteration=0, goal=goal)

    report = FinalEngineeringReport(
        goal=goal,
        status="COMPLETED",
        iterations=(),
        statistics=AutonomousStatistics(),
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AutonomousIteration",
    "AutonomousState",
    "AutonomousStatistics",
    "EngineeringGoal",
    "FinalEngineeringReport",
    "IterationStatus",
]


# ---------------------------------------------------------------------------
# IterationStatus
# ---------------------------------------------------------------------------


class IterationStatus(str):
    """Status of an autonomous iteration.

    Attributes:
        COMPLETED: Iteration completed successfully.
        FAILED: Iteration failed due to an error.
        SKIPPED: Iteration was skipped due to policy.
        STOPPED: Iteration was stopped by stopping condition.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    STOPPED = "STOPPED"


# ---------------------------------------------------------------------------
# EngineeringGoal
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringGoal:
    """Immutable engineering goal definition.

    Attributes:
        id: Unique goal identifier.
        objective: Human-readable engineering objective.
        constraints: Tuple of constraint descriptions.
        success_criteria: Tuple of success criteria descriptions.
        max_iterations: Maximum number of iterations allowed.
        metadata: Additional metadata about the goal.
    """

    id: str
    objective: str
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    max_iterations: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AutonomousIteration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutonomousIteration:
    """Immutable record of a single autonomous iteration.

    Attributes:
        iteration: 1-based iteration number.
        workflow_name: Name of the workflow executed.
        evaluation_score: Evaluation score (0.0 to 1.0).
        verification_status: Verification status string.
        duration_ms: Iteration duration in milliseconds.
        result_summary: Human-readable summary of the iteration result.
        status: Iteration status (COMPLETED, FAILED, SKIPPED, STOPPED).
        metadata: Additional metadata about the iteration.
    """

    iteration: int
    workflow_name: str
    evaluation_score: float
    verification_status: str
    duration_ms: int
    result_summary: str
    status: IterationStatus = IterationStatus.COMPLETED
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AutonomousState
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutonomousState:
    """Immutable autonomous execution state.

    Attributes:
        current_iteration: Current iteration number (0-based).
        completed_workflows: Tuple of executed workflow names.
        completed_iterations: Tuple of completed AutonomousIteration records.
        current_goal: The engineering goal being pursued.
        metadata: Additional metadata about the state.
    """

    current_iteration: int
    completed_workflows: tuple[str, ...] = ()
    completed_iterations: tuple[AutonomousIteration, ...] = ()
    current_goal: EngineeringGoal = None  # type: ignore
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and set defaults."""
        if self.current_goal is None:
            object.__setattr__(
                self,
                "current_goal",
                EngineeringGoal(
                    id="unknown",
                    objective="Unknown",
                ),
            )


# ---------------------------------------------------------------------------
# AutonomousStatistics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutonomousStatistics:
    """Aggregate statistics for autonomous execution.

    Attributes:
        total_iterations: Total number of iterations attempted.
        successful_iterations: Number of successful iterations.
        failed_iterations: Number of failed iterations.
        workflows_executed: Total number of workflows executed.
        total_duration_ms: Total execution duration in milliseconds.
        average_evaluation_score: Average evaluation score across iterations.
    """

    total_iterations: int = 0
    successful_iterations: int = 0
    failed_iterations: int = 0
    workflows_executed: int = 0
    total_duration_ms: int = 0
    average_evaluation_score: float = 0.0


# ---------------------------------------------------------------------------
# FinalEngineeringReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FinalEngineeringReport:
    """Complete engineering report for an autonomous execution.

    This is the canonical output artifact of the AutonomousEngine.
    It becomes the stable contract consumed by downstream components.

    Attributes:
        goal: The engineering goal that was pursued.
        status: Overall execution status.
        iterations: Tuple of all iteration records.
        statistics: Execution statistics.
        final_summary: Human-readable final summary.
        recommendations: Tuple of recommendation strings.
    """

    goal: EngineeringGoal
    status: str
    iterations: tuple[AutonomousIteration, ...] = ()
    statistics: AutonomousStatistics = field(
        default_factory=AutonomousStatistics
    )
    final_summary: str = ""
    recommendations: tuple[str, ...] = ()