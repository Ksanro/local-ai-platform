"""Deterministic controller decision logic.

Implements the decision state machine for the Engineering Controller v2.
All decisions are pure functions of their inputs — no randomness, no side effects.

Decision State Machine
----------------------

    Execution Failed ──────────────────→ FAIL
           │
           ▼
    Verification Failed ──────────────→ RETRY (if retries < max)
                                      → FAIL (if retries >= max)
           │
           ▼
    Verification Passed
           │
           ▼
    Evaluation >= threshold ──────────→ COMPLETE
           │
           ▼
    Evaluation < threshold
           │
           ├── Evaluation >= review_threshold → REQUEST_REVIEW
           │
           └── Evaluation < review_threshold → FAIL

Constraints
-----------

- All decisions are deterministic.
- No randomness or non-deterministic behavior.
- No external state dependencies.
- Pure function of inputs.

Public API
----------

.. code-block:: python

    from packages.controller.decision import ControllerDecisionMaker

    report = ControllerDecisionMaker.make_decision(
        config=config,
        execution_report=execution_report,
        verification_report=verification_report,
        evaluation_report=evaluation_report,
        retry_count=retry_count,
        iteration=iteration,
    )

"""

from __future__ import annotations

from datetime import datetime, timezone

from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
    ControllerReport,
)


