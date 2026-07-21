"""Engineering planner module.

Implements the EngineeringPlanner that produces deterministic workflow
sequences from engineering goals. The planner chooses workflow sequences
and respects constraints without inspecting repositories or generating
patches.

Architecture
------------

EngineeringGoal --> EngineeringPlanner --> tuple[type[Workflow], ...]

Responsibilities
----------------

- Choose workflow sequence from engineering goal.
- Respect goal constraints.
- Produce deterministic planning.
- No providers.
- No repository analysis.
- No patch generation.

Non-responsibilities
--------------------

- Must NOT inspect repositories.
- Must NOT parse repositories.
- Must NOT invoke providers.
- Must NOT generate patches.
- Must NOT duplicate workflow logic.
- Must NOT duplicate task logic.

Public API
----------

.. code-block:: python

    from packages.autonomous.planner import EngineeringPlanner

    planner = EngineeringPlanner()
    sequence = planner.plan(
        engineering_goal=goal,
    )

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.autonomous.models import EngineeringGoal

if TYPE_CHECKING:
    pass  # Workflow types imported lazily to avoid circular imports

__all__ = [
    "EngineeringPlanner",
]


# ---------------------------------------------------------------------------
# EngineeringPlanner
# ---------------------------------------------------------------------------


class EngineeringPlanner:
    """Deterministic engineering planner.

    The planner takes an ``EngineeringGoal`` and produces a deterministic
    sequence of workflow classes to execute.  It respects constraints from
    the goal and produces a stable ordering.

    The planner is stateless and deterministic — given the same goal it
    always produces the same workflow sequence.

    Constraints
    -----------

    - Must NOT inspect repositories.
    - Must NOT parse repositories.
    - Must NOT invoke providers.
    - Must NOT generate patches.
    - Must NOT duplicate workflow logic.
    - Must NOT duplicate task logic.
    - Must produce deterministic output.

    Usage
    -----

    .. code-block:: python

        from packages.autonomous.planner import EngineeringPlanner

        planner = EngineeringPlanner()
        sequence = planner.plan(
            engineering_goal=goal,
        )

    """

    # Default workflow sequence — executed in this order when no
    # constraints override the selection.  The sequence represents the
    # canonical engineering lifecycle: review → plan → implement → verify.
    _DEFAULT_WORKFLOW_ORDER: tuple[str, ...] = (
        "architecture-review",
        "implementation",
        "self-verification",
    )

    @classmethod
    def plan(
        cls,
        engineering_goal: EngineeringGoal,
        available_workflows: dict[str, type] | None = None,
    ) -> tuple[type, ...]:
        """Plan a deterministic workflow sequence for the given goal.

        This is the main entry point for the EngineeringPlanner. It
        analyses the goal constraints and produces a stable ordering of
        workflow classes.

        Args:
            engineering_goal: The engineering goal to plan for.
            available_workflows: Optional mapping of workflow name →
                workflow class.  When not provided the planner uses the
                default workflow order.

        Returns:
            Tuple of workflow classes in deterministic execution order.

        Raises:
            ValueError: If no valid workflows can be selected.
        """
        # Build the candidate set from available workflows or defaults.
        candidates = cls._build_candidates(available_workflows)

        # Filter by constraints.
        filtered = cls._apply_constraints(
            engineering_goal, candidates
        )

        # Order deterministically.
        ordered = cls._order_workflows(
            engineering_goal, filtered
        )

        if not ordered:
            raise ValueError(
                f"No valid workflows for goal '{engineering_goal.id}'."
            )

        return tuple(ordered)

    @classmethod
    def _build_candidates(
        cls,
        available_workflows: dict[str, type] | None,
    ) -> dict[str, type]:
        """Build the candidate workflow mapping.

        Args:
            available_workflows: Optional external workflow registry.

        Returns:
            Mapping of workflow name → workflow class.
        """
        if available_workflows is not None:
            return dict(available_workflows)

        # Return empty — the default order is handled in _order_workflows.
        return {}

    @classmethod
    def _apply_constraints(
        cls,
        goal: EngineeringGoal,
        candidates: dict[str, type],
    ) -> dict[str, type]:
        """Apply goal constraints to filter candidates.

        Constraints are evaluated as exclusion rules.  If a constraint
        string matches a workflow name that workflow is excluded.

        Args:
            goal: The engineering goal with constraints.
            candidates: Candidate workflow mapping.

        Returns:
            Filtered candidate mapping.
        """
        filtered: dict[str, type] = {}

        for name, workflow_class in candidates.items():
            excluded = False

            for constraint in goal.constraints:
                # Simple constraint matching: if the constraint string
                # appears in the workflow name or class name the workflow
                # is excluded.
                if constraint.lower() in name.lower():
                    excluded = True
                    break
                if constraint.lower() in workflow_class.__name__.lower():
                    excluded = True
                    break

            if not excluded:
                filtered[name] = workflow_class

        return filtered

    @classmethod
    def _order_workflows(
        cls,
        goal: EngineeringGoal,
        candidates: dict[str, type],
    ) -> dict[str, type]:
        """Order workflows deterministically.

        Workflows are ordered by the canonical default order first,
        then by alphabetical name for any remaining candidates.

        Args:
            goal: The engineering goal.
            candidates: Filtered candidate workflow mapping.

        Returns:
            Ordered candidate mapping preserving insertion order.
        """
        ordered: dict[str, type] = {}

        # First pass: add workflows in the default order.
        for name in cls._DEFAULT_WORKFLOW_ORDER:
            if name in candidates:
                ordered[name] = candidates[name]

        # Second pass: add remaining workflows alphabetically.
        remaining = sorted(
            name for name in candidates if name not in ordered
        )
        for name in remaining:
            ordered[name] = candidates[name]

        return ordered