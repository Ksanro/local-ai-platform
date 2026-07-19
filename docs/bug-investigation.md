# Bug Investigation Workflow v1

## Overview

The Bug Investigation workflow assists in identifying the most likely repository locations, affected symbols, dependencies, and architectural impact for a reported software defect. It produces a deterministic investigation plan suitable for an AI coding agent.

**No providers are invoked. No source code is modified.**

## Architecture

```
BugInvestigationRequest
    ↓ to_task_request()
TaskRequest
    ↓
BugInvestigationWorkflow
    ↓
BugInvestigationTask
    ↓
RepositoryIndex + TaskRequest
    ↓
TaskPlan
```

## Workflow DAG

```
    repository-search
        /       |       \\
       v        v        v
    architecture-review   diagnostics   impact-analysis
        \\         |         /
         v        v        v
        cross-reference
                |
                v
          context-builder
                |
                v
           WorkflowPlan
```

## Components

### BugInvestigationRequest

The immutable input model for bug investigation:

```python
@dataclass(frozen=True, slots=True)
class BugInvestigationRequest:
    summary: str
    description: str
    suspected_modules: tuple[str, ...]
    suspected_symbols: tuple[str, ...]
    observed_stacktrace: str | None
    reproduction_steps: tuple[str, ...]
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `summary` | `str` | Brief summary of the bug |
| `description` | `str` | Detailed description of the bug |
| `suspected_modules` | `tuple[str, ...]` | Module paths suspected to contain the bug |
| `suspected_symbols` | `tuple[str, ...]` | Symbol names suspected to be involved |
| `observed_stacktrace` | `str \| None` | Optional stacktrace observed during the bug |
| `reproduction_steps` | `tuple[str, ...]` | Steps to reproduce the bug |

**Mapper:**

```python
request = BugInvestigationRequest(
    summary="Auth fails on timeout",
    description="Authentication fails when session expires",
    suspected_modules=("packages/auth/", "packages/session/"),
    suspected_symbols=("authenticate", "validate_session"),
    observed_stacktrace="TimeoutError at line 42",
    reproduction_steps=("login", "wait", "access protected resource"),
)

task_request = request.to_task_request()
```

### TaskRequest

The intermediate representation consumed by the task framework. The `BugInvestigationRequest.to_task_request()` method maps fields into:

- `query` — constructed from summary and description
- `options` — contains suspected_modules, suspected_symbols, observed_stacktrace, reproduction_steps
- `user_messages` — tuple of (summary, description)
- `repository_root` — always `"."`

### Workflow

The `BugInvestigationWorkflow` class orchestrates the investigation pipeline:

```python
from packages.workflows.workflows.bug_investigation import BugInvestigationWorkflow

workflow = BugInvestigationWorkflow()
plan = workflow.plan(repository_index, request)
```

**DAG Nodes:**

| Node ID | Task Class | Depends On |
|---------|------------|------------|
| `repository-search` | `InvestigateBugTask` | — |
| `architecture-review` | `ArchitectureReviewTask` | `repository-search` |
| `diagnostics` | `DiagnosticsTask` | `repository-search` |
| `impact-analysis` | `ImpactAnalysisTask` | `repository-search` |
| `cross-reference` | `ReviewPullRequestTask` | `architecture-review`, `diagnostics`, `impact-analysis` |
| `context-builder` | `ContextBuilderTask` | `cross-reference` |

**Methods:**

- `name` — Returns `"bug-investigation"`
- `workflow_nodes` — Returns the tuple of `WorkflowNode` instances
- `plan()` — Generates a `WorkflowPlan` from repository data and request
- `estimate()` — Computes execution estimates

### Tasks

#### InvestigateBugTask

The primary task that identifies likely affected symbols and modules:

```python
from packages.tasks.investigate_bug import InvestigateBugTask

task = InvestigateBugTask()
plan = task.plan(repository_index, request)
```

**Responsibilities:**

1. Identify likely affected symbols from `suspected_symbols` in request options
2. Identify likely affected modules from `suspected_modules` in request options
3. Collect dependency information from repository index
4. Collect diagnostics from repository index
5. Collect architecture findings from repository index
6. Produce a `TaskPlan` describing the investigation scope

**TaskPlan Steps:**

| Order | Title | Description |
|-------|-------|-------------|
| 0 | Identify candidate symbols | Identify candidate symbols from suspected symbols |
| 1 | Identify affected modules | Identify affected modules from suspected modules |
| 2 | Collect dependency paths | Collect dependency paths for candidate symbols |
| 3 | Collect diagnostics | Collect diagnostics findings |
| 4 | Collect architecture findings | Collect architecture findings |
| 5 | Build investigation context | Build investigation context summary |

#### Supporting Tasks

The workflow also consumes existing tasks:

- **ArchitectureReviewTask** — Analyzes modules, dependency cycles, layering violations, orphan modules, high coupling modules
- **DiagnosticsTask** — Checks dead symbols, dependency cycles, orphan modules, large modules
- **ImpactAnalysisTask** — Analyzes impact of changed symbols
- **ReviewPullRequestTask** — Used as cross-reference engine
- **ContextBuilderTask** — Builds context for the final plan

### Capability

The `BugInvestigationCapability` class orchestrates the capability pipeline:

```python
from packages.capabilities.bug_investigation import BugInvestigationCapability

