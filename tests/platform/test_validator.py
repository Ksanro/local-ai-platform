"""Tests for PlatformValidator.

Tests cover:
- Bootstrap validation
- Dependency graph validation
- Registry validation
- Provider validation
- Workflow validation
- Task validation
- Capability validation
- Configuration validation
- Public API validation
- Duplicate detection
- Dependency cycle detection
- Full validation
- Deterministic reports
"""

from __future__ import annotations

import pytest

from packages.platform.models import Severity
from packages.platform.validator import PlatformValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockRegistries:
    """Mock registries object for testing."""

    def __init__(
        self,
        workflow_registry: object | None = None,
        session_registry: object | None = None,
        observability_registry: object | None = None,
        verification_registry: object | None = None,
        provider_registry: object | None = None,
        task_registry: object | None = None,
        capability_registry: object | None = None,
    ) -> None:
        self.workflow_registry = workflow_registry
        self.session_registry = session_registry
        self.observability_registry = observability_registry
        self.verification_registry = verification_registry
        self.provider_registry = provider_registry
        self.task_registry = task_registry
        self.capability_registry = capability_registry


class _MockContainer:
    """Mock dependency container for testing."""

    def __init__(
        self,
        count: int = 0,
        validate_errors: list[str] | None = None,
    ) -> None:
        self._count = count
        self._validate_errors = validate_errors or []

    @property
    def count(self) -> int:  # type: ignore[override]
        return self._count

    def validate(self) -> list[str]:  # type: ignore[override]
        return self._validate_errors


class _MockConfig:
    """Mock configuration for testing."""

    def __init__(
        self,
        max_symbols: int = 10000,
        max_tokens: int = 100000,
        max_steps: int = 100,
        max_concurrent_steps: int = 4,
        max_sessions: int = 10,
        max_iterations: int = 50,
    ) -> None:
        self.repository = _MockRepository(max_symbols, max_tokens)
        self.workflow = _MockWorkflow(max_steps)
        self.execution = _MockExecution(max_concurrent_steps)
        self.session = _MockSession(max_sessions)
        self.autonomous = _MockAutonomous(max_iterations)


class _MockRepository:
    def __init__(self, max_symbols: int, max_tokens: int) -> None:
        self.max_symbols = max_symbols
        self.max_tokens = max_tokens


class _MockWorkflow:
    def __init__(self, max_steps: int) -> None:
        self.max_steps = max_steps


class _MockExecution:
    def __init__(self, max_concurrent_steps: int) -> None:
        self.max_concurrent_steps = max_concurrent_steps


class _MockSession:
    def __init__(self, max_sessions: int) -> None:
        self.max_sessions = max_sessions


class _MockAutonomous:
    def __init__(self, max_iterations: int) -> None:
        self.max_iterations = max_iterations


def _make_valid_config() -> _MockConfig:
    return _MockConfig()


# ---------------------------------------------------------------------------
# Bootstrap validation tests
# ---------------------------------------------------------------------------


class TestBootstrapValidation:
    """Tests for bootstrap validation."""

    def test_bootstrap_none_registries(self) -> None:
        validator = PlatformValidator()
        report = validator.validate(None, None, None)
        assert report.is_valid is False
        assert any(i.severity == Severity.CRITICAL for i in report.issues)

    def test_bootstrap_missing_workflow_registry(self) -> None:
        registries = _MockRegistries(session_registry="session")
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        assert report.is_valid is False
        assert any("workflow" in i.description.lower() for i in report.issues)

    def test_bootstrap_missing_session_registry(self) -> None:
        registries = _MockRegistries(workflow_registry="workflow")
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        assert report.is_valid is False
        assert any("session" in i.description.lower() for i in report.issues)

    def test_bootstrap_complete(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        bootstrap_issues = [i for i in report.issues if i.component.startswith("bootstrap_")]
        assert all(i.severity != Severity.ERROR for i in bootstrap_issues)


# ---------------------------------------------------------------------------
# Dependency graph validation tests
# ---------------------------------------------------------------------------


class TestDependencyGraphValidation:
    """Tests for dependency graph validation."""

    def test_dependency_graph_none_container(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), None)
        assert any(i.severity == Severity.CRITICAL for i in report.issues)

    def test_dependency_graph_empty_container(self) -> None:
        registries = _MockRegistries()
        container = _MockContainer(count=0)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), container)
        assert any("no registered" in i.description.lower() for i in report.issues)

    def test_dependency_graph_with_errors(self) -> None:
        registries = _MockRegistries()
        container = _MockContainer(
            count=5,
            validate_errors=["Dependency 'a' requires 'b', which is not registered."],
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), container)
        assert any("not registered" in i.description for i in report.issues)

    def test_dependency_graph_valid(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
        )
        container = _MockContainer(count=5, validate_errors=[])
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), container)
        dep_issues = [i for i in report.issues if i.component == "dependency_graph"]
        assert all(i.severity != Severity.ERROR for i in dep_issues)


