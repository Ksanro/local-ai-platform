# Platform Validation Framework

## Overview

The Platform Validation Framework performs a complete integrity validation of the assembled engineering platform. It is executed after Platform Bootstrap and before the Engineering Controller accepts requests.

**Constraints:**
- NEVER performs engineering work
- NEVER invokes providers
- NEVER analyzes repositories
- ONLY validates platform consistency

## Architecture

```
PlatformBootstrap
        │
        ▼
PlatformValidator
        │
        ├── Dependency Validation
        ├── Registry Validation
        ├── Provider Validation
        ├── Workflow Validation
        ├── Task Validation
        ├── Capability Validation
        ├── Configuration Validation
        ├── Public API Validation
        └── Health Report

PlatformValidator
        │
        ▼
PlatformHealthChecker
        │
        ├── health() — compute health status
        ├── summary() — one-line summary
        └── details() — multi-line details
```

## Components

### Models (`packages/platform/models.py`)

Immutable dataclasses for health reporting:

| Model | Description |
|-------|-------------|
| `Severity` | Severity constants: `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `ValidationIssue` | Single finding with identifier, component, severity, description, recommendation |
| `ValidationStatistics` | Numeric summary: total_checks, issues_count, errors_count, warnings_count, critical_count |
| `ValidationReport` | Complete validation result with issues and statistics |
| `PlatformHealth` | Health snapshot with status (HEALTHY, UNHEALTHY, DEGRADED) |
| `HealthReport` | Human-readable health summary with details |

All models use `frozen=True, slots=True` for immutability.

### Validator (`packages/platform/validator.py`)

`PlatformValidator` performs complete integrity validation:

```python
from packages.platform.validator import PlatformValidator

validator = PlatformValidator()
report = validator.validate(registries, configuration, container)
```

**Validation Rules:**

| Rule | Severity | Description |
|------|----------|-------------|
| Bootstrap | CRITICAL | Registries object exists |
| Bootstrap | ERROR | Required registry attributes present |
| Dependency Graph | CRITICAL | Container is not None |
| Dependency Graph | ERROR | Container has registrations |
| Dependency Graph | ERROR | No missing dependencies |
| Registries | CRITICAL | All required registries present |
| Registries | WARNING | Registry is not set |
| Providers | ERROR | Required providers registered |
| Workflows | ERROR | Required workflows registered |
| Tasks | WARNING | Task registry is not empty |
| Capabilities | WARNING | Capability registry is not empty |
| Configuration | CRITICAL | Configuration is not None |
| Configuration | ERROR | Configuration values are positive |
| Public API | WARNING | Registry has required methods |
| Duplicates | ERROR | No duplicate registrations |
| Cycles | CRITICAL | No circular dependencies |

### Health Checker (`packages/platform/health.py`)

`PlatformHealthChecker` computes deterministic health status:

```python
from packages.platform.health import PlatformHealthChecker

checker = PlatformHealthChecker()
health = checker.health(report)
print(checker.summary(health))
```

**Health Status Rules:**

| Condition | Status |
|-----------|--------|
| No issues | HEALTHY |
| Only WARNING issues | DEGRADED |
| Any ERROR or CRITICAL | UNHEALTHY |

### Diagnostics (`packages/platform/diagnostics.py`)

`DiagnosticsEngine` produces structured diagnostic issues:

```python
from packages.platform.diagnostics import DiagnosticsEngine

diag = DiagnosticsEngine()
issue = diag.create_issue(
    identifier="DIAG-001",
    component="workflow_registry",
    severity=Severity.ERROR,
    description="Workflow registry is missing.",
    recommendation="Ensure the bootstrap creates the workflow registry.",
)
```

## Public API

```python
from packages.platform.validator import PlatformValidator
from packages.platform.health import PlatformHealthChecker
from packages.platform.models import (
    ValidationIssue,
    PlatformHealth,
    ValidationReport,
    HealthReport,
    Severity,
)

# Validate platform
validator = PlatformValidator()
report = validator.validate(registries, configuration, container)

# Check health
checker = PlatformHealthChecker()
health = checker.health(report)

if health.status == PlatformHealth.HEALTHY:
    print("Platform is healthy")
```

## Validation Lifecycle

```
1. PlatformBootstrap.build()
        │
        ▼
2. PlatformValidator.validate()
        │
        ├── Bootstrap validation
        ├── Dependency graph validation
        ├── Registry validation
        ├── Provider validation
        ├── Workflow validation
        ├── Task validation
        ├── Capability validation
        ├── Configuration validation
        ├── Public API validation
        ├── Duplicate detection
        └── Cycle detection
        │
        ▼
3. PlatformHealthChecker.health()
        │
        ▼
4. Engineering Controller accepts requests (if HEALTHY)
```

## Startup Validation

The Platform Validation Framework is executed as a gate before the Engineering Controller accepts requests:

```python
from packages.platform.validator import PlatformValidator
from packages.platform.health import PlatformHealthChecker

validator = PlatformValidator()
checker = PlatformHealthChecker()

report = validator.validate(registries, configuration, container)
health = checker.health(report)

