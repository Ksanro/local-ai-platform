# Pull Request Review Workflow v1

## Overview

The Pull Request Review workflow analyzes a proposed code change and produces a deterministic review package suitable for an LLM. This feature validates the platform architecture by composing existing components without introducing new infrastructure.

## Input

### PullRequestReviewRequest

```python
@dataclass(frozen=True, slots=True)
class PullRequestReviewRequest:
    title: str
    description: str
    changed_files: tuple[str, ...] = ()
    changed_symbols: tuple[str, ...] = ()
    user_notes: str | None = None
```

This model is immutable (frozen dataclass with slots). It represents the domain-specific input for a pull request review.

### Conversion to TaskRequest

The `PullRequestReviewRequest` is converted to the platform's `TaskRequest` via the `to_task_request()` method:

```python
request = PullRequestReviewRequest(
    title="Add caching layer",
    description="Add an LRU cache to the gateway",
    changed_files=("apps/gateway/cache.py", "apps/gateway/main.py"),
    changed_symbols=("Cache", "get_cache"),
    user_notes="Ensure thread safety",
)

task_request = request.to_task_request()
```

The conversion maps:
- `title` → `options["pr_title"]`
- `description` → `options["pr_description"]`
- `changed_files` → `options["changed_files"]`
- `changed_symbols` → `options["changed_symbols"]`
- `user_notes` → `options["user_notes"]`
- Combined text → `query`

## Workflow

### PullRequestReviewWorkflow

The workflow defines a DAG (Directed Acyclic Graph) with the following structure:

```
    repository-search
        /       |       \
       v        v        v
    architecture-review   diagnostics   impact-analysis
        \         |         /
         v        v        v
       refactoring-advisor
               |
               v
          context-builder
               |
               v
         execution-planner
```

### DAG Structure

| Node | Dependencies | Task Class |
|------|-------------|------------|
| `repository-search` | (none) | `ReviewPullRequestTask` |
| `architecture-review` | `repository-search` | `ArchitectureReviewTask` |
| `diagnostics` | `repository-search` | `DiagnosticsTask` |
| `impact-analysis` | `repository-search` | `ImpactAnalysisTask` |
| `refactoring-advisor` | `architecture-review`, `diagnostics`, `impact-analysis` | `RefactoringAdvisorTask` |
| `context-builder` | `refactoring-advisor` | `ContextBuilderTask` |
| `execution-planner` | `context-builder` | `ExecutionPlannerTask` |

### Parallel Branches

Three branches run in parallel after `repository-search`:

1. **Architecture Review** — Analyzes module coupling, layering, and dependency cycles
2. **Diagnostics** — Identifies dead code, orphan modules, large modules, and dependency cycles
3. **Impact Analysis** — Analyzes the impact of changed symbols

These branches converge at `refactoring-advisor`, which aggregates results from all three.

## Tasks

### ReviewPullRequestTask

**Responsibilities:**
- Identify affected symbols from `changed_symbols` in request options
- Identify affected modules from `changed_files` in request options
- Validate affected symbols and modules against the `RepositoryIndex`
- Produce a `TaskPlan` describing the review scope

**Output:**
- Steps: "Identify affected symbols", "Identify affected modules", "Build review scope summary"
- Constraints: `read-only`, `deterministic`

### ArchitectureReviewTask

**Responsibilities:**
- Invoke `ArchitectureAnalyzer`
- Collect architecture findings (modules, dependency cycles, layering violations, orphan modules, high coupling modules)
- Produce a `TaskPlan` describing the architecture

### DiagnosticsTask

**Responsibilities:**
- Invoke `DiagnosticsEngine`
- Collect diagnostics findings (dead symbols, dependency cycles, orphan modules, large modules)
- Produce a `TaskPlan` describing diagnostics results

### ImpactAnalysisTask

**Responsibilities:**
- Extract changed symbols from request options
- Analyze impact of changed symbols
- Produce a `TaskPlan` describing impact analysis

### RefactoringAdvisorTask

**Responsibilities:**
- Invoke `RefactoringAdvisor`
- Collect refactoring opportunities
- Produce a `TaskPlan` describing refactoring opportunities

### ContextBuilderTask

**Responsibilities:**
- Invoke `ContextBuilder`
- Build context from repository index using PR information
- Produce a `TaskPlan` describing context results

### ExecutionPlannerTask

**Responsibilities:**
- Summarize affected architecture
- Review dependency impact
- Identify diagnostics
- Identify refactoring opportunities
- Generate review context
- Produce a `TaskPlan` with execution steps

## Capabilities

### PullRequestReviewCapability

**Responsibilities:**
- Convert `PullRequestReviewRequest` to `TaskRequest`
- Execute the capability pipeline
- Aggregate results

**Public API:**