class ControllerDecisionMaker:
    """Deterministic decision maker for the engineering controller.

    The decision maker evaluates the current state of the engineering
    session and produces a deterministic decision.

    Decision Rules (evaluated in strict order):

    1. If execution failed → FAIL
    2. If verification failed AND retry_count < max_retries → RETRY
    3. If verification failed AND retry_count >= max_retries → FAIL
    4. If evaluation_score >= evaluation_threshold AND verification passed → COMPLETE
    5. If evaluation_score < evaluation_threshold AND evaluation_score >= auto_review_threshold → REQUEST_REVIEW
    6. If evaluation_score < auto_review_threshold → FAIL

    Usage
    -----

    .. code-block:: python

        from packages.controller.models_v2 import ControllerConfig, ControllerDecision

        config = ControllerConfig()

        report = ControllerDecisionMaker.make_decision(
            config=config,
            execution_report=execution_report,
            verification_report=verification_report,
            evaluation_report=evaluation_report,
            retry_count=0,
            iteration=1,
        )

        assert report.decision == ControllerDecision.COMPLETE
    """

    @staticmethod
    def make_decision(
        config: ControllerConfig,
        execution_report: Any,
        verification_report: Any,
        evaluation_report: Any,
        retry_count: int,
        iteration: int,
    ) -> ControllerReport:
        """Make a deterministic controller decision.

        Evaluates the current state and produces a decision report.

        Args:
            config: Controller configuration with thresholds.
            execution_report: Execution report (must have 'success' attribute).
            verification_report: Verification report (must have 'verification_status' and 'score' attributes).
            evaluation_report: Evaluation report (must have 'overall_score' attribute).
            retry_count: Current retry count.
            iteration: Current iteration number (1-based).

        Returns:
            A ControllerReport with the decision and reason.

        Raises:
            ValueError: If required report attributes are missing.
        """
        # Rule 1: Check execution status first
        execution_failed = ControllerDecisionMaker._is_execution_failed(execution_report)
        if execution_failed:
            return ControllerReport(
                decision=ControllerDecision.FAIL,
                reason="Execution failed unrecoverably",
                iteration=iteration,
                retry_count=retry_count,
                evaluation_score=ControllerDecisionMaker._get_evaluation_score(evaluation_report),
                verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
            )

        # Rule 2-3: Check verification status
        verification_failed = ControllerDecisionMaker._is_verification_failed(verification_report)
        if verification_failed:
            if retry_count < config.max_retries:
                return ControllerReport(
                    decision=ControllerDecision.RETRY,
                    reason=f"Verification failed, retry available ({retry_count}/{config.max_retries})",
                    iteration=iteration,
                    retry_count=retry_count,
                    evaluation_score=ControllerDecisionMaker._get_evaluation_score(evaluation_report),
                    verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
                )
            else:
                return ControllerReport(
                    decision=ControllerDecision.FAIL,
                    reason=f"Verification failed, max retries exhausted ({config.max_retries})",
                    iteration=iteration,
                    retry_count=retry_count,
                    evaluation_score=ControllerDecisionMaker._get_evaluation_score(evaluation_report),
                    verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
                )

        # Rules 4-6: Check evaluation score
        eval_score = ControllerDecisionMaker._get_evaluation_score(evaluation_report)

        if eval_score is not None:
            if eval_score >= config.evaluation_threshold:
                return ControllerReport(
                    decision=ControllerDecision.COMPLETE,
                    reason=f"Evaluation score {eval_score:.3f} meets threshold {config.evaluation_threshold}",
                    iteration=iteration,
                    retry_count=retry_count,
                    evaluation_score=eval_score,
                    verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
                )
            elif eval_score >= config.auto_review_threshold:
                return ControllerReport(
                    decision=ControllerDecision.REQUEST_REVIEW,
                    reason=f"Evaluation score {eval_score:.3f} below threshold, requires review",
                    iteration=iteration,
                    retry_count=retry_count,
                    evaluation_score=eval_score,
                    verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
                )
            else:
                return ControllerReport(
                    decision=ControllerDecision.FAIL,
                    reason=f"Evaluation score {eval_score:.3f} below review threshold {config.auto_review_threshold}",
                    iteration=iteration,
                    retry_count=retry_count,
                    evaluation_score=eval_score,
                    verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
                )

        # No evaluation report — if verification passed, COMPLETE
        return ControllerReport(
            decision=ControllerDecision.COMPLETE,
            reason="Verification passed, no evaluation report to contradict completion",
            iteration=iteration,
            retry_count=retry_count,
            evaluation_score=None,
            verification_score=ControllerDecisionMaker._get_verification_score(verification_report),
        )

    @staticmethod
    def _is_execution_failed(execution_report: Any) -> bool:
        """Check if execution report indicates failure.

        Args:
            execution_report: Execution report with 'success' attribute.

        Returns:
            True if execution failed, False otherwise.
        """
        if execution_report is None:
            return False  # No report means we can't determine failure

        success = getattr(execution_report, "success", None)
        if success is None:
            # Try execution_status attribute
            status = getattr(execution_report, "execution_status", None)
            if status is not None:
                status_str = getattr(status, "value", str(status)).upper()
                return status_str in ("FAILED", "ERROR", "FAILURE")
            return False

        if isinstance(success, bool):
            return not success

        # Treat as success if truthy
        return not bool(success)

    @staticmethod
    def _is_verification_failed(verification_report: Any) -> bool:
        """Check if verification report indicates failure.

        Args:
            verification_report: Verification report with 'verification_status' attribute.

        Returns:
            True if verification failed, False otherwise.
        """
        if verification_report is None:
            return False  # No report means we can't determine failure

        status = getattr(verification_report, "verification_status", None)
        if status is None:
            return False

        status_str = getattr(status, "value", str(status)).upper()
        return status_str == "FAILED"

    @staticmethod
    def _get_evaluation_score(evaluation_report: Any) -> float | None:
        """Extract evaluation score from report.

        Args:
            evaluation_report: Evaluation report with 'overall_score' attribute.

        Returns:
            Evaluation score as float, or None if not available.
        """
        if evaluation_report is None:
            return None

        score = getattr(evaluation_report, "overall_score", None)
        if score is None:
            return None

        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get_verification_score(verification_report: Any) -> float | None:
        """Extract verification score from report.

        Args:
            verification_report: Verification report with 'score' attribute.

        Returns:
            Verification score as float, or None if not available.
        """
        if verification_report is None:
            return None

        score = getattr(verification_report, "score", None)
        if score is None:
            return None

        try:
            return float(score)
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Type import for type hints
# ---------------------------------------------------------------------------

from typing import Any  # noqa: E402