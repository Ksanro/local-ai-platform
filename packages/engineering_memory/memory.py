"""Engineering Memory — Main service layer.

Implements the EngineeringMemory service that stores completed engineering
sessions and provides deterministic query capabilities.

Execution Flow
--------------

EngineeringController
    ↓
EngineeringSessionRecord (after Execution → Verification → Evaluation)
    ↓
EngineeringMemory.store(record)
    ↓
Future Engineering Sessions (query memory for context)

Architecture
------------

Controller writes.
Consumers read.
No component writes memory except Controller.
Memory never modifies reports.
Memory never performs analysis.

Constraints
-----------

- No vector database.
- No embeddings.
- No semantic search.
- No repository analysis.
- No provider calls.
- Deterministic behaviour.

Public API
----------

.. code-block:: python

    from packages.engineering_memory.memory import EngineeringMemory

    memory = EngineeringMemory()

    # Store a completed session
    memory.store(record)

    # Query sessions
    session = memory.find_session("sess-001")
    sessions = memory.find_by_workflow("bug-fix")
    successful = memory.find_successful()
    failed = memory.find_failed()
    module_sessions = memory.find_by_module("module_x")
    recent = memory.recent(limit=10)
    all_sessions = memory.list_sessions()

    # Get statistics
    stats = memory.statistics()

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.engineering_memory.models import (
    EngineeringSessionRecord,
    MemoryStatistics,
)
from packages.engineering_memory.persistence import (
    MemoryStorage,
    DEFAULT_STORAGE_PATH,
)

__all__ = [
    "EngineeringMemory",
]


# ---------------------------------------------------------------------------
# EngineeringMemory
# ---------------------------------------------------------------------------


class EngineeringMemory:
    """Deterministic engineering memory service.

    Stores completed engineering session facts and provides deterministic
    query capabilities. Never performs semantic search, embeddings, or
    provider calls.

    The EngineeringMemory is the SINGLE source of truth for engineering
    session facts. It is write-once (sessions are immutable once stored)
    and read-many.

    Usage:
        memory = EngineeringMemory()
        memory.store(record)
        sessions = memory.find_by_workflow("bug-fix")

    Thread Safety:
        All methods are thread-safe.
    """

    def __init__(
        self,
        storage_path: str | None = None,
        in_memory_only: bool = False,
    ) -> None:
        """Initialize the engineering memory.

        Args:
            storage_path: Optional path to the JSON storage file.
                When None, uses DEFAULT_STORAGE_PATH.
            in_memory_only: When True, skip persistence (for testing).
        """
        self._in_memory_only = in_memory_only
        self._storage_path = storage_path or DEFAULT_STORAGE_PATH

        # In-memory store: session_id -> EngineeringSessionRecord
        self._sessions: dict[str, EngineeringSessionRecord] = {}

        # Storage instance (only used when not in_memory_only)
        if not in_memory_only:
            self._storage = MemoryStorage(storage_path=self._storage_path)
        else:
            self._storage = MemoryStorage(storage_path=":memory:")

    @property
    def storage_path(self) -> str:
        """Path to the storage file."""
        return self._storage_path

    @property
    def session_count(self) -> int:
        """Number of stored sessions."""
        return len(self._sessions)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(self, record: EngineeringSessionRecord) -> None:
        """Store a completed engineering session record.

        This is the ONLY method that writes to memory. It is called by
        the EngineeringController after a session completes.

        Duplicate session_ids are silently ignored — the first stored
        record for a session_id is preserved.

        Args:
            record: The engineering session record to store.
        """
        # Never modify existing records — first write wins
        if record.session_id in self._sessions:
            return

        self._sessions[record.session_id] = record

        # Persist to disk (unless in-memory only mode)
        if not self._in_memory_only:
            self._persist()

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def find_session(self, session_id: str) -> EngineeringSessionRecord | None:
        """Find a session by its ID.

        Args:
            session_id: The session ID to look up.

        Returns:
            The EngineeringSessionRecord if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> tuple[EngineeringSessionRecord, ...]:
        """List all stored sessions.

        Returns:
            Tuple of all sessions, sorted by session_id (deterministic).
        """
        return tuple(
            sorted(
                self._sessions.values(),
                key=lambda r: (r.session_id, r.completed_at),
            )
        )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def find_by_workflow(self, workflow_name: str) -> tuple[EngineeringSessionRecord, ...]:
        """Find sessions by workflow name.

        Args:
            workflow_name: The workflow name to filter by.

        Returns:
            Tuple of matching sessions, sorted by session_id (deterministic).
        """
        results = [
            r for r in self._sessions.values()
            if r.workflow_name == workflow_name
        ]
        return tuple(sorted(results, key=lambda r: (r.session_id, r.completed_at)))

    def find_successful(self) -> tuple[EngineeringSessionRecord, ...]:
        """Find all successful sessions.

        A session is successful if its controller_decision is "COMPLETE".

        Returns:
            Tuple of successful sessions, sorted by session_id (deterministic).
        """
        results = [
            r for r in self._sessions.values()
            if r.controller_decision == "COMPLETE"
        ]
        return tuple(sorted(results, key=lambda r: (r.session_id, r.completed_at)))

    def find_failed(self) -> tuple[EngineeringSessionRecord, ...]:
        """Find all failed sessions.

        A session is failed if its controller_decision is NOT "COMPLETE".

        Returns:
            Tuple of failed sessions, sorted by session_id (deterministic).
        """
        results = [
            r for r in self._sessions.values()
            if r.controller_decision != "COMPLETE"
        ]
        return tuple(sorted(results, key=lambda r: (r.session_id, r.completed_at)))

    def find_by_module(self, module_name: str) -> tuple[EngineeringSessionRecord, ...]:
        """Find sessions that modified a specific module.

        Searches the metadata's modified_modules field.

        Args:
            module_name: The module name to search for.

        Returns:
            Tuple of matching sessions, sorted by session_id (deterministic).
        """
        results = []
        for record in self._sessions.values():
            if module_name in record.modified_modules:
                results.append(record)
        return tuple(sorted(results, key=lambda r: (r.session_id, r.completed_at)))

    def recent(self, limit: int) -> tuple[EngineeringSessionRecord, ...]:
        """Get the most recent sessions.

        Sessions are sorted by completed_at descending, then by session_id
        ascending as a tiebreaker.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            Tuple of the most recent sessions (up to limit).
        """
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda r: (r.completed_at, r.session_id),
            reverse=True,
        )
        return tuple(sorted_sessions[:limit])

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def statistics(self) -> MemoryStatistics:
        """Compute statistics about stored sessions.

        Returns:
            MemoryStatistics with computed metrics.
        """
        all_sessions = list(self._sessions.values())
        total = len(all_sessions)

        if total == 0:
            return MemoryStatistics()

        successful = [r for r in all_sessions if r.controller_decision == "COMPLETE"]
        failed = [r for r in all_sessions if r.controller_decision != "COMPLETE"]

        # Calculate average evaluation score
        scores = [
            r.evaluation_score
            for r in all_sessions
            if r.evaluation_score is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Calculate average iterations
        iterations = [r.iteration_count for r in all_sessions]
        avg_iterations = sum(iterations) / len(iterations) if iterations else 0.0

        # Calculate workflow usage
        workflow_usage: dict[str, int] = {}
        for r in all_sessions:
            workflow_usage[r.workflow_name] = workflow_usage.get(r.workflow_name, 0) + 1

        return MemoryStatistics(
            total_sessions=total,
            successful_sessions=len(successful),
            failed_sessions=len(failed),
            average_evaluation_score=round(avg_score, 6),
            average_iterations=round(avg_iterations, 6),
            workflow_usage=workflow_usage,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Persist all sessions to disk.

        Called after each store operation (unless in_memory_only is True).
        """
        if self._in_memory_only:
            return

        all_sessions = list(self._sessions.values())
        self._storage.save(all_sessions)

    def reload(self) -> int:
        """Reload sessions from disk.

        Clears in-memory state and reloads from the storage file.

        Returns:
            Number of sessions reloaded.
        """
        loaded = self._storage.load()
        self._sessions.clear()
        for record in loaded:
            self._sessions[record.session_id] = record
        return len(loaded)

    def clear(self) -> None:
        """Clear all stored sessions (both in-memory and persistent)."""
        self._sessions.clear()
        if not self._in_memory_only:
            self._storage.clear()

    # ------------------------------------------------------------------
    # Duplicate prevention
    # ------------------------------------------------------------------

    def has_session(self, session_id: str) -> bool:
        """Check if a session already exists in memory.

        Args:
            session_id: The session ID to check.

        Returns:
            True if the session exists, False otherwise.
        """
        return session_id in self._sessions

    def store_if_new(self, record: EngineeringSessionRecord) -> bool:
        """Store a record only if it doesn't already exist.

        Args:
            record: The engineering session record to store.

        Returns:
            True if the record was stored, False if it was a duplicate.
        """
        if record.session_id in self._sessions:
            return False
        self.store(record)
        return True