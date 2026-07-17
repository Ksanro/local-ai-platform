"""Planning rules and rule engine.

Defines deterministic rules for each intent and provides the rule
matching engine. Rules are evaluated in order. First matching rule
wins.

Rules Table
-----------

Each intent maps to a deterministic PlanningRule:

- EXPLAIN: relationship_expansion=True, maximum_depth=1,
  include_callers=True, include_callees=True, include_modules=True,
  include_diagnostics=False, ranking_profile="EXPLAIN"
- IMPLEMENT: relationship_expansion=True, maximum_depth=1,
  include_callers=False, include_callees=True, include_modules=True,
  include_diagnostics=False, ranking_profile="IMPLEMENT"
- REFACTOR: relationship_expansion=True, maximum_depth=1,
  include_callers=True, include_callees=True, include_modules=True,
  include_diagnostics=False, ranking_profile="REFACTOR"
- DEBUG: relationship_expansion=True, maximum_depth=2,
  include_callers=True, include_callees=True, include_modules=True,
  include_diagnostics=True, ranking_profile="DEBUG"
- TEST: relationship_expansion=True, maximum_depth=1,
  include_callers=True, include_callees=False, include_modules=True,
  include_diagnostics=True, ranking_profile="TEST"
- SEARCH: relationship_expansion=False, maximum_depth=0,
  include_callers=False, include_callees=False, include_modules=False,
  include_diagnostics=False, ranking_profile="SEARCH"
- DEFAULT: relationship_expansion=False, maximum_depth=0,
  include_callers=False, include_callees=False, include_modules=True,
  include_diagnostics=False, ranking_profile="DEFAULT"

Constraints
-----------

- Rules are evaluated in order.
- First matching rule wins.
- Future rules may be registered without modifying ContextPlanner.
- No side effects during rule evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.planning.plan import ContextPlan


@dataclass(frozen=True)
class PlanningRule:
    """A single deterministic planning rule.

    Attributes:
        intent: The intent this rule applies to.
        relationship_expansion: Whether to expand relationships.
        maximum_depth: Maximum relationship traversal depth.
        include_callers: Whether to include direct callers.
        include_callees: Whether to include direct callees.
        include_modules: Whether to include module-level context.
        include_diagnostics: Whether to include diagnostic information.
        ranking_profile: Ranking profile to use for symbol scoring.
        estimated_complexity: Estimated complexity of requests with this intent.
    """

    intent: str
    relationship_expansion: bool
    maximum_depth: int
    include_callers: bool
    include_callees: bool
    include_modules: bool
    include_diagnostics: bool
    ranking_profile: str
    estimated_complexity: str = "MODERATE"


# Built-in planning rules. Evaluated in order. First match wins.
BUILTIN_RULES: tuple[PlanningRule, ...] = (
    PlanningRule(
        intent="EXPLAIN",
        relationship_expansion=True,
        maximum_depth=1,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="EXPLAIN",
        estimated_complexity="MODERATE",
    ),
    PlanningRule(
        intent="IMPLEMENT",
        relationship_expansion=True,
        maximum_depth=1,
        include_callers=False,
        include_callees=True,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="IMPLEMENT",
        estimated_complexity="MODERATE",
    ),
    PlanningRule(
        intent="REFACTOR",
        relationship_expansion=True,
        maximum_depth=1,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="REFACTOR",
        estimated_complexity="COMPLEX",
    ),
    PlanningRule(
        intent="DEBUG",
        relationship_expansion=True,
        maximum_depth=2,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=True,
        ranking_profile="DEBUG",
        estimated_complexity="COMPLEX",
    ),
    PlanningRule(
        intent="TEST",
        relationship_expansion=True,
        maximum_depth=1,
        include_callers=True,
        include_callees=False,
        include_modules=True,
        include_diagnostics=True,
        ranking_profile="TEST",
        estimated_complexity="MODERATE",
    ),
    PlanningRule(
        intent="SEARCH",
        relationship_expansion=False,
        maximum_depth=0,
        include_callers=False,
        include_callees=False,
        include_modules=False,
        include_diagnostics=False,
        ranking_profile="SEARCH",
        estimated_complexity="SIMPLE",
    ),
    PlanningRule(
        intent="DEFAULT",
        relationship_expansion=False,
        maximum_depth=0,
        include_callers=False,
        include_callees=False,
        include_modules=True,
        include_diagnostics=False,
        ranking_profile="DEFAULT",
        estimated_complexity="SIMPLE",
    ),
)


class RuleEngine:
    """Evaluates planning rules and produces a ContextPlan.

    Rules are evaluated in order. First matching rule wins.
    The engine is stateless and deterministic.

    Attributes:
        _rules: Ordered list of planning rules to evaluate.
    """

    def __init__(self, rules: tuple[PlanningRule, ...] | None = None) -> None:
        """Initialize the rule engine.

        Args:
            rules: Optional custom rule list. Defaults to BUILTIN_RULES.

        Raises:
            ValueError: If custom rules are provided without a DEFAULT rule.
        """
        rules = rules if rules is not None else BUILTIN_RULES
        self._rules = rules
        # Validate that a DEFAULT rule exists when custom rules are used.
        # This prevents silent fallback to undefined behavior per-request.
        if rules is not BUILTIN_RULES and not any(r.intent == "DEFAULT" for r in self._rules):
            raise ValueError("Custom rules must include a DEFAULT rule")

    @property
    def rules(self) -> tuple[PlanningRule, ...]:
        """The ordered list of planning rules."""
        return self._rules

    def match(self, intent: str) -> PlanningRule:
        """Find the first matching rule for the given intent.

        Rules are evaluated in order. First match wins.
        If no rule matches the intent, returns the DEFAULT rule.

        Args:
            intent: The detected intent string.

        Returns:
            The first matching PlanningRule.
        """
        for rule in self._rules:
            if rule.intent == intent:
                return rule

        # Fallback: return DEFAULT rule.
        for rule in self._rules:
            if rule.intent == "DEFAULT":
                return rule

        raise ValueError(f"No rule found for intent: {intent}")

    def build_plan(self, intent: str) -> ContextPlan:
        """Build a ContextPlan from the matched rule.

        Creates an immutable ContextPlan with primary_symbols=().

        Args:
            intent: The detected intent string.

        Returns:
            An immutable ContextPlan.
        """
        rule = self.match(intent)
        return ContextPlan(
            intent=rule.intent,
            primary_symbols=(),
            relationship_expansion=rule.relationship_expansion,
            ranking_profile=rule.ranking_profile,
            maximum_depth=rule.maximum_depth,
            include_callers=rule.include_callers,
            include_callees=rule.include_callees,
            include_modules=rule.include_modules,
            include_diagnostics=rule.include_diagnostics,
            estimated_complexity=rule.estimated_complexity,
        )
