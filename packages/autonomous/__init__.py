"""Autonomous Engineering Framework.

The orchestration layer of the platform.

Coordinates the entire engineering lifecycle by repeatedly invoking
existing workflows until an engineering objective is achieved or a
deterministic stopping condition is reached.

Architecture
------------

EngineeringGoal
       │
       ▼
AutonomousEngine
       │
       ├── Workflow Engine
       ├── Execution Engine
       ├── Evaluation Framework
       ├── Patch Generator
       ├── Code Modification Engine
       ├── Self Verification
       └── Decision Loop

This framework is the orchestration layer of the platform.

It is NOT another Workflow Engine.

It sits ABOVE the Workflow Engine and repeatedly invokes existing
workflows until an engineering objective is achieved or a deterministic
stopping condition is reached.

It MUST compose existing public APIs only.

It MUST NOT duplicate Workflow, Task, Capability, Repository, Evaluation,
Patch Generation, Modification, or Verification logic.

Public API
----------

.. code-block:: python

    from packages.autonomous import (
        AutonomousEngine,
        EngineeringGoal,
        AutonomousIteration,
        AutonomousState,
        FinalEngineeringReport,
        IterationStatus,
    )

    goal = EngineeringGoal(
        id="goal-001",
        objective="Implement feature X",
        max_iterations=10,
    )

    engine = AutonomousEngine()
    report = engine.execute(goal)

"""

from __future__ import annotations

__all__ = [
    # Models
    "AutonomousIteration",
    "AutonomousState",
    "AutonomousStatistics",
    "EngineeringGoal",
    "FinalEngineeringReport",
    "IterationStatus",
    # Engine
    "AutonomousEngine",
    # Policy
    "MaximumIterationPolicy",
    "PolicyDecision",
    "PolicyResult",
    "SequentialPolicy",
    "StopOnFailurePolicy",
    "VerificationGatePolicy",
    # Registry
    "AutonomousPolicyRegistry",
    # State
    "AutonomousStateManager",
    # Stopping
    "check_all_stopping_conditions",
    "check_goal_achieved",
    "check_max_iterations_reached",
    "check_policy_request_stop",
    "check_repeated_failure",
    "check_verification_successful",
    # Planner
    "EngineeringPlanner",
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

from packages.autonomous.models import (
    AutonomousIteration,
    AutonomousState,
    AutonomousStatistics,
    EngineeringGoal,
    FinalEngineeringReport,
    IterationStatus,
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

from packages.autonomous.engine import AutonomousEngine

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

from packages.autonomous.policy import (
    MaximumIterationPolicy,
    PolicyDecision,
    PolicyResult,
    SequentialPolicy,
    StopOnFailurePolicy,
    VerificationGatePolicy,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from packages.autonomous.registry import AutonomousPolicyRegistry

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

from packages.autonomous.state import AutonomousStateManager

# ---------------------------------------------------------------------------
# Stopping
# ---------------------------------------------------------------------------

from packages.autonomous.stopping import (
    check_all_stopping_conditions,
    check_goal_achieved,
    check_max_iterations_reached,
    check_policy_request_stop,
    check_repeated_failure,
    check_verification_successful,
)

# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

from packages.autonomous.planner import EngineeringPlanner