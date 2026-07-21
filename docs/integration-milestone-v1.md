# Integration Milestone v1

## Overview

Integration Milestone v1 wires the existing platform components together into one complete engineering execution flow. This is a **pure integration** task — no new frameworks or abstractions are introduced.

The execution flow becomes:

```
Request
  → Planning
  → Workflow Selection
  → Workflow Engine
  → Execution Engine
  → Self Verification
  → Evaluation
  → Provider
  → Response
```

Repository context generation remains unchanged.

---

## Execution Pipeline

### Complete Flow

```
┌─────────────┐
│   Request    │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ PlanningStage    │  (intent detection, rule matching)
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│ RepositoryContextStage│  (assemble repository context)
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│ WorkflowStage    │  (select workflow, generate WorkflowPlan)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ ExecutionStage   │  (execute WorkflowPlan → ExecutionReport)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ VerificationStage│  (self-verify → VerificationReport)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ EvaluationStage  │  (evaluate → EvaluationReport)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ ProviderStage    │  (serialize, call provider)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Response        │
└──────────────────┘
```

### Stage Descriptions

| Stage | Input | Output | Responsibility |
|-------|-------|--------|----------------|
| **PlanningStage** | Request | ContextPlan | Intent detection, rule matching |
| **RepositoryContextStage** | RepositoryIndex | ContextPackage | Assemble repository context |
| **WorkflowStage** | ContextPlan, RepositoryIndex | WorkflowPlan | Select workflow, generate plan |
| **ExecutionStage** | WorkflowPlan | ExecutionReport | Execute workflow steps |
| **VerificationStage** | ExecutionReport | VerificationReport | Self-verify execution results |
| **EvaluationStage** | ExecutionReport, VerificationReport | EvaluationReport | Evaluate quality of execution |
| **ProviderStage** | ContextPackage, reports | ProviderResponse | Serialize and call provider |

---

## PipelineContext

`PipelineContext` is the mutable state object shared across all pipeline stages. It preserves all data through every stage without serialization loss.

### Fields

```python
@dataclass
class PipelineContext:
    # Identity
    request_id: str

    # Input
    request: dict[str, Any]

    # Stage results
    stage_results: dict[str, PipelineStageResult]

    # Metadata (free-form dict)
    metadata: dict[str, Any]

    # Timing
    start_time: float

    # Integration Milestone v1 fields
    context_package: ContextPackage | None    # After RepositoryContextStage
    workflow_plan: Any                        # After WorkflowStage
    execution_report: Any                     # After ExecutionStage
    verification_report: Any                  # After VerificationStage
    evaluation_report: Any                    # After EvaluationStage
```

### Data Flow

```
PipelineContext
├── request                    # Original request (immutable)
├── stage_results              # Per-stage results
├── metadata                   # Free-form data sharing
├── context_package            # Repository context
├── workflow_plan              # WorkflowPlan (immutable)
├── execution_report           # ExecutionReport (immutable)
├── verification_report        # VerificationReport (immutable)
└── evaluation_report          # EvaluationReport (immutable)
```

### Metadata Keys

| Key | Type | Set By | Description |
|-----|------|--------|-------------|
| `workflow_enabled` | bool | User/Config | Whether workflow execution is enabled |
| `workflow_name` | str | User/Config | Name of workflow to execute |
| `workflow_plan` | WorkflowPlan | WorkflowStage | Stored in both context and metadata |
| `execution_enabled` | bool | User/Config | Whether execution is enabled |
| `execution_report` | ExecutionReport | ExecutionStage | Stored in both context and metadata |
| `verification_enabled` | bool | User/Config | Whether verification is enabled |
| `verification_report` | VerificationReport | VerificationStage | Stored in both context and metadata |
| `evaluation_enabled` | bool | User/Config | Whether evaluation is enabled |
| `evaluation_report` | EvaluationReport | EvaluationStage | Stored in both context and metadata |
| `repository_index` | RepositoryIndex | RepositoryContextStage | Index for workflow planning |

---

## Component Lifecycle

### 1. WorkflowEngine

**Responsibility:** Select and execute a workflow from the registry, producing a `WorkflowPlan`.

