"""Tests for Engineering Intent Resolution (Planning v2).

Tests cover:
- Implementation queries
- Explanation queries
- Debugging queries
- Workflow queries
- Provider queries
- Registry queries
- Serializer queries
- Architecture queries
- Deterministic planning
- Conflicting rules
- All engineering retrieval profiles

Target coverage: >95%
"""

from __future__ import annotations

import pytest

from packages.planning.intent_rules import (
    BUILTIN_INTENT_RULES,
    EngineeringIntentRule,
    IntentRuleEngine,
)
from packages.planning.plan import ContextPlan
from packages.planning.rules import (
    BUILTIN_RULES,
    PlanningRule,
    RuleEngine,
)


# ---------------------------------------------------------------------------
# EngineeringIntentRule model tests
# ---------------------------------------------------------------------------


class TestEngineeringIntentRule:
    """Tests for the EngineeringIntentRule dataclass."""

    def test_default_values(self):
        """EngineeringIntentRule should have sensible defaults."""
        rule = EngineeringIntentRule(
            trigger_patterns=("test",),
            retrieval_profile="TEST",
        )
        assert rule.preferred_symbol_types == ()
        assert rule.preferred_module_patterns == ()
        assert rule.relationship_preferences == ()
        assert rule.excluded_patterns == ()
        assert rule.priority_packages == ()
        assert rule.secondary_packages == ()
        assert rule.priority == 50

    def test_frozen(self):
        """EngineeringIntentRule should be immutable."""
        rule = EngineeringIntentRule(
            trigger_patterns=("test",),
            retrieval_profile="TEST",
        )
        with pytest.raises(Exception):
            rule.trigger_patterns = ("new",)


# ---------------------------------------------------------------------------
# BUILTIN_INTENT_RULES tests
# ---------------------------------------------------------------------------


class TestBuiltinIntentRules:
    """Tests for BUILTIN_INTENT_RULES."""

    def test_has_default_rule(self):
        """BUILTIN_INTENT_RULES should include a DEFAULT fallback rule."""
        default_rules = [r for r in BUILTIN_INTENT_RULES if r.retrieval_profile == "DEFAULT"]
        assert len(default_rules) >= 1

    def test_has_implementations_rules(self):
        """BUILTIN_INTENT_RULES should include IMPLEMENTATION rules."""
        impl_rules = [r for r in BUILTIN_INTENT_RULES if r.retrieval_profile == "IMPLEMENTATION"]
        assert len(impl_rules) >= 1

    def test_has_all_profiles(self):
        """BUILTIN_INTENT_RULES should cover all engineering profiles."""
        profiles = {r.retrieval_profile for r in BUILTIN_INTENT_RULES}
        expected_profiles = {
            "IMPLEMENTATION",
            "INTERFACE",
            "REGISTRY",
            "ENTRY_POINT",
            "EXECUTION_FLOW",
            "CONFIGURATION",
            "TEST",
            "DEPENDENCY_INJECTION",
            "API_BOUNDARY",
            "SERIALIZER",
            "WORKFLOW",
            "TASK",
            "CAPABILITY",
            "PROVIDER",
            "VALIDATION",
            "FACTORY",
            "EXTENSION",
            "ARCHITECTURE",
            "SIMILAR",
            "DEFAULT",
        }
        assert expected_profiles.issubset(profiles)


# ---------------------------------------------------------------------------
# IntentRuleEngine tests
# ---------------------------------------------------------------------------


