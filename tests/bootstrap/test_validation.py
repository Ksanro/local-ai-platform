"""Tests for PlatformValidator.

Tests cover:
- Container validation
- Registry validation
- Configuration validation
- Missing providers detection
- Missing workflows detection
- Duplicate registration detection
- Dependency cycle detection
- Full validation
"""

from __future__ import annotations

import pytest

from packages.bootstrap.validation import (
    PlatformValidator,
    ValidationResult,
    ValidationSeverity,
)


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_empty_result(self) -> None:
        result = ValidationResult()
        assert result.errors == []
        assert result.warnings == []
        assert result.has_errors is False
        assert result.has_warnings is False

    def test_result_with_errors(self) -> None:
        result = ValidationResult(errors=["error1", "error2"])
        assert result.errors == ["error1", "error2"]
        assert result.has_errors is True

    def test_result_with_warnings(self) -> None:
        result = ValidationResult(warnings=["warning1"])
        assert result.warnings == ["warning1"]
        assert result.has_warnings is True

    def test_add_error(self) -> None:
        result = ValidationResult()
        result.add_error("error1")
        assert result.errors == ["error1"]
        assert result.has_errors is True

    def test_add_warning(self) -> None:
        result = ValidationResult()
        result.add_warning("warning1")
        assert result.warnings == ["warning1"]
        assert result.has_warnings is True

    def test_combined_errors_and_warnings(self) -> None:
        result = ValidationResult(
            errors=["error1"],
            warnings=["warning1", "warning2"],
        )
        assert result.has_errors is True
        assert result.has_warnings is True


# ---------------------------------------------------------------------------
# PlatformValidator tests
# ---------------------------------------------------------------------------


class TestPlatformValidator:
    """Tests for PlatformValidator."""

    def test_validate_container_no_validate_method(self) -> None:
        validator = PlatformValidator()
        result = validator.validate_container("not_a_container")
        assert any("validate" in e for e in result)

    def test_validate_container_empty(self) -> None:
        from packages.bootstrap.container import DependencyContainer

        container = DependencyContainer()
        validator = PlatformValidator()
        result = validator.validate_container(container)
        assert any("no registered" in e for e in result)

    def test_validate_container_valid(self) -> None:
        from packages.bootstrap.container import DependencyContainer

        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: "value_b", dependencies=("a",))
        validator = PlatformValidator()
        result = validator.validate_container(container)
        assert result == []

    def test_validate_registries_missing_required(self) -> None:
        from packages.bootstrap.registry import PlatformRegistries

        registries = PlatformRegistries()
        validator = PlatformValidator()
        result = validator.validate_registries(registries)
        assert any("Workflow registry" in e for e in result)
        assert any("Provider registry" in e for e in result)
        assert any("Session registry" in e for e in result)

    def test_validate_registries_complete(self) -> None:
        from packages.bootstrap.registry import PlatformRegistries

        registries = PlatformRegistries(
            workflow_registry="workflow",
            provider_registry="provider",
            session_registry="session",
        )
        validator = PlatformValidator()
        result = validator.validate_registries(registries)
        assert result == []

    def test_validate_configuration_invalid_repository(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            RepositoryConfig,
        )

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1, max_tokens=-100)
        )
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert any("max_symbols" in e for e in result)
        assert any("max_tokens" in e for e in result)

    def test_validate_configuration_invalid_workflow(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            WorkflowConfig,
        )

        config = PlatformConfiguration(
            workflow=WorkflowConfig(max_steps=-1)
        )
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert any("max_steps" in e for e in result)

    def test_validate_configuration_invalid_execution(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            ExecutionConfig,
        )

        config = PlatformConfiguration(
            execution=ExecutionConfig(max_concurrent_steps=-1)
        )
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert any("max_concurrent_steps" in e for e in result)

    def test_validate_configuration_invalid_session(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            SessionConfig,
        )

        config = PlatformConfiguration(
            session=SessionConfig(max_sessions=-1)
        )
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert any("max_sessions" in e for e in result)

    def test_validate_configuration_invalid_autonomous(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            AutonomousConfig,
        )

        config = PlatformConfiguration(
            autonomous=AutonomousConfig(max_iterations=-1)
        )
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert any("max_iterations" in e for e in result)

    def test_validate_configuration_valid(self) -> None:
        from packages.bootstrap.configuration import PlatformConfiguration

        config = PlatformConfiguration.default()
        validator = PlatformValidator()
        result = validator.validate_configuration(config)
        assert result == []

    def test_check_duplicate_registrations(self) -> None:
        from packages.bootstrap.container import DependencyContainer

        container = DependencyContainer()
        validator = PlatformValidator()
        result = validator.check_duplicate_registrations(container)
        assert result == []

    def test_check_dependency_cycles(self) -> None:
        from packages.bootstrap.container import DependencyContainer

        container = DependencyContainer()
        container.register("a", lambda: "value_a")
        container.register("b", lambda a: "value_b", dependencies=("a",))
        validator = PlatformValidator()
        result = validator.check_dependency_cycles(container)
        assert result == []

    def test_check_missing_providers_no_registry(self) -> None:
        from packages.bootstrap.registry import PlatformRegistries

        registries = PlatformRegistries()
        validator = PlatformValidator()
        result = validator.check_missing_providers(None, registries)
        assert result == []

    def test_check_missing_workflows_no_registry(self) -> None:
        from packages.bootstrap.registry import PlatformRegistries

        registries = PlatformRegistries()
        validator = PlatformValidator()
        result = validator.check_missing_workflows(None, registries)
        assert result == []

    def test_full_validation(self) -> None:
        from packages.bootstrap.configuration import PlatformConfiguration
        from packages.bootstrap.container import DependencyContainer
        from packages.bootstrap.registry import PlatformRegistries

        container = DependencyContainer()
        container.register("a", lambda: "value_a")

        registries = PlatformRegistries(
            workflow_registry="workflow",
            provider_registry="provider",
            session_registry="session",
        )

        config = PlatformConfiguration.default()

        validator = PlatformValidator()
        result = validator.validate(container, registries, config)
        assert result.has_errors is False

    def test_full_validation_with_errors(self) -> None:
        from packages.bootstrap.configuration import (
            PlatformConfiguration,
            RepositoryConfig,
        )
        from packages.bootstrap.container import DependencyContainer
        from packages.bootstrap.registry import PlatformRegistries

        container = DependencyContainer()
        container.register("b", lambda a: "value_b", dependencies=("a",))

        registries = PlatformRegistries()

        config = PlatformConfiguration(
            repository=RepositoryConfig(max_symbols=-1)
        )

        validator = PlatformValidator()
        result = validator.validate(container, registries, config)
        assert result.has_errors is True
        assert len(result.errors) > 0

    def test_custom_required_providers(self) -> None:
        validator = PlatformValidator(
            required_providers=("custom-provider",)
        )
        assert validator._required_providers == ("custom-provider",)

    def test_custom_required_workflows(self) -> None:
        validator = PlatformValidator(
            required_workflows=("custom-workflow",)
        )
        assert validator._required_workflows == ("custom-workflow",)