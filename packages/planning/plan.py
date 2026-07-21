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
- Retrieval hints are deterministic engineering intent signals.

Planning v2 — Engineering Intent Resolution
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

Architecture
------------

User Messages
       |
       v
Intent Detection (intent.py)
       |
       v
Engineering Intent Resolution (intent_rules.py)
       |
       v
ContextPlan (with retrieval hints)
       |
       v
RankingEngine (consumes hints for scoring)

Public API
----------

.. code-block:: python

    from packages.planning.plan import ContextPlan

    plan = ContextPlan(
        intent="EXPLAIN",
        retrieval_profile="ARCHITECTURE",
        preferred_symbol_types=("CLASS", "FUNCTION"),
    )

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

        # Planning v2 — Retrieval Hints

        retrieval_profile: Engineering goal label. Examples:
            IMPLEMENTATION, INTERFACE, REGISTRY, ENTRY_POINT,
            EXECUTION_FLOW, CONFIGURATION, TEST, DEPENDENCY_INJECTION,
            API_BOUNDARY, SERIALIZER, WORKFLOW, TASK, CAPABILITY,
            PROVIDER, VALIDATION, FACTORY, EXTENSION, ARCHITECTURE.
            Defaults to "DEFAULT".
        preferred_symbol_types: Symbol types to prioritize during
            ranking. Examples: ("CLASS",), ("CLASS", "FUNCTION").
            Empty tuple means no preference.
        preferred_module_patterns: Module path patterns to prioritize.
            Examples: ("providers/", "api/"). Empty tuple means no
            preference.
        relationship_preferences: Relationship types to prioritize.
            Examples: ("CALLS",), ("DEFINES", "CALLS"). Empty tuple
            means no preference.
        excluded_patterns: Patterns to exclude from results. Examples:
            ("tests/", "generated/"). Empty tuple means no exclusions.
        priority_packages: Packages to rank highest. Examples:
            ("packages/providers/",). Empty tuple means no preference.
        secondary_packages: Packages to rank as secondary candidates.
            Examples: ("packages/core/",). Empty tuple means no
            preference.
        estimated_complexity: Estimated complexity of the request.

    Constraints:
        - primary_symbols is always () for this version.
        - No mutable state.
        - Retrieval hints are deterministic.
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

    # --- Planning v2 retrieval hints ---

    retrieval_profile: str = "DEFAULT"
    """Engineering goal label for retrieval."""

    preferred_symbol_types: tuple[str, ...] = ()
    """Symbol types to prioritize during ranking."""

    preferred_module_patterns: tuple[str, ...] = ()
    """Module path patterns to prioritize."""

    relationship_preferences: tuple[str, ...] = ()
    """Relationship types to prioritize."""

    excluded_patterns: tuple[str, ...] = ()
    """Patterns to exclude from results."""

    priority_packages: tuple[str, ...] = ()
    """Packages to rank highest."""

    secondary_packages: tuple[str, ...] = ()
    """Packages to rank as secondary candidates."""