capability = BugInvestigationCapability()
result = capability.execute(query="Why is auth failing?", repository_index=index)
```

**Properties:**

| Property | Value | Description |
|----------|-------|-------------|
| `name` | `"bug-investigation"` | Unique capability name |
| `intent` | `PlannerIntent.DEBUG` | Debug intent for investigation |
| `profile` | `DEBUG_PROFILE` | DEBUG retrieval profile |

**Pipeline:**

1. **Stage 1 — Planning:** Invoke `ContextPlanner` with the query
2. **Stage 2 — Repository Search:** Query the repository index with `find()`
3. **Stage 3 — Context Building:** Build context using `ContextBuilder`
4. **Stage 4 — Package Assembly:** Assemble `ContextPackage` from builder output
5. **Stage 5 — Serialization:** Serialize to `ProviderRequest`

**Retrieval Profile (DEBUG):**

| Option | Value |
|--------|-------|
| `include_callers` | `true` |
| `include_callees` | `true` |
| `include_diagnostics` | `true` |
| `include_dependencies` | `true` |
| `relationship_depth` | `2` |
| `include_dead_code` | `false` |
| `include_tests` | `true` |

### WorkflowPlan

The `WorkflowPlan` is the final output of the workflow:

```python
from packages.workflows.models import WorkflowPlan

plan = workflow.plan(repository_index, request)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `workflow_name` | `str` | `"bug-investigation"` |
| `task_plans` | `tuple[TaskPlan, ...]` | Execution plans for each task |
| `workflow_steps` | `tuple[WorkflowStep, ...]` | Ordered workflow steps |
| `merged_context_package` | `ContextPackage` | Merged context from all tasks |
| `metrics` | `WorkflowMetrics` | Aggregated workflow metrics |
| `constraints` | `tuple[TaskConstraint, ...]` | Aggregated constraints |

**Plan Contents:**

- **Candidate symbols** — Symbols identified as likely involved in the bug
- **Affected modules** — Modules identified as likely containing the bug
- **Dependency paths** — Dependency relationships involving candidate symbols
- **Diagnostics** — Dead symbols, orphan modules, large modules, dependency cycles
- **Architecture findings** — Dependency cycles, high coupling modules, layering violations
- **Investigation context** — Summary of all findings for the AI coding agent

## Repository Search

The repository search step identifies affected symbols and modules:

1. Extract suspected symbols and modules from request options
2. Validate each symbol against `repository_index.find()`
3. Validate each module against `repository_index.find_module()`
4. Include both validated and unvalidated items as candidates (external symbols may not be in the index)

## Dependency Analysis

Dependency paths are collected from the repository index:

1. Query `repository_index.relationships()` for all relationships
2. Filter relationships where source or target matches candidate symbols
3. Build path strings from relationship source → target
4. Also check module-level dependencies from `repository_index.modules`

## Impact Analysis

Impact analysis identifies the blast radius of the bug:

1. Extract changed symbols from request options
2. Analyze impact using `ChangeImpactAnalyzer`
3. Collect callers, callees, and transitive dependencies

## Context Generation

Context is generated by combining:

1. **Primary symbol** — First candidate symbol from repository search
2. **Supporting symbols** — Remaining candidates ordered by rank
3. **Related callers** — Symbols that call the primary symbol
4. **Related callees** — Symbols called by the primary symbol
5. **Related modules** — All modules containing candidate symbols
6. **Relationship summary** — Counts of callers, callees, modules, symbols

## Constraints

The implementation must:

- **Compose existing public APIs exclusively**
- **NOT** invoke providers
- **NOT** call LLMs
- **NOT** edit source code
- **NOT** inspect AST directly
- **NOT** duplicate repository logic
- **NOT** duplicate diagnostics
- **NOT** duplicate architecture logic

## Usage

```python
from packages.tasks.bug_investigation_request import BugInvestigationRequest
from packages.workflows.workflows.bug_investigation import BugInvestigationWorkflow

# Create the request
request = BugInvestigationRequest(
    summary="Auth fails on timeout",
    description="Authentication fails when session expires",
    suspected_modules=("packages/auth/", "packages/session/"),
    suspected_symbols=("authenticate", "validate_session"),
    observed_stacktrace="TimeoutError at line 42",
    reproduction_steps=("login", "wait", "access protected resource"),
)

# Convert to TaskRequest
task_request = request.to_task_request()

# Create the workflow
workflow = BugInvestigationWorkflow()

# Generate the plan
plan = workflow.plan(repository_index, task_request)

# Access the results
for task_plan in plan.task_plans:
    print(f"Task: {task_plan.task_name}")
    for step in task_plan.steps:
        print(f"  Step {step.order}: {step.title}")
        print(f"    {step.description}")
```

## Testing

Tests verify:

- Immutable request model (`frozen=True`)
- Deterministic WorkflowPlan
- Candidate symbols identified
- Dependency paths included
- Diagnostics included
- Architecture findings included
- Serializer accepts WorkflowPlan
- >95% coverage

Run tests with:

```bash
pytest tests/tasks/test_investigate_bug.py tests/capabilities/test_bug_investigation.py tests/workflows/test_bug_investigation.py -v
```

## Files

| File | Description |
|------|-------------|
| `packages/tasks/bug_investigation_request.py` | `BugInvestigationRequest` dataclass |
| `packages/tasks/investigate_bug.py` | `InvestigateBugTask` |
| `packages/capabilities/bug_investigation.py` | `BugInvestigationCapability` |
| `packages/workflows/workflows/bug_investigation.py` | `BugInvestigationWorkflow` |
| `tests/tasks/test_investigate_bug.py` | Task tests |
| `tests/capabilities/test_bug_investigation.py` | Capability tests |
| `tests/workflows/test_bug_investigation.py` | Workflow tests |