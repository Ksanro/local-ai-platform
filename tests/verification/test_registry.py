"""Tests for verification rule registry.

Verifies:
- Registration
- Lookup
- Duplicate prevention
- Sorted order
- Empty registry
- Coverage >95%

"""

from __future__ import annotations

import pytest

from packages.verification.models import VerificationFinding, VerificationSeverity
from packages.verification.rules import VerificationRule
from packages.verification.registry import VerificationRuleRegistry


# ---------------------------------------------------------------------------
# Mock Rule for testing
# ---------------------------------------------------------------------------


class MockRule(VerificationRule):
    """Mock rule for testing."""

    def __init__(self, rule_id: str = "mock-rule") -> None:
        self._rule_id = rule_id

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def category(self) -> str:
        return "mock"

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.INFO

    def verify(self, workspace_changes: object) -> VerificationFinding | None:
        return None


class MockRuleWithSeverity(VerificationRule):
    """Mock rule with MEDIUM severity for testing."""

    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(self, workspace_changes: object) -> VerificationFinding | None:
        return None


# ---------------------------------------------------------------------------
# Test: Registry Initialization
# ---------------------------------------------------------------------------


class TestRegistryInitialization:
    """Tests for registry initialization."""

    def test_empty_registry(self) -> None:
        """Registry should start empty."""
        registry = VerificationRuleRegistry()
        assert registry.count == 0
        assert registry.all() == ()
        assert registry.sorted_rules() == ()

    def test_registry_count_is_zero(self) -> None:
        """Registry count should be zero initially."""
        registry = VerificationRuleRegistry()
        assert registry.count == 0


# ---------------------------------------------------------------------------
# Test: Rule Registration
# ---------------------------------------------------------------------------


class TestRuleRegistration:
    """Tests for rule registration."""

    def test_register_single_rule(self) -> None:
        """Should register a single rule."""
        registry = VerificationRuleRegistry()
        rule = MockRule()
        registry.register(rule)
        assert registry.count == 1

    def test_register_multiple_rules(self) -> None:
        """Should register multiple rules."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-b")
        rule3 = MockRule(rule_id="rule-c")
        registry.register(rule1)
        registry.register(rule2)
        registry.register(rule3)
        assert registry.count == 3

    def test_register_duplicate_rule(self) -> None:
        """Duplicate registrations should be silently ignored."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-a")  # Same ID
        registry.register(rule1)
        registry.register(rule2)
        assert registry.count == 1

    def test_register_preserves_original(self) -> None:
        """Registering duplicate should preserve the original."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-a")
        registry.register(rule1)
        registry.register(rule2)
        assert registry.get("rule-a") is rule1

    def test_register_different_ids(self) -> None:
        """Should register rules with different IDs."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-b")
        registry.register(rule1)
        registry.register(rule2)
        assert registry.count == 2
        assert registry.get("rule-a") is rule1
        assert registry.get("rule-b") is rule2


# ---------------------------------------------------------------------------
# Test: Rule Lookup
# ---------------------------------------------------------------------------


class TestRuleLookup:
    """Tests for rule lookup."""

    def test_get_existing_rule(self) -> None:
        """Should return existing rule by ID."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="rule-a")
        registry.register(rule)
        assert registry.get("rule-a") is rule

    def test_get_nonexistent_rule(self) -> None:
        """Should return None for nonexistent rule."""
        registry = VerificationRuleRegistry()
        assert registry.get("nonexistent") is None

    def test_all_returns_all_rules(self) -> None:
        """Should return all registered rules."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-b")
        registry.register(rule1)
        registry.register(rule2)
        all_rules = registry.all()
        assert len(all_rules) == 2
        assert rule1 in all_rules
        assert rule2 in all_rules


# ---------------------------------------------------------------------------
# Test: Sorted Order
# ---------------------------------------------------------------------------


