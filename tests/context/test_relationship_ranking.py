"""Tests for Relationship-Aware Context Ranking.

Verifies relationship scoring, deterministic ordering, duplicate prevention,
context expansion, and environment variable configuration.

Acceptance Criteria
-------------------

- caller bonus applied correctly
- callee bonus applied correctly
- shared module bonus applied correctly
- shared class bonus applied correctly
- shared parent bonus applied correctly
- deterministic ordering
- duplicate prevention
- expansion disabled
- expansion enabled
- budget respected
- repeated execution identical
- environment variable configuration
- no modification of existing behavior when disabled

Coverage target: >95%
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from packages.context.models import ContextCandidate
from packages.context.ranking import RankingEngine
from packages.context.ranking_config import RankingConfig
WEIGHT_DIRECT_CALLER = RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLER
WEIGHT_DIRECT_CALLEE = RankingConfig.WEIGHT_CALL_GRAPH_DIRECT_CALLEE
WEIGHT_SHARED_CLASS = RankingConfig.WEIGHT_CALL_GRAPH_SAME_CLASS
WEIGHT_SHARED_MODULE = RankingConfig.WEIGHT_CALL_GRAPH_SAME_MODULE
WEIGHT_SHARED_PARENT = RankingConfig.WEIGHT_CALL_GRAPH_SHARED_PARENT
from packages.context.scoring import (
    RankingReason,
    score_relationship,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _candidate(
    symbol_id: str,
    qualified_name: str,
    module: str,
) -> ContextCandidate:
    """Helper to create a ContextCandidate."""
    return ContextCandidate(
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module=module,
    )


def _mock_graph_view(
    callers_map: dict[str, list[str]] | None = None,
    callees_map: dict[str, list[str]] | None = None,
    parents_map: dict[str, list[str]] | None = None,
    children_map: dict[str, list[str]] | None = None,
) -> MagicMock:
    """Create a mock SymbolGraphView with configurable relationships.

    Args:
        callers_map: Maps primary_symbol.qualified_name -> list of caller qualified names.
        callees_map: Maps primary_symbol.qualified_name -> list of callee qualified names.
        parents_map: Maps primary_symbol.qualified_name -> list of parent qualified names.
        children_map: Maps parent qualified_name -> list of child qualified names.

    Returns:
        A MagicMock configured as a SymbolGraphView.
    """
    view = MagicMock()

    def mock_callers(primary):
        result = []
        if callers_map and primary.qualified_name in callers_map:
            for qn in callers_map[primary.qualified_name]:
                result.append(_candidate(qn, qn, _get_module_for_qn(qn)))
        return result

    def mock_callees(primary):
        result = []
        if callees_map and primary.qualified_name in callees_map:
            for qn in callees_map[primary.qualified_name]:
                result.append(_candidate(qn, qn, _get_module_for_qn(qn)))
        return result

    def mock_parents(primary):
        result = []
        if parents_map and primary.qualified_name in parents_map:
            for qn in parents_map[primary.qualified_name]:
                result.append(_candidate(qn, qn, _get_module_for_qn(qn)))
        return result

    def mock_children(parent):
        result = []
        if children_map and parent.qualified_name in children_map:
            for qn in children_map[parent.qualified_name]:
                result.append(_candidate(qn, qn, _get_module_for_qn(qn)))
        return result

    view.callers = mock_callers
    view.callees = mock_callees
    view.parents = mock_parents
    view.children = mock_children

    return view


def _get_module_for_qn(qn: str) -> str:
    """Derive a module path from a qualified name for test purposes."""
    parts = qn.split(".")
    if len(parts) >= 3:
        return "/".join(parts[:-1]) + ".py"
    return parts[0] + ".py"


# ------------------------------------------------------------------
# Relationship scoring — DIRECT_CALLER
# ------------------------------------------------------------------


class TestDirectCallerBonus:
    """Tests for DIRECT_CALLER relationship scoring."""

    def test_direct_caller_bonus_applied(self) -> None:
        """Candidate that calls the primary symbol gets +WEIGHT_DIRECT_CALLER."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        caller = _candidate("auth.views.login", "auth.views.login", "auth/views.py")

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]}
        )

        score, reasons = score_relationship(
            candidate=caller,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score >= WEIGHT_DIRECT_CALLER
        assert RankingReason.DIRECT_CALLER in reasons

    def test_direct_caller_not_applied_when_not_caller(self) -> None:
        """No caller bonus when candidate does not call the primary."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        unrelated = _candidate("auth.utils.helper", "auth.utils.helper", "auth/utils.py")

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]}
        )

        score, reasons = score_relationship(
            candidate=unrelated,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.DIRECT_CALLER not in reasons

    def test_direct_caller_disabled(self) -> None:
        """No caller bonus when relationship scoring is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        caller = _candidate("auth.views.login", "auth.views.login", "auth/views.py")

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]}
        )

        score, reasons = score_relationship(
            candidate=caller,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=False,
        )

        assert score == 0
        assert RankingReason.DIRECT_CALLER not in reasons

    def test_direct_caller_no_primary(self) -> None:
        """No caller bonus when primary symbol is None."""
        caller = _candidate("auth.views.login", "auth.views.login", "auth/views.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=caller,
            primary_symbol=None,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score == 0
        assert RankingReason.DIRECT_CALLER not in reasons


# ------------------------------------------------------------------
# Relationship scoring — DIRECT_CALLEE
# ------------------------------------------------------------------


class TestDirectCalleeBonus:
    """Tests for DIRECT_CALLEE relationship scoring."""

    def test_direct_callee_bonus_applied(self) -> None:
        """Candidate that is called by the primary symbol gets +WEIGHT_DIRECT_CALLEE."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        callee = _candidate("auth.services.validate", "auth.services.validate", "auth/services.py")

        graph_view = _mock_graph_view(
            callees_map={"auth.App.run": ["auth.services.validate"]}
        )

        score, reasons = score_relationship(
            candidate=callee,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score >= WEIGHT_DIRECT_CALLEE
        assert RankingReason.DIRECT_CALLEE in reasons

    def test_direct_callee_not_applied_when_not_callee(self) -> None:
        """No callee bonus when candidate is not called by the primary."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        unrelated = _candidate("auth.utils.helper", "auth.utils.helper", "auth/utils.py")

        graph_view = _mock_graph_view(
            callees_map={"auth.App.run": ["auth.services.validate"]}
        )

        score, reasons = score_relationship(
            candidate=unrelated,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.DIRECT_CALLEE not in reasons

    def test_direct_callee_disabled(self) -> None:
        """No callee bonus when relationship scoring is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        callee = _candidate("auth.services.validate", "auth.services.validate", "auth/services.py")

        graph_view = _mock_graph_view(
            callees_map={"auth.App.run": ["auth.services.validate"]}
        )

        score, reasons = score_relationship(
            candidate=callee,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=False,
        )

        assert score == 0
        assert RankingReason.DIRECT_CALLEE not in reasons


# ------------------------------------------------------------------
# Relationship scoring — SHARED_MODULE
# ------------------------------------------------------------------


class TestSharedModuleBonus:
    """Tests for SHARED_MODULE relationship scoring."""

    def test_shared_module_bonus_applied(self) -> None:
        """Candidate in the same module as primary gets +WEIGHT_SHARED_MODULE."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        same_module = _candidate("auth.App.helper", "auth.App.helper", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=same_module,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score >= WEIGHT_SHARED_MODULE
        assert RankingReason.SHARED_MODULE in reasons

    def test_shared_module_not_applied(self) -> None:
        """No shared module bonus when candidates are in different modules."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        different_module = _candidate("utils.helper", "utils.helper", "utils/helper.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=different_module,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.SHARED_MODULE not in reasons

    def test_shared_module_disabled(self) -> None:
        """No shared module bonus when relationship scoring is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        same_module = _candidate("auth.App.helper", "auth.App.helper", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=same_module,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=False,
        )

        assert score == 0
        assert RankingReason.SHARED_MODULE not in reasons


# ------------------------------------------------------------------
# Relationship scoring — SHARED_CLASS
# ------------------------------------------------------------------


class TestSharedClassBonus:
    """Tests for SHARED_CLASS relationship scoring."""

    def test_shared_class_bonus_applied(self) -> None:
        """Candidate in the same class scope as primary gets +WEIGHT_SHARED_CLASS."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        same_class = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=same_class,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score >= WEIGHT_SHARED_CLASS
        assert RankingReason.SHARED_CLASS in reasons

    def test_shared_class_not_applied_for_different_classes(self) -> None:
        """No shared class bonus when candidates are in different classes."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        other_class = _candidate("auth.OtherApp.run", "auth.OtherApp.run", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=other_class,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.SHARED_CLASS not in reasons

    def test_shared_class_not_applied_for_functions(self) -> None:
        """No shared class bonus when both are functions (no class scope)."""
        primary = _candidate("auth.run", "auth.run", "auth/app.py")
        other_func = _candidate("auth.validate", "auth.validate", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=other_func,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.SHARED_CLASS not in reasons

    def test_shared_class_disabled(self) -> None:
        """No shared class bonus when relationship scoring is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        same_class = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=same_class,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=False,
        )

        assert score == 0
        assert RankingReason.SHARED_CLASS not in reasons


# ------------------------------------------------------------------
# Relationship scoring — SHARED_PARENT
# ------------------------------------------------------------------


class TestSharedParentBonus:
    """Tests for SHARED_PARENT relationship scoring."""

    def test_shared_parent_bonus_applied(self) -> None:
        """Candidate that shares a parent with primary gets +WEIGHT_SHARED_PARENT."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        sibling = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        graph_view = _mock_graph_view(
            parents_map={"auth.App.run": ["auth.App"]},
            children_map={"auth.App": ["auth.App.validate"]},
        )

        score, reasons = score_relationship(
            candidate=sibling,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score >= WEIGHT_SHARED_PARENT
        assert RankingReason.SHARED_PARENT in reasons

    def test_shared_parent_not_applied(self) -> None:
        """No shared parent bonus when candidates have different parents."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        unrelated = _candidate("utils.helper", "utils.helper", "utils/helper.py")

        graph_view = _mock_graph_view(
            parents_map={"auth.App.run": ["auth.App"]},
            children_map={"auth.App": ["auth.App.validate"]},
        )

        score, reasons = score_relationship(
            candidate=unrelated,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert RankingReason.SHARED_PARENT not in reasons

    def test_shared_parent_disabled(self) -> None:
        """No shared parent bonus when relationship scoring is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        sibling = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        graph_view = _mock_graph_view(
            parents_map={"auth.App.run": ["auth.App"]},
            children_map={"auth.App": ["auth.App.validate"]},
        )

        score, reasons = score_relationship(
            candidate=sibling,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=False,
        )

        assert score == 0
        assert RankingReason.SHARED_PARENT not in reasons


# ------------------------------------------------------------------
# Combined relationship signals
# ------------------------------------------------------------------


class TestCombinedRelationshipSignals:
    """Tests for combined relationship signals."""

    def test_multiple_relationships_accumulate(self) -> None:
        """Multiple relationship signals accumulate."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        # Same module, same class, and direct caller
        caller = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.App.validate"]},
            callees_map={},
            parents_map={"auth.App.run": ["auth.App"]},
            children_map={"auth.App": ["auth.App.validate"]},
        )

        score, reasons = score_relationship(
            candidate=caller,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        # SHARED_MODULE + SHARED_CLASS + DIRECT_CALLER + SHARED_PARENT
        expected = (
            WEIGHT_SHARED_MODULE
            + WEIGHT_SHARED_CLASS
            + WEIGHT_DIRECT_CALLER
            + WEIGHT_SHARED_PARENT
        )
        assert score == expected
        assert RankingReason.DIRECT_CALLER in reasons
        assert RankingReason.SHARED_MODULE in reasons
        assert RankingReason.SHARED_CLASS in reasons
        assert RankingReason.SHARED_PARENT in reasons

    def test_same_symbol_not_scored(self) -> None:
        """The primary symbol itself is not scored for relationship signals."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")

        graph_view = _mock_graph_view()

        score, reasons = score_relationship(
            candidate=primary,
            primary_symbol=primary,
            symbol_graph_view=graph_view,
            relationship_enabled=True,
        )

        assert score == 0
        assert reasons == []


# ------------------------------------------------------------------
# RankingEngine — Deterministic ordering
# ------------------------------------------------------------------


class TestDeterministicOrdering:
    """Tests for deterministic ranking ordering."""

    def test_deterministic_ordering_with_relationships(self) -> None:
        """Same input always produces identical ranking with relationships."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
            _candidate("auth.services.helper", "auth.services.helper", "auth/services.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
            callees_map={"auth.App.run": ["auth.services.helper"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=False,
        )

        results = [engine.rank("test", candidates) for _ in range(10)]
        first = results[0]
        for result in results[1:]:
            assert result == first

    def test_tie_breaker_respected_with_relationships(self) -> None:
        """Ties are broken by qualified_name ascending with relationships."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.z", "auth.z", "auth/z.py"),
            _candidate("auth.a", "auth.a", "auth/a.py"),
            _candidate("auth.m", "auth.m", "auth/m.py"),
        ]

        graph_view = _mock_graph_view()

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=False,
            expansion_enabled=False,
        )

        ranked = engine.rank("nonexistent", candidates)
        names = [c.qualified_name for c in ranked]
        assert names == sorted(names)

    def test_repeated_execution_identical(self) -> None:
        """Repeated executions produce identical ranking."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
            _candidate("auth.services.helper", "auth.services.helper", "auth/services.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
            callees_map={"auth.App.run": ["auth.services.helper"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=False,
        )

        results = [engine.rank("test", candidates) for _ in range(5)]
        first = results[0]
        for result in results[1:]:
            assert result == first


# ------------------------------------------------------------------
# Duplicate prevention
# ------------------------------------------------------------------


class TestDuplicatePrevention:
    """Tests for duplicate prevention."""

    def test_no_duplicate_candidates(self) -> None:
        """No duplicate candidates in ranked output."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
            callees_map={"auth.App.run": ["auth.App.validate"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=False,
        )

        ranked = engine.rank("test", candidates)
        qualified_names = [c.qualified_name for c in ranked]
        assert len(qualified_names) == len(set(qualified_names))

    def test_primary_symbol_not_duplicated(self) -> None:
        """Primary symbol is not duplicated when it appears in candidates."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            primary,
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=False,
        )

        ranked = engine.rank("run", candidates)
        qualified_names = [c.qualified_name for c in ranked]
        run_count = sum(1 for n in qualified_names if n == "auth.App.run")
        assert run_count == 1


# ------------------------------------------------------------------
# Context expansion — disabled
# ------------------------------------------------------------------


class TestExpansionDisabled:
    """Tests for expansion disabled behavior."""

    def test_expansion_disabled_no_addition(self) -> None:
        """No expansion candidates added when expansion is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
            callees_map={"auth.App.run": ["auth.services.helper"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=False,
        )

        ranked = engine.rank("test", candidates, max_tokens=4096)
        # Only the original candidates, no expansion
        assert len(ranked) == 1
        assert ranked[0].qualified_name == "auth.App.validate"


# ------------------------------------------------------------------
# Context expansion — enabled
# ------------------------------------------------------------------


class TestExpansionEnabled:
    """Tests for expansion enabled behavior."""

    def test_expansion_adds_callers(self) -> None:
        """Direct callers are added when expansion is enabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=True,
        )

        ranked = engine.rank("test", candidates, max_tokens=4096)
        qualified_names = [c.qualified_name for c in ranked]
        assert "auth.views.login" in qualified_names

    def test_expansion_adds_callees(self) -> None:
        """Direct callees are added when expansion is enabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
        ]

        graph_view = _mock_graph_view(
            callees_map={"auth.App.run": ["auth.services.helper"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=True,
        )

        ranked = engine.rank("test", candidates, max_tokens=4096)
        qualified_names = [c.qualified_name for c in ranked]
        assert "auth.services.helper" in qualified_names

    def test_expansion_respects_budget(self) -> None:
        """Expansion respects the token budget."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login"]},
            callees_map={"auth.App.run": ["auth.services.helper"]},
        )

        # Very small budget — only 1 candidate fits (100 tokens)
        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=True,
        )

        ranked = engine.rank("test", candidates, max_tokens=100)
        # Only the original candidate fits; no expansion due to budget
        assert len(ranked) == 1

    def test_expansion_skips_existing(self) -> None:
        """Expansion skips candidates already in the ranked list."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidates = [
            _candidate("auth.App.validate", "auth.App.validate", "auth/app.py"),
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
        ]

        graph_view = _mock_graph_view(
            callers_map={"auth.App.run": ["auth.views.login", "auth.services.helper"]},
        )

        engine = RankingEngine(
            symbol_graph_view=graph_view,
            primary_symbol=primary,
            relationship_enabled=True,
            expansion_enabled=True,
        )

        ranked = engine.rank("test", candidates, max_tokens=4096)
        qualified_names = [c.qualified_name for c in ranked]
        # auth.views.login should appear only once
        assert qualified_names.count("auth.views.login") == 1
        # auth.services.helper should be added (not in original list)
        assert "auth.services.helper" in qualified_names


# ------------------------------------------------------------------
# Environment variable configuration
# ------------------------------------------------------------------


class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_relationship_ranking_enabled_by_default(self) -> None:
        """Relationship ranking is enabled by default."""
        # Ensure the env var is not set to "false"
        old_val = os.environ.pop("RELATIONSHIP_RANKING_ENABLED", None)
        try:
            engine = RankingEngine()
            assert engine.relationship_enabled is True
        finally:
            if old_val is not None:
                os.environ["RELATIONSHIP_RANKING_ENABLED"] = old_val

    def test_relationship_ranking_disabled_by_env(self) -> None:
        """Relationship ranking can be disabled via environment variable."""
        old_val = os.environ.get("RELATIONSHIP_RANKING_ENABLED")
        try:
            os.environ["RELATIONSHIP_RANKING_ENABLED"] = "false"
            engine = RankingEngine()
            assert engine.relationship_enabled is False
        finally:
            if old_val is not None:
                os.environ["RELATIONSHIP_RANKING_ENABLED"] = old_val
            else:
                os.environ.pop("RELATIONSHIP_RANKING_ENABLED", None)

    def test_expansion_enabled_by_default(self) -> None:
        """Expansion is enabled by default."""
        old_val = os.environ.pop("RELATIONSHIP_EXPANSION_ENABLED", None)
        try:
            engine = RankingEngine()
            assert engine.expansion_enabled is True
        finally:
            if old_val is not None:
                os.environ["RELATIONSHIP_EXPANSION_ENABLED"] = old_val

    def test_expansion_disabled_by_env(self) -> None:
        """Expansion can be disabled via environment variable."""
        old_val = os.environ.get("RELATIONSHIP_EXPANSION_ENABLED")
        try:
            os.environ["RELATIONSHIP_EXPANSION_ENABLED"] = "false"
            engine = RankingEngine()
            assert engine.expansion_enabled is False
        finally:
            if old_val is not None:
                os.environ["RELATIONSHIP_EXPANSION_ENABLED"] = old_val
            else:
                os.environ.pop("RELATIONSHIP_EXPANSION_ENABLED", None)

    def test_programmatic_override(self) -> None:
        """Programmatic configuration overrides environment variables."""
        old_val = os.environ.get("RELATIONSHIP_RANKING_ENABLED")
        try:
            os.environ["RELATIONSHIP_RANKING_ENABLED"] = "false"
            engine = RankingEngine(relationship_enabled=True)
            assert engine.relationship_enabled is True
        finally:
            if old_val is not None:
                os.environ["RELATIONSHIP_RANKING_ENABLED"] = old_val
            else:
                os.environ.pop("RELATIONSHIP_RANKING_ENABLED", None)


# ------------------------------------------------------------------
# RankingEngine — No relationship graph
# ------------------------------------------------------------------


class TestNoRelationshipGraph:
    """Tests for ranking without a relationship graph."""

    def test_ranking_without_graph_view(self) -> None:
        """Ranking works without a graph view (no relationship signals)."""
        candidates = [
            _candidate("auth.App.run", "auth.App.run", "auth/app.py"),
            _candidate("auth.views.login", "auth.views.login", "auth/views.py"),
        ]

        engine = RankingEngine()
        ranked = engine.rank("app", candidates)

        # Should still rank by lexical signals only
        assert len(ranked) == 2
        assert ranked[0].qualified_name == "auth.App.run"

    def test_ranking_with_none_graph_view(self) -> None:
        """Ranking with None graph view produces no relationship signals."""
        candidates = [
            _candidate("auth.App.run", "auth.App.run", "auth/app.py"),
        ]

        engine = RankingEngine(
            symbol_graph_view=None,
            primary_symbol=_candidate("auth.App.run", "auth.App.run", "auth/app.py"),
        )

        ranked = engine.rank("app", candidates)
        # No relationship signals should be present
        for candidate in ranked:
            assert RankingReason.DIRECT_CALLER not in candidate.reasons
            assert RankingReason.DIRECT_CALLEE not in candidate.reasons
            assert RankingReason.SHARED_MODULE not in candidate.reasons
            assert RankingReason.SHARED_CLASS not in candidate.reasons
            assert RankingReason.SHARED_PARENT not in candidate.reasons


# ------------------------------------------------------------------
# Existing behavior preservation
# ------------------------------------------------------------------


class TestExistingBehaviorPreserved:
    """Tests that existing ranking behavior is preserved."""

    def test_exact_name_outranks_partial(self) -> None:
        """Exact symbol name match outranks partial name match."""
        candidates = [
            _candidate("Middleware", "auth.AuthMiddleware", "auth.py"),  # partial
            _candidate("Middleware", "auth.Middleware", "auth.py"),  # exact
        ]

        engine = RankingEngine()
        ranked = engine.rank("middleware", candidates)
        assert ranked[0].qualified_name == "auth.Middleware"
        assert ranked[1].qualified_name == "auth.AuthMiddleware"

    def test_partial_outranks_token_overlap(self) -> None:
        """Partial name match outranks token overlap only."""
        candidates = [
            _candidate("Middleware", "auth.Middleware", "auth.py"),  # partial
            _candidate("Authentication", "auth.Authentication", "auth.py"),  # no match -> +5
        ]

        engine = RankingEngine()
        ranked = engine.rank("middl", candidates)
        assert ranked[0].qualified_name == "auth.Middleware"

    def test_public_symbol_bonus_applied(self) -> None:
        """Public symbol bonus is applied."""
        candidate = _candidate("Public", "main.Public", "main.py")
        engine = RankingEngine()
        engine.rank("public", [candidate])
        assert candidate.score > 0
        assert RankingReason.PUBLIC_NAME in candidate.reasons

    def test_empty_query_zero_scores(self) -> None:
        """Empty query produces zero scores."""
        candidates = [
            _candidate("App", "main.App", "main.py"),
            _candidate("Middleware", "auth.Middleware", "auth.py"),
        ]
        engine = RankingEngine()
        ranked = engine.rank("", candidates)
        for candidate in ranked:
            assert candidate.score == 0

    def test_no_duplicate_candidates(self) -> None:
        """No duplicate candidates in output."""
        candidates = [
            _candidate("A", "mod.A", "mod.py"),
            _candidate("B", "mod.B", "mod.py"),
            _candidate("C", "mod.C", "mod.py"),
        ]
        engine = RankingEngine()
        ranked = engine.rank("test", candidates)
        qualified_names = [c.qualified_name for c in ranked]
        assert len(qualified_names) == len(set(qualified_names))


# ------------------------------------------------------------------
# score_relationship edge cases
# ------------------------------------------------------------------


class TestScoreRelationshipEdgeCases:
    """Tests for score_relationship edge cases."""

    def test_no_graph_view_returns_zero(self) -> None:
        """No relationship score when graph view is None."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidate = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        score, reasons = score_relationship(
            candidate=candidate,
            primary_symbol=primary,
            symbol_graph_view=None,
            relationship_enabled=True,
        )

        assert score == 0
        assert reasons == []

    def test_disabled_relationship_returns_zero(self) -> None:
        """No relationship score when relationship is disabled."""
        primary = _candidate("auth.App.run", "auth.App.run", "auth/app.py")
        candidate = _candidate("auth.App.validate", "auth.App.validate", "auth/app.py")

        score, reasons = score_relationship(
            candidate=candidate,
            primary_symbol=primary,
            symbol_graph_view=MagicMock(),
            relationship_enabled=False,
        )

        assert score == 0
        assert reasons == []
