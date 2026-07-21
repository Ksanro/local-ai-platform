"""Context Planner.

Selects the retrieval strategy before context construction begins.
No AI or LLM inference is performed. Planning is entirely deterministic.

Architecture
------------

User Messages
    ↓
Intent Detection (intent.py)
    ↓
Engineering Intent Resolution (intent_rules.py)
    ↓
Rule Matching (rules.py)
    ↓
ContextPlan

The planner does NOT:
- access providers
- execute repository analysis
- parse source files
- modify RepositoryIndex
- modify ContextBuilder
- search RepositoryIndex
- resolve symbol names
- perform fuzzy matching

The planner only produces a ContextPlan.

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

from typing import TYPE_CHECKING

from packages.planning.intent import Intent
from packages.planning.intent_rules import IntentRuleEngine
from packages.planning.plan import ContextPlan
from packages.planning.rules import RuleEngine

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex


class ContextPlanner:
    """Deterministic context planner.

    Detects intent from user messages, resolves engineering intent,
    matches planning rules, and produces an immutable ContextPlan
    with retrieval hints.

    The planner is stateless and deterministic. Same input always
    produces the same output.

    Attributes:
        _rule_engine: The rule engine used for rule matching.
        _intent_rule_engine: The engine used for engineering intent resolution.
    """

    def __init__(self, rule_engine: RuleEngine | None = None) -> None:
        """Initialize the planner.

        Args:
            rule_engine: Optional custom rule engine. Defaults to
                RuleEngine() with BUILTIN_RULES.
        """
        self._rule_engine = rule_engine if rule_engine is not None else RuleEngine()
        self._intent_rule_engine = IntentRuleEngine()

    def build(
        self,
        user_messages: list[str],
        repository_index: RepositoryIndex | None = None,
    ) -> ContextPlan:
        """Build a ContextPlan from user messages.

        Detects intent from messages, resolves engineering intent
        via IntentRuleEngine, matches against planning rules,
        and returns an immutable ContextPlan with retrieval hints.

        The repository_index parameter is accepted for API compatibility
        but is not used. Planning is not retrieval.

        Args:
            user_messages: List of user message strings.
            repository_index: Optional RepositoryIndex (not used).

        Returns:
            An immutable ContextPlan with retrieval hints.
        """
        # Combine messages for intent detection and engineering resolution.
        combined = " ".join(m for m in user_messages if m and m.strip())

        # Step 1: Detect high-level intent from user messages.
        intent = Intent.detect(user_messages)

        # Step 2: Resolve engineering intent (retrieval profile + hints).
        engineering_plan = self._intent_rule_engine.resolve(combined, intent)

        # Step 3: Match planning rule for structural configuration.
        plan = self._rule_engine.build_plan(intent)

        # Step 4: Merge engineering hints into the plan.
        # The structural config comes from the PlanningRule,
        # while the retrieval hints come from the EngineeringIntentRule.
        return ContextPlan(
            intent=plan.intent,
            primary_symbols=plan.primary_symbols,
            relationship_expansion=plan.relationship_expansion,
            ranking_profile=plan.ranking_profile,
            maximum_depth=plan.maximum_depth,
            include_callers=plan.include_callers,
            include_callees=plan.include_callees,
            include_modules=plan.include_modules,
            include_diagnostics=plan.include_diagnostics,
            estimated_complexity=plan.estimated_complexity,
            # Engineering retrieval hints from IntentRuleEngine.
            retrieval_profile=engineering_plan.retrieval_profile,
            preferred_symbol_types=engineering_plan.preferred_symbol_types,
            preferred_module_patterns=engineering_plan.preferred_module_patterns,
            relationship_preferences=engineering_plan.relationship_preferences,
            excluded_patterns=engineering_plan.excluded_patterns,
            priority_packages=engineering_plan.priority_packages,
            secondary_packages=engineering_plan.secondary_packages,
        )