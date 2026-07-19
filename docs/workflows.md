# Workflow Engine v1

## Overview

The Workflow Engine provides deterministic orchestration of Tasks into reusable engineering workflows.

A Workflow composes Tasks.

A Task composes Capabilities.

A Capability composes Repository Intelligence.

The Workflow Engine owns orchestration only. It never owns repository intelligence, performs repository analysis, invokes providers, or edits source code.

---

## Architecture

```
User Request
    ↓
TaskRequest
    ↓
Workflow
    ↓
Task
    ↓
Capability
    ↓
Planner
    ↓
Repository Intelligence
    ↓
Context Builder
    ↓
Context Package
    ↓
Provider Serializer
    ↓
LLM
```

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Engine                          │
│  (orchestration only - no repository intelligence)          │
├─────────────────────────────────────────────────────────────┤
│                        Workflow                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  WorkflowNode│  │  WorkflowNode│  │  WorkflowNode│      │
│  │   (task A)   │  │   (task B)   │  │   (task C)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                 ↓                 ↓               │
├─────────────────────────────────────────────────────────────┤
│                        Tasks                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Architecture│  │   Impact     │  │ Implementation│      │
│  │   Review     │  │   Analysis   │  │    Task      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                 ↓                 ↓               │
├─────────────────────────────────────────────────────────────┤
│                     Capabilities                            │
│  ┌──────────────────────────────────────────────────┐      │
│  │          Capability (Architecture Review)         │      │
│  │  ┌──────────────┐  ┌──────────────┐              │      │
│  │  │   Planner    │  │ Repository   │              │      │
│  │  │              │  │ Intelligence │              │      │
│  │  └──────────────┘  └──────────────┘              │      │
│  └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow Lifecycle

```
  User                    Workflow               WorkflowEngine         Task
   │                        │                         │                 │
   │  TaskRequest           │                         │                 │
   ├──────────────────────►│                         │                 │
   │                        │                         │                 │
   │                        │  validate()             │                 │
   │                        ├────────────────────────►│                 │
   │                        │                         │                 │
   │                        │  plan()                 │                 │
   │                        ├────────────────────────►│                 │
   │                        │                         │  plan()        │
   │                        │                         ├────────────────►│
   │                        │                         │                 │
   │                        │      TaskPlan           │                 │
   │                        │◄────────────────────────┴────────────────┤
   │                        │                         │                 │
   │                        │  merge ContextPackages  │                 │
   │                        │                         │                 │
   │   WorkflowPlan         │                         │                 │
   │◄───────────────────────┤                         │                 │
```

### Steps

1. **Request**: User creates a `TaskRequest` with a query.
2. **Validation**: Workflow validates the request against its constraints.
3. **Planning**: Workflow generates a `WorkflowPlan` by invoking each task's `plan()` method.
4. **Context Merging**: Engine merges `ContextPackage`s from all tasks.
5. **Metrics Aggregation**: Engine aggregates `TaskMetrics` into `WorkflowMetrics`.
6. **Constraint Aggregation**: Engine deduplicates and aggregates `TaskConstraint`s.
7. **Result**: Returns a complete `WorkflowPlan`.

---

## Task Orchestration

### DAG-Based Execution

Workflows define execution order through explicit dependencies:

```python
WorkflowNode(
    node_id="architecture-review",
    task=ArchitectureReviewTask,
    depends_on=(),  # No dependencies - runs first
)
WorkflowNode(
    node_id="impact-analysis",
    task=ImpactAnalysisTask,
    depends_on=("architecture-review",),  # Depends on architecture
)
WorkflowNode(
    node_id="implementation",
    task=ImplementationTask,
    depends_on=("impact-analysis",),  # Depends on impact
)
```

### Linear Pipeline

```
architecture-review → impact-analysis → implementation
```

### DAG (Directed Acyclic Graph)

```
        architecture-review
          /              \
      impact-analysis   diagnostics
          \              /
        implementation
```

