"""Tests for deterministic metric computation.

Verifies:
- Deterministic output
- Edge cases (zero, negative, empty)
- All metric functions
- Coverage >95%
"""

from __future__ import annotations

import pytest

from packages.evaluation.metrics import (
    compute_architecture_findings_count,
    compute_context_compression_ratio,
    compute_context_utilization,
    compute_diagnostics_collected,
    compute_execution_consistency,
    compute_execution_duration_ms,
    compute_identifier_stability,
    compute_selected_modules_count,
    compute_selected_relationships_count,
    compute_selected_symbols_count,
    compute_throughput,
    compute_total_tokens,
    compute_workflow_completeness,
)


# ---------------------------------------------------------------------------
# Test: Context Quality Metrics
# ---------------------------------------------------------------------------


class TestContextQualityMetrics:
    """Tests for context quality metric functions."""

    def test_compute_selected_symbols_count_empty(self) -> None:
        """Empty symbols should return 0.0."""
        result = compute_selected_symbols_count(())
        assert result == 0.0

    def test_compute_selected_symbols_count_single(self) -> None:
        """Single symbol should return 1.0."""
        result = compute_selected_symbols_count(("foo",))
        assert result == 1.0

    def test_compute_selected_symbols_count_multiple(self) -> None:
        """Multiple symbols should return correct count."""
        result = compute_selected_symbols_count(("a", "b", "c"))
        assert result == 3.0

    def test_compute_selected_modules_count_empty(self) -> None:
        """Empty modules should return 0.0."""
        result = compute_selected_modules_count(())
        assert result == 0.0

    def test_compute_selected_modules_count_single(self) -> None:
        """Single module should return 1.0."""
        result = compute_selected_modules_count(("pkg.py",))
        assert result == 1.0

    def test_compute_selected_modules_count_multiple(self) -> None:
        """Multiple modules should return correct count."""
        result = compute_selected_modules_count(("a.py", "b.py", "c.py", "d.py"))
        assert result == 4.0

    def test_compute_selected_relationships_count_empty(self) -> None:
        """Empty relationships should return 0.0."""
        result = compute_selected_relationships_count(())
        assert result == 0.0

    def test_compute_selected_relationships_count_single(self) -> None:
        """Single relationship should return 1.0."""
        rel: tuple[tuple[str, str, str], ...] = (("a", "b", "CALLS"),)
        result = compute_selected_relationships_count(rel)
        assert result == 1.0

    def test_compute_selected_relationships_count_multiple(self) -> None:
        """Multiple relationships should return correct count."""
        rels: tuple[tuple[str, str, str], ...] = (
            ("a", "b", "CALLS"),
            ("b", "c", "DEPENDS_ON"),
            ("c", "a", "RELATED_TO"),
        )
        result = compute_selected_relationships_count(rels)
        assert result == 3.0

    def test_compute_context_compression_ratio_equal(self) -> None:
        """Equal tokens should return 1.0."""
        result = compute_context_compression_ratio(1000, 1000)
        assert result == 1.0

    def test_compute_context_compression_ratio_under(self) -> None:
        """Under-estimation should be clamped to 1.0."""
        result = compute_context_compression_ratio(1000, 1500)
        assert result == 1.0

    def test_compute_context_compression_ratio_over(self) -> None:
        """Over-estimation should return ratio < 1.0."""
        result = compute_context_compression_ratio(1500, 1000)
        assert result == 1000 / 1500

    def test_compute_context_compression_ratio_zero_estimated(self) -> None:
        """Zero estimated tokens should return 1.0."""
        result = compute_context_compression_ratio(0, 1000)
        assert result == 1.0

    def test_compute_context_compression_ratio_both_zero(self) -> None:
        """Both zero should return 1.0."""
        result = compute_context_compression_ratio(0, 0)
        assert result == 1.0

    def test_compute_context_utilization_equal(self) -> None:
        """Equal tokens should return 1.0."""
        result = compute_context_utilization(1000, 1000)
        assert result == 1.0

    def test_compute_context_utilization_under(self) -> None:
        """Under-estimation should return > 1.0."""
        result = compute_context_utilization(1000, 1500)
        assert result == 1.5

    def test_compute_context_utilization_over(self) -> None:
        """Over-estimation should return ratio < 1.0."""
        result = compute_context_utilization(1500, 1000)
        assert result == 1000 / 1500

    def test_compute_context_utilization_zero_estimated(self) -> None:
        """Zero estimated tokens should return 0.0."""
        result = compute_context_utilization(0, 1000)
        assert result == 0.0

    def test_compute_context_utilization_both_zero(self) -> None:
        """Both zero should return 0.0."""
        result = compute_context_utilization(0, 0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Test: Execution Quality Metrics
# ---------------------------------------------------------------------------


class TestExecutionQualityMetrics:
    """Tests for execution quality metric functions."""

    def test_compute_execution_duration_ms_empty(self) -> None:
        """Empty step results should return 0.0."""
        result = compute_execution_duration_ms(())
        assert result == 0.0

    def test_compute_execution_duration_ms_single(self) -> None:
        """Single step result should return its duration."""
        steps = ({"duration_ms": 500},)
        result = compute_execution_duration_ms(steps)
        assert result == 500.0

    def test_compute_execution_duration_ms_multiple(self) -> None:
        """Multiple step results should sum durations."""
        steps = (
            {"duration_ms": 100},
            {"duration_ms": 200},
            {"duration_ms": 300},
        )
        result = compute_execution_duration_ms(steps)
        assert result == 600.0

    def test_compute_execution_duration_ms_missing_key(self) -> None:
        """Missing duration_ms key should default to 0."""
        steps = (
            {"duration_ms": 100},
            {"other_key": 200},
        )
        result = compute_execution_duration_ms(steps)
        assert result == 100.0

    def test_compute_total_tokens(self) -> None:
        """Total tokens should be sum of completion and prompt."""
        result = compute_total_tokens(500, 1500)
        assert result == 2000.0

    def test_compute_total_tokens_zero_completion(self) -> None:
        """Zero completion tokens should still count prompt."""
        result = compute_total_tokens(0, 1000)
        assert result == 1000.0

    def test_compute_total_tokens_zero_prompt(self) -> None:
        """Zero prompt tokens should still count completion."""
        result = compute_total_tokens(1000, 0)
        assert result == 1000.0

    def test_compute_total_tokens_both_zero(self) -> None:
        """Both zero should return 0.0."""
        result = compute_total_tokens(0, 0)
        assert result == 0.0

    def test_compute_throughput(self) -> None:
        """Throughput should be tokens per second."""
        # 1000 tokens in 2000ms = 0.5 seconds => 2000 tokens/sec
        result = compute_throughput(1000, 2000)
        assert result == 500.0

    def test_compute_throughput_zero_duration(self) -> None:
        """Zero duration should return 0.0."""
        result = compute_throughput(1000, 0)
        assert result == 0.0

    def test_compute_throughput_zero_tokens(self) -> None:
        """Zero tokens should return 0.0."""
        result = compute_throughput(0, 1000)
        assert result == 0.0


# ---------------------------------------------------------------------------
# Test: Engineering Quality Metrics
# ---------------------------------------------------------------------------


class TestEngineeringQualityMetrics:
    """Tests for engineering quality metric functions."""

    def test_compute_diagnostics_collected_none(self) -> None:
        """None input should return 0.0."""
        result = compute_diagnostics_collected(None)
        assert result == 0.0

    def test_compute_diagnostics_collected_empty(self) -> None:
        """Empty dict should return 0.0."""
        result = compute_diagnostics_collected({})
        assert result == 0.0

    def test_compute_diagnostics_collected_single(self) -> None:
        """Single key should return 1.0."""
        result = compute_diagnostics_collected({"diagnostics": {}})
        assert result == 1.0

    def test_compute_diagnostics_collected_multiple(self) -> None:
        """Multiple keys should return correct count."""
        data = {
            "symbols": {},
            "modules": {},
            "relationships": {},
        }
        result = compute_diagnostics_collected(data)
        assert result == 3.0

    def test_compute_architecture_findings_count_none(self) -> None:
        """None input should return 0.0."""
        result = compute_architecture_findings_count(None)
        assert result == 0.0

    def test_compute_architecture_findings_count_empty(self) -> None:
        """Empty dict should return 0.0."""
        result = compute_architecture_findings_count({})
        assert result == 0.0

    def test_compute_architecture_findings_count_single(self) -> None:
        """Single key should return 1.0."""
        result = compute_architecture_findings_count({"findings": {}})
        assert result == 1.0

    def test_compute_architecture_findings_count_multiple(self) -> None:
        """Multiple keys should return correct count."""
        data = {
            "patterns": {},
            "smells": {},
            "recommendations": {},
        }
        result = compute_architecture_findings_count(data)
        assert result == 3.0

    def test_compute_workflow_completeness_full(self) -> None:
        """All steps executed should return 1.0."""
        result = compute_workflow_completeness(5, 5)
        assert result == 1.0

    def test_compute_workflow_completeness_partial(self) -> None:
        """Partial execution should return ratio."""
        result = compute_workflow_completeness(3, 5)
        assert result == 0.6

    def test_compute_workflow_completeness_zero_expected(self) -> None:
        """Zero expected steps should return 1.0."""
        result = compute_workflow_completeness(0, 0)
        assert result == 1.0

    def test_compute_workflow_completeness_zero_executed(self) -> None:
        """Zero executed steps should return 0.0."""
        result = compute_workflow_completeness(0, 5)
        assert result == 0.0

    def test_compute_workflow_completeness_over_executed(self) -> None:
        """Over-execution should be clamped to 1.0."""
        result = compute_workflow_completeness(10, 5)
        assert result == 1.0


# ---------------------------------------------------------------------------
# Test: Determinism Metrics
# ---------------------------------------------------------------------------


class TestDeterminismMetrics:
    """Tests for determinism metric functions."""

    def test_compute_execution_consistency_single_execution(self) -> None:
        """Single execution should return 1.0."""
        result = compute_execution_consistency((("a", "b"),))
        assert result == 1.0

    def test_compute_execution_consistency_all_match(self) -> None:
        """All matching executions should return 1.0."""
        outputs = (
            ("a", "b"),
            ("a", "b"),
            ("a", "b"),
        )
        result = compute_execution_consistency(outputs)
        assert result == 1.0

    def test_compute_execution_consistency_all_different(self) -> None:
        """All different executions should return 0.0."""
        outputs = (
            ("a", "b"),
            ("c", "d"),
            ("e", "f"),
        )
        result = compute_execution_consistency(outputs)
        assert result == 0.0

    def test_compute_execution_consistency_partial_match(self) -> None:
        """Partial matching should return correct ratio."""
        outputs = (
            ("a", "b"),
            ("a", "b"),
            ("c", "d"),
        )
        result = compute_execution_consistency(outputs)
        assert result == 0.5  # 1 match out of 2 comparisons = 0.5

    def test_compute_execution_consistency_empty(self) -> None:
        """Empty tuple should return 1.0."""
        result = compute_execution_consistency(())
        assert result == 1.0

    def test_compute_identifier_stability_single_execution(self) -> None:
        """Single execution should return 1.0."""
        result = compute_identifier_stability((("id1",),))
        assert result == 1.0

    def test_compute_identifier_stability_all_match(self) -> None:
        """All matching should return 1.0."""
        ids = (
            ("id1", "id2"),
            ("id1", "id2"),
            ("id1", "id2"),
        )
        result = compute_identifier_stability(ids)
        assert result == 1.0

    def test_compute_identifier_stability_all_different(self) -> None:
        """All different should return 0.0."""
        ids = (
            ("id1",),
            ("id2",),
            ("id3",),
        )
        result = compute_identifier_stability(ids)
        assert result == 0.0

    def test_compute_identifier_stability_empty(self) -> None:
        """Empty tuple should return 1.0."""
        result = compute_identifier_stability(())
        assert result == 1.0


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_compression_ratio(self) -> None:
        """Same inputs should produce same output."""
        r1 = compute_context_compression_ratio(1000, 800)
        r2 = compute_context_compression_ratio(1000, 800)
        assert r1 == r2

    def test_deterministic_throughput(self) -> None:
        """Same inputs should produce same output."""
        r1 = compute_throughput(1000, 2000)
        r2 = compute_throughput(1000, 2000)
        assert r1 == r2

    def test_deterministic_completeness(self) -> None:
        """Same inputs should produce same output."""
        r1 = compute_workflow_completeness(3, 5)
        r2 = compute_workflow_completeness(3, 5)
        assert r1 == r2