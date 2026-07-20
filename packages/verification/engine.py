"""Self Verification Engine.

Orchestrates the verification process by executing registered rules,
aggregating findings, calculating scores, and producing immutable
VerificationReport objects.

Architecture
------------

WorkflowPlan      -->  \
ExecutionPlan     -->  \
EvaluationReport  -->  SelfVerificationEngine  -->  VerificationReport
PatchSet          -->  /
WorkspaceChanges  -->  /

Responsibilities
----------------

- Execute registered verification rules against workspace changes.
- Aggregate findings from all rules.
- Calculate deterministic verification score.
- Calculate verification status from findings.
- Produce immutable VerificationReport.

Non-responsibilities
--------------------

- Must NOT edit files.
- Must NOT generate patches.
- Must NOT invoke providers.
- Must NOT inspect repositories.
- Must NOT execute shell commands.
- Must NOT duplicate evaluation logic.

Public API
----------

.. code-block:: python

    from packages.verification.engine import SelfVerificationEngine

    report = SelfVerificationEngine.verify(
        workflow_plan=workflow_plan,
        execution_plan=execution_plan,
        evaluation_report=evaluation_report,
        patch_set=patch_set,
        workspace_changes=workspace_changes,
    )

"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)
from packages.verification.registry import VerificationRuleRegistry
from packages.verification.rules import (
    NoDuplicateChangesRule,
    NoUnexpectedFilesRule,
    PatchAppliedRule,
    PatchStatisticsConsistencyRule,
    VerificationRule,
    WorkspaceConsistencyRule,
)

if TYPE_CHECKING:
    pass  # No additional imports needed

__all__ = [
    "SelfVerificationEngine",
]

# ---------------------------------------------------------------------------
# Severity Weights (constants)
# ---------------------------------------------------------------------------

# Severity weights define the penalty applied to the verification score
# for each severity level. These are constants — no hidden heuristics.
#
# Penalty scale:
#   - INFO:     0.00 (no penalty)
#   - LOW:      0.05 (minor penalty)
#   - MEDIUM:   0.15 (moderate penalty)
#   - HIGH:     0.30 (significant penalty)
#   - CRITICAL: 0.50 (critical penalty)

SEVERITY_WEIGHTS: dict[str, float] = {
    VerificationSeverity.INFO.value: 0.00,
    VerificationSeverity.LOW.value: 0.05,
    VerificationSeverity.MEDIUM.value: 0.15,
    VerificationSeverity.HIGH.value: 0.30,
    VerificationSeverity.CRITICAL.value: 0.50,
}


# ---------------------------------------------------------------------------
# SelfVerificationEngine
# ---------------------------------------------------------------------------


class SelfVerificationEngine:
    """Self Verification Engine.

    Orchestrates the verification process by executing registered rules,
    aggregating findings, calculating scores, and producing immutable
    VerificationReport objects.

    Usage
    -----

    .. code-block:: python

        from packages.verification.engine import SelfVerificationEngine

        report = SelfVerificationEngine.verify(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
            evaluation_report=evaluation_report,
            patch_set=patch_set,
            workspace_changes=workspace_changes,
        )

    Constraints
    -----------

    - Must NOT edit files.
    - Must NOT generate patches.
    - Must NOT invoke providers.
    - Must NOT inspect repositories.
    - Must NOT execute shell commands.
    - Must NOT duplicate evaluation logic.
    - Must produce deterministic output.
    """

    @staticmethod
    def verify(
        workflow_plan: Any,
        execution_plan: Any,
        evaluation_report: Any,
        patch_set: Any,
        workspace_changes: Any,
    ) -> VerificationReport:
        """Verify engineering execution and produce a VerificationReport.

        This is the main entry point for the SelfVerificationEngine. It
        executes all registered rules, aggregates findings, calculates
        the verification score and status, and returns an immutable
        VerificationReport.

        Args:
            workflow_plan: WorkflowPlan-like object with:
                - workflow_name: str
                - task_plans: tuple
            execution_plan: ExecutionPlan-like object with:
                - workflow_name: str
                - execution_id: str
            evaluation_report: EvaluationReport-like object with:
                - overall_score: float
                - summary: str
            patch_set: PatchSet-like object with:
                - workflow_name: str
                - execution_id: str
                - files: tuple of PatchFile-like objects
            workspace_changes: WorkspaceChanges-like object with:
                - applied_files: tuple of ModifiedFile-like objects
                - statistics: ModificationStatistics-like object
                - success: bool
                - warnings: tuple of warning strings

        Returns:
            An immutable VerificationReport with computed findings and score.
        """
        start_time = time.monotonic()

        # Extract identifiers
        workflow_name = getattr(
            workflow_plan, "workflow_name", "unknown"
        )
        execution_id = getattr(
            workspace_changes, "execution_id", "unknown"
        )

        # Initialize registry and register built-in rules
        registry = SelfVerificationEngine._create_default_registry()

        # Execute all registered rules
        findings: list[VerificationFinding] = []
        statistics = VerificationStatistics()

        sorted_rules = registry.sorted_rules()
        executed_count = 0
        passed_count = 0
        failed_count = 0
        warning_count = 0

        for rule in sorted_rules:
            finding = rule.verify(workspace_changes)
            if finding is not None:
                findings.append(finding)
                executed_count += 1

                # Classify the finding
                if finding.severity == VerificationSeverity.INFO:
                    passed_count += 1
                elif finding.severity in (
                    VerificationSeverity.LOW,
                    VerificationSeverity.MEDIUM,
                ):
                    warning_count += 1
                elif finding.severity in (
                    VerificationSeverity.HIGH,
                    VerificationSeverity.CRITICAL,
                ):
                    failed_count += 1
                else:
                    passed_count += 1

        # Calculate duration
        end_time = time.monotonic()
        duration_ms = int((end_time - start_time) * 1000)

        # Update statistics
        statistics = VerificationStatistics(
            executed_rules=executed_count,
            passed_rules=passed_count,
            failed_rules=failed_count,
            warnings=warning_count,
            duration_ms=duration_ms,
        )

        # Calculate score
        score = SelfVerificationEngine._calculate_score(findings)

        # Calculate status
        status = SelfVerificationEngine._calculate_status(
            findings, failed_count, executed_count
        )

        # Build metadata
        metadata: dict[str, object] = {
            "engine": "SelfVerificationEngine",
            "version": "1.0.0",
            "scoring_algorithm": "weighted_severity_penalty",
        }

        # Add evaluation report metadata if available
        if evaluation_report is not None:
            overall_score = getattr(
                evaluation_report, "overall_score", None
            )
            if overall_score is not None:
                metadata["evaluation_score"] = overall_score

        # Produce immutable report
        report = VerificationReport(
            workflow_name=workflow_name,
            execution_id=execution_id,
            verification_status=status,
            findings=tuple(findings),
            statistics=statistics,
            score=score,
            metadata=metadata,
        )

        return report

    @staticmethod
    def _create_default_registry() -> VerificationRuleRegistry:
        """Create a registry with all built-in rules registered.

        Returns:
            VerificationRuleRegistry with all built-in rules registered.
        """
        registry = VerificationRuleRegistry()

        # Register all built-in rules in deterministic order
        rules: tuple[VerificationRule, ...] = (
            NoDuplicateChangesRule(),
            NoUnexpectedFilesRule(),
            PatchAppliedRule(),
            PatchStatisticsConsistencyRule(),
            WorkspaceConsistencyRule(),
        )

        for rule in rules:
            registry.register(rule)

        return registry

    @staticmethod
    def _calculate_score(findings: list[VerificationFinding]) -> float:
        """Calculate a deterministic verification score.

        Uses weighted severity penalties. Each finding reduces the
        base score of 1.0 by its severity weight.

        Formula:
            score = max(0.0, 1.0 - sum(severity_weight for finding in findings))

        Args:
            findings: List of VerificationFinding objects.

        Returns:
            Score in range [0.0, 1.0].
        """
        score = 1.0

        for finding in findings:
            weight = SEVERITY_WEIGHTS.get(
                finding.severity.value, 0.0
            )
            score -= weight

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, score))

    @staticmethod
    def _calculate_status(
        findings: list[VerificationFinding],
        failed_count: int,
        executed_count: int,
    ) -> VerificationStatus:
        """Calculate the overall verification status.

        Rules:
        - If no rules executed: SKIPPED
        - If any CRITICAL findings: FAILED
        - If any HIGH severity findings: FAILED
        - If any MEDIUM severity findings: WARNING
        - Otherwise: PASSED

        Args:
            findings: List of VerificationFinding objects.
            failed_count: Number of failed rules.
            executed_count: Number of executed rules.

        Returns:
            VerificationStatus value.
        """
        if executed_count == 0:
            return VerificationStatus.SKIPPED

        has_critical = any(
            f.severity == VerificationSeverity.CRITICAL
            for f in findings
        )
        has_high = any(
            f.severity == VerificationSeverity.HIGH
            for f in findings
        )
        has_medium = any(
            f.severity == VerificationSeverity.MEDIUM
            for f in findings
        )

        if has_critical or has_high:
            return VerificationStatus.FAILED
        if has_medium:
            return VerificationStatus.WARNING
        return VerificationStatus.PASSED