**Lifecycle:**
1. Receives request from PlanningStage
2. Looks up workflow in registry
3. Creates workflow instance via `WorkflowFactory`
4. Generates `WorkflowPlan` via `WorkflowEngine.generate_plan()`
5. Stores result in `context.workflow_plan`

**Public API:**
```python
from packages.workflows.engine import WorkflowEngine
from packages.workflows.factory import WorkflowFactory
from packages.workflows.registry import WorkflowRegistry

registry = WorkflowRegistry()
engine = WorkflowEngine()
factory = WorkflowFactory(registry)
workflow = factory.create("implement-feature")
plan = engine.generate_plan(workflow, repository_index, task_request)
```

### 2. ExecutionEngine

**Responsibility:** Execute every `WorkflowStep` in deterministic order, producing an immutable `ExecutionReport`.

**Lifecycle:**
1. Receives `WorkflowPlan` from WorkflowStage
2. Creates `ProviderExecutionAdapter`
3. Executes each step in order
4. Produces immutable `ExecutionReport`
5. Stores result in `context.execution_report`

**Public API:**
```python
from packages.execution.engine import ExecutionEngine
from packages.execution.adapter import ProviderExecutionAdapter

engine = ExecutionEngine()
adapter = ProviderExecutionAdapter()
report = engine.execute(workflow_plan, adapter)
```

### 3. SelfVerificationEngine

**Responsibility:** Execute automatically after ExecutionEngine, verify execution results, produce `VerificationReport`.

**Lifecycle:**
1. Receives `ExecutionReport` from ExecutionStage
2. Executes verification rules
3. Produces immutable `VerificationReport`
4. Stores result in `context.verification_report`

**Public API:**
```python
from packages.verification.engine import SelfVerificationEngine

engine = SelfVerificationEngine()
report = engine.verify(workflow_plan, execution_plan, evaluation_report, patch_set, workspace_changes)
```

**Constraints:**
- Never executes independently
- Never edits code
- Never invokes providers
- Never inspects repositories

### 4. WorkflowEvaluator

**Responsibility:** Execute immediately after SelfVerificationEngine, evaluate execution and verification results, produce `EvaluationReport`.

**Lifecycle:**
1. Receives `ExecutionReport` and `VerificationReport` from context
2. Computes evaluation metrics
3. Produces immutable `EvaluationReport`
4. Stores result in `context.evaluation_report`

**Public API:**
```python
from packages.evaluation.evaluator import WorkflowEvaluator

evaluator = WorkflowEvaluator()
report = evaluator.evaluate(workflow_plan, execution_report, capability_result, task_plan, provider_response)
```

**Constraints:**
- Never executes independently
- Never edits code
- Never invokes providers
- Never inspects repositories

---

## Public API Boundaries

Strict boundary rules ensure separation of concerns:

| Component | Can Call | Cannot Call |
|-----------|----------|-------------|
| **Gateway** | Workflow Engine only | Everything else directly |
| **Workflow Engine** | Tasks | Providers, Repository, Code |
| **Tasks** | Capabilities | Providers, Repository, Code |
| **Capabilities** | Repository Intelligence | Providers, Code |
| **Execution Engine** | WorkflowPlan, Adapters | Repository, Planning |
| **Self Verification** | ExecutionReport | Code editing, Providers, Repository |
| **Evaluation** | ExecutionReport, VerificationReport | Code editing, Providers, Repository |

### Boundary Enforcement

1. **Gateway only communicates with Workflow Engine** — The gateway (PipelineEngine) orchestrates stages but does not bypass the workflow engine.

2. **Workflow Engine only communicates with Tasks** — Workflows compose tasks; they do not directly invoke providers or parse repositories.

3. **Tasks only communicate with Capabilities** — Tasks use capabilities for their operations.

4. **Capabilities only communicate with Repository Intelligence** — Capabilities query repository context but do not edit code.

5. **Execution Engine never performs repository analysis** — It only executes workflow steps.

6. **Verification never edits code** — It only inspects execution reports.

7. **Evaluation never edits code** — It only inspects execution and verification reports.

---

## Data Flow

### Request Flow

```
1. Request enters PipelineEngine
2. PipelineEngine creates PipelineContext with request data
3. Stages execute in order, each reading/writing context
4. Final response is returned to caller
```

