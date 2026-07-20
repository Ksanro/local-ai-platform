"""Deterministic verification rule registry.

Provides registration, lookup, and deterministic sorted execution of
verification rules. Rules execute in deterministic sorted order by rule_id.

Architecture
------------

Registry --> Rule Registration --> Rule Lookup --> Sorted Execution
Registry --> Duplicate Prevention --> Deterministic Order

Constraints
-----------

- Deterministic sorted order by rule_id.
- No global mutable state.
- No singleton pattern.
- Consume only public APIs.

Public API
----------

.. code-block:: python

    from packages.verification.registry import VerificationRuleRegistry

    registry = VerificationRuleRegistry()
    registry.register(rule)
    rules = registry.sorted_rules()

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.verification.rules import VerificationRule

if TYPE_CHECKING:
    pass  # No additional imports needed

__all__ = [
    "VerificationRuleRegistry",
]


# ---------------------------------------------------------------------------
# VerificationRuleRegistry
# ---------------------------------------------------------------------------


class VerificationRuleRegistry:
    """Deterministic verification rule registry.

    Manages registration, lookup, and deterministic sorted execution
    of verification rules. Rules execute in sorted order by rule_id.

    Usage
    -----

    .. code-block:: python

        from packages.verification.rules import PatchAppliedRule

        registry = VerificationRuleRegistry()
        registry.register(PatchAppliedRule())
        rules = registry.sorted_rules()

    Constraints
    -----------

    - Rules execute in deterministic sorted order by rule_id.
    - Duplicate registrations are silently ignored.
    - No global mutable state.
    - Thread-safe for read operations after registration is complete.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._rules: dict[str, VerificationRule] = {}

    def register(self, rule: VerificationRule) -> None:
        """Register a verification rule.

        Duplicate registrations are silently ignored — the original
        registration is preserved.

        Args:
            rule: VerificationRule-like object to register.
        """
        rule_id = rule.rule_id
        if rule_id in self._rules:
            return  # Duplicate — ignore silently
        self._rules[rule_id] = rule

    def unregister(self, rule_id: str) -> None:
        """Unregister a verification rule by ID.

        Args:
            rule_id: Unique identifier of the rule to unregister.
        """
        self._rules.pop(rule_id, None)

    def get(self, rule_id: str) -> VerificationRule | None:
        """Look up a registered rule by ID.

        Args:
            rule_id: Unique identifier of the rule to look up.

        Returns:
            VerificationRule-like object, or None if not found.
        """
        return self._rules.get(rule_id)

    def all(self) -> tuple[VerificationRule, ...]:
        """Get all registered rules in insertion order.

        Returns:
            Tuple of all registered VerificationRule objects.
        """
        return tuple(self._rules.values())

    def sorted_rules(self) -> tuple[VerificationRule, ...]:
        """Get all registered rules in deterministic sorted order by rule_id.

        Returns:
            Tuple of all registered VerificationRule objects sorted by rule_id.
        """
        return tuple(
            self._rules[rule_id]
            for rule_id in sorted(self._rules.keys())
        )

    def clear(self) -> None:
        """Remove all registered rules.

        This is primarily used in tests to ensure isolation between
        test cases. Do not call in production code.
        """
        self._rules.clear()

    @property
    def count(self) -> int:
        """Number of registered rules.

        Returns:
            Integer count of registered rules.
        """
        return len(self._rules)