"""Platform registries — aggregated registry container.

Provides a frozen container that holds references to all subsystem registries.
This is the single source of truth for registry access during platform construction.

Architecture
------------

PlatformRegistries
    │
    ├── workflow_registry: WorkflowRegistry
    ├── execution_registry: ExecutionRegistry
    ├── verification_registry: VerificationRuleRegistry
    ├── session_registry: SessionRegistry
    ├── observability_registry: EventRegistry
    ├── provider_registry: ProviderRegistry
    ├── serializer_registry: SerializerRegistry
    ├── capability_registry: CapabilityRegistry
    └── task_registry: TaskRegistry

Public API
----------

.. code-block:: python

    from packages.bootstrap.registry import PlatformRegistries

    registries = PlatformRegistries(
        workflow_registry=WorkflowRegistry(),
        verification_registry=VerificationRuleRegistry(),
        session_registry=SessionRegistry(),
        observability_registry=EventRegistry(),
        provider_registry=ProviderRegistry(),
        serializer_registry=SerializerRegistry(),
        capability_registry=CapabilityRegistry(),
        task_registry=TaskRegistry(),
    )

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.evaluation.registry import MetricRegistry  # noqa: F401
    from packages.observability.registry import EventRegistry  # noqa: F401
    from packages.providers.registry import ProviderRegistry  # noqa: F401
    from packages.serializers.registry import SerializerRegistry  # noqa: F401
    from packages.session.registry import SessionRegistry  # noqa: F401
    from packages.verification.registry import VerificationRuleRegistry  # noqa: F401
    from packages.workflows.registry import WorkflowRegistry  # noqa: F401


__all__ = [
    "PlatformRegistries",
]


# ---------------------------------------------------------------------------
# PlatformRegistries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformRegistries:
    """Aggregated container for all platform registries.

    This is an immutable container that holds references to all subsystem
    registries. It provides a single entry point for accessing any registry
    during platform construction and execution.

    All fields are optional (defaulting to None) to allow incremental
    construction. The ``ensure_complete()`` method can validate that all
    required registries are present.

    Attributes:
        workflow_registry: Workflow orchestration registry.
        execution_registry: Execution step registry.
        verification_registry: Verification rule registry.
        session_registry: Engineering session registry.
        observability_registry: Telemetry event registry.
        provider_registry: LLM provider registry.
        serializer_registry: Serialization layer registry.
        capability_registry: Capability registry.
        task_registry: Task registry.
        evaluation_registry: Evaluation metric registry.

    Usage
    -----

    .. code-block:: python

        from packages.bootstrap.registry import PlatformRegistries
        from packages.workflows.registry import WorkflowRegistry

        # Minimal construction
        registries = PlatformRegistries(
            workflow_registry=WorkflowRegistry(),
        )

        # Access registries
        workflow = registries.workflow_registry
    """

    workflow_registry: object | None = None
    execution_registry: object | None = None
    verification_registry: object | None = None
    session_registry: object | None = None
    observability_registry: object | None = None
    provider_registry: object | None = None
    serializer_registry: object | None = None
    capability_registry: object | None = None
    task_registry: object | None = None
    evaluation_registry: object | None = None

    def with_workflow_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the workflow registry set.

        Args:
            registry: The workflow registry instance.

        Returns:
            A new PlatformRegistries with the workflow registry set.
        """
        return PlatformRegistries(
            workflow_registry=registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_execution_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the execution registry set.

        Args:
            registry: The execution registry instance.

        Returns:
            A new PlatformRegistries with the execution registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_verification_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the verification registry set.

        Args:
            registry: The verification registry instance.

        Returns:
            A new PlatformRegistries with the verification registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_session_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the session registry set.

        Args:
            registry: The session registry instance.

        Returns:
            A new PlatformRegistries with the session registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_observability_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the observability registry set.

        Args:
            registry: The observability registry instance.

        Returns:
            A new PlatformRegistries with the observability registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_provider_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the provider registry set.

        Args:
            registry: The provider registry instance.

        Returns:
            A new PlatformRegistries with the provider registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_serializer_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the serializer registry set.

        Args:
            registry: The serializer registry instance.

        Returns:
            A new PlatformRegistries with the serializer registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_capability_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the capability registry set.

        Args:
            registry: The capability registry instance.

        Returns:
            A new PlatformRegistries with the capability registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=registry,
            task_registry=self.task_registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_task_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the task registry set.

        Args:
            registry: The task registry instance.

        Returns:
            A new PlatformRegistries with the task registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=registry,
            evaluation_registry=self.evaluation_registry,
        )

    def with_evaluation_registry(
        self, registry: object
    ) -> PlatformRegistries:
        """Create a new PlatformRegistries with the evaluation registry set.

        Args:
            registry: The evaluation registry instance.

        Returns:
            A new PlatformRegistries with the evaluation registry set.
        """
        return PlatformRegistries(
            workflow_registry=self.workflow_registry,
            execution_registry=self.execution_registry,
            verification_registry=self.verification_registry,
            session_registry=self.session_registry,
            observability_registry=self.observability_registry,
            provider_registry=self.provider_registry,
            serializer_registry=self.serializer_registry,
            capability_registry=self.capability_registry,
            task_registry=self.task_registry,
            evaluation_registry=registry,
        )

    @property
    def has_workflow_registry(self) -> bool:
        """Check if workflow registry is set.

        Returns:
            True if workflow registry is set, False otherwise.
        """
        return self.workflow_registry is not None

    @property
    def has_provider_registry(self) -> bool:
        """Check if provider registry is set.

        Returns:
            True if provider registry is set, False otherwise.
        """
        return self.provider_registry is not None

    @property
    def has_session_registry(self) -> bool:
        """Check if session registry is set.

        Returns:
            True if session registry is set, False otherwise.
        """
        return self.session_registry is not None

    @property
    def count(self) -> int:
        """Count how many registries are set (not None).

        Returns:
            Integer count of non-None registries.
        """
        count = 0
        if self.workflow_registry is not None:
            count += 1
        if self.execution_registry is not None:
            count += 1
        if self.verification_registry is not None:
            count += 1
        if self.session_registry is not None:
            count += 1
        if self.observability_registry is not None:
            count += 1
        if self.provider_registry is not None:
            count += 1
        if self.serializer_registry is not None:
            count += 1
        if self.capability_registry is not None:
            count += 1
        if self.task_registry is not None:
            count += 1
        if self.evaluation_registry is not None:
            count += 1
        return count