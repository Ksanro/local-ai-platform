"""Platform configuration — immutable configuration model.

Defines the complete configuration model for the engineering platform.
All configuration is immutable (frozen dataclasses) with strict typing.

Architecture
------------

PlatformConfiguration
    │
    ├── providers: ProviderConfig
    ├── repository: RepositoryConfig
    ├── pipeline: PipelineConfig
    ├── workflow: WorkflowConfig
    ├── execution: ExecutionConfig
    ├── evaluation: EvaluationConfig
    ├── verification: VerificationConfig
    ├── observability: ObservabilityConfig
    ├── session: SessionConfig
    ├── autonomous: AutonomousConfig
    └── controller: ControllerConfig

All sub-configurations are frozen dataclasses with slots=True.

Public API
----------

.. code-block:: python

    from packages.bootstrap.configuration import PlatformConfiguration

    config = PlatformConfiguration.default()

    # Access configuration
    enabled = config.observability.enabled
    max_symbols = config.repository.max_symbols

"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

def _get_fields(dc: object) -> dict:
    """Get field values from a frozen dataclass as a dict.

    Args:
        dc: A frozen dataclass instance.

    Returns:
        Dictionary of field name to field value.
    """
    return {f.name: getattr(dc, f.name) for f in fields(dc)}


__all__ = [
    "AutonomousConfig",
    "ControllerConfig",
    "EvaluationConfig",
    "ExecutionConfig",
    "ObservabilityConfig",
    "PipelineConfig",
    "PlatformConfiguration",
    "ProviderConfig",
    "RepositoryConfig",
    "SessionConfig",
    "VerificationConfig",
    "WorkflowConfig",
]


# ---------------------------------------------------------------------------
# Provider Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Configuration for provider subsystem.

    Attributes:
        default_provider: Default provider name (e.g. "vllm").
        request_timeout_seconds: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        api_keys: Mapping of provider name to API key.
    """

    default_provider: str = "vllm"
    request_timeout_seconds: float = 60.0
    max_retries: int = 3
    api_keys: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repository Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryConfig:
    """Configuration for repository subsystem.

    Attributes:
        max_symbols: Maximum symbols in context.
        max_modules: Maximum modules in context.
        max_tokens: Maximum token budget.
        context_enabled: Whether repository context is enabled.
    """

    max_symbols: int = 20
    max_modules: int = 10
    max_tokens: int = 4096
    context_enabled: bool = True


# ---------------------------------------------------------------------------
# Pipeline Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Configuration for pipeline subsystem.

    Attributes:
        stages: Ordered list of pipeline stage names to execute.
        enable_repository_context: Whether to enable repository context stage.
        enable_authentication: Whether to enable authentication stage.
    """

    stages: tuple[str, ...] = field(default=("repository_context", "provider"))
    enable_repository_context: bool = True
    enable_authentication: bool = False


# ---------------------------------------------------------------------------
# Workflow Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    """Configuration for workflow subsystem.

    Attributes:
        default_workflow: Default workflow name for execute operations.
        max_steps: Maximum number of steps in a workflow plan.
        enable_autonomous_loop: Whether to enable autonomous iteration.
    """

    default_workflow: str = "default-engineering"
    max_steps: int = 50
    enable_autonomous_loop: bool = False


# ---------------------------------------------------------------------------
# Execution Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Configuration for execution subsystem.

    Attributes:
        max_concurrent_steps: Maximum concurrent execution steps.
        step_timeout_seconds: Timeout per execution step.
        enable_parallel_execution: Whether to enable parallel step execution.
    """

    max_concurrent_steps: int = 1
    step_timeout_seconds: float = 300.0
    enable_parallel_execution: bool = False


# ---------------------------------------------------------------------------
# Evaluation Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    """Configuration for evaluation subsystem.

    Attributes:
        enabled: Whether evaluation is enabled.
        metrics: List of metric names to evaluate.
        categories: List of category names to evaluate.
    """

    enabled: bool = True
    metrics: tuple[str, ...] = field(
        default=("correctness", "efficiency", "quality")
    )
    categories: tuple[str, ...] = field(
        default=("technical", "reliability", "maintainability")
    )


# ---------------------------------------------------------------------------
# Verification Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    """Configuration for verification subsystem.

    Attributes:
        enabled: Whether verification is enabled.
        rules: List of rule names to apply.
        strict_mode: Whether to enforce strict verification.
    """

    enabled: bool = True
    rules: tuple[str, ...] = field(
        default=("syntax", "imports", "exports", "types")
    )
    strict_mode: bool = False


# ---------------------------------------------------------------------------
# Observability Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Configuration for observability subsystem.

    Attributes:
        enabled: Whether telemetry is enabled.
        max_events: Maximum number of events to retain.
        max_metrics: Maximum number of metrics to retain.
        max_traces: Maximum number of traces to retain.
    """

    enabled: bool = False
    max_events: int = 10000
    max_metrics: int = 5000
    max_traces: int = 1000


