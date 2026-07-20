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
- ``title`` is the only required field.

Public API
----------

.. code-block:: python

    from packages.tasks.bug_investigation_request import BugInvestigationRequest

    request = BugInvestigationRequest(
        title="Auth fails on timeout",
        description="Authentication fails when session expires",
        observed_behavior="TimeoutError after 30s",
        expected_behavior="Successful authentication",
        changed_files=("packages/auth/auth.py",),
        changed_symbols=("authenticate", "validate_session"),
        stack_trace="TimeoutError at line 42",
        logs=("ERROR: timeout",),
        tags=("auth", "timeout"),
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
        title: Brief summary of the bug (required).
        description: Detailed description of the bug.
        observed_behavior: Description of what actually happens.
        expected_behavior: Description of what should happen.
        changed_files: Tuple of file paths that were changed recently.
        changed_symbols: Tuple of symbol names that were changed.
        stack_trace: Optional stack trace observed during the bug.
        logs: Tuple of relevant log messages.
        tags: Tuple of classification tags.
    """

    title: str
    description: str = ""
    observed_behavior: str = ""
    expected_behavior: str = ""
    changed_files: tuple[str, ...] = ()
    changed_symbols: tuple[str, ...] = ()
    stack_trace: str | None = None
    logs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def to_task_request(self) -> TaskRequest:
        """Convert to a TaskRequest for the task framework.

        Maps the bug investigation request fields into TaskRequest fields
        by constructing a descriptive query and populating options with
        the changed files, symbols, and additional context.

        Returns:
            A TaskRequest suitable for task execution.
        """
        # Build a descriptive query from title and description
        query_parts = [self.title]
        if self.description:
            query_parts.append(self.description)
        query = " ".join(query_parts)

        # Build options dict with investigation context
        options: dict[str, object] = {
            "changed_files": list(self.changed_files),
            "changed_symbols": list(self.changed_symbols),
            "observed_behavior": self.observed_behavior,
            "expected_behavior": self.expected_behavior,
        }
        if self.stack_trace:
            options["stack_trace"] = self.stack_trace
        if self.logs:
            options["logs"] = list(self.logs)
        if self.tags:
            options["tags"] = list(self.tags)

        return TaskRequest(
            query=query,
            repository_root=".",
            user_messages=(self.title, self.description) if self.description else (self.title,),
            options=options,
        )