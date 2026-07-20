# Execution Engine

## Overview

The Execution Engine is responsible for executing immutable `WorkflowPlan` objects through an `ExecutionAdapter` abstraction. It is the bridge between Planning and AI execution.

## Architecture

```
WorkflowPlan
    │
    ▼
ExecutionEngine
    │
    ├── validate(WorkflowPlan)
    ├── create ExecutionSession
    │
    ▼
ExecutionAdapter
    │
    ├── execute_step(WorkflowStep, TaskPlan) → ExecutionStepResult
    │
    ▼
ExecutionReport
```

### Data Flow

```
WorkflowPlan  -->  ExecutionEngine  -->  ExecutionAdapter  -->  ExecutionReport
       │                    │
       │                    v
       │             ExecutionSession (internal)
       │                    │
       │                    v
       │             ExecutionStepResult (collected)
       │                    │
       │                    v
       │             ExecutionReport (output)
```

## Responsibilities

### ExecutionEngine

- Validate `WorkflowPlan`
- Create `ExecutionSession`
- Execute `WorkflowSteps` sequentially
- Collect `ExecutionStepResult`s
- Stop on first failure
- Produce immutable `ExecutionReport`

### ExecutionAdapter

- Execute a single workflow step
- Receive `WorkflowStep` + `TaskPlan`
- Return `ExecutionStepResult`
- Be stateless

### ExecutionReport

- Immutable record of execution
- Contains all step results in deterministic order
- Contains success/failure status
- Contains adapter name used

## Non-Responsibilities

The Execution Engine does NOT:

- Inspect repositories
- Parse AST
- Rank symbols
- Build context
- Invoke planners
- Modify `WorkflowPlan`
- Modify `TaskPlan`
- Know provider implementations
- Handle retries
- Handle scheduling
- Handle parallelism
- Handle checkpoints
- Handle recovery

Version 1 is intentionally simple.

## Public API

```python
from packages.execution.engine import ExecutionEngine
from packages.execution.adapter import ExecutionAdapter, ProviderExecutionAdapter
from packages.execution.runtime_models import (
    ExecutionReport,
    ExecutionSession,
    ExecutionStepResult,
    ExecutionStatus,
)
from packages.workflows.models import WorkflowPlan

# Execute a workflow plan
adapter = ProviderExecutionAdapter()
report = ExecutionEngine.execute(workflow_plan, adapter)
```

## Execution Flow

1. **Validation**: The engine validates the `WorkflowPlan` (non-empty name, non-empty steps).
2. **Session Creation**: An `ExecutionSession` is created with a unique `session_id`.
3. **Sequential Execution**: Each `WorkflowStep` is executed in order via the adapter.
4. **Result Collection**: Each `ExecutionStepResult` is collected into the report.
5. **Failure Handling**: On first failure, execution stops immediately.
6. **Report Generation**: An immutable `ExecutionReport` is produced.

## Adapter Abstraction

### ExecutionAdapter (ABC)

The `ExecutionAdapter` is an abstract base class that defines the interface for all execution adapters.

```python
class ExecutionAdapter(ABC):
    @property
    def name(self) -> str: ...

    @property
    def supported_capabilities(self) -> tuple[str, ...]: ...

    @abstractmethod
    def execute_step(
        self,
        workflow_step: WorkflowStep,
        task_plan: TaskPlan,
    ) -> ExecutionStepResult: ...
```

### Adapter Constraints

- Adapters receive `WorkflowStep` + `TaskPlan` only.
- Adapters are **stateless** (no internal state mutation).
- Adapters do NOT access `RepositoryIndex` directly.
- Adapters do NOT invoke Repository Intelligence.
- Adapters execute. Nothing more.

### ProviderExecutionAdapter

The first concrete implementation wraps existing Provider infrastructure.

```python
class ProviderExecutionAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "ProviderExecutionAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("provider_execution",)

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Delegate to Provider infrastructure
        # Does not implement provider logic
        ...
```

## Future Adapters

The adapter abstraction allows interchangeable execution implementations:

### DSPARK Adapter

Future adapter for distributed Spark execution.

```python
class DSPARKAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "DSPARKAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("distributed_execution", "spark")

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Execute via Spark cluster
        ...
```

