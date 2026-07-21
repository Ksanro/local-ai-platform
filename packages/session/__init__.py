"""Engineering Session Framework v1.

Deterministic execution session spanning an entire engineering request.

The Session owns every artifact produced during execution.
It is the root object for future UI, CLI, IDE integration and
long-running engineering work.

Architecture
------------

EngineeringRequest
       |
       v
EngineeringSession
       |
       ├── WorkflowPlan
       ├── ExecutionPlan
       ├── EvaluationReport
       ├── PatchSet
       ├── WorkspaceChanges
       ├── VerificationReport
       ├── Telemetry
       └── FinalEngineeringReport

Everything belongs to one Session.

Non-responsibilities
--------------------

- NEVER performs engineering work
- NEVER invokes providers
- NEVER performs repository analysis
- ONLY coordinates lifecycle

Public API
----------

.. code-block:: python

    from packages.session import (
        EngineeringSession,
        SessionArtifact,
        SessionManager,
        SessionRegistry,
        SessionSnapshot,
        SessionStatus,
        SessionStatistics,
    )

    manager = SessionManager()
    session = manager.create(
        request_id="req-001",
        workflow_name="bug-investigation",
    )

"""

from __future__ import annotations

__all__ = [
    # Models
    "EngineeringSession",
    "SessionArtifact",
    "SessionSnapshot",
    "SessionStatistics",
    "SessionStatus",
    # Lifecycle
    "LifecycleError",
    "transition",
    "validate_transition",
    # Manager
    "SessionManager",
    # Persistence
    "SessionPersistence",
    # Registry
    "SessionRegistry",
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

from packages.session.models import (
    EngineeringSession,
    SessionArtifact,
    SessionSnapshot,
    SessionStatistics,
    SessionStatus,
)

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

from packages.session.lifecycle import (
    LifecycleError,
    transition,
    validate_transition,
)

# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

from packages.session.manager import SessionManager

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

from packages.session.persistence import SessionPersistence

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from packages.session.registry import SessionRegistry