class TestSortedOrder:
    """Tests for deterministic sorted order."""

    def test_sorted_rules_returns_sorted(self) -> None:
        """sorted_rules should return rules in sorted order."""
        registry = VerificationRuleRegistry()
        rule_c = MockRule(rule_id="rule-c")
        rule_a = MockRule(rule_id="rule-a")
        rule_b = MockRule(rule_id="rule-b")
        registry.register(rule_c)
        registry.register(rule_a)
        registry.register(rule_b)
        sorted_rules = registry.sorted_rules()
        ids = [r.rule_id for r in sorted_rules]
        assert ids == ["rule-a", "rule-b", "rule-c"]

    def test_sorted_order_is_deterministic(self) -> None:
        """Sorted order should be deterministic."""
        registry = VerificationRuleRegistry()
        rule_z = MockRule(rule_id="rule-z")
        rule_m = MockRule(rule_id="rule-m")
        rule_a = MockRule(rule_id="rule-a")
        registry.register(rule_z)
        registry.register(rule_m)
        registry.register(rule_a)
        # Multiple calls should return same order
        order1 = registry.sorted_rules()
        order2 = registry.sorted_rules()
        assert [r.rule_id for r in order1] == [r.rule_id for r in order2]

    def test_empty_sorted_rules(self) -> None:
        """Sorted rules should be empty for empty registry."""
        registry = VerificationRuleRegistry()
        assert registry.sorted_rules() == ()


# ---------------------------------------------------------------------------
# Test: Unregistration
# ---------------------------------------------------------------------------


class TestUnregistration:
    """Tests for rule unregistration."""

    def test_unregister_existing_rule(self) -> None:
        """Should unregister an existing rule."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="rule-a")
        registry.register(rule)
        registry.unregister("rule-a")
        assert registry.count == 0
        assert registry.get("rule-a") is None

    def test_unregister_nonexistent_rule(self) -> None:
        """Unregister should not fail for nonexistent rule."""
        registry = VerificationRuleRegistry()
        registry.unregister("nonexistent")  # Should not raise
        assert registry.count == 0

    def test_unregister_reduces_count(self) -> None:
        """Unregister should reduce count."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-b")
        registry.register(rule1)
        registry.register(rule2)
        registry.unregister("rule-a")
        assert registry.count == 1


# ---------------------------------------------------------------------------
# Test: Clear
# ---------------------------------------------------------------------------


class TestClear:
    """Tests for registry clear."""

    def test_clear_removes_all_rules(self) -> None:
        """Clear should remove all rules."""
        registry = VerificationRuleRegistry()
        rule1 = MockRule(rule_id="rule-a")
        rule2 = MockRule(rule_id="rule-b")
        registry.register(rule1)
        registry.register(rule2)
        registry.clear()
        assert registry.count == 0
        assert registry.all() == ()

    def test_clear_on_empty_registry(self) -> None:
        """Clear should not fail on empty registry."""
        registry = VerificationRuleRegistry()
        registry.clear()  # Should not raise
        assert registry.count == 0


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_register_same_rule_twice(self) -> None:
        """Registering the same rule instance twice should be handled."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="rule-a")
        registry.register(rule)
        registry.register(rule)
        assert registry.count == 1

    def test_registry_with_many_rules(self) -> None:
        """Registry should handle many rules."""
        registry = VerificationRuleRegistry()
        for i in range(100):
            registry.register(MockRule(rule_id=f"rule-{i:03d}"))
        assert registry.count == 100
        sorted_rules = registry.sorted_rules()
        assert len(sorted_rules) == 100
        ids = [r.rule_id for r in sorted_rules]
        assert ids == sorted(ids)

    def test_registry_rule_ids_are_strings(self) -> None:
        """All rule IDs should be strings."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="test-rule")
        registry.register(rule)
        all_rules = registry.all()
        for r in all_rules:
            assert isinstance(r.rule_id, str)

    def test_registry_all_returns_tuple(self) -> None:
        """all() should return a tuple."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="test-rule")
        registry.register(rule)
        result = registry.all()
        assert isinstance(result, tuple)

    def test_registry_sorted_returns_tuple(self) -> None:
        """sorted_rules() should return a tuple."""
        registry = VerificationRuleRegistry()
        rule = MockRule(rule_id="test-rule")
        registry.register(rule)
        result = registry.sorted_rules()
        assert isinstance(result, tuple)