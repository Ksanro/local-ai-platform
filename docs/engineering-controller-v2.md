# Engineering Controller v2

> Status: dormant / not wired into the live gateway.
>
> This document describes scaffolded future architecture. It is not runtime
> behavior unless `docs/STATUS.md` says otherwise.

## Central Orchestration Component for Autonomous Engineering Sessions

The Engineering Controller v2 is the central orchestration component responsible for autonomous engineering sessions. It coordinates existing platform components without duplicating their responsibilities.

---

## Table of Contents

- [Architecture](#architecture)
- [Controller Lifecycle](#controller-lifecycle)
- [Decision State Machine](#decision-state-machine)
- [Retry Policy](#retry-policy)
- [Integration Sequence](#integration-sequence)
- [Responsibilities](#responsibilities)
- [Public API Boundaries](#public-api-boundaries)
- [Session State](#session-state)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)

---

## Architecture

```
Gateway ──→ EngineeringControllerV2 ──→ EngineeringSessionV2
                    │
                    ├── WorkflowEngine (public API only)
                    ├── ExecutionEngine (public API only)
                    ├── SelfVerificationEngine (public API only)
                    ├── WorkflowEvaluator (public API only)
                    └── ControllerDecisionMaker (internal)
```

The controller is the **SINGLE source of truth** for session state and decisions. It orchestrates the complete engineering flow:

```
EngineeringRequest
       │
       ▼
Planning ──────────────────→ WorkflowPlan
       │
       ▼
Workflow Selection ─────────→ Select workflow from registry
       │
       ▼
Workflow Engine ────────────→ Generate WorkflowPlan
       │
       ▼
Execution Engine ───────────→ ExecuteWorkflow → ExecutionReport
       │
       ▼
Self Verification ──────────→ Verify → VerificationReport
       │
       ▼
Evaluation ─────────────────→ Evaluate → EvaluationReport
       │
       ▼
Controller Decision ────────→ COMPLETE / RETRY / REQUEST_REVIEW / FAIL
       │
       ├── COMPLETE → Final Engineering Result
       ├── RETRY → Loop back to Workflow Engine (if retries available)
       ├── REQUEST_REVIEW → Human review gate
       └── FAIL → Terminate session
```

---

## Controller Lifecycle

### 1. Session Creation

```python
from packages.controller.models_v2 import EngineeringSessionV2, ControllerConfig

session = EngineeringSessionV2.create(
    session_id="sess-001",
    request_id="req-001",
    config=ControllerConfig(max_retries=3, max_iterations=10),
)
```

The session starts in `ACTIVE` status with zero iterations.

### 2. Control Loop Execution

The controller runs a deterministic control loop:

```python
while session.iteration < session.max_iterations:
    # 1. Select workflow
    workflow_name = controller._select_workflow(request, session)

    # 2. Execute workflow (via public API)
    workflow_plan, execution_report = controller._execute_workflow(request, workflow_name, session)

    # 3. Verify (via public API)
    verification_report = controller._verify(execution_report)

    # 4. Evaluate (via public API)
    evaluation_report = controller._evaluate(workflow_plan, execution_report)

    # 5. Record history
    session = session.append_history(iteration_entry)

    # 6. Make decision
    report = ControllerDecisionMaker.make_decision(...)

    # 7. Handle decision
    if report.decision == COMPLETE:
        return build_complete_result()
    elif report.decision == FAIL:
        return build_fail_result()
    elif report.decision == REQUEST_REVIEW:
        return build_review_result()
    elif report.decision == RETRY:
        if should_retry(session.retry_count):
            session = increment_retry(session)
            continue  # Loop back
        else:
            return build_fail_result()
```

### 3. Result Production

The controller produces an `EngineeringResultV2`:

```python
result = EngineeringResultV2(
    request_id="req-001",
    session_id="sess-001",
    decision=ControllerDecision.COMPLETE,
    status=SessionStatusV2.COMPLETED,
    session=session,
    workflow_plan=workflow_plan,
    execution_report=execution_report,
    verification_report=verification_report,
    evaluation_report=evaluation_report,
)
```

### 4. Session Termination

The session terminates when:
- A COMPLETE decision is made
- A FAIL decision is made
- Max iterations reached
- An exception occurs

---

## Decision State Machine

```
    Execution Failed ──────────────────→ FAIL
           │
           ▼
    Verification Failed ──────────────→ RETRY (if retries < max)
                                      → FAIL (if retries >= max)
           │
           ▼
    Verification Passed
           │
           ▼
    Evaluation >= threshold ──────────→ COMPLETE
           │
           ▼
    Evaluation < threshold
           │
           ├── Evaluation >= review_threshold → REQUEST_REVIEW
           │
           └── Evaluation < review_threshold → FAIL
```

### Decision Rules (evaluated in strict order)

| Rule | Condition | Decision |
|------|-----------|----------|
| 1 | Execution failed | FAIL |
| 2 | Verification failed AND retry_count < max_retries | RETRY |
| 3 | Verification failed AND retry_count >= max_retries | FAIL |
| 4 | Evaluation score >= evaluation_threshold AND verification passed | COMPLETE |
| 5 | Evaluation score < evaluation_threshold AND >= auto_review_threshold | REQUEST_REVIEW |
| 6 | Evaluation score < auto_review_threshold | FAIL |
| 7 | No evaluation report AND verification passed | COMPLETE |

### Decision Implementation

```python
from packages.controller.decision import ControllerDecisionMaker

report = ControllerDecisionMaker.make_decision(
    config=config,
    execution_report=execution_report,
    verification_report=verification_report,
    evaluation_report=evaluation_report,
    retry_count=retry_count,
    iteration=iteration,
)
```

---

## Retry Policy

### Rules

1. A retry is only allowed when the controller decision is RETRY.
2. A retry is only allowed when `retry_count < max_retries`.
3. Each retry must re-execute the full workflow pipeline.
4. The Workflow Engine and Execution Engine must never be bypassed.

### Policy Enforcement

```python
from packages.controller.retry_policy import RetryPolicy

# Check if retry is allowed
should_retry = RetryPolicy.should_retry(
    config=config,
    retry_count=retry_count,
    decision=ControllerDecision.RETRY,
)

# Increment retry count
new_retry_count = RetryPolicy.increment_retry(retry_count)

# Check remaining retries
remaining = RetryPolicy.remaining_retries(config, retry_count)

# Check if max retries reached
is_max = RetryPolicy.is_max_retries_reached(config, retry_count)
```

### Constraints

- Never bypass Workflow Engine
- Never bypass Execution Engine
- Maximum retry count is configurable
- Each retry re-executes the full workflow pipeline

---

## Integration Sequence

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Gateway │────▶│ EngineeringCtrlV2│────▶│ EngineeringSess │
└──────────┘     └────────┬─────────┘     └─────────────────┘
                         │
                         ├──▶ WorkflowEngine (public API)
                         │      │
                         │      ├── Generate WorkflowPlan
                         │      └──▶ Select workflow
                         │
                         ├──▶ ExecutionEngine (public API)
                         │      │
                         │      ├── ExecuteWorkflow
                         │      └──▶ ExecutionReport
                         │
                         ├──▶ SelfVerificationEngine (public API)
                         │      │
                         │      ├── Verify
                         │      └──▶ VerificationReport
                         │
                         ├──▶ WorkflowEvaluator (public API)
                         │      │
                         │      ├── Evaluate
                         │      └──▶ EvaluationReport
                         │
                         └──▶ ControllerDecisionMaker (internal)
                                │
                                ├── COMPLETE
                                ├── RETRY
                                ├── REQUEST_REVIEW
                                └── FAIL
```

### Integration Points

1. **Gateway** invokes `EngineeringControllerV2.execute(request)`
2. **Controller** orchestrates the complete engineering session
3. **Existing Repository Context pipeline** remains unchanged
4. **Provider adapters** remain unchanged

---

## Responsibilities

### Controller MUST Do

| Responsibility | Description |
|----------------|-------------|
| Select next workflow | Choose the appropriate workflow for the current iteration |
| Stop execution | Terminate when max iterations or max retries reached |
| Retry execution | Re-execute workflow when verification fails |
| Request human review | Transition to REVIEW_REQUIRED when evaluation is borderline |

### Controller MUST NEVER Do

| Responsibility | Reason |
|----------------|--------|
| Modify repository | Not the controller's responsibility |
| Generate patches | Handled by Execution Engine |
| Invoke providers directly | Handled by Execution Engine |
| Perform verification | Handled by SelfVerificationEngine |
| Perform evaluation | Handled by WorkflowEvaluator |
| Analyze repositories | Not the controller's responsibility |
| Parse code | Not the controller's responsibility |

---

## Public API Boundaries

The controller consumes **only public APIs** from other components:

```
EngineeringControllerV2
       │
       ├── WorkflowEngine.execute()  (public API)
       ├── ExecutionEngine.execute() (public API)
       ├── VerificationEngine.verify() (public API)
       └── WorkflowEvaluator.evaluate() (public API)
```

### Component Independence

| Component | Status | Reason |
|-----------|--------|--------|
| WorkflowEngine | Unchanged | Existing implementation reused |
| ExecutionEngine | Unchanged | Existing implementation reused |
| VerificationEngine | Unchanged | Existing implementation reused |
| WorkflowEvaluator | Unchanged | Existing implementation reused |
| EngineeringControllerV2 | **NEW** | Central orchestration |

---

## Session State

### EngineeringSessionV2

The session is **immutable** — all state changes create new instances:

```python
# Session creation
session = EngineeringSessionV2.create(
    session_id="sess-001",
    request_id="req-001",
    config=ControllerConfig(),
)

# Immutable state transitions
new_session = session.with_iteration(5)
new_session = session.with_retry_count(2)
new_session = session.with_status(SessionStatusV2.COMPLETED)
new_session = session.append_history(entry)
```

### Session Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `session_id` | `str` | Unique session identifier |
| `request_id` | `str` | Associated request identifier |
| `status` | `SessionStatusV2` | Current session status |
| `iteration` | `int` | Current iteration number (1-based) |
| `max_iterations` | `int` | Maximum allowed iterations |
| `retry_count` | `int` | Current retry count |
| `max_retries` | `int` | Maximum allowed retries |
| `history` | `tuple[SessionHistoryEntry]` | Completed iteration history |
| `created_at` | `str` | ISO format timestamp |
| `updated_at` | `str` | ISO format timestamp of last update |
| `metadata` | `dict` | Additional metadata |

### Query Methods

```python
# Get workflow history
workflow_names = session.workflow_history  # tuple[str, ...]

# Get execution reports
reports = session.execution_reports  # tuple[Any, ...]

# Get verification reports
reports = session.verification_reports  # tuple[Any, ...]

# Get evaluation reports
reports = session.evaluation_reports  # tuple[Any, ...]

# Get controller decisions
decisions = session.controller_decisions  # tuple[ControllerReport, ...]

# Get snapshot
snapshot = session.snapshot()  # Returns self (immutable)
```

---

## Configuration

### ControllerConfig

```python
from packages.controller.models_v2 import ControllerConfig

config = ControllerConfig(
    evaluation_threshold=0.7,      # Minimum score for COMPLETE
    max_retries=3,                  # Maximum retry attempts
    max_iterations=10,              # Maximum total iterations
    verification_required=True,     # Whether verification must pass
    auto_review_threshold=0.5,      # Score below this triggers REQUEST_REVIEW
)
```

### Threshold Behavior

| Threshold | Purpose | Default |
|-----------|---------|---------|
| `evaluation_threshold` | Minimum evaluation score for COMPLETE | 0.7 |
| `auto_review_threshold` | Evaluation score below this triggers REQUEST_REVIEW | 0.5 |
| `max_retries` | Maximum retry attempts | 3 |
| `max_iterations` | Maximum total iterations | 10 |
| `verification_required` | Whether verification must pass | True |

---

## Usage

### Basic Usage

```python
from packages.controller.controller_v2 import EngineeringControllerV2
from packages.controller.models_v2 import EngineeringRequestV2

# Create controller
controller = EngineeringControllerV2()

# Create request
request = EngineeringRequestV2(
    request_id="req-001",
    operation=OperationType.EXECUTE,
    description="Implement feature X",
)

# Execute
result = controller.execute(request)

# Access result
print(f"Decision: {result.decision}")
print(f"Status: {result.status}")
print(f"Session: {result.session_id}")
print(f"Error: {result.error_message}")
```

### With Custom Configuration

```python
config = ControllerConfig(
    evaluation_threshold=0.8,
    max_retries=5,
    max_iterations=20,
)

controller = EngineeringControllerV2(config=config)
request = EngineeringRequestV2(
    request_id="req-001",
    operation=OperationType.EXECUTE,
    description="Implement feature X",
    config=config,
)
result = controller.execute(request)
```

### With Injected Engines

```python
# Inject real engines
controller = EngineeringControllerV2(
    workflow_selector=real_workflow_selector,
    workflow_engine=real_workflow_engine,
    execution_engine=real_execution_engine,
    verification_engine=real_verification_engine,
    evaluator=real_evaluator,
)

request = EngineeringRequestV2(...)
result = controller.execute(request)
```

### Session Resumption

```python
# Resume an existing session
session = EngineeringSessionV2.create(
    session_id="sess-existing",
    request_id="req-001",
)

result = controller.execute_with_session(request, session)
```

---

## Testing

### Test Coverage

The following integration tests cover the controller:

| Test File | Coverage |
|-----------|----------|
| `test_models_v2.py` | Model classes, immutability, defaults |
| `test_decision.py` | Decision logic, edge cases, determinism |
| `test_retry_policy.py` | Retry policy, constraints, validation |
| `test_controller_v2.py` | Control loop, session management, decisions |
| `test_integration_v2.py` | End-to-end flows, history, reports |

### Key Test Scenarios

1. **Successful completion** — All checks pass → COMPLETE
2. **Retry flow** — Verification fails → RETRY → Re-execute → COMPLETE
3. **Verification failure** — Verification fails → FAIL (max retries)
4. **Evaluation failure** — Low score → REQUEST_REVIEW or FAIL
5. **Maximum retry reached** — Max retries exhausted → FAIL
6. **Deterministic decisions** — Same inputs → Same output
7. **Immutable session** — Original session unchanged
8. **Session history correctness** — History entries in order

### Running Tests

```bash
# Run all controller v2 tests
pytest tests/controller/test_models_v2.py -v
pytest tests/controller/test_decision.py -v
pytest tests/controller/test_retry_policy.py -v
pytest tests/controller/test_controller_v2.py -v
pytest tests/controller/test_integration_v2.py -v

# Run all controller tests
pytest tests/controller/ -v
```

---

## Files

| File | Description |
|------|-------------|
| `packages/controller/models_v2.py` | Controller models (Config, Request, Result, Session) |
| `packages/controller/decision.py` | Deterministic decision logic |
| `packages/controller/retry_policy.py` | Retry policy enforcement |
| `packages/controller/controller_v2.py` | Main controller loop |
| `packages/controller/__init__.py` | Package exports |
| `tests/controller/test_models_v2.py` | Model tests |
| `tests/controller/test_decision.py` | Decision logic tests |
| `tests/controller/test_retry_policy.py` | Retry policy tests |
| `tests/controller/test_controller_v2.py` | Controller loop tests |
| `tests/controller/test_integration_v2.py` | Integration tests |

---

## Constraints

- **No duplicated workflow logic** — Workflow Engine handles workflow execution
- **No duplicated execution logic** — Execution Engine handles execution
- **No duplicated verification logic** — Verification Engine handles verification
- **No duplicated evaluation logic** — Evaluator handles evaluation
- **No repository analysis** — Not the controller's responsibility
- **No provider-specific logic** — Provider adapters handle provider logic
- **Deterministic behavior** — No randomness or non-deterministic operations

---

## Summary

The Engineering Controller v2 is the central orchestration component for autonomous engineering sessions. It implements a deterministic control loop that coordinates existing platform components through their public APIs, manages immutable session state, enforces configurable retry policies, and produces deterministic decisions based on execution, verification, and evaluation reports.
