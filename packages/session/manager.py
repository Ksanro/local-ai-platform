"""Session manager — public API for session lifecycle management.

Provides the high-level interface for creating, updating, and managing
engineering sessions. Enforces lifecycle constraints and artifact ownership.

Architecture
------------

SessionManager is the sole public API for session operations.
It delegates to:
- SessionRegistry for storage
- lifecycle for state transitions
- models for immutable data structures

Constraints
-----------

- NEVER performs engineering work.
- NEVER invokes providers.
- NEVER performs repository analysis.
- ONLY coordinates lifecycle.
- Enforces deterministic lifecycle transitions.
- Tracks artifact ownership.

Public API
----------

.. code-block:: python

    from packages.session.manager import SessionManager
    from packages.session.models import SessionArtifact, SessionStatus

    manager = SessionManager()

    # Create a session
    session = manager.create(
        request_id="req-001",
        workflow_name="bug-investigation",
    )

    # Update status
    session = manager.update_status(session.session_id, SessionStatus.PLANNING)

    # Attach artifact
    artifact = SessionArtifact(
        artifact_type="WorkflowPlan",
        artifact_id="plan-001",
    )
    session = manager.attach_artifact(session.session_id, artifact)

    # Take snapshot
    snapshot = manager.snapshot(session.session_id)

    # Close session
    session = manager.close(session.session_id)

"""

from __future__ import annotations

from datetime import datetime, timezone

from packages.session.lifecycle import transition
from packages.session.models import (
    EngineeringSession,
    SessionArtifact,
    SessionSnapshot,
    SessionStatistics,
    SessionStatus,
)
from packages.session.registry import SessionRegistry


class SessionManager:
    """Public API for session lifecycle management.

    Provides deterministic lifecycle enforcement, artifact ownership
    tracking, and immutable snapshot creation.

    Attributes:
        registry: The session registry used for storage.
        _artifacts: Internal mapping of session_id to artifacts.
        _statistics: Internal mapping of session_id to statistics.
    """

    def __init__(self, registry: SessionRegistry | None = None) -> None:
        """Initialize the session manager.

        Args:
            registry: Optional registry. Creates a new one if not provided.
        """
        self.registry = registry if registry is not None else SessionRegistry()
        self._artifacts: dict[str, list[SessionArtifact]] = {}
        self._statistics: dict[str, SessionStatistics] = {}

    def create(
        self,
        request_id: str,
        workflow_name: str,
        metadata: dict[str, object] | None = None,
    ) -> EngineeringSession:
        """Create a new engineering session.

        Creates a session in the CREATED status and registers it.

        Args:
            request_id: The associated request identifier.
            workflow_name: The workflow name for this session.
            metadata: Optional additional metadata.

        Returns:
            The newly created EngineeringSession.
        """
        session_id = f"sess-{request_id}"

        session = EngineeringSession(
            session_id=session_id,
            request_id=request_id,
            status=SessionStatus.CREATED,
            workflow_name=workflow_name,
            metadata=metadata or {},
        )

        self.registry.register(session)
        self._artifacts[session_id] = []
        self._statistics[session_id] = SessionStatistics()

        return session

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
    ) -> EngineeringSession:
        """Update a session's status with lifecycle validation.

        Validates the lifecycle transition and updates the session.

        Args:
            session_id: The session identifier.
            status: The new status.

        Returns:
            The updated EngineeringSession.

        Raises:
            ValueError: If the session is not found.
            LifecycleError: If the transition is invalid.
        """
        session = self.registry.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        updated = transition(session, status)
        self.registry.register(updated)
        return updated

    def attach_artifact(
        self,
        session_id: str,
        artifact: SessionArtifact,
    ) -> EngineeringSession:
        """Attach an artifact to a session.

        Records the artifact in the session's artifact list.

        Args:
            session_id: The session identifier.
            artifact: The artifact to attach.

        Returns:
            The updated EngineeringSession.

        Raises:
            ValueError: If the session is not found.
        """
        session = self.registry.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if session_id not in self._artifacts:
            self._artifacts[session_id] = []

        self._artifacts[session_id].append(artifact)
        return session

    def snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """Create a deterministic snapshot of a session.

        Returns a point-in-time view of the session state including
        all artifacts and statistics.

        Args:
            session_id: The session identifier.

        Returns:
            A SessionSnapshot.

        Raises:
            ValueError: If the session is not found.
        """
        session = self.registry.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        artifacts = tuple(self._artifacts.get(session_id, []))
        statistics = self._statistics.get(session_id, SessionStatistics())

        return SessionSnapshot(
            session=session,
            artifacts=artifacts,
            statistics=statistics,
        )

    def close(
        self,
        session_id: str,
    ) -> EngineeringSession:
        """Close a session by transitioning to COMPLETED.

        Validates the lifecycle transition to COMPLETED and returns
        the updated session.

        Args:
            session_id: The session identifier.

        Returns:
            The updated EngineeringSession.

        Raises:
            ValueError: If the session is not found.
            LifecycleError: If the transition is invalid.
        """
        session = self.registry.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        updated = transition(session, SessionStatus.COMPLETED)
        self.registry.register(updated)
        return updated

    def get_statistics(
        self,
        session_id: str,
    ) -> SessionStatistics:
        """Get statistics for a session.

        Args:
            session_id: The session identifier.

        Returns:
            The session statistics, or default if none exist.
        """
        return self._statistics.get(session_id, SessionStatistics())

    def update_statistics(
        self,
        session_id: str,
        statistics: SessionStatistics,
    ) -> None:
        """Update statistics for a session.

        Args:
            session_id: The session identifier.
            statistics: The new statistics.
        """
        self._statistics[session_id] = statistics