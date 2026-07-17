"""Tests for planning rules and rule engine.

Tests deterministic rule matching, first-match behaviour, and ContextPlan
production for all defined intents.
"""

from __future__ import annotations

import pytest

from packages.planning.rules import (
    BUILTIN_RULES,
    PlanningRule,
    RuleEngine,
)


class TestPlanningRule:
    """Test PlanningRule dataclass."""

    def test_planning_rule_is_frozen(self):
        """PlanningRule is immutable."""
        rule = PlanningRule(
            intent="EXPLAIN",
            relationship_expansion=True,
            maximum_depth=1,
            include_callers=True,
            include_callees=True,
            include_modules=True,
            include_diagnostics=False,
            ranking_profile="EXPLAIN",
            estimated_complexity="MODERATE",
        )
        with pytest.raises(Exception):
            rule.intent = "DEBUG"

    def test_planning_rule_defaults(self):
        """PlanningRule has sensible defaults for estimated_complexity."""
        rule = PlanningRule(
            intent="SEARCH",
            relationship_expansion=False,
            maximum_depth=0,
            include_callers=False,
            include_callees=False,
            include_modules=False,
            include_diagnostics=False,
            ranking_profile="SEARCH",
        )
        assert rule.estimated_complexity == "MODERATE"


class TestBuiltinRules:
    """Test BUILTIN_RULES configuration."""

    def test_builtin_rules_count(self):
        """BUILTIN_RULES contains all 7 rules."""
        assert len(BUILTIN_RULES) == 7

    def test_builtin_rules_intents(self):
        """BUILTIN_RULES contains all expected intents."""
        intents = {rule.intent for rule in BUILTIN_RULES}
        expected = {"EXPLAIN", "IMPLEMENT", "REFACTOR", "DEBUG", "TEST", "SEARCH", "DEFAULT"}
        assert intents == expected

    def test_explain_rule(self):
        """EXPLAIN rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "EXPLAIN")
        assert rule.relationship_expansion is True
        assert rule.maximum_depth == 1
        assert rule.include_callers is True
        assert rule.include_callees is True
        assert rule.include_modules is True
        assert rule.include_diagnostics is False
        assert rule.ranking_profile == "EXPLAIN"

    def test_implement_rule(self):
        """IMPLEMENT rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "IMPLEMENT")
        assert rule.relationship_expansion is True
        assert rule.maximum_depth == 1
        assert rule.include_callers is False
        assert rule.include_callees is True
        assert rule.include_modules is True
        assert rule.include_diagnostics is False
        assert rule.ranking_profile == "IMPLEMENT"

    def test_refactor_rule(self):
        """REFACTOR rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "REFACTOR")
        assert rule.relationship_expansion is True
        assert rule.maximum_depth == 1
        assert rule.include_callers is True
        assert rule.include_callees is True
        assert rule.include_modules is True
        assert rule.include_diagnostics is False
        assert rule.ranking_profile == "REFACTOR"

    def test_debug_rule(self):
        """DEBUG rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "DEBUG")
        assert rule.relationship_expansion is True
        assert rule.maximum_depth == 2
        assert rule.include_callers is True
        assert rule.include_callees is True
        assert rule.include_modules is True
        assert rule.include_diagnostics is True
        assert rule.ranking_profile == "DEBUG"

    def test_test_rule(self):
        """TEST rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "TEST")
        assert rule.relationship_expansion is True
        assert rule.maximum_depth == 1
        assert rule.include_callers is True
        assert rule.include_callees is False
        assert rule.include_modules is True
        assert rule.include_diagnostics is True
        assert rule.ranking_profile == "TEST"

    def test_search_rule(self):
        """SEARCH rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "SEARCH")
        assert rule.relationship_expansion is False
        assert rule.maximum_depth == 0
        assert rule.include_callers is False
        assert rule.include_callees is False
        assert rule.include_modules is False
        assert rule.include_diagnostics is False
        assert rule.ranking_profile == "SEARCH"

    def test_default_rule(self):
        """DEFAULT rule configuration matches spec."""
        rule = next(r for r in BUILTIN_RULES if r.intent == "DEFAULT")
        assert rule.relationship_expansion is False
        assert rule.maximum_depth == 0
        assert rule.include_callers is False
        assert rule.include_callees is False
        assert rule.include_modules is True
        assert rule.include_diagnostics is False
        assert rule.ranking_profile == "DEFAULT"


