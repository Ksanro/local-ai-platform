"""Tests for WorkflowEvaluator.

Verifies:
- Input validation
- Metric computation
- Score calculation
- Report structure
- Edge cases
- Coverage >95%
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from packages.evaluation.evaluator import WorkflowEvaluator
from packages.evaluation.models import EvaluationReport


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _make_workflow_plan(**overrides: str) -> MagicMock:
    """Create a mock WorkflowPlan."""
    plan = MagicMock()
    plan.workflow_name = overrides.get("workflow_name", "bug-investigation")
    plan.task_plans = ()
    plan.metrics = MagicMock()
    plan.metrics.estimated_tokens = 1000
    return plan


def _make_execution_report(**overrides: object) -> MagicMock:
    """Create a mock ExecutionReport."""
    report = MagicMock()
    report.workflow_name = overrides.get("workflow_name", "bug-investigation")
    report.execution_status = "completed"
    report.total_duration_ms = overrides.get("total_duration_ms", 5000)
    report.step_results = overrides.get(
        "step_results",
        (
            {"duration_ms": 1000},
            {"duration_ms": 2000},
            {"duration_ms": 2000},
        ),
    )
    report.success = overrides.get("success", True)
    report.failures = overrides.get("failures", ())
    return report


def _make_capability_result(**overrides: object) -> MagicMock:
    """Create a mock CapabilityResult."""
    result = MagicMock()
    result.selected_symbols = overrides.get(
        "selected_symbols",
        ("pkg.module.func", "pkg.module.Class"),
    )
    result.selected_modules = overrides.get(
        "selected_modules",
        ("pkg/module.py", "pkg/other.py"),
    )
    result.estimated_tokens = overrides.get("estimated_tokens", 1000)
    result.investigation_report = overrides.get(
        "investigation_report",
        {"diagnostics": {}, "architecture": {}},
    )
    return result


def _make_task_plan(**overrides: str) -> MagicMock:
    """Create a mock TaskPlan."""
    plan = MagicMock()
    plan.task_name = overrides.get("task_name", "investigate-bug")
    plan.constraints = ()
    return plan


def _make_provider_response(**overrides: int | str) -> dict:
    """Create a mock provider response."""
    return {
        "completion_tokens": overrides.get("completion_tokens", 500),
        "prompt_tokens": overrides.get("prompt_tokens", 1000),
        "provider": overrides.get("provider", "vllm"),
        "model": overrides.get("model", "gpt-4"),
    }


# ---------------------------------------------------------------------------
# Test: Evaluate Method — Basic
# ---------------------------------------------------------------------------


class TestEvaluateBasic:
    """Tests for basic evaluate functionality."""

    def test_evaluate_returns_report(self) -> None:
        """Evaluate should return an EvaluationReport."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert isinstance(report, EvaluationReport)

    def test_evaluate_with_all_inputs(self) -> None:
        """Evaluate should handle all inputs."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        task_plan = _make_task_plan()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            task_plan=task_plan,
            provider_response=provider_response,
        )

        assert isinstance(report, EvaluationReport)
        assert report.workflow_name == "bug-investigation"
        assert report.task_name == "investigate-bug"
        assert report.provider == "vllm"
        assert report.model == "gpt-4"

    def test_report_has_metrics(self) -> None:
        """Report should have computed metrics."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        assert len(report.metrics) > 0

    def test_report_has_scores(self) -> None:
        """Report should have computed scores."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        assert len(report.scores) > 0

    def test_report_has_overall_score(self) -> None:
        """Report should have overall score."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        assert report.overall_score >= 0.0
        assert report.overall_score <= 1.0

    def test_report_has_summary(self) -> None:
        """Report should have summary."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        assert report.summary != ""

    def test_report_timestamps(self) -> None:
        """Report should have timestamps."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert report.started_at != ""
        assert report.completed_at != ""


# ---------------------------------------------------------------------------
# Test: Evaluate Method — Edge Cases
# ---------------------------------------------------------------------------


