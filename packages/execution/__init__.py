"""Execution Planner package.

Transforms WorkflowPlans into deterministic ExecutionPlans
consumable by coding agents.

Architecture
------------

WorkflowPlan  -->  ExecutionPlanner  -->  ExecutionPlan
                                              |
                                              v
                                      ProviderSerializer
                                              |
                                              v
                                             LLM

Public API
----------

.. code-block:: python

    from packages.execution import (
        ExecutionStep,
        ExecutionMetrics,
        ExecutionPlan,
        ExecutionPlanner,
        ExecutionValidator,
    )

"""

from __future__ import annotations

from packages.execution.models import ExecutionMetrics, ExecutionPlan, ExecutionStep
from packages.execution.planner import ExecutionPlanner
from packages.execution.validator import ExecutionValidator

__all__ = [
    "ExecutionMetrics",
    "ExecutionPlan",
    "ExecutionPlanner",
    "ExecutionStep",
    "ExecutionValidator",
]
