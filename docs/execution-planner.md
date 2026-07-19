# Execution Planner v1

## Overview

The Execution Planner transforms one or more `TaskPlan` objects produced by a `WorkflowPlan` into a deterministic `ExecutionPlan` consumable by coding agents.

The Execution Planner owns **execution planning only**. It never performs repository analysis, invokes providers, edits source code, or owns workflow logic.

## Architecture

```
TaskRequest
    ↓
Task
    ↓
TaskPlan
    ↓
Workflow
    ↓
WorkflowPlan
    ↓
ExecutionPlanner
    ↓
ExecutionPlan
    ↓
ProviderSerializer
    ↓
LLM
```

### Data Flow

1. **TaskRequest** → User input for a task
2. **Task** → Orchestrates public APIs, produces `TaskPlan`
3. **TaskPlan** → Immutable execution plan for a single task
4. **Workflow** → Orchestrates multiple tasks, produces `WorkflowPlan`
5. **WorkflowPlan** → Complete orchestration plan with all task plans
6. **ExecutionPlanner** → Translates `WorkflowPlan` to `ExecutionPlan`
7. **ExecutionPlan** → Deterministic plan for coding agents
8. **ProviderSerializer** → Serializes plan for LLM consumption
9. **LLM** → Executes the plan

## Models

### ExecutionStep

An immutable step in an execution plan.

```python
@dataclass(frozen=True, slots=True)
class ExecutionStep:
    order: int
    title: str
    description: str
    required_symbols: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `order` | `int` | Execution order (0-based, deterministic) |
| `title` | `str` | Human-readable step title |
| `description` | `str` | Detailed step description |
| `required_symbols` | `tuple[str, ...]` | Symbols required for this step |
| `required_modules` | `tuple[str, ...]` | Modules required for this step |
| `constraints` | `tuple[str, ...]` | Constraints applicable to this step |

### ExecutionMetrics

Estimated metrics for an execution plan, derived from `WorkflowMetrics`.

```python
@dataclass(frozen=True, slots=True)
class ExecutionMetrics:
    estimated_tokens: int = 0
    estimated_duration_ms: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `estimated_tokens` | `int` | Total estimated token count |
| `estimated_duration_ms` | `int` | Total estimated duration in milliseconds |
| `estimated_complexity` | `TaskComplexity` | Overall complexity level |

**Derivation Rules:**

- `estimated_tokens`: Sum of all task plan token estimates
- `estimated_duration_ms`: Sum of all task plan duration estimates
- `estimated_complexity`: Maximum complexity across all tasks

No duplicated calculations — metrics are derived directly from workflow metrics.

### ExecutionPlan

Complete execution plan for a workflow.

```python
@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    workflow_name: str
    objective: str
    execution_steps: tuple[ExecutionStep, ...] = ()
    context_package: object = None
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    constraints: tuple[str, ...] = ()
    validation_requirements: tuple[str, ...] = ()
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | `str` | The workflow name |
| `objective` | `str` | The workflow objective |
| `execution_steps` | `tuple[ExecutionStep, ...]` | Ordered execution steps |
| `context_package` | `object` | The merged context package from the workflow |
| `metrics` | `ExecutionMetrics` | Aggregated execution metrics |
| `constraints` | `tuple[str, ...]` | Aggregated constraints from all tasks |
| `validation_requirements` | `tuple[str, ...]` | Requirements that must be validated |

## ExecutionPlanner

The `ExecutionPlanner` converts a `WorkflowPlan` into a deterministic `ExecutionPlan`.

### Responsibilities

1. **Consume WorkflowPlan** — Accept the workflow plan as input
2. **Flatten TaskPlans** — Convert `TaskPlan.steps` into ordered `ExecutionStep` objects
3. **Preserve dependency ordering** — Maintain the order defined by `WorkflowPlan.workflow_steps`
4. **Aggregate constraints** — Collect and deduplicate constraints from all task plans
5. **Preserve ContextPackage** — Pass through the merged context from the workflow
6. **Aggregate metrics** — Sum tokens/duration, take max complexity
7. **Generate validation requirements** — Create list of requirements to validate

### API

```python
from packages.execution.planner import ExecutionPlanner
from packages.workflows.models import WorkflowPlan

workflow_plan = WorkflowPlan(
    workflow_name="implement_feature",
    task_plans=(),
    workflow_steps=(),
)

