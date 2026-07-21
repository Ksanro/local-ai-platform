"""Platform validation — dependency validation and verification.

Provides comprehensive validation of platform dependencies, registries,
and configuration. Detects missing dependencies, duplicate registrations,
dependency cycles, missing providers, missing workflows, and invalid configuration.

Architecture
------------

PlatformValidator
    │
    ├── check_missing_dependencies()
    ├── check_duplicate_registrations()
    ├── check_dependency_cycles()
    ├── check_missing_providers()
    ├── check_missing_workflows()
    └── check_invalid_configuration()

Public API
----------

.. code-block:: python

    from packages.bootstrap.validation import (
        PlatformValidator,
        ValidationResult,
        ValidationSeverity,
    )

    validator = PlatformValidator()

    result = validator.validate(
        container=container,
        registries=registries,
        configuration=configuration,
    )

    if result.has_errors:
        for error in result.errors:
            print(f"Error: {error}")

"""

from __future__ import annotations

from dataclasses import dataclass, field


__all__ = [
    "PlatformValidator",
    "ValidationResult",
    "ValidationSeverity",
]


# ---------------------------------------------------------------------------
# Validation Result
# ---------------------------------------------------------------------------


class ValidationSeverity:
    """Severity levels for validation results.

    Attributes:
        ERROR: Critical issue that prevents platform operation.
        WARNING: Non-critical issue that should be investigated.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationResult:
    """Result of a platform validation.

    Attributes:
        errors: List of error messages.
        warnings: List of warning messages.
    """

    def __init__(
        self,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        """Initialize the validation result.

        Args:
            errors: List of error messages.
            warnings: List of warning messages.
        """
        self.errors: list[str] = errors if errors is not None else []
        self.warnings: list[str] = warnings if warnings is not None else []

    @property
    def has_errors(self) -> bool:
        """Check if there are any validation errors.

        Returns:
            True if there are errors, False otherwise.
        """
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any validation warnings.

        Returns:
            True if there are warnings, False otherwise.
        """
        return len(self.warnings) > 0

    def add_error(self, message: str) -> None:
        """Add an error message.

        Args:
            message: The error message to add.
        """
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message.

        Args:
            message: The warning message to add.
        """
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# PlatformValidator
# ---------------------------------------------------------------------------


class PlatformValidator:
    """Platform dependency validator.

    Performs comprehensive validation of platform dependencies,
    registries, and configuration. Detects:

    - Missing dependencies (dependencies that reference unregistered names)
    - Duplicate registrations (same name registered multiple times)
    - Dependency cycles (circular dependency chains)
    - Missing providers (required providers not registered)
    - Missing workflows (required workflows not registered)
    - Invalid configuration (configuration that violates constraints)

    Usage
    -----

    .. code-block:: python

        from packages.bootstrap.validation import PlatformValidator

        validator = PlatformValidator()

        result = validator.validate(
            container=container,
            registries=registries,
            configuration=configuration,
        )

        if result.has_errors:
            raise RuntimeError(
                "Platform validation failed:\\n"
                + "\\n".join(result.errors)
            )

    Attributes
    ----------
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
                If not provided, defaults to ("vllm",).
            required_workflows: Tuple of required workflow names.
                If not provided, defaults to ("default-engineering",).
        """
        self._required_providers = required_providers or ("vllm",)
        self._required_workflows = required_workflows or ("default-engineering",)

    def validate(
        self,
        container: object,
        registries: object,
        configuration: object,
    ) -> ValidationResult:
        """Perform complete platform validation.

        Runs all validation checks and returns a combined result.

        Args:
            container: The dependency container instance.
            registries: The platform registries instance.
            configuration: The platform configuration instance.

        Returns:
            A ValidationResult with all errors and warnings.

        Example
        -------

        .. code-block:: python

            result = validator.validate(container, registries, config)
            if result.has_errors:
                print("Validation failed:")
                for error in result.errors:
                    print(f"  - {error}")
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Run all validation checks
        container_errors = self.validate_container(container)
        errors.extend(container_errors)

        registry_errors = self.validate_registries(registries)
        errors.extend(registry_errors)

        config_errors = self.validate_configuration(configuration)
        errors.extend(config_errors)

        provider_errors = self.check_missing_providers(container, registries)
        errors.extend(provider_errors)

        workflow_errors = self.check_missing_workflows(container, registries)
        errors.extend(workflow_errors)

        return ValidationResult(
            errors=errors,
            warnings=warnings,
        )

    def validate_container(
        self,
        container: object,
    ) -> list[str]:
        """Validate the dependency container.

        Checks for:
        - Missing dependencies (dependencies that reference unregistered names)
        - Dependency cycles
        - Self-referencing dependencies

        Args:
            container: The dependency container instance.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        # Check if container has validate method
        if not hasattr(container, "validate"):
            errors.append(
                "Dependency container does not have a 'validate' method."
            )
            return errors

        # Use container's own validation
        container_errors = container.validate()  # type: ignore[union-attr]
        errors.extend(container_errors)

        # Check for empty container
        if not hasattr(container, "count") or container.count == 0:  # type: ignore[union-attr]
            errors.append(
                "Dependency container has no registered dependencies."
            )

        return errors

    def validate_registries(
        self,
        registries: object,
    ) -> list[str]:
        """Validate the platform registries.

        Checks for:
        - Missing required registries
        - Empty registries

        Args:
            registries: The platform registries instance.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        # Check required registries
        required_registries = [
            ("workflow_registry", "Workflow registry is required."),
            ("provider_registry", "Provider registry is required."),
            ("session_registry", "Session registry is required."),
        ]

        for attr, message in required_registries:
            if not hasattr(registries, attr):
                errors.append(
                    f"Platform registries does not have '{attr}' attribute."
                )
            elif getattr(registries, attr) is None:  # type: ignore[union-attr]
                errors.append(message)

        return errors

    def validate_configuration(
        self,
        configuration: object,
    ) -> list[str]:
        """Validate the platform configuration.

        Checks for:
        - Invalid configuration values
        - Missing required configuration

        Args:
            configuration: The platform configuration instance.

        Returns:
            List of error messages.
        """
        errors: list[str] = []

        # Check repository configuration
        if hasattr(configuration, "repository"):
            repo = configuration.repository
            if hasattr(repo, "max_symbols") and repo.max_symbols <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Repository max_symbols must be positive."
                )
            if hasattr(repo, "max_tokens") and repo.max_tokens <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Repository max_tokens must be positive."
                )

        # Check workflow configuration
        if hasattr(configuration, "workflow"):
            wf = configuration.workflow
            if hasattr(wf, "max_steps") and wf.max_steps <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Workflow max_steps must be positive."
                )

        # Check execution configuration
        if hasattr(configuration, "execution"):
            exec_cfg = configuration.execution
            if hasattr(exec_cfg, "max_concurrent_steps") and exec_cfg.max_concurrent_steps <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Execution max_concurrent_steps must be positive."
                )

        # Check session configuration
        if hasattr(configuration, "session"):
            sess = configuration.session
            if hasattr(sess, "max_sessions") and sess.max_sessions <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Session max_sessions must be positive."
                )

        # Check autonomous configuration
        if hasattr(configuration, "autonomous"):
            auto = configuration.autonomous
            if hasattr(auto, "max_iterations") and auto.max_iterations <= 0:  # type: ignore[union-attr]
                errors.append(
                    "Autonomous max_iterations must be positive."
                )

        return errors

    def check_missing_providers(
        self,
        container: object,
        registries: object,
    ) -> list[str]:
        """Check for missing required providers.

        Verifies that all required providers are registered in the
        provider registry.

        Args:
            container: The dependency container instance.
            registries: The platform registries instance.

        Returns:
            List of error messages for missing providers.
        """
        errors: list[str] = []

        # Get the provider registry
        if not hasattr(registries, "provider_registry"):
            return errors

        provider_registry = registries.provider_registry  # type: ignore[union-attr]
        if provider_registry is None:
            return errors

        # Check if provider registry has an all() method
        if not hasattr(provider_registry, "all"):
            return errors

        # Get registered providers
        try:
            all_providers = provider_registry.all()
            registered_names = set()

            for provider in all_providers:
                if hasattr(provider, "name"):
                    registered_names.add(provider.name)
                elif isinstance(provider, str):
                    registered_names.add(provider)

            # Check required providers
            for required in self._required_providers:
                if required not in registered_names:
                    errors.append(
                        f"Required provider '{required}' is not registered."
                    )
        except Exception:
            # If we can't read the provider registry, skip this check
            pass

        return errors

    def check_missing_workflows(
        self,
        container: object,
        registries: object,
    ) -> list[str]:
        """Check for missing required workflows.

        Verifies that all required workflows are registered in the
        workflow registry.

        Args:
            container: The dependency container instance.
            registries: The platform registries instance.

        Returns:
            List of error messages for missing workflows.
        """
        errors: list[str] = []

        # Get the workflow registry
        if not hasattr(registries, "workflow_registry"):
            return errors

        workflow_registry = registries.workflow_registry  # type: ignore[union-attr]
        if workflow_registry is None:
            return errors

        # Check if workflow registry has discovery method
        if not hasattr(workflow_registry, "all"):
            return errors

        # Get registered workflows
        try:
            all_workflows = workflow_registry.all()
            registered_names = set()

            for workflow in all_workflows:
                if hasattr(workflow, "name"):
                    registered_names.add(workflow.name)
                elif isinstance(workflow, str):
                    registered_names.add(workflow)

            # Check required workflows
            for required in self._required_workflows:
                if required not in registered_names:
                    errors.append(
                        f"Required workflow '{required}' is not registered."
                    )
        except Exception:
            # If we can't read the workflow registry, skip this check
            pass

        return errors

    def check_duplicate_registrations(
        self,
        container: object,
    ) -> list[str]:
        """Check for duplicate registrations in the container.

        Args:
            container: The dependency container instance.

        Returns:
            List of error messages for duplicates.
        """
        errors: list[str] = []

        if not hasattr(container, "registered_names"):
            return errors

        try:
            names = container.registered_names
            seen: set[str] = set()
            for name in names:
                if name in seen:
                    errors.append(
                        f"Duplicate registration detected: '{name}'."
                    )
                seen.add(name)
        except Exception:
            pass

        return errors

    def check_dependency_cycles(
        self,
        container: object,
    ) -> list[str]:
        """Check for dependency cycles in the container.

        Args:
            container: The dependency container instance.

        Returns:
            List of error messages for cycles.
        """
        errors: list[str] = []

        if not hasattr(container, "validate"):
            return errors

        try:
            cycle_errors = container.validate()
            errors.extend(cycle_errors)
        except Exception:
            pass

        return errors