# ---------------------------------------------------------------------------
# Registry validation tests
# ---------------------------------------------------------------------------


class TestRegistryValidation:
    """Tests for registry validation."""

    def test_registry_all_none(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        reg_issues = [i for i in report.issues if i.component.startswith("registry_")]
        assert len(reg_issues) > 0

    def test_registry_partial(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
            observability_registry="obs",
            verification_registry="verif",
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        reg_issues = [i for i in report.issues if i.component.startswith("registry_")]
        assert all(i.severity == Severity.WARNING for i in reg_issues)

    def test_registry_complete(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
            observability_registry="obs",
            verification_registry="verif",
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        reg_issues = [i for i in report.issues if i.component.startswith("registry_")]
        # When all registries are present, there should be 0 registry issues
        assert len(reg_issues) == 0


# ---------------------------------------------------------------------------
# Provider validation tests
# ---------------------------------------------------------------------------


class TestProviderValidation:
    """Tests for provider validation."""

    def test_provider_no_registry(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        prov_issues = [i for i in report.issues if i.component == "provider_registry"]
        assert len(prov_issues) == 0

    def test_provider_missing_required(self) -> None:
        mock_reg = _MockProviderRegistry([])
        registries = _MockRegistries(provider_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        prov_issues = [i for i in report.issues if i.component == "provider_registry"]
        assert any("vllm" in i.description for i in prov_issues)

    def test_provider_present(self) -> None:
        mock_reg = _MockProviderRegistry(["vllm", "openai"])
        registries = _MockRegistries(provider_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        prov_issues = [i for i in report.issues if i.component == "provider_registry"]
        assert not any("vllm" in i.description for i in prov_issues)

    def test_provider_custom_required(self) -> None:
        validator = PlatformValidator(required_providers=("custom-provider",))
        mock_reg = _MockProviderRegistry(["vllm"])
        registries = _MockRegistries(provider_registry=mock_reg)
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        assert any("custom-provider" in i.description for i in report.issues)


class _MockProviderRegistry:
    def __init__(self, providers: list[str]) -> None:
        self._providers = providers

    def all(self) -> list[str]:
        return self._providers


# ---------------------------------------------------------------------------
# Workflow validation tests
# ---------------------------------------------------------------------------


class TestWorkflowValidation:
    """Tests for workflow validation."""

    def test_workflow_no_registry(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        work_issues = [i for i in report.issues if i.component == "workflow_registry"]
        assert len(work_issues) == 0

    def test_workflow_missing_required(self) -> None:
        mock_reg = _MockWorkflowRegistry([])
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        assert any("default-engineering" in i.description for i in report.issues)

    def test_workflow_present(self) -> None:
        mock_reg = _MockWorkflowRegistry(["default-engineering", "code-review"])
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        work_issues = [i for i in report.issues if i.component == "workflow_registry"]
        assert len(work_issues) == 0

    def test_workflow_custom_required(self) -> None:
        validator = PlatformValidator(required_workflows=("custom-workflow",))
        mock_reg = _MockWorkflowRegistry(["default-engineering"])
        registries = _MockRegistries(workflow_registry=mock_reg)
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        assert any("custom-workflow" in i.description for i in report.issues)


class _MockWorkflowRegistry:
    def __init__(self, workflows: list[str]) -> None:
        self._workflows = workflows

    def all(self) -> list[str]:
        return self._workflows


# ---------------------------------------------------------------------------
# Task validation tests
# ---------------------------------------------------------------------------


class TestTaskValidation:
    """Tests for task validation."""

    def test_task_no_registry(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        task_issues = [i for i in report.issues if i.component == "task_registry"]
        assert len(task_issues) == 0

    def test_task_empty(self) -> None:
        mock_reg = _MockTaskRegistry([])
        registries = _MockRegistries(task_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        task_issues = [i for i in report.issues if i.component == "task_registry"]
        assert any("empty" in i.description.lower() for i in task_issues)

    def test_task_present(self) -> None:
        mock_reg = _MockTaskRegistry(["task1", "task2"])
        registries = _MockRegistries(task_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        task_issues = [i for i in report.issues if i.component == "task_registry"]
        assert len(task_issues) == 0


class _MockTaskRegistry:
    def __init__(self, tasks: list[str]) -> None:
        self._tasks = tasks

    def all(self) -> list[str]:
        return self._tasks


# ---------------------------------------------------------------------------
# Capability validation tests
# ---------------------------------------------------------------------------


class TestCapabilityValidation:
    """Tests for capability validation."""

    def test_capability_no_registry(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        cap_issues = [i for i in report.issues if i.component == "capability_registry"]
        assert len(cap_issues) == 0

    def test_capability_empty(self) -> None:
        mock_reg = _MockCapabilityRegistry([])
        registries = _MockRegistries(capability_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        cap_issues = [i for i in report.issues if i.component == "capability_registry"]
        assert any("empty" in i.description.lower() for i in cap_issues)

    def test_capability_present(self) -> None:
        mock_reg = _MockCapabilityRegistry(["cap1", "cap2"])
        registries = _MockRegistries(capability_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        cap_issues = [i for i in report.issues if i.component == "capability_registry"]
        assert len(cap_issues) == 0


class _MockCapabilityRegistry:
    def __init__(self, capabilities: list[str]) -> None:
        self._capabilities = capabilities

    def all(self) -> list[str]:
        return self._capabilities


# ---------------------------------------------------------------------------
# Configuration validation tests
# ---------------------------------------------------------------------------


class TestConfigurationValidation:
    """Tests for configuration validation."""

    def test_config_none(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(None, None, None)
        assert any(i.severity == Severity.CRITICAL for i in report.issues)

    def test_config_negative_values(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
        )
        config = _MockConfig(
            max_symbols=-1,
            max_tokens=-100,
            max_steps=-1,
            max_concurrent_steps=-1,
            max_sessions=-1,
            max_iterations=-1,
        )
        validator = PlatformValidator()
        report = validator.validate(registries, config, _MockContainer())
        conf_issues = [i for i in report.issues if i.component.startswith("configuration.")]
        assert len(conf_issues) == 6

    def test_config_valid(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
        )
        config = _make_valid_config()
        validator = PlatformValidator()
        report = validator.validate(registries, config, _MockContainer())
        conf_issues = [i for i in report.issues if i.component.startswith("configuration.")]
        assert len(conf_issues) == 0

    def test_config_zero_values(self) -> None:
        registries = _MockRegistries(
            workflow_registry="workflow",
            session_registry="session",
        )
        config = _MockConfig(
            max_symbols=0,
            max_tokens=0,
            max_steps=0,
            max_concurrent_steps=0,
            max_sessions=0,
            max_iterations=0,
        )
        validator = PlatformValidator()
        report = validator.validate(registries, config, _MockContainer())
        conf_issues = [i for i in report.issues if i.component.startswith("configuration.")]
        assert len(conf_issues) == 6


# ---------------------------------------------------------------------------
# Public API validation tests
# ---------------------------------------------------------------------------


class TestPublicAPIValidation:
    """Tests for public API validation."""

    def test_public_api_no_registry(self) -> None:
        registries = _MockRegistries()
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        api_issues = [i for i in report.issues if i.component.startswith("public_api_")]
        assert len(api_issues) == 0

    def test_public_api_missing_method(self) -> None:
        mock_reg = _MockRegistryWithoutAll()
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        api_issues = [i for i in report.issues if i.component.startswith("public_api_")]
        assert any("missing public method" in i.description for i in api_issues)

    def test_public_api_present(self) -> None:
        mock_reg = _MockRegistryWithAll()
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        api_issues = [i for i in report.issues if i.component.startswith("public_api_")]
        assert len(api_issues) == 0


class _MockRegistryWithoutAll:
    """Registry without 'all' method."""
    pass


class _MockRegistryWithAll:
    """Registry with 'all' method."""
    def all(self) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Tests for duplicate registration detection."""

    def test_no_duplicates(self) -> None:
        mock_reg = _MockWorkflowRegistry(["wf1", "wf2"])
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        dup_issues = [i for i in report.issues if i.component.startswith("registry_") and "DUP" in str(i.identifier)]
        assert len(dup_issues) == 0

    def test_duplicates_detected(self) -> None:
        mock_reg = _MockDuplicateRegistry(["wf1", "wf1", "wf2"])
        registries = _MockRegistries(workflow_registry=mock_reg)
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), _MockContainer())
        dup_issues = [i for i in report.issues if "Duplicate" in i.description]
        assert len(dup_issues) > 0


class _MockDuplicateRegistry:
    """Registry that returns duplicate entries."""

    def __init__(self, entries: list[str]) -> None:
        self._entries = entries

    def all(self) -> list[str]:
        return self._entries


# ---------------------------------------------------------------------------
# Dependency cycle detection tests
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Tests for dependency cycle detection."""

    def test_no_cycles(self) -> None:
        container = _MockContainer(count=5, validate_errors=[])
        registries = _MockRegistries(
            workflow_registry="wf",
            session_registry="sess",
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), container)
        cycle_issues = [i for i in report.issues if i.component == "dependency_graph" and "cycle" in i.description.lower()]
        assert len(cycle_issues) == 0

    def test_cycles_detected(self) -> None:
        container = _MockContainer(
            count=5,
            validate_errors=["Circular dependency detected: a -> b -> a."],
        )
        registries = _MockRegistries(
            workflow_registry="wf",
            session_registry="sess",
        )
        validator = PlatformValidator()
        report = validator.validate(registries, _make_valid_config(), container)
        cycle_issues = [i for i in report.issues if i.component == "dependency_graph" and i.severity == Severity.CRITICAL]
        assert len(cycle_issues) > 0


# ---------------------------------------------------------------------------
# Full validation tests
# ---------------------------------------------------------------------------


class TestFullValidation:
    """Tests for full validation."""

    def test_full_validation_healthy(self) -> None:
        mock_reg = _MockWorkflowRegistry(["default-engineering"])
        mock_cap = _MockCapabilityRegistry(["cap1"])
        mock_task = _MockTaskRegistry(["task1"])
        mock_prov = _MockProviderRegistry(["vllm"])

        registries = _MockRegistries(
            workflow_registry=mock_reg,
            session_registry="session",
            observability_registry="obs",
            verification_registry="verif",
            provider_registry=mock_prov,
            task_registry=mock_task,
            capability_registry=mock_cap,
        )
        config = _make_valid_config()
        container = _MockContainer(count=5, validate_errors=[])

        validator = PlatformValidator()
        report = validator.validate(registries, config, container)

        # Should have no errors (only warnings for empty registries)
        error_issues = [i for i in report.issues if i.severity in (Severity.ERROR, Severity.CRITICAL)]
        assert len(error_issues) == 0

    def test_full_validation_unhealthy(self) -> None:
        registries = _MockRegistries()
        config = _MockConfig(max_symbols=-1)
        container = _MockContainer(count=0, validate_errors=["cycle error"])

        validator = PlatformValidator()
        report = validator.validate(registries, config, container)

        assert report.is_valid is False
        assert report.statistics.issues_count > 0

    def test_full_validation_deterministic(self) -> None:
        mock_reg = _MockWorkflowRegistry(["default-engineering"])
        registries = _MockRegistries(
            workflow_registry=mock_reg,
            session_registry="session",
        )
        config = _make_valid_config()
        container = _MockContainer(count=3, validate_errors=[])

        # Create separate validators to ensure counter starts fresh
        report1 = PlatformValidator().validate(registries, config, container)
        report2 = PlatformValidator().validate(registries, config, container)

        assert len(report1.issues) == len(report2.issues)
        for i1, i2 in zip(report1.issues, report2.issues):
            assert i1.identifier == i2.identifier
            assert i1.component == i2.component
            assert i1.severity == i2.severity
            assert i1.description == i2.description


# ---------------------------------------------------------------------------
# Validator attributes tests
# ---------------------------------------------------------------------------


class TestValidatorAttributes:
    """Tests for validator configuration."""

    def test_custom_required_providers(self) -> None:
        validator = PlatformValidator(required_providers=("custom-provider",))
        assert validator._required_providers == ("custom-provider",)

    def test_custom_required_workflows(self) -> None:
        validator = PlatformValidator(required_workflows=("custom-workflow",))
        assert validator._required_workflows == ("custom-workflow",)

    def test_default_required_providers(self) -> None:
        validator = PlatformValidator()
        assert validator._required_providers == ("vllm",)

    def test_default_required_workflows(self) -> None:
        validator = PlatformValidator()
        assert validator._required_workflows == ("default-engineering",)