"""Tests for PlatformConfiguration and all sub-configurations.

Tests cover:
- Immutable configuration (frozen dataclass)
- Default values
- Override methods (with_providers, with_repository, with_observability)
- Invalid configuration values
- Type safety
"""

from __future__ import annotations

import pytest

from packages.bootstrap.configuration import (
    AutonomousConfig,
    ControllerConfig,
    EvaluationConfig,
    ExecutionConfig,
    ObservabilityConfig,
    PipelineConfig,
    PlatformConfiguration,
    ProviderConfig,
    RepositoryConfig,
    SessionConfig,
    VerificationConfig,
    WorkflowConfig,
)


# ---------------------------------------------------------------------------
# ProviderConfig tests
# ---------------------------------------------------------------------------


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_default_values(self) -> None:
        config = ProviderConfig()
        assert config.default_provider == "vllm"
        assert config.request_timeout_seconds == 60.0
        assert config.max_retries == 3
        assert config.api_keys == {}

    def test_custom_values(self) -> None:
        config = ProviderConfig(
            default_provider="openai",
            request_timeout_seconds=120.0,
            max_retries=5,
            api_keys={"openai": "sk-test"},
        )
        assert config.default_provider == "openai"
        assert config.request_timeout_seconds == 120.0
        assert config.max_retries == 5
        assert config.api_keys == {"openai": "sk-test"}

    def test_frozen_dataclass(self) -> None:
        config = ProviderConfig()
        with pytest.raises(Exception):
            config.default_provider = "test"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# RepositoryConfig tests
# ---------------------------------------------------------------------------


class TestRepositoryConfig:
    """Tests for RepositoryConfig."""

    def test_default_values(self) -> None:
        config = RepositoryConfig()
        assert config.max_symbols == 20
        assert config.max_modules == 10
        assert config.max_tokens == 4096
        assert config.context_enabled is True

    def test_custom_values(self) -> None:
        config = RepositoryConfig(
            max_symbols=50,
            max_modules=20,
            max_tokens=8192,
            context_enabled=False,
        )
        assert config.max_symbols == 50
        assert config.max_modules == 20
        assert config.max_tokens == 8192
        assert config.context_enabled is False

    def test_frozen_dataclass(self) -> None:
        config = RepositoryConfig()
        with pytest.raises(Exception):
            config.max_symbols = 50  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PipelineConfig tests
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_values(self) -> None:
        config = PipelineConfig()
        assert config.stages == ("repository_context", "provider")
        assert config.enable_repository_context is True
        assert config.enable_authentication is False

    def test_custom_values(self) -> None:
        config = PipelineConfig(
            stages=("auth", "repository_context", "provider"),
            enable_repository_context=False,
            enable_authentication=True,
        )
        assert config.stages == ("auth", "repository_context", "provider")
        assert config.enable_repository_context is False
        assert config.enable_authentication is True

    def test_frozen_dataclass(self) -> None:
        config = PipelineConfig()
        with pytest.raises(Exception):
            config.stages = ("test",)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# WorkflowConfig tests
# ---------------------------------------------------------------------------


class TestWorkflowConfig:
    """Tests for WorkflowConfig."""

    def test_default_values(self) -> None:
        config = WorkflowConfig()
        assert config.default_workflow == "default-engineering"
        assert config.max_steps == 50
        assert config.enable_autonomous_loop is False

    def test_custom_values(self) -> None:
        config = WorkflowConfig(
            default_workflow="custom-workflow",
            max_steps=100,
            enable_autonomous_loop=True,
        )
        assert config.default_workflow == "custom-workflow"
        assert config.max_steps == 100
        assert config.enable_autonomous_loop is True

    def test_frozen_dataclass(self) -> None:
        config = WorkflowConfig()
        with pytest.raises(Exception):
            config.max_steps = 100  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# ExecutionConfig tests
# ---------------------------------------------------------------------------


