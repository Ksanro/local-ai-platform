# Bootstrap Framework

## Overview

The Bootstrap Framework is the central assembly point for the entire engineering platform. It constructs all registries, factories, engines, and components, then validates and returns a ready-to-use `EngineeringController`.

## Architecture

```
PlatformBootstrap
    │
    ├── build(configuration) -> EngineeringController
    │
    ├── Steps:
    │   1. Construct all registries
    │   2. Construct all factories
    │   3. Construct all engines
    │   4. Register providers
    │   5. Register workflows
    │   6. Register capabilities
    │   7. Register tasks
    │   8. Validate platform
    │   9. Return ready-to-use EngineeringController
    │
    ▼
EngineeringController
```

The Bootstrap Framework is the **ONLY** component allowed to wire together implementations. Every other component receives dependencies through constructors. No component may instantiate another subsystem directly.

## Public API

### PlatformBootstrap

```python
from packages.bootstrap import PlatformBootstrap, build
from packages.bootstrap.configuration import PlatformConfiguration

# Using the class
bootstrap = PlatformBootstrap()
config = PlatformConfiguration.default()
controller = bootstrap.build(config)

# Using the convenience function
controller = build()
```

### PlatformConfiguration

```python
from packages.bootstrap.configuration import PlatformConfiguration

# Default configuration
config = PlatformConfiguration.default()

# Custom configuration
config = PlatformConfiguration(
    repository=RepositoryConfig(max_symbols=50),
    observability=ObservabilityConfig(enabled=True),
)

# Override specific sub-configurations
config = config.with_providers(default_provider="openai")
config = config.with_repository(max_symbols=50)
config = config.with_observability(enabled=True)
```

## Bootstrap Lifecycle

### 1. Configuration

Configuration is created first. All configuration is immutable (frozen dataclasses).

```python
config = PlatformConfiguration.default()
```

### 2. Registry Construction

All platform registries are constructed:

```python
registries = bootstrap._construct_registries(config)
```

Registries include:
- `WorkflowRegistry` - workflow classes
- `ProviderRegistry` - AI provider implementations
- `SessionRegistry` - engineering session tracking
- `EventRegistry` - observability events
- `SerializerRegistry` - data serialization
- `VerificationRuleRegistry` - verification rules
- `MetricRegistry` - evaluation metrics

### 3. Factory Construction

All platform factories are constructed:

```python
factories = bootstrap._construct_factories(registries, config)
```

Factories include:
- `create_provider` - AI provider creation
- `SerializerFactory` - data serialization

### 4. Engine Construction

All platform engines are constructed:

```python
engines = bootstrap._construct_engines(factories, registries, config)
```

Engines include:
- `SessionManager` - session lifecycle management
- `EngineeringTelemetry` - observability and metrics

### 5. Component Registration

Providers and workflows are registered:

```python
bootstrap._register_components(factories, engines, registries, config)
```

### 6. Platform Validation

The platform is validated for correctness:

```python
result = bootstrap._validate_platform(registries, config)
```

Validation checks:
- Required registries exist
- Configuration values are valid
- No duplicate registrations
- No dependency cycles
- No missing providers

### 7. Controller Construction

The `EngineeringController` is constructed with all dependencies:

```python
controller = bootstrap._construct_controller(engistries, config)
```

## Dependency Graph

```
PlatformBootstrap
    │
    ├── PlatformRegistries
    │   ├── WorkflowRegistry
    │   ├── ProviderRegistry
    │   ├── SessionRegistry
    │   ├── EventRegistry
    │   ├── SerializerRegistry
    │   ├── VerificationRuleRegistry
    │   └── MetricRegistry
    │
    ├── Factories
    │   ├── create_provider
    │   └── SerializerFactory
    │
    ├── Engines
    │   ├── SessionManager
    │   └── EngineeringTelemetry
    │
    └── EngineeringController
```

## Registration Process

### Provider Registration

Providers are registered through the `ProviderRegistry`. The bootstrap framework triggers auto-registration of all available providers.

```python
from packages.providers import _load_providers
from packages.providers.registry import ProviderRegistry

_load_providers()  # Auto-registers all providers
```

### Workflow Registration

Default workflows are registered through the `WorkflowRegistry`:

```python
registry.register("default-engineering", DefaultEngineeringWorkflow)
registry.register("code-review", CodeReviewWorkflow)
registry.register("implement-feature", ImplementFeatureWorkflow)
```

## Configuration Model

### PlatformConfiguration

The top-level configuration class. All configuration is immutable.

