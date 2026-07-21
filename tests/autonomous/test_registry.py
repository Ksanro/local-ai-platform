"""Tests for autonomous policy registry.

Tests cover:
- Registry operations
- Deterministic ordering
- Duplicate handling
- Edge cases
"""

from __future__ import annotations

import pytest

from packages.autonomous.policy import (
    MaximumIterationPolicy,
    PolicyDecision,
    PolicyResult,
    SequentialPolicy,
    StopOnFailurePolicy,
    VerificationGatePolicy,
)
from packages.autonomous.registry import AutonomousPolicyRegistry


# ---------------------------------------------------------------------------
# AutonomousPolicyRegistry
# ---------------------------------------------------------------------------


class TestAutonomousPolicyRegistry:
    """Tests for AutonomousPolicyRegistry."""

    def setup_method(self) -> None:
        """Clear registry before each test."""
        self.registry = AutonomousPolicyRegistry()

    def test_empty_registry(self) -> None:
        registry = AutonomousPolicyRegistry()
        assert registry.count == 0
        assert registry.all() == ()
        assert registry.sorted_policies() == ()

    def test_register_single_policy(self) -> None:
        policy = SequentialPolicy()
        self.registry.register(policy)
        assert self.registry.count == 1
        assert self.registry.all() == (policy,)

    def test_register_multiple_policies(self) -> None:
        p1 = SequentialPolicy()
        p2 = StopOnFailurePolicy()
        p3 = MaximumIterationPolicy()

        self.registry.register(p1)
        self.registry.register(p2)
        self.registry.register(p3)

        assert self.registry.count == 3
        assert len(self.registry.all()) == 3

    def test_duplicate_registration_ignored(self) -> None:
        policy = SequentialPolicy()
        self.registry.register(policy)
        self.registry.register(policy)  # Duplicate

        assert self.registry.count == 1
        assert self.registry.all() == (policy,)

    def test_get_registered_policy(self) -> None:
        policy = SequentialPolicy()
        self.registry.register(policy)

        result = self.registry.get("SequentialPolicy")
        assert result is policy

    def test_get_unregistered_policy(self) -> None:
        result = self.registry.get("NonExistentPolicy")
        assert result is None

    def test_unregister_existing(self) -> None:
        policy = SequentialPolicy()
        self.registry.register(policy)
        self.registry.unregister("SequentialPolicy")

        assert self.registry.count == 0
        assert self.registry.get("SequentialPolicy") is None

    def test_unregister_nonexistent(self) -> None:
        # Should not raise
        self.registry.unregister("NonExistentPolicy")
        assert self.registry.count == 0

    def test_sorted_policies(self) -> None:
        p1 = MaximumIterationPolicy()
        p2 = SequentialPolicy()
        p3 = StopOnFailurePolicy()
        p4 = VerificationGatePolicy()

        # Register in non-sorted order
        self.registry.register(p3)
        self.registry.register(p1)
        self.registry.register(p4)
        self.registry.register(p2)

        sorted_policies = self.registry.sorted_policies()
        policy_ids = [p.policy_id for p in sorted_policies]

        # Should be sorted alphabetically
        assert policy_ids == sorted(policy_ids)

    def test_sorted_policies_empty(self) -> None:
        assert self.registry.sorted_policies() == ()

    def test_clear(self) -> None:
        self.registry.register(SequentialPolicy())
        self.registry.register(StopOnFailurePolicy())
        assert self.registry.count == 2

        self.registry.clear()
        assert self.registry.count == 0
        assert self.registry.all() == ()

    def test_all_returns_insertion_order(self) -> None:
        p1 = SequentialPolicy()
        p2 = StopOnFailurePolicy()

        self.registry.register(p1)
        self.registry.register(p2)

        all_policies = self.registry.all()
        assert all_policies[0].policy_id == "SequentialPolicy"
        assert all_policies[1].policy_id == "StopOnFailurePolicy"

    def test_mixed_registration_types(self) -> None:
        """Test that different policy types can be registered together."""
        policies = [
            SequentialPolicy(),
            StopOnFailurePolicy(),
            MaximumIterationPolicy(),
            VerificationGatePolicy(),
        ]

        for policy in policies:
            self.registry.register(policy)

        assert self.registry.count == 4
        assert len(self.registry.sorted_policies()) == 4


class TestPolicyLookup:
    """Tests for policy lookup operations."""

    def test_get_by_policy_id(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)

        result = registry.get("SequentialPolicy")
        assert result is policy

    def test_get_by_wrong_id(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)

        result = registry.get("WrongPolicyId")
        assert result is None

    def test_multiple_gets(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)

        # Multiple gets should return the same object
        result1 = registry.get("SequentialPolicy")
        result2 = registry.get("SequentialPolicy")

        assert result1 is result2
        assert result1 is policy


class TestPolicyRemoval:
    """Tests for policy removal operations."""

    def test_unregister_after_get(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)

        # Get should work
        assert registry.get("SequentialPolicy") is policy

        # Unregister
        registry.unregister("SequentialPolicy")

        # Get should return None
        assert registry.get("SequentialPolicy") is None

    def test_unregister_then_register_again(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy1 = SequentialPolicy()
        registry.register(policy1)
        registry.unregister("SequentialPolicy")

        policy2 = StopOnFailurePolicy()
        registry.register(policy2)

        assert registry.count == 1
        result = registry.get("StopOnFailurePolicy")
        assert result is policy2


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_register_same_policy_twice(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()

        registry.register(policy)
        registry.register(policy)

        assert registry.count == 1

    def test_unregister_all_then_check(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)
        registry.unregister("SequentialPolicy")

        assert registry.count == 0
        assert registry.all() == ()
        assert registry.sorted_policies() == ()

    def test_clear_then_check(self) -> None:
        registry = AutonomousPolicyRegistry()
        policy = SequentialPolicy()
        registry.register(policy)
        registry.clear()

        assert registry.count == 0
        assert registry.all() == ()
        assert registry.sorted_policies() == ()
        assert registry.get("SequentialPolicy") is None