"""Context Planning Engine.

Deterministic planning for retrieval strategy selection.

The planner selects the retrieval strategy before context construction begins.
No AI or LLM inference is performed. Planning is entirely deterministic.

Architecture
------------

Pipeline
    ↓
PlanningStage
    ↓
RepositoryContextStage (consumes ContextPlan)
    ↓
SerializerStage
    ↓
Provider

ContextPlan is the single source of truth for retrieval configuration.
Components such as RepositoryContextStage, RankingEngine, BudgetEstimator,
and Serializer must consume the ContextPlan rather than introducing
independent decision logic.

Public API
----------

.. code-block:: python

    planner = ContextPlanner()
    plan = planner.build(
        user_messages=["Explain ProviderFactory"],
        repository_index=index,
    )
"""

from __future__ import annotations

from packages.planning.intent import Intent
from packages.planning.plan import ContextPlan
from packages.planning.planner import ContextPlanner

__all__ = [
    "ContextPlan",
    "ContextPlanner",
    "Intent",
]
