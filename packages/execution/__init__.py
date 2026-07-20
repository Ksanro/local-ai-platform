"""Execution Planner and Execution Engine packages.

Execution Planner: Transforms WorkflowPlans into deterministic ExecutionPlans
consumable by coding agents.

Execution Engine: Orchestrates the execution of immutable WorkflowPlan objects
through ExecutionAdapters.

Architecture
------------

WorkflowPlan  -->  ExecutionPlanner  -->  ExecutionPlan
WorkflowPlan  -->  ExecutionEngine  -->  ExecutionReport

Public API
----------

.. code-block:: python

    from packages.execution import (
        # Execution Planner
        ExecutionStep,
        ExecutionMetrics,
        ExecutionPlan,
        ExecutionPlanner,
        ExecutionValidator,
        # Execution Engine
        ExecutionStatus,
        ExecutionStepResult,
        ExecutionSession,
        ExecutionReport,
        ExecutionAdapter,
        ProviderExecutionAdapter,
        ExecutionEngine,
    )

"""

from __future__ import annotations

from packages.execution.adapter import (
    ExecutionAdapter,
    ProviderExecutionAdapter,
)
from packages.execution.engine import ExecutionEngine
from packages.execution.models import ExecutionMetrics, ExecutionPlan, ExecutionStep
from packages.execution.planner import ExecutionPlanner
from packages.execution.runtime_models import (
    ExecutionReport,
    ExecutionSession,
    ExecutionStatus,
    ExecutionStepResult,
)
from packages.execution.validator import ExecutionValidator

__all__ = [
    # Execution Planner
    "ExecutionMetrics",
    "ExecutionPlan",
    "ExecutionPlanner",
    "ExecutionStep",
    "ExecutionValidator",
    # Execution Engine
    "ExecutionAdapter",
    "ExecutionEngine",
    "ExecutionReport",
    "ExecutionSession",
    "ExecutionStatus",
    "ExecutionStepResult",
    "ProviderExecutionAdapter",
]
