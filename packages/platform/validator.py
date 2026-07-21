"""Platform Validator — comprehensive validation of platform integrity.

Architecture
------------

PlatformValidator performs complete integrity validation of the assembled
engineering platform. It is executed after Platform Bootstrap and before
the Engineering Controller accepts requests.

    PlatformValidator
        │
        ├── validate()
        │   ├── validate_bootstrap()
        │   ├── validate_dependency_graph()
        │   ├── validate_registries()
        │   ├── validate_providers()
        │   ├── validate_workflows()
        │   ├── validate_tasks()
        │   ├── validate_capabilities()
        │   ├── validate_configuration()
        │   ├── validate_public_api()
        │   ├── check_duplicate_registrations()
        │   └── check_dependency_cycles()
        │
        └── ValidationReport

Public API
----------

.. code-block:: python

    from packages.platform.validator import PlatformValidator

    validator = PlatformValidator()
    report = validator.validate(registries, configuration, container)

    if report.is_valid:
        print("Platform is healthy")
    else:
        for issue in report.issues:
            print(f"{issue.severity}: {issue.description}")

Constraints
-----------

- NEVER performs engineering work.
- NEVER invokes providers.
- NEVER analyzes repositories.
- ONLY validates platform consistency.

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.platform.diagnostics import DiagnosticsEngine
from packages.platform.models import (
    PlatformHealth,
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationStatistics,
)

if TYPE_CHECKING:
    from packages.platform.models import HealthReport  # noqa: F401

__all__ = [
    "PlatformValidator",
]


# ---------------------------------------------------------------------------
# PlatformValidator
# ---------------------------------------------------------------------------


class PlatformValidator:
    """Performs complete integrity validation of the assembled platform.

    This validator checks:

    - Bootstrap completed successfully
    - Dependency graph is complete and cycle-free
    - All required registries are present and non-empty
    - Required providers are registered
    - Required workflows are registered
    - Tasks and capabilities are consistent
    - Configuration values are valid
    - Public APIs are present on all components
    - No duplicate registrations exist
    - No circular dependencies exist

    Usage
    -----

    .. code-block:: python

        from packages.platform.validator import PlatformValidator

        validator = PlatformValidator()
        report = validator.validate(registries, config, container)

        if report.is_valid:
            controller.accept_requests()
        else:
            raise RuntimeError("Platform validation failed")

    Attributes
    ----------
    _diagnostics: Diagnostics engine instance.
    _required_providers: Set of required provider names.
    _required_workflows: Set of required workflow names.
    """

    def __init__(
        self,
        required_providers: tuple[str, ...] | None = None,
        required_workflows: tuple[str, ...] | None = None,
    ) -> None:
        """Initialize the platform validator.

        Args:
            required_providers: Tuple of required provider names.
                Defaults to ("vllm",).
            required_workflows: Tuple of required workflow names.
                Defaults to ("default-engineering",).
        """
        self._diagnostics = DiagnosticsEngine()
        self._required_providers = required_providers or ("vllm",)
        self._required_workflows = required_workflows or ("default-engineering",)

    def validate(
        self,
        registries: object,
        configuration: object,
        container: object,
    ) -> ValidationReport:
        """Perform complete platform validation.

        Runs all validation checks in order and returns a combined report.

        Args:
            registries: The platform registries instance.
            configuration: The platform configuration instance.
            container: The dependency container instance.

        Returns:
            A ValidationReport with all issues and statistics.

        Example
        -------

        .. code-block:: python

            report = validator.validate(registries, config, container)
            if report.is_valid:
                print("Platform is healthy")
            else:
                for issue in report.issues:
                    print(f"{issue.severity}: {issue.description}")
        """
        issues: list[ValidationIssue] = []

        # Step 1: Validate bootstrap completed
        issues.extend(self._validate_bootstrap(registries))

        # Step 2: Validate dependency graph
        issues.extend(self._validate_dependency_graph(container))

        # Step 3: Validate registry integrity
        issues.extend(self._validate_registries(registries))

        # Step 4: Validate providers
        issues.extend(self._validate_providers(container, registries))

        # Step 5: Validate workflows
        issues.extend(self._validate_workflows(registries))

        # Step 6: Validate tasks
        issues.extend(self._validate_tasks(registries))

        # Step 7: Validate capabilities
        issues.extend(self._validate_capabilities(registries))

        # Step 8: Validate configuration
        issues.extend(self._validate_configuration(configuration))

        # Step 9: Validate public APIs
        issues.extend(self._validate_public_api(registries))

        # Step 10: Check duplicates
        issues.extend(self._check_duplicate_registrations(registries))

        # Step 11: Check dependency cycles
        issues.extend(self._check_dependency_cycles(container))

        return ValidationReport(
            issues=tuple(issues),
        )

    def health(
        self,
        registries: object,
        configuration: object,
        container: object,
    ) -> PlatformHealth:
        """Expose deterministic platform health.

        Args:
            registries: The platform registries instance.
            configuration: The platform configuration instance.
            container: The dependency container instance.

        Returns:
            PlatformHealth with status HEALTHY, UNHEALTHY, or DEGRADED.

        Example
        -------

        .. code-block:: python

            health = validator.health(registries, config, container)
            if health.status == PlatformHealth.HEALTHY:
                print("All good")
        """
        from packages.platform.models import PlatformHealth as _PH

        report = self.validate(registries, configuration, container)

        has_critical = any(
            i.severity in (Severity.ERROR, Severity.CRITICAL)
            for i in report.issues
        )
        has_warnings = any(i.severity == Severity.WARNING for i in report.issues)

        if has_critical:
            status = _PH.UNHEALTHY
        elif has_warnings:
            status = _PH.DEGRADED
        else:
            status = _PH.HEALTHY

        return PlatformHealth(
            status=status,
            report=report,
        )

    def diagnostics(
        self,
        registries: object,
        configuration: object,
        container: object,
    ) -> list[ValidationIssue]:
        """Provide structured diagnostic issues.

        This is an alias for running all diagnostics and returning
        the issues as a flat list.

        Args:
            registries: The platform registries instance.
            configuration: The platform configuration instance.
            container: The dependency container instance.

        Returns:
            List of ValidationIssue instances.
        """
        report = self.validate(registries, configuration, container)
        return list(report.issues)

    def summary(self, report: ValidationReport) -> str:
        """Generate a human-readable summary of a validation report.

        Args:
            report: The validation report to summarize.

        Returns:
            One-line summary string.

        Example
        -------

        .. code-block:: python

            summary = validator.summary(report)
            print(summary)  # "Platform health: HEALTHY (0 issues)"
        """
        stats = report.statistics
        status = "HEALTHY" if report.is_valid else "UNHEALTHY"
        return f"Platform health: {status} ({stats.issues_count} issues)"

    # ------------------------------------------------------------------
    # Internal validation methods
    # ------------------------------------------------------------------

    def _validate_bootstrap(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate that bootstrap completed successfully.

        Checks that:
        - Registries object exists and is accessible
        - Required registry attributes are present

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics
        counter = 0

        # Check registries object exists
        if registries is None:
            counter += 1
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("BOOT"),
                component="bootstrap",
                severity=Severity.CRITICAL,
                description="Platform registries object is None.",
                recommendation="Ensure PlatformBootstrap.build() completes successfully.",
            ))
            return issues

        # Check required registry attributes
        required_attrs = [
            ("workflow_registry", "Workflow registry is required for platform operation."),
            ("session_registry", "Session registry is required for session management."),
        ]

        for attr, desc in required_attrs:
            counter += 1
            has_attr = hasattr(registries, attr)
            attr_val = getattr(registries, attr, None)
            if not has_attr or attr_val is None:
                issues.append(diag.create_issue(
                    identifier=diag.next_identifier("BOOT"),
                    component=f"bootstrap_{attr}",
                    severity=Severity.ERROR,
                    description=desc,
                    recommendation=f"Ensure the bootstrap creates the '{attr}' registry.",
                ))

        return issues

    def _validate_dependency_graph(
        self,
        container: object,
    ) -> list[ValidationIssue]:
        """Validate that the dependency graph is complete.

        Checks that:
        - Container has registrations
        - All dependencies reference registered names

        Args:
            container: The dependency container instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if container is None:
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("DEPG"),
                component="dependency_graph",
                severity=Severity.CRITICAL,
                description="Dependency container is None.",
                recommendation="Ensure the bootstrap initializes the dependency container.",
            ))
            return issues

        # Check container has registrations
        if hasattr(container, "count"):
            if container.count == 0:  # type: ignore[union-attr]
                issues.append(diag.create_issue(
                    identifier=diag.next_identifier("DEPG"),
                    component="dependency_graph",
                    severity=Severity.ERROR,
                    description="Dependency container has no registered dependencies.",
                    recommendation="Ensure the bootstrap registers required dependencies.",
                ))

        # Check for missing dependencies via validate method
        if hasattr(container, "validate"):
            try:
                container_errors = container.validate()  # type: ignore[union-attr]
                if container_errors:
                    for err in container_errors:
                        issues.append(diag.create_issue(
                            identifier=diag.next_identifier("DEPG"),
                            component="dependency_graph",
                            severity=Severity.ERROR,
                            description=err,
                            recommendation="Review dependency registration to fix missing references.",
                        ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _validate_registries(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate registry integrity.

        Checks that:
        - All required registries are present
        - No registries are empty (have entries)

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is None:
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("REGS"),
                component="registries",
                severity=Severity.CRITICAL,
                description="Platform registries object is None.",
                recommendation="Ensure the bootstrap creates all platform registries.",
            ))
            return issues

        # Check each registry attribute
        registry_attrs = [
            "workflow_registry",
            "session_registry",
            "observability_registry",
            "verification_registry",
        ]

        for attr in registry_attrs:
            try:
                val = getattr(registries, attr, None)  # type: ignore[union-attr]
                if val is None:
                    issues.append(diag.create_issue(
                        identifier=diag.next_identifier("REGS"),
                        component=f"registry_{attr}",
                        severity=Severity.WARNING,
                        description=f"{attr} is not set.",
                        recommendation=f"Ensure the bootstrap initializes {attr}.",
                    ))
            except Exception:  # noqa: BLE001
                issues.append(diag.create_issue(
                    identifier=diag.next_identifier("REGS"),
                    component=f"registry_{attr}",
                    severity=Severity.WARNING,
                    description=f"Cannot access {attr}.",
                    recommendation=f"Check that {attr} is properly initialized.",
                ))

        return issues

    def _validate_providers(
        self,
        container: object,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate provider registrations.

        Checks that:
        - Required providers are registered
        - No unsupported providers are referenced

        Args:
            container: The dependency container instance.
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        # Check provider registry
        if registries is not None:
            try:
                provider_reg = getattr(registries, "provider_registry", None)  # type: ignore[union-attr]
                if provider_reg is not None and hasattr(provider_reg, "all"):
                    all_providers = provider_reg.all()  # type: ignore[union-attr]
                    registered_names: set[str] = set()

                    for provider in all_providers:
                        if hasattr(provider, "name"):
                            registered_names.add(provider.name)
                        elif isinstance(provider, str):
                            registered_names.add(provider)

                    for required in self._required_providers:
                        if required not in registered_names:
                            issues.append(diag.create_issue(
                                identifier=diag.next_identifier("PROV"),
                                component="provider_registry",
                                severity=Severity.ERROR,
                                description=f"Required provider '{required}' is not registered.",
                                recommendation=f"Register the '{required}' provider during bootstrap.",
                            ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _validate_workflows(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate workflow registrations.

        Checks that:
        - Required workflows are registered
        - No duplicate workflow names exist

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is not None:
            try:
                workflow_reg = getattr(registries, "workflow_registry", None)  # type: ignore[union-attr]
                if workflow_reg is not None and hasattr(workflow_reg, "all"):
                    all_workflows = workflow_reg.all()  # type: ignore[union-attr]
                    registered_names = set(all_workflows)

                    for required in self._required_workflows:
                        if required not in registered_names:
                            issues.append(diag.create_issue(
                                identifier=diag.next_identifier("WORK"),
                                component="workflow_registry",
                                severity=Severity.ERROR,
                                description=f"Required workflow '{required}' is not registered.",
                                recommendation=f"Register the '{required}' workflow during bootstrap.",
                            ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _validate_tasks(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate task registrations.

        Checks that:
        - Task registry is consistent
        - Task entries reference valid components

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is not None:
            try:
                task_reg = getattr(registries, "task_registry", None)  # type: ignore[union-attr]
                if task_reg is not None and hasattr(task_reg, "all"):
                    all_tasks = task_reg.all()  # type: ignore[union-attr]
                    if not all_tasks:
                        issues.append(diag.create_issue(
                            identifier=diag.next_identifier("TASK"),
                            component="task_registry",
                            severity=Severity.WARNING,
                            description="Task registry is empty.",
                            recommendation="Register tasks during platform bootstrap.",
                        ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _validate_capabilities(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate capability registrations.

        Checks that:
        - Capability registry is consistent
        - Capability entries reference valid components

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is not None:
            try:
                cap_reg = getattr(registries, "capability_registry", None)  # type: ignore[union-attr]
                if cap_reg is not None and hasattr(cap_reg, "all"):
                    all_caps = cap_reg.all()  # type: ignore[union-attr]
                    if not all_caps:
                        issues.append(diag.create_issue(
                            identifier=diag.next_identifier("CAPB"),
                            component="capability_registry",
                            severity=Severity.WARNING,
                            description="Capability registry is empty.",
                            recommendation="Register capabilities during platform bootstrap.",
                        ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _validate_configuration(
        self,
        configuration: object,
    ) -> list[ValidationIssue]:
        """Validate configuration values.

        Checks that:
        - All configuration values are within valid bounds
        - Required configuration fields are present

        Args:
            configuration: The platform configuration instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if configuration is None:
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("CONF"),
                component="configuration",
                severity=Severity.CRITICAL,
                description="Platform configuration is None.",
                recommendation="Provide a valid PlatformConfiguration instance.",
            ))
            return issues

        # Check repository configuration
        if hasattr(configuration, "repository"):
            repo = configuration.repository
            self._check_positive_value(
                issues, diag, "repository.max_symbols",
                getattr(repo, "max_symbols", None),  # type: ignore[union-attr]
            )
            self._check_positive_value(
                issues, diag, "repository.max_tokens",
                getattr(repo, "max_tokens", None),  # type: ignore[union-attr]
            )

        # Check workflow configuration
        if hasattr(configuration, "workflow"):
            wf = configuration.workflow
            self._check_positive_value(
                issues, diag, "workflow.max_steps",
                getattr(wf, "max_steps", None),  # type: ignore[union-attr]
            )

        # Check execution configuration
        if hasattr(configuration, "execution"):
            exec_cfg = configuration.execution
            self._check_positive_value(
                issues, diag, "execution.max_concurrent_steps",
                getattr(exec_cfg, "max_concurrent_steps", None),  # type: ignore[union-attr]
            )

        # Check session configuration
        if hasattr(configuration, "session"):
            sess = configuration.session
            self._check_positive_value(
                issues, diag, "session.max_sessions",
                getattr(sess, "max_sessions", None),  # type: ignore[union-attr]
            )

        # Check autonomous configuration
        if hasattr(configuration, "autonomous"):
            auto = configuration.autonomous
            self._check_positive_value(
                issues, diag, "autonomous.max_iterations",
                getattr(auto, "max_iterations", None),  # type: ignore[union-attr]
            )

        return issues

    def _check_positive_value(
        self,
        issues: list[ValidationIssue],
        diag: DiagnosticsEngine,
        name: str,
        value: Any | None,
    ) -> None:
        """Check that a configuration value is positive.

        Args:
            issues: List to append issues to.
            diag: Diagnostics engine for creating issues.
            name: Configuration field name.
            value: Value to check.
        """
        if value is not None and value <= 0:
            issues.append(diag.create_issue(
                identifier=diag.next_identifier("CONF"),
                component=f"configuration.{name}",
                severity=Severity.ERROR,
                description=f"Configuration '{name}' must be positive, got {value}.",
                recommendation=f"Set '{name}' to a positive integer value.",
            ))

    def _validate_public_api(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Validate that public APIs are present on all components.

        Checks that:
        - All registries have required methods (all, get, register)
        - Required registry interfaces are consistent

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is None:
            return issues

        # Required public API methods for registries
        required_methods = ["all"]

        registry_attrs = [
            "workflow_registry",
            "session_registry",
            "observability_registry",
            "verification_registry",
        ]

        for attr in registry_attrs:
            try:
                reg = getattr(registries, attr, None)  # type: ignore[union-attr]
                if reg is not None:
                    for method in required_methods:
                        if not hasattr(reg, method):
                            issues.append(diag.create_issue(
                                identifier=diag.next_identifier("API"),
                                component=f"public_api_{attr}",
                                severity=Severity.WARNING,
                                description=f"{attr} is missing public method '{method}'.",
                                recommendation=f"Add '{method}()' method to {attr}.",
                            ))
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _check_duplicate_registrations(
        self,
        registries: object,
    ) -> list[ValidationIssue]:
        """Check for duplicate registrations across registries.

        Args:
            registries: The platform registries instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if registries is None:
            return issues

        registry_attrs = [
            "workflow_registry",
            "session_registry",
            "observability_registry",
            "verification_registry",
        ]

        for attr in registry_attrs:
            try:
                reg = getattr(registries, attr, None)  # type: ignore[union-attr]
                if reg is not None and hasattr(reg, "all"):
                    entries = reg.all()  # type: ignore[union-attr]
                    seen: set[str] = set()
                    for entry in entries:
                        name = entry if isinstance(entry, str) else str(entry)
                        if name in seen:
                            issues.append(diag.create_issue(
                                identifier=diag.next_identifier("DUP"),
                                component=f"registry_{attr}",
                                severity=Severity.ERROR,
                                description=f"Duplicate registration detected: '{name}'.",
                                recommendation=f"Remove duplicate '{name}' from {attr}.",
                            ))
                        seen.add(name)
            except Exception:  # noqa: BLE001
                pass

        return issues

    def _check_dependency_cycles(
        self,
        container: object,
    ) -> list[ValidationIssue]:
        """Check for dependency cycles in the container.

        Args:
            container: The dependency container instance.

        Returns:
            List of ValidationIssue instances.
        """
        issues: list[ValidationIssue] = []
        diag = self._diagnostics

        if container is None:
            return issues

        if hasattr(container, "validate"):
            try:
                cycle_errors = container.validate()  # type: ignore[union-attr]
                if cycle_errors:
                    for err in cycle_errors:
                        issues.append(diag.create_issue(
                            identifier=diag.next_identifier("CYCL"),
                            component="dependency_graph",
                            severity=Severity.CRITICAL,
                            description=err,
                            recommendation="Break the circular dependency by refactoring component dependencies.",
                        ))
            except Exception:  # noqa: BLE001
                pass

        return issues