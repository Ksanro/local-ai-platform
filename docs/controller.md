# Engineering Controller v1

## Single Public Orchestration Entry Point

The Engineering Controller is the **ONLY** public API exposed to future:
- CLI
- VSCode Extension
- JetBrains Plugin
- Web UI
- REST API
- MCP Server
- Agent integrations

Everything else (Workflows, Tasks, Evaluation, Verification, Sessions, Execution) becomes internal implementation.

---

## Architecture

```
User Request
    │
    ▼
EngineeringController  ← SINGLE ENTRY POINT
    │
    ├── SessionManager (lifecycle)
    ├── WorkflowEngine (orchestration)
    ├── ExecutionEngine (execution)
    ├── EvaluationFramework (evaluation)
    ├── PatchGenerator (patches)
    ├── CodeModificationEngine (apply patches)
    ├── SelfVerification (verification)
    ├── Observability (telemetry)
    └── AutonomousEngineering (optional)
    │
    ▼
EngineeringResult
```

### Before Controller (Current)

```
External Consumer (CLI/Extension/UI/API)
    │
    ├──→ SessionManager (lifecycle only)
    ├──→ WorkflowEngine (plan generation)
    ├──→ ExecutionEngine (execution)
    ├──→ WorkflowEvaluator (evaluation)
    ├──→ PatchGenerator (patch generation)
    ├──→ CodeModificationEngine (apply patches)
    ├──→ SelfVerificationEngine (verification)
    └──→ EngineeringTelemetry (observability)
```

**Problem:** Every consumer must know about 9+ internal packages.

### After Controller (Target)

```
External Consumer (CLI/Extension/UI/API)
    │
    ▼
EngineeringController  ← ONLY KNOWN PACKAGE
    │
    └──→ Everything else is internal
```

**Result:** Consumers know ONLY about `EngineeringController`.

---

## Public API

### EngineeringRequest (Input)

```python
@dataclass(frozen=True, slots=True)
class EngineeringRequest:
    """Canonical engineering request that flows through the controller.

    Attributes:
        request_id: Unique request identifier.
        operation: Type of operation (execute, review, implement, refactor, debug, explain).
        description: Human-readable description of the engineering task.
        workspace_path: Target workspace path.
        workflow_name: Optional specific workflow to use.
        context: Additional context (files, code snippets, constraints).
        metadata: Free-form metadata for extensibility.
    """
    request_id: str
    operation: OperationType
    description: str
    workspace_path: str = ""
    workflow_name: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### EngineeringResult (Output)

```python
@dataclass(frozen=True, slots=True)
class EngineeringResult:
    """Canonical result returned by every controller operation.

    Attributes:
        request_id: Associated request identifier.
        session_id: Associated session identifier.
        operation: Operation that was performed.
        status: Final operation status (SUCCESS, FAILED, PARTIAL).
        workflow_plan: Generated workflow plan (if applicable).
        execution_report: Execution report (if applicable).
        evaluation_report: Evaluation report (if applicable).
        patch_set: Generated patch set (if applicable).
        workspace_changes: Applied workspace changes (if applicable).
        verification_report: Self-verification report (if applicable).
        final_report: Final engineering report (if applicable).
        telemetry: Telemetry data collected during execution.
        error_message: Error message if operation failed.
        created_at: ISO format timestamp when the result was created.
    """
    request_id: str
    session_id: str
    operation: OperationType
    status: str = "SUCCESS"
    workflow_plan: Any = None
    execution_report: Any = None
    evaluation_report: Any = None
    patch_set: Any = None
    workspace_changes: Any = None
    verification_report: Any = None
    final_report: Any = None
    telemetry: Any = None
    error_message: str = ""
    created_at: str = ...
```

### EngineeringController Methods

```python
class EngineeringController:
    """Single public orchestration entry point of the platform."""

    def execute(self, request: EngineeringRequest) -> EngineeringResult
    def review(self, request: EngineeringRequest) -> EngineeringResult
    def implement(self, request: EngineeringRequest) -> EngineeringResult
    def refactor(self, request: EngineeringRequest) -> EngineeringResult
    def debug(self, request: EngineeringRequest) -> EngineeringResult
    def explain(self, request: EngineeringRequest) -> EngineeringResult