| Field | Type | Default |
|-------|------|---------|
| `providers` | `ProviderConfig` | Default provider config |
| `repository` | `RepositoryConfig` | Default repository config |
| `pipeline` | `PipelineConfig` | Default pipeline config |
| `workflow` | `WorkflowConfig` | Default workflow config |
| `execution` | `ExecutionConfig` | Default execution config |
| `evaluation` | `EvaluationConfig` | Default evaluation config |
| `verification` | `VerificationConfig` | Default verification config |
| `observability` | `ObservabilityConfig` | Default observability config |
| `session` | `SessionConfig` | Default session config |
| `autonomous` | `AutonomousConfig` | Default autonomous config |
| `controller` | `ControllerConfig` | Default controller config |

### Sub-Configurations

#### ProviderConfig

| Field | Type | Default |
|-------|------|---------|
| `default_provider` | `str` | `"vllm"` |
| `request_timeout_seconds` | `float` | `60.0` |
| `max_retries` | `int` | `3` |
| `api_keys` | `dict[str, str]` | `{}` |

#### RepositoryConfig

| Field | Type | Default |
|-------|------|---------|
| `max_symbols` | `int` | `20` |
| `max_modules` | `int` | `10` |
| `max_tokens` | `int` | `4096` |
| `context_enabled` | `bool` | `True` |

#### WorkflowConfig

| Field | Type | Default |
|-------|------|---------|
| `default_workflow` | `str` | `"default-engineering"` |
| `max_steps` | `int` | `50` |
| `enable_autonomous_loop` | `bool` | `False` |

#### ExecutionConfig

| Field | Type | Default |
|-------|------|---------|
| `max_concurrent_steps` | `int` | `1` |
| `step_timeout_seconds` | `float` | `300.0` |
| `enable_parallel_execution` | `bool` | `False` |

#### ObservabilityConfig

| Field | Type | Default |
|-------|------|---------|
| `enabled` | `bool` | `False` |
| `max_events` | `int` | `10000` |
| `max_metrics` | `int` | `5000` |
| `max_traces` | `int` | `1000` |

#### SessionConfig

| Field | Type | Default |
|-------|------|---------|
| `enabled` | `bool` | `True` |
| `max_sessions` | `int` | `100` |
| `auto_close_timeout_seconds` | `float` | `3600.0` |

#### AutonomousConfig

| Field | Type | Default |
|-------|------|---------|
| `enabled` | `bool` | `False` |
| `max_iterations` | `int` | `5` |
| `stopping_policy` | `str` | `"convergence"` |
| `retry_on_failure` | `bool` | `True` |

## Extension Process

### Adding Custom Providers

Providers are auto-registered through the provider registry. To add a custom provider:

```python
from packages.providers.registry import ProviderRegistry
from packages.providers.base import BaseProvider

class MyCustomProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "my-custom-provider"

    def _do_complete(self, request: object) -> object:
        # Implementation
        pass

# Auto-registration happens through _load_providers()
```

### Adding Custom Workflows

Custom workflows are registered through the `WorkflowRegistry`:

```python
from packages.workflows.base import Workflow

class MyCustomWorkflow(Workflow):
    @property
    def name(self) -> str:
        return "my-custom-workflow"

    @property
    def workflow_nodes(self) -> tuple[object, ...]:
        return ()

    def _do_plan(self, repository_index: object, request: object) -> object:
        # Implementation
        pass

    def _do_estimate(self, repository_index: object, request: object) -> object:
        # Implementation
        pass

# Registration happens through _register_workflows()
```

### Customizing Configuration

```python
from packages.bootstrap.configuration import PlatformConfiguration

# Start with defaults
config = PlatformConfiguration.default()

# Override specific sub-configurations
config = (
    config
    .with_providers(default_provider="openai", max_retries=5)
    .with_repository(max_symbols=50, max_tokens=8192)
    .with_observability(enabled=True, max_events=50000)
)
```

## Dependency Container

The `DependencyContainer` is a lightweight deterministic dependency injection container used by the bootstrap framework.

### Public API

```python
from packages.bootstrap.container import DependencyContainer

container = DependencyContainer()

# Register a dependency
container.register("name", factory_func, dependencies=("dep1", "dep2"))

# Resolve a dependency
result = container.resolve("name")

# Check if a dependency is registered
has_it = container.contains("name")

# Get all registered dependencies
all_deps = container.all()

# Validate dependencies
errors = container.validate()
```

### Constraints

- Constructor injection only
- No reflection
- No runtime discovery
- No magic
- No singleton
- No service locator
- No hidden globals

## Validation

The bootstrap framework validates the platform at build time:

### Container Validation

- Checks for empty container
- Validates all dependencies are registered
- Detects missing dependencies
- Detects dependency cycles

### Registry Validation

- Checks required registries exist
- Validates registry contents

### Configuration Validation

- Validates all configuration values are valid
- Detects invalid/negative values
- Checks required fields

### Error Reporting

Validation errors are collected and reported through `ValidationResult`:

```python
from packages.bootstrap.validation import ValidationResult

result = ValidationResult(errors=["error1", "error2"], warnings=["warning1"])
if result.has_errors:
    # Handle errors