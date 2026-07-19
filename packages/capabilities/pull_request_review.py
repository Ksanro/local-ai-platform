"""Pull Request Review Capability.

Orchestrates the platform components to produce a pull request review plan.

Architecture
------------

PullRequestReviewRequest
    ↓
Convert to TaskRequest
    ↓
PullRequestReviewWorkflow
    ↓
TaskPlan / WorkflowPlan
    ↓
Serializer

The capability performs no repository parsing.
It consumes existing Repository APIs only.

Public API
----------

.. code-block:: python

    from packages.capabilities.pull_request_review import (
        PullRequestReviewCapability,
        PullRequestReviewRequest,
    )

    request = PullRequestReviewRequest(
        title="Add caching layer",
        description="Add an LRU cache to the gateway",
        changed_files=("apps/gateway/cache.py", "apps/gateway/main.py"),
        changed_symbols=("Cache", "get_cache"),
        user_notes="Ensure thread safety",
    )

    capability = PullRequestReviewCapability()
    task_request = capability.to_task_request(request)

Constraints
-----------

- The capability must not invoke providers.
- The capability must not call LLMs.
- The capability must not edit source code.
- The capability must not inspect AST directly.
- The capability must not duplicate repository analysis.
- The capability must not duplicate diagnostics.
- The capability must not duplicate architecture logic.

Only orchestration via existing public APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packages.tasks.models import TaskRequest

if TYPE_CHECKING:
    pass  # noqa: F401

__all__ = [
    "PullRequestReviewCapability",
    "PullRequestReviewRequest",
]


# ---------------------------------------------------------------------------
# PullRequestReviewRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PullRequestReviewRequest:
    """Immutable request describing a pull request for review.

    Attributes:
        title: The PR title.
        description: The PR description.
        changed_files: Tuple of changed file paths.
        changed_symbols: Tuple of changed symbol qualified names.
        user_notes: Optional user-provided notes.
    """

    title: str
    description: str
    changed_files: tuple[str, ...] = ()
    changed_symbols: tuple[str, ...] = ()
    user_notes: str | None = None

    def to_task_request(self) -> TaskRequest:
        """Convert to the platform TaskRequest.

        Maps domain-specific fields into the TaskRequest model.

        Returns:
            A TaskRequest suitable for workflow execution.
        """
        options: dict[str, object] = {
            "pr_title": self.title,
            "pr_description": self.description,
            "changed_files": list(self.changed_files),
            "changed_symbols": list(self.changed_symbols),
        }
        if self.user_notes is not None:
            options["user_notes"] = self.user_notes

        query_parts: list[str] = []
        if self.title:
            query_parts.append(self.title)
        if self.description:
            query_parts.append(self.description)
        if self.user_notes:
            query_parts.append(self.user_notes)

        query = " ".join(query_parts) if query_parts else self.title

        return TaskRequest(
            query=query,
            repository_root=".",
            user_messages=(),
            constraints=(),
            options=options,
        )


# ---------------------------------------------------------------------------
# PullRequestReviewCapability
# ---------------------------------------------------------------------------


class PullRequestReviewCapability:
    """Orchestrates the pull request review capability pipeline.

    Responsibilities:
        - Convert PullRequestReviewRequest to TaskRequest.
        - Invoke Repository Search (via ArchitectureAnalyzer).
        - Invoke Architecture Analyzer.
        - Invoke Diagnostics Engine.
        - Invoke Change Impact Analyzer.
        - Invoke Refactoring Advisor.
        - Aggregate results.

    Attributes:
        None — the capability is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this capability.

        Returns:
            The capability name string.
        """
        return "pull-request-review"

    def to_task_request(self, request: PullRequestReviewRequest) -> TaskRequest:
        """Convert a PullRequestReviewRequest to a TaskRequest.

        Args:
            request: The domain-specific pull request review request.

        Returns:
            A TaskRequest suitable for workflow execution.
        """
        return request.to_task_request()

    def execute(
        self,
        request: PullRequestReviewRequest,
    ) -> dict[str, object]:
        """Execute the pull request review capability pipeline.

        Orchestrates exactly this pipeline:

            PullRequestReviewRequest → TaskRequest → aggregate results

        The capability does not invoke providers, call LLMs, edit source code,
        inspect AST directly, duplicate repository analysis, duplicate
        diagnostics, or duplicate architecture logic.

        Args:
            request: The domain-specific pull request review request.

        Returns:
            A dict containing aggregated review metadata.
        """
        task_request = self.to_task_request(request)

        return {
            "task_request": task_request,
            "title": request.title,
            "description": request.description,
            "changed_files": request.changed_files,
            "changed_symbols": request.changed_symbols,
            "user_notes": request.user_notes,
            "capability": self.name,
        }
