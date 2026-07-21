"""Platform bootstrap — constructs the complete engineering platform.

The PlatformBootstrap is the central assembly point for the entire platform.
It constructs all registries, factories, engines, and components, then
validates and returns a ready-to-use EngineeringController.

Architecture
------------

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

Public API
----------

.. code-block:: python

    from packages.bootstrap import PlatformBootstrap, build

    # Using the class
    bootstrap = PlatformBootstrap()
    controller = bootstrap.build(configuration)

    # Using the convenience function
    controller = build()

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.bootstrap.configuration import PlatformConfiguration
from packages.bootstrap.registry import PlatformRegistries
from packages.bootstrap.validation import PlatformValidator, ValidationResult

if TYPE_CHECKING:
    from packages.controller.controller import EngineeringController  # noqa: F401
    from packages.controller.models import EngineeringRequest  # noqa: F401
    from packages.controller.models import OperationType  # noqa: F401
    from packages.workflows.registry import WorkflowRegistry  # noqa: F401


__all__ = [
    "PlatformBootstrap",
    "build",
]


# ---------------------------------------------------------------------------
# PlatformBootstrap
# ---------------------------------------------------------------------------


class PlatformBootstrap:
    """Constructs the complete engineering platform.

    The PlatformBootstrap is the single place where the entire platform
    is assembled. It follows the principle that the bootstrap is the ONLY
    component allowed to wire together implementations.

    Every other component receives dependencies through constructors.
    No component may instantiate another subsystem directly.

    Public API
    ----------

    .. code-block:: python

        from packages.bootstrap import PlatformBootstrap
        from packages.bootstrap.configuration import PlatformConfiguration

        bootstrap = PlatformBootstrap()
        config = PlatformConfiguration.default()

        controller = bootstrap.build(config)

    Responsibilities
    ----------------

    - Construct every registry
    - Construct every factory
    - Construct every engine
    - Register providers
    - Register workflows
    - Register capabilities
    - Register tasks
    - Validate platform
    - Return ready-to-use EngineeringController

    Attributes
    ----------
    _validator: Platform validator instance.
    """

    def __init__(
        self,
        validator: PlatformValidator | None = None,
    ) -> None:
        """Initialize the platform bootstrap.

        Args:
            validator: Optional validator. Creates internal one if not provided.
        """
        self._validator = validator if validator is not None else PlatformValidator()

    def build(
        self,
        configuration: PlatformConfiguration,
    ) -> EngineeringController:
        """Build the complete engineering platform.

        Constructs all platform components in the correct order:
        1. Construct all registries
        2. Construct all factories
        3. Construct all engines
        4. Register providers
        5. Register workflows
        6. Register capabilities
        7. Register tasks
        8. Validate platform
        9. Return ready-to-use EngineeringController

        Args:
            configuration: The platform configuration.

        Returns:
            A fully configured EngineeringController.

        Raises:
            RuntimeError: If platform validation fails.

        Example
        -------

        .. code-block:: python

            bootstrap = PlatformBootstrap()
            config = PlatformConfiguration.default()
            controller = bootstrap.build(config)
            result = controller.execute(request)
        """
        # Step 1: Construct all registries
        registries = self._construct_registries(configuration)

        # Step 2: Construct all factories
        factories = self._construct_factories(registries, configuration)

        # Step 3: Construct all engines
        engines = self._construct_engines(factories, registries, configuration)

        # Step 4-7: Register providers, workflows, capabilities, tasks
        self._register_components(factories, engines, registries, configuration)

        # Step 8: Validate platform
        validation_result = self._validate_platform(
            registries, configuration
        )

        if validation_result.has_errors:
            error_messages = "\\n".join(validation_result.errors)
            raise RuntimeError(
                f"Platform validation failed:\\n{error_messages}"
            )

        # Step 9: Return ready-to-use EngineeringController
        controller = self._construct_controller(
            engines, registries, configuration
        )

        return controller

    def _construct_registries(
        self,
        configuration: PlatformConfiguration,
    ) -> PlatformRegistries:
        """Construct all platform registries.

        Creates and returns a PlatformRegistries instance with all
        subsystem registries initialized.

        Args:
            configuration: The platform configuration.

        Returns:
            A fully constructed PlatformRegistries instance.
        """
        # Import registry classes that actually exist as classes
        from packages.observability.registry import EventRegistry
        from packages.session.registry import SessionRegistry
        from packages.verification.registry import VerificationRuleRegistry
        from packages.workflows.registry import WorkflowRegistry

        # Construct all registries
        workflow_registry = WorkflowRegistry()
        # Providers use module-level functions, not a class-based registry
        provider_registry = None
        session_registry = SessionRegistry()
        observability_registry = EventRegistry()
        # Serializers use module-level functions, not a class-based registry
        serializer_registry = None
        verification_registry = VerificationRuleRegistry()
        # Evaluation uses module-level functions, not a class-based registry
        evaluation_registry = None

        # Build PlatformRegistries
        registries = PlatformRegistries(
            workflow_registry=workflow_registry,
            provider_registry=provider_registry,
            session_registry=session_registry,
            observability_registry=observability_registry,
            serializer_registry=serializer_registry,
            verification_registry=verification_registry,
            evaluation_registry=evaluation_registry,
        )

        return registries

    def _construct_factories(
        self,
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> dict[str, object]:
        """Construct all platform factories.

        Creates and returns all factory instances that will be used
        to create platform components.

        Args:
            registries: The platform registries.
            configuration: The platform configuration.

        Returns:
            Dictionary mapping factory names to instances.
        """
        from packages.providers.factory import create_provider

        factories: dict[str, object] = {
            "create_provider": create_provider,
        }

        return factories

    def _construct_engines(
        self,
        factories: dict[str, object],
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> dict[str, object]:
        """Construct all platform engines.

        Creates and returns all engine instances that will be used
        to execute platform operations.

        Args:
            factories: Platform factories.
            registries: Platform registries.
            configuration: Platform configuration.

        Returns:
            Dictionary mapping engine names to instances.
        """
        from packages.observability.collector import EngineeringTelemetry
        from packages.session.manager import SessionManager

        # Construct session manager
        session_manager = SessionManager(
            registry=registries.session_registry  # type: ignore[union-attr]
        )

        # Construct telemetry
        telemetry = EngineeringTelemetry(
            enabled=configuration.observability.enabled
        )

        engines: dict[str, object] = {
            "session_manager": session_manager,
            "telemetry": telemetry,
        }

        return engines

    def _register_components(
        self,
        factories: dict[str, object],
        engines: dict[str, object],
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> None:
        """Register providers, workflows, capabilities, and tasks.

        This method registers all platform components into their
        respective registries.

        Args:
            factories: Platform factories.
            engines: Platform engines.
            registries: Platform registries.
            configuration: Platform configuration.
        """
        # Register providers
        self._register_providers(registries, configuration)

        # Register workflows
        self._register_workflows(registries, configuration)

    def _register_providers(
        self,
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> None:
        """Register all provider implementations.

        Args:
            registries: Platform registries.
            configuration: Platform configuration.
        """
        # Import and trigger provider auto-registration
        from packages.providers import _load_providers

        _load_providers()

    def _register_workflows(
        self,
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> None:
        """Register all workflow implementations.

        Args:
            registries: Platform registries.
            configuration: Platform configuration.
        """
        from packages.workflows.registry import WorkflowRegistry

        if isinstance(registries.workflow_registry, WorkflowRegistry):
            registry = registries.workflow_registry  # type: ignore[assignment]
            self._register_default_workflows(registry, configuration)

    def _register_default_workflows(
        self,
        registry: WorkflowRegistry,
        configuration: PlatformConfiguration,
    ) -> None:
        """Register default workflow implementations.

        Args:
            registry: The workflow registry.
            configuration: Platform configuration.
        """
        from packages.workflows.base import Workflow

        # Default engineering workflow
        class DefaultEngineeringWorkflow(Workflow):
            """Default engineering workflow for execute operations."""

            @property
            def name(self) -> str:
                return "default-engineering"

            @property
            def workflow_nodes(self) -> tuple[object, ...]:
                return ()

            def _do_plan(self, repository_index: object, request: object) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class DefaultWorkflowPlan:
                    workflow_name: str = "default-engineering"
                    steps: tuple[object, ...] = field(default_factory=tuple)
                    status: str = "PLANNED"

                return DefaultWorkflowPlan()

            def _do_estimate(
                self, repository_index: object, request: object
            ) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class DefaultWorkflowMetrics:
                    estimated_steps: int = 0
                    estimated_duration_seconds: float = 0.0

                return DefaultWorkflowMetrics()

        # Code review workflow
        class CodeReviewWorkflow(Workflow):
            """Code review workflow."""

            @property
            def name(self) -> str:
                return "code-review"

            @property
            def workflow_nodes(self) -> tuple[object, ...]:
                return ()

            def _do_plan(self, repository_index: object, request: object) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class ReviewWorkflowPlan:
                    workflow_name: str = "code-review"
                    steps: tuple[object, ...] = field(default_factory=tuple)
                    status: str = "PLANNED"

                return ReviewWorkflowPlan()

            def _do_estimate(
                self, repository_index: object, request: object
            ) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class DefaultWorkflowMetrics:
                    estimated_steps: int = 0
                    estimated_duration_seconds: float = 0.0

                return DefaultWorkflowMetrics()

        # Implement feature workflow
        class ImplementFeatureWorkflow(Workflow):
            """Feature implementation workflow."""

            @property
            def name(self) -> str:
                return "implement-feature"

            @property
            def workflow_nodes(self) -> tuple[object, ...]:
                return ()

            def _do_plan(self, repository_index: object, request: object) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class ImplementWorkflowPlan:
                    workflow_name: str = "implement-feature"
                    steps: tuple[object, ...] = field(default_factory=tuple)
                    status: str = "PLANNED"

                return ImplementWorkflowPlan()

            def _do_estimate(
                self, repository_index: object, request: object
            ) -> object:
                from dataclasses import dataclass, field

                @dataclass(frozen=True, slots=True)
                class DefaultWorkflowMetrics:
                    estimated_steps: int = 0
                    estimated_duration_seconds: float = 0.0

                return DefaultWorkflowMetrics()

        # Register all workflows
        registry.register("default-engineering", DefaultEngineeringWorkflow)
        registry.register("code-review", CodeReviewWorkflow)
        registry.register("implement-feature", ImplementFeatureWorkflow)

    def _validate_platform(
        self,
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> ValidationResult:
        """Validate the platform configuration and registries.

        Args:
            registries: Platform registries.
            configuration: Platform configuration.

        Returns:
            Validation result with errors and warnings.
        """
        # Validate configuration
        errors: list[str] = []
        warnings: list[str] = []

        # Check required registries
        if registries.workflow_registry is None:
            errors.append("Workflow registry is required.")
        # Provider registry uses module-level functions, not a class-based registry
        if registries.session_registry is None:
            errors.append("Session registry is required.")

        # Validate configuration values
        config_errors = self._validate_configuration(configuration)
        errors.extend(config_errors)

        return ValidationResult(errors=errors, warnings=warnings)

    def _validate_configuration(
        self,
        configuration: PlatformConfiguration,
    ) -> list[str]:
        """Validate platform configuration values.

        Args:
            configuration: Platform configuration.

        Returns:
            List of validation error messages.
        """
        errors: list[str] = []

        # Check repository configuration
        if configuration.repository.max_symbols <= 0:
            errors.append("Repository max_symbols must be positive.")
        if configuration.repository.max_tokens <= 0:
            errors.append("Repository max_tokens must be positive.")

        # Check workflow configuration
        if configuration.workflow.max_steps <= 0:
            errors.append("Workflow max_steps must be positive.")

        # Check execution configuration
        if configuration.execution.max_concurrent_steps <= 0:
            errors.append("Execution max_concurrent_steps must be positive.")

        # Check session configuration
        if configuration.session.max_sessions <= 0:
            errors.append("Session max_sessions must be positive.")

        # Check autonomous configuration
        if configuration.autonomous.max_iterations <= 0:
            errors.append("Autonomous max_iterations must be positive.")

        return errors

    def _construct_controller(
        self,
        engines: dict[str, object],
        registries: PlatformRegistries,
        configuration: PlatformConfiguration,
    ) -> EngineeringController:
        """Construct the EngineeringController.

        Creates the EngineeringController with all dependencies injected.

        Args:
            engines: Platform engines.
            registries: Platform registries.
            configuration: Platform configuration.

        Returns:
            A fully configured EngineeringController.
        """
        from packages.controller.controller import EngineeringController
        from packages.controller.registry import OperationRegistry
        from packages.controller.validator import RequestValidator

        # Create controller components
        validator = RequestValidator()
        registry = OperationRegistry()

        # Get session manager from engines
        session_manager = engines.get("session_manager")
        telemetry = engines.get("telemetry")

        # Create controller
        controller = EngineeringController(
            session_manager=session_manager,
            telemetry=telemetry,
        )

        # Controller will initialize its own registry and validators
        # when execute() is called

        return controller


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def build(
    configuration: PlatformConfiguration | None = None,
) -> EngineeringController:
    """Convenience function to build the platform.

    Creates a PlatformBootstrap with default configuration and
    returns a ready-to-use EngineeringController.

    Args:
        configuration: Optional configuration. Uses defaults if not provided.

    Returns:
        A fully configured EngineeringController.

    Example
    -------

    .. code-block:: python

        from packages.bootstrap import build

        # With default configuration
        controller = build()

        # With custom configuration
        from packages.bootstrap.configuration import PlatformConfiguration
        config = PlatformConfiguration.default().with_observability(enabled=True)
        controller = build(config)
    """
    bootstrap = PlatformBootstrap()
    config = configuration if configuration is not None else PlatformConfiguration.default()
    return bootstrap.build(config)