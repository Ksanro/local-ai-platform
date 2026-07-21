"""Tests for PlatformRegistries.

Tests cover:
- Frozen dataclass
- Registry construction
- Incremental construction with with_* methods
- Property checks
- Count method
"""

from __future__ import annotations

import pytest

from packages.bootstrap.registry import PlatformRegistries


# ---------------------------------------------------------------------------
# PlatformRegistries tests
# ---------------------------------------------------------------------------


class TestPlatformRegistries:
    """Tests for PlatformRegistries."""

    def test_empty_registries(self) -> None:
        registries = PlatformRegistries()
        assert registries.workflow_registry is None
        assert registries.execution_registry is None
        assert registries.verification_registry is None
        assert registries.session_registry is None
        assert registries.observability_registry is None
        assert registries.provider_registry is None
        assert registries.serializer_registry is None
        assert registries.capability_registry is None
        assert registries.task_registry is None
        assert registries.evaluation_registry is None

    def test_count_all_none(self) -> None:
        registries = PlatformRegistries()
        assert registries.count == 0

    def test_count_with_values(self) -> None:
        registries = PlatformRegistries(
            workflow_registry="workflow",
            provider_registry="provider",
            session_registry="session",
        )
        assert registries.count == 3

    def test_frozen_dataclass(self) -> None:
        registries = PlatformRegistries()
        with pytest.raises(Exception):
            registries.workflow_registry = "test"  # type: ignore[assignment]

    def test_has_workflow_registry_true(self) -> None:
        registries = PlatformRegistries(
            workflow_registry="workflow"
        )
        assert registries.has_workflow_registry is True

    def test_has_workflow_registry_false(self) -> None:
        registries = PlatformRegistries()
        assert registries.has_workflow_registry is False

    def test_has_provider_registry_true(self) -> None:
        registries = PlatformRegistries(
            provider_registry="provider"
        )
        assert registries.has_provider_registry is True

    def test_has_provider_registry_false(self) -> None:
        registries = PlatformRegistries()
        assert registries.has_provider_registry is False

    def test_has_session_registry_true(self) -> None:
        registries = PlatformRegistries(
            session_registry="session"
        )
        assert registries.has_session_registry is True

    def test_has_session_registry_false(self) -> None:
        registries = PlatformRegistries()
        assert registries.has_session_registry is False

    def test_with_workflow_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_workflow_registry("workflow")
        assert new_registries.workflow_registry == "workflow"
        assert new_registries.provider_registry is None

    def test_with_execution_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_execution_registry("execution")
        assert new_registries.execution_registry == "execution"

    def test_with_verification_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_verification_registry("verification")
        assert new_registries.verification_registry == "verification"

    def test_with_session_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_session_registry("session")
        assert new_registries.session_registry == "session"

    def test_with_observability_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_observability_registry("observability")
        assert new_registries.observability_registry == "observability"

    def test_with_provider_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_provider_registry("provider")
        assert new_registries.provider_registry == "provider"

    def test_with_serializer_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_serializer_registry("serializer")
        assert new_registries.serializer_registry == "serializer"

    def test_with_capability_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_capability_registry("capability")
        assert new_registries.capability_registry == "capability"

    def test_with_task_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_task_registry("task")
        assert new_registries.task_registry == "task"

    def test_with_evaluation_registry(self) -> None:
        registries = PlatformRegistries()
        new_registries = registries.with_evaluation_registry("evaluation")
        assert new_registries.evaluation_registry == "evaluation"

    def test_incremental_construction(self) -> None:
        registries = PlatformRegistries()
        registries = registries.with_workflow_registry("workflow")
        registries = registries.with_provider_registry("provider")
        registries = registries.with_session_registry("session")
        assert registries.workflow_registry == "workflow"
        assert registries.provider_registry == "provider"
        assert registries.session_registry == "session"
        assert registries.count == 3

    def test_no_shared_state(self) -> None:
        registries1 = PlatformRegistries()
        registries2 = registries1.with_workflow_registry("workflow")
        # registries1 should not be affected
        assert registries1.workflow_registry is None
        assert registries2.workflow_registry == "workflow"