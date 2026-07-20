# Self Verification Framework

## Architecture

The Self Verification Framework validates the result of engineering execution. It determines whether an engineering execution produced the expected outcome and generates a deterministic `VerificationReport`.

```
WorkflowPlan      -->  \
ExecutionPlan     -->  \
EvaluationReport  -->  SelfVerificationEngine  -->  VerificationReport
PatchSet          -->  /
WorkspaceChanges  -->  /
```

## Verification Lifecycle

```
1. Engineering Execution
   └── WorkflowPlan
   └── ExecutionPlan
   └── EvaluationReport
   └── PatchSet
   └── WorkspaceChanges
        │
        ▼
2. Self Verification
   ├── Rule Execution (registered rules)
   ├── Finding Aggregation
   ├── Score Calculation
   ├── Status Calculation
   └── VerificationReport Output
        │
        ▼
3. Quality Gate
   └── VerificationReport consumed by downstream components
```

## Rule Framework

### VerificationRule (Abstract Base Class)

All verification rules inherit from `VerificationRule`:

```python
from packages.verification.rules import VerificationRule

class MyRule(VerificationRule):
    @property
    def severity(self) -> VerificationSeverity:
        return VerificationSeverity.MEDIUM

    def verify(self, workspace_changes: Any) -> VerificationFinding | None:
        # Return Finding if issues found, None otherwise
        ...
```

### Built-in Rules

| Rule | Category | Severity | Description |
|------|----------|----------|-------------|
| `PatchAppliedRule` | patch-applied | MEDIUM | Verifies all patches were applied successfully |
| `NoUnexpectedFilesRule` | unexpected-files | LOW | Detects unexpected files in workspace |
| `NoDuplicateChangesRule` | duplicate-changes | MEDIUM | Ensures no duplicate changes exist |
| `WorkspaceConsistencyRule` | workspace-consistency | MEDIUM | Validates workspace statistics consistency |
| `PatchStatisticsConsistencyRule` | patch-statistics | MEDIUM | Validates patch statistics integrity |

### Rule Execution Order

Rules execute in **deterministic sorted order** by `rule_id`. This ensures that the same inputs always produce the same output.

## Scoring

### Weighted Severity Penalty

The verification score is calculated using deterministic weighted severity penalties:

| Severity | Weight (Penalty) |
|----------|------------------|
| INFO | 0.00 (no penalty) |
| LOW | 0.05 |
| MEDIUM | 0.15 |
| HIGH | 0.30 |
| CRITICAL | 0.50 |

**Formula:**

```
score = max(0.0, 1.0 - sum(severity_weight for finding in findings))
```

**Clamped to range [0.0, 1.0].**

### Status Calculation

| Condition | Status |
|-----------|--------|
| No rules executed | SKIPPED |
| Any CRITICAL findings | FAILED |
| Any HIGH severity findings | FAILED |
| Any MEDIUM severity findings | WARNING |
| All INFO or no findings | PASSED |

## Responsibilities

### What It Does

- Execute registered verification rules against workspace changes
- Aggregate findings from all rules
- Calculate deterministic verification score
- Calculate verification status from findings
- Produce immutable `VerificationReport`
- Validate `VerificationReport` integrity

### What It Does NOT Do

- **Must NOT** edit files
- **Must NOT** generate patches
- **Must NOT** invoke providers
- **Must NOT** inspect repositories
- **Must NOT** execute shell commands
- **Must NOT** duplicate evaluation logic
- **Must NOT** modify any input artifacts

## VerificationReport Contract

```python
@dataclass(frozen=True, slots=True)
class VerificationReport:
    workflow_name: str
    execution_id: str
    verification_status: VerificationStatus
    findings: tuple[VerificationFinding, ...] = ()
    statistics: VerificationStatistics = field(default_factory=VerificationStatistics)
    score: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | `str` | Name of the verified workflow |
| `execution_id` | `str` | Unique execution identifier |
| `verification_status` | `VerificationStatus` | PASSED, FAILED, WARNING, or SKIPPED |
| `findings` | `tuple[VerificationFinding, ...]` | All verification findings in deterministic order |
| `statistics` | `VerificationStatistics` | Verification run statistics |
| `score` | `float` | Deterministic verification score (0.0 to 1.0) |
| `metadata` | `dict[str, object]` | Additional metadata about the verification |

### VerificationFinding Contract

```python
@dataclass(frozen=True, slots=True)
class VerificationFinding:
    id: str
    category: str
    severity: VerificationSeverity
    title: str
    description: str
    evidence: str
    recommendation: str | None = None
```

### VerificationStatistics Contract

```python
@dataclass(frozen=True, slots=True)
class VerificationStatistics:
    executed_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    warnings: int = 0
    duration_ms: int = 0
```

## Public API

### Engine

```python
from packages.verification.engine import SelfVerificationEngine

report = SelfVerificationEngine.verify(
    workflow_plan=workflow_plan,
    execution_plan=execution_plan,
    evaluation_report=evaluation_report,
    patch_set=patch_set,
    workspace_changes=workspace_changes,
)
```

### Registry

```python
from packages.verification.registry import VerificationRuleRegistry

registry = VerificationRuleRegistry()
registry.register(rule)
rules = registry.sorted_rules()
```

### Validator

```python
from packages.verification.validator import VerificationReportValidator

is_valid, errors = VerificationReportValidator.validate(report)
```

### Models

```python
from packages.verification.models import (
    VerificationFinding,
    VerificationReport,
    VerificationSeverity,
    VerificationStatus,
    VerificationStatistics,
)
```

## Integration with Autonomous Multi-step Engineering

The `VerificationReport` becomes the quality gate before any future Autonomous Engineering execution continues:

```
1. Engineering Execution completes
2. Self Verification produces VerificationReport
3. Quality Gate Check:
   - If PASSED: Continue to next phase
   - If WARNING: Log warnings, continue with caution
   - If FAILED: Block further execution, trigger review
   - If SKIPPED: Log skip reason, continue
4. VerificationReport is consumed by downstream components
```

## Architecture

```
packages/verification/
    __init__.py          # Package exports, architecture documentation
    models.py            # Immutable dataclass definitions
    rules.py             # VerificationRule ABC + built-in rules
    registry.py          # VerificationRuleRegistry
    validator.py         # VerificationReportValidator
    engine.py            # SelfVerificationEngine

tests/verification/
    __init__.py          # Test package marker
    test_models.py       # Model immutability, construction, edge cases
    test_rules.py        # Rule execution, deterministic ordering
    test_registry.py     # Registration, lookup, sorted order
    test_validator.py    # Report validation, duplicate detection
    test_engine.py       # Full engine flow, scoring, statistics
```

## Design Principles

1. **Immutability**: All models use `@dataclass(frozen=True, slots=True)`
2. **Determinism**: Same inputs always produce identical outputs
3. **No Side Effects**: Rules never modify inputs or the environment
4. **Public API Only**: Consume only public APIs from other packages
5. **Explicit Boundaries**: Non-responsibilities are explicitly documented
6. **Comprehensive Tests**: >95% coverage with edge case testing