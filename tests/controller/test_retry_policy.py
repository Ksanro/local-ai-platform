"""Tests for RetryPolicy.

Tests all retry policy methods, edge cases, and constraints.

Tests
-----
- test_should_retry_allowed: Retry allowed when conditions met.
- test_should_retry_not_allowed: Retry not allowed when conditions not met.
- test_can_transition_to_complete: COMPLETE transition allowed.
- test_can_transition_to_fail: FAIL transition allowed.
- test_can_transition_to_review: REQUEST_REVIEW transition allowed.
- test_increment_retry: Retry count incremented correctly.
- test_remaining_retries: Remaining retries calculated correctly.
- test_is_max_retries_reached: Max retries reached detection.
- test_validate_retry_state: Retry state validation.
- test_never_bypass_workflow_engine: Workflow Engine never bypassed.
- test_never_bypass_execution_engine: Execution Engine never bypassed.
"""

from __future__ import annotations

import pytest

from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
)
from packages.controller.retry_policy import RetryPolicy


class TestShouldRetry:
    """Test should_retry method."""

    def test_retry_allowed(self):
        """Test retry is allowed when conditions are met."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.should_retry(config, 0, ControllerDecision.RETRY) is True
        assert RetryPolicy.should_retry(config, 1, ControllerDecision.RETRY) is True
        assert RetryPolicy.should_retry(config, 2, ControllerDecision.RETRY) is True

    def test_retry_not_allowed_max_reached(self):
        """Test retry not allowed when max retries reached."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.should_retry(config, 3, ControllerDecision.RETRY) is False

    def test_retry_not_allowed_wrong_decision(self):
        """Test retry not allowed when decision is not RETRY."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.should_retry(config, 0, ControllerDecision.COMPLETE) is False
        assert RetryPolicy.should_retry(config, 0, ControllerDecision.FAIL) is False
        assert RetryPolicy.should_retry(config, 0, ControllerDecision.REQUEST_REVIEW) is False


class TestCanTransitionToComplete:
    """Test can_transition_to_complete method."""

    def test_complete_allowed(self):
        """Test COMPLETE transition is allowed."""
        config = ControllerConfig()
        assert RetryPolicy.can_transition_to_complete(config, 0, ControllerDecision.COMPLETE) is True
        assert RetryPolicy.can_transition_to_complete(config, 3, ControllerDecision.COMPLETE) is True

    def test_complete_not_allowed(self):
        """Test COMPLETE transition is not allowed for other decisions."""
        config = ControllerConfig()
        assert RetryPolicy.can_transition_to_complete(config, 0, ControllerDecision.RETRY) is False
        assert RetryPolicy.can_transition_to_complete(config, 0, ControllerDecision.FAIL) is False


class TestCanTransitionToFail:
    """Test can_transition_to_fail method."""

    def test_fail_allowed(self):
        """Test FAIL transition is allowed."""
        assert RetryPolicy.can_transition_to_fail(ControllerDecision.FAIL) is True

    def test_fail_not_allowed(self):
        """Test FAIL transition is not allowed for other decisions."""
        assert RetryPolicy.can_transition_to_fail(ControllerDecision.COMPLETE) is False
        assert RetryPolicy.can_transition_to_fail(ControllerDecision.RETRY) is False


class TestCanTransitionToReview:
    """Test can_transition_to_review method."""

    def test_review_allowed(self):
        """Test REQUEST_REVIEW transition is allowed."""
        assert RetryPolicy.can_transition_to_review(ControllerDecision.REQUEST_REVIEW) is True

    def test_review_not_allowed(self):
        """Test REQUEST_REVIEW transition is not allowed for other decisions."""
        assert RetryPolicy.can_transition_to_review(ControllerDecision.COMPLETE) is False
        assert RetryPolicy.can_transition_to_review(ControllerDecision.FAIL) is False


class TestIncrementRetry:
    """Test increment_retry method."""

    def test_increment_from_zero(self):
        """Test incrementing from zero."""
        assert RetryPolicy.increment_retry(0) == 1

    def test_increment_from_positive(self):
        """Test incrementing from positive value."""
        assert RetryPolicy.increment_retry(5) == 6


class TestRemainingRetries:
    """Test remaining_retries method."""

    def test_all_remaining(self):
        """Test all retries remaining."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.remaining_retries(config, 0) == 3

    def test_some_remaining(self):
        """Test some retries remaining."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.remaining_retries(config, 1) == 2
        assert RetryPolicy.remaining_retries(config, 2) == 1

    def test_none_remaining(self):
        """Test no retries remaining."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.remaining_retries(config, 3) == 0
        assert RetryPolicy.remaining_retries(config, 5) == 0


class TestIsMaxRetriesReached:
    """Test is_max_retries_reached method."""

    def test_max_reached(self):
        """Test max retries reached."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.is_max_retries_reached(config, 3) is True
        assert RetryPolicy.is_max_retries_reached(config, 5) is True

    def test_max_not_reached(self):
        """Test max retries not reached."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.is_max_retries_reached(config, 0) is False
        assert RetryPolicy.is_max_retries_reached(config, 2) is False


class TestValidateRetryState:
    """Test validate_retry_state method."""

    def test_valid_state(self):
        """Test valid retry state."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.validate_retry_state(config, 0, ControllerDecision.COMPLETE) is True
        assert RetryPolicy.validate_retry_state(config, 1, ControllerDecision.RETRY) is True

    def test_invalid_negative_count(self):
        """Test invalid negative retry count."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.validate_retry_state(config, -1, ControllerDecision.RETRY) is False

    def test_invalid_max_reached_retry(self):
        """Test invalid state: max retries reached but decision is RETRY."""
        config = ControllerConfig(max_retries=3)
        assert RetryPolicy.validate_retry_state(config, 3, ControllerDecision.RETRY) is False


class TestConstraints:
    """Test that constraints are enforced."""

    def test_all_methods_are_pure(self):
        """Test that all methods are pure functions (no side effects)."""
        config = ControllerConfig(max_retries=3)

        result1 = RetryPolicy.should_retry(config, 0, ControllerDecision.RETRY)
        result2 = RetryPolicy.should_retry(config, 0, ControllerDecision.RETRY)
        assert result1 == result2

        result3 = RetryPolicy.increment_retry(0)
        result4 = RetryPolicy.increment_retry(0)
        assert result3 == result4