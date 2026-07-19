"""Tests for the ExecutionValidator.

Verifies:
- Dependency ordering validation
- Context validation
- Constraint validation
- Ordering validation
- Valid plan acceptance
- Invalid plan rejection
"""

from __future__ import annotations

from packages.execution.models import ExecutionPlan, ExecutionStep
from packages.execution.validator import ExecutionValidator

# ---------------------------------------------------------------------------
# Test: Validate Dependencies
# ---------------------------------------------------------------------------


class TestValidateDependencies:
    """Tests for dependency ordering validation."""

    def test_valid_sequential_dependencies(self) -> None:
        """Valid sequential dependencies should produce no errors."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=1, title="Second", description="B"),
            ExecutionStep(order=2, title="Third", description="C"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_dependencies(plan)
        assert errors == []

    def test_missing_dependency_order(self) -> None:
        """Missing dependency order should produce error."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=2, title="Third", description="C"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_dependencies(plan)
        assert len(errors) >= 1
        assert "Missing dependency order 1" in errors[0]

    def test_empty_plan(self) -> None:
        """Empty plan should produce no dependency errors."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )

        errors = ExecutionValidator.validate_dependencies(plan)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: Validate Context
# ---------------------------------------------------------------------------


class TestValidateContext:
    """Tests for context validation."""

    def test_valid_context_with_requirements(self) -> None:
        """Context present when required should produce no errors."""
        steps = (
            ExecutionStep(
                order=0,
                title="Analyze",
                description="Analyze",
                required_symbols=("SymbolA",),
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package={"symbols": {"SymbolA": "value"}},
        )

        errors = ExecutionValidator.validate_context(plan)
        assert errors == []

    def test_missing_context_when_required(self) -> None:
        """No context when required should produce error."""
        steps = (
            ExecutionStep(
                order=0,
                title="Analyze",
                description="Analyze",
                required_symbols=("SymbolA",),
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package=None,
        )

        errors = ExecutionValidator.validate_context(plan)
        assert len(errors) == 1
        assert "context_package is None" in errors[0]

    def test_no_context_when_not_required(self) -> None:
        """No context when not required should produce no errors."""
        steps = (
            ExecutionStep(
                order=0,
                title="Simple",
                description="Simple step",
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package=None,
        )

        errors = ExecutionValidator.validate_context(plan)
        assert errors == []

    def test_context_with_required_modules(self) -> None:
        """Modules required without context should produce error."""
        steps = (
            ExecutionStep(
                order=0,
                title="Analyze",
                description="Analyze",
                required_modules=("mod.py",),
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package=None,
        )

        errors = ExecutionValidator.validate_context(plan)
        assert len(errors) == 1
        assert "context_package is None" in errors[0]


# ---------------------------------------------------------------------------
# Test: Validate Constraints
# ---------------------------------------------------------------------------


class TestValidateConstraints:
    """Tests for constraint validation."""

    def test_valid_constraints(self) -> None:
        """Valid constraints should produce no errors."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            constraints=("read-only", "deterministic"),
        )

        errors = ExecutionValidator.validate_constraints(plan)
        assert errors == []

    def test_empty_constraints(self) -> None:
        """Empty constraints should produce no errors."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )

        errors = ExecutionValidator.validate_constraints(plan)
        assert errors == []

    def test_invalid_empty_constraint(self) -> None:
        """Empty string constraint should produce error."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            constraints=("read-only", "", "deterministic"),
        )

        errors = ExecutionValidator.validate_constraints(plan)
        assert len(errors) >= 1
        assert "Invalid constraint" in errors[0]

    def test_invalid_whitespace_constraint(self) -> None:
        """Whitespace-only constraint should produce error."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            constraints=("read-only", "   ", "deterministic"),
        )

        errors = ExecutionValidator.validate_constraints(plan)
        assert len(errors) >= 1
        assert "Invalid constraint" in errors[0]


# ---------------------------------------------------------------------------
# Test: Validate Ordering
# ---------------------------------------------------------------------------


class TestValidateOrdering:
    """Tests for deterministic ordering validation."""

    def test_valid_sequential_ordering(self) -> None:
        """Valid sequential ordering should produce no errors."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=1, title="Second", description="B"),
            ExecutionStep(order=2, title="Third", description="C"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_ordering(plan)
        assert errors == []

    def test_negative_order(self) -> None:
        """Negative order should produce error."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=-1, title="Invalid", description="B"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_ordering(plan)
        assert len(errors) >= 1
        assert "Invalid negative order" in errors[0]

    def test_duplicate_order(self) -> None:
        """Duplicate order should produce error."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=0, title="Duplicate", description="B"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_ordering(plan)
        assert len(errors) >= 1
        assert "Duplicate order" in errors[0]

    def test_missing_order(self) -> None:
        """Missing order should produce error."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=2, title="Third", description="C"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
        )

        errors = ExecutionValidator.validate_ordering(plan)
        assert len(errors) >= 1
        assert "Missing order" in errors[0]

    def test_empty_plan(self) -> None:
        """Empty plan should produce no ordering errors."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )

        errors = ExecutionValidator.validate_ordering(plan)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: Validate All
# ---------------------------------------------------------------------------


class TestValidateAll:
    """Tests for combined validation."""

    def test_valid_plan(self) -> None:
        """A fully valid plan should produce no errors."""
        steps = (
            ExecutionStep(order=0, title="First", description="A"),
            ExecutionStep(order=1, title="Second", description="B"),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package={"key": "value"},
            constraints=("read-only",),
        )

        errors = ExecutionValidator.validate_all(plan)
        assert errors == []

    def test_invalid_plan(self) -> None:
        """An invalid plan should produce multiple errors."""
        steps = (
            ExecutionStep(
                order=-1,
                title="Invalid",
                description="Bad",
                required_symbols=("Sym",),
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package=None,
            constraints=("",),
        )

        errors = ExecutionValidator.validate_all(plan)
        assert len(errors) > 0

    def test_empty_plan_validation(self) -> None:
        """An empty plan should pass most validations."""
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
        )

        errors = ExecutionValidator.validate_all(plan)
        # Empty plan should only have constraint validation passing
        # (no constraints = valid)
        assert len(errors) == 0

    def test_multiple_error_types(self) -> None:
        """Multiple error types should all be reported."""
        steps = (
            ExecutionStep(
                order=-1,
                title="Invalid",
                description="Bad",
                required_symbols=("Sym",),
            ),
            ExecutionStep(
                order=0,
                title="Also Invalid",
                description="Bad",
                required_modules=("mod.py",),
            ),
        )
        plan = ExecutionPlan(
            workflow_name="test",
            objective="Test",
            execution_steps=steps,
            context_package=None,
            constraints=("", "   "),
        )

        errors = ExecutionValidator.validate_all(plan)

        # Should have errors from multiple validators
        error_str = " ".join(errors)
        assert "negative order" in error_str or "Invalid negative" in error_str
        assert "context_package is None" in error_str
        assert "Invalid constraint" in error_str
