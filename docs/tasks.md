# Task Framework v1

> Executable development workflows.

## Overview

Tasks represent executable engineering workflows.

They consume existing capabilities and repository intelligence to build deterministic execution plans.

Tasks **do not**:

- Call providers
- Edit source code
- Inspect AST
- Parse repositories
- Duplicate capability logic

Tasks describe **what should happen**, not **how an LLM performs it**.

## Architecture

```
User Request
      │
      ▼
TaskRequest
      │
      ▼
Task
      │
      ▼
Capability
      │
      ▼
Planner
      │
      ▼
Repository Intelligence
      │
      ▼
Context Package
      │
      ▼
Serializer
      │
      ▼
LLM
```

## Public API

```python
from packages.tasks.base import Task
from packages.tasks.factory import TaskFactory
from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskRequest,
    TaskStep,
)
from packages.tasks.registry import TaskRegistry

# 1. Create registry and register tasks
registry = TaskRegistry()
registry.register("refactor", RefactorTask)

# 2. Create factory
factory = TaskFactory(registry)

# 3. Create a task instance
task = factory.create("refactor")

# 4. Create a request
request = TaskRequest(
    query="Refactor ProviderFactory",
    repository_root=".",
)

# 5. Plan
plan = task.plan(
    repository_index=index,
    request=request,
)
```

## Task

The `Task` ABC defines the interface for all tasks.

```python
class Task(ABC):

    @property
    def name(self) -> str:
        ...

    @property
    def capability(self) -> str:
        ...

    def plan(
        self,
        repository_index: RepositoryIndex,
        request: TaskRequest,
    ) -> TaskPlan:
        ...
```

### Lifecycle

Tasks follow an explicit lifecycle:

1. **`plan()`** — Produce a `TaskPlan` from repository data and request.

Future lifecycle stages (when needed):

2. **`validate()`** — Validate the plan against constraints.
3. **`estimate()`** — Compute execution estimates.

### Constraints

- Tasks are **stateless** (no instance attributes beyond the ABC).
- Tasks orchestrate existing public APIs only.
- Tasks must not access providers directly, parse repositories,
  implement ranking, planning, or serialization.

## TaskRequest

Input request for a task execution.

```python
@dataclass(frozen=True, slots=True)
class TaskRequest:
    query: str
    repository_root: str = "."
    user_messages: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    options: dict[str, object] = field(default_factory=dict)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's natural language query. |
| `repository_root` | `str` | Path to the repository root directory. |
| `user_messages` | `tuple[str, ...]` | Optional list of user messages providing context. |
| `constraints` | `tuple[str, ...]` | Additional constraint identifiers. |
| `options` | `dict[str, object]` | Task-specific configuration options. |

## TaskPlan

Complete execution plan for a task.

```python
@dataclass(frozen=True, slots=True)
class TaskPlan:
    task_name: str
    capability: str
    context_package: object
    steps: tuple[TaskStep, ...] = ()
    constraints: tuple[TaskConstraint, ...] = ()
    metrics: TaskMetrics = field(default_factory=TaskMetrics)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `task_name` | `str` | Unique task identifier. |
| `capability` | `str` | The capability consumed by this task. |
| `context_package` | `object` | The assembled context package. |
| `steps` | `tuple[TaskStep, ...]` | Execution steps in deterministic order. |
| `constraints` | `tuple[TaskConstraint, ...]` | Constraints applicable to this task. |
| `metrics` | `TaskMetrics` | Estimated execution metrics. |

## TaskStep

An immutable step in a task execution plan.

