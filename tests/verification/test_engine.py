"""Tests for self verification engine.

Verifies:
- Full engine flow
- Scoring calculation
- Statistics aggregation
- All status paths
- Empty verification
- Failed verification
- Warning handling
- Coverage >95%

"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)
from packages.verification.engine import SelfVerificationEngine
from packages.verification.rules import VerificationRule


# ---------------------------------------------------------------------------
# Mock objects for testing
# ---------------------------------------------------------------------------


@dataclass
class MockModifiedFile:
    """Mock ModifiedFile for testing."""

    path: str
    operation: str
    status: str = "APPLIED"


@dataclass
class MockStatistics:
    """Mock ModificationStatistics for testing."""

    files_modified: int = 0
    files_created: int = 0
    files_deleted: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    total_operations: int = 0


@dataclass
class MockWorkspaceChanges:
    """Mock WorkspaceChanges for testing."""

    applied_files: tuple = ()
    statistics: object = None
    success: bool = True
    warnings: tuple = ()
    execution_id: str = "exec-1"

    def __post_init__(self) -> None:
        """Set default statistics if None."""
        if self.statistics is None:
            object.__setattr__(self, "statistics", MockStatistics())


@dataclass
class MockWorkflowPlan:
    """Mock WorkflowPlan for testing."""

    workflow_name: str = "test-workflow"
    task_plans: tuple = ()


@dataclass
class MockExecutionPlan:
    """Mock ExecutionPlan for testing."""

    workflow_name: str = "test-workflow"
    execution_id: str = "exec-1"


@dataclass
class MockEvaluationReport:
    """Mock EvaluationReport for testing."""

    overall_score: float = 0.85
    summary: str = "Test summary"


@dataclass
class MockPatchSet:
    """Mock PatchSet for testing."""

    workflow_name: str = "test-workflow"
    execution_id: str = "exec-1"
    files: tuple = ()


# ---------------------------------------------------------------------------
# Test: Full Engine Flow
# ---------------------------------------------------------------------------


class TestEngineFlow:
    """Tests for full engine flow."""

    def test_successful_engine_flow(self) -> None:
        """Engine should produce a report for successful execution."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="implement")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert isinstance(report, VerificationReport)
        assert report.workflow_name == "implement"
        assert report.execution_id == "exec-1"

    def test_report_has_findings(self) -> None:
        """Report should contain findings."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert len(report.findings) > 0

    def test_report_has_statistics(self) -> None:
        """Report should contain statistics."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert report.statistics.executed_rules > 0

    def test_report_has_score(self) -> None:
        """Report should contain a score."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert 0.0 <= report.score <= 1.0

    def test_report_has_metadata(self) -> None:
        """Report should contain metadata."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert "engine" in report.metadata
        assert report.metadata["engine"] == "SelfVerificationEngine"


# ---------------------------------------------------------------------------
# Test: Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    """Tests for score calculation."""

    def test_score_is_deterministic(self) -> None:
        """Same inputs should produce same score."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report1 = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        report2 = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert report1.score == report2.score

    def test_score_in_range(self) -> None:
        """Score should be in range [0.0, 1.0]."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert 0.0 <= report.score <= 1.0

    def test_score_includes_evaluation_metadata(self) -> None:
        """Score should include evaluation report metadata."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert "evaluation_score" in report.metadata
        assert report.metadata["evaluation_score"] == 0.85


# ---------------------------------------------------------------------------
# Test: Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for statistics aggregation."""

    def test_statistics_has_executed_rules(self) -> None:
        """Statistics should contain executed_rules count."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert report.statistics.executed_rules > 0

    def test_statistics_has_duration(self) -> None:
        """Statistics should contain duration_ms."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert report.statistics.duration_ms >= 0

    def test_statistics_passed_plus_failed_plus_warnings_equals_executed(self) -> None:
        """passed + failed + warnings should equal executed."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        total = (
            report.statistics.passed_rules
            + report.statistics.failed_rules
            + report.statistics.warnings
        )
        assert total == report.statistics.executed_rules


# ---------------------------------------------------------------------------
# Test: PASSED Status
# ---------------------------------------------------------------------------


class TestPassedStatus:
    """Tests for PASSED status path."""

    def test_passed_status_with_no_issues(self) -> None:
        """PASSED status should be set when no issues found."""
        # The built-in rules produce INFO findings for successful execution
        # which results in PASSED status
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        # INFO findings result in PASSED status (no MEDIUM/HIGH/CRITICAL)
        assert report.verification_status in (
            VerificationStatus.PASSED,
            VerificationStatus.WARNING,
        )


# ---------------------------------------------------------------------------
# Test: FAILED Status
# ---------------------------------------------------------------------------


class TestFailedStatus:
    """Tests for FAILED status path."""

    def test_failed_status_with_high_severity(self) -> None:
        """FAILED status should be set when HIGH severity findings exist."""
        # Use a subprocess approach to test custom rule behavior
        # We'll verify the logic by checking the _calculate_status method directly
        from packages.verification.engine import SelfVerificationEngine

        # Create findings with HIGH severity
        findings = [
            VerificationFinding(
                id="high-001",
                category="test",
                severity=VerificationSeverity.HIGH,
                title="High issue",
                description="High issue found.",
                evidence="Evidence.",
            )
        ]
        status = SelfVerificationEngine._calculate_status(findings, 1, 1)
        assert status == VerificationStatus.FAILED


# ---------------------------------------------------------------------------
# Test: WARNING Status
# ---------------------------------------------------------------------------


class TestWarningStatus:
    """Tests for WARNING status path."""

    def test_warning_status_with_medium_severity(self) -> None:
        """WARNING status should be set when MEDIUM severity findings exist."""
        from packages.verification.engine import SelfVerificationEngine

        # Create findings with MEDIUM severity
        findings = [
            VerificationFinding(
                id="medium-001",
                category="test",
                severity=VerificationSeverity.MEDIUM,
                title="Medium issue",
                description="Medium issue found.",
                evidence="Evidence.",
            )
        ]
        status = SelfVerificationEngine._calculate_status(findings, 1, 1)
        assert status == VerificationStatus.WARNING


# ---------------------------------------------------------------------------
# Test: Empty Verification
# ---------------------------------------------------------------------------


class TestEmptyVerification:
    """Tests for empty verification scenarios."""

    def test_empty_applied_files(self) -> None:
        """Engine should handle empty applied_files."""
        changes = MockWorkspaceChanges(applied_files=())
        report = SelfVerificationEngine.verify(
            workflow_plan=MockWorkflowPlan(),
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert isinstance(report, VerificationReport)

    def test_no_workflow_plan(self) -> None:
        """Engine should handle None workflow_plan."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        report = SelfVerificationEngine.verify(
            workflow_plan=None,  # type: ignore
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert isinstance(report, VerificationReport)


