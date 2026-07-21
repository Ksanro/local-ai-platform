"""Session persistence — metadata-only save/load operations.

Never persists providers, RepositoryIndex, or mutable runtime objects.
Only session metadata is persisted.

Architecture
------------

SessionPersistence handles:
- Saving session metadata to disk
- Loading session metadata from disk
- Creating deterministic JSON snapshots

Constraints
-----------

- Never persist providers.
- Never persist RepositoryIndex.
- Never persist mutable runtime objects.
- Metadata only.
- Deterministic JSON output.

Public API
----------

.. code-block:: python

    from packages.session.persistence import SessionPersistence
    from pathlib import Path

    persistence = SessionPersistence(Path("./sessions"))

    # Save session metadata
    path = persistence.save(session)

    # Load session metadata
    loaded = persistence.load("sess-001")

    # Deterministic JSON snapshot
    json_str = persistence.snapshot(session)

"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.session.models import EngineeringSession

__all__ = [
    "SessionPersistence",
]


class SessionPersistence:
    """Metadata-only session persistence.

    Handles saving, loading, and snapshotting session metadata.
    Never persists providers, RepositoryIndex, or mutable runtime objects.

    Attributes:
        base_dir: The base directory for session storage.
    """

    def __init__(self, base_dir: Path | str = "./sessions") -> None:
        """Initialize persistence with base directory.

        Args:
            base_dir: Base directory for session storage.
        """
        self.base_dir = Path(base_dir) if isinstance(base_dir, str) else base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: EngineeringSession) -> Path:
        """Save session metadata to disk.

        Writes only the session metadata to a JSON file.
        Does NOT persist providers, RepositoryIndex, or runtime objects.

        Args:
            session: The session to save.

        Returns:
            Path to the saved file.
        """
        file_path = self.base_dir / f"{session.session_id}.json"
        data = self._serialize(session)
        file_path.write_text(json.dumps(data, indent=2, sort_keys=True))
        return file_path

    def load(self, session_id: str) -> EngineeringSession | None:
        """Load session metadata from disk.

        Reads and deserializes session metadata from a JSON file.

        Args:
            session_id: The session identifier to load.

        Returns:
            The loaded EngineeringSession, or None if not found.
        """
        file_path = self.base_dir / f"{session_id}.json"
        if not file_path.exists():
            return None

        data = json.loads(file_path.read_text())
        return self._deserialize(data)

    def snapshot(self, session: EngineeringSession) -> str:
        """Create a deterministic JSON snapshot of a session.

        Returns a deterministic JSON string representation of the session.
        Does NOT include providers, RepositoryIndex, or runtime objects.

        Args:
            session: The session to snapshot.

        Returns:
            Deterministic JSON string.
        """
        data = self._serialize(session)
        return json.dumps(data, indent=2, sort_keys=True)

    def _serialize(self, session: EngineeringSession) -> dict[str, Any]:
        """Serialize a session to a dictionary.

        Args:
            session: The session to serialize.

        Returns:
            Dictionary representation of the session.
        """
        return {
            "created_at": session.created_at,
            "evaluation_id": session.evaluation_id,
            "execution_id": session.execution_id,
            "metadata": session.metadata,
            "request_id": session.request_id,
            "session_id": session.session_id,
            "status": session.status.value,
            "updated_at": session.updated_at,
            "verification_id": session.verification_id,
            "workflow_name": session.workflow_name,
        }

    def _deserialize(self, data: dict[str, Any]) -> EngineeringSession:
        """Deserialize a session from a dictionary.

        Args:
            data: Dictionary representation of a session.

        Returns:
            EngineeringSession instance.
        """
        from packages.session.models import SessionStatus

        return EngineeringSession(
            session_id=data["session_id"],
            request_id=data["request_id"],
            status=SessionStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            workflow_name=data.get("workflow_name", ""),
            execution_id=data.get("execution_id", ""),
            evaluation_id=data.get("evaluation_id", ""),
            verification_id=data.get("verification_id", ""),
            metadata=data.get("metadata", {}),
        )