class TestEvaluateEdgeCases:
    """Tests for edge cases in evaluate."""

    def test_no_capability_result(self) -> None:
        """Evaluate should work without capability result."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert isinstance(report, EvaluationReport)

    def test_no_task_plan(self) -> None:
        """Evaluate should work without task plan."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            task_plan=None,
        )

        assert report.task_name == "unknown"

    def test_no_provider_response(self) -> None:
        """Evaluate should work without provider response."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            provider_response=None,
        )

        assert report.provider == "unknown"
        assert report.model == "unknown"

    def test_failed_execution(self) -> None:
        """Evaluate should handle failed execution."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report(success=False)
        execution_report.failures = ("step1",)

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert "FAILED" in report.summary

    def test_empty_step_results(self) -> None:
        """Evaluate should handle empty step results."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report(step_results=())

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert isinstance(report, EvaluationReport)

    def test_custom_workflow_name(self) -> None:
        """Evaluate should use custom workflow name."""
        workflow_plan = _make_workflow_plan(workflow_name="architecture-review")
        execution_report = _make_execution_report(
            workflow_name="architecture-review"
        )

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert report.workflow_name == "architecture-review"

    def test_custom_task_name(self) -> None:
        """Evaluate should use custom task name."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        task_plan = _make_task_plan(task_name="implement-feature")

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            task_plan=task_plan,
        )

        assert report.task_name == "implement-feature"


# ---------------------------------------------------------------------------
# Test: Metric Computation
# ---------------------------------------------------------------------------


class TestMetricComputation:
    """Tests for metric computation."""

    def test_context_metrics_computed(self) -> None:
        """Context metrics should be computed."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        metric_names = [m.name for m in report.metrics]
        assert "selected_symbols_count" in metric_names
        assert "selected_modules_count" in metric_names

    def test_execution_metrics_computed(self) -> None:
        """Execution metrics should be computed."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            provider_response=provider_response,
        )

        metric_names = [m.name for m in report.metrics]
        assert "execution_duration_ms" in metric_names
        assert "total_tokens" in metric_names

    def test_engineering_metrics_computed(self) -> None:
        """Engineering metrics should be computed."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
        )

        metric_names = [m.name for m in report.metrics]
        assert "workflow_completeness" in metric_names

    def test_determinism_metrics_placeholder(self) -> None:
        """Determinism metrics should have placeholder values."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        metric_names = [m.name for m in report.metrics]
        assert "execution_consistency" in metric_names
        assert "identifier_stability" in metric_names

        for m in report.metrics:
            if m.name == "execution_consistency":
                assert m.value == 1.0
            if m.name == "identifier_stability":
                assert m.value == 1.0


# ---------------------------------------------------------------------------
# Test: Score Computation
# ---------------------------------------------------------------------------


class TestScoreComputation:
    """Tests for score computation."""

    def test_all_categories_scored(self) -> None:
        """All categories should be scored."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        score_categories = {s.category for s in report.scores}
        assert "Context Quality" in score_categories
        assert "Execution Quality" in score_categories
        assert "Engineering Quality" in score_categories
        assert "Performance" in score_categories
        assert "Determinism" in score_categories

    def test_scores_in_valid_range(self) -> None:
        """All scores should be in [0.0, 1.0]."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        for score in report.scores:
            assert 0.0 <= score.score <= 1.0

    def test_overall_score_in_valid_range(self) -> None:
        """Overall score should be in [0.0, 1.0]."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        assert 0.0 <= report.overall_score <= 1.0


# ---------------------------------------------------------------------------
# Test: Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    """Tests for report immutability."""

    def test_report_is_frozen(self) -> None:
        """Report should be immutable."""
        from dataclasses import FrozenInstanceError

        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        with pytest.raises(FrozenInstanceError):
            report.workflow_name = "modified"  # type: ignore[misc]

    def test_metrics_are_tuples(self) -> None:
        """Metrics should be tuples."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert isinstance(report.metrics, tuple)
        assert isinstance(report.scores, tuple)


# ---------------------------------------------------------------------------
# Test: Summary Generation
# ---------------------------------------------------------------------------


class TestSummaryGeneration:
    """Tests for summary generation."""

    def test_summary_contains_workflow_name(self) -> None:
        """Summary should contain workflow name."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert "bug-investigation" in report.summary

    def test_summary_contains_overall_score(self) -> None:
        """Summary should contain overall score."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert "Overall Score:" in report.summary

    def test_summary_contains_status(self) -> None:
        """Summary should contain status."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert "PASSED" in report.summary

    def test_summary_contains_failed_status(self) -> None:
        """Summary should contain FAILED status for failed execution."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report(success=False)

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
        )

        assert "FAILED" in report.summary

    def test_summary_contains_category_scores(self) -> None:
        """Summary should contain category scores."""
        workflow_plan = _make_workflow_plan()
        execution_report = _make_execution_report()
        capability_result = _make_capability_result()
        provider_response = _make_provider_response()

        report = WorkflowEvaluator.evaluate(
            workflow_plan=workflow_plan,
            execution_report=execution_report,
            capability_result=capability_result,
            provider_response=provider_response,
        )

        for score in report.scores:
            assert score.category in report.summary