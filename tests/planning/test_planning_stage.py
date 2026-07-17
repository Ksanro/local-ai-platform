"""Tests for PlanningStage pipeline stage.

Tests the before/execute/after hooks and message extraction.
"""

from __future__ import annotations

import asyncio

from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.planning.plan import ContextPlan
from packages.planning.planner import ContextPlanner
from packages.planning.rules import PlanningRule, RuleEngine


class TestPlanningStageName:
    """Test PlanningStage.name property."""

    def test_stage_name(self):
        """Stage name is 'planning'."""
        stage = PlanningStage()
        assert stage.name == "planning"


class TestPlanningStageBefore:
    """Test PlanningStage.before hook."""

    def test_before_enabled_by_default(self):
        """Planning is enabled by default."""
        stage = PlanningStage()
        context = PipelineContext()
        result = asyncio.run(stage.before(context))

        # Returns None to proceed with execute()
        assert result is None

    def test_before_disabled(self):
        """Planning can be disabled via metadata."""
        stage = PlanningStage()
        context = PipelineContext()
        context.set_metadata("planning_enabled", False)
        result = asyncio.run(stage.before(context))

        assert result is not None
        assert result.success is True
        assert result.data == {"planning_enabled": False}

    def test_before_short_circuits(self):
        """When disabled, before() returns no-op result."""
        stage = PlanningStage()
        context = PipelineContext()
        context.set_metadata("planning_enabled", False)
        result = asyncio.run(stage.before(context))

        assert isinstance(result, PipelineStageResult)
        assert result.stage_name == "planning"


class TestPlanningStageExecute:
    """Test PlanningStage.execute hook."""

    def test_execute_with_user_messages(self):
        """Execute processes user messages correctly."""
        stage = PlanningStage()
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "Explain how ProviderFactory works"},
                    {"role": "assistant", "content": "Sure!"},
                    {"role": "user", "content": "What does it do?"},
                ]
            }
        )

        result = asyncio.run(stage.execute(context))

        assert result.success is True
        assert result.data is not None
        plan = result.data
        assert isinstance(plan, ContextPlan)
        assert plan.intent == "EXPLAIN"
        # Verify plan is stored in metadata
        stored_plan = context.get_metadata("context_plan")
        assert stored_plan is plan

    def test_execute_with_empty_messages(self):
        """Execute handles empty messages gracefully."""
        stage = PlanningStage()
        context = PipelineContext(request={"messages": []})

        result = asyncio.run(stage.execute(context))

        assert result.success is True
        assert result.data is not None
        plan = result.data
        assert isinstance(plan, ContextPlan)
        assert plan.intent == "DEFAULT"

    def test_execute_with_no_messages_in_request(self):
        """Execute handles missing messages field gracefully."""
        stage = PlanningStage()
        context = PipelineContext(request={})

        result = asyncio.run(stage.execute(context))

        assert result.success is True
        plan = result.data
        assert isinstance(plan, ContextPlan)
        assert plan.intent == "DEFAULT"

    def test_execute_with_non_dict_request(self):
        """Execute handles non-dict request gracefully."""
        stage = PlanningStage()
        context = PipelineContext(request="not a dict")  # type: ignore[arg-type]

        result = asyncio.run(stage.execute(context))

        assert result.success is True
        plan = result.data
        assert isinstance(plan, ContextPlan)
        assert plan.intent == "DEFAULT"

    def test_execute_stores_plan_in_metadata(self):
        """Execute stores ContextPlan in metadata."""
        stage = PlanningStage()
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "Fix the bug"},
                ]
            }
        )

        asyncio.run(stage.execute(context))

        plan = context.get_metadata("context_plan")
        assert plan is not None
        assert plan.intent == "DEBUG"

    def test_execute_with_custom_planner(self):
        """Execute uses custom planner when provided."""
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
        stage = PlanningStage(planner=planner)

        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "Explain this"},
                ]
            }
        )

        result = asyncio.run(stage.execute(context))

        assert result.success is True
        plan = result.data
        assert plan.ranking_profile == "CUSTOM_EXPLAIN"


class TestPlanningStageAfter:
    """Test PlanningStage.after hook."""

    def test_after_success(self):
        """After hook handles success result."""
        stage = PlanningStage()
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "Explain this"},
                ]
            }
        )
        result = asyncio.run(stage.execute(context))

        after_result = asyncio.run(stage.after(context, result))

        # Returns None to keep existing result
        assert after_result is None

    def test_after_with_no_plan(self):
        """After hook handles missing plan gracefully."""
        stage = PlanningStage()
        context = PipelineContext(request={})
        # Don't set a plan in metadata
        result = PipelineStageResult(
            stage_name="planning",
            success=True,
            data=None,
        )

        after_result = asyncio.run(stage.after(context, result))

        assert after_result is None