A linear workflow is simply a DAG where each node depends on the previous one.

### Deterministic Ordering

The WorkflowEngine uses topological sorting with alphabetical tie-breaking to ensure deterministic execution order. Running the same workflow twice always produces the same execution order.

---

## Context Merging

The WorkflowEngine merges `ContextPackage`s returned by Tasks.

### ContextPackageMerger

```python
from packages.context.context_merger import ContextPackageMerger

merger = ContextPackageMerger()
merged = merger.merge([context_package_1, context_package_2, ...])
```

### Merging Rules

1. **Deterministic ordering**: Repeated execution produces identical merged `ContextPackage`s.
2. **Duplicate elimination**: Duplicate packages are removed.
3. **Preserve ranking**: Original ranking order is preserved.
4. **Preserve token estimates**: Token estimates are aggregated.

### Architecture

```
Task A → ContextPackage A ─┐
                           ├────────► ContextPackageMerger ──► Merged ContextPackage
Task B → ContextPackage B ─┘
```

---

## Metrics Aggregation

WorkflowMetrics are aggregated from TaskMetrics across all workflow tasks.

### Aggregation Rules

| Field | Aggregation |
|-------|-------------|
| `estimated_tokens` | Sum of all task tokens |
| `estimated_duration_ms` | Sum of all task durations |
| `estimated_complexity` | Maximum complexity level |

### Complexity Hierarchy

```
LOW < MEDIUM < HIGH < VERY_HIGH
```

### Architecture

```
TaskMetrics A (100 tokens, LOW) ─┐
                                  ├────────► Sum/Max ──► WorkflowMetrics
TaskMetrics B (200 tokens, HIGH) ─┘
```

Result:

| Field | Value |
|-------|-------|
| `estimated_tokens` | 300 |
| `estimated_duration_ms` | (sum) |
| `estimated_complexity` | HIGH |

---

## Constraint Aggregation

TaskConstraints are aggregated and deduplicated across all workflow tasks.

### Deduplication Rules

Constraints are deduplicated by `(type, description)` tuple.

### Architecture

```
TaskConstraint A (read-only, "must not modify") ─┐
                                                   ├────────► Deduplicate ──► Unique Constraints
TaskConstraint B (read-only, "must not modify") ─┘
TaskConstraint C (timeout, "complete within 30s") ─┘
```

Result:

```
1. (read-only, "must not modify")
2. (timeout, "complete within 30s")
```

---

## Registry

The `WorkflowRegistry` manages workflow registration, lookup, and discovery.

### Public API

```python
from packages.workflows.registry import WorkflowRegistry

registry = WorkflowRegistry()

# Register
registry.register("implement-feature", ImplementFeatureWorkflow)

# Lookup
workflow_cls = registry.get("implement-feature")

# Check existence
has_it = registry.has("implement-feature")  # True

# List all (sorted)
all_workflows = registry.all()  # ["implement-feature", ...]

# Unregister
registry.unregister("implement-feature")
```

### Constraints

- Stores workflow **classes**, not instances.
- Prevents duplicate registration.
- Returns deterministic ordering (sorted).

---

## Factory

The `WorkflowFactory` creates workflow instances through the registry.

### Public API

```python
from packages.workflows.factory import WorkflowFactory
from packages.workflows.registry import WorkflowRegistry

registry = WorkflowRegistry()
registry.register("implement-feature", ImplementFeatureWorkflow)

factory = WorkflowFactory(registry)
workflow = factory.create("implement-feature")
```

### Constraints

- No hardcoded workflow classes.
- All lookup goes through the registry.
- Deterministic error messages.

---

## Built-in Workflows

### ImplementFeatureWorkflow

```
Architecture Review → Impact Analysis → Implementation Task
```

Tasks:

1. **Architecture Review**: Analyze the repository architecture.
2. **Impact Analysis**: Determine the impact of the requested change.
3. **Implementation Task**: Create an implementation plan.

### ReviewWorkflow

