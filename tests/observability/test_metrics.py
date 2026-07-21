"""Tests for the metrics module.

Tests metric aggregation, statistics, and convenience functions.
"""

from __future__ import annotations

import pytest

from packages.observability.metrics import (
    MetricAggregator,
    MetricRecord,
    collect_execution_duration,
    collect_provider_latency,
    collect_workflow_duration,
)


class TestMetricRecord:
    """Tests for MetricRecord."""

    def test_basic_creation(self) -> None:
        """Test basic MetricRecord creation."""
        record = MetricRecord(
            name="workflow_duration_ms",
            value=1234.5,
            source="workflow_engine",
        )

        assert record.name == "workflow_duration_ms"
        assert record.value == 1234.5
        assert record.source == "workflow_engine"
        assert record.labels == {}

    def test_with_labels(self) -> None:
        """Test MetricRecord with labels."""
        record = MetricRecord(
            name="provider_latency_ms",
            value=567.8,
            labels={"provider": "vllm", "model": "gpt-4"},
            source="provider",
        )

        assert record.labels["provider"] == "vllm"
        assert record.labels["model"] == "gpt-4"

    def test_immutability(self) -> None:
        """Test that MetricRecord is immutable."""
        record = MetricRecord(name="test", value=1.0)
        assert record.__class__.__dataclass_params__.frozen is True


class TestMetricAggregator:
    """Tests for MetricAggregator."""

    def test_empty_aggregator(self) -> None:
        """Test empty aggregator."""
        agg = MetricAggregator()
        assert agg.count == 0
        assert agg.get_records() == ()

    def test_record_metric(self) -> None:
        """Test recording a metric."""
        agg = MetricAggregator()
        agg.record("duration_ms", 1234.5, source="test")
        assert agg.count == 1

    def test_get_all_records(self) -> None:
        """Test getting all records."""
        agg = MetricAggregator()
        agg.record("metric_a", 1.0)
        agg.record("metric_b", 2.0)
        agg.record("metric_a", 3.0)

        all_records = agg.get_records()
        assert len(all_records) == 3

    def test_get_records_by_name(self) -> None:
        """Test filtering records by name."""
        agg = MetricAggregator()
        agg.record("metric_a", 1.0)
        agg.record("metric_b", 2.0)
        agg.record("metric_a", 3.0)

        records_a = agg.get_records("metric_a")
        assert len(records_a) == 2
        assert all(r.name == "metric_a" for r in records_a)

    def test_get_latest(self) -> None:
        """Test getting the latest record."""
        agg = MetricAggregator()
        agg.record("duration", 100.0)
        agg.record("duration", 200.0)
        agg.record("duration", 300.0)

        latest = agg.get_latest("duration")
        assert latest is not None
        assert latest.value == 300.0

    def test_get_latest_not_found(self) -> None:
        """Test get_latest for non-existent name."""
        agg = MetricAggregator()
        assert agg.get_latest("nonexistent") is None

    def test_get_statistics_empty(self) -> None:
        """Test statistics for non-existent metric."""
        agg = MetricAggregator()
        stats = agg.get_statistics("nonexistent")

        assert stats["count"] == 0
        assert stats["sum"] == 0.0
        assert stats["avg"] == 0.0

    def test_get_statistics_single_value(self) -> None:
        """Test statistics for single value."""
        agg = MetricAggregator()
        agg.record("duration", 100.0)

        stats = agg.get_statistics("duration")
        assert stats["count"] == 1
        assert stats["sum"] == 100.0
        assert stats["min"] == 100.0
        assert stats["max"] == 100.0
        assert stats["avg"] == 100.0

    def test_get_statistics_multiple_values(self) -> None:
        """Test statistics for multiple values."""
        agg = MetricAggregator()
        agg.record("duration", 100.0)
        agg.record("duration", 200.0)
        agg.record("duration", 300.0)

        stats = agg.get_statistics("duration")
        assert stats["count"] == 3
        assert stats["sum"] == 600.0
        assert stats["min"] == 100.0
        assert stats["max"] == 300.0
        assert stats["avg"] == 200.0

    def test_clear(self) -> None:
        """Test clearing all records."""
        agg = MetricAggregator()
        agg.record("metric_a", 1.0)
        agg.record("metric_b", 2.0)

        assert agg.count == 2
        agg.clear()
        assert agg.count == 0

    def test_deterministic_ordering(self) -> None:
        """Test that records are returned in insertion order."""
        agg = MetricAggregator()
        agg.record("metric", 1.0)
        agg.record("metric", 2.0)
        agg.record("metric", 3.0)

        records = agg.get_records()
        assert records[0].value == 1.0
        assert records[1].value == 2.0
        assert records[2].value == 3.0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_collect_workflow_duration(self) -> None:
        """Test workflow duration collection."""
        record = collect_workflow_duration(
            duration_ms=5000.0,
            workflow_name="test",
            workflow_id="wf-001",
        )

        assert record.name == "workflow_duration_ms"
        assert record.value == 5000.0
        assert record.labels["workflow_name"] == "test"
        assert record.source == "workflow_engine"

    def test_collect_execution_duration(self) -> None:
        """Test execution duration collection."""
        record = collect_execution_duration(
            duration_ms=3000.0,
            workflow_name="test",
            execution_id="exec-001",
        )

        assert record.name == "execution_duration_ms"
        assert record.value == 3000.0
        assert record.source == "execution_engine"

    def test_collect_provider_latency(self) -> None:
        """Test provider latency collection."""
        record = collect_provider_latency(
            latency_ms=250.0,
            provider_name="vllm",
            model="gpt-4",
        )

        assert record.name == "provider_latency_ms"
        assert record.value == 250.0
        assert record.labels["provider_name"] == "vllm"
        assert record.labels["model"] == "gpt-4"
        assert record.source == "provider"


class TestMetricRecordImmutability:
    """Tests for MetricRecord immutability."""

    def test_frozen(self) -> None:
        """Test that MetricRecord is frozen."""
        record = MetricRecord(name="test", value=1.0)
        assert record.__class__.__dataclass_params__.frozen is True

    def test_no_dict(self) -> None:
        """Test that MetricRecord has no __dict__."""
        record = MetricRecord(name="test", value=1.0)
        assert not hasattr(record, "__dict__")