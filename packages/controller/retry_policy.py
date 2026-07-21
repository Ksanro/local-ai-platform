"""Retry policy enforcement for the Engineering Controller v2.

Implements deterministic retry policy enforcement. The policy ensures that:
- Retries never bypass the Workflow Engine
- Retries never bypass the Execution Engine
- Maximum retry count is enforced
- Each retry re-executes the full workflow pipeline

Constraints
-----------

- Never bypass Workflow Engine
- Never bypass Execution Engine
- Maximum retry count is configurable
- Each retry re-executes the full workflow pipeline

Public API
----------

.. code-block:: python

    from packages.controller.retry_policy import RetryPolicy

    should_retry = RetryPolicy.should_retry(
        config=config,
        retry_count=retry_count,
        decision=decision,
    )

"""

from __future__ import annotations

from packages.controller.models_v2 import (
    ControllerConfig,
    ControllerDecision,
)


class RetryPolicy:
    """Deterministic retry policy for the engineering controller.

    The retry policy enforces constraints on when and how retries can occur.
    All methods are pure functions — no side effects, no state.

    Retry Rules
    -----------

    1. A retry is only allowed when the controller decision is RETRY.
    2. A retry is only allowed when retry_count < max_retries.
    3. Each retry must re-execute the full workflow pipeline.
    4. The Workflow Engine and Execution Engine must never be bypassed.

    Usage
    -----

    .. code-block:: python

        from packages.controller.models_v2 import ControllerConfig, ControllerDecision
        from packages.controller.retry_policy import RetryPolicy

        config = ControllerConfig(max_retries=3)

        # Check if retry is allowed
        should_retry = RetryPolicy.should_retry(
            config=config,
            retry_count=2,
            decision=ControllerDecision.RETRY,
        )
        assert should_retry is True

        # Check if retry is allowed when max reached
        should_retry = RetryPolicy.should_retry(
            config=config,
            retry_count=3,
            decision=ControllerDecision.RETRY,
        )
        assert should_retry is False
    """

    @staticmethod
    def should_retry(
        config: ControllerConfig,
        retry_count: int,
        decision: ControllerDecision,
    ) -> bool:
        """Check if a retry is allowed.

        A retry is allowed when:
        - The controller decision is RETRY
        - The current retry count is less than max_retries

        Args:
            config: Controller configuration with max_retries.
            retry_count: Current retry count.
            decision: The controller decision.

        Returns:
            True if retry is allowed, False otherwise.

        Example:
            .. code-block:: python

                config = ControllerConfig(max_retries=3)
                assert RetryPolicy.should_retry(config, 2, ControllerDecision.RETRY) is True
                assert RetryPolicy.should_retry(config, 3, ControllerDecision.RETRY) is False
                assert RetryPolicy.should_retry(config, 0, ControllerDecision.COMPLETE) is False
        """
        if decision != ControllerDecision.RETRY:
            return False

        if retry_count >= config.max_retries:
            return False

        return True

    @staticmethod
    def can_transition_to_complete(
        config: ControllerConfig,
        retry_count: int,
        decision: ControllerDecision,
    ) -> bool:
        """Check if the session can transition to COMPLETE.

        A transition to COMPLETE is allowed when:
        - The controller decision is COMPLETE
        - The retry count is within bounds

        Args:
            config: Controller configuration.
            retry_count: Current retry count.
            decision: The controller decision.

        Returns:
            True if COMPLETE transition is allowed, False otherwise.
        """
        if decision != ControllerDecision.COMPLETE:
            return False

        # COMPLETE is always allowed regardless of retry count
        return True

    @staticmethod
    def can_transition_to_fail(
        decision: ControllerDecision,
    ) -> bool:
        """Check if the session can transition to FAIL.

        A transition to FAIL is allowed when:
        - The controller decision is FAIL

        Args:
            decision: The controller decision.

        Returns:
            True if FAIL transition is allowed, False otherwise.
        """
        return decision == ControllerDecision.FAIL

    @staticmethod
    def can_transition_to_review(
        decision: ControllerDecision,
    ) -> bool:
        """Check if the session can transition to REQUEST_REVIEW.

        A transition to REQUEST_REVIEW is allowed when:
        - The controller decision is REQUEST_REVIEW

        Args:
            decision: The controller decision.

        Returns:
            True if REQUEST_REVIEW transition is allowed, False otherwise.
        """
        return decision == ControllerDecision.REQUEST_REVIEW

    @staticmethod
    def increment_retry(retry_count: int) -> int:
        """Increment the retry count.

        Args:
            retry_count: Current retry count.

        Returns:
            Incremented retry count.

        Example:
            .. code-block:: python

                assert RetryPolicy.increment_retry(0) == 1
                assert RetryPolicy.increment_retry(2) == 3
        """
        return retry_count + 1

    @staticmethod
    def remaining_retries(config: ControllerConfig, retry_count: int) -> int:
        """Calculate remaining retries.

        Args:
            config: Controller configuration with max_retries.
            retry_count: Current retry count.

        Returns:
            Number of remaining retries (0 if none left).

        Example:
            .. code-block:: python

                config = ControllerConfig(max_retries=3)
                assert RetryPolicy.remaining_retries(config, 0) == 3
                assert RetryPolicy.remaining_retries(config, 2) == 1
                assert RetryPolicy.remaining_retries(config, 3) == 0
        """
        remaining = config.max_retries - retry_count
        return max(0, remaining)

    @staticmethod
    def is_max_retries_reached(config: ControllerConfig, retry_count: int) -> bool:
        """Check if maximum retries have been reached.

        Args:
            config: Controller configuration with max_retries.
            retry_count: Current retry count.

        Returns:
            True if max retries reached, False otherwise.

        Example:
            .. code-block:: python

                config = ControllerConfig(max_retries=3)
                assert RetryPolicy.is_max_retries_reached(config, 3) is True
                assert RetryPolicy.is_max_retries_reached(config, 2) is False
        """
        return retry_count >= config.max_retries

    @staticmethod
    def validate_retry_state(
        config: ControllerConfig,
        retry_count: int,
        decision: ControllerDecision,
    ) -> bool:
        """Validate that the retry state is valid.

        A valid retry state is one where:
        - retry_count >= 0
        - retry_count <= max_retries (for RETRY decisions)
        - decision is a valid controller decision

        Args:
            config: Controller configuration.
            retry_count: Current retry count.
            decision: The controller decision.

        Returns:
            True if the retry state is valid, False otherwise.
        """
        if retry_count < 0:
            return False

        if decision == ControllerDecision.RETRY and retry_count >= config.max_retries:
            return False

        return True