class TestIntentRuleEngine:
    """Tests for the IntentRuleEngine."""

    def test_match_implementation_implement(self):
        """'implement X' should match IMPLEMENTATION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("implement authentication")
        assert rule.retrieval_profile == "IMPLEMENTATION"

    def test_match_implementation_locate(self):
        """'locate X' should match IMPLEMENTATION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("locate the service implementation")
        assert rule.retrieval_profile == "IMPLEMENTATION"

    def test_match_implementation_implementation(self):
        """'implementation of X' should match IMPLEMENTATION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("what is the implementation of this")
        assert rule.retrieval_profile == "IMPLEMENTATION"

    def test_match_interface(self):
        """'interface' should match INTERFACE profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the API interface")
        assert rule.retrieval_profile == "INTERFACE"

    def test_match_abstract(self):
        """'abstract' should match INTERFACE profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the abstract class")
        assert rule.retrieval_profile == "INTERFACE"

    def test_match_registry(self):
        """'register' should match REGISTRY profile."""
        engine = IntentRuleEngine()
        rule = engine.match("where is the service registry")
        assert rule.retrieval_profile == "REGISTRY"

    def test_match_entry_point(self):
        """'entry point' should match ENTRY_POINT profile."""
        engine = IntentRuleEngine()
        rule = engine.match("what is the application entry point")
        assert rule.retrieval_profile == "ENTRY_POINT"

    def test_match_bootstrap(self):
        """'bootstrap' should match ENTRY_POINT profile."""
        engine = IntentRuleEngine()
        rule = engine.match("how does the application bootstrap")
        assert rule.retrieval_profile == "ENTRY_POINT"

    def test_match_execution_flow(self):
        """'how does' should match EXECUTION_FLOW profile."""
        engine = IntentRuleEngine()
        # Use "call flow" to avoid matching WORKFLOW (which has "pipeline")
        rule = engine.match("how does the call flow work")
        assert rule.retrieval_profile == "EXECUTION_FLOW"

    def test_match_configuration(self):
        """'config' should match CONFIGURATION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("where is Redis configured")
        assert rule.retrieval_profile == "CONFIGURATION"

    def test_match_test(self):
        """'test' should match TEST profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the unit tests")
        assert rule.retrieval_profile == "TEST"

    def test_match_dependency_injection(self):
        """'dependency injection' should match DEPENDENCY_INJECTION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("how is the DI container wired")
        assert rule.retrieval_profile == "DEPENDENCY_INJECTION"

    def test_match_api_boundary(self):
        """'endpoint' should match API_BOUNDARY profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the API endpoints")
        assert rule.retrieval_profile == "API_BOUNDARY"

    def test_match_serializer(self):
        """'serializer' should match SERIALIZER profile."""
        engine = IntentRuleEngine()
        rule = engine.match("how is data serialized")
        assert rule.retrieval_profile == "SERIALIZER"

    def test_match_workflow(self):
        """'workflow' should match WORKFLOW profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the deployment workflow")
        assert rule.retrieval_profile == "WORKFLOW"

    def test_match_task(self):
        """'background task' should match TASK profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the background task")
        assert rule.retrieval_profile == "TASK"

    def test_match_capability(self):
        """'capability' should match CAPABILITY profile."""
        engine = IntentRuleEngine()
        # Avoid "registration" which matches REGISTRY first
        rule = engine.match("find the capability feature")
        assert rule.retrieval_profile == "CAPABILITY"

    def test_match_provider(self):
        """'provider' should match PROVIDER profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the database provider")
        assert rule.retrieval_profile == "PROVIDER"

    def test_match_validation(self):
        """'validation' should match VALIDATION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the validation logic")
        assert rule.retrieval_profile == "VALIDATION"

    def test_match_factory(self):
        """'factory' should match FACTORY profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the factory pattern")
        assert rule.retrieval_profile == "FACTORY"

    def test_match_extension(self):
        """'extension' should match EXTENSION profile."""
        engine = IntentRuleEngine()
        rule = engine.match("find the extension point")
        assert rule.retrieval_profile == "EXTENSION"

    def test_match_architecture(self):
        """'architecture' should match ARCHITECTURE profile."""
        engine = IntentRuleEngine()
        rule = engine.match("why is the architecture designed this way")
        assert rule.retrieval_profile == "ARCHITECTURE"

    def test_match_similar(self):
        """'similar' should match SIMILAR profile."""
        engine = IntentRuleEngine()
        # Avoid "implementation" which matches IMPLEMENTATION first
        rule = engine.match("find similar example")
        assert rule.retrieval_profile == "SIMILAR"

    def test_match_debug(self):
        """'fix' should match IMPLEMENTATION profile with diagnostics."""
        engine = IntentRuleEngine()
        rule = engine.match("fix the authentication bug")
        assert rule.retrieval_profile == "IMPLEMENTATION"

    def test_match_default(self):
        """Unrecognized queries should match DEFAULT profile."""
        engine = IntentRuleEngine()
        rule = engine.match("hello world")
        assert rule.retrieval_profile == "DEFAULT"

    def test_case_insensitive_matching(self):
        """Rule matching should be case-insensitive."""
        engine = IntentRuleEngine()
        rule1 = engine.match("WHERE IS PROVIDERFACTORY")
        rule2 = engine.match("where is providerfactory")
        rule3 = engine.match("Where Is ProviderFactory")
        # "where is" no longer matches IMPLEMENTATION, so these should match DEFAULT
        # or a more specific rule. Let's test with "implement" which is specific.
        rule1 = engine.match("IMPLEMENT authentication")
        rule2 = engine.match("implement AUTHENTICATION")
        rule3 = engine.match("Implement Authentication")
        assert rule1.retrieval_profile == rule2.retrieval_profile
        assert rule2.retrieval_profile == rule3.retrieval_profile
        assert rule1.retrieval_profile == "IMPLEMENTATION"

    def test_resolve_produces_context_plan(self):
        """resolve() should produce a ContextPlan with retrieval hints."""
        engine = IntentRuleEngine()
        plan = engine.resolve("implement authentication service", "SEARCH")
        assert isinstance(plan, ContextPlan)
        assert plan.retrieval_profile == "IMPLEMENTATION"
        assert plan.intent == "SEARCH"

    def test_resolve_includes_preferred_symbol_types(self):
        """resolve() should include preferred_symbol_types from the rule."""
        engine = IntentRuleEngine()
        plan = engine.resolve("implement authentication service", "SEARCH")
        assert "CLASS" in plan.preferred_symbol_types
        assert "FUNCTION" in plan.preferred_symbol_types

    def test_resolve_includes_preferred_module_patterns(self):
        """resolve() should include preferred_module_patterns from the rule."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the API endpoints", "SEARCH")
        # API_BOUNDARY has module patterns
        assert len(plan.preferred_module_patterns) > 0
        assert any("api" in p.lower() for p in plan.preferred_module_patterns)

    def test_resolve_includes_relationship_preferences(self):
        """resolve() should include relationship_preferences from the rule."""
        engine = IntentRuleEngine()
        plan = engine.resolve("how does the call flow work", "EXPLAIN")
        assert "CALLS" in plan.relationship_preferences

    def test_resolve_includes_excluded_patterns(self):
        """resolve() should include excluded_patterns from the rule."""
        engine = IntentRuleEngine()
        plan = engine.resolve("fix the authentication bug", "DEBUG")
        assert len(plan.excluded_patterns) > 0

    def test_custom_rules(self):
        """IntentRuleEngine should accept custom rules."""
        custom_rules = (
            EngineeringIntentRule(
                trigger_patterns=("custom",),
                retrieval_profile="CUSTOM",
                preferred_symbol_types=("CLASS",),
                priority=5,
            ),
            EngineeringIntentRule(
                trigger_patterns=(),
                retrieval_profile="DEFAULT",
                priority=100,
            ),
        )
        engine = IntentRuleEngine(rules=custom_rules)
        rule = engine.match("custom query")
        assert rule.retrieval_profile == "CUSTOM"

    def test_priority_ordering(self):
        """Higher priority rules should be evaluated first."""
        custom_rules = (
            EngineeringIntentRule(
                trigger_patterns=("test",),
                retrieval_profile="LOW_PRIORITY",
                priority=50,
            ),
            EngineeringIntentRule(
                trigger_patterns=("test",),
                retrieval_profile="HIGH_PRIORITY",
                priority=5,
            ),
            EngineeringIntentRule(
                trigger_patterns=(),
                retrieval_profile="DEFAULT",
                priority=100,
            ),
        )
        engine = IntentRuleEngine(rules=custom_rules)
        rule = engine.match("test query")
        # Both "test" rules match, but HIGH_PRIORITY (5) should win over LOW_PRIORITY (50)
        assert rule.retrieval_profile == "HIGH_PRIORITY"


# ---------------------------------------------------------------------------
# RuleEngine tests
# ---------------------------------------------------------------------------


class TestRuleEngine:
    """Tests for the RuleEngine."""

    def test_match_explain(self):
        """RuleEngine should match EXPLAIN intent."""
        engine = RuleEngine()
        rule = engine.match("EXPLAIN")
        assert rule.intent == "EXPLAIN"

    def test_match_implement(self):
        """RuleEngine should match IMPLEMENT intent."""
        engine = RuleEngine()
        rule = engine.match("IMPLEMENT")
        assert rule.intent == "IMPLEMENT"

    def test_match_debug(self):
        """RuleEngine should match DEBUG intent."""
        engine = RuleEngine()
        rule = engine.match("DEBUG")
        assert rule.intent == "DEBUG"

    def test_match_default(self):
        """RuleEngine should match DEFAULT intent."""
        engine = RuleEngine()
        rule = engine.match("UNKNOWN")
        assert rule.intent == "DEFAULT"

    def test_build_plan(self):
        """build_plan should produce a ContextPlan."""
        engine = RuleEngine()
        plan = engine.build_plan("EXPLAIN")
        assert isinstance(plan, ContextPlan)
        assert plan.intent == "EXPLAIN"

    def test_build_plan_has_retrieval_profile(self):
        """build_plan should include retrieval_profile."""
        engine = RuleEngine()
        plan = engine.build_plan("EXPLAIN")
        assert plan.retrieval_profile == "ARCHITECTURE"

    def test_build_plan_has_empty_hints(self):
        """build_plan should have empty hint tuples for structural config."""
        engine = RuleEngine()
        plan = engine.build_plan("SEARCH")
        assert plan.preferred_symbol_types == ()
        assert plan.preferred_module_patterns == ()
        assert plan.priority_packages == ()


# ---------------------------------------------------------------------------
# ContextPlanner integration tests
# ---------------------------------------------------------------------------


class TestContextPlannerIntegration:
    """Integration tests for ContextPlanner with engineering intent."""

    def test_build_integration(self):
        """ContextPlanner.build should produce a ContextPlan with hints."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["implement authentication service"])
        assert isinstance(plan, ContextPlan)
        assert plan.retrieval_profile == "IMPLEMENTATION"
        assert plan.preferred_symbol_types == ("CLASS", "FUNCTION")

    def test_integration_interface_query(self):
        """Interface queries should produce INTERFACE profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["find the API interface"])
        assert plan.retrieval_profile == "INTERFACE"

    def test_integration_registry_query(self):
        """Registry queries should produce REGISTRY profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["where is the service registry"])
        assert plan.retrieval_profile == "REGISTRY"

    def test_integration_workflow_query(self):
        """Workflow queries should produce WORKFLOW profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["find the deployment workflow"])
        assert plan.retrieval_profile == "WORKFLOW"

    def test_integration_provider_query(self):
        """Provider queries should produce PROVIDER profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["find the database provider"])
        assert plan.retrieval_profile == "PROVIDER"

    def test_integration_serializer_query(self):
        """Serializer queries should produce SERIALIZER profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["how is data serialized"])
        assert plan.retrieval_profile == "SERIALIZER"

    def test_integration_architecture_query(self):
        """Architecture queries should produce ARCHITECTURE profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["why is the architecture designed this way"])
        assert plan.retrieval_profile == "ARCHITECTURE"

    def test_integration_debug_query(self):
        """Debug queries should produce IMPLEMENTATION profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["fix the authentication bug"])
        assert plan.retrieval_profile == "IMPLEMENTATION"

    def test_integration_explanation_query(self):
        """Explanation queries should produce ARCHITECTURE profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["explain the architecture"])
        assert plan.retrieval_profile == "ARCHITECTURE"

    def test_integration_empty_query(self):
        """Empty queries should produce DEFAULT profile."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build([])
        assert plan.retrieval_profile == "DEFAULT"

    def test_integration_multiple_messages(self):
        """Multiple messages should be combined for intent detection."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["implement", "authentication service"])
        assert plan.retrieval_profile == "IMPLEMENTATION"


