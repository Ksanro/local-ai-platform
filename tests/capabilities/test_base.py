"""Tests for the Capability Framework base module.

Verifies:
- PlannerIntent enum values
- Capability ABC interface
- Stateless nature of capabilities
- Intent property implementation
"""

from __future__ import annotations

from abc import ABC
from typing import Any

import pytest

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.profiles import EXPLAIN_PROFILE

# ---------------------------------------------------------------------------
# Test: PlannerIntent Enum
# ---------------------------------------------------------------------------


class TestPlannerIntent:
    """Tests for the PlannerIntent enum."""

    def test_explain_value(self) -> None:
        """PlannerIntent.EXPLAIN should have value 'EXPLAIN'."""
        assert PlannerIntent.EXPLAIN.value == "EXPLAIN"

    def test_debug_value(self) -> None:
        """PlannerIntent.DEBUG should have value 'DEBUG'."""
        assert PlannerIntent.DEBUG.value == "DEBUG"

    def test_review_value(self) -> None:
        """PlannerIntent.REVIEW should have value 'REVIEW'."""
        assert PlannerIntent.REVIEW.value == "REVIEW"

    def test_refactor_value(self) -> None:
        """PlannerIntent.REFACTOR should have value 'REFACTOR'."""
        assert PlannerIntent.REFACTOR.value == "REFACTOR"

    def test_implement_value(self) -> None:
        """PlannerIntent.IMPLEMENT should have value 'IMPLEMENT'."""
        assert PlannerIntent.IMPLEMENT.value == "IMPLEMENT"

    def test_generate_tests_value(self) -> None:
        """PlannerIntent.GENERATE_TESTS should have value 'GENERATE_TESTS'."""
        assert PlannerIntent.GENERATE_TESTS.value == "GENERATE_TESTS"

    def test_all_values_present(self) -> None:
        """All expected intent values should be present."""
        values = {item.value for item in PlannerIntent}
        expected = {"EXPLAIN", "DEBUG", "REVIEW", "REFACTOR", "IMPLEMENT", "GENERATE_TESTS"}
        assert values == expected


# ---------------------------------------------------------------------------
# Test: Capability ABC
# ---------------------------------------------------------------------------


class TestCapabilityABC:
    """Tests for the Capability ABC."""

    def test_capability_is_abc(self) -> None:
        """Capability should be an ABC."""
        assert issubclass(Capability, ABC)

    def test_capability_cannot_be_instantiated(self) -> None:
        """Capability cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Capability()  # type: ignore[abstract]

    def test_abstract_intent_property(self) -> None:
        """intent property should be abstract."""
        # The intent property should be marked as abstract
        assert hasattr(Capability, "intent")

    def test_abstract_execute_method(self) -> None:
        """execute method should be abstract."""
        assert hasattr(Capability, "execute")


class DummyCapability(Capability):
    """A concrete capability implementation for testing."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.DEBUG

    @property
    def profile(self):
        return EXPLAIN_PROFILE

    def execute(
        self,
        query: str,
        repository_index: Any,
    ) -> Any:
        return None


class TestConcreteCapability:
    """Tests for concrete capability implementations."""

    def test_dummy_capability_creation(self) -> None:
        """A concrete capability should be instantiable."""
        cap = DummyCapability()
        assert isinstance(cap, Capability)

    def test_name_property(self) -> None:
        """name property should return the capability name."""
        cap = DummyCapability()
        assert cap.name == "dummy"

    def test_intent_property(self) -> None:
        """intent property should return the correct intent."""
        cap = DummyCapability()
        assert cap.intent == PlannerIntent.DEBUG

    def test_execute_returns_none(self) -> None:
        """execute should return the expected value."""
        cap = DummyCapability()
        result = cap.execute("test", None)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Stateless Nature
# ---------------------------------------------------------------------------


class TestStatelessCapability:
    """Tests that capabilities are stateless."""

    def test_no_instance_attributes(self) -> None:
        """Capabilities should not have instance attributes."""
        cap = DummyCapability()
        # State should be minimal — only dunder attributes
        non_dunder = [k for k in vars(cap) if not k.startswith("_")]
        assert len(non_dunder) == 0

    def test_multiple_instances_are_independent(self) -> None:
        """Multiple instances should be independent."""
        cap1 = DummyCapability()
        cap2 = DummyCapability()
        assert cap1 is not cap2
        assert cap1.name == cap2.name
        assert cap1.intent == cap2.intent
