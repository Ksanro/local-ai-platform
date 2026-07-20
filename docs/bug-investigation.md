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
BugInvestigationCapability
    ↓
RepositoryIndex + ContextPlanner + ContextBuilder
    ↓
CapabilityResult (with investigation_report)
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
    title: str
    description: str = ""
    observed_behavior: str = ""
    expected_behavior: str = ""
    changed_files: tuple[str, ...] = ()
    changed_symbols: tuple[str, ...] = ()
    stack_trace: str | None = None
    logs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | `str` | Brief summary of the bug (required) |
| `description` | `str` | Detailed description of the bug |
| `observed_behavior` | `str` | What actually happens when the bug occurs |
| `expected_behavior` | `str` | What should happen in normal operation |
| `changed_files` | `tuple[str, ...]` | File paths that were recently changed |
| `changed_symbols` | `tuple[str, ...]` | Symbol names that were recently changed |
| `stack_trace` | `str \| None` | Optional stacktrace observed during the bug |
| `logs` | `tuple[str, ...]` | Log messages related to the bug |
| `tags` | `tuple[str, ...]` | Tags for categorizing the bug |

**Mapper:**

```python
request = BugInvestigationRequest(
    title="Auth fails on timeout",
    description="Authentication fails when session expires",
    observed_behavior="TimeoutError after 30s",
    expected_behavior="Successful authentication",
    changed_files=("packages/auth/auth.py", "packages/session/session.py"),
    changed_symbols=("authenticate", "validate_session"),
    stack_trace="TimeoutError at line 42",
    logs=("ERROR: timeout", "WARN: session expired"),
    tags=("auth", "timeout", "session"),
)

task_request = request.to_task_request()
```

### TaskRequest

The intermediate representation consumed by the task framework. The `BugInvestigationRequest.to_task_request()` method maps fields into:

- `query` — constructed from title and description
- `options` — contains changed_files, changed_symbols, stack_trace, logs, tags
- `user_messages` — tuple of (title, description)
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

### Task

#### InvestigateBugTask

The primary task that identifies likely affected symbols and modules:

```python
from packages.tasks.investigate_bug import InvestigateBugTask

task = InvestigateBugTask()
plan = task.plan(repository_index, request)
```

**Responsibilities:**

1. Identify likely affected symbols from `changed_symbols` in request options
2. Identify likely affected modules from `changed_files` in request options
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

### Investigation Report

The `CapabilityResult` includes an `investigation_report` field with metadata:

```python
result = capability.execute(query="Auth fails on timeout", repository_index=index)
report = result.investigation_report
```

**Report Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `affected_modules` | `tuple[str, ...]` | Modules identified as affected |
| `affected_symbols` | `tuple[str, ...]` | Symbols identified as affected |
| `dependency_summary` | `str` | Summary of dependency relationships |
| `diagnostics_summary` | `str` | Summary of diagnostic findings |
| `impact_summary` | `str` | Summary of impact analysis |
| `architectural_findings` | `tuple[str, ...]` | Architectural issues found |
| `refactoring_opportunities` | `tuple[str, ...]` | Suggested refactoring opportunities |
| `context_statistics` | `dict` | Statistics about the context package |
| `estimated_tokens` | `int` | Estimated token usage |

**Context Statistics:**

| Field | Type | Description |
|-------|------|-------------|
| `primary_symbol` | `str` | Primary symbol qualified name |
| `supporting_symbols_count` | `int` | Number of supporting symbols |
| `related_callers_count` | `int` | Number of related callers |
| `related_callees_count` | `int` | Number of related callees |
| `related_modules_count` | `int` | Number of related modules |
| `total_symbols` | `int` | Total symbol count |

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

## Request Flow

```
User Request (BugInvestigationRequest)
    ↓
Workflow (BugInvestigationWorkflow)
    ↓
Task (InvestigateBugTask)
    ↓
Capability (BugInvestigationCapability)
    ↓
Repository Intelligence (RepositoryIndex + ContextPlanner + ContextBuilder)
    ↓
Context Package (ContextPackage)
    ↓
Execution Engine (responsible for execution, not this workflow)
```

## Why Investigation is Deterministic

The bug investigation workflow produces deterministic output because:

1. **No randomness:** All operations use deterministic algorithms — no random sampling, no stochastic ranking.
2. **Fixed input:** Given the same `BugInvestigationRequest` and `RepositoryIndex`, the same output is always produced.
3. **No external dependencies:** The workflow does not call providers, LLMs, or any external services.
4. **Immutable models:** All request, result, and plan models are frozen dataclasses with slots.
5. **No state mutation:** The workflow does not mutate the repository index or any input data.
6. **Sorted outputs:** All outputs are sorted (e.g., module names, symbol names) to ensure consistent ordering.

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
- **NOT** invoke the Execution Engine

## Usage

```python
from packages.tasks.bug_investigation_request import BugInvestigationRequest
from packages.workflows.workflows.bug_investigation import BugInvestigationWorkflow

# Create the request
request = BugInvestigationRequest(
    title="Auth fails on timeout",
    description="Authentication fails when session expires",
    observed_behavior="TimeoutError after 30s",
    expected_behavior="Successful authentication",
    changed_files=("packages/auth/auth.py", "packages/session/session.py"),
    changed_symbols=("authenticate", "validate_session"),
    stack_trace="TimeoutError at line 42",
    logs=("ERROR: timeout", "WARN: session expired"),
    tags=("auth", "timeout", "session"),
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
- Deterministic TaskPlan
- Deterministic CapabilityResult
- Workflow uses only public APIs
- No repository duplication
- No provider execution
- >95% coverage

Run tests with:

```bash
pytest tests/tasks/test_bug_investigation_request.py tests/tasks/test_investigate_bug.py tests/capabilities/test_bug_investigation.py tests/workflows/test_bug_investigation.py -v
```

## Files

| File | Description |
|------|-------------|
| `packages/tasks/bug_investigation_request.py` | `BugInvestigationRequest` dataclass |
| `packages/tasks/investigate_bug.py` | `InvestigateBugTask` |
| `packages/tasks/bug_investigation.py` | `BugInvestigationTask` (alias) |
| `packages/capabilities/bug_investigation.py` | `BugInvestigationCapability` |
| `packages/workflows/workflows/bug_investigation.py` | `BugInvestigationWorkflow` |
| `tests/tasks/test_bug_investigation_request.py` | Request model tests |
| `tests/tasks/test_investigate_bug.py` | Task tests |
| `tests/capabilities/test_bug_investigation.py` | Capability tests |
| `tests/workflows/test_bug_investigation.py` | Workflow tests |