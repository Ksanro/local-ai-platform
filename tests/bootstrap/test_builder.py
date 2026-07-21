"""Tests for PlatformBootstrap.

Tests cover:
- Build process
- Registry construction
- Factory construction
- Engine construction
- Component registration
- Platform validation
- Controller construction
- Error handling
- Build function
"""

from __future__ import annotations

import pytest

from packages.bootstrap.builder import PlatformBootstrap
from packages.bootstrap.configuration import PlatformConfiguration


# ---------------------------------------------------------------------------
# PlatformBootstrap tests
# ---------------------------------------------------------------------------


class TestPlatformBootstrap:
    """Tests for PlatformBootstrap."""

    def test_build_success(self) -> None:
        """Test successful platform build."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        controller = bootstrap.build(config)
        assert controller is not None

    def test_build_with_custom_validator(self) -> None:
        """Test build with custom validator."""
        from packages.bootstrap.validation import PlatformValidator

        validator = PlatformValidator()
        bootstrap = PlatformBootstrap(validator=validator)
        config = PlatformConfiguration.default()
        controller = bootstrap.build(config)
        assert controller is not None

    def test_build_invalid_configuration_raises(self) -> None:
        """Test build with invalid configuration raises RuntimeError."""
        from packages.bootstrap.configuration import RepositoryConfig

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1)
        )
        bootstrap = PlatformBootstrap()
        with pytest.raises(RuntimeError, match="validation failed"):
            bootstrap.build(config)

    def test_construct_registries(self) -> None:
        """Test registry construction."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        assert registries.workflow_registry is not None
        # Providers use module-level functions, not a class-based registry
        assert registries.provider_registry is None
        assert registries.session_registry is not None
        assert registries.observability_registry is not None
        # Serializers use module-level functions, not a class-based registry
        assert registries.serializer_registry is None
        assert registries.verification_registry is not None
        # Evaluation uses module-level functions, not a class-based registry
        assert registries.evaluation_registry is None

    def test_construct_factories(self) -> None:
        """Test factory construction."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        factories = bootstrap._construct_factories(registries, config)
        assert "create_provider" in factories

    def test_construct_engines(self) -> None:
        """Test engine construction."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        factories = bootstrap._construct_factories(registries, config)
        engines = bootstrap._construct_engines(factories, registries, config)
        assert "session_manager" in engines
        assert "telemetry" in engines

    def test_register_providers(self) -> None:
        """Test provider registration."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        factories = bootstrap._construct_factories(registries, config)
        bootstrap._register_components(factories, {}, registries, config)
        # Should not raise - providers use module-level functions
        assert registries.provider_registry is None

    def test_register_workflows(self) -> None:
        """Test workflow registration."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        factories = bootstrap._construct_factories(registries, config)
        bootstrap._register_components(factories, {}, registries, config)
        # Check that default workflows are registered
        workflow_registry = registries.workflow_registry
        assert workflow_registry is not None
        assert workflow_registry.has("default-engineering")
        assert workflow_registry.has("code-review")
        assert workflow_registry.has("implement-feature")

    def test_validate_platform_valid(self) -> None:
        """Test platform validation with valid configuration."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        result = bootstrap._validate_platform(registries, config)
        assert result.has_errors is False

    def test_validate_platform_invalid(self) -> None:
        """Test platform validation with invalid configuration."""
        from packages.bootstrap.configuration import RepositoryConfig

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1)
        )
        bootstrap = PlatformBootstrap()
        registries = bootstrap._construct_registries(config)
        result = bootstrap._validate_platform(registries, config)
        assert result.has_errors is True

    def test_validate_configuration_valid(self) -> None:
        """Test configuration validation with valid config."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        errors = bootstrap._validate_configuration(config)
        assert errors == []

    def test_validate_configuration_invalid_repository(self) -> None:
        """Test configuration validation with invalid repository config."""
        from packages.bootstrap.configuration import RepositoryConfig

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1, max_tokens=-100)
        )
        bootstrap = PlatformBootstrap()
        errors = bootstrap._validate_configuration(config)
        assert any("max_symbols" in e for e in errors)
        assert any("max_tokens" in e for e in errors)

    def test_validate_configuration_invalid_workflow(self) -> None:
        """Test configuration validation with invalid workflow config."""
        from packages.bootstrap.configuration import WorkflowConfig

        config = PlatformConfiguration(
            workflow=WorkflowConfig(max_steps=-1)
        )
        bootstrap = PlatformBootstrap()
        errors = bootstrap._validate_configuration(config)
        assert any("max_steps" in e for e in errors)

    def test_validate_configuration_invalid_execution(self) -> None:
        """Test configuration validation with invalid execution config."""
        from packages.bootstrap.configuration import ExecutionConfig

        config = PlatformConfiguration(
            execution=ExecutionConfig(max_concurrent_steps=-1)
        )
        bootstrap = PlatformBootstrap()
        errors = bootstrap._validate_configuration(config)
        assert any("max_concurrent_steps" in e for e in errors)

    def test_validate_configuration_invalid_session(self) -> None:
        """Test configuration validation with invalid session config."""
        from packages.bootstrap.configuration import SessionConfig

        config = PlatformConfiguration(
            session=SessionConfig(max_sessions=-1)
        )
        bootstrap = PlatformBootstrap()
        errors = bootstrap._validate_configuration(config)
        assert any("max_sessions" in e for e in errors)

    def test_validate_configuration_invalid_autonomous(self) -> None:
        """Test configuration validation with invalid autonomous config."""
        from packages.bootstrap.configuration import AutonomousConfig

        config = PlatformConfiguration(
            autonomous=AutonomousConfig(max_iterations=-1)
        )
        bootstrap = PlatformBootstrap()
        errors = bootstrap._validate_configuration(config)
        assert any("max_iterations" in e for e in errors)

    def test_construct_controller(self) -> None:
        """Test controller construction."""
        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()
        registries = bootstrap._construct_registries(config)
        factories = bootstrap._construct_factories(registries, config)
        engines = bootstrap._construct_engines(factories, registries, config)
        controller = bootstrap._construct_controller(engines, registries, config)
        assert controller is not None


# ---------------------------------------------------------------------------
# build function tests
# ---------------------------------------------------------------------------


class TestBuildFunction:
    """Tests for the build() convenience function."""

    def test_build_default(self) -> None:
        """Test build with default configuration."""
        from packages.bootstrap import build

        controller = build()
        assert controller is not None

    def test_build_with_config(self) -> None:
        """Test build with custom configuration."""
        from packages.bootstrap import build

        config = PlatformConfiguration.default()
        controller = build(config)
        assert controller is not None

    def test_build_invalid_raises(self) -> None:
        """Test build with invalid configuration raises RuntimeError."""
        from packages.bootstrap.configuration import RepositoryConfig
        from packages.bootstrap import build

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1)
        )
        with pytest.raises(RuntimeError, match="validation failed"):
            build(config)