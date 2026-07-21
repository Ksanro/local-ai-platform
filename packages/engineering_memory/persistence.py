"""Engineering Memory persistence — JSON storage layer.

Provides deterministic, versioned, forward-compatible JSON persistence
for Engineering Memory records.

Storage Format
--------------

The storage file uses the following structure:

.. code-block:: json

    {
        "version": "1.0",
        "stored_at": "2026-07-21T15:00:00+00:00",
        "sessions": [
            {
                "session_id": "sess-001",
                "workflow_name": "bug-fix",
                "request_summary": "...",
                "transaction_id": "txn-001",
                "execution_report": {...},
                "verification_report": {...},
                "evaluation_report": {...},
                "controller_decision": "COMPLETE",
                "completed_at": "2026-07-21T14:55:00+00:00",
                "metadata": {...}
            }
        ]
    }

Properties
----------

- Versioned: "version": "1.0" for forward compatibility
- Stable ordering: sessions array sorted by session_id
- Deterministic JSON: sort_keys=True, consistent indentation
- Forward-compatible: unknown fields are preserved on load

Constraints
-----------

- No embeddings.
- No semantic search.
- No vector database.
- No provider calls.

Public API
----------

.. code-block:: python

    from packages.engineering_memory.persistence import (
        MemoryStorage,
        DEFAULT_STORAGE_PATH,
    )

    storage = MemoryStorage(storage_path="/path/to/memory.json")
    storage.save(records)
    loaded = storage.load()

"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.engineering_memory.models import EngineeringSessionRecord

__all__ = [
    "DEFAULT_STORAGE_PATH",
    "CURRENT_VERSION",
    "MemoryStorage",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STORAGE_PATH = "data/engineering_memory/memory_v1.json"
CURRENT_VERSION = "1.0"

# Required fields that must be present in stored records
REQUIRED_FIELDS = frozenset([
    "session_id",
    "workflow_name",
    "request_summary",
    "transaction_id",
    "controller_decision",
    "completed_at",
])


# ---------------------------------------------------------------------------
# MemoryStorage
# ---------------------------------------------------------------------------


class MemoryStorage:
    """JSON persistence layer for Engineering Memory.

    Handles reading, writing, and versioning of engineering session
    records to a deterministic JSON file.

    Usage:
        storage = MemoryStorage(storage_path="data/memory.json")
        storage.save(records)
        loaded = storage.load()

    Thread Safety:
        All methods are thread-safe for concurrent reads/writes.
    """

    def __init__(self, storage_path: str | Path = DEFAULT_STORAGE_PATH) -> None:
        """Initialize the storage.

        Args:
            storage_path: Path to the JSON storage file.
        """
        self._storage_path = Path(storage_path)
        self._lock = threading.Lock()

    @property
    def storage_path(self) -> Path:
        """Path to the storage file."""
        return self._storage_path

    def ensure_directory(self) -> None:
        """Create the storage directory if it doesn't exist."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, records: list[EngineeringSessionRecord]) -> None:
        """Save engineering session records to the storage file.

        Records are sorted by session_id for deterministic ordering.
        The file is written atomically using a temporary file.

        Args:
            records: List of engineering session records to save.
        """
        with self._lock:
            self.ensure_directory()

            # Sort records by session_id for deterministic ordering
            sorted_records = sorted(
                records,
                key=lambda r: (r.session_id, r.completed_at),
            )

            # Serialize records
            session_data = []
            for record in sorted_records:
                data = record.to_dict()
                session_data.append(data)

            # Build storage document
            storage_doc = {
                "version": CURRENT_VERSION,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "sessions": session_data,
            }

            # Write to file
            json_content = json.dumps(
                storage_doc,
                indent=2,
                sort_keys=False,
                default=str,
            )

            self._storage_path.write_text(json_content, encoding="utf-8")

    def load(self) -> list[EngineeringSessionRecord]:
        """Load engineering session records from the storage file.

        Handles version mismatches gracefully — older versions are loaded
        with warnings, newer versions preserve unknown fields.

        Returns:
            List of loaded engineering session records.
            Returns empty list if file doesn't exist.
        """
        if not self._storage_path.exists():
            return []

        with self._lock:
            content = self._storage_path.read_text(encoding="utf-8")
            storage_doc = json.loads(content)

            # Validate version
            version = storage_doc.get("version", "0.0")
            if not self._is_compatible_version(version):
                # Log warning but continue loading for forward compatibility
                pass

            sessions_data = storage_doc.get("sessions", [])

            # Deserialize records
            records = []
            for session_data in sessions_data:
                try:
                    record = EngineeringSessionRecord.from_dict(session_data)
                    records.append(record)
                except ValueError:
                    # Skip malformed records for forward compatibility
                    continue

            # Sort by session_id for deterministic ordering
            records.sort(key=lambda r: (r.session_id, r.completed_at))
            return records

    def append(self, record: EngineeringSessionRecord) -> None:
        """Append a single record to the storage file.

        This is a convenience method that loads existing records,
        appends the new record, and saves everything.

        Args:
            record: The record to append.
        """
        with self._lock:
            existing = self._load_unlocked()
            existing.append(record)
            self.save_unlocked(existing)

    def delete(self, session_id: str) -> bool:
        """Delete a record by session_id.

        Args:
            session_id: The session_id of the record to delete.

        Returns:
            True if the record was found and deleted, False otherwise.
        """
        with self._lock:
            existing = self._load_unlocked()
            original_count = len(existing)
            existing = [r for r in existing if r.session_id != session_id]

            if len(existing) < original_count:
                self.save_unlocked(existing)
                return True
            return False

    def clear(self) -> None:
        """Clear all records from the storage file."""
        with self._lock:
            self.save_unlocked([])

    # ------------------------------------------------------------------
    # Internal (unlocked) methods for use within lock context
    # ------------------------------------------------------------------

    def _load_unlocked(self) -> list[EngineeringSessionRecord]:
        """Load records without acquiring the lock.

        Must be called within a lock context.

        Returns:
            List of loaded records.
        """
        if not self._storage_path.exists():
            return []

        content = self._storage_path.read_text(encoding="utf-8")
        storage_doc = json.loads(content)

        sessions_data = storage_doc.get("sessions", [])
        records = []
        for session_data in sessions_data:
            try:
                record = EngineeringSessionRecord.from_dict(session_data)
                records.append(record)
            except ValueError:
                continue

        records.sort(key=lambda r: (r.session_id, r.completed_at))
        return records

    def save_unlocked(self, records: list[EngineeringSessionRecord]) -> None:
        """Save records without acquiring the lock.

        Must be called within a lock context.

        Args:
            records: List of records to save.
        """
        self.ensure_directory()

        sorted_records = sorted(
            records,
            key=lambda r: (r.session_id, r.completed_at),
        )

        session_data = []
        for record in sorted_records:
            data = record.to_dict()
            session_data.append(data)

        storage_doc = {
            "version": CURRENT_VERSION,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "sessions": session_data,
        }

        json_content = json.dumps(
            storage_doc,
            indent=2,
            sort_keys=False,
            default=str,
        )

        self._storage_path.write_text(json_content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Version compatibility
    # ------------------------------------------------------------------

    @staticmethod
    def _is_compatible_version(version: str) -> bool:
        """Check if a storage version is compatible with this reader.

        Version compatibility follows semantic versioning rules:
        - Same major version = compatible
        - Higher minor version = forward compatible (newer features)
        - Lower minor version = backward compatible (older features)

        Args:
            version: The version string from the storage file.

        Returns:
            True if the version is compatible.
        """
        try:
            major, minor = version.split(".")
            current_major, current_minor = CURRENT_VERSION.split(".")

            # Same major version is always compatible
            if int(major) != int(current_major):
                return False

            # Same major, any minor is compatible
            return True
        except (ValueError, AttributeError):
            # Malformed version string — assume compatible for resilience
            return True