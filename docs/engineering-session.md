# Engineering Session Framework v1

## Overview

The Engineering Session Framework provides a deterministic execution session spanning an entire engineering request. It is the root object for future UI, CLI, IDE integration and long-running engineering work.

**The Session owns every artifact produced during execution.**

## Architecture

```
EngineeringRequest
       │
       ▼
EngineeringSession
       │
       ├── WorkflowPlan
       ├── ExecutionPlan
       ├── EvaluationReport
       ├── PatchSet
       ├── WorkspaceChanges
       ├── VerificationReport
       ├── Telemetry
       └── FinalEngineeringReport
```

Everything belongs to one Session.

## Non-Responsibilities

The Session Framework is purely a coordination and ownership layer. It **NEVER**:

- Performs engineering work
- Invokes providers
- Performs repository analysis
- Replaces existing frameworks

It **ONLY** coordinates lifecycle.

## Session Lifecycle

```
CREATED --> PLANNING --> EXECUTING --> VERIFYING --> COMPLETED
   │           │            │            │
   ▼           ▼            ▼            ▼
 FAILED      FAILED       FAILED       FAILED
   │
 CANCELLED (terminal)
```

### Allowed Transitions

| Current     | Allowed Targets                          |
|-------------|------------------------------------------|
| CREATED     | PLANNING, FAILED, CANCELLED              |
| PLANNING    | EXECUTING, FAILED, CANCELLED             |
| EXECUTING   | VERIFYING, FAILED, CANCELLED             |
| VERIFYING   | COMPLETED, FAILED, CANCELLED             |
| COMPLETED   | *(none - terminal)*                      |
| FAILED      | *(none - terminal)*                      |
| CANCELLED   | *(none - terminal)*                      |

### Invalid Transitions

- Cannot transition from terminal states (COMPLETED, FAILED, CANCELLED)
- Cannot skip phases (e.g., CREATED → EXECUTING)
- Cannot transition to the same state (e.g., CREATED → CREATED)

## Ownership Model

### Session Ownership

The `EngineeringSession` is the root object. It owns:

- All artifacts attached via `SessionManager.attach_artifact()`
- All statistics tracked via `SessionManager.update_statistics()`
- All lifecycle state transitions

### Artifact Ownership

Artifacts are attached to sessions via `SessionArtifact`:

```python
artifact = SessionArtifact(
    artifact_type="WorkflowPlan",
    artifact_id="plan-001",
    metadata={"files_count": 5},
)
manager.attach_artifact(session.session_id, artifact)
```

### Statistics Ownership

Statistics are tracked per session:

```python
stats = SessionStatistics(
    workflows=3,
    executions=5,
    evaluations=2,
    patches=4,
    modifications=3,
    verifications=2,
    duration_ms=10000,
)
manager.update_statistics(session.session_id, stats)
```

## Artifact Model

### SessionArtifact

```python
@dataclass(frozen=True, slots=True)
class SessionArtifact:
    artifact_type: str           # e.g. "WorkflowPlan", "PatchSet"
    artifact_id: str             # Unique artifact identifier
    created_at: str              # ISO timestamp
    metadata: dict[str, Any]     # Additional metadata
```

### SessionStatistics

```python
@dataclass(frozen=True, slots=True)
class SessionStatistics:
    workflows: int = 0           # Total workflows executed
    executions: int = 0          # Total executions
    evaluations: int = 0         # Total evaluations
    patches: int = 0             # Total patches generated
    modifications: int = 0       # Total code modifications
    verifications: int = 0       # Total verifications
    duration_ms: int = 0         # Total duration
```

### SessionSnapshot

```python
@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session: EngineeringSession           # The session itself
    artifacts: tuple[SessionArtifact, ...]  # All attached artifacts
    statistics: SessionStatistics           # Session statistics
```

## Persistence Boundaries

### What IS Persisted

- Session metadata (session_id, request_id, status, timestamps)
- Workflow name, execution ID, evaluation ID, verification ID
- Session metadata dictionary

### What is NOT Persisted

- **Providers** — Never persist provider configurations
- **RepositoryIndex** — Never persist mutable repository indices
- **Runtime objects** — Never persist mutable runtime state
- **Artifacts** — Artifacts are tracked but not persisted with the session

