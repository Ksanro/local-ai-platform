"""Tests for Execution Engine runtime models."""

from __future__ import annotations

import pytest

from packages.execution.runtime_models import (
    ExecutionReport,
    ExecutionSession,
    ExecutionStatus,
    ExecutionStepResult,
)

# ---------------------------------------------------------------------------
# ExecutionStatus
# ---------------------------------------------------------------------------


class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_enum_values(self):
        """Enum has correct string values."""
        assert ExecutionStatus.PENDING.value == "PENDING"
        assert ExecutionStatus.RUNNING.value == "RUNNING"
        assert ExecutionStatus.COMPLETED.value == "COMPLETED"
        assert ExecutionStatus.FAILED.value == "FAILED"
        assert ExecutionStatus.CANCELLED.value == "CANCELLED"

    def test_enum_equality(self):
        """Enum equality works correctly."""
        assert ExecutionStatus.COMPLETED.value == "COMPLETED"
        assert ExecutionStatus.PENDING.value != ExecutionStatus.RUNNING.value  # type: ignore[comparison-overlap]

    def test_enum_iteration(self):
        """Enum can be iterated."""
        values = [s.value for s in ExecutionStatus]
        assert len(values) == 5


# ---------------------------------------------------------------------------
# ExecutionStepResult
# ---------------------------------------------------------------------------


class TestExecutionStepResult:
    """Tests for ExecutionStepResult model."""

    def test_immutable(self):
        """Model is immutable (frozen dataclass)."""
        result = ExecutionStepResult(
            step_name="test_step",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test completed",
        )
        with pytest.raises(Exception):
            result.step_name = "changed"  # type: ignore[misc]
        with pytest.raises(Exception):
            result.status = ExecutionStatus.FAILED  # type: ignore[misc]
        with pytest.raises(Exception):
            result.metadata = {"key": "value"}  # type: ignore[misc]

    def test_default_metadata(self):
        """Metadata defaults to empty dict."""
        result = ExecutionStepResult(
            step_name="test_step",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test completed",
        )
        assert result.metadata == {}

    def test_equality(self):
        """Equality comparison works correctly."""
        result1 = ExecutionStepResult(
            step_name="test_step",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test completed",
            metadata={"key": "value"},
        )
        result2 = ExecutionStepResult(
            step_name="test_step",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test completed",
            metadata={"key": "value"},
        )
        assert result1 == result2

    def test_inequality(self):
        """Inequality comparison works correctly."""
        result1 = ExecutionStepResult(
            step_name="step_a",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test A",
        )
        result2 = ExecutionStepResult(
            step_name="step_b",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Test B",
        )
        assert result1 != result2

    def test_deterministic_ordering(self):
        """Models are comparable for sorting."""
        results = [
            ExecutionStepResult(
                step_name="b",
                status=ExecutionStatus.COMPLETED,
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:00:01",
                duration_ms=500,
                output_summary="B",
            ),
            ExecutionStepResult(
                step_name="a",
                status=ExecutionStatus.COMPLETED,
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:00:01",
                duration_ms=300,
                output_summary="A",
            ),
        ]
        sorted_results = sorted(results, key=lambda r: r.step_name)
        assert sorted_results[0].step_name == "a"
        assert sorted_results[1].step_name == "b"


# ---------------------------------------------------------------------------
# ExecutionSession
# ---------------------------------------------------------------------------


class TestExecutionSession:
    """Tests for ExecutionSession model."""

    def test_immutable(self):
        """Model is immutable (frozen dataclass)."""
        session = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.RUNNING,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
        )
        with pytest.raises(Exception):
            session.session_id = "changed"  # type: ignore[misc]
        with pytest.raises(Exception):
            session.execution_status = ExecutionStatus.COMPLETED  # type: ignore[misc]

    def test_default_executed_steps(self):
        """executed_steps defaults to empty tuple."""
        session = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.RUNNING,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
        )
        assert session.executed_steps == ()

    def test_default_metadata(self):
        """metadata defaults to empty dict."""
        session = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.RUNNING,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
        )
        assert session.metadata == {}

    def test_with_steps(self):
        """Session can contain step results."""
        step1 = ExecutionStepResult(
            step_name="step1",
            status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            duration_ms=1000,
            output_summary="Done",
        )
        session = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
            executed_steps=(step1,),
        )
        assert len(session.executed_steps) == 1
        assert session.executed_steps[0].step_name == "step1"

    def test_equality(self):
        """Equality comparison works correctly."""
        session1 = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
        )
        session2 = ExecutionSession(
            session_id="sess-001",
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:00:10",
        )
        assert session1 == session2


# ---------------------------------------------------------------------------
# ExecutionReport
# ---------------------------------------------------------------------------


class TestExecutionReport:
    """Tests for ExecutionReport model."""

    def test_immutable(self):
        """Model is immutable (frozen dataclass)."""
        report = ExecutionReport(
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=5000,
            step_results=(),
            adapter_name="TestAdapter",
            success=True,
        )
        with pytest.raises(Exception):
            report.workflow_name = "changed"  # type: ignore[misc]
        with pytest.raises(Exception):
            report.execution_status = ExecutionStatus.FAILED  # type: ignore[misc]
        with pytest.raises(Exception):
            report.success = False  # type: ignore[misc]

    def test_default_failures(self):
        """failures defaults to empty tuple."""
        report = ExecutionReport(
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=5000,
            step_results=(),
            adapter_name="TestAdapter",
            success=True,
        )
        assert report.failures == ()

    def test_success_true(self):
        """success=True when all steps complete."""
        report = ExecutionReport(
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=5000,
            step_results=(),
            adapter_name="TestAdapter",
            success=True,
        )
        assert report.success is True

    def test_success_false(self):
        """success=False when execution failed."""
        report = ExecutionReport(
            workflow_name="test_workflow",
            execution_status=ExecutionStatus.FAILED,
            total_duration_ms=5000,
            step_results=(),
            adapter_name="TestAdapter",
            success=False,
            failures=("Step failed",),
        )
        assert report.success is False
        assert len(report.failures) == 1

    def test_equality(self):
        """Equality comparison works correctly."""
        report1 = ExecutionReport(
            workflow_name="test",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=1000,
            step_results=(),
            adapter_name="Adapter",
            success=True,
        )
        report2 = ExecutionReport(
            workflow_name="test",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=1000,
            step_results=(),
            adapter_name="Adapter",
            success=True,
        )
        assert report1 == report2

    def test_inequality(self):
        """Inequality comparison works correctly."""
        report1 = ExecutionReport(
            workflow_name="test1",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=1000,
            step_results=(),
            adapter_name="Adapter",
            success=True,
        )
        report2 = ExecutionReport(
            workflow_name="test2",
            execution_status=ExecutionStatus.COMPLETED,
            total_duration_ms=1000,
            step_results=(),
            adapter_name="Adapter",
            success=True,
        )
        assert report1 != report2

    def test_deterministic_ordering(self):
        """Models are sortable by first field."""
        reports = [
            ExecutionReport(
                workflow_name="b",
                execution_status=ExecutionStatus.COMPLETED,
                total_duration_ms=1000,
                step_results=(),
                adapter_name="Adapter",
                success=True,
            ),
            ExecutionReport(
                workflow_name="a",
                execution_status=ExecutionStatus.COMPLETED,
                total_duration_ms=1000,
                step_results=(),
                adapter_name="Adapter",
                success=True,
            ),
        ]
        sorted_reports = sorted(reports, key=lambda r: r.workflow_name)
        assert sorted_reports[0].workflow_name == "a"
        assert sorted_reports[1].workflow_name == "b"
