"""Bug Investigation Request model.

Defines the immutable ``BugInvestigationRequest`` dataclass used as input
for the bug investigation workflow.  A mapper converts this request into
the existing ``TaskRequest``.

Architecture
------------

BugInvestigationRequest
    ↓ to_task_request()
TaskRequest

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.

Public API
----------

.. code-block:: python

    from packages.tasks.bug_investigation_request import BugInvestigationRequest

    request = BugInvestigationRequest(
        summary="Auth fails on timeout",
        description="Authentication fails when session expires",
        suspected_modules=("packages/auth/",),
        suspected_symbols=("authenticate", "validate_session"),
        observed_stacktrace="TimeoutError at line 42",
        reproduction_steps=("login", "wait", "access protected resource"),
    )

    task_request = request.to_task_request()
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.tasks.models import TaskRequest


@dataclass(frozen=True, slots=True)
class BugInvestigationRequest:
    """Immutable request for bug investigation.

    Attributes:
        summary: Brief summary of the bug.
        description: Detailed description of the bug.
        suspected_modules: Tuple of module paths suspected to contain the bug.
        suspected_symbols: Tuple of symbol names suspected to be involved.
        observed_stacktrace: Optional stacktrace observed during the bug.
        reproduction_steps: Tuple of steps to reproduce the bug.
    """

    summary: str
    description: str
    suspected_modules: tuple[str, ...] = ()
    suspected_symbols: tuple[str, ...] = ()
    observed_stacktrace: str | None = None
    reproduction_steps: tuple[str, ...] = ()

    def to_task_request(self) -> TaskRequest:
        """Convert to a TaskRequest for the task framework.

        Maps the bug investigation request fields into TaskRequest fields
        by constructing a descriptive query and populating options with
        the suspected modules, symbols, and reproduction steps.

        Returns:
            A TaskRequest suitable for task execution.
        """
        # Build a descriptive query from summary and description
        query_parts = [self.summary]
        if self.description:
            query_parts.append(self.description)
        query = " ".join(query_parts)

        # Build options dict with investigation context
        options: dict[str, object] = {
            "suspected_modules": list(self.suspected_modules),
            "suspected_symbols": list(self.suspected_symbols),
            "reproduction_steps": list(self.reproduction_steps),
        }
        if self.observed_stacktrace:
            options["observed_stacktrace"] = self.observed_stacktrace

        return TaskRequest(
            query=query,
            repository_root=".",
            user_messages=(self.summary, self.description),
            options=options,
        )