# ---------------------------------------------------------------------------
# Session Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Configuration for session subsystem.

    Attributes:
        enabled: Whether session management is enabled.
        max_sessions: Maximum number of concurrent sessions.
        auto_close_timeout_seconds: Auto-close idle sessions after this duration.
    """

    enabled: bool = True
    max_sessions: int = 100
    auto_close_timeout_seconds: float = 3600.0


# ---------------------------------------------------------------------------
# Autonomous Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutonomousConfig:
    """Configuration for autonomous engineering subsystem.

    Attributes:
        enabled: Whether autonomous engineering is enabled.
        max_iterations: Maximum autonomous iteration count.
        stopping_policy: Name of the stopping policy to use.
        retry_on_failure: Whether to retry on failure.
    """

    enabled: bool = False
    max_iterations: int = 5
    stopping_policy: str = "convergence"
    retry_on_failure: bool = True


# ---------------------------------------------------------------------------
# Controller Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Configuration for controller subsystem.

    Attributes:
        validate_requests: Whether to validate incoming requests.
        enable_caching: Whether to enable request caching.
        default_operation: Default operation for unmapped requests.
    """

    validate_requests: bool = True
    enable_caching: bool = False
    default_operation: str = "execute"


# ---------------------------------------------------------------------------
# Platform Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformConfiguration:
    """Complete immutable platform configuration.

    This is the single source of truth for all platform configuration.
    All fields are immutable (frozen dataclass with slots=True).

    Attributes:
        providers: Provider subsystem configuration.
        repository: Repository subsystem configuration.
        pipeline: Pipeline subsystem configuration.
        workflow: Workflow subsystem configuration.
        execution: Execution subsystem configuration.
        evaluation: Evaluation subsystem configuration.
        verification: Verification subsystem configuration.
        observability: Observability subsystem configuration.
        session: Session subsystem configuration.
        autonomous: Autonomous engineering subsystem configuration.
        controller: Controller subsystem configuration.

    Usage
    -----

    .. code-block:: python

        from packages.bootstrap.configuration import PlatformConfiguration

        # Use defaults
        config = PlatformConfiguration.default()

        # Custom configuration
        config = PlatformConfiguration(
            repository=RepositoryConfig(
                max_symbols=50,
                context_enabled=True,
            ),
            observability=ObservabilityConfig(
                enabled=True,
            ),
        )
    """

    providers: ProviderConfig = field(default_factory=ProviderConfig)
    repository: RepositoryConfig = field(default_factory=RepositoryConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    autonomous: AutonomousConfig = field(default_factory=AutonomousConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)

    @classmethod
    def default(cls) -> PlatformConfiguration:
        """Create a platform configuration with all default values.

        Returns:
            A new PlatformConfiguration with all defaults.
        """
        return cls(
            providers=ProviderConfig(),
            repository=RepositoryConfig(),
            pipeline=PipelineConfig(),
            workflow=WorkflowConfig(),
            execution=ExecutionConfig(),
            evaluation=EvaluationConfig(),
            verification=VerificationConfig(),
            observability=ObservabilityConfig(),
            session=SessionConfig(),
            autonomous=AutonomousConfig(),
            controller=ControllerConfig(),
        )

    def with_providers(self, **overrides: object) -> PlatformConfiguration:
        """Create a new configuration with provider overrides.

        Args:
            **overrides: Key-value pairs to override in ProviderConfig.

        Returns:
            A new PlatformConfiguration with overrides applied.
        """
        current = self.providers
        new_kwargs = {**_get_fields(current)}
        new_kwargs.update(overrides)
        return PlatformConfiguration(
            providers=ProviderConfig(**new_kwargs),
            repository=self.repository,
            pipeline=self.pipeline,
            workflow=self.workflow,
            execution=self.execution,
            evaluation=self.evaluation,
            verification=self.verification,
            observability=self.observability,
            session=self.session,
            autonomous=self.autonomous,
            controller=self.controller,
        )

    def with_repository(self, **overrides: object) -> PlatformConfiguration:
        """Create a new configuration with repository overrides.

        Args:
            **overrides: Key-value pairs to override in RepositoryConfig.

        Returns:
            A new PlatformConfiguration with overrides applied.
        """
        current = self.repository
        new_kwargs = {**_get_fields(current)}
        new_kwargs.update(overrides)
        return PlatformConfiguration(
            providers=self.providers,
            repository=RepositoryConfig(**new_kwargs),
            pipeline=self.pipeline,
            workflow=self.workflow,
            execution=self.execution,
            evaluation=self.evaluation,
            verification=self.verification,
            observability=self.observability,
            session=self.session,
            autonomous=self.autonomous,
            controller=self.controller,
        )

    def with_observability(self, **overrides: object) -> PlatformConfiguration:
        """Create a new configuration with observability overrides.

        Args:
            **overrides: Key-value pairs to override in ObservabilityConfig.

        Returns:
            A new PlatformConfiguration with overrides applied.
        """
        current = self.observability
        new_kwargs = {**_get_fields(current)}
        new_kwargs.update(overrides)
        return PlatformConfiguration(
            providers=self.providers,
            repository=self.repository,
            pipeline=self.pipeline,
            workflow=self.workflow,
            execution=self.execution,
            evaluation=self.evaluation,
            verification=self.verification,
            observability=ObservabilityConfig(**new_kwargs),
            session=self.session,
            autonomous=self.autonomous,
            controller=self.controller,
        )