if health.status != PlatformHealth.HEALTHY:
    raise RuntimeError(f"Platform validation failed: {checker.summary(health)}")

# Platform is healthy — controller can accept requests
controller.accept_requests()
```

## Extension Process

### Adding New Validation Rules

1. Add a new `_validate_*` method to `PlatformValidator`
2. Call it from `validate()` in the appropriate order
3. Add corresponding tests in `tests/platform/test_validator.py`

Example:

```python
def _validate_new_feature(self, registries: object) -> list[ValidationIssue]:
    """Validate new feature configuration."""
    issues: list[ValidationIssue] = []
    diag = self._diagnostics

    if registries is not None:
        feature_reg = getattr(registries, "feature_registry", None)
        if feature_reg is None:
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("FEAT"),
                component="feature_registry",
                severity=Severity.WARNING,
                description="Feature registry is not set.",
                recommendation="Ensure the bootstrap initializes feature_registry.",
            ))

    return issues
```

### Adding New Health Statuses

1. Add new constant to `PlatformHealth` class
2. Update `_compute_status()` in `PlatformHealthChecker`
3. Update `summary()` and `details()` methods

### Custom Required Providers/Workflows

```python
validator = PlatformValidator(
    required_providers=("vllm", "openai", "anthropic"),
    required_workflows=("default-engineering", "code-review"),
)
```

## Distributed Deployments

For distributed deployments, the validation framework can be extended to:

- Validate node connectivity
- Check registry synchronization across nodes
- Verify provider availability on remote endpoints
- Validate load balancer configuration

These extensions should be added as separate validation rules in `PlatformValidator`.

## Remote Providers

For remote provider validation:

- Add `_validate_remote_providers()` method
- Check provider endpoint reachability
- Verify authentication credentials
- Validate rate limiting configuration

## Test Coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| `test_models.py` | 25+ | Model immutability, equality, statistics |
| `test_validator.py` | 40+ | All validation rules, edge cases |
| `test_health.py` | 25+ | Health status computation, summaries |
| `test_diagnostics.py` | 15+ | Issue creation, identifier generation |

**Target:** >95% code coverage

## Architecture Review

### Design Principles

1. **Immutability** — All models use frozen dataclasses
2. **Determinism** — Same inputs always produce same outputs
3. **Separation of Concerns** — Validator, Health, Diagnostics are separate
4. **No Side Effects** — The framework NEVER performs engineering work
5. **Explicit APIs** — All public APIs are documented with examples

### Compliance

| Requirement | Status |
|-------------|--------|
| Uses immutable dataclasses | ✅ |
| slots=True | ✅ |
| Strict typing | ✅ |
| Deterministic behaviour | ✅ |
| Explicit __all__ | ✅ |
| Consumes only public APIs | ✅ |
| No singleton | ✅ |
| No global mutable state | ✅ |
| Production-quality | ✅ |

## Files Created

| File | Purpose |
|------|---------|
| `packages/platform/__init__.py` | Public API exports |
| `packages/platform/models.py` | Model dataclasses |
| `packages/platform/validator.py` | PlatformValidator |
| `packages/platform/health.py` | PlatformHealthChecker |
| `packages/platform/diagnostics.py` | DiagnosticsEngine |
| `tests/platform/__init__.py` | Test package init |
| `tests/platform/test_models.py` | Model tests |
| `tests/platform/test_validator.py` | Validator tests |
| `tests/platform/test_health.py` | Health checker tests |
| `tests/platform/test_diagnostics.py` | Diagnostics tests |
| `docs/platform-validation.md` | This documentation |

## Platform Validation Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Platform Bootstrap                         │
│  - Creates registries                                        │
│  - Registers providers/workflows/tasks                       │
│  - Initializes dependency container                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  PlatformValidator.validate()                 │
│                                                              │
│  1. Bootstrap validation                                     │
│  2. Dependency graph validation                              │
│  3. Registry integrity validation                            │
│  4. Provider registration validation                         │
│  5. Workflow registration validation                         │
│  6. Task registration validation                             │
│  7. Capability registration validation                       │
│  8. Configuration validation                                 │
│  9. Public API validation                                    │
│ 10. Duplicate registration detection                         │
│ 11. Dependency cycle detection                               │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              PlatformHealthChecker.health()                   │
│                                                              │
│  - No issues → HEALTHY                                       │
│  - Only WARNING → DEGRADED                                   │
│  - ERROR/CRITICAL → UNHEALTHY                                │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Engineering Controller                           │
│                                                              │
│  - If HEALTHY: Accept requests                               │
│  - If DEGRADED: Accept with monitoring                       │
│  - If UNHEALTHY: Reject requests                             │
└──────────────────────────────────────────────────────────────┘
```

## Future Extension Points

1. **Plugin Validation** — Validate custom plugin registrations
2. **Distributed Validation** — Validate multi-node deployments
3. **Remote Provider Validation** — Validate remote provider endpoints
4. **Performance Validation** — Validate platform performance thresholds
5. **Security Validation** — Validate security configurations
6. **Compliance Validation** — Validate regulatory compliance requirements