```
Architecture Review → Diagnostics → Review Task
```

Tasks:

1. **Architecture Review**: Analyze the repository architecture.
2. **Diagnostics**: Run repository diagnostics.
3. **Review Task**: Create a review plan.

### RefactorWorkflow

```
Impact Analysis → Refactoring Advisor → Refactor Task
```

Tasks:

1. **Impact Analysis**: Determine the impact of the refactoring.
2. **Refactoring Advisor**: Get refactoring advice.
3. **Refactor Task**: Create a refactoring plan.

---

## Future Workflows

Future workflows require only one Workflow class + registration:

- PR Review
- Large Refactoring
- Feature Implementation
- API Migration
- Test Generation
- Security Audit
- Documentation Generation
- DSPARK

---

## Models

### WorkflowNode

```python
@dataclass(frozen=True, slots=True)
class WorkflowNode:
    node_id: str
    task: type[Task]
    depends_on: tuple[str, ...] = ()
    parallelizable: bool = False
```

### WorkflowStep

```python
@dataclass(frozen=True, slots=True)
class WorkflowStep:
    step_id: str
    order: int
    workflow_node: str
    task_name: str
    description: str
```

### WorkflowMetrics

```python
@dataclass(frozen=True, slots=True)
class WorkflowMetrics:
    estimated_tokens: int = 0
    estimated_duration_ms: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW
```

### WorkflowPlan

```python
@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    workflow_name: str
    task_plans: tuple[TaskPlan, ...]
    workflow_steps: tuple[WorkflowStep, ...]
    merged_context_package: ContextPackage
    metrics: WorkflowMetrics
    constraints: tuple[TaskConstraint, ...]
```

All models are immutable (`frozen=True, slots=True`).

---

## WorkflowGraph

The `WorkflowGraph` owns all DAG operations:

- Validate node IDs (no duplicates)
- Validate dependencies (all referenced nodes exist)
- Detect cycles (no directed cycles allowed)
- Detect unreachable nodes (all nodes must be reachable from roots)
- Deterministic topological sort (stable, alphabetical tie-break)
- Execution layer grouping

### Architecture

```
WorkflowEngine
    ↓
WorkflowGraph ← DAG validation + topological sort
    ↓
ordered WorkflowNodes
```

---

## Public API Summary

```python
from packages.workflows.base import Workflow
from packages.workflows.factory import WorkflowFactory
from packages.workflows.engine import WorkflowEngine
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowNode,
    WorkflowPlan,
    WorkflowStep,
)
from packages.workflows.registry import WorkflowRegistry

# 1. Create registry and register workflows
registry = WorkflowRegistry()
registry.register("implement-feature", ImplementFeatureWorkflow)

# 2. Create factory
factory = WorkflowFactory(registry)

# 3. Create workflow instance
workflow = factory.create("implement-feature")

# 4. Create engine
engine = WorkflowEngine()

# 5. Generate plan
request = TaskRequest(query="Implement OAuth authentication")
plan: WorkflowPlan = engine.generate_plan(
    workflow=workflow,
    repository_index=repository_index,
    request=request,
)

# 6. Estimate metrics
metrics: WorkflowMetrics = engine.estimate(
    workflow=workflow,
    repository_index=repository_index,
    request=request,
)
```

---

## Architectural Constraints

The WorkflowEngine must NOT:

- Inspect AST
- Parse repositories
- Edit source code
- Invoke providers
- Duplicate Task logic
- Duplicate Capability logic
- Duplicate Repository analysis

The WorkflowEngine consumes only public Task APIs.

Tasks consume only public Capability APIs.

Capabilities consume only public Repository APIs.

---

## Testing

```bash
# Run all workflow tests
pytest tests/workflows/ -v

# Run with coverage
pytest tests/workflows/ -v --cov=packages.workflows --cov-report=term-missing

# Run with ruff
ruff check packages/workflows/ tests/workflows/

# Run mypy
mypy packages/workflows/ tests/workflows/