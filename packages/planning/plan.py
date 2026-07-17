"""Immutable ContextPlan model.

Defines the output of the ContextPlanner. This is the single source of
truth for retrieval configuration.

ContextPlan is consumed by RepositoryContextStage, RankingEngine,
BudgetEstimator, and Serializer.

Constraints
-----------

- Immutable (frozen=True).
- No mutable state.
- primary_symbols is always empty tuple for this version (planning is
  not retrieval).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPlan:
    """Immutable retrieval plan produced by ContextPlanner.

    Attributes:
        intent: Detected intent from user messages.
        primary_symbols: Explicitly resolved symbols. Always empty for
            this version -- planning is not retrieval.
        relationship_expansion: Whether to expand relationships during
            context construction.
        ranking_profile: Ranking profile to use for symbol scoring.
        maximum_depth: Maximum relationship depth for traversal.
        include_callers: Whether to include direct callers.
        include_callees: Whether to include direct callees.
        include_modules: Whether to include module-level context.
        include_diagnostics: Whether to include diagnostic information.
        estimated_complexity: Estimated complexity of the request.

    Constraints:
        - primary_symbols is always () for this version.
        - No mutable state.
    """

    intent: str
    primary_symbols: tuple[str, ...] = ()
    relationship_expansion: bool = False
    ranking_profile: str = "DEFAULT"
    maximum_depth: int = 0
    include_callers: bool = False
    include_callees: bool = False
    include_modules: bool = False
    include_diagnostics: bool = False
    estimated_complexity: str = "SIMPLE"