```

---

## Usage

```python
from packages.controller import (
    EngineeringController,
    EngineeringRequest,
    OperationType,
)

# Create controller
controller = EngineeringController()

# Create request
request = EngineeringRequest(
    request_id="req-001",
    operation=OperationType.EXECUTE,
    description="Fix the bug in module X",
    workspace_path="/path/to/workspace",
)

# Execute
result = controller.execute(request)

# Access result
print(f"Status: {result.status}")
print(f"Session: {result.session_id}")
print(f"Error: {result.error_message}")
print(f"Workflow Plan: {result.workflow_plan}")
print(f"Execution Report: {result.execution_report}")
print(f"Verification: {result.verification_report}")
```

---

## Operation Delegation Map

| Operation | Default Workflow | Delegates To |
|-----------|-----------------|--------------|
| `execute` | `default-engineering` | WorkflowEngine → ExecutionEngine → Evaluation → Patches → Modification → Verification |
| `review` | `code-review` | WorkflowEngine → ExecutionEngine → Evaluation |
| `implement` | `implement-feature` | Full pipeline including AutonomousEngine |
| `refactor` | `large-refactoring` | Full pipeline including AutonomousEngine |
| `debug` | `bug-investigation` | WorkflowEngine → ExecutionEngine → Verification |
| `explain` | `code-explanation` | WorkflowEngine (read-only, no execution) |

---

## Lifecycle

### Request Processing Flow

```
1. Receive EngineeringRequest
       │
       ▼
2. Validate Request (RequestValidator)
       │
       ▼
3. Ensure Controller Initialized
       │
       ▼
4. Create Session (SessionManager)
       │
       ▼
5. Get Handler from Registry
       │
       ▼
6. Execute Handler
       │
       ├── WorkflowEngine (plan)
       ├── ExecutionEngine (execute)
       ├── EvaluationFramework (evaluate)
       ├── PatchGenerator (generate patches)
       ├── CodeModificationEngine (apply patches)
       └── SelfVerificationEngine (verify)
       │
       ▼
7. Aggregate Artifacts
       │
       ▼
8. Record Telemetry
       │
       ▼
9. Return EngineeringResult
```

### Session Lifecycle

```
CREATED → PLANNING → EXECUTING → VERIFYING → COMPLETED
                                    │
                                    ▼
                                 FAILED
```

The controller owns the session lifecycle:
1. Creates session on first request processing
2. Updates session status through transitions
3. Attaches artifacts to session
4. Takes snapshots at key points
5. Closes session when complete

---

## Extension Points

### 1. Custom Operations

Register new operations via the registry:

```python
from packages.controller import EngineeringController, OperationType

controller = EngineeringController()
controller._ensure_initialized()

# Register a custom operation
controller.registry.register_handler(
    operation=OperationType("custom-op"),  # Add new enum value
    handler=my_custom_handler,
    default_workflow="custom-workflow",
)
```

### 2. Custom Session Manager

Inject a custom session manager:

```python
from packages.controller import EngineeringController
from packages.session import SessionManager

custom_manager = SessionManager()
controller = EngineeringController(session_manager=custom_manager)
```

### 3. Custom Telemetry

Inject custom telemetry:

```python
from packages.controller import EngineeringController
from packages.observability import EngineeringTelemetry

telemetry = EngineeringTelemetry()
controller = EngineeringController(telemetry=telemetry)
```

### 4. Custom Validator

Configure validation rules:

```python
from packages.controller import EngineeringController
from packages.controller.validator import RequestValidator

