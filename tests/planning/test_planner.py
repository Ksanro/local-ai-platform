"""Tests for ContextPlanner.

Tests the full planning pipeline: intent detection → rule matching →
ContextPlan production. Verifies deterministic planning and integration
with the rule engine.
"""

from __future__ import annotations

import pytest

from packages.planning.planner import ContextPlanner
from packages.planning.rules import PlanningRule, RuleEngine


class TestContextPlanner:
    """Test ContextPlanner build method."""

    def test_build_explain_intent(self):
        """ContextPlan for explain intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Explain how ProviderFactory works"])

        assert plan.intent == "EXPLAIN"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.ranking_profile == "EXPLAIN"

    def test_build_implement_intent(self):
        """ContextPlan for implement intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Implement a new provider"])

        assert plan.intent == "IMPLEMENT"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.ranking_profile == "IMPLEMENT"

    def test_build_refactor_intent(self):
        """ContextPlan for refactor intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Refactor the ContextBuilder"])

        assert plan.intent == "REFACTOR"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.ranking_profile == "REFACTOR"

    def test_build_debug_intent(self):
        """ContextPlan for debug intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Fix failing tests"])

        assert plan.intent == "DEBUG"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.maximum_depth == 2
        assert plan.include_diagnostics is True
        assert plan.ranking_profile == "DEBUG"

    def test_build_test_intent(self):
        """ContextPlan for test intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Run the test suite"])

        assert plan.intent == "TEST"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is True
        assert plan.include_callers is True
        assert plan.include_callees is False
        assert plan.ranking_profile == "TEST"

    def test_build_search_intent(self):
        """ContextPlan for search intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Find dead code"])

        assert plan.intent == "SEARCH"
        assert plan.primary_symbols == ()
        assert plan.relationship_expansion is False
        assert plan.maximum_depth == 0
        assert plan.include_callers is False
        assert plan.include_callees is False
        assert plan.ranking_profile == "SEARCH"

    def test_build_unknown_uses_default(self):
        """Unknown requests use DEFAULT intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Random unrelated message"])

        assert plan.intent == "DEFAULT"
        assert plan.ranking_profile == "DEFAULT"

    def test_build_empty_messages(self):
        """Empty messages produce DEFAULT intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=[])

        assert plan.intent == "DEFAULT"
        assert plan.ranking_profile == "DEFAULT"

    def test_build_empty_string_messages(self):
        """Empty string messages produce DEFAULT intent."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=[""])

        assert plan.intent == "DEFAULT"
        assert plan.ranking_profile == "DEFAULT"

    def test_repository_index_not_used(self):
        """repository_index parameter is accepted but not used."""
        planner = ContextPlanner()
        # Should not raise even without repository_index
        plan = planner.build(user_messages=["Explain this"])
        assert plan.intent == "EXPLAIN"

    def test_repository_index_none(self):
        """Passing None as repository_index is fine."""
        planner = ContextPlanner()
        plan = planner.build(
            user_messages=["Explain this"],
            repository_index=None,
        )
        assert plan.intent == "EXPLAIN"


class TestDeterministicPlanning:
    """Test that planning is deterministic."""

    def test_same_input_same_output(self):
        """Same input always produces same output."""
        planner = ContextPlanner()
        messages = ["Explain how ProviderFactory works"]

        plan1 = planner.build(user_messages=messages)
        plan2 = planner.build(user_messages=messages)

        assert plan1.intent == plan2.intent
        assert plan1.ranking_profile == plan2.ranking_profile
        assert plan1.relationship_expansion == plan2.relationship_expansion
        assert plan1.maximum_depth == plan2.maximum_depth
        assert plan1.primary_symbols == plan2.primary_symbols

    def test_deterministic_multiple_runs(self):
        """Deterministic across multiple different intents."""
        planner = ContextPlanner()

        test_cases = [
            (["Explain this"], "EXPLAIN"),
            (["Implement feature"], "IMPLEMENT"),
            (["Refactor code"], "REFACTOR"),
            (["Fix bug"], "DEBUG"),
            (["Run the test suite"], "TEST"),
            (["Find symbol"], "SEARCH"),
            (["Random"], "DEFAULT"),
        ]

        for messages, expected_intent in test_cases:
            plan1 = planner.build(user_messages=messages)
            plan2 = planner.build(user_messages=messages)
            assert plan1.intent == expected_intent
            assert plan2.intent == expected_intent
            assert plan1.intent == plan2.intent


class TestContextPlanImmutability:
    """Test ContextPlan immutability."""

    def test_context_plan_is_frozen(self):
        """ContextPlan cannot be modified after creation."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Explain this"])

        with pytest.raises(Exception):
            plan.intent = "DEBUG"  # type: ignore[misc]

        with pytest.raises(Exception):
            plan.ranking_profile = "CUSTOM"  # type: ignore[misc]

        with pytest.raises(Exception):
            plan.relationship_expansion = False  # type: ignore[misc]

    def test_context_plan_primary_symbols_immutable(self):
        """primary_symbols tuple cannot be modified."""
        planner = ContextPlanner()
        plan = planner.build(user_messages=["Explain this"])

        assert plan.primary_symbols == ()
        # primary_symbols is a tuple, should be immutable
        with pytest.raises(Exception):
            plan.primary_symbols = ("some_symbol",)  # type: ignore[misc]


class TestCustomRuleEngine:
    """Test ContextPlanner with custom rule engine."""

    def test_custom_rule_engine(self):
        """Custom rule engine is used by planner."""
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
        rule_engine = RuleEngine(rules=custom_rules)
        planner = ContextPlanner(rule_engine=rule_engine)

        plan = planner.build(user_messages=["Explain this"])

        # Should use custom rule for EXPLAIN
        assert plan.ranking_profile == "CUSTOM_EXPLAIN"
        assert plan.relationship_expansion is False

    def test_custom_rule_engine_unknown_fallback(self):
        """Custom rule engine falls back to DEFAULT for unknown intents."""
        custom_rules = (
            PlanningRule(
                intent="EXPLAIN",
                relationship_expansion=True,
                maximum_depth=1,
                include_callers=True,
                include_callees=True,
                include_modules=True,
                include_diagnostics=False,
                ranking_profile="EXPLAIN",
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
        rule_engine = RuleEngine(rules=custom_rules)
        planner = ContextPlanner(rule_engine=rule_engine)

        # Unknown intent should fall back to DEFAULT
        plan = planner.build(user_messages=["Random message"])
        assert plan.intent == "DEFAULT"
        assert plan.ranking_profile == "DEFAULT"