class TestRuleEngine:
    """Test RuleEngine matching and plan production."""

    def test_rule_engine_default_rules(self):
        """RuleEngine uses BUILTIN_RULES by default."""
        engine = RuleEngine()
        assert engine.rules == BUILTIN_RULES

    def test_rule_engine_custom_rules(self):
        """RuleEngine accepts custom rules with DEFAULT fallback."""
        custom_rules = (
            PlanningRule(
                intent="CUSTOM",
                relationship_expansion=False,
                maximum_depth=0,
                include_callers=False,
                include_callees=False,
                include_modules=False,
                include_diagnostics=False,
                ranking_profile="CUSTOM",
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
            ),
        )
        engine = RuleEngine(rules=custom_rules)
        assert engine.rules == custom_rules

    def test_match_explain(self):
        """Match EXPLAIN intent."""
        engine = RuleEngine()
        rule = engine.match("EXPLAIN")
        assert rule.intent == "EXPLAIN"

    def test_match_implement(self):
        """Match IMPLEMENT intent."""
        engine = RuleEngine()
        rule = engine.match("IMPLEMENT")
        assert rule.intent == "IMPLEMENT"

    def test_match_refactor(self):
        """Match REFACTOR intent."""
        engine = RuleEngine()
        rule = engine.match("REFACTOR")
        assert rule.intent == "REFACTOR"

    def test_match_debug(self):
        """Match DEBUG intent."""
        engine = RuleEngine()
        rule = engine.match("DEBUG")
        assert rule.intent == "DEBUG"

    def test_match_test(self):
        """Match TEST intent."""
        engine = RuleEngine()
        rule = engine.match("TEST")
        assert rule.intent == "TEST"

    def test_match_search(self):
        """Match SEARCH intent."""
        engine = RuleEngine()
        rule = engine.match("SEARCH")
        assert rule.intent == "SEARCH"

    def test_match_default(self):
        """Match DEFAULT intent."""
        engine = RuleEngine()
        rule = engine.match("DEFAULT")
        assert rule.intent == "DEFAULT"

    def test_match_unknown_returns_default(self):
        """Unknown intent falls back to DEFAULT rule."""
        engine = RuleEngine()
        rule = engine.match("UNKNOWN_INTENT")
        assert rule.intent == "DEFAULT"

    def test_build_plan_explain(self):
        """build_plan produces correct ContextPlan for EXPLAIN."""
        engine = RuleEngine()
        plan = engine.build_plan("EXPLAIN")

        assert plan.intent == "EXPLAIN"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.maximum_depth == 1
        assert plan.include_callers is True
        assert plan.include_callees is True
        assert plan.include_modules is True
        assert plan.include_diagnostics is False
        assert plan.ranking_profile == "EXPLAIN"

    def test_build_plan_debug(self):
        """build_plan produces correct ContextPlan for DEBUG."""
        engine = RuleEngine()
        plan = engine.build_plan("DEBUG")

        assert plan.intent == "DEBUG"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.maximum_depth == 2
        assert plan.include_diagnostics is True
        assert plan.ranking_profile == "DEBUG"

    def test_build_plan_search(self):
        """build_plan produces correct ContextPlan for SEARCH."""
        engine = RuleEngine()
        plan = engine.build_plan("SEARCH")

        assert plan.intent == "SEARCH"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is False
        assert plan.maximum_depth == 0
        assert plan.include_callers is False
        assert plan.include_callees is False
        assert plan.include_modules is False
        assert plan.include_diagnostics is False
        assert plan.ranking_profile == "SEARCH"

    def test_build_plan_default(self):
        """build_plan produces correct ContextPlan for DEFAULT."""
        engine = RuleEngine()
        plan = engine.build_plan("DEFAULT")

        assert plan.intent == "DEFAULT"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is False
        assert plan.maximum_depth == 0
        assert plan.include_modules is True
        assert plan.ranking_profile == "DEFAULT"

    def test_build_plan_unknown_returns_default(self):
        """build_plan for unknown intent returns DEFAULT plan."""
        engine = RuleEngine()
        plan = engine.build_plan("NONEXISTENT")

        assert plan.intent == "DEFAULT"
        assert plan.ranking_profile == "DEFAULT"

    def test_build_plan_is_immutable(self):
        """ContextPlan is immutable."""
        engine = RuleEngine()
        plan = engine.build_plan("EXPLAIN")

        with pytest.raises(Exception):
            plan.intent = "DEBUG"

    def test_build_plan_primary_symbols_empty(self):
        """primary_symbols is always empty tuple."""
        engine = RuleEngine()
        plan = engine.build_plan("EXPLAIN")
        assert plan.primary_symbols == ()


class TestFirstMatchBehaviour:
    """Test first-match rule behaviour."""

    def test_first_rule_matches(self):
        """First matching rule is returned."""
        custom_rules = (
            PlanningRule(
                intent="FIRST",
                relationship_expansion=True,
                maximum_depth=1,
                include_callers=True,
                include_callees=False,
                include_modules=True,
                include_diagnostics=False,
                ranking_profile="FIRST",
            ),
            PlanningRule(
                intent="SECOND",
                relationship_expansion=False,
                maximum_depth=0,
                include_callers=False,
                include_callees=True,
                include_modules=False,
                include_diagnostics=True,
                ranking_profile="SECOND",
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
            ),
        )
        engine = RuleEngine(rules=custom_rules)
        rule = engine.match("FIRST")
        assert rule.intent == "FIRST"
        assert rule.ranking_profile == "FIRST"

    def test_custom_rules_override_builtin(self):
        """Custom rules completely override builtin rules."""
        custom_rules = (
            PlanningRule(
                intent="EXPLAIN",
                relationship_expansion=False,
                maximum_depth=0,
                include_callers=False,
                include_callees=False,
                include_modules=False,
                include_diagnostics=False,
                ranking_profile="CUSTOM_EXPLAIN",
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
            ),
        )
        engine = RuleEngine(rules=custom_rules)
        rule = engine.match("EXPLAIN")
        assert rule.ranking_profile == "CUSTOM_EXPLAIN"
        assert rule.relationship_expansion is False