validator = RequestValidator(
    max_description_length=5000,
    max_request_id_length=32,
)
controller = EngineeringController()
controller.validator = validator
```

---

## Engineering Execution

### Execute Operation

The `execute` operation performs the full engineering pipeline:

1. **Workflow Planning** — Selects and plans workflow steps
2. **Execution** — Executes planned steps
3. **Evaluation** — Evaluates execution quality
4. **Patch Generation** — Generates patches from artifacts
5. **Code Modification** — Applies patches to workspace
6. **Self-Verification** — Verifies changes

### Review Operation

The `review` operation performs code review:

1. **Workflow Planning** — Selects review workflow
2. **Execution** — Executes review steps
3. **Evaluation** — Produces evaluation report

### Implement Operation

The `implement` operation performs feature implementation:

1. **Full pipeline** with autonomous execution capability
2. **Self-verification** ensures quality
3. **Session tracking** for all artifacts

### Refactor Operation

The `refactor` operation performs code refactoring:

1. **Full pipeline** with autonomous execution
2. **Verification** ensures no regressions
3. **Session tracking** for all changes

### Debug Operation

The `debug` operation performs bug investigation:

1. **Workflow Planning** — Selects investigation workflow
2. **Execution** — Executes diagnostic steps
3. **Verification** — Verifies findings

### Explain Operation

The `explain` operation provides code explanation:

1. **Read-only** — No workspace modifications
2. **Workflow Planning** — Generates explanation plan
3. **No execution** — Does not invoke coding agents

---

## Non-Responsibilities (MUST NEVER Do)

The Engineering Controller **MUST NEVER**:

- Inspect repositories directly
- Perform architecture analysis
- Modify code directly
- Generate patches
- Invoke providers directly
- Duplicate workflow logic

All of these responsibilities belong to internal packages. The controller only **coordinates**.

---

## Files Created

| File | Purpose |
|------|---------|
| `packages/controller/__init__.py` | Package exports |
| `packages/controller/models.py` | Request/Result models |
| `packages/controller/controller.py` | Main controller class |
| `packages/controller/validator.py` | Request validation |
| `packages/controller/registry.py` | Operation registry |
| `tests/controller/__init__.py` | Test package init |
| `tests/controller/test_models.py` | Model tests |
| `tests/controller/test_validator.py` | Validator tests |
| `tests/controller/test_registry.py` | Registry tests |
| `tests/controller/test_controller.py` | Controller tests |

---

## Architectural Compliance

| Constraint | Status |
|------------|--------|
| Single entry point | ✅ Only `EngineeringController` exposed |
| No duplicated logic | ✅ All delegation to existing packages |
| Session ownership | ✅ Controller creates and owns session |
| Deterministic execution | ✅ Uses existing deterministic engines |
| No direct repository access | ✅ Delegates to existing packages |
| No provider invocation | ✅ Delegates to existing engines |
| Telemetry integration | ✅ Records events via Observability |

---

## Test Coverage

| Component | Tests | Coverage Target |
|-----------|-------|-----------------|
| Models | `test_models.py` | >95% |
| Validator | `test_validator.py` | >95% |
| Registry | `test_registry.py` | >95% |
| Controller | `test_controller.py` | >95% |

### Test Categories

- **Model tests**: Frozen dataclasses, field types, defaults
- **Validator tests**: Invalid operations, missing fields, invalid paths
- **Registry tests**: Registration, lookup, duplicate prevention
- **Controller tests**:
  - Every public API method
  - Session ownership
  - Deterministic execution
  - Error handling
  - Artifact aggregation
  - Telemetry recording
  - Autonomous execution

---

## Suggested Simplifications

Now that all subsystems are complete, the following simplifications are possible:

### 1. Unified Request/Result Pattern

All consumers (CLI, Extension, UI, API) now use the same `EngineeringRequest` → `EngineeringResult` pattern. No need for separate adapters.

### 2. Single Package Import

Instead of importing 9+ packages:
```python
# Before
from packages.session import SessionManager
from packages.workflows import WorkflowEngine
from packages.execution import ExecutionEngine
# ... etc
```

Consumers now import only:
```python
# After
from packages.controller import EngineeringController
```

### 3. Eliminated Gateway Layer

The controller makes the gateway layer redundant for most use cases. Direct controller usage is sufficient.

### 4. Standardized Error Handling

All errors flow through `EngineeringResult.error_message`, eliminating the need for consumers to handle multiple error types.