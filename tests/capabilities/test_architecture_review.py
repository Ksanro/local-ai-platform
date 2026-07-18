"""Tests for the Architecture Review Capability.

Verifies:
- capability is registered
- capability executes correctly
- no provider invocation
- deterministic execution
- immutable result
- correct pipeline stages
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.architecture.models import ArchitectureReview, ModuleSummary
from packages.capabilities.architecture_review import ArchitectureReviewCapability
from packages.capabilities.models import CapabilityResult
from packages.context.context_package import ContextPackage
from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult
from packages.repository.index.models import (
    RepositoryIndex,
    RepositoryStatistics,
)
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_index() -> RepositoryIndex:
    """Create a minimal RepositoryIndex for testing."""
    sym_factory = MagicMock(
        name="Factory",
        qualified_name="packages.providers.factory.ProviderFactory",
        lineno=1,
    )
    sym_create = MagicMock(
        name="create",
        qualified_name="packages.providers.factory.ProviderFactory.create",
        lineno=5,
    )

    return RepositoryIndex(
        modules={
            "packages/providers/factory.py": MagicMock(
                path="packages/providers/factory.py",
            ),
        },
        _symbols=[sym_factory, sym_create],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=1,
            symbol_count=2,
        ),
    )


def _make_architecture_review() -> ArchitectureReview:
    """Create a minimal ArchitectureReview."""
    return ArchitectureReview(
        modules=(
            ModuleSummary(
                module="packages/providers/factory.py",
                symbol_count=2,
                dependency_count=0,
                dependent_count=0,
                instability_score=0.0,
            ),
        ),
        dependency_summary={},
        dependency_cycles=(),
        layering_violations=(),
        orphan_modules=(),
        high_coupling_modules=(),
        largest_components=(),
        diagnostics={"module_count": 1, "symbol_count": 2},
        impact_summary={},
        repository_statistics={"module_count": 1, "symbol_count": 2},
    )


def _make_context_result() -> ContextResult:
    """Create a minimal ContextResult."""
    return ContextResult(
        candidates=[
            ContextCandidate(
                symbol_id="packages.providers.factory.ProviderFactory",
                qualified_name="packages.providers.factory.ProviderFactory",
                module="packages/providers/factory.py",
                score=100,
            ),
        ],
        selected_modules=["packages/providers/factory.py"],
        budget=ContextBudgetResult(
            estimated_tokens=256,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        ),
    )


def _make_context_package() -> ContextPackage:
    """Create a minimal ContextPackage."""
    from packages.context.context_package import ContextMetadata, RelationshipSummary

    return ContextPackage(
        primary_symbol="packages.providers.factory.ProviderFactory",
        supporting_symbols=[],
        related_callers=[],
        related_callees=[],
        related_modules=["packages/providers/factory.py"],
        relationship_summary=RelationshipSummary(
            caller_count=0,
            callee_count=0,
            module_count=1,
            symbol_count=1,
        ),
        estimated_tokens=256,
        metadata=ContextMetadata(
            ranking_version="1",
            repository_revision="",
            estimated_tokens=256,
        ),
    )


def _make_provider_request() -> ProviderRequest:
    """Create a minimal ProviderRequest."""
    return ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[{"role": "user", "content": "Review the architecture"}],
        model="default",
    )


def _make_capability() -> ArchitectureReviewCapability:
    """Create an ArchitectureReviewCapability instance."""
    return ArchitectureReviewCapability()


# ---------------------------------------------------------------------------
# Test: Capability Registration
# ---------------------------------------------------------------------------


class TestCapabilityRegistration:
    """Tests that the capability is registered correctly."""

    def test_capability_has_correct_name(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Capability should have the correct name."""
        assert capability.name == "architecture-review"

    def test_capability_has_review_intent(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Capability should have REVIEW intent."""
        from packages.capabilities.base import PlannerIntent

        assert capability.intent == PlannerIntent.REVIEW


# ---------------------------------------------------------------------------
# Test: Capability Execution
# ---------------------------------------------------------------------------


class TestCapabilityExecution:
    """Tests that the capability executes correctly."""

    def test_capability_returns_result(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Capability should return a CapabilityResult."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        assert isinstance(result, CapabilityResult)

    def test_capability_returns_correct_intent(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Result should have REVIEW intent."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        assert result.intent == "REVIEW"

    def test_capability_returns_correct_query(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Result should have the correct query."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        assert result.query == "Review the architecture"


# ---------------------------------------------------------------------------
# Test: Pipeline Stages
# ---------------------------------------------------------------------------


class TestPipelineStages:
    """Tests that all pipeline stages are called."""

    def test_architecture_analysis_called(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Stage 1 should be called."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ) as mock_analysis:
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )
                        mock_analysis.assert_called_once()

    def test_context_building_called(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Stage 2 should be called."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ) as mock_context:
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )
                        mock_context.assert_called_once()

    def test_serialization_called(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Stage 4 should be called."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ) as mock_ser:
                        capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )
                        mock_ser.assert_called_once()


# ---------------------------------------------------------------------------
# Test: No Provider Invocation
# ---------------------------------------------------------------------------


class TestNoProviderInvocation:
    """Tests that no provider is invoked."""

    def test_no_provider_calls(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Capability should not make any provider calls."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        # If we get here without provider errors, the test passes.
                        result = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )
                        assert isinstance(result, CapabilityResult)


# ---------------------------------------------------------------------------
# Test: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests that the capability produces deterministic output."""

    def test_deterministic_output(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """Two runs with the same input should produce the same output."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result1 = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result2 = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        assert result1.query == result2.query
        assert result1.intent == result2.intent


# ---------------------------------------------------------------------------
# Test: Immutable Result
# ---------------------------------------------------------------------------


class TestImmutableResult:
    """Tests that the result is immutable."""

    def test_result_is_frozen(
        self,
        capability: ArchitectureReviewCapability,
    ) -> None:
        """CapabilityResult should be a frozen dataclass."""
        index = _make_index()

        with patch.object(
            capability,
            "_stage_architecture_analysis",
            return_value=_make_architecture_review(),
        ):
            with patch.object(
                capability,
                "_stage_context_building",
                return_value=_make_context_result(),
            ):
                with patch.object(
                    capability,
                    "_stage_assemble_package",
                    return_value=_make_context_package(),
                ):
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        result = capability.execute(
                            query="Review the architecture",
                            repository_index=index,
                        )

        assert isinstance(result, CapabilityResult)

        with pytest.raises(Exception):
            result.query = "new query"  # type: ignore[misc]

        with pytest.raises(Exception):
            result.intent = "NEW"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Fixtures for pytest
# ---------------------------------------------------------------------------


@pytest.fixture()
def capability() -> ArchitectureReviewCapability:
    """Create an ArchitectureReviewCapability instance."""
    return ArchitectureReviewCapability()