# ---------------------------------------------------------------------------
# Deterministic planning tests
# ---------------------------------------------------------------------------


class TestDeterministicPlanning:
    """Tests for deterministic planning behavior."""

    def test_same_input_same_output(self):
        """Same input should always produce the same output."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        query = "implement ProviderFactory"

        plan1 = planner.build([query])
        plan2 = planner.build([query])
        plan3 = planner.build([query])

        assert plan1.retrieval_profile == plan2.retrieval_profile
        assert plan2.retrieval_profile == plan3.retrieval_profile
        assert plan1.preferred_symbol_types == plan2.preferred_symbol_types
        assert plan2.preferred_symbol_types == plan3.preferred_symbol_types

    def test_rule_engine_deterministic(self):
        """IntentRuleEngine should be deterministic."""
        from packages.planning import IntentRuleEngine

        engine = IntentRuleEngine()
        query = "implement ProviderFactory"

        rule1 = engine.match(query)
        rule2 = engine.match(query)

        assert rule1.retrieval_profile == rule2.retrieval_profile
        assert rule1.preferred_symbol_types == rule2.preferred_symbol_types

    def test_no_side_effects(self):
        """Rule evaluation should have no side effects."""
        from packages.planning import IntentRuleEngine

        engine = IntentRuleEngine()
        query = "implement ProviderFactory"

        rule1 = engine.match(query)
        rule2 = engine.match(query)

        assert rule1.trigger_patterns == rule2.trigger_patterns
        assert rule1.retrieval_profile == rule2.retrieval_profile


# ---------------------------------------------------------------------------
# Conflicting rules tests
# ---------------------------------------------------------------------------


class TestConflictingRules:
    """Tests for conflicting rule resolution."""

    def test_first_match_wins(self):
        """When multiple rules match, first match (highest priority) wins."""
        custom_rules = (
            EngineeringIntentRule(
                trigger_patterns=("fix", "error"),
                retrieval_profile="FIX_PROFILE",
                priority=10,
            ),
            EngineeringIntentRule(
                trigger_patterns=("error",),
                retrieval_profile="ERROR_PROFILE",
                priority=20,
            ),
            EngineeringIntentRule(
                trigger_patterns=(),
                retrieval_profile="DEFAULT",
                priority=100,
            ),
        )
        engine = IntentRuleEngine(rules=custom_rules)
        rule = engine.match("fix the error")
        # Both rules match, but FIX_PROFILE (priority 10) wins over ERROR_PROFILE (priority 20)
        assert rule.retrieval_profile == "FIX_PROFILE"

    def test_conflicting_implementation_and_debug(self):
        """Debug queries should prefer IMPLEMENTATION with diagnostics."""
        from packages.planning import ContextPlanner

        planner = ContextPlanner()
        plan = planner.build(["fix the error in the code"])
        # Debug rule has lower priority than implementation rule
        # but both match "fix" and "error"
        assert plan.retrieval_profile == "IMPLEMENTATION"


# ---------------------------------------------------------------------------
# All retrieval profile tests
# ---------------------------------------------------------------------------


class TestAllRetrievalProfiles:
    """Tests for all engineering retrieval profiles."""

    def test_implementation_profile(self):
        """IMPLEMENTATION profile should have correct hints."""
        engine = IntentRuleEngine()
        plan = engine.resolve("implement authentication service", "SEARCH")
        assert plan.retrieval_profile == "IMPLEMENTATION"
        assert "CLASS" in plan.preferred_symbol_types
        assert "FUNCTION" in plan.preferred_symbol_types

    def test_interface_profile(self):
        """INTERFACE profile should prefer CLASS symbols."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the interface", "SEARCH")
        assert plan.retrieval_profile == "INTERFACE"
        assert plan.preferred_symbol_types == ("CLASS",)

    def test_registry_profile(self):
        """REGISTRY profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the registry", "SEARCH")
        assert plan.retrieval_profile == "REGISTRY"
        assert len(plan.preferred_module_patterns) > 0

    def test_entry_point_profile(self):
        """ENTRY_POINT profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the entry point", "SEARCH")
        assert plan.retrieval_profile == "ENTRY_POINT"
        assert len(plan.preferred_module_patterns) > 0

    def test_execution_flow_profile(self):
        """EXECUTION_FLOW profile should have relationship preferences."""
        engine = IntentRuleEngine()
        plan = engine.resolve("how does the call flow work", "EXPLAIN")
        assert plan.retrieval_profile == "EXECUTION_FLOW"
        assert "CALLS" in plan.relationship_preferences

    def test_configuration_profile(self):
        """CONFIGURATION profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("where is Redis configured", "SEARCH")
        assert plan.retrieval_profile == "CONFIGURATION"
        assert len(plan.preferred_module_patterns) > 0

    def test_test_profile(self):
        """TEST profile should have test module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the tests", "SEARCH")
        assert plan.retrieval_profile == "TEST"
        assert len(plan.preferred_module_patterns) > 0

    def test_dependency_injection_profile(self):
        """DEPENDENCY_INJECTION profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("how is the DI container wired", "SEARCH")
        assert plan.retrieval_profile == "DEPENDENCY_INJECTION"
        assert len(plan.preferred_module_patterns) > 0

    def test_api_boundary_profile(self):
        """API_BOUNDARY profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the API endpoints", "SEARCH")
        assert plan.retrieval_profile == "API_BOUNDARY"
        assert len(plan.preferred_module_patterns) > 0

    def test_serializer_profile(self):
        """SERIALIZER profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("how is data serialized", "SEARCH")
        assert plan.retrieval_profile == "SERIALIZER"
        assert len(plan.preferred_module_patterns) > 0

    def test_workflow_profile(self):
        """WORKFLOW profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the deployment workflow", "SEARCH")
        assert plan.retrieval_profile == "WORKFLOW"
        assert len(plan.preferred_module_patterns) > 0

    def test_task_profile(self):
        """TASK profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the background task", "SEARCH")
        assert plan.retrieval_profile == "TASK"
        assert len(plan.preferred_module_patterns) > 0

    def test_capability_profile(self):
        """CAPABILITY profile should prefer CLASS symbols."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the capability", "SEARCH")
        assert plan.retrieval_profile == "CAPABILITY"
        assert plan.preferred_symbol_types == ("CLASS",)

    def test_provider_profile(self):
        """PROVIDER profile should prefer CLASS symbols."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the database provider", "SEARCH")
        assert plan.retrieval_profile == "PROVIDER"
        assert plan.preferred_symbol_types == ("CLASS",)

    def test_validation_profile(self):
        """VALIDATION profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the validation logic", "SEARCH")
        assert plan.retrieval_profile == "VALIDATION"
        assert len(plan.preferred_module_patterns) > 0

    def test_factory_profile(self):
        """FACTORY profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the factory pattern", "SEARCH")
        assert plan.retrieval_profile == "FACTORY"
        assert len(plan.preferred_module_patterns) > 0

    def test_extension_profile(self):
        """EXTENSION profile should have module patterns."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find the extension point", "SEARCH")
        assert plan.retrieval_profile == "EXTENSION"
        assert len(plan.preferred_module_patterns) > 0

    def test_architecture_profile(self):
        """ARCHITECTURE profile should have relationship preferences."""
        engine = IntentRuleEngine()
        plan = engine.resolve("why is the architecture designed this way", "EXPLAIN")
        assert plan.retrieval_profile == "ARCHITECTURE"
        assert "DEFINES" in plan.relationship_preferences
        assert "CALLS" in plan.relationship_preferences

    def test_similar_profile(self):
        """SIMILAR profile should have correct hints."""
        engine = IntentRuleEngine()
        plan = engine.resolve("find similar example", "SEARCH")
        assert plan.retrieval_profile == "SIMILAR"
        assert "CLASS" in plan.preferred_symbol_types
        assert "FUNCTION" in plan.preferred_symbol_types

    def test_default_profile(self):
        """DEFAULT profile should have no hints."""
        engine = IntentRuleEngine()
        plan = engine.resolve("hello world", "SEARCH")
        assert plan.retrieval_profile == "DEFAULT"
        assert plan.preferred_symbol_types == ()
        assert plan.preferred_module_patterns == ()
        assert plan.relationship_preferences == ()