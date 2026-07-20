"""Tests for evaluation models.

Verifies:
- Immutability (frozen=True, slots=True)
- Default values
- Construction with all fields
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from packages.evaluation.models import (
    EvaluationMetric,
    EvaluationReport,
    EvaluationScore,
)


# ---------------------------------------------------------------------------
# Test: EvaluationMetric Immutability
# ---------------------------------------------------------------------------


class TestEvaluationMetricImmutability:
    """Tests for EvaluationMetric immutability."""

    def test_model_is_frozen(self) -> None:
        """EvaluationMetric should be immutable."""
        metric = EvaluationMetric(
            name="test_metric",
            value=1.0,
            weight=0.5,
            passed=True,
        )
        with pytest.raises(FrozenInstanceError):
            metric.name = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """EvaluationMetric should use slots."""
        metric = EvaluationMetric(
            name="test_metric",
            value=1.0,
            weight=0.5,
            passed=True,
        )
        # slots=True means no __dict__ for attribute storage
        assert not hasattr(metric, "__dict__")

    def test_model_cannot_add_arbitrary_attributes(self) -> None:
        """EvaluationMetric should not allow arbitrary attribute addition."""
        metric = EvaluationMetric(
            name="test_metric",
            value=1.0,
            weight=0.5,
            passed=True,
        )
        with pytest.raises(FrozenInstanceError):
            metric.extra_field = "extra"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: EvaluationMetric Construction
# ---------------------------------------------------------------------------


class TestEvaluationMetricConstruction:
    """Tests for EvaluationMetric construction."""

    def test_minimal_construction(self) -> None:
        """EvaluationMetric should accept required fields only."""
        metric = EvaluationMetric(
            name="test_metric",
            value=0.5,
            weight=1.0,
            passed=False,
        )
        assert metric.name == "test_metric"
        assert metric.value == 0.5
        assert metric.weight == 1.0
        assert metric.passed is False
        assert metric.metadata == {}

    def test_full_construction(self) -> None:
        """EvaluationMetric should accept all fields."""
        metric = EvaluationMetric(
            name="context_compression",
            value=0.85,
            weight=0.50,
            passed=True,
            metadata={
                "description": "Compression ratio",
                "estimated": 1000,
                "actual": 850,
            },
        )
        assert metric.name == "context_compression"
        assert metric.value == 0.85
        assert metric.weight == 0.50
        assert metric.passed is True
        assert metric.metadata["description"] == "Compression ratio"
        assert metric.metadata["estimated"] == 1000
        assert metric.metadata["actual"] == 850

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """metadata should default to empty dict."""
        metric = EvaluationMetric(
            name="test",
            value=0.0,
            weight=1.0,
            passed=True,
        )
        assert metric.metadata == {}
        assert isinstance(metric.metadata, dict)

    def test_metadata_is_independent(self) -> None:
        """Each metric should have independent metadata."""
        m1 = EvaluationMetric(
            name="m1",
            value=1.0,
            weight=1.0,
            passed=True,
            metadata={"key": "value1"},
        )
        m2 = EvaluationMetric(
            name="m2",
            value=2.0,
            weight=1.0,
            passed=False,
            metadata={"key": "value2"},
        )
        assert m1.metadata is not m2.metadata
        assert m1.metadata["key"] == "value1"
        assert m2.metadata["key"] == "value2"


# ---------------------------------------------------------------------------
# Test: EvaluationScore Immutability
# ---------------------------------------------------------------------------


class TestEvaluationScoreImmutability:
    """Tests for EvaluationScore immutability."""

    def test_model_is_frozen(self) -> None:
        """EvaluationScore should be immutable."""
        score = EvaluationScore(
            category="Context Quality",
            score=0.85,
            maximum=1.0,
            weight=0.25,
        )
        with pytest.raises(FrozenInstanceError):
            score.category = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """EvaluationScore should use slots."""
        score = EvaluationScore(
            category="Context Quality",
            score=0.85,
            maximum=1.0,
            weight=0.25,
        )
        assert not hasattr(score, "__dict__")


# ---------------------------------------------------------------------------
# Test: EvaluationScore Construction
# ---------------------------------------------------------------------------


class TestEvaluationScoreConstruction:
    """Tests for EvaluationScore construction."""

    def test_minimal_construction(self) -> None:
        """EvaluationScore should accept all required fields."""
        score = EvaluationScore(
            category="Context Quality",
            score=0.85,
            maximum=1.0,
            weight=0.25,
        )
        assert score.category == "Context Quality"
        assert score.score == 0.85
        assert score.maximum == 1.0
        assert score.weight == 0.25

    def test_zero_score(self) -> None:
        """EvaluationScore should handle zero score."""
        score = EvaluationScore(
            category="Performance",
            score=0.0,
            maximum=1.0,
            weight=0.10,
        )
        assert score.score == 0.0

    def test_maximum_one(self) -> None:
        """EvaluationScore should handle maximum=1.0."""
        score = EvaluationScore(
            category="Determinism",
            score=1.0,
            maximum=1.0,
            weight=0.15,
        )
        assert score.score == 1.0
        assert score.maximum == 1.0

    def test_non_standard_maximum(self) -> None:
        """EvaluationScore should handle non-standard maximum."""
        score = EvaluationScore(
            category="Custom",
            score=5.0,
            maximum=10.0,
            weight=0.50,
        )
        assert score.maximum == 10.0


# ---------------------------------------------------------------------------
# Test: EvaluationReport Immutability
# ---------------------------------------------------------------------------


class TestEvaluationReportImmutability:
    """Tests for EvaluationReport immutability."""

    def test_model_is_frozen(self) -> None:
        """EvaluationReport should be immutable."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test-task",
            provider="vllm",
            model="gpt-4",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        with pytest.raises(FrozenInstanceError):
            report.workflow_name = "modified"  # type: ignore[misc]

    def test_model_has_slots(self) -> None:
        """EvaluationReport should use slots."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test-task",
            provider="vllm",
            model="gpt-4",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert not hasattr(report, "__dict__")


# ---------------------------------------------------------------------------
# Test: EvaluationReport Construction
# ---------------------------------------------------------------------------


class TestEvaluationReportConstruction:
    """Tests for EvaluationReport construction."""

    def test_minimal_construction(self) -> None:
        """EvaluationReport should accept required fields."""
        report = EvaluationReport(
            workflow_name="bug-investigation",
            task_name="investigate-bug",
            provider="vllm",
            model="gpt-4",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.workflow_name == "bug-investigation"
        assert report.task_name == "investigate-bug"
        assert report.provider == "vllm"
        assert report.model == "gpt-4"
        assert report.started_at == "2024-01-01T00:00:00"
        assert report.completed_at == "2024-01-01T00:01:00"
        assert report.metrics == ()
        assert report.scores == ()
        assert report.overall_score == 0.0
        assert report.summary == ""
        assert report.metadata == {}

    def test_full_construction(self) -> None:
        """EvaluationReport should accept all fields."""
        metric = EvaluationMetric(
            name="test_metric",
            value=0.85,
            weight=0.5,
            passed=True,
        )
        score = EvaluationScore(
            category="Context Quality",
            score=0.85,
            maximum=1.0,
            weight=0.25,
        )
        report = EvaluationReport(
            workflow_name="bug-investigation",
            task_name="investigate-bug",
            provider="vllm",
            model="gpt-4",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            metrics=(metric,),
            scores=(score,),
            overall_score=0.85,
            summary="Good quality execution.",
            metadata={"reviewer": "system"},
        )
        assert len(report.metrics) == 1
        assert len(report.scores) == 1
        assert report.overall_score == 0.85
        assert report.summary == "Good quality execution."
        assert report.metadata == {"reviewer": "system"}

    def test_empty_metrics_tuple(self) -> None:
        """metrics should default to empty tuple."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.metrics == ()
        assert isinstance(report.metrics, tuple)

    def test_empty_scores_tuple(self) -> None:
        """scores should default to empty tuple."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.scores == ()
        assert isinstance(report.scores, tuple)

    def test_overall_score_defaults_to_zero(self) -> None:
        """overall_score should default to 0.0."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.overall_score == 0.0

    def test_summary_defaults_to_empty(self) -> None:
        """summary should default to empty string."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.summary == ""

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """metadata should default to empty dict."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert report.metadata == {}
        assert isinstance(report.metadata, dict)


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_metric(self) -> None:
        """Same inputs should produce identical metrics."""
        m1 = EvaluationMetric(
            name="test",
            value=0.5,
            weight=1.0,
            passed=True,
        )
        m2 = EvaluationMetric(
            name="test",
            value=0.5,
            weight=1.0,
            passed=True,
        )
        assert m1.name == m2.name
        assert m1.value == m2.value
        assert m1.weight == m2.weight
        assert m1.passed == m2.passed

    def test_deterministic_report(self) -> None:
        """Same inputs should produce identical reports."""
        r1 = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        r2 = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
        )
        assert r1.workflow_name == r2.workflow_name
        assert r1.task_name == r2.task_name
        assert r1.provider == r2.provider
        assert r1.model == r2.model


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_name(self) -> None:
        """EvaluationMetric should handle empty name."""
        metric = EvaluationMetric(
            name="",
            value=0.0,
            weight=0.0,
            passed=False,
        )
        assert metric.name == ""

    def test_negative_value(self) -> None:
        """EvaluationMetric should handle negative values."""
        metric = EvaluationMetric(
            name="negative",
            value=-1.0,
            weight=1.0,
            passed=False,
        )
        assert metric.value == -1.0

    def test_large_value(self) -> None:
        """EvaluationMetric should handle large values."""
        metric = EvaluationMetric(
            name="large",
            value=1e18,
            weight=1.0,
            passed=True,
        )
        assert metric.value == 1e18

    def test_zero_weight(self) -> None:
        """EvaluationMetric should handle zero weight."""
        metric = EvaluationMetric(
            name="zero_weight",
            value=0.5,
            weight=0.0,
            passed=True,
        )
        assert metric.weight == 0.0

    def test_unicode_name(self) -> None:
        """EvaluationMetric should handle unicode in name."""
        metric = EvaluationMetric(
            name="metric_\u4f60\u597d",
            value=0.5,
            weight=1.0,
            passed=True,
        )
        assert metric.name == "metric_\u4f60\u597d"

    def test_unicode_summary(self) -> None:
        """EvaluationReport should handle unicode in summary."""
        report = EvaluationReport(
            workflow_name="test",
            task_name="test",
            provider="test",
            model="test",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            summary="Quality: \u4f60\u597d",
        )
        assert report.summary == "Quality: \u4f60\u597d"