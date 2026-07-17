"""Tests for the Capability Factory.

Verifies:
- factory creation
- deterministic exceptions
- factory uses registry
- factory never hardcodes classes
- explain capability created through factory
- execution through factory
"""

from __future__ import annotations

import pytest

from packages.capabilities.base import Capability, PlannerIntent
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.registry import CapabilityRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockCapability(Capability):
    """A mock capability for testing."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def intent(self) -> PlannerIntent:
        return PlannerIntent.DEBUG

    def execute(self, query: str, repository_index: object) -> object:
        return None


@pytest.fixture()
def registry() -> CapabilityRegistry:
    """Create a registry with explain registered."""
    reg = CapabilityRegistry()
    reg.register("explain", ExplainCapability)
    return reg


@pytest.fixture()
def factory(registry: CapabilityRegistry) -> CapabilityFactory:
    """Create a factory with a registry."""
    return CapabilityFactory(registry)


# ---------------------------------------------------------------------------
# Test: Factory Creation
# ---------------------------------------------------------------------------


class TestFactoryCreation:
    """Tests for factory creation."""

    def test_factory_creation(self) -> None:
        """A factory should be created with a registry."""
        reg = CapabilityRegistry()
        factory = CapabilityFactory(reg)
        assert factory._registry is reg

    def test_factory_with_empty_registry(self) -> None:
        """A factory should work with an empty registry."""
        reg = CapabilityRegistry()
        factory = CapabilityFactory(reg)
        assert factory._registry is reg


# ---------------------------------------------------------------------------
# Test: Factory Create - Valid Names
# ---------------------------------------------------------------------------


class TestFactoryCreateValid:
    """Tests for factory create with valid names."""

    def test_create_explain(self, factory: CapabilityFactory) -> None:
        """Creating 'explain' should return an ExplainCapability instance."""
        capability = factory.create("explain")
        assert isinstance(capability, ExplainCapability)

    def test_create_returns_instance(self, factory: CapabilityFactory) -> None:
        """create() should return an instance, not a class."""
        capability = factory.create("explain")
        assert capability is not ExplainCapability
        assert callable(capability.execute)

    def test_create_explain_name(self, factory: CapabilityFactory) -> None:
        """The created capability should have name 'explain'."""
        capability = factory.create("explain")
        assert capability.name == "explain"

    def test_create_explain_intent(self, factory: CapabilityFactory) -> None:
        """The created capability should have EXPLAIN intent."""
        capability = factory.create("explain")
        assert capability.intent == PlannerIntent.EXPLAIN

    def test_create_multiple_times(self, factory: CapabilityFactory) -> None:
        """Multiple create calls should return independent instances."""
        cap1 = factory.create("explain")
        cap2 = factory.create("explain")
        assert cap1 is not cap2
        assert cap1.name == cap2.name
        assert cap1.intent == cap2.intent


# ---------------------------------------------------------------------------
# Test: Factory Create - Invalid Names
# ---------------------------------------------------------------------------


class TestFactoryCreateInvalid:
    """Tests for factory create with invalid names."""

    def test_create_unregistered_raises_value_error(self, factory: CapabilityFactory) -> None:
        """Creating an unregistered capability should raise ValueError."""
        with pytest.raises(ValueError, match="not registered"):
            factory.create("nonexistent")

    def test_create_unregistered_shows_available(self, factory: CapabilityFactory) -> None:
        """Error message should show available capabilities."""
        with pytest.raises(ValueError, match="explain"):
            factory.create("nonexistent")

    def test_create_empty_name(self, factory: CapabilityFactory) -> None:
        """Creating with empty name should raise ValueError."""
        with pytest.raises(ValueError, match="not registered"):
            factory.create("")


# ---------------------------------------------------------------------------
# Test: Factory Uses Registry
# ---------------------------------------------------------------------------


class TestFactoryUsesRegistry:
    """Tests that factory uses the registry for lookups."""

    def test_factory_uses_same_registry(self, registry: CapabilityRegistry) -> None:
        """Factory should use the same registry instance."""
        factory = CapabilityFactory(registry)
        assert factory._registry is registry

    def test_registry_changes_reflected(self, registry: CapabilityRegistry) -> None:
        """Changes to registry should be reflected in factory."""
        factory = CapabilityFactory(registry)

        # Register a new capability
        registry.register("mock", MockCapability)

        capability = factory.create("mock")
        assert isinstance(capability, MockCapability)

    def test_factory_rejects_unregistered(self, registry: CapabilityRegistry) -> None:
        """Factory should reject capabilities not in registry."""
        factory = CapabilityFactory(registry)

        with pytest.raises(ValueError, match="not registered"):
            factory.create("unregistered")


# ---------------------------------------------------------------------------
# Test: Explain Capability Through Factory
# ---------------------------------------------------------------------------


class TestExplainThroughFactory:
    """Tests for ExplainCapability through factory."""

    def test_explain_registered(self, registry: CapabilityRegistry) -> None:
        """ExplainCapability should be registered."""
        assert registry.has("explain")

    def test_explain_created_through_factory(self, factory: CapabilityFactory) -> None:
        """ExplainCapability should be creatable through factory."""
        capability = factory.create("explain")
        assert isinstance(capability, ExplainCapability)

    def test_explain_has_correct_name(self, factory: CapabilityFactory) -> None:
        """Created ExplainCapability should have correct name."""
        capability = factory.create("explain")
        assert capability.name == "explain"

    def test_explain_has_correct_intent(self, factory: CapabilityFactory) -> None:
        """Created ExplainCapability should have EXPLAIN intent."""
        capability = factory.create("explain")
        assert capability.intent == PlannerIntent.EXPLAIN


# ---------------------------------------------------------------------------
# Test: Factory Never Hardcodes
# ---------------------------------------------------------------------------


class TestFactoryNoHardcoding:
    """Tests that factory never hardcodes capability classes."""

    def test_factory_only_uses_registry(self, registry: CapabilityRegistry) -> None:
        """Factory should only use registry for lookups."""
        # If the registry is empty, factory should not be able to create anything
        empty_reg = CapabilityRegistry()
        empty_factory = CapabilityFactory(empty_reg)

        with pytest.raises(ValueError, match="not registered"):
            empty_factory.create("explain")

    def test_factory_does_not_import_capability_classes(self) -> None:
        """Factory module should not import specific capability classes."""
        import inspect

        import packages.capabilities.factory as factory_module

        # Get the actual code (not docstring) by compiling and extracting
        source = inspect.getsource(factory_module)
        # Remove the docstring to check only executable code
        lines = source.split("\n")
        # Skip lines that are part of the module docstring (first triple-quoted block)
        code_lines: list[str] = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if not in_docstring and stripped.startswith('"""'):
                in_docstring = True
                continue
            if in_docstring:
                if stripped.endswith('"""') and len(stripped) > 3:
                    in_docstring = False
                continue
            code_lines.append(line)

        code = "\n".join(code_lines)
        # The factory should not import or reference specific capability classes
        assert "ExplainCapability" not in code
        assert "MockCapability" not in code
        assert "DebugCapability" not in code