### DFLASH Adapter

Future adapter for high-speed flash execution.

```python
class DFLASHAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "DFLASHAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("high_speed_execution", "flash")

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Execute via flash infrastructure
        ...
```

### Claude Code Adapter

Future adapter for Claude Code execution.

```python
class ClaudeCodeAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "ClaudeCodeAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("claude_code_execution",)

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Execute via Claude Code API
        ...
```

### OpenHands Adapter

Future adapter for OpenHands execution.

```python
class OpenHandsAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "OpenHandsAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("openhands_execution",)

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Execute via OpenHands API
        ...
```

### Generic Provider Adapter

Future adapter for generic provider execution.

```python
class GenericProviderAdapter(ExecutionAdapter):
    @property
    def name(self) -> str:
        return "GenericProviderAdapter"

    @property
    def supported_capabilities(self) -> tuple[str, ...]:
        return ("generic_provider_execution",)

    def execute_step(self, workflow_step, task_plan) -> ExecutionStepResult:
        # Execute via generic provider interface
        ...
```

**Adapters are interchangeable implementations.** The engine does not know which adapter is behind the abstraction.

## Models

### ExecutionStatus

```python
class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

### ExecutionStepResult

```python
@dataclass(frozen=True, slots=True)
class ExecutionStepResult:
    step_name: str
    status: ExecutionStatus
    started_at: str
    finished_at: str
    duration_ms: int
    output_summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ExecutionSession

```python
@dataclass(frozen=True, slots=True)
class ExecutionSession:
    session_id: str
    workflow_name: str
    execution_status: ExecutionStatus
    started_at: str
    completed_at: str
    executed_steps: tuple[ExecutionStepResult, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
```

### ExecutionReport

```python
@dataclass(frozen=True, slots=True)
class ExecutionReport:
    workflow_name: str
    execution_status: ExecutionStatus
    total_duration_ms: int
    step_results: tuple[ExecutionStepResult, ...]
    adapter_name: str
    success: bool
    failures: tuple[str, ...] = ()
```

All models are **immutable** (frozen dataclasses with slots).

## Package Structure

```
packages/execution/
    __init__.py          # Package exports
    models.py            # Execution Planner models (unchanged)
    base.py              # Execution Planner base class (unchanged)
    planner.py           # ExecutionPlanner implementation (unchanged)
    validator.py         # ExecutionValidator (unchanged)
    runtime_models.py    # Execution Engine runtime models (new)
    adapter.py           # ExecutionAdapter ABC + ProviderExecutionAdapter (new)
    engine.py            # ExecutionEngine (new)

tests/execution/
    __init__.py
    test_engine.py       # Engine tests
    test_models.py       # Runtime models tests
    test_adapter.py      # Adapter tests
```

## Constraints

### ExecutionEngine must NOT

- Inspect repositories
- Parse AST
- Rank symbols
- Build context
- Invoke planners
- Modify WorkflowPlan
- Modify TaskPlan
- Know provider implementations

### Adapter must NOT

- Access RepositoryIndex directly
- Invoke Repository Intelligence
- Maintain internal state
- Execute multiple steps

## Bounded Contexts

The `packages/execution` package contains two distinct bounded contexts:

| Context | Files | Responsibility |
|---------|-------|----------------|
| **Execution Planner** | `models.py`, `base.py`, `planner.py`, `validator.py` | Transform `WorkflowPlan` → `ExecutionPlan` |
| **Execution Engine** | `runtime_models.py`, `adapter.py`, `engine.py` | Execute `WorkflowPlan` → `ExecutionReport` |

These contexts are separate and do not mix their models.

## TODO

**Revisit whether `ExecutionPlanner` provides enough value over raw `WorkflowPlan` to justify its existence.** The `ExecutionPlanner` flattens `TaskPlan` steps into `ExecutionStep` objects — this may be a responsibility better placed in the Execution Engine or in consumer code.

## Acceptance Criteria

- [x] pytest passes
- [x] ruff passes
- [x] mypy passes
- [x] deterministic execution
- [x] immutable models
- [x] adapter abstraction
- [x] ProviderExecutionAdapter implemented
- [x] documentation complete
- [x] no framework modifications