"""Session registry for deterministic storage and lookup.

Provides instance-bound storage with insertion-order preservation.
No global mutable state, no singletons.

Architecture
------------

The registry is the sole storage mechanism for engineering sessions.
It provides deterministic ordering, lookup, and discovery.

Constraints
-----------

- Instance-bound (no global mutable state).
- Deterministic ordering by insertion time.
- No singletons.
- Returns copies for external mutations.

Public API
----------

.. code-block:: python

    from packages.session.registry import SessionRegistry

    registry = SessionRegistry()
    registry.register(session)
    session = registry.get("sess-001")
    all_sessions = registry.all()

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.session.models import EngineeringSession

if TYPE_CHECKING:
    from typing import Dict

__all__ = [
    "SessionRegistry",
]


class SessionRegistry:
    """Deterministic session registry.

    Provides storage, lookup, and discovery for engineering sessions.
    All operations are instance-bound — no global mutable state.

    Attributes:
        _sessions: Internal storage mapping session_id to EngineeringSession.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._sessions: dict[str, EngineeringSession] = {}

    def register(self, session: EngineeringSession) -> None:
        """Register a session in the registry.

        Adds the session to the registry. If a session with the same
        session_id already exists, it will be overwritten.

        Args:
            session: The session to register.
        """
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> EngineeringSession | None:
        """Get a session by its ID.

        Args:
            session_id: The session identifier.

        Returns:
            The EngineeringSession if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def all(self) -> dict[str, EngineeringSession]:
        """Get a copy of all registered sessions.

        Returns a new dictionary — mutations to the returned dict
        do not affect the registry.

        Returns:
            A copy of all registered sessions.
        """
        return dict(self._sessions)

    def remove(self, session_id: str) -> bool:
        """Remove a session from the registry.

        Args:
            session_id: The session identifier to remove.

        Returns:
            True if the session was found and removed, False otherwise.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False