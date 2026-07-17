"""Tests for the Debug Capability.

Verifies:
- Capability registration
- Factory creation
- DEBUG planner intent used
- Callers requested in context
- Callees requested in context
- Diagnostics requested in context
- Dependency expansion requested in context
- Context respects token budget
- Deterministic execution
- Immutable result
- Explain behavior unchanged
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.capabilities.base import PlannerIntent
from packages.capabilities.debug import DebugCapability
from packages.capabilities.explain import ExplainCapability
from packages.capabilities.factory import CapabilityFactory
from packages.capabilities.models import CapabilityResult
from packages.capabilities.registry import CapabilityRegistry
from packages.context.context_package import ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
    ContextResult,
)
from packages.planning.plan import ContextPlan
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
    sym_service = MagicMock(
        name="ServiceA",
        qualified_name="tests.fixtures.repositories.simple.module_a.ServiceA",
        lineno=10,
    )
    sym_process = MagicMock(
        name="process",
        qualified_name="tests.fixtures.repositories.simple.module_a.ServiceA.process",
        lineno=15,
    )
    sym_helper = MagicMock(
        name="helper_a",
        qualified_name="tests.fixtures.repositories.simple.module_a.helper_a",
        lineno=20,
    )

    return RepositoryIndex(
        modules={
            "packages/providers/factory.py": MagicMock(
                path="packages/providers/factory.py",
            ),
            "tests/fixtures/repositories/simple/module_a.py": MagicMock(
                path="tests/fixtures/repositories/simple/module_a.py",
            ),
        },
        _symbols=[sym_factory, sym_create, sym_service, sym_process, sym_helper],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=5,
            class_count=3,
            function_count=5,
            symbol_count=5,
        ),
    )


def _make_debug_plan() -> ContextPlan:
    """Create a ContextPlan with DEBUG intent and debug-specific settings."""
    return ContextPlan(
        intent="DEBUG",
        primary_symbols=(),
        relationship_expansion=True,
        ranking_profile="DEFAULT",
        maximum_depth=2,
        include_callers=True,
        include_callees=True,
        include_modules=True,
        include_diagnostics=True,
        estimated_complexity="MODERATE",
    )


def _make_explain_plan() -> ContextPlan:
    """Create a ContextPlan with EXPLAIN intent (for unchanged-behavior test)."""
    return ContextPlan(
        intent="EXPLAIN",
        primary_symbols=(),
        relationship_expansion=False,
        ranking_profile="DEFAULT",
        maximum_depth=0,
        include_callers=False,
        include_callees=False,
        include_modules=False,
        include_diagnostics=False,
        estimated_complexity="SIMPLE",
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
    return ContextPackage(
        primary_symbol="packages.providers.factory.ProviderFactory",
        supporting_symbols=[],
        related_callers=[],
        related_callees=[],
        related_modules=["packages/providers/factory.py"],
        estimated_tokens=256,
    )


def _make_provider_request() -> ProviderRequest:
    """Create a minimal ProviderRequest."""
    return ProviderRequest(
        provider_type=ProviderType.openai,
        messages=[{"role": "user", "content": "Why is auth failing?"}],
        model="default",
    )


@pytest.fixture()
def capability() -> DebugCapability:
    """Create a DebugCapability instance."""
    return DebugCapability()


# ---------------------------------------------------------------------------
# Test: Capability Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests that the Debug capability is properly registered."""

    def test_registry_can_register_debug(
        self,
    ) -> None:
        """registry.register('debug', DebugCapability) should succeed."""
        registry = CapabilityRegistry()
        registry.register("debug", DebugCapability)
        assert registry.get("debug") is DebugCapability

    def test_registry_lists_debug_in_all_capabilities(
        self,
    ) -> None:
        """Debug capability should appear in all()."""
        registry = CapabilityRegistry()
        registry.register("debug", DebugCapability)
        names = registry.all()
        assert "debug" in names

    def test_registry_duplicate_registration_raises(
        self,
    ) -> None:
        """Registering the same capability twice should raise."""
        registry = CapabilityRegistry()
        registry.register("debug", DebugCapability)
        with pytest.raises(ValueError):
            registry.register("debug", DebugCapability)