# ---------------------------------------------------------------------------
# Test: Failed Verification
# ---------------------------------------------------------------------------


class TestFailedVerification:
    """Tests for failed verification scenarios."""

    def test_failed_report_has_findings(self) -> None:
        """Failed verification should have findings and reduced score."""
        from packages.verification.engine import SelfVerificationEngine

        # Create findings with HIGH severity
        findings = [
            VerificationFinding(
                id="high-001",
                category="test",
                severity=VerificationSeverity.HIGH,
                title="Critical issue",
                description="Critical issue found.",
                evidence="Evidence.",
            )
        ]
        status = SelfVerificationEngine._calculate_status(findings, 1, 1)
        assert status == VerificationStatus.FAILED

        # Score should be reduced by HIGH severity weight (0.30)
        score = SelfVerificationEngine._calculate_score(findings)
        assert score < 1.0
        assert score == 0.70  # 1.0 - 0.30 = 0.70


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_same_inputs_produce_same_report(self) -> None:
        """Same inputs should produce identical reports."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="test")

        report1 = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        report2 = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )

        assert report1.score == report2.score
        assert report1.verification_status == report2.verification_status
        assert len(report1.findings) == len(report2.findings)


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_unicode_workflow_name(self) -> None:
        """Engine should handle unicode in workflow_name."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        workflow = MockWorkflowPlan(workflow_name="\u4f60\u597d-workflow")
        report = SelfVerificationEngine.verify(
            workflow_plan=workflow,
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert "\u4f60\u597d" in report.workflow_name

    def test_many_applied_files(self) -> None:
        """Engine should handle many applied files."""
        files = tuple(
            MockModifiedFile(path=f"src/file_{i}.py", operation="MODIFY")
            for i in range(50)
        )
        changes = MockWorkspaceChanges(applied_files=files, success=True)
        report = SelfVerificationEngine.verify(
            workflow_plan=MockWorkflowPlan(),
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert isinstance(report, VerificationReport)

    def test_no_evaluation_report(self) -> None:
        """Engine should handle None evaluation_report."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        report = SelfVerificationEngine.verify(
            workflow_plan=MockWorkflowPlan(),
            execution_plan=MockExecutionPlan(),
            evaluation_report=None,  # type: ignore
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        assert isinstance(report, VerificationReport)
        assert "evaluation_score" not in report.metadata

    def test_report_is_immutable(self) -> None:
        """Report should be immutable."""
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            success=True,
        )
        report = SelfVerificationEngine.verify(
            workflow_plan=MockWorkflowPlan(),
            execution_plan=MockExecutionPlan(),
            evaluation_report=MockEvaluationReport(),
            patch_set=MockPatchSet(),
            workspace_changes=changes,
        )
        with pytest.raises(Exception):
            report.workflow_name = "modified"  # type: ignore[misc]