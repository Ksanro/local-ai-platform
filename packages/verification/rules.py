"""Verification rules framework.

Implements a rule-based framework for verifying engineering execution
results. Each rule is stateless and deterministic.

Architecture
------------

VerificationRule (ABC) --> Built-in Rules
                              |-- PatchAppliedRule
                              |-- NoUnexpectedFilesRule
                              |-- NoDuplicateChangesRule
                              |-- WorkspaceConsistencyRule
                              |-- PatchStatisticsConsistencyRule

Constraints
-----------

- Rules are stateless and deterministic.
- Rules consume only public engineering artifacts.
- Rules NEVER modify inputs.
- Rules NEVER inspect repositories.
- Rules NEVER execute code.

Public API
----------

.. code-block:: python

    from packages.verification.rules import (
        NoDuplicateChangesRule,
        NoUnexpectedFilesRule,
        PatchAppliedRule,
        PatchStatisticsConsistencyRule,
        VerificationRule,
        WorkspaceConsistencyRule,
    )

    rule = PatchAppliedRule()
    finding = rule.verify(workspace_changes)

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from packages.verification.models import (
    VerificationFinding,
    VerificationSeverity,
    VerificationStatus,
)

__all__ = [
    "NoDuplicateChangesRule",
    "NoUnexpectedFilesRule",
    "PatchAppliedRule",
    "PatchStatisticsConsistencyRule",
    "VerificationRule",
    "WorkspaceConsistencyRule",
]


# ---------------------------------------------------------------------------
# VerificationRule (Abstract Base Class)
# ---------------------------------------------------------------------------


class VerificationRule(ABC):
    """Abstract base class for all verification rules.

    Each rule is stateless and deterministic. Rules consume only public
    engineering artifacts and produce VerificationFinding or None.

    Attributes:
        rule_id: Unique identifier for the rule.
        category: Category of the rule.
        severity: Severity level of findings from this rule.
    """

    @property
    def rule_id(self) -> str:
        """Unique identifier for the rule."""
        return self.__class__.__name__

    @property
    def category(self) -> str:
        """Category of the rule."""
        return self.__class__.__name__

    @property
    def severity(self) -> VerificationSeverity:
        """Severity level of findings from this rule."""
        return VerificationSeverity.INFO

    @abstractmethod
    def verify(self, workspace_changes: Any) -> VerificationFinding | None:
        """Verify workspace changes and produce a finding or None.

        Args:
            workspace_changes: WorkspaceChanges-like object with:
                - applied_files: tuple of ModifiedFile-like objects
                - statistics: ModificationStatistics-like object
                - success: bool
                - warnings: tuple of warning strings

        Returns:
            VerificationFinding if issues found, None otherwise.
        """
        ...


# ---------------------------------------------------------------------------
# PatchAppliedRule
# ---------------------------------------------------------------------------


class PatchAppliedRule(VerificationRule):
    """Verifies that all patches were applied successfully.

    Checks that all applied files have APPLIED status when success is True.
    Reports FAILED status for files that show FAILED status.
    """

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(
        self, workspace_changes: Any
    ) -> VerificationFinding | None:
        """Verify that patches were applied successfully.

        Args:
            workspace_changes: WorkspaceChanges-like object.

        Returns:
            VerificationFinding if issues found, None otherwise.
        """
        applied_files = getattr(
            workspace_changes, "applied_files", ()
        )
        success = getattr(workspace_changes, "success", True)

        if not applied_files:
            return None

        failed_files: list[str] = []

        for file in applied_files:
            status = getattr(file, "status", None)
            if status is None:
                continue

            # Check if status is a string or enum value
            status_value: str
            if hasattr(status, "value"):
                status_value = status.value
            else:
                status_value = str(status)

            if status_value == "FAILED":
                failed_files.append(getattr(file, "path", "unknown"))

        if failed_files:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="patch-applied",
                severity=VerificationSeverity.MEDIUM,
                title="Some patches failed to apply",
                description=(
                    f"{len(failed_files)} file(s) failed to apply: "
                    f"{', '.join(failed_files)}"
                ),
                evidence=f"Failed files: {', '.join(failed_files)}",
                recommendation=(
                    "Review the modification engine logs to determine "
                    "why these patches failed."
                ),
            )

        if success:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="patch-applied",
                severity=VerificationSeverity.INFO,
                title="All patches applied successfully",
                description=(
                    f"All {len(applied_files)} patch(es) were applied "
                    "without errors."
                ),
                evidence=(
                    f"Applied files: "
                    f"{', '.join(getattr(f, 'path', '') for f in applied_files)}"
                ),
                recommendation=None,
            )

        return None


# ---------------------------------------------------------------------------
# NoUnexpectedFilesRule
# ---------------------------------------------------------------------------


class NoUnexpectedFilesRule(VerificationRule):
    """Verifies that no unexpected files exist in the workspace.

    Checks that all modified files are expected based on the patch set.
    Reports any files that were not part of the original patch set.
    """

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.LOW

    def verify(
        self, workspace_changes: Any
    ) -> VerificationFinding | None:
        """Verify no unexpected files exist.

        Args:
            workspace_changes: WorkspaceChanges-like object.

        Returns:
            VerificationFinding if unexpected files found, None otherwise.
        """
        applied_files = getattr(
            workspace_changes, "applied_files", ()
        )
        warnings = getattr(workspace_changes, "warnings", ())

        unexpected_files: list[str] = []

        for warning in warnings:
            if "unexpected" in warning.lower() or "untracked" in warning.lower():
                unexpected_files.append(warning)

        if unexpected_files:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="unexpected-files",
                severity=VerificationSeverity.LOW,
                title="Unexpected files detected in workspace",
                description=(
                    f"{len(unexpected_files)} unexpected file(s) detected: "
                    f"{', '.join(unexpected_files[:5])}"
                ),
                evidence=(
                    f"Unexpected: {', '.join(unexpected_files[:10])}"
                ),
                recommendation=(
                    "Review the workspace for untracked or unexpected "
                    "changes not part of the original patch set."
                ),
            )

        return VerificationFinding(
            id=f"{self.rule_id}-001",
            category="unexpected-files",
            severity=VerificationSeverity.INFO,
            title="No unexpected files detected",
            description="All workspace files are expected.",
            evidence="No unexpected files found in workspace.",
            recommendation=None,
        )


# ---------------------------------------------------------------------------
# NoDuplicateChangesRule
# ---------------------------------------------------------------------------


class NoDuplicateChangesRule(VerificationRule):
    """Verifies that no duplicate changes exist in the workspace.

    Checks that no two files in the applied files list have the same path.
    Reports duplicate paths if found.
    """

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(
        self, workspace_changes: Any
    ) -> VerificationFinding | None:
        """Verify no duplicate changes exist.

        Args:
            workspace_changes: WorkspaceChanges-like object.

        Returns:
            VerificationFinding if duplicates found, None otherwise.
        """
        applied_files = getattr(
            workspace_changes, "applied_files", ()
        )

        seen_paths: dict[str, int] = {}
        duplicates: list[str] = []

        for idx, file in enumerate(applied_files):
            path = getattr(file, "path", "")
            if path in seen_paths:
                if path not in duplicates:
                    duplicates.append(path)
            else:
                seen_paths[path] = idx

        if duplicates:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="duplicate-changes",
                severity=VerificationSeverity.MEDIUM,
                title="Duplicate changes detected",
                description=(
                    f"{len(duplicates)} file(s) have duplicate changes: "
                    f"{', '.join(duplicates)}"
                ),
                evidence=f"Duplicate paths: {', '.join(duplicates)}",
                recommendation=(
                    "Review the patch set for duplicate entries. "
                    "Each file should appear only once."
                ),
            )

        return VerificationFinding(
            id=f"{self.rule_id}-001",
            category="duplicate-changes",
            severity=VerificationSeverity.INFO,
            title="No duplicate changes detected",
            description="All applied files have unique paths.",
            evidence=(
                f"{len(applied_files)} unique files applied."
            ),
            recommendation=None,
        )


# ---------------------------------------------------------------------------
# WorkspaceConsistencyRule
# ---------------------------------------------------------------------------


class WorkspaceConsistencyRule(VerificationRule):
    """Verifies workspace state consistency.

    Checks that the workspace state is consistent with the reported
    statistics. Ensures that file counts match operation counts.
    """

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(
        self, workspace_changes: Any
    ) -> VerificationFinding | None:
        """Verify workspace consistency.

        Args:
            workspace_changes: WorkspaceChanges-like object.

        Returns:
            VerificationFinding if inconsistencies found, None otherwise.
        """
        applied_files = getattr(
            workspace_changes, "applied_files", ()
        )
        statistics = getattr(
            workspace_changes, "statistics", None
        )

        if statistics is None:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="workspace-consistency",
                severity=VerificationSeverity.HIGH,
                title="Missing workspace statistics",
                description="Workspace statistics are missing.",
                evidence="No statistics object found.",
                recommendation=(
                    "Ensure the modification engine produces statistics."
                ),
            )

        # Count operations by type
        modify_count = 0
        add_count = 0
        delete_count = 0

        for file in applied_files:
            operation = getattr(file, "operation", "")
            if operation == "MODIFY":
                modify_count += 1
            elif operation == "ADD":
                add_count += 1
            elif operation == "DELETE":
                delete_count += 1

        # Check consistency
        inconsistencies: list[str] = []

        if getattr(statistics, "files_modified", 0) != modify_count:
            inconsistencies.append(
                f"files_modified mismatch: "
                f"reported={getattr(statistics, 'files_modified', 0)}, "
                f"actual={modify_count}"
            )

        if getattr(statistics, "files_created", 0) != add_count:
            inconsistencies.append(
                f"files_created mismatch: "
                f"reported={getattr(statistics, 'files_created', 0)}, "
                f"actual={add_count}"
            )

        if getattr(statistics, "files_deleted", 0) != delete_count:
            inconsistencies.append(
                f"files_deleted mismatch: "
                f"reported={getattr(statistics, 'files_deleted', 0)}, "
                f"actual={delete_count}"
            )

        if inconsistencies:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="workspace-consistency",
                severity=VerificationSeverity.MEDIUM,
                title="Workspace statistics inconsistency",
                description=(
                    f"{len(inconsistencies)} inconsistency(ies) found: "
                    f"{'; '.join(inconsistencies[:3])}"
                ),
                evidence="\n".join(inconsistencies),
                recommendation=(
                    "Review the modification engine to ensure statistics "
                    "are calculated correctly."
                ),
            )

        return VerificationFinding(
            id=f"{self.rule_id}-001",
            category="workspace-consistency",
            severity=VerificationSeverity.INFO,
            title="Workspace is consistent",
            description="All workspace statistics are consistent.",
            evidence=(
                f"Files: {modify_count} modified, "
                f"{add_count} created, {delete_count} deleted."
            ),
            recommendation=None,
        )


# ---------------------------------------------------------------------------
# PatchStatisticsConsistencyRule
# ---------------------------------------------------------------------------


class PatchStatisticsConsistencyRule(VerificationRule):
    """Verifies that patch statistics are consistent.

    Checks that the total_operations count matches the sum of
    individual operations and that lines added/removed are non-negative.
    """

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(
        self, workspace_changes: Any
    ) -> VerificationFinding | None:
        """Verify patch statistics consistency.

        Args:
            workspace_changes: WorkspaceChanges-like object.

        Returns:
            VerificationFinding if inconsistencies found, None otherwise.
        """
        applied_files = getattr(
            workspace_changes, "applied_files", ()
        )
        statistics = getattr(
            workspace_changes, "statistics", None
        )

        if statistics is None:
            return None

        # Calculate total operations from applied files
        total_operations = len(applied_files)

        reported_operations = getattr(
            statistics, "total_operations", 0
        )

        if total_operations != reported_operations:
            return VerificationFinding(
                id=f"{self.rule_id}-001",
                category="patch-statistics",
                severity=VerificationSeverity.MEDIUM,
                title="Patch statistics mismatch",
                description=(
                    f"total_operations mismatch: "
                    f"reported={reported_operations}, "
                    f"actual={total_operations}"
                ),
                evidence=(
                    f"Reported: {reported_operations}, "
                    f"Actual: {total_operations}"
                ),
                recommendation=(
                    "Ensure total_operations matches the number of "
                    "applied files."
                ),
            )

        # Check for negative values
        lines_added = getattr(statistics, "lines_added", 0)
        lines_removed = getattr(statistics, "lines_removed", 0)

        if lines_added < 0:
            return VerificationFinding(
                id=f"{self.rule_id}-002",
                category="patch-statistics",
                severity=VerificationSeverity.HIGH,
                title="Negative lines added",
                description=(
                    f"lines_added is negative: {lines_added}"
                ),
                evidence=f"lines_added={lines_added}",
                recommendation=(
                    "Review the modification engine to ensure "
                    "lines_added is calculated correctly."
                ),
            )

        if lines_removed < 0:
            return VerificationFinding(
                id=f"{self.rule_id}-002",
                category="patch-statistics",
                severity=VerificationSeverity.HIGH,
                title="Negative lines removed",
                description=(
                    f"lines_removed is negative: {lines_removed}"
                ),
                evidence=f"lines_removed={lines_removed}",
                recommendation=(
                    "Review the modification engine to ensure "
                    "lines_removed is calculated correctly."
                ),
            )

        return VerificationFinding(
            id=f"{self.rule_id}-001",
            category="patch-statistics",
            severity=VerificationSeverity.INFO,
            title="Patch statistics are consistent",
            description="All patch statistics are valid.",
            evidence=(
                f"Operations: {reported_operations}, "
                f"Added: {lines_added}, Removed: {lines_removed}"
            ),
            recommendation=None,
        )