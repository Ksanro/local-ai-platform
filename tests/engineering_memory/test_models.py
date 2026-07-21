"""Tests for Engineering Memory models.

Covers:
- Immutable dataclass validation
- Required fields validation
- Serialization/deserialization round-trip
- Property accessors (evaluation_score, iteration_count, modified_modules)
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from packages.engineering_memory.models import (
    EngineeringSessionRecord,
    MemoryStatistics,
)


# ---------------------------------------------------------------------------
# EngineeringSessionRecord
# ---------------------------------------------------------------------------


class TestEngineeringSessionRecord:
    """Tests for EngineeringSessionRecord model."""

    def test_create_minimal_record(self):
        """Test creating a record with required fields."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Fix null pointer",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
        )

        assert record.session_id == "sess-001"
        assert record.workflow_name == "bug-fix"
        assert record.request_summary == "Fix null pointer"
        assert record.transaction_id == "txn-001"
        assert record.controller_decision == "COMPLETE"
        assert record.execution_report == {}
        assert record.verification_report == {}
        assert record.evaluation_report == {}
        assert record.metadata == {}

    def test_create_full_record(self):
        """Test creating a record with all fields."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Fix null pointer in ModuleX",
            transaction_id="txn-001",
            execution_report={
                "status": "COMPLETED",
                "duration_ms": 1234,
            },
            verification_report={
                "status": "PASSED",
                "score": 0.95,
            },
            evaluation_report={
                "overall_score": 0.9,
                "metrics": ["correctness", "performance"],
            },
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={
                "modified_modules": ["module_x", "module_y"],
                "iteration_count": 3,
            },
        )

        assert record.session_id == "sess-001"
        assert record.execution_report["status"] == "COMPLETED"
        assert record.verification_report["score"] == 0.95
        assert record.evaluation_report["overall_score"] == 0.9
        assert record.metadata["iteration_count"] == 3

    def test_immutability(self):
        """Test that records are immutable (frozen dataclass)."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Fix null pointer",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
        )

        with pytest.raises(AttributeError):
            record.session_id = "sess-002"

        with pytest.raises(AttributeError):
            record.execution_report = {"new": "data"}

    def test_evaluation_score_extraction(self):
        """Test evaluation_score property."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            evaluation_report={"overall_score": 0.85},
        )
        assert record.evaluation_score == 0.85

    def test_evaluation_score_missing(self):
        """Test evaluation_score returns None when missing."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            evaluation_report={},
        )
        assert record.evaluation_score is None

    def test_evaluation_score_invalid(self):
        """Test evaluation_score returns None for invalid values."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            evaluation_report={"overall_score": "not-a-number"},
        )
        assert record.evaluation_score is None

    def test_iteration_count_extraction(self):
        """Test iteration_count property."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={"iteration_count": 5},
        )
        assert record.iteration_count == 5

    def test_iteration_count_missing(self):
        """Test iteration_count returns 0 when missing."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={},
        )
        assert record.iteration_count == 0

    def test_modified_modules_from_list(self):
        """Test modified_modules from a list."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={"modified_modules": ["module_z", "module_a", "module_b"]},
        )
        assert record.modified_modules == ("module_a", "module_b", "module_z")

    def test_modified_modules_from_string(self):
        """Test modified_modules from a single string."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={"modified_modules": "module_x"},
        )
        assert record.modified_modules == ("module_x",)

    def test_modified_modules_empty(self):
        """Test modified_modules when metadata is empty."""
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={},
        )
        assert record.modified_modules == ()

    def test_to_dict_round_trip(self):
        """Test serialization and deserialization round-trip."""
        original = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Fix null pointer",
            transaction_id="txn-001",
            execution_report={"status": "COMPLETED"},
            verification_report={"status": "PASSED"},
            evaluation_report={"overall_score": 0.9},
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
            metadata={"modified_modules": ["module_x"]},
        )

        data = original.to_dict()
        restored = EngineeringSessionRecord.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.workflow_name == original.workflow_name
        assert restored.request_summary == original.request_summary
        assert restored.transaction_id == original.transaction_id
        assert restored.execution_report == original.execution_report
        assert restored.verification_report == original.verification_report
        assert restored.evaluation_report == original.evaluation_report
        assert restored.controller_decision == original.controller_decision
        assert restored.completed_at == original.completed_at
        assert restored.metadata == original.metadata

    def test_from_dict_missing_required_field(self):
        """Test from_dict raises ValueError for missing required fields."""
        incomplete_data = {
            "session_id": "sess-001",
            "workflow_name": "bug-fix",
            # Missing request_summary, transaction_id, etc.
        }

        with pytest.raises(ValueError, match="Missing required field"):
            EngineeringSessionRecord.from_dict(incomplete_data)

    def test_from_dict_preserves_optional_fields(self):
        """Test from_dict with minimal data preserves defaults."""
        minimal_data = {
            "session_id": "sess-001",
            "workflow_name": "bug-fix",
            "request_summary": "Test",
            "transaction_id": "txn-001",
            "controller_decision": "COMPLETE",
            "completed_at": "2026-07-21T14:55:00+00:00",
        }

        record = EngineeringSessionRecord.from_dict(minimal_data)
        assert record.execution_report == {}
        assert record.verification_report == {}
        assert record.evaluation_report == {}
        assert record.metadata == {}

    def test_equality(self):
        """Test record equality comparison."""
        record1 = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
        )
        record2 = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
        )

        assert record1 == record2

    def test_not_hashable(self):
        """Test that records with dict fields are not hashable.

        Frozen dataclasses with mutable fields (dict) cannot be hashed
        because dict is not hashable in Python.
        """
        record = EngineeringSessionRecord(
            session_id="sess-001",
            workflow_name="bug-fix",
            request_summary="Test",
            transaction_id="txn-001",
            controller_decision="COMPLETE",
            completed_at="2026-07-21T14:55:00+00:00",
        )

        # Dict fields make it unhashable
        with pytest.raises(TypeError):
            hash(record)


class TestMemoryStatistics:
    """Tests for MemoryStatistics model."""

    def test_default_statistics(self):
        """Test default statistics values."""
        stats = MemoryStatistics()
        assert stats.total_sessions == 0
        assert stats.successful_sessions == 0
        assert stats.failed_sessions == 0
        assert stats.average_evaluation_score == 0.0
        assert stats.average_iterations == 0.0
        assert stats.workflow_usage == {}

    def test_success_rate_empty(self):
        """Test success_rate returns 0.0 when no sessions."""
        stats = MemoryStatistics()
        assert stats.success_rate == 0.0

    def test_success_rate_with_sessions(self):
        """Test success_rate calculation."""
        stats = MemoryStatistics(
            total_sessions=10,
            successful_sessions=8,
            failed_sessions=2,
        )
        assert stats.success_rate == 0.8

    def test_success_rate_all_successful(self):
        """Test success_rate when all sessions are successful."""
        stats = MemoryStatistics(
            total_sessions=5,
            successful_sessions=5,
            failed_sessions=0,
        )
        assert stats.success_rate == 1.0

    def test_immutability(self):
        """Test that statistics are immutable."""
        stats = MemoryStatistics(total_sessions=10)
        with pytest.raises(AttributeError):
            stats.total_sessions = 20

    def test_full_statistics(self):
        """Test statistics with full data."""
        stats = MemoryStatistics(
            total_sessions=100,
            successful_sessions=85,
            failed_sessions=15,
            average_evaluation_score=0.875,
            average_iterations=3.5,
            workflow_usage={
                "bug-fix": 40,
                "feature-add": 35,
                "refactor": 25,
            },
        )

        assert stats.total_sessions == 100
        assert stats.successful_sessions == 85
        assert stats.failed_sessions == 15
        assert stats.average_evaluation_score == 0.875
        assert stats.average_iterations == 3.5
        assert stats.workflow_usage == {
            "bug-fix": 40,
            "feature-add": 35,
            "refactor": 25,
        }