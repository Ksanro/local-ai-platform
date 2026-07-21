"""Deterministic policy registry.

Provides registration, lookup, and deterministic sorted execution of
autonomous policies. Policies execute in deterministic sorted order by
policy_id.

Architecture
------------

Registry --> Policy Registration --> Policy Lookup --> Sorted Execution
Registry --> Duplicate Prevention --> Deterministic Order

Constraints
-----------

- Deterministic sorted order by policy_id.
- No global mutable state.
- No singleton pattern.
- Consume only public APIs.

Public API
----------

.. code-block:: python

    from packages.autonomous.registry import AutonomousPolicyRegistry

    registry = AutonomousPolicyRegistry()
    registry.register(policy)
    policies = registry.sorted_policies()

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.autonomous.policy import Policy

if TYPE_CHECKING:
    pass  # No additional imports needed

__all__ = [
    "AutonomousPolicyRegistry",
]


# ---------------------------------------------------------------------------
# AutonomousPolicyRegistry
# ---------------------------------------------------------------------------


class AutonomousPolicyRegistry:
    """Deterministic policy registry.

    Manages registration, lookup, and deterministic sorted execution
    of autonomous policies. Policies execute in sorted order by policy_id.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.policy import SequentialPolicy

        registry = AutonomousPolicyRegistry()
        registry.register(SequentialPolicy())
        policies = registry.sorted_policies()

    Constraints
    -----------

    - Policies execute in deterministic sorted order by policy_id.
    - Duplicate registrations are silently ignored — the original
      registration is preserved.
    - No global mutable state.
    - Thread-safe for read operations after registration is complete.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._policies: dict[str, Policy] = {}

    def register(self, policy: Policy) -> None:
        """Register a policy.

        Duplicate registrations are silently ignored — the original
        registration is preserved.

        Args:
            policy: Policy-like object to register.
        """
        policy_id = policy.policy_id
        if policy_id in self._policies:
            return  # Duplicate — ignore silently
        self._policies[policy_id] = policy

    def unregister(self, policy_id: str) -> None:
        """Unregister a policy by ID.

        Args:
            policy_id: Unique identifier of the policy to unregister.
        """
        self._policies.pop(policy_id, None)

    def get(self, policy_id: str) -> Policy | None:
        """Look up a registered policy by ID.

        Args:
            policy_id: Unique identifier of the policy to look up.

        Returns:
            Policy-like object, or None if not found.
        """
        return self._policies.get(policy_id)

    def all(self) -> tuple[Policy, ...]:
        """Get all registered policies in insertion order.

        Returns:
            Tuple of all registered Policy objects.
        """
        return tuple(self._policies.values())

    def sorted_policies(self) -> tuple[Policy, ...]:
        """Get all registered policies in deterministic sorted order by policy_id.

        Returns:
            Tuple of all registered Policy objects sorted by policy_id.
        """
        return tuple(
            self._policies[policy_id]
            for policy_id in sorted(self._policies.keys())
        )

    def clear(self) -> None:
        """Remove all registered policies.

        This is primarily used in tests to ensure isolation between
        test cases. Do not call in production code.
        """
        self._policies.clear()

    @property
    def count(self) -> int:
        """Number of registered policies.

        Returns:
            Integer count of registered policies.
        """
        return len(self._policies)