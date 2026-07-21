# Autonomous Engineering Framework

## Architecture Overview

The Autonomous Engineering Framework is the orchestration layer of the platform. It sits **above** the Workflow Engine and repeatedly invokes existing workflows until an engineering objective is achieved or a deterministic stopping condition is reached.

```
EngineeringGoal
       │
       ▼
AutonomousEngine
       │
       ├── Workflow Engine
       ├── Execution Engine
       ├── Evaluation Framework
       ├── Patch Generator
       ├── Code Modification Engine
       ├── Self Verification
       └── Decision Loop
```

**This is NOT another Workflow Engine.**

It coordinates existing frameworks through their public APIs only. It never performs engineering work itself.

## Architecture

```
EngineeringGoal
       │
       ▼
AutonomousEngine
       │
       ├── Workflow Engine
       ├── Execution Engine
       ├── Evaluation Framework
       ├── Patch Generator
       ├── Code Modification Engine
       ├── Self Verification
       └── Decision Loop
       │
       ▼
FinalEngineeringReport
```

## Orchestration Lifecycle

The AutonomousEngine coordinates the entire engineering lifecycle:

1. **Goal Reception** — An `EngineeringGoal` is received with:
   - `id`: Unique identifier
   - `objective`: Description of the engineering task
   - `constraints`: Tuple of constraints to respect
   - `success_criteria`: Tuple of success criteria
   - `max_iterations`: Maximum number of iterations allowed
   - `metadata`: Additional metadata

2. **State Creation** — Initial `AutonomousState` is created with iteration 0 and empty history.

3. **Workflow Planning** — The `EngineeringPlanner` produces a sequence of workflow classes to execute.

4. **Execution Loop** — The engine enters a deterministic loop:
   - Check stopping conditions
   - Evaluate policy decisions
   - Execute the next workflow iteration
   - Record the iteration result
   - Update autonomous state

5. **Report Generation** — A `FinalEngineeringReport` is produced with:
   - The original goal
   - Final status
   - All completed iterations
   - Statistics
   - Final summary
   - Recommendations

## Execution Loop

```python
while not should_stop:
    # Check stopping conditions
    should_stop, reasons = check_all_stopping_conditions(state, last_iteration)
    if should_stop:
        break

    # Evaluate policies
    for policy in policies:
        result = policy.evaluate(state, last_iteration)
        if result.decision == STOP:
            break
        if result.decision == SKIP:
            break

    # Execute workflow
    workflow_class = workflow_sequence[current_iteration % len(workflow_sequence)]
    iteration = execute_workflow_iteration(goal, workflow_class, state)

    # Update state
    if iteration.failed:
        record_failure(state, iteration)
    else:
        advance_iteration(state, iteration)
```

## Policies

Policies are stateless deterministic decision makers that govern how the engine iterates through workflows.

### Built-in Policies

| Policy | Behavior |
|--------|----------|
| `SequentialPolicy` | Always allows execution to continue |
| `StopOnFailurePolicy` | Stops when the last iteration failed |
| `VerificationGatePolicy` | Requires verification status to indicate success |
| `MaximumIterationPolicy` | Stops when max iterations reached |

### Policy Interface

```python
class Policy(ABC):
    @property
    def policy_id(self) -> str:
        ...

    @abstractmethod
    def evaluate(
        self,
        state: AutonomousState,
        last_iteration: Any | None = None,
    ) -> PolicyResult:
        ...
```

### PolicyResult

```python
@dataclass(frozen=True, slots=True)
class PolicyResult:
    decision: PolicyDecision  # CONTINUE, STOP, or SKIP
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

### PolicyDecision

```python
class PolicyDecision(str):
    CONTINUE = "CONTINUE"  # Continue execution normally
    STOP = "STOP"          # Stop execution immediately
    SKIP = "SKIP"          # Skip the current iteration