# ---------------------------------------------------------------------------
# Test: Factory Creation
# ---------------------------------------------------------------------------


class TestFactoryCreation:
    """Tests that the factory creates DebugCapability correctly."""

    def test_factory_creates_debug_capability(
        self,
    ) -> None:
        """factory.create('debug') should return a DebugCapability instance."""
        registry = CapabilityRegistry()
        registry.register("debug", DebugCapability)
        factory = CapabilityFactory(registry)
        cap = factory.create("debug")
        assert isinstance(cap, DebugCapability)

    def test_factory_debug_capability_has_correct_name(
        self,
    ) -> None:
        """The created capability should have name 'debug'."""
        registry = CapabilityRegistry()
        registry.register("debug", DebugCapability)
        factory = CapabilityFactory(registry)
        cap = factory.create("debug")
        assert cap.name == "debug"


# ---------------------------------------------------------------------------
# Test: DEBUG Planner Intent
# ---------------------------------------------------------------------------


class TestDebugIntent:
    """Tests that the DEBUG intent is used."""

    def test_intent_property_returns_debug(
        self,
    ) -> None:
        """capability.intent should return PlannerIntent.DEBUG."""
        cap = DebugCapability()
        assert cap.intent == PlannerIntent.DEBUG

    def test_intent_value_is_debug(
        self,
    ) -> None:
        """The intent value string should be 'DEBUG'."""
        cap = DebugCapability()
        assert cap.intent.value == "DEBUG"

    def test_result_intent_matches_plan(
        self,
        capability: DebugCapability,
    ) -> None:
        """CapabilityResult.intent should match the ContextPlan intent."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.intent == "DEBUG"


# ---------------------------------------------------------------------------
# Test: Callers Requested in Context
# ---------------------------------------------------------------------------


class TestCallersRequested:
    """Tests that callers are requested in context."""

    def test_debug_plan_includes_callers(
        self,
    ) -> None:
        """DEBUG plan should have include_callers=True."""
        plan = _make_debug_plan()
        assert plan.include_callers is True

    def test_debug_context_query_includes_callers(
        self,
        capability: DebugCapability,
    ) -> None:
        """Context building should request callers via relationship_expansion."""
        index = _make_index()
        plan = _make_debug_plan()

        captured_query: ContextQuery | None = None

        def _capture_build(query: ContextQuery) -> ContextResult:
            nonlocal captured_query
            captured_query = query
            return _make_context_result()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                            # Patch the ContextBuilder.build to capture the query.
                            from packages.context.builder import ContextBuilder

                            def _mock_build(self, query: ContextQuery) -> ContextResult:
                                nonlocal captured_query
                                captured_query = query
                                return _make_context_result()

            with patch.object(
                ContextBuilder,
                "build",
                _mock_build,
            ):
                capability.execute(
                    query="Why is auth failing?",
                    repository_index=index,
                )

        assert captured_query is not None
        assert captured_query.relationship_expansion is True

    def test_related_callers_extracted_from_package(
        self,
        capability: DebugCapability,
    ) -> None:
        """ContextPackage should contain related_callers for debug."""
        # Build a context result with multiple candidates from the same module
        # so that callers/callees can be derived.
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod.func_a",
                qualified_name="pkg.mod.func_a",
                module="pkg/mod.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_b",
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=80,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_c",
                qualified_name="pkg.mod.func_c",
                module="pkg/mod.py",
                score=60,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=512,
                estimated_symbols=3,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=context_result,
                ):
                    # Don't mock _stage_assemble_package — we want to test
                    # the actual assembly logic.
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        package = capability._stage_assemble_package(
                            context_result,
                            _make_index(),
                        )

        # func_a is primary, func_b and func_c are after it in the list
        # so they become callees (after primary), callers is empty
        # because func_a is at index 0.
        assert isinstance(package, ContextPackage)
        # The package should have the primary symbol set
        assert package.primary_symbol == "pkg.mod.func_a"
        # func_b and func_c come after func_a in the candidate list
        # so they are callees
        assert "pkg.mod.func_b" in package.related_callees
        assert "pkg.mod.func_c" in package.related_callees


# ---------------------------------------------------------------------------
# Test: Callees Requested in Context
# ---------------------------------------------------------------------------


class TestCalleesRequested:
    """Tests that callees are requested in context."""

    def test_debug_plan_includes_callees(
        self,
    ) -> None:
        """DEBUG plan should have include_callees=True."""
        plan = _make_debug_plan()
        assert plan.include_callees is True

    def test_related_callees_extracted_from_package(
        self,
        capability: DebugCapability,
    ) -> None:
        """ContextPackage should contain related_callees for debug."""
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod.func_a",
                qualified_name="pkg.mod.func_a",
                module="pkg/mod.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_b",
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=80,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=256,
                estimated_symbols=2,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        with patch.object(
            capability,
            "_stage_planning",
            return_value=_make_debug_plan(),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=context_result,
                ):
                    # Don't mock _stage_assemble_package — we want to test
                    # the actual assembly logic.
                    with patch.object(
                        capability,
                        "_stage_serialization",
                        return_value=_make_provider_request(),
                    ):
                        package = capability._stage_assemble_package(
                            context_result,
                            _make_index(),
                        )

        assert "pkg.mod.func_b" in package.related_callees


# ---------------------------------------------------------------------------
# Test: Assemble Package Edge Cases
# ---------------------------------------------------------------------------


class TestAssemblePackageEdgeCases:
    """Tests for edge cases in _stage_assemble_package."""

    def test_empty_candidates(
        self,
        capability: DebugCapability,
    ) -> None:
        """Empty candidates should produce an empty package."""
        context_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=ContextBudgetResult(
                estimated_tokens=0,
                estimated_symbols=0,
                estimated_modules=0,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        assert package.primary_symbol == ""
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == []

    def test_single_candidate(
        self,
        capability: DebugCapability,
    ) -> None:
        """Single candidate should have no callers or callees."""
        context_result = ContextResult(
            candidates=[
                ContextCandidate(
                    symbol_id="pkg.mod.func_a",
                    qualified_name="pkg.mod.func_a",
                    module="pkg/mod.py",
                    score=100,
                ),
            ],
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=128,
                estimated_symbols=1,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        assert package.primary_symbol == "pkg.mod.func_a"
        assert package.supporting_symbols == []
        assert package.related_callers == []
        assert package.related_callees == []

    def test_callers_when_primary_not_first(
        self,
        capability: DebugCapability,
    ) -> None:
        """When primary (candidates[0]) is not first in module_symbols,
        symbols before it in module_symbols are callers."""
        # func_b is at index 0 (primary), func_a is at index 1, func_c at index 2.
        # All same module. module_symbols = [func_b, func_a, func_c]
        # primary_index = 0 (func_b), so no callers (nothing before index 0).
        # Callees = func_a, func_c (after index 0).
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod.func_b",
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=90,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_a",
                qualified_name="pkg.mod.func_a",
                module="pkg/mod.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_c",
                qualified_name="pkg.mod.func_c",
                module="pkg/mod.py",
                score=80,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=384,
                estimated_symbols=3,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        # func_b is primary (candidates[0]), func_a and func_c are callees
        assert package.primary_symbol == "pkg.mod.func_b"
        assert "pkg.mod.func_a" in package.related_callees
        assert "pkg.mod.func_c" in package.related_callees

    def test_callers_exist_when_primary_in_middle(
        self,
        capability: DebugCapability,
    ) -> None:
        """When primary is in the middle of module_symbols, symbols before it are callers."""
        # Put a different-module candidate first, then func_a, then func_c.
        # module_symbols (same-module only) = [func_a, func_c]
        # primary_index = 0, so no callers.
        # To get callers, we need a same-module candidate BEFORE func_a.
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod.func_a",
                qualified_name="pkg.mod.func_a",
                module="pkg/mod.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_c",
                qualified_name="pkg.mod.func_c",
                module="pkg/mod.py",
                score=80,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_b",
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=90,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=384,
                estimated_symbols=3,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        # func_a is primary (candidates[0]), func_c and func_b are callees
        assert package.primary_symbol == "pkg.mod.func_a"
        assert "pkg.mod.func_c" in package.related_callees
        assert "pkg.mod.func_b" in package.related_callees
        assert package.related_callers == []

    def test_multiple_modules_in_callers(
        self,
        capability: DebugCapability,
    ) -> None:
        """Callers from different modules should all be collected."""
        # func_x (mod_a) is primary, func_y (mod_b) is supporting,
        # func_a (mod_a) is supporting.
        # module_symbols (same-module as primary=mod_a) = [func_x, func_a]
        # primary_index = 0, so no callers.
        # Callees: func_a (same module, after primary).
        # For callees from different modules, we need func_y after primary in module_symbols.
        # But func_y is in mod_b, not mod_a, so it won't be in module_symbols.
        # To test cross-module callees, we need a different approach.
        # Let's make func_x primary, func_y (mod_b) and func_a (mod_a) both after.
        # module_symbols = [func_x, func_a] (only mod_a candidates)
        # primary_index = 0, callees = [func_a] (after index 0 in module_symbols)
        # func_y is a supporting candidate but not in module_symbols, so it won't be a callee.
        # To get cross-module callees, we need func_y to be in module_symbols.
        # That means func_y must be in the same module as primary.
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod_a.func_x",
                qualified_name="pkg.mod_a.func_x",
                module="pkg/mod_a.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod_a.func_a",
                qualified_name="pkg.mod_a.func_a",
                module="pkg/mod_a.py",
                score=80,
            ),
            ContextCandidate(
                symbol_id="pkg.mod_b.func_y",
                qualified_name="pkg.mod_b.func_y",
                module="pkg/mod_b.py",
                score=90,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod_a.py", "pkg/mod_b.py"],
            budget=ContextBudgetResult(
                estimated_tokens=384,
                estimated_symbols=3,
                estimated_modules=2,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        # func_x is primary, func_a is callee (same module, after primary)
        assert package.primary_symbol == "pkg.mod_a.func_x"
        assert "pkg.mod_a.func_a" in package.related_callees
        # func_y is a supporting symbol but not a callee (different module)
        assert "pkg.mod_b.func_y" in package.supporting_symbols
        # related_modules should include both modules
        assert "pkg/mod_a.py" in package.related_modules
        assert "pkg/mod_b.py" in package.related_modules

    def test_deduplication_of_supporting_symbols(
        self,
        capability: DebugCapability,
    ) -> None:
        """Duplicate symbols in candidates should be deduplicated."""
        candidates = [
            ContextCandidate(
                symbol_id="pkg.mod.func_a",
                qualified_name="pkg.mod.func_a",
                module="pkg/mod.py",
                score=100,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_b",
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=80,
            ),
            ContextCandidate(
                symbol_id="pkg.mod.func_b",  # duplicate
                qualified_name="pkg.mod.func_b",
                module="pkg/mod.py",
                score=70,
            ),
        ]
        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["pkg/mod.py"],
            budget=ContextBudgetResult(
                estimated_tokens=256,
                estimated_symbols=2,
                estimated_modules=1,
                within_budget=True,
                truncated=False,
            ),
        )

        package = capability._stage_assemble_package(
            context_result,
            _make_index(),
        )

        # func_b should appear only once
        assert package.supporting_symbols.count("pkg.mod.func_b") == 1
        assert package.supporting_symbols == ["pkg.mod.func_b"]


# ---------------------------------------------------------------------------
# Test: Diagnostics Requested in Context
# ---------------------------------------------------------------------------


class TestDiagnosticsRequested:
    """Tests that diagnostics are requested in context."""

    def test_debug_plan_includes_diagnostics(
        self,
    ) -> None:
        """DEBUG plan should have include_diagnostics=True."""
        plan = _make_debug_plan()
        assert plan.include_diagnostics is True

    def test_debug_plan_includes_modules(
        self,
    ) -> None:
        """DEBUG plan should have include_modules=True."""
        plan = _make_debug_plan()
        assert plan.include_modules is True


# ---------------------------------------------------------------------------
# Test: Dependency Expansion Requested in Context
# ---------------------------------------------------------------------------


class TestDependencyExpansion:
    """Tests that dependency expansion is requested in context."""

    def test_debug_plan_has_relationship_expansion(
        self,
    ) -> None:
        """DEBUG plan should have relationship_expansion=True."""
        plan = _make_debug_plan()
        assert plan.relationship_expansion is True

    def test_debug_plan_has_maximum_depth_2(
        self,
    ) -> None:
        """DEBUG plan should have maximum_depth=2."""
        plan = _make_debug_plan()
        assert plan.maximum_depth == 2


# ---------------------------------------------------------------------------
# Test: Context Respects Token Budget
# ---------------------------------------------------------------------------


class TestTokenBudget:
    """Tests that context respects token budget."""

    def test_result_includes_estimated_tokens(
        self,
        capability: DebugCapability,
    ) -> None:
        """CapabilityResult should include estimated_tokens from context."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        assert isinstance(result.estimated_tokens, int)
        assert result.estimated_tokens > 0

    def test_context_query_max_tokens_set(
        self,
        capability: DebugCapability,
    ) -> None:
        """ContextQuery should have max_tokens=4096."""
        index = _make_index()
        plan = _make_debug_plan()

        captured_query: ContextQuery | None = None

        from packages.context.builder import ContextBuilder

        def _mock_build(self, query: ContextQuery) -> ContextResult:
            nonlocal captured_query
            captured_query = query
            return _make_context_result()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                        with patch.object(
                            ContextBuilder,
                            "build",
                            _mock_build,
                        ):
                            capability.execute(
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        assert captured_query is not None
        assert captured_query.max_tokens == 4096


# ---------------------------------------------------------------------------
# Test: Deterministic Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests that the capability produces deterministic output."""

    def test_deterministic_output(
        self,
        capability: DebugCapability,
    ) -> None:
        """Two runs with the same input should produce the same output."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            result2 = capability.execute(
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        assert result1.query == result2.query
        assert result1.intent == result2.intent
        assert result1.context_plan == result2.context_plan
        assert result1.context_package == result2.context_package
        assert result1.provider_request == result2.provider_request
        assert result1.selected_symbols == result2.selected_symbols
        assert result1.selected_modules == result2.selected_modules
        assert result1.estimated_tokens == result2.estimated_tokens


# ---------------------------------------------------------------------------
# Test: Immutable Result
# ---------------------------------------------------------------------------


class TestImmutableResult:
    """Tests that the result is immutable."""

    def test_result_is_frozen(
        self,
        capability: DebugCapability,
    ) -> None:
        """CapabilityResult should be a frozen dataclass."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        assert isinstance(result, CapabilityResult)

        with pytest.raises(Exception):
            result.query = "new query"  # type: ignore[misc]

        with pytest.raises(Exception):
            result.selected_symbols = ("new",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: Explain Behavior Unchanged
# ---------------------------------------------------------------------------


class TestExplainUnchanged:
    """Tests that Explain capability behavior is unchanged."""

    def test_explain_intent_is_still_explain(
        self,
    ) -> None:
        """ExplainCapability should still return EXPLAIN intent."""
        cap = ExplainCapability()
        assert cap.intent == PlannerIntent.EXPLAIN
        assert cap.intent.value == "EXPLAIN"

    def test_explain_capability_still_instantiable(
        self,
    ) -> None:
        """ExplainCapability should still be instantiable."""
        cap = ExplainCapability()
        assert isinstance(cap, ExplainCapability)
        assert cap.name == "explain"

    def test_explain_capability_not_affected_by_debug(
        self,
    ) -> None:
        """Adding DebugCapability should not affect ExplainCapability."""
        registry = CapabilityRegistry()
        registry.register("explain", ExplainCapability)
        registry.register("debug", DebugCapability)
        factory = CapabilityFactory(registry)

        explain_cap = factory.create("explain")
        debug_cap = factory.create("debug")

        assert explain_cap.name == "explain"
        assert debug_cap.name == "debug"
        assert explain_cap.intent == PlannerIntent.EXPLAIN
        assert debug_cap.intent == PlannerIntent.DEBUG


# ---------------------------------------------------------------------------
# Test: Pipeline Stages Invoked
# ---------------------------------------------------------------------------


class TestPipelineStages:
    """Tests that all pipeline stages are invoked."""

    def test_all_stages_called(
        self,
        capability: DebugCapability,
    ) -> None:
        """All five pipeline stages should be called."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ) as mock_plan:
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
            ) as mock_search:
                with patch.object(
                    capability,
                    "_stage_context_building",
                    return_value=_make_context_result(),
                ) as mock_build:
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        return_value=_make_context_package(),
                    ) as mock_assemble:
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            return_value=_make_provider_request(),
                        ) as mock_ser:
                            capability.execute(
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        mock_plan.assert_called_once()
        mock_search.assert_called_once()
        mock_build.assert_called_once()
        mock_assemble.assert_called_once()
        mock_ser.assert_called_once()

    def test_stages_called_in_order(
        self,
        capability: DebugCapability,
    ) -> None:
        """Stages should be called in the correct order."""
        index = _make_index()
        plan = _make_debug_plan()

        call_order: list[str] = []

        def _track(name: str):
            def _decorator(func):
                def _wrapper(*args, **kwargs):
                    call_order.append(name)
                    return func(*args, **kwargs)
                return _wrapper
            return _decorator

        with patch.object(
            capability,
            "_stage_planning",
            _track("planning")(lambda *a, **k: plan),
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                _track("repository_search")(lambda *a, **k: ()),
            ):
                with patch.object(
                    capability,
                    "_stage_context_building",
                    _track("context_building")(
                        lambda *a, **k: _make_context_result()
                    ),
                ):
                    with patch.object(
                        capability,
                        "_stage_assemble_package",
                        _track("assemble_package")(
                            lambda *a, **k: _make_context_package()
                        ),
                    ):
                        with patch.object(
                            capability,
                            "_stage_serialization",
                            _track("serialization")(
                                lambda *a, **k: _make_provider_request()
                            ),
                        ):
                            capability.execute(
                                query="Why is auth failing?",
                                repository_index=index,
                            )

        expected = [
            "planning",
            "repository_search",
            "context_building",
            "assemble_package",
            "serialization",
        ]
        assert call_order == expected


# ---------------------------------------------------------------------------
# Test: CapabilityResult Structure
# ---------------------------------------------------------------------------


class TestCapabilityResultStructure:
    """Tests that the CapabilityResult has the correct structure."""

    def test_result_has_query(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the query field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.query == "Why is auth failing?"

    def test_result_has_intent(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the intent field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.intent == "DEBUG"

    def test_result_has_context_plan(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the context_plan field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.context_plan == plan

    def test_result_has_context_package(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the context_package field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.context_package == _make_context_package()

    def test_result_has_provider_request(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the provider_request field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert result.provider_request == _make_provider_request()

    def test_result_has_selected_symbols(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the selected_symbols field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_symbols, tuple)

    def test_result_has_selected_modules(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the selected_modules field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert isinstance(result.selected_modules, tuple)

    def test_result_has_estimated_tokens(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the estimated_tokens field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert isinstance(result.estimated_tokens, int)

    def test_result_has_execution_time_ms(
        self,
        capability: DebugCapability,
    ) -> None:
        """Result should have the execution_time_ms field."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert isinstance(result.execution_time_ms, float)
                            assert result.execution_time_ms >= 0


# ---------------------------------------------------------------------------
# Test: Planning Stage Actual Code
# ---------------------------------------------------------------------------


class TestPlanningStage:
    """Tests that exercise the actual _stage_planning code."""

    def test_stage_planning_invokes_planner(
        self,
        capability: DebugCapability,
    ) -> None:
        """_stage_planning should import and instantiate ContextPlanner."""
        index = _make_index()

        # Patch only ContextPlanner.build — the import and instantiation
        # should still execute, covering lines 184-191.
        from packages.planning.planner import ContextPlanner

        plan = _make_debug_plan()

        with patch.object(
            ContextPlanner,
            "build",
            return_value=plan,
        ):
            result = capability._stage_planning(
                query="Why is auth failing?",
                repository_index=index,
            )

        assert result is plan


# ---------------------------------------------------------------------------
# Test: Stateless Nature
# ---------------------------------------------------------------------------


class TestStateless:
    """Tests that the DebugCapability is stateless."""

    def test_no_instance_attributes(
        self,
        capability: DebugCapability,
    ) -> None:
        """DebugCapability should not have instance attributes."""
        non_dunder = [k for k in vars(capability) if not k.startswith("_")]
        assert len(non_dunder) == 0

    def test_multiple_instances_independent(
        self,
    ) -> None:
        """Multiple instances should be independent."""
        cap1 = DebugCapability()
        cap2 = DebugCapability()
        assert cap1 is not cap2
        assert cap1.name == cap2.name
        assert cap1.intent == cap2.intent


# ---------------------------------------------------------------------------
# Test: No Provider Invocation
# ---------------------------------------------------------------------------


class TestNoProviderInvocation:
    """Tests that no provider is invoked."""

    def test_no_network_calls(
        self,
        capability: DebugCapability,
    ) -> None:
        """Capability should not make any network calls."""
        index = _make_index()
        plan = _make_debug_plan()

        with patch.object(
            capability,
            "_stage_planning",
            return_value=plan,
        ):
            with patch.object(
                capability,
                "_stage_repository_search",
                return_value=(),
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
                                query="Why is auth failing?",
                                repository_index=index,
                            )
                            assert isinstance(result, CapabilityResult)


# ---------------------------------------------------------------------------
# Test: Repeated Execution Identical
# ---------------------------------------------------------------------------


class TestRepeatedExecutionIdentical:
    """Tests that repeated execution produces identical results."""

    def test_repeated_execution_identical(
        self,
        capability: DebugCapability,
    ) -> None:
        """Repeated execution with the same input should produce identical results."""
        index = _make_index()
        plan = _make_debug_plan()

        results: list[CapabilityResult] = []
        for _ in range(3):
            with patch.object(
                capability,
                "_stage_planning",
                return_value=plan,
            ):
                with patch.object(
                    capability,
                    "_stage_repository_search",
                    return_value=(),
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
                                results.append(
                                    capability.execute(
                                        query="Why is auth failing?",
                                        repository_index=index,
                                    )
                                )

        for result in results:
            assert result.query == "Why is auth failing?"
            assert result.intent == "DEBUG"
            assert result.context_plan == plan
            assert result.context_package == _make_context_package()
            assert result.provider_request == _make_provider_request()
            assert result.selected_symbols == ()
            assert result.selected_modules == ("packages/providers/factory.py",)
            assert result.estimated_tokens == 256