```python
@dataclass(frozen=True, slots=True)
class TaskStep:
    order: int
    title: str
    description: str
    required_symbols: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `order` | `int` | Execution order (0-based, deterministic). |
| `title` | `str` | Human-readable step title. |
| `description` | `str` | Detailed step description. |
| `required_symbols` | `tuple[str, ...]` | Symbols required for this step. |
| `required_modules` | `tuple[str, ...]` | Modules required for this step. |

## TaskMetrics

Estimated metrics for a task execution.

```python
@dataclass(frozen=True, slots=True)
class TaskMetrics:
    estimated_tokens: int = 0
    estimated_complexity: TaskComplexity = TaskComplexity.LOW
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `estimated_tokens` | `int` | Estimated token count for the context. |
| `estimated_complexity` | `TaskComplexity` | Complexity level of the task. |

## TaskComplexity

```python
class TaskComplexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
```

## TaskConstraint

A constraint that applies to task execution.

```python
@dataclass(frozen=True, slots=True)
class TaskConstraint:
    type: str
    description: str
```

### Common Constraint Types

| Type | Description |
|------|-------------|
| `read_only` | Task must not modify source code |
| `no_provider` | Task must not call providers |
| `requires_repository` | Task requires repository index |
| `deterministic` | Task must produce deterministic output |
| `no_filesystem` | Task must not access filesystem |

## TaskRegistry

Manages registration, lookup, and discovery of tasks.

```python
registry = TaskRegistry()
registry.register("refactor", RefactorTask)
task_cls = registry.get("refactor")
names = registry.all()
```

### Methods

| Method | Description |
|--------|-------------|
| `register(name, task_class)` | Register a task class by name |
| `get(name)` | Lookup a task class by name |
| `has(name)` | Check if a task is registered |
| `all()` | List all registered task names (sorted) |
| `unregister(name)` | Remove a task from the registry |

### Constraints

- Prevents duplicate registration.
- Deterministic ordering via sorted output.
- Raises `ValueError` on duplicate registration.
- Raises `KeyError` on unregister of non-existent task.

## TaskFactory

Creates task instances through the registry.

```python
factory = TaskFactory(registry)
task = factory.create("refactor")
```

### Methods

| Method | Description |
|--------|-------------|
| `create(name)` | Create a task instance by name |

### Constraints

- Delegates all lookup to the registry.
- Never hardcodes task classes.
- Raises `ValueError` for unregistered names.
- Error message includes available tasks.

## Example: RefactorTask

```python
from packages.tasks.base import Task
from packages.tasks.models import TaskPlan, TaskRequest, TaskStep

class RefactorTask(Task):

    @property
    def name(self) -> str:
        return "refactor"

    @property
    def capability(self) -> str:
        return "refactor"

    def _do_plan(
        self,
        repository_index,
        request: TaskRequest,
    ) -> TaskPlan:
        return TaskPlan(
            task_name="refactor",
            capability="refactor",
            context_package=...,
            steps=(
                TaskStep(
                    order=0,
                    title="Analyze repository",
                    description="Examine the repository structure",
                ),
                TaskStep(
                    order=1,
                    title="Identify targets",
                    description="Identify symbols and modules to refactor",
                ),
                TaskStep(
                    order=2,
                    title="Generate plan",
                    description="Generate refactoring execution plan",
                ),
            ),
        )
```

## Future Tasks

Future tasks must require only:

- One class
- One registration

No framework modifications.

| Task | Description |
|------|-------------|
| Rename Symbol | Rename a symbol across the codebase |
| Move Class | Move a class to a new module |
| Extract Interface | Extract an interface from a class |
| Generate Tests | Generate test cases for a module |
| Review PR | Review a pull request |
| Implement Feature | Implement a new feature |
| Migrate API | Migrate between API versions |

## Files

```
packages/tasks/
    __init__.py      # Package exports
    base.py          # Task ABC
    models.py        # Immutable dataclasses
    registry.py      # TaskRegistry
    factory.py       # TaskFactory

tests/tasks/
    __init__.py
    test_base.py     # Task ABC tests
    test_models.py   # Model tests
    test_registry.py # Registry tests
    test_factory.py  # Factory tests

docs/
    tasks.md         # This file