### Persistence API

```python
from packages.session.persistence import SessionPersistence
from pathlib import Path

persistence = SessionPersistence(Path("./sessions"))

# Save session metadata
path = persistence.save(session)

# Load session metadata
loaded = persistence.load("sess-001")

# Deterministic JSON snapshot
json_str = persistence.snapshot(session)
```

## Integration with Autonomous Engineering

The Session Framework integrates with the Autonomous Engineering Framework:

```
EngineeringRequest
       │
       ▼
EngineeringSession (CREATED)
       │
       ├── WorkflowPlan ──────────────┐
       ├── ExecutionPlan              │
       ├── EvaluationReport           │
       ├── PatchSet                   │
       ├── WorkspaceChanges           │
       ├── VerificationReport         │
       ├── Telemetry                  │
       ├── FinalEngineeringReport     │
       │                               │
       └── AutonomousEngine ──────────┘
```

The session wraps the entire autonomous execution lifecycle:

1. **CREATED** → Session is created
2. **PLANNING** → AutonomousEngine creates the workflow plan
3. **EXECUTING** → AutonomousEngine executes iterations
4. **VERIFYING** → Self-verification runs
5. **COMPLETED** → Final report is produced

## Public API

### Models

```python
from packages.session.models import (
    EngineeringSession,    # Immutable session model
    SessionArtifact,       # Immutable artifact model
    SessionSnapshot,       # Immutable snapshot model
    SessionStatistics,     # Immutable statistics model
    SessionStatus,         # Session status enum
)
```

### Lifecycle

```python
from packages.session.lifecycle import (
    LifecycleError,        # Lifecycle transition error
    validate_transition,   # Validate transition
    transition,            # Apply transition
)
```

### Manager

```python
from packages.session.manager import SessionManager

manager = SessionManager()

# Create session
session = manager.create(
    request_id="req-001",
    workflow_name="bug-investigation",
    metadata={"priority": "high"},
)

# Update status
session = manager.update_status(
    session.session_id,
    SessionStatus.PLANNING,
)

# Attach artifact
artifact = SessionArtifact(
    artifact_type="WorkflowPlan",
    artifact_id="plan-001",
)
manager.attach_artifact(session.session_id, artifact)

# Take snapshot
snapshot = manager.snapshot(session.session_id)

# Close session
session = manager.close(session.session_id)
```

### Registry

```python
from packages.session.registry import SessionRegistry

registry = SessionRegistry()
registry.register(session)
session = registry.get("sess-001")
all_sessions = registry.all()
registry.remove("sess-001")
```

### Persistence

```python
from packages.session.persistence import SessionPersistence
from pathlib import Path

persistence = SessionPersistence(Path("./sessions"))
path = persistence.save(session)
loaded = persistence.load("sess-001")
json_str = persistence.snapshot(session)
```

## Usage Example

```python
from packages.session import SessionManager, SessionStatus, SessionArtifact

# Create manager
manager = SessionManager()

# Create session
session = manager.create(
    request_id="req-001",
    workflow_name="bug-investigation",
)

# Transition through lifecycle
session = manager.update_status(session.session_id, SessionStatus.PLANNING)
session = manager.update_status(session.session_id, SessionStatus.EXECUTING)
session = manager.update_status(session.session_id, SessionStatus.VERIFYING)

# Attach artifacts during execution
plan_artifact = SessionArtifact(
    artifact_type="WorkflowPlan",
    artifact_id="plan-001",
)
manager.attach_artifact(session.session_id, plan_artifact)

# Close session
session = manager.close(session.session_id)

# Take final snapshot
snapshot = manager.snapshot(session.session_id)
```

## Design Principles

1. **Immutability** — All models use frozen dataclasses with slots
2. **Determinism** — All operations are deterministic and reproducible
3. **Ownership** — Session owns all artifacts produced during execution
4. **Separation** — Session never performs engineering work
5. **Metadata-only** — Only metadata is persisted, never runtime objects
6. **Strict lifecycle** — Invalid transitions are rejected with explicit errors
7. **No singletons** — All components are instance-bound
8. **Explicit exports** — All modules have explicit `__all__` lists