class TestMessageExtraction:
    """Test _extract_messages static method."""

    def test_extract_user_messages(self):
        """Only user messages are extracted."""
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "First message"},
                    {"role": "assistant", "content": "Response"},
                    {"role": "user", "content": "Second message"},
                ]
            }
        )

        messages = PlanningStage._extract_messages(context)

        assert len(messages) == 2
        assert messages[0] == "First message"
        assert messages[1] == "Second message"

    def test_extract_messages_empty(self):
        """Empty messages list returns empty list."""
        context = PipelineContext(request={"messages": []})
        messages = PlanningStage._extract_messages(context)
        assert messages == []

    def test_extract_messages_no_messages_key(self):
        """Missing messages key returns empty list."""
        context = PipelineContext(request={})
        messages = PlanningStage._extract_messages(context)
        assert messages == []

    def test_extract_messages_non_dict_request(self):
        """Non-dict request returns empty list."""
        context = PipelineContext(request="not a dict")  # type: ignore[arg-type]
        messages = PlanningStage._extract_messages(context)
        assert messages == []

    def test_extract_messages_strips_whitespace(self):
        """Message content is stripped."""
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "  Explain this  "},
                ]
            }
        )
        messages = PlanningStage._extract_messages(context)
        assert messages[0] == "Explain this"

    def test_extract_messages_skips_non_user(self):
        """Non-user messages are skipped."""
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "assistant", "content": "Assistant response"},
                    {"role": "system", "content": "System message"},
                ]
            }
        )
        messages = PlanningStage._extract_messages(context)
        assert messages == []

    def test_extract_messages_skips_non_dict_messages(self):
        """Non-dict message entries are skipped."""
        context = PipelineContext(
            request={
                "messages": [
                    "not a dict",
                    123,
                    None,
                ]
            }
        )
        messages = PlanningStage._extract_messages(context)
        assert messages == []


class TestPlanningStageIntegration:
    """Integration tests for PlanningStage."""

    def test_full_pipeline_before_execute_after(self):
        """Full stage lifecycle: before → execute → after."""
        stage = PlanningStage()
        context = PipelineContext(
            request={
                "messages": [
                    {"role": "user", "content": "Refactor the code"},
                ]
            }
        )

        # before: should return None (proceed)
        before_result = asyncio.run(stage.before(context))
        assert before_result is None

        # execute: should produce plan
        execute_result = asyncio.run(stage.execute(context))
        assert execute_result.success is True
        assert execute_result.data.intent == "REFACTOR"

        # after: should return None
        after_result = asyncio.run(stage.after(context, execute_result))
        assert after_result is None

        # Verify plan is in metadata
        plan = context.get_metadata("context_plan")
        assert plan is not None
        assert plan.intent == "REFACTOR"

    def test_disabled_stage_skips_execute(self):
        """When before returns no-op, execute is skipped."""
        stage = PlanningStage()
        context = PipelineContext()
        context.set_metadata("planning_enabled", False)

        before_result = asyncio.run(stage.before(context))
        assert before_result is not None
        assert before_result.success is True

        # before returns a result, so execute() should not be called
        # (this is the pipeline engine's responsibility, but we verify
        # the before result is self-contained)
        assert before_result.data == {"planning_enabled": False}

    def test_all_intents_produce_valid_plans(self):
        """All intent types produce valid ContextPlan."""
        stage = PlanningStage()

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
            context = PipelineContext(
                request={"messages": [{"role": "user", "content": msg} for msg in messages]}
            )
            result = asyncio.run(stage.execute(context))
            assert result.success is True
            plan = result.data
            assert plan.intent == expected_intent, f"Failed for intent: {expected_intent}"

    def test_all_intents_have_estimated_complexity(self):
        """All intent types produce a non-empty estimated_complexity."""
        stage = PlanningStage()

        test_cases = [
            (["Explain this"], "EXPLAIN", "MODERATE"),
            (["Implement feature"], "IMPLEMENT", "MODERATE"),
            (["Refactor code"], "REFACTOR", "COMPLEX"),
            (["Fix bug"], "DEBUG", "COMPLEX"),
            (["Run the test suite"], "TEST", "MODERATE"),
            (["Find symbol"], "SEARCH", "SIMPLE"),
            (["Random"], "DEFAULT", "SIMPLE"),
        ]

        for messages, expected_intent, expected_complexity in test_cases:
            context = PipelineContext(
                request={"messages": [{"role": "user", "content": msg} for msg in messages]}
            )
            result = asyncio.run(stage.execute(context))
            assert result.success is True
            plan = result.data
            assert plan.intent == expected_intent
            assert plan.estimated_complexity == expected_complexity
