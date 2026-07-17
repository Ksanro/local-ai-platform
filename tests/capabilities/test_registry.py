"""Tests for the Capability Registry.

Verifies:
- capability registration
- duplicate registration rejected
- lookup by name
- deterministic ordering
- unregister
- has method
"""

from __future__ import annotations

import pytest

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.registry import CapabilityRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockCapability(Capability):
    """A mock capability for testing registration."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.DEBUG

    def execute(self, query: str, repository_index: object) -> object:
        return None


# ---------------------------------------------------------------------------
# Test: Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for capability registration."""

    def test_register_capability(self) -> None:
        """A capability should be registered successfully."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        assert registry.has("mock")

    def test_registered_capability_lookup(self) -> None:
        """A registered capability should be retrievable by name."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        result = registry.get("mock")
        assert result is MockCapability

    def test_registered_capability_all(self) -> None:
        """all() should return registered capability names."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        names = registry.all()
        assert "mock" in names

    def test_register_multiple_capabilities(self) -> None:
        """Multiple capabilities should be registerable."""
        registry = CapabilityRegistry()

        class AnotherCapability(Capability):
            @property
            def name(self) -> str:
                return "another"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.REVIEW

            def execute(self, query: str, repository_index: object) -> object:
                return None

        registry.register("mock", MockCapability)
        registry.register("another", AnotherCapability)

        assert registry.has("mock")
        assert registry.has("another")
        names = registry.all()
        assert "mock" in names
        assert "another" in names


# ---------------------------------------------------------------------------
# Test: Duplicate Registration Rejected
# ---------------------------------------------------------------------------


class TestDuplicateRegistration:
    """Tests that duplicate registration is rejected."""

    def test_duplicate_registration_raises_value_error(self) -> None:
        """Registering the same name twice should raise ValueError."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("mock", MockCapability)

    def test_duplicate_registration_preserves_original(self) -> None:
        """Duplicate registration should not modify the original."""
        registry = CapabilityRegistry()

        class FirstClass(Capability):
            @property
            def name(self) -> str:
                return "first"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.DEBUG

            def execute(self, query: str, repository_index: object) -> object:
                return None

        class SecondClass(Capability):
            @property
            def name(self) -> str:
                return "second"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.DEBUG

            def execute(self, query: str, repository_index: object) -> object:
                return None

        registry.register("test", FirstClass)

        with pytest.raises(ValueError):
            registry.register("test", SecondClass)

        # Original should be preserved
        assert registry.get("test") is FirstClass


# ---------------------------------------------------------------------------
# Test: Deterministic Ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic registry ordering."""

    def test_all_returns_sorted_names(self) -> None:
        """all() should return names in sorted order."""
        registry = CapabilityRegistry()

        class CapA(Capability):
            @property
            def name(self) -> str:
                return "a"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.DEBUG

            def execute(self, query: str, repository_index: object) -> object:
                return None

        class CapB(Capability):
            @property
            def name(self) -> str:
                return "b"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.DEBUG

            def execute(self, query: str, repository_index: object) -> object:
                return None

        class CapC(Capability):
            @property
            def name(self) -> str:
                return "c"

            @property
            def intent(self) -> PlannerIntent:
                return PlannerIntent.DEBUG

            def execute(self, query: str, repository_index: object) -> object:
                return None

        registry.register("c", CapC)
        registry.register("a", CapA)
        registry.register("b", CapB)

        names = registry.all()
        assert names == ["a", "b", "c"]

    def test_empty_registry_returns_empty_list(self) -> None:
        """An empty registry should return an empty list."""
        registry = CapabilityRegistry()
        assert registry.all() == []


# ---------------------------------------------------------------------------
# Test: Lookup
# ---------------------------------------------------------------------------


class TestLookup:
    """Tests for capability lookup."""

    def test_get_unregistered_returns_none(self) -> None:
        """Getting an unregistered capability should return None."""
        registry = CapabilityRegistry()
        assert registry.get("nonexistent") is None

    def test_has_unregistered_returns_false(self) -> None:
        """Checking for an unregistered capability should return False."""
        registry = CapabilityRegistry()
        assert not registry.has("nonexistent")

    def test_has_registered_returns_true(self) -> None:
        """Checking for a registered capability should return True."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        assert registry.has("mock")


# ---------------------------------------------------------------------------
# Test: Unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    """Tests for capability unregistration."""

    def test_unregister_existing(self) -> None:
        """Unregistering an existing capability should succeed."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        registry.unregister("mock")
        assert not registry.has("mock")

    def test_unregister_nonexistent_raises_key_error(self) -> None:
        """Unregistering a non-existent capability should raise KeyError."""
        registry = CapabilityRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("nonexistent")

    def test_unregister_removes_from_all(self) -> None:
        """Unregistering should remove the capability from all()."""
        registry = CapabilityRegistry()
        registry.register("mock", MockCapability)
        assert "mock" in registry.all()

        registry.unregister("mock")
        assert "mock" not in registry.all()
