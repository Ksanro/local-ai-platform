"""Tests for DependencyContainer.

Tests cover:
- Registration and resolution
- Duplicate detection
- Cycle detection
- Missing dependency detection
- Deterministic ordering
- Validation
- Clear and unregister
"""

from __future__ import annotations

import pytest

from packages.bootstrap.container import (
    DependencyContainer,
    RegistrationError,
    ResolutionError,
)


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for dependency registration."""

    def test_empty_container(self) -> None:
        container = DependencyContainer()
        assert container.count == 0
        assert container.registered_names == ()

    def test_register_single_dependency(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        assert container.count == 1
        assert container.registered_names == ("a",)

    def test_register_multiple_dependencies(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda: "value_b")
        container.register("c", lambda: "value_c")
        assert container.count == 3
        assert container.registered_names == ("a", "b", "c")

    def test_register_with_dependencies(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: f"value_b({a})", dependencies=("a",))
        assert container.count == 2

    def test_empty_name_raises(self) -> None:
        container = DependencyContainer()
        with pytest.raises(RegistrationError, match="empty"):
            container.register("", lambda: "value")

    def test_non_callable_factory_raises(self) -> None:
        container = DependencyContainer()
        with pytest.raises(RegistrationError, match="callable"):
            container.register("a", "not_callable")  # type: ignore[arg-type]

    def test_duplicate_registration_raises(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        with pytest.raises(RegistrationError, match="already registered"):
            container.register("a", lambda: "value_a_2")

    def test_self_dependency_raises(self) -> None:
        container = DependencyContainer()
        with pytest.raises(RegistrationError, match="itself"):
            container.register("a", lambda a: "value", dependencies=("a",))


# ---------------------------------------------------------------------------
# Resolution tests
# ---------------------------------------------------------------------------


class TestResolution:
    """Tests for dependency resolution."""

    def test_resolve_single_dependency(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        result = container.resolve("a")
        assert result == "value_a"

    def test_resolve_with_dependencies(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: f"value_b({a})", dependencies=("a",))
        result = container.resolve("b")
        assert result == "value_b(value_a)"

    def test_resolve_caches_result(self) -> None:
        container = DependencyContainer()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return "value"

        container.register("a", factory)
        container.resolve("a")
        container.resolve("a")
        assert call_count == 1

    def test_contains_returns_true(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        assert container.contains("a") is True

    def test_contains_returns_false(self) -> None:
        container = DependencyContainer()
        assert container.contains("a") is False

    def test_resolve_missing_dependency_raises(self) -> None:
        container = DependencyContainer()
        with pytest.raises(ResolutionError, match="not registered"):
            container.resolve("a")

    def test_resolve_missing_dependency_in_chain(self) -> None:
        container = DependencyContainer()
        container.register("b", lambda a: "value", dependencies=("a",))
        with pytest.raises(ResolutionError, match="not registered"):
            container.resolve("b")

    def test_contains_after_registration(self) -> None:
        container = DependencyContainer()
        assert container.contains("a") is False
        container.register("a", lambda: "value_a")
        assert container.contains("a") is True


# ---------------------------------------------------------------------------
# All() tests
# ---------------------------------------------------------------------------


class TestAll:
    """Tests for the all() method."""

    def test_all_empty(self) -> None:
        container = DependencyContainer()
        result = container.all()
        assert result == {}

    def test_all_with_dependencies(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: f"value_b({a})", dependencies=("a",))
        container.register("c", lambda a, b: f"value_c({a},{b})", dependencies=("a", "b"))
        result = container.all()
        assert result["a"] == "value_a"
        assert result["b"] == "value_b(value_a)"
        assert result["c"] == "value_c(value_a,value_b(value_a))"

    def test_all_deterministic_order(self) -> None:
        container = DependencyContainer()
        container.register("c", lambda: "value_c")
        container.register("a", lambda: "value_a")
        container.register("b", lambda: "value_b")
        result = container.all()
        assert list(result.keys()) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for container validation."""

    def test_valid_container(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: "value_b", dependencies=("a",))
        errors = container.validate()
        assert errors == []

    def test_missing_dependency_in_validation(self) -> None:
        container = DependencyContainer()
        container.register("b", lambda a: "value_b", dependencies=("a",))
        errors = container.validate()
        assert any("a" in e for e in errors)

    def test_self_dependency_in_validation(self) -> None:
        container = DependencyContainer()
        # Self-dependency is caught at registration time, not validation
        # So test that registration raises
        from pytest import raises
        with raises(RegistrationError, match="itself"):
            container.register("a", lambda a: "value", dependencies=("a",))

    def test_empty_container_validation(self) -> None:
        container = DependencyContainer()
        errors = container.validate()
        assert errors == []


# ---------------------------------------------------------------------------
# Cycle detection tests
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_no_cycle(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: "value_b", dependencies=("a",))
        container.register("c", lambda b: "value_c", dependencies=("b",))
        # No cycle - should not raise
        result = container.resolve("c")
        assert result == "value_c"

    def test_direct_cycle(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda b: "value_a", dependencies=("b",))
        container.register("b", lambda a: "value_b", dependencies=("a",))
        with pytest.raises(ResolutionError, match="Circular"):
            container.resolve("a")

    def test_indirect_cycle(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda b: "value_a", dependencies=("b",))
        container.register("b", lambda c: "value_b", dependencies=("c",))
        container.register("c", lambda a: "value_c", dependencies=("a",))
        with pytest.raises(ResolutionError, match="Circular"):
            container.resolve("a")


# ---------------------------------------------------------------------------
# Clear and unregister tests
# ---------------------------------------------------------------------------


class TestClearAndUnregister:
    """Tests for clear() and unregister() methods."""

    def test_unregister(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.unregister("a")
        assert container.contains("a") is False
        assert container.count == 0

    def test_unregister_nonexistent(self) -> None:
        container = DependencyContainer()
        container.unregister("a")  # Should not raise
        assert container.count == 0

    def test_clear(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda: "value_b")
        container.clear()
        assert container.count == 0
        assert container.registered_names == ()

    def test_clear_resolved_cache(self) -> None:
        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.resolve("a")
        container.clear()
        assert container.count == 0
        assert container.contains("a") is False