execution_plan = ExecutionPlanner.plan(workflow_plan)
```

### Translation Layer

The ExecutionPlanner is a **translation layer**. It:

- Converts WorkflowPlans into ExecutionPlans
- Owns **no** repository intelligence
- Owns **no** workflow logic
- Owns **no** task logic

If implementation requires duplicating Workflow or Task behavior, stop and ask rather than introducing architectural coupling.

## ExecutionValidator

The `ExecutionValidator` validates `ExecutionPlan` objects for correctness and readiness.

### Validation Methods

#### validate_dependencies

Validates that dependency ordering is correct. Checks that all steps reference valid preceding steps based on their order values.

```python
errors = ExecutionValidator.validate_dependencies(plan)
# Returns: [] if valid, or list of error strings
```

#### validate_context

Validates that required context exists. Checks that the `context_package` is present when execution steps require symbols or modules.

```python
errors = ExecutionValidator.validate_context(plan)
# Returns: [] if valid, or list of error strings
```

#### validate_constraints

Validates that constraints are satisfied. Checks that all constraints are well-formed (non-empty strings, valid format).

```python
errors = ExecutionValidator.validate_constraints(plan)
# Returns: [] if valid, or list of error strings
```

#### validate_ordering

Validates deterministic ordering. Checks that:
- Steps are ordered sequentially from 0
- No duplicate order values exist
- All steps have valid order values (>= 0)

```python
errors = ExecutionValidator.validate_ordering(plan)
# Returns: [] if valid, or list of error strings
```

#### validate_all

Runs all validation checks and returns combined errors.

```python
errors = ExecutionValidator.validate_all(plan)
# Returns: combined list of all error strings
```

## Dependency Preservation

The ExecutionPlanner preserves dependency ordering from the `WorkflowPlan`. Steps are flattened in the order defined by `WorkflowPlan.workflow_steps`, maintaining the topological order established by the workflow.

### Ordering Rules

1. Steps from `workflow_steps[0]` come first
2. Steps from `workflow_steps[1]` come next
3. And so on...

Within each workflow step, task plan steps maintain their internal order.

### Example

```
WorkflowPlan:
  workflow_steps: [step_a, step_b, step_c]
  task_plans:
    step_a → TaskPlan(steps=[a1, a2])
    step_b → TaskPlan(steps=[b1])
    step_c → TaskPlan(steps=[c1, c2])

ExecutionPlan:
  execution_steps: [a1, a2, b1, c1, c2]
```

## Deterministic Ordering

The ExecutionPlanner produces **deterministic** output — the same input always produces the same output.

### Guarantees

1. **Same input → Same output**: Multiple calls with identical input produce identical output
2. **Sequential ordering**: Steps are ordered 0, 1, 2, ...
3. **No randomness**: No random elements in planning
4. **Stable sorting**: All aggregations use deterministic sorting

### Verification

```python
plan1 = ExecutionPlanner.plan(workflow_plan)
plan2 = ExecutionPlanner.plan(workflow_plan)

# Always true
assert plan1.execution_steps == plan2.execution_steps
```

## Constraints

The ExecutionPlanner **must NOT**:

- Inspect AST
- Parse repositories
- Invoke providers
- Edit source code
- Duplicate Workflow logic
- Duplicate Task logic

The ExecutionPlanner consumes only public Workflow APIs.

## Repository Layout

```
packages/execution/
    __init__.py      # Package init, public API exports
    base.py          # ExecutionPlannerBase ABC
    models.py        # Immutable dataclasses
    planner.py       # ExecutionPlanner implementation
    validator.py     # ExecutionValidator implementation

tests/execution/
    __init__.py      # Test package init
    test_models.py   # Model tests
    test_planner.py  # Planner tests
    test_validator.py # Validator tests

docs/execution-planner.md  # This documentation
```

## Future Evolution

Future planners may support:

- Parallel execution
- Checkpointing
- Retries
- Distributed execution
- Multi-agent scheduling

The public API must not require changes for these additions.

## Acceptance Criteria

- [x] pytest passes
- [x] ruff passes
- [x] mypy passes
- [x] immutable models (frozen=True, slots=True)
- [x] deterministic ExecutionPlan
- [x] validator implemented
- [x] documentation complete