class TestExecutionConfig:
    """Tests for ExecutionConfig."""

    def test_default_values(self) -> None:
        config = ExecutionConfig()
        assert config.max_concurrent_steps == 1
        assert config.step_timeout_seconds == 300.0
        assert config.enable_parallel_execution is False

    def test_custom_values(self) -> None:
        config = ExecutionConfig(
            max_concurrent_steps=4,
            step_timeout_seconds=600.0,
            enable_parallel_execution=True,
        )
        assert config.max_concurrent_steps == 4
        assert config.step_timeout_seconds == 600.0
        assert config.enable_parallel_execution is True

    def test_frozen_dataclass(self) -> None:
        config = ExecutionConfig()
        with pytest.raises(Exception):
            config.max_concurrent_steps = 4  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# EvaluationConfig tests
# ---------------------------------------------------------------------------


class TestEvaluationConfig:
    """Tests for EvaluationConfig."""

    def test_default_values(self) -> None:
        config = EvaluationConfig()
        assert config.enabled is True
        assert config.metrics == ("correctness", "efficiency", "quality")
        assert config.categories == ("technical", "reliability", "maintainability")

    def test_custom_values(self) -> None:
        config = EvaluationConfig(
            enabled=False,
            metrics=("performance",),
            categories=("security",),
        )
        assert config.enabled is False
        assert config.metrics == ("performance",)
        assert config.categories == ("security",)

    def test_frozen_dataclass(self) -> None:
        config = EvaluationConfig()
        with pytest.raises(Exception):
            config.enabled = False  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# VerificationConfig tests
# ---------------------------------------------------------------------------


class TestVerificationConfig:
    """Tests for VerificationConfig."""

    def test_default_values(self) -> None:
        config = VerificationConfig()
        assert config.enabled is True
        assert config.rules == ("syntax", "imports", "exports", "types")
        assert config.strict_mode is False

    def test_custom_values(self) -> None:
        config = VerificationConfig(
            enabled=False,
            rules=("custom-rule",),
            strict_mode=True,
        )
        assert config.enabled is False
        assert config.rules == ("custom-rule",)
        assert config.strict_mode is True

    def test_frozen_dataclass(self) -> None:
        config = VerificationConfig()
        with pytest.raises(Exception):
            config.enabled = False  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# ObservabilityConfig tests
# ---------------------------------------------------------------------------


class TestObservabilityConfig:
    """Tests for ObservabilityConfig."""

    def test_default_values(self) -> None:
        config = ObservabilityConfig()
        assert config.enabled is False
        assert config.max_events == 10000
        assert config.max_metrics == 5000
        assert config.max_traces == 1000

    def test_custom_values(self) -> None:
        config = ObservabilityConfig(
            enabled=True,
            max_events=50000,
            max_metrics=25000,
            max_traces=5000,
        )
        assert config.enabled is True
        assert config.max_events == 50000
        assert config.max_metrics == 25000
        assert config.max_traces == 5000

    def test_frozen_dataclass(self) -> None:
        config = ObservabilityConfig()
        with pytest.raises(Exception):
            config.enabled = True  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# SessionConfig tests
# ---------------------------------------------------------------------------


class TestSessionConfig:
    """Tests for SessionConfig."""

    def test_default_values(self) -> None:
        config = SessionConfig()
        assert config.enabled is True
        assert config.max_sessions == 100
        assert config.auto_close_timeout_seconds == 3600.0

    def test_custom_values(self) -> None:
        config = SessionConfig(
            enabled=False,
            max_sessions=50,
            auto_close_timeout_seconds=1800.0,
        )
        assert config.enabled is False
        assert config.max_sessions == 50
        assert config.auto_close_timeout_seconds == 1800.0

    def test_frozen_dataclass(self) -> None:
        config = SessionConfig()
        with pytest.raises(Exception):
            config.enabled = False  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# AutonomousConfig tests
# ---------------------------------------------------------------------------


