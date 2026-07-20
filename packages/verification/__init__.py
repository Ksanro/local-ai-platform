"""Self Verification Framework package.

Validates the result of engineering execution and produces deterministic
VerificationReport objects. This framework NEVER modifies code, generates
patches, performs repository intelligence, invokes providers, or repairs
failures.

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
- Produce immutable VerificationReport.
- Validate VerificationReport integrity.

Non-responsibilities
--------------------

- Must NOT modify code.
- Must NOT generate patches.
- Must NOT perform repository intelligence.
- Must NOT invoke providers.
- Must NOT repair failures.
- Must NOT inspect repositories.
- Must NOT execute shell commands.
- Must NOT duplicate evaluation logic.

Public API
----------

.. code-block:: python

    from packages.verification.models import (
        VerificationFinding,
        VerificationReport,
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
    from packages.verification.registry import VerificationRuleRegistry
    from packages.verification.validator import VerificationReportValidator
    from packages.verification.engine import SelfVerificationEngine

"""

from __future__ import annotations

from packages.verification.engine import SelfVerificationEngine
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
from packages.verification.validator import VerificationReportValidator

__all__ = [
    # Engine
    "SelfVerificationEngine",
    # Models
    "VerificationFinding",
    "VerificationReport",
    "VerificationSeverity",
    "VerificationStatus",
    "VerificationStatistics",
    # Registry
    "VerificationRuleRegistry",
    # Rules
    "NoDuplicateChangesRule",
    "NoUnexpectedFilesRule",
    "PatchAppliedRule",
    "PatchStatisticsConsistencyRule",
    "VerificationRule",
    "WorkspaceConsistencyRule",
    # Validator
    "VerificationReportValidator",
]