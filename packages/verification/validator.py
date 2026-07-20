"""Verification report validation.

Validates VerificationReport objects for integrity. Validation never
mutates the report — it produces a tuple of (is_valid, errors).

Architecture
------------

VerificationReport --> VerificationReportValidator --> (is_valid, errors)

Constraints
-----------

- Validation only.
- Must NOT mutate VerificationReport.
- No file system operations.
- No repository inspection.
- Deterministic output.

Public API
----------

.. code-block:: python

    from packages.verification.validator import VerificationReportValidator

    is_valid, errors = VerificationReportValidator.validate(report)

"""

from __future__ import annotations

from typing import Any

from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)

__all__ = [
    "VerificationReportValidator",
]


# ---------------------------------------------------------------------------
# VerificationReportValidator
# ---------------------------------------------------------------------------


class VerificationReportValidator:
    """Validates VerificationReport objects for integrity.

    The validator checks VerificationReport against defined rules and
    produces a validation result. It never mutates the report.

    Constraints
    -----------

    - Validation only.
    - Must NOT mutate VerificationReport.
    - No file system operations.
    - No repository inspection.
    - Must produce deterministic output.

    Validation Rules
    ----------------

    1. Duplicate findings: No two findings with the same ID.
    2. Invalid score: Score must be in range [0.0, 1.0].
    3. Invalid status: Status must be a valid VerificationStatus value.
    4. Invalid statistics: Statistics must match findings count.
    5. Inconsistent metadata: Metadata must be a dict.

    Usage
    -----

    .. code-block:: python

        from packages.verification.validator import VerificationReportValidator

        is_valid, errors = VerificationReportValidator.validate(report)
        if not is_valid:
            print(f"Validation errors: {errors}")

    """

    @staticmethod
    def validate(report: Any) -> tuple[bool, list[str]]:
        """Validate a VerificationReport and return validation result.

        Checks all validation rules and returns a tuple of
        (is_valid, errors) found.

        Args:
            report: VerificationReport-like object with:
                - findings: tuple of VerificationFinding-like objects
                - score: float
                - verification_status: VerificationStatus-like value
                - statistics: VerificationStatistics-like object
                - metadata: dict

        Returns:
            Tuple of (is_valid, errors) where errors is a list of
            error message strings.
        """
        if report is None:
            return False, ["Report cannot be None"]

        errors: list[str] = []

        # Extract fields
        findings = getattr(report, "findings", ())
        score = getattr(report, "score", None)
        status = getattr(report, "verification_status", None)
        statistics = getattr(report, "statistics", None)
        metadata = getattr(report, "metadata", None)

        # Run all validations
        errors.extend(_validate_duplicate_findings(findings))
        errors.extend(_validate_invalid_score(score))
        errors.extend(_validate_invalid_status(status))
        errors.extend(_validate_invalid_statistics(statistics, findings))
        errors.extend(_validate_inconsistent_metadata(metadata))

        return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Internal Validation Rule Functions
# ---------------------------------------------------------------------------


def _validate_duplicate_findings(
    findings: tuple[Any, ...],
) -> list[str]:
    """Check for duplicate finding IDs.

    Args:
        findings: Tuple of VerificationFinding-like objects.

    Returns:
        List of error messages for duplicate findings found.
    """
    errors: list[str] = []
    seen_ids: dict[str, int] = {}

    for idx, finding in enumerate(findings):
        finding_id = getattr(finding, "id", "")
        if finding_id in seen_ids:
            errors.append(
                f"Duplicate finding ID: '{finding_id}' "
                f"(first at index {seen_ids[finding_id]}, "
                f"duplicate at index {idx})"
            )
        seen_ids[finding_id] = idx

    return errors


def _validate_invalid_score(
    score: Any,
) -> list[str]:
    """Check for invalid score value.

    Args:
        score: Score value to validate.

    Returns:
        List of error messages for invalid scores found.
    """
    errors: list[str] = []

    if score is None:
        errors.append("Score is None")
        return errors

    if not isinstance(score, (int, float)):
        errors.append(
            f"Score must be a number, got {type(score).__name__}"
        )
        return errors

    score_value = float(score)
    if score_value < 0.0 or score_value > 1.0:
        errors.append(
            f"Score must be in range [0.0, 1.0], got {score_value}"
        )

    return errors


def _validate_invalid_status(
    status: Any,
) -> list[str]:
    """Check for invalid verification status.

    Args:
        status: Status value to validate.

    Returns:
        List of error messages for invalid status found.
    """
    errors: list[str] = []

    if status is None:
        errors.append("Verification status is None")
        return errors

    # Check if it's a valid VerificationStatus value
    valid_statuses = {
        VerificationStatus.PASSED.value,
        VerificationStatus.FAILED.value,
        VerificationStatus.WARNING.value,
        VerificationStatus.SKIPPED.value,
    }

    status_value: str
    if hasattr(status, "value"):
        status_value = status.value
    else:
        status_value = str(status)

    if status_value not in valid_statuses:
        errors.append(
            f"Invalid verification status: '{status_value}'. "
            f"Valid values: {', '.join(sorted(valid_statuses))}"
        )

    return errors


def _validate_invalid_statistics(
    statistics: Any,
    findings: tuple[Any, ...],
) -> list[str]:
    """Check for invalid statistics values.

    Args:
        statistics: Statistics object to validate.
        findings: Tuple of findings to cross-check.

    Returns:
        List of error messages for invalid statistics found.
    """
    errors: list[str] = []

    if statistics is None:
        errors.append("Statistics is None")
        return errors

    executed_rules = getattr(statistics, "executed_rules", None)
    passed_rules = getattr(statistics, "passed_rules", None)
    failed_rules = getattr(statistics, "failed_rules", None)
    warnings = getattr(statistics, "warnings", None)
    duration_ms = getattr(statistics, "duration_ms", None)

    if executed_rules is None:
        errors.append("executed_rules is None")
    elif executed_rules < 0:
        errors.append(f"executed_rules must be >= 0, got {executed_rules}")

    if passed_rules is None:
        errors.append("passed_rules is None")
    elif passed_rules < 0:
        errors.append(f"passed_rules must be >= 0, got {passed_rules}")

    if failed_rules is None:
        errors.append("failed_rules is None")
    elif failed_rules < 0:
        errors.append(f"failed_rules must be >= 0, got {failed_rules}")

    if warnings is None:
        errors.append("warnings is None")
    elif warnings < 0:
        errors.append(f"warnings must be >= 0, got {warnings}")

    if duration_ms is None:
        errors.append("duration_ms is None")
    elif duration_ms < 0:
        errors.append(f"duration_ms must be >= 0, got {duration_ms}")

    # Cross-check: executed_rules should equal passed + failed + warnings
    if (
        executed_rules is not None
        and passed_rules is not None
        and failed_rules is not None
        and warnings is not None
    ):
        expected = passed_rules + failed_rules + warnings
        if executed_rules != expected:
            errors.append(
                f"executed_rules ({executed_rules}) != "
                f"passed ({passed_rules}) + failed ({failed_rules}) + "
                f"warnings ({warnings}) = {expected}"
            )

    return errors


def _validate_inconsistent_metadata(
    metadata: Any,
) -> list[str]:
    """Check for inconsistent metadata.

    Args:
        metadata: Metadata value to validate.

    Returns:
        List of error messages for inconsistent metadata found.
    """
    errors: list[str] = []

    if metadata is None:
        errors.append("Metadata is None")
        return errors

    if not isinstance(metadata, dict):
        errors.append(
            f"Metadata must be a dict, got {type(metadata).__name__}"
        )

    return errors