class TestAutonomousConfig:
    """Tests for AutonomousConfig."""

    def test_default_values(self) -> None:
        config = AutonomousConfig()
        assert config.enabled is False
        assert config.max_iterations == 5
        assert config.stopping_policy == "convergence"
        assert config.retry_on_failure is True

    def test_custom_values(self) -> None:
        config = AutonomousConfig(
            enabled=True,
            max_iterations=10,
            stopping_policy="timeout",
            retry_on_failure=False,
        )
        assert config.enabled is True
        assert config.max_iterations == 10
        assert config.stopping_policy == "timeout"
        assert config.retry_on_failure is False

    def test_frozen_dataclass(self) -> None:
        config = AutonomousConfig()
        with pytest.raises(Exception):
            config.enabled = True  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# ControllerConfig tests
# ---------------------------------------------------------------------------


class TestControllerConfig:
    """Tests for ControllerConfig."""

    def test_default_values(self) -> None:
        config = ControllerConfig()
        assert config.validate_requests is True
        assert config.enable_caching is False
        assert config.default_operation == "execute"

    def test_custom_values(self) -> None:
        config = ControllerConfig(
            validate_requests=False,
            enable_caching=True,
            default_operation="analyze",
        )
        assert config.validate_requests is False
        assert config.enable_caching is True
        assert config.default_operation == "analyze"

    def test_frozen_dataclass(self) -> None:
        config = ControllerConfig()
        with pytest.raises(Exception):
            config.validate_requests = False  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PlatformConfiguration tests
# ---------------------------------------------------------------------------


class TestPlatformConfiguration:
    """Tests for PlatformConfiguration."""

    def test_default_values(self) -> None:
        config = PlatformConfiguration.default()
        assert isinstance(config.providers, ProviderConfig)
        assert isinstance(config.repository, RepositoryConfig)
        assert isinstance(config.pipeline, PipelineConfig)
        assert isinstance(config.workflow, WorkflowConfig)
        assert isinstance(config.execution, ExecutionConfig)
        assert isinstance(config.evaluation, EvaluationConfig)
        assert isinstance(config.verification, VerificationConfig)
        assert isinstance(config.observability, ObservabilityConfig)
        assert isinstance(config.session, SessionConfig)
        assert isinstance(config.autonomous, AutonomousConfig)
        assert isinstance(config.controller, ControllerConfig)

    def test_custom_values(self) -> None:
        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=50),
            observability=ObservabilityConfig(enabled=True),
        )
        assert config.repository.max_symbols == 50
        assert config.observability.enabled is True
        # Other fields should be defaults
        assert config.providers.default_provider == "vllm"

    def test_frozen_dataclass(self) -> None:
        config = PlatformConfiguration.default()
        with pytest.raises(Exception):
            config.providers = ProviderConfig()  # type: ignore[assignment]

    def test_with_providers(self) -> None:
        config = PlatformConfiguration.default()
        new_config = config.with_providers(default_provider="openai")
        assert new_config.providers.default_provider == "openai"
        assert new_config.repository == config.repository

    def test_with_repository(self) -> None:
        config = PlatformConfiguration.default()
        new_config = config.with_repository(max_symbols=50)
        assert new_config.repository.max_symbols == 50
        assert new_config.providers == config.providers

    def test_with_observability(self) -> None:
        config = PlatformConfiguration.default()
        new_config = config.with_observability(enabled=True)
        assert new_config.observability.enabled is True
        assert new_config.repository == config.repository

    def test_immutable_sub_configs(self) -> None:
        config = PlatformConfiguration.default()
        # Sub-configs should also be frozen
        with pytest.raises(Exception):
            config.providers.default_provider = "test"  # type: ignore[assignment]

    def test_no_shared_state(self) -> None:
        config1 = PlatformConfiguration.default()
        config2 = config1.with_providers(default_provider="openai")
        # config1 should not be affected
        assert config1.providers.default_provider == "vllm"
        assert config2.providers.default_provider == "openai"