### Report Immutability

All reports (`WorkflowPlan`, `ExecutionReport`, `VerificationReport`, `EvaluationReport`) are **immutable** (frozen dataclasses). This ensures:

1. **No accidental mutation** — Reports cannot be modified after creation.
2. **Deterministic behavior** — Reports are the same across all references.
3. **Thread safety** — Reports can be shared across threads without locking.

```python
# ExecutionReport is frozen.
from packages.execution.runtime_models import ExecutionReport

report = ExecutionReport(...)
report.workflow_name = "new"  # Raises FrozenInstanceError
```

### Context Survival

PipelineContext preserves all reports through every stage:

```python
# After WorkflowStage:
assert context.workflow_plan is not None

# After ExecutionStage:
assert context.execution_report is not None

# After VerificationStage:
assert context.verification_report is not None

# After EvaluationStage:
assert context.evaluation_report is not None

# All reports are accessible via direct attribute or metadata:
assert context.get_metadata("workflow_plan") is context.workflow_plan
```

---

## Constraints

### No New Frameworks

- No new frameworks introduced
- No new abstractions beyond existing ones
- Existing components are wired together as-is

### No New Architecture

- Existing component boundaries are preserved
- No new architectural patterns introduced
- Integration is achieved through PipelineStage orchestration

### Repository Parsing

- Repository parsing only occurs in Repository Intelligence
- No duplicated parsing logic
- No parsing outside RepositoryContextStage

### Planning Logic

- Planning logic exists only in PlanningStage
- No duplicated planning logic
- Planning produces ContextPlan, not WorkflowPlan

### Verification Logic

- Verification logic exists only in VerificationStage
- No duplicated verification logic
- Verification never executes independently

### Provider Logic

- Provider-specific logic exists only in Provider adapters
- No provider-specific logic outside adapters
- ProviderStage is the only stage that calls providers

### Deterministic Behavior

- All stages execute in deterministic order
- All reports are immutable
- Pipeline behavior is reproducible

---

## Integration Tests

Located in `tests/integration/test_engineering_flow.py`:

| Test | Verifies |
|------|----------|
| `test_full_pipeline_execution` | All stages execute successfully |
| `test_deterministic_order` | Stages execute in correct order |
| `test_immutable_reports` | Reports are frozen dataclasses |
| `test_context_survival` | PipelineContext preserves all reports |
| `test_provider_receives_unchanged_request` | Provider receives original request |
| `test_repository_context_pipeline` | Existing repository-context pipeline works |
| `test_stage_boundary_constraints` | Stage classes have expected properties |
| `test_pipeline_context_fields` | PipelineContext has all required fields |

### Running Integration Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific test
pytest tests/integration/test_engineering_flow.py::test_full_pipeline_execution -v
```

---

## Files

### Created

| File | Description |
|------|-------------|
| `packages/pipeline/stages/workflow_stage.py` | Workflow selection and plan generation |
| `packages/pipeline/stages/execution_stage.py` | WorkflowPlan execution |
| `packages/pipeline/stages/verification_stage.py` | Self-verification |
| `packages/pipeline/stages/evaluation_stage.py` | Evaluation |
| `tests/integration/test_engineering_flow.py` | Integration tests |

### Modified

| File | Changes |
|------|---------|
| `packages/pipeline/context.py` | Added workflow_plan, execution_report, verification_report, evaluation_report fields |
| `packages/pipeline/stages/__init__.py` | Added new stage exports |

---

## Summary

Integration Milestone v1 achieves the following:

1. **Complete execution flow** — Request → Planning → Workflow → Execution → Verification → Evaluation → Provider → Response
2. **PipelineContext preservation** — All reports survive every stage without serialization loss
3. **Immutable reports** — ExecutionReport, VerificationReport, EvaluationReport are frozen dataclasses
4. **Deterministic behavior** — Stages execute in fixed order, reports are immutable
5. **Strict boundaries** — Each component has clear responsibilities and cannot call components outside its scope
6. **No new frameworks** — Existing components are wired together without introducing new abstractions
7. **Repository context preserved** — Existing repository-context pipeline remains functional