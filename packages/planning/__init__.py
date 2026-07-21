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

Planning v2 - Engineering Intent Resolution
-------------------------------------------

ContextPlan now includes **retrieval hints** that describe the
engineering goal inferred from the user's query. These hints are
produced by the ``IntentRuleEngine`` and consumed by ``RankingEngine``
to improve repository retrieval quality.

Retrieval Hints
~~~~~~~~~~~~~~~

- ``preferred_symbol_types`` — Symbol types to prioritize (CLASS,
  FUNCTION, METHOD, VARIABLE).
- ``preferred_module_patterns`` — Module path patterns to prioritize.
- ``relationship_preferences`` — Relationship types to prioritize
  (CALLS, DEFINES, etc.).
- ``excluded_patterns`` — Patterns to exclude from results.
- ``priority_packages`` — Packages to rank highest.
- ``secondary_packages`` — Packages to rank as secondary candidates.
- ``retrieval_profile`` — Engineering goal label (IMPLEMENTATION,
  INTERFACE, REGISTRY, etc.).

Public API
----------

.. code-block:: python

    from packages.planning import (
        ContextPlan,
        ContextPlanner,
        Intent,
        EngineeringIntentRule,
        IntentRuleEngine,
        PlanningRule,
        RuleEngine,
    )

    planner = ContextPlanner()
    plan = planner.build(
        user_messages=["Explain ProviderFactory"],
        repository_index=index,
    )

    # Access retrieval hints
    print(plan.retrieval_profile)  # e.g., "ARCHITECTURE"
    print(plan.preferred_symbol_types)  # e.g., ("CLASS", "FUNCTION")
"""

from __future__ import annotations

from packages.planning.intent import Intent
from packages.planning.intent_rules import (
    BUILTIN_INTENT_RULES,
    EngineeringIntentRule,
    IntentRuleEngine,
)
from packages.planning.plan import ContextPlan
from packages.planning.planner import ContextPlanner
from packages.planning.rules import (
    BUILTIN_RULES,
    PlanningRule,
    RuleEngine,
)

__all__ = [
    # Core
    "ContextPlan",
    "ContextPlanner",
    "Intent",
    # Intent rules
    "BUILTIN_INTENT_RULES",
    "EngineeringIntentRule",
    "IntentRuleEngine",
    # Planning rules
    "BUILTIN_RULES",
    "PlanningRule",
    "RuleEngine",
]