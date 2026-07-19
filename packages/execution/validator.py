"""ExecutionValidator implementation.

Validates ExecutionPlan objects for correctness and readiness.

Architecture
------------

ExecutionPlan  -->  ExecutionValidator  -->  ValidationResults

Constraints
-----------

- No provider execution.
- No source code modification.
- No repository analysis.
- Validates structural properties only.

Public API
----------

.. code-block:: python

    from packages.execution.validator import ExecutionValidator
    from packages.execution.models import ExecutionPlan

    plan = ExecutionPlan(
        workflow_name="implement_feature",
        objective="Add new feature",
    )

    errors = ExecutionValidator.validate_all(plan)

"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.execution.models import ExecutionPlan  # noqa: F401


class ExecutionValidator:
    """Validates ExecutionPlan objects.

    Responsibilities:
        - Validate dependency ordering
        - Validate required context exists
        - Validate constraints are satisfied
        - Validate deterministic ordering

    All validation methods return a list of error strings.
    An empty list means the plan is valid.
    """

    @staticmethod
    def validate_dependencies(plan: ExecutionPlan) -> list[str]:
        """Validate that dependency ordering is correct.

        Checks that all steps reference valid preceding steps
        based on their order values.

        Args:
            plan: The execution plan to validate.

        Returns:
            A list of error strings (empty if valid).
        """
        errors: list[str] = []

        step_orders = {step.order: step for step in plan.execution_steps}

        for step in plan.execution_steps:
            # Each step's order should be sequential
            # Order 0 is the first step, no dependencies
            if step.order == 0:
                continue

            # Check that all lower orders exist
            for prev_order in range(step.order):
                if prev_order not in step_orders:
                    errors.append(
                        f"Missing dependency order {prev_order} for step '{step.title}'",
                    )

        return errors

    @staticmethod
    def validate_context(plan: ExecutionPlan) -> list[str]:
        """Validate that required context exists.

        Checks that the context_package is present when execution_steps
        require symbols or modules.

        Args:
            plan: The execution plan to validate.

        Returns:
            A list of error strings (empty if valid).
        """
        errors: list[str] = []

        # Check if any step requires symbols or modules
        has_requirements = any(
            step.required_symbols or step.required_modules
            for step in plan.execution_steps
        )

        if has_requirements and plan.context_package is None:
            errors.append(
                "Execution steps require context but context_package is None",
            )

        return errors

    @staticmethod
    def validate_constraints(plan: ExecutionPlan) -> list[str]:
        """Validate that constraints are satisfied.

        Checks that all constraints in the plan are well-formed
        (non-empty strings, valid format).

        Args:
            plan: The execution plan to validate.

        Returns:
            A list of error strings (empty if valid).
        """
        errors: list[str] = []

        for constraint in plan.constraints:
            if not isinstance(constraint, str) or not constraint.strip():
                errors.append(
                    f"Invalid constraint: '{constraint}'",
                )

        return errors

    @staticmethod
    def validate_ordering(plan: ExecutionPlan) -> list[str]:
        """Validate deterministic ordering.

        Checks that:
        - Steps are ordered sequentially from 0
        - No duplicate order values exist
        - All steps have valid order values (>= 0)

        Args:
            plan: The execution plan to validate.

        Returns:
            A list of error strings (empty if valid).
        """
        errors: list[str] = []

        if not plan.execution_steps:
            return errors

        orders = [step.order for step in plan.execution_steps]

        # Check for negative orders
        for order in orders:
            if order < 0:
                errors.append(f"Invalid negative order: {order}")

        # Check for duplicates
        seen: set[int] = set()
        for order in orders:
            if order in seen:
                errors.append(f"Duplicate order value: {order}")
            seen.add(order)

        # Check for sequential ordering
        expected_orders = set(range(len(orders)))
        actual_orders = set(orders)
        if expected_orders != actual_orders:
            missing = expected_orders - actual_orders
            errors.append(f"Missing order values: {sorted(missing)}")

        return errors

    @staticmethod
    def validate_all(plan: ExecutionPlan) -> list[str]:
        """Run all validation checks on an ExecutionPlan.

        Convenience method that runs all validation methods and
        returns combined errors.

        Args:
            plan: The execution plan to validate.

        Returns:
            A combined list of all error strings.
        """
        errors: list[str] = []
        errors.extend(ExecutionValidator.validate_dependencies(plan))
        errors.extend(ExecutionValidator.validate_context(plan))
        errors.extend(ExecutionValidator.validate_constraints(plan))
        errors.extend(ExecutionValidator.validate_ordering(plan))
        return errors
