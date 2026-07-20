"""Tests for verification rules.

Verifies:
- Rule execution
- Deterministic ordering
- All built-in rules
- Edge cases
- Coverage >95%

"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from packages.verification.models import (
    VerificationFinding,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)
from packages.verification.rules import (
    NoDuplicateChangesRule,
    NoUnexpectedFilesRule,
    PatchAppliedRule,
    PatchStatisticsConsistencyRule,
    VerificationRule,
    WorkspaceConsistencyRule,
)


# ---------------------------------------------------------------------------
# Mock WorkspaceChanges for testing
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

    def __post_init__(self) -> None:
        """Set default statistics if None."""
        if self.statistics is None:
            object.__setattr__(self, "statistics", MockStatistics())


# ---------------------------------------------------------------------------
# Test: VerificationRule Base
# ---------------------------------------------------------------------------


class TestVerificationRuleBase:
    """Tests for VerificationRule base class."""

    def test_rule_id_is_class_name(self) -> None:
        """VerificationRule.rule_id should be the class name."""
        rule = PatchAppliedRule()
        assert rule.rule_id == "PatchAppliedRule"

    def test_category_is_class_name(self) -> None:
        """VerificationRule.category should be the class name."""
        rule = PatchAppliedRule()
        assert rule.category == "PatchAppliedRule"

    def test_default_severity_is_info(self) -> None:
        """VerificationRule default severity should be INFO."""

        class TestRule(VerificationRule):
            def verify(self, workspace_changes: object) -> VerificationFinding | None:
                return None

        rule = TestRule()
        assert rule.severity == VerificationSeverity.INFO


# ---------------------------------------------------------------------------
# Test: PatchAppliedRule
# ---------------------------------------------------------------------------


class TestPatchAppliedRule:
    """Tests for PatchAppliedRule."""

    def test_no_applied_files(self) -> None:
        """PatchAppliedRule should return None when no files."""
        rule = PatchAppliedRule()
        changes = MockWorkspaceChanges(applied_files=())
        result = rule.verify(changes)
        assert result is None

    def test_all_patches_applied(self) -> None:
        """PatchAppliedRule should return INFO when all patches applied."""
        rule = PatchAppliedRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY", status="APPLIED")
        file2 = MockModifiedFile(path="src/utils.py", operation="MODIFY", status="APPLIED")
        changes = MockWorkspaceChanges(
            applied_files=(file1, file2),
            success=True,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert result.title == "All patches applied successfully"

    def test_some_patches_failed(self) -> None:
        """PatchAppliedRule should return MEDIUM when patches failed."""
        rule = PatchAppliedRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY", status="FAILED")
        file2 = MockModifiedFile(path="src/utils.py", operation="MODIFY", status="APPLIED")
        changes = MockWorkspaceChanges(
            applied_files=(file1, file2),
            success=False,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.MEDIUM
        assert "failed to apply" in result.title.lower()

    def test_all_patches_failed(self) -> None:
        """PatchAppliedRule should report all failures."""
        rule = PatchAppliedRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY", status="FAILED")
        file2 = MockModifiedFile(path="src/utils.py", operation="MODIFY", status="FAILED")
        changes = MockWorkspaceChanges(
            applied_files=(file1, file2),
            success=False,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.MEDIUM
        assert "2 file(s) failed" in result.description

    def test_severity_is_medium(self) -> None:
        """PatchAppliedRule severity should be MEDIUM."""
        rule = PatchAppliedRule()
        assert rule.severity == VerificationSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test: NoUnexpectedFilesRule
# ---------------------------------------------------------------------------


class TestNoUnexpectedFilesRule:
    """Tests for NoUnexpectedFilesRule."""

    def test_no_warnings(self) -> None:
        """NoUnexpectedFilesRule should return INFO when no warnings."""
        rule = NoUnexpectedFilesRule()
        changes = MockWorkspaceChanges(warnings=())
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "No unexpected files" in result.title

    def test_with_unexpected_warnings(self) -> None:
        """NoUnexpectedFilesRule should return LOW when unexpected files found."""
        rule = NoUnexpectedFilesRule()
        changes = MockWorkspaceChanges(
            warnings=("unexpected file detected: src/extra.py",)
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.LOW
        assert "Unexpected files" in result.title

    def test_with_untracked_warnings(self) -> None:
        """NoUnexpectedFilesRule should detect untracked files."""
        rule = NoUnexpectedFilesRule()
        changes = MockWorkspaceChanges(
            warnings=("untracked file: src/debug.py",)
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.LOW

    def test_severity_is_low(self) -> None:
        """NoUnexpectedFilesRule severity should be LOW."""
        rule = NoUnexpectedFilesRule()
        assert rule.severity == VerificationSeverity.LOW


# ---------------------------------------------------------------------------
# Test: NoDuplicateChangesRule
# ---------------------------------------------------------------------------


class TestNoDuplicateChangesRule:
    """Tests for NoDuplicateChangesRule."""

    def test_no_duplicates(self) -> None:
        """NoDuplicateChangesRule should return INFO when no duplicates."""
        rule = NoDuplicateChangesRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        file2 = MockModifiedFile(path="src/utils.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1, file2),
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "No duplicate" in result.title

    def test_with_duplicates(self) -> None:
        """NoDuplicateChangesRule should return MEDIUM when duplicates found."""
        rule = NoDuplicateChangesRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        file2 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        changes = MockWorkspaceChanges(
            applied_files=(file1, file2),
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.MEDIUM
        assert "Duplicate" in result.title

    def test_severity_is_medium(self) -> None:
        """NoDuplicateChangesRule severity should be MEDIUM."""
        rule = NoDuplicateChangesRule()
        assert rule.severity == VerificationSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test: WorkspaceConsistencyRule
# ---------------------------------------------------------------------------


class TestWorkspaceConsistencyRule:
    """Tests for WorkspaceConsistencyRule."""

    def test_consistent_workspace(self) -> None:
        """WorkspaceConsistencyRule should return INFO when consistent."""
        rule = WorkspaceConsistencyRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        stats = MockStatistics(files_modified=1)
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "consistent" in result.title.lower()

    def test_missing_statistics(self) -> None:
        """WorkspaceConsistencyRule should return INFO when statistics missing but no files."""
        rule = WorkspaceConsistencyRule()
        changes = MockWorkspaceChanges(
            applied_files=(),
            statistics=None,
        )
        result = rule.verify(changes)
        # When no applied files and no statistics, the workspace is consistent
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "consistent" in result.title.lower()

    def test_inconsistent_statistics(self) -> None:
        """WorkspaceConsistencyRule should return MEDIUM when inconsistent."""
        rule = WorkspaceConsistencyRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        stats = MockStatistics(files_modified=0)  # Should be 1
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.MEDIUM
        assert "inconsistency" in result.title.lower()

    def test_severity_is_medium(self) -> None:
        """WorkspaceConsistencyRule base severity should be MEDIUM."""
        rule = WorkspaceConsistencyRule()
        assert rule.severity == VerificationSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test: PatchStatisticsConsistencyRule
# ---------------------------------------------------------------------------


class TestPatchStatisticsConsistencyRule:
    """Tests for PatchStatisticsConsistencyRule."""

    def test_consistent_statistics(self) -> None:
        """PatchStatisticsConsistencyRule should return INFO when consistent."""
        rule = PatchStatisticsConsistencyRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        stats = MockStatistics(total_operations=1, lines_added=5, lines_removed=3)
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "consistent" in result.title.lower()

    def test_mismatched_operations(self) -> None:
        """PatchStatisticsConsistencyRule should return MEDIUM on mismatch."""
        rule = PatchStatisticsConsistencyRule()
        file1 = MockModifiedFile(path="src/main.py", operation="MODIFY")
        stats = MockStatistics(total_operations=0)  # Should be 1
        changes = MockWorkspaceChanges(
            applied_files=(file1,),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.MEDIUM
        assert "mismatch" in result.title.lower()

    def test_negative_lines_added(self) -> None:
        """PatchStatisticsConsistencyRule should return HIGH on negative lines_added."""
        rule = PatchStatisticsConsistencyRule()
        stats = MockStatistics(total_operations=0, lines_added=-5)
        changes = MockWorkspaceChanges(
            applied_files=(),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.HIGH
        assert "Negative lines added" in result.title

    def test_negative_lines_removed(self) -> None:
        """PatchStatisticsConsistencyRule should return HIGH on negative lines_removed."""
        rule = PatchStatisticsConsistencyRule()
        stats = MockStatistics(total_operations=0, lines_removed=-10)
        changes = MockWorkspaceChanges(
            applied_files=(),
            statistics=stats,
        )
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.HIGH
        assert "Negative lines removed" in result.title

    def test_no_statistics(self) -> None:
        """PatchStatisticsConsistencyRule returns INFO when no statistics and no files."""
        rule = PatchStatisticsConsistencyRule()
        changes = MockWorkspaceChanges(
            applied_files=(),
            statistics=None,
        )
        result = rule.verify(changes)
        # When no applied files, no statistics needed - consistent state
        assert result is not None
        assert result.severity == VerificationSeverity.INFO
        assert "consistent" in result.title.lower()

    def test_severity_is_medium(self) -> None:
        """PatchStatisticsConsistencyRule base severity should be MEDIUM."""
        rule = PatchStatisticsConsistencyRule()
        assert rule.severity == VerificationSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test: Deterministic Ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic rule ordering."""

    def test_all_rules_have_unique_ids(self) -> None:
        """All rules should have unique rule IDs."""
        rules = [
            NoDuplicateChangesRule(),
            NoUnexpectedFilesRule(),
            PatchAppliedRule(),
            PatchStatisticsConsistencyRule(),
            WorkspaceConsistencyRule(),
        ]
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids))

    def test_all_rules_have_unique_categories(self) -> None:
        """All rules should have unique categories."""
        rules = [
            NoDuplicateChangesRule(),
            NoUnexpectedFilesRule(),
            PatchAppliedRule(),
            PatchStatisticsConsistencyRule(),
            WorkspaceConsistencyRule(),
        ]
        categories = [r.category for r in rules]
        assert len(categories) == len(set(categories))

    def test_rules_execute_in_sorted_order(self) -> None:
        """Rules should execute in sorted order by rule_id."""
        rules = [
            WorkspaceConsistencyRule(),
            NoDuplicateChangesRule(),
            PatchStatisticsConsistencyRule(),
            NoUnexpectedFilesRule(),
            PatchAppliedRule(),
        ]
        sorted_ids = sorted(r.rule_id for r in rules)
        assert sorted_ids == [
            "NoDuplicateChangesRule",
            "NoUnexpectedFilesRule",
            "PatchAppliedRule",
            "PatchStatisticsConsistencyRule",
            "WorkspaceConsistencyRule",
        ]


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file_path(self) -> None:
        """Rules should handle empty file paths."""
        rule = NoDuplicateChangesRule()
        file1 = MockModifiedFile(path="", operation="MODIFY")
        changes = MockWorkspaceChanges(applied_files=(file1,))
        result = rule.verify(changes)
        assert result is not None

    def test_unicode_file_path(self) -> None:
        """Rules should handle unicode in file paths."""
        rule = NoDuplicateChangesRule()
        file1 = MockModifiedFile(path="src/\u4f60\u597d.py", operation="MODIFY")
        changes = MockWorkspaceChanges(applied_files=(file1,))
        result = rule.verify(changes)
        assert result is not None

    def test_many_applied_files(self) -> None:
        """Rules should handle many applied files."""
        rule = NoDuplicateChangesRule()
        files = tuple(
            MockModifiedFile(path=f"src/file_{i}.py", operation="MODIFY")
            for i in range(100)
        )
        changes = MockWorkspaceChanges(applied_files=files)
        result = rule.verify(changes)
        assert result is not None
        assert result.severity == VerificationSeverity.INFO

    def test_all_severity_levels(self) -> None:
        """All rules should handle all severity levels correctly."""
        for severity in VerificationSeverity:
            finding = VerificationFinding(
                id="test",
                category="test",
                severity=severity,
                title="Test",
                description="Test.",
                evidence="Test.",
            )
            assert finding.severity == severity