```python
from packages.capabilities.pull_request_review import (
    PullRequestReviewCapability,
    PullRequestReviewRequest,
)

request = PullRequestReviewRequest(
    title="Add caching layer",
    description="Add an LRU cache to the gateway",
    changed_files=("apps/gateway/cache.py",),
    changed_symbols=("Cache",),
    user_notes="Ensure thread safety",
)

capability = PullRequestReviewCapability()
result = capability.execute(request)
```

## Execution Plan

The workflow produces a `WorkflowPlan` with the following steps:

| Order | Step | Description |
|-------|------|-------------|
| 0 | `repository-search` | Identify affected symbols and modules |
| 1 | `architecture-review` | Analyze module coupling and layering |
| 2 | `diagnostics` | Identify dead code and orphans |
| 3 | `impact-analysis` | Analyze impact of changed symbols |
| 4 | `refactoring-advisor` | Aggregate refactoring opportunities |
| 5 | `context-builder` | Build context from repository |
| 6 | `execution-planner` | Generate review context |

### WorkflowPlan Structure

```python
WorkflowPlan(
    workflow_name="pull-request-review",
    task_plans=(
        TaskPlan(task_name="review-pull-request", ...),
        TaskPlan(task_name="architecture-review", ...),
        TaskPlan(task_name="diagnostics", ...),
        TaskPlan(task_name="impact-analysis", ...),
        TaskPlan(task_name="refactoring-advisor", ...),
        TaskPlan(task_name="context-builder", ...),
        TaskPlan(task_name="execution-planner", ...),
    ),
    workflow_steps=(
        WorkflowStep(order=0, workflow_node="repository-search", ...),
        WorkflowStep(order=1, workflow_node="architecture-review", ...),
        WorkflowStep(order=2, workflow_node="diagnostics", ...),
        WorkflowStep(order=3, workflow_node="impact-analysis", ...),
        WorkflowStep(order=4, workflow_node="refactoring-advisor", ...),
        WorkflowStep(order=5, workflow_node="context-builder", ...),
        WorkflowStep(order=6, workflow_node="execution-planner", ...),
    ),
    constraints=(...),
    metrics=WorkflowMetrics(...),
)
```

## Serializer

The resulting `WorkflowPlan` is compatible with the existing `SerializerFactory` and `ProviderSerializer`:

```python
from packages.serializers.factory import SerializerFactory

factory = SerializerFactory()
serializer = factory.create("workflow-plan")
serialized = serializer.serialize(plan)
```

No review-specific serializer is added. The existing serialization infrastructure handles the `WorkflowPlan`.

## Architecture Composition

The Pull Request Review workflow composes the following existing platform components:

| Component | Source | Purpose |
|-----------|--------|---------|
| `WorkflowEngine` | `packages.workflows.engine` | Orchestrates task planning in deterministic order |
| `WorkflowGraph` | `packages.workflows.models` | DAG validation and topological sorting |
| `ReviewPullRequestTask` | `packages.tasks.review_pull_request` | Repository search for PR review |
| `ArchitectureReviewTask` | `packages.tasks.architecture_review` | Architecture analysis |
| `DiagnosticsTask` | `packages.tasks.diagnostics` | Repository diagnostics |
| `ImpactAnalysisTask` | `packages.tasks.impact_analysis` | Change impact analysis |
| `RefactoringAdvisorTask` | `packages.tasks.refactoring_advisor` | Refactoring opportunities |
| `ContextBuilderTask` | `packages.tasks.context_builder` | Context building |
| `ExecutionPlannerTask` | `packages.tasks.execution_planner` | Execution planning |
| `PullRequestReviewRequest` | `packages.capabilities.pull_request_review` | Domain-specific input model |
| `PullRequestReviewCapability` | `packages.capabilities.pull_request_review` | Capability orchestration |
| `SerializerFactory` | `packages.serializers.factory` | Plan serialization |

## Constraints

The implementation must NOT:

- Invoke providers
- Call LLMs
- Edit source code
- Inspect AST directly
- Duplicate repository analysis
- Duplicate diagnostics
- Duplicate architecture logic

All operations use existing public APIs exclusively.

## Repository Layout

```
packages/capabilities/pull_request_review.py    # Request model + capability
packages/tasks/review_pull_request.py            # Repository search task
packages/tasks/architecture_review.py            # Architecture review task
packages/tasks/diagnostics.py                    # Diagnostics task
packages/tasks/impact_analysis.py                # Impact analysis task
packages/tasks/refactoring_advisor.py            # Refactoring advisor task
packages/tasks/context_builder.py                # Context builder task
packages/tasks/execution_planner.py              # Execution planner task
packages/workflows/workflows/pull_request_review.py  # Workflow
tests/capabilities/test_pull_request_review.py  # Capability tests
tests/tasks/test_review_pull_request.py         # Task tests
tests/workflows/test_pull_request_review.py     # Workflow tests
docs/pull-request-review.md                     # Documentation
```

## Quality Gates

- `pytest` passes with >95% coverage
- `ruff` passes
- `mypy` passes
- Deterministic workflow
- Deterministic `WorkflowPlan`
- No duplicated framework logic
- Documentation complete