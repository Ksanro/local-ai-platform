"""Code Modification Engine package.

Applies PatchSet objects to a workspace. The engine is responsible only
for applying patches - it never generates patches, performs repository
intelligence, or invokes providers.

Architecture
------------

PatchSet --> CodeModificationEngine --> WorkspaceChanges

Responsibilities
----------------

- Validate PatchSet before execution.
- Create backup before modification.
- Apply patches in deterministic order.
- Collect statistics.
- Rollback on failure.
- Produce immutable WorkspaceChanges.

Non-responsibilities
--------------------

- Must NOT generate patches.
- Must NOT inspect repository semantics.
- Must NOT perform AST parsing.
- Must NOT invoke providers.
- Must NOT decide WHAT to change.

Public API
----------

.. code-block:: python

    from packages.modification import (
        CodeModificationEngine,
        ModifiedFile,
        ModificationStatistics,
        ModificationStatus,
        WorkspaceChanges,
    )
    from packages.modification.backup import BackupManager
    from packages.modification.validator import ModificationValidator
    from packages.modification.workspace import WorkspaceFileSystem

"""

from __future__ import annotations

from packages.modification.engine import CodeModificationEngine
from packages.modification.models import (
    ModifiedFile,
    ModificationStatistics,
    ModificationStatus,
    WorkspaceChanges,
)
from packages.modification.validator import ModificationValidator
from packages.modification.workspace import WorkspaceFileSystem

__all__ = [
    # Engine
    "CodeModificationEngine",
    # Models
    "ModifiedFile",
    "ModificationStatistics",
    "ModificationStatus",
    "WorkspaceChanges",
    # Validator
    "ModificationValidator",
    # Workspace
    "WorkspaceFileSystem",
]