```

## Stopping Conditions

Stopping conditions prevent infinite loops and ensure deterministic termination:

| Condition | Description |
|-----------|-------------|
| `check_goal_achieved` | Any iteration has evaluation score >= 0.8 |
| `check_verification_successful` | Last iteration has verification status PASSED/COMPLETED/SUCCESS |
| `check_max_iterations_reached` | Current iteration count >= max_iterations |
| `check_repeated_failure` | Last N iterations (default 3) all failed |
| `check_policy_request_stop` | Policy metadata contains `policy_stop: True` |

### Combined Check

```python
should_stop, reasons = check_all_stopping_conditions(state, last_iteration)
```

Returns `(True, tuple_of_reasons)` if any condition is met, otherwise `(False, ())`.

## Engineering State

### AutonomousState

```python
@dataclass(frozen=True, slots=True)
class AutonomousState:
    current_iteration: int
    completed_workflows: tuple[str, ...]
    completed_iterations: tuple[AutonomousIteration, ...]
    current_goal: EngineeringGoal
    metadata: dict[str, Any]
```

### AutonomousIteration

```python
@dataclass(frozen=True, slots=True)
class AutonomousIteration:
    iteration: int
    workflow_name: str
    evaluation_score: float
    verification_status: str
    duration_ms: int
    result_summary: str
    status: IterationStatus = IterationStatus.COMPLETED
    metadata: dict[str, Any] = field(default_factory=dict)
```

### AutonomousStatistics

```python
@dataclass(frozen=True, slots=True)
class AutonomousStatistics:
    total_iterations: int
    successful_iterations: int
    failed_iterations: int
    workflows_executed: int
    total_duration_ms: int
    average_evaluation_score: float
```

## FinalEngineeringReport

```python
@dataclass(frozen=True, slots=True)
class FinalEngineeringReport:
    goal: EngineeringGoal
    status: str  # "COMPLETED", "PARTIAL", "FAILED", "EMPTY"
    iterations: tuple[AutonomousIteration, ...]
    statistics: AutonomousStatistics
    final_summary: str
    recommendations: tuple[str, ...]
```

## Responsibilities

### AutonomousEngine MUST

- [x] Invoke Workflow Engine
- [x] Invoke Execution Engine
- [x] Invoke Evaluation Framework
- [x] Invoke Patch Generator
- [x] Invoke Code Modification Engine
- [x] Invoke Self Verification
- [x] Evaluate policies
- [x] Update autonomous state
- [x] Determine next workflow
- [x] Stop deterministically
- [x] Produce FinalEngineeringReport

### AutonomousEngine MUST NOT

- [ ] Inspect repositories directly
- [ ] Edit code directly
- [ ] Call providers directly
- [ ] Duplicate existing framework logic
- [ ] Bypass public APIs

## Architectural Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                   AutonomousEngine                       │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Planner     │  │  Policies    │  │  Stopping    │  │
│  │              │  │              │  │  Conditions  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Execution Loop                       │   │
│  │                                                  │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐ │   │
│  │  │ Workflow   │  │ Execution  │  │ Evaluation │ │   │
│  │  │ Engine     │→ │ Engine     │→ │ Framework  │ │   │
│  └──────────────┘  └────────────┘  └────────────┘ │   │
│       │                                                  │   │
│       ▼                                                  │   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │ Patch        │  │ Code         │  │ Self         │ │   │
│  │ Generator    │→ │ Modification │→ │ Verification │ │   │
│  │              │  │ Engine       │  │              │ │   │
│  └──────────────┘  └──────────────┘  └──────────────┘ │   │
│                                                          │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              FinalEngineeringReport                      │
└─────────────────────────────────────────────────────────┘
```

## Public API

```python
from packages.autonomous import (
    AutonomousEngine,
    EngineeringGoal,
    AutonomousIteration,
    AutonomousState,
    FinalEngineeringReport,
    IterationStatus,
)
from packages.autonomous.policy import (
    SequentialPolicy,
    StopOnFailurePolicy,
    VerificationGatePolicy,
    MaximumIterationPolicy,
    PolicyDecision,
    PolicyResult,
)
from packages.autonomous.registry import AutonomousPolicyRegistry
from packages.autonomous.stopping import (
    check_all_stopping_conditions,
    check_goal_achieved,
    check_verification_successful,
    check_max_iterations_reached,
    check_repeated_failure,
)
from packages.autonomous.state import AutonomousStateManager
from packages.autonomous.planner import EngineeringPlanner
```

## Usage

```python
from packages.autonomous import AutonomousEngine, EngineeringGoal

# Define the engineering goal
goal = EngineeringGoal(
    id="goal-001",
    objective="Implement feature X",
    constraints=("no-breaking-changes",),
    success_criteria=("tests-pass", "docs-updated"),
    max_iterations=10,
)

# Create the engine
engine = AutonomousEngine()

# Execute the autonomous engineering lifecycle
report = engine.execute(goal)

# Access results
print(f"Status: {report.status}")
print(f"Iterations: {report.statistics.total_iterations}")
print(f"Summary: {report.final_summary}")
for rec in report.recommendations:
    print(f"  - {rec}")
```

## Custom Policies

```python
from packages.autonomous.policy import Policy, PolicyResult, PolicyDecision

class CustomPolicy(Policy):
    def evaluate(self, state, last_iteration=None) -> PolicyResult:
        # Custom logic here
        if some_condition:
            return PolicyResult(
                decision=PolicyDecision.STOP,
                reason="Custom condition met.",
            )
        return PolicyResult(
            decision=PolicyDecision.CONTINUE,
            reason="Continue execution.",
        )
```

## Custom Planner

```python
from packages.autonomous.planner import EngineeringPlanner

class CustomPlanner(EngineeringPlanner):
    def plan(self, goal, available_workflows=None):
        # Custom workflow planning logic
        return (CustomWorkflow1, CustomWorkflow2)
```

## Registry

```python
from packages.autonomous.registry import AutonomousPolicyRegistry

registry = AutonomousPolicyRegistry()
registry.register(SequentialPolicy())
registry.register(StopOnFailurePolicy())

# Get sorted policies
policies = registry.sorted_policies()

# Get specific policy
policy = registry.get("SequentialPolicy")
```

## Constraints

1. **No global mutable state** — All state is internal to objects.
2. **No singleton pattern** — All components are instantiated explicitly.
3. **Immutable dataclasses** — All models use `frozen=True, slots=True`.
4. **Deterministic behavior** — Same inputs always produce same outputs.
5. **Public API only** — All interactions use public APIs of other frameworks.
6. **No infinite loops** — Stopping conditions guarantee termination.

## Extension Points

The framework is designed for extension:

1. **Custom Policies** — Add new policies by subclassing `Policy`.
2. **Custom Planner** — Add new planning strategies by subclassing `EngineeringPlanner`.
3. **Custom Adapters** — Provide custom workflow/execution/evaluation adapters.
4. **Custom Stopping Conditions** — Add new conditions by extending `check_all_stopping_conditions`.
5. **Custom Reports** — Extend `FinalEngineeringReport` with additional fields.

## Files

| File | Purpose |
|------|---------|
| `packages/autonomous/__init__.py` | Package initialization and exports |
| `packages/autonomous/models.py` | Immutable dataclass models |
| `packages/autonomous/planner.py` | Engineering planner |
| `packages/autonomous/policy.py` | Policy implementations |
| `packages/autonomous/registry.py` | Policy registry |
| `packages/autonomous/state.py` | State management |
| `packages/autonomous/stopping.py` | Stopping conditions |
| `packages/autonomous/engine.py` | Main engine implementation |
| `tests/autonomous/test_models.py` | Model tests |
| `tests/autonomous/test_engine.py` | Engine tests |
| `tests/autonomous/test_policy.py` | Policy tests |
| `tests/autonomous/test_registry.py` | Registry tests |
| `tests/autonomous/test_stopping.py` | Stopping condition tests |
| `tests/autonomous/test_state.py` | State management tests |