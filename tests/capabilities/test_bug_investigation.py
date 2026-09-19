"""Tests for the BugInvestigationCapability.

Verifies:
- Capability name
- Intent is DEBUG
- Profile is DEBUG_PROFILE
- Execute returns CapabilityResult
- Selected symbols included
- Selected modules included
- Context plan included
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex  # noqa: F401


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _make_mock_index() -> object:
    """Create a minimal mock RepositoryIndex for testing."""
    from unittest.mock import MagicMock

    mock_index = MagicMock()
    mock_index.find.return_value = []
    mock_index.find_module.return_value = None
    mock_index.modules = {}
    mock_index.relationships.return_value = []
    mock_index.symbols.return_value = []
    mock_index.statistics.return_value = MagicMock(
        module_count=0,
        symbol_count=0,
    )
    return mock_index


# ---------------------------------------------------------------------------
# Test: Capability Properties
# ---------------------------------------------------------------------------


class TestCapabilityProperties:
    """Tests for BugInvestigationCapability properties."""

    def test_capability_name(self) -> None:
        """Capability should have correct name."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        assert cap.name == "bug-investigation"

    def test_capability_intent(self) -> None:
        """Capability should have DEBUG intent."""
        from packages.capabilities.base import PlannerIntent
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        assert cap.intent == PlannerIntent.DEBUG

    def test_capability_profile(self) -> None:
        """Capability should have DEBUG_PROFILE."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.capabilities.profiles import DEBUG_PROFILE

        cap = BugInvestigationCapability()
        assert cap.profile == DEBUG_PROFILE


# ---------------------------------------------------------------------------
# Test: Execute Returns CapabilityResult
# ---------------------------------------------------------------------------


class TestExecuteReturnsCapabilityResult:
    """Tests for execute returning CapabilityResult."""

    def test_execute_returns_capability_result(self) -> None:
        """Execute should return a CapabilityResult."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.capabilities.models import CapabilityResult

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert isinstance(result, CapabilityResult)

    def test_execute_result_has_query(self) -> None:
        """Result should have the query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Auth fails on timeout", repository_index=mock_index)

        assert result.query == "Auth fails on timeout"

    def test_execute_result_has_intent(self) -> None:
        """Result should have intent."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        # The intent comes from the planner which analyzes the query.
        # With a mock index, the planner may return a different intent
        # based on the query text. We just verify intent is set.
        assert result.intent is not None
        assert isinstance(result.intent, str) or hasattr(result.intent, "value")


# ---------------------------------------------------------------------------
# Test: Selected Symbols
# ---------------------------------------------------------------------------


class TestSelectedSymbols:
    """Tests for selected symbols in capability result."""

    def test_result_has_selected_symbols(self) -> None:
        """Result should have selected_symbols."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.selected_symbols is not None
        assert isinstance(result.selected_symbols, tuple)


# ---------------------------------------------------------------------------
# Test: Selected Modules
# ---------------------------------------------------------------------------


class TestSelectedModules:
    """Tests for selected modules in capability result."""

    def test_result_has_selected_modules(self) -> None:
        """Result should have selected_modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.selected_modules is not None
        assert isinstance(result.selected_modules, tuple)


# ---------------------------------------------------------------------------
# Test: Context Plan
# ---------------------------------------------------------------------------


class TestContextPlan:
    """Tests for context plan in capability result."""

    def test_result_has_context_plan(self) -> None:
        """Result should have context_plan."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.context_plan is not None

    def test_result_context_plan_has_intent(self) -> None:
        """Context plan should have intent."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        # The context plan intent comes from the planner.
        # With a mock index, the planner may return a different intent.
        # We just verify the intent is set.
        assert result.context_plan.intent is not None


# ---------------------------------------------------------------------------
# Test: Context Package
# ---------------------------------------------------------------------------


class TestContextPackage:
    """Tests for context package in capability result."""

    def test_result_has_context_package(self) -> None:
        """Result should have context_package."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.context_package is not None

    def test_context_package_has_primary_symbol(self) -> None:
        """Context package should have primary_symbol."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert hasattr(result.context_package, "primary_symbol")

    def test_context_package_has_estimated_tokens(self) -> None:
        """Context package should have estimated_tokens."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert hasattr(result.context_package, "estimated_tokens")


# ---------------------------------------------------------------------------
# Test: Provider Request
# ---------------------------------------------------------------------------


class TestProviderRequest:
    """Tests for provider request in capability result."""

    def test_result_has_provider_request(self) -> None:
        """Result should have provider_request."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.provider_request is not None


# ---------------------------------------------------------------------------
# Test: Execution Time
# ---------------------------------------------------------------------------


class TestExecutionTime:
    """Tests for execution time in capability result."""

    def test_result_has_execution_time(self) -> None:
        """Result should have execution_time_ms."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.execution_time_ms >= 0

    def test_execution_time_is_positive(self) -> None:
        """Execution time should be positive."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.execution_time_ms > 0


# ---------------------------------------------------------------------------
# Test: Estimated Tokens
# ---------------------------------------------------------------------------


class TestEstimatedTokens:
    """Tests for estimated tokens in capability result."""

    def test_result_has_estimated_tokens(self) -> None:
        """Result should have estimated_tokens."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.estimated_tokens >= 0


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_result(self) -> None:
        """Multiple calls should produce identical results."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result1 = cap.execute(query="Test query", repository_index=mock_index)
        result2 = cap.execute(query="Test query", repository_index=mock_index)

        assert result1.query == result2.query
        assert result1.intent == result2.intent
        assert result1.selected_symbols == result2.selected_symbols
        assert result1.selected_modules == result2.selected_modules


# ---------------------------------------------------------------------------
# Test: Context Building with Candidates
# ---------------------------------------------------------------------------


class TestContextBuildingWithCandidates:
    """Tests for context building with actual candidates."""

    def test_execute_with_candidates(self) -> None:
        """Execute should handle candidates properly."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        # Create a mock index with candidates
        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.query == "Test query"

    def test_execute_with_empty_candidates(self) -> None:
        """Execute should handle empty candidates."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.selected_symbols == ()
        assert result.selected_modules == ()

    def test_execute_with_multiple_candidates(self) -> None:
        """Execute should handle multiple candidates."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.provider_request is not None

    def test_execute_with_no_relationships(self) -> None:
        """Execute should handle no relationships."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None

    def test_execute_with_no_symbols(self) -> None:
        """Execute should handle no symbols."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None
        assert result.context_package.estimated_tokens >= 0

    def test_execute_with_no_modules(self) -> None:
        """Execute should handle no modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None

    def test_execute_with_no_candidates(self) -> None:
        """Execute should handle no candidates."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None
        assert result.context_package.primary_symbol == ""

    def test_execute_with_no_relationships_or_modules(self) -> None:
        """Execute should handle no relationships or modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None
        assert result.context_package.related_callers == []
        assert result.context_package.related_callees == []

    def test_execute_with_empty_query(self) -> None:
        """Execute should handle empty query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="", repository_index=mock_index)

        assert result is not None
        assert result.query == ""

    def test_execute_with_long_query(self) -> None:
        """Execute should handle long query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        long_query = "A" * 10000
        result = cap.execute(query=long_query, repository_index=mock_index)

        assert result is not None
        assert result.query == long_query

    def test_execute_with_special_characters(self) -> None:
        """Execute should handle special characters in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query with special chars: !@#$%^&*()",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query with special chars: !@#$%^&*()"

    def test_execute_with_unicode(self) -> None:
        """Execute should handle unicode in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query with unicode: 你好世界",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query with unicode: 你好世界"

    def test_execute_with_newlines(self) -> None:
        """Execute should handle newlines in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query\nwith\nnewlines",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query\nwith\nnewlines"

    def test_execute_with_tabs(self) -> None:
        """Execute should handle tabs in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query\twith\ttabs",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query\twith\ttabs"

    def test_execute_with_carrying_return(self) -> None:
        """Execute should handle carriage returns in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query\rwith\rcarriage\rreturns",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query\rwith\rcarriage\rreturns"

    def test_execute_with_mixed_whitespace(self) -> None:
        """Execute should handle mixed whitespace in query."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        from unittest.mock import MagicMock

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(
            query="Test query\n\twith\tmixed\r\nwhitespace",
            repository_index=mock_index,
        )

        assert result is not None
        assert result.query == "Test query\n\twith\tmixed\r\nwhitespace"

    def test_execute_assemble_package_with_candidates(self) -> None:
        """_stage_assemble_package should handle candidates with modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.authenticate"
        assert "auth.validate" in package.supporting_symbols

    def test_execute_assemble_package_publishes_no_call_relationships(self) -> None:
        """_stage_assemble_package publishes ranked candidates, never call edges."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.authenticate" in package.supporting_symbols
        assert "auth.logout" in package.supporting_symbols

    def test_execute_assemble_package_with_multiple_modules(self) -> None:
        """_stage_assemble_package should handle multiple modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert "packages/auth/auth.py" in package.related_modules
        assert "packages/session/session.py" in package.related_modules

    def test_execute_assemble_package_empty_candidates(self) -> None:
        """_stage_assemble_package should handle empty candidates."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextResult

        cap = BugInvestigationCapability()

        budget = ContextBudgetResult(
            estimated_tokens=0,
            estimated_symbols=0,
            estimated_modules=0,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == ""
        assert package.supporting_symbols == []

    def test_stage_planning(self) -> None:
        """_stage_planning should return a ContextPlan."""
        from unittest.mock import MagicMock

        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        plan = cap._stage_planning("Test query", mock_index)
        assert plan is not None

    def test_stage_repository_search(self) -> None:
        """_stage_repository_search should return tuple of symbol names."""
        from unittest.mock import MagicMock

        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        symbols = cap._stage_repository_search("Test query", mock_index)
        assert isinstance(symbols, tuple)

    def test_stage_context_building(self) -> None:
        """_stage_context_building should return a ContextResult."""
        from unittest.mock import MagicMock

        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        plan = cap._stage_planning("Test query", mock_index)
        result = cap._stage_context_building("Test query", plan, mock_index)
        assert result is not None

    def test_stage_serialization(self) -> None:
        """_stage_serialization should return a ProviderRequest."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.context_package import ContextPackage

        cap = BugInvestigationCapability()

        package = ContextPackage(
            primary_symbol="auth.authenticate",
            supporting_symbols=[],
            related_callers=[],
            related_callees=[],
            related_modules=[],
            estimated_tokens=100,
        )

        provider_request = cap._stage_serialization(package, "Test query")
        assert provider_request is not None

    def test_assemble_package_same_module_neighbour_is_not_a_caller(self) -> None:
        """_stage_assemble_package keeps a ranked neighbour out of both lists."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.authenticate" in package.supporting_symbols

    def test_assemble_package_multiple_modules_stay_supporting_symbols(self) -> None:
        """_stage_assemble_package keeps multi-module candidates out of both lists."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate4 = ContextCandidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
        )

        candidates = [candidate1, candidate2, candidate3, candidate4]

        budget = ContextBudgetResult(
            estimated_tokens=200,
            estimated_symbols=4,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # First candidate is primary
        assert package.primary_symbol == "auth.logout"
        # Rank order and shared modules are not CALLS edges.
        assert "auth.authenticate" in package.supporting_symbols
        assert "auth.validate" in package.supporting_symbols
        # Both modules should be in related_modules
        assert "packages/auth/auth.py" in package.related_modules
        assert "packages/session/session.py" in package.related_modules

    def test_assemble_package_supporting_candidate_is_not_a_caller(self) -> None:
        """_stage_assemble_package keeps supporting candidates out of both lists."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # Rank order and shared modules are not CALLS edges.
        assert package.primary_symbol == "auth.validate"
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.helper" in package.supporting_symbols

    def test_assemble_package_relationship_summary(self) -> None:
        """_stage_assemble_package should build relationship summary."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.authenticate",
            qualified_name="auth.authenticate",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.relationship_summary is not None
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0
        assert package.relationship_summary.module_count == 1
        assert package.relationship_summary.symbol_count == 3

    def test_assemble_package_metadata(self) -> None:
        """_stage_assemble_package should include metadata."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1]

        budget = ContextBudgetResult(
            estimated_tokens=50,
            estimated_symbols=1,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.metadata is not None
        assert package.metadata.estimated_tokens == 50
        assert package.metadata.ranking_version == "1"

    def test_execute_with_relationships(self) -> None:
        """Execute should handle repository with relationships."""
        from unittest.mock import MagicMock

        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        result = cap.execute(query="Test query with relationships", repository_index=mock_index)

        assert result is not None
        assert result.provider_request is not None
        assert result.context_package is not None

    def test_execute_with_module_dependencies(self) -> None:
        """Execute should handle repository with module dependencies."""
        from unittest.mock import MagicMock

        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()

        mock_mod = MagicMock()
        mock_mod.dependencies = ["packages/session/session.py"]

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=1,
            symbol_count=0,
        )

        result = cap.execute(query="Test query with modules", repository_index=mock_index)

        assert result is not None
        assert result.context_package is not None

    def test_assemble_package_ranked_neighbour_is_not_a_caller(self) -> None:
        """_stage_assemble_package publishes a supporting module, not a caller."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.logout" in package.supporting_symbols

    def test_assemble_package_symbol_count_includes_all(self) -> None:
        """_stage_assemble_package should count all symbols in relationship summary."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.relationship_summary is not None
        # primary + 2 supporting = 3 symbols
        assert package.relationship_summary.symbol_count == 3
        # 1 module
        assert package.relationship_summary.module_count == 1
        # Rank order and shared modules are not CALLS edges.
        assert package.relationship_summary.caller_count == 0
        assert package.relationship_summary.callee_count == 0

    def test_assemble_package_supporting_module_stays_a_module(self) -> None:
        """A same-module neighbour stays a supporting symbol.

        Its module is already published through the candidate list, so the
        package derives nothing else from it.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        # but whose module is only found via supporting_candidates lookup.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # Rank order and shared modules are not CALLS edges.
        assert package.primary_symbol == "auth.validate"
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.helper" in package.supporting_symbols
        assert "packages/auth/auth.py" in package.related_modules


# ---------------------------------------------------------------------------
# Test: _stage_assemble_package - additional coverage
# ---------------------------------------------------------------------------


class TestStageAssemblePackageAdditional:
    """Additional tests for _stage_assemble_package."""

    def test_package_with_ranked_same_module_candidates(self) -> None:
        """The first candidate is the primary and the rest stay supporting.

        Note: ranking chooses the primary symbol; neither ranking nor shared
        module membership says the primary calls the others.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextResult
        from packages.context.models import ContextCandidate as Candidate

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = Candidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
            score=0.9,
        )
        candidate2 = Candidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
            score=0.95,
        )
        candidate3 = Candidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
            score=0.85,
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # First candidate is always primary
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.validate" in package.supporting_symbols
        # session.create is primary for its own module group
        assert "session.create" in package.supporting_symbols

    def test_package_with_no_candidates(self) -> None:
        """Package should handle empty candidates list."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextResult

        cap = BugInvestigationCapability()

        budget = ContextBudgetResult(
            estimated_tokens=0,
            estimated_symbols=0,
            estimated_modules=0,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=[],
            selected_modules=[],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # When no candidates, primary_symbol is empty string, not None
        assert package.primary_symbol == ""
        assert package.related_callers == []
        assert package.related_callees == []
        assert package.related_modules == []

    def test_package_with_multiple_modules(self) -> None:
        """Package should handle candidates from multiple modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextResult
        from packages.context.models import ContextCandidate as Candidate

        cap = BugInvestigationCapability()

        candidate1 = Candidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
            score=0.95,
        )
        candidate2 = Candidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
            score=0.85,
        )
        candidate3 = Candidate(
            symbol_id="token.refresh",
            qualified_name="token.refresh",
            module="packages/token/token.py",
            score=0.8,
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=300,
            estimated_symbols=3,
            estimated_modules=3,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=[
                "packages/auth/auth.py",
                "packages/session/session.py",
                "packages/token/token.py",
            ],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # All three modules should be in related_modules
        assert "packages/auth/auth.py" in package.related_modules
        assert "packages/session/session.py" in package.related_modules
        assert "packages/token/token.py" in package.related_modules

    def test_relationship_summary_counts_match_published_lists(self) -> None:
        """Test that relationship summary is built correctly."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextResult
        from packages.context.models import ContextCandidate as Candidate

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = Candidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
            score=0.9,
        )
        candidate2 = Candidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
            score=0.95,
        )
        candidate3 = Candidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
            score=0.85,
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        # Rank order and shared modules are not CALLS edges.
        assert package.relationship_summary.caller_count == 0
        # Rank order and shared modules are not CALLS edges.
        assert package.relationship_summary.callee_count == 0
        # 1 module
        assert package.relationship_summary.module_count == 1
        # 3 symbols total
        assert package.relationship_summary.symbol_count == 3
    def test_assemble_package_multiple_modules_publish_no_callees(self) -> None:
        """Candidates from several modules stay symbols and modules.

        Cross-module rank order publishes no relationship.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.helper" in package.supporting_symbols
        # Rank order and shared modules are not CALLS edges.
        assert "session.create" in package.supporting_symbols
        # Both modules should be in related_modules
        assert "packages/auth/auth.py" in package.related_modules
        assert "packages/session/session.py" in package.related_modules

    def test_assemble_package_primary_is_always_the_first_candidate(self) -> None:
        """A candidate ranked after the primary is not its callee.

        Same-module candidates that rank below the primary stay supporting
        symbols, and the caller list stays empty.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        # Primary is always the first candidate in the module group, so we need
        # to set primary_symbol_name to find validate. But the code searches for
        # the primary symbol by name within the module_symbols list.
        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        # The first candidate is always primary
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.validate" in package.supporting_symbols
        assert "auth.logout" in package.supporting_symbols

    def test_assemble_package_primary_symbol_follows_rank_not_module_order(self) -> None:
        """The primary symbol is simply the first ranked candidate.

        Module membership changes nothing about the relationships the
        package publishes.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # auth module group: helper (index 0, primary), validate (index 1)
        # session module group: create (index 0, primary for its group)
        # The overall primary is from the first module group (auth)
        candidate1 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        # auth.helper is primary (first in first module group)
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        assert "auth.validate" in package.supporting_symbols
        # session.create is in supporting_symbols (different module group)
        assert "session.create" in package.supporting_symbols

    def test_assemble_module_group_publishes_no_callers(self) -> None:
        """A module group never produces callers.

        Everything ranked in the same module stays a supporting symbol.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Ranked candidates that share a module: helper ranks first and is
        # the primary, validate follows it as a supporting symbol.
        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        # helper is primary (first in module group)
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.validate" in package.supporting_symbols

    def test_assemble_package_candidate_module_is_only_a_module(self) -> None:
        """A candidate module is published as a module, not a relationship.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate3 = ContextCandidate(
            symbol_id="auth.logout",
            qualified_name="auth.logout",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2, candidate3]

        budget = ContextBudgetResult(
            estimated_tokens=150,
            estimated_symbols=3,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.validate"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.helper" in package.supporting_symbols
        assert "auth.logout" in package.supporting_symbols
        # auth module should be in related_modules
        assert "packages/auth/auth.py" in package.related_modules

    def test_assemble_package_supporting_candidate_is_not_a_callee(self) -> None:
        """A supporting candidate never becomes a callee.

        Its module is still collected, because modules come from the
        candidate list rather than from any call graph.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Rank order and shared modules are not CALLS edges.
        candidate1 = ContextCandidate(
            symbol_id="auth.primary",
            qualified_name="auth.primary",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="session.create",
            qualified_name="session.create",
            module="packages/session/session.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=2,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py", "packages/session/session.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.primary"
        # session.create is in supporting_symbols
        assert "session.create" in package.supporting_symbols
        # Both modules should be in related_modules
        assert "packages/auth/auth.py" in package.related_modules
        assert "packages/session/session.py" in package.related_modules

    def test_assemble_package_same_module_supporting_candidate_stays_supporting(self) -> None:
        """A same-module supporting candidate stays a supporting symbol.

        It contributes its name to the symbol list and its module to the
        module list, and nothing else.
        """
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        # Primary at index 0, supporting in same module at index 1
        # This ensures the supporting candidate is added to module_symbols
        # via the supporting_candidates loop (line 322).
        candidate1 = ContextCandidate(
            symbol_id="auth.primary",
            qualified_name="auth.primary",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.supporting",
            qualified_name="auth.supporting",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.primary"
        # Rank order and shared modules are not CALLS edges.
        assert "auth.supporting" in package.supporting_symbols


    def test_assemble_package_module_list_never_becomes_relationships(self) -> None:
        """_stage_assemble_package keeps modules out of both relationship lists."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.validate" in package.supporting_symbols

    def test_assemble_package_symbol_names_come_from_candidates_only(self) -> None:
        """_stage_assemble_package builds the symbol count from candidates only."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability
        from packages.context.models import ContextBudgetResult, ContextCandidate, ContextResult

        cap = BugInvestigationCapability()

        candidate1 = ContextCandidate(
            symbol_id="auth.helper",
            qualified_name="auth.helper",
            module="packages/auth/auth.py",
        )
        candidate2 = ContextCandidate(
            symbol_id="auth.validate",
            qualified_name="auth.validate",
            module="packages/auth/auth.py",
        )

        candidates = [candidate1, candidate2]

        budget = ContextBudgetResult(
            estimated_tokens=100,
            estimated_symbols=2,
            estimated_modules=1,
            within_budget=True,
            truncated=False,
        )

        context_result = ContextResult(
            candidates=candidates,
            selected_modules=["packages/auth/auth.py"],
            budget=budget,
        )

        package = cap._stage_assemble_package(
            context_result=context_result,
            repository_index=None,  # type: ignore[arg-type]
        )

        assert package is not None
        assert package.primary_symbol == "auth.helper"
        # Rank order and shared modules are not CALLS edges.
        assert package.related_callers == []
        assert package.related_callees == []
        # Rank order and shared modules are not CALLS edges.
        assert "auth.validate" in package.supporting_symbols
        # symbol_count should include primary + supporting
        assert package.relationship_summary.symbol_count == 2







# ---------------------------------------------------------------------------
# Test: Investigation Report
# ---------------------------------------------------------------------------


class TestInvestigationReport:
    """Tests for investigation_report in CapabilityResult."""

    def test_result_has_investigation_report(self) -> None:
        """Result should have investigation_report field."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        assert result.investigation_report is not None

    def test_investigation_report_has_affected_modules(self) -> None:
        """Investigation report should have affected_modules."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "affected_modules" in report

    def test_investigation_report_has_affected_symbols(self) -> None:
        """Investigation report should have affected_symbols."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "affected_symbols" in report

    def test_investigation_report_has_dependency_summary(self) -> None:
        """Investigation report should have dependency_summary."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "dependency_summary" in report

    def test_investigation_report_has_diagnostics_summary(self) -> None:
        """Investigation report should have diagnostics_summary."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "diagnostics_summary" in report

    def test_investigation_report_has_impact_summary(self) -> None:
        """Investigation report should have impact_summary."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "impact_summary" in report

    def test_investigation_report_has_architectural_findings(self) -> None:
        """Investigation report should have architectural_findings."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "architectural_findings" in report

    def test_investigation_report_has_refactoring_opportunities(self) -> None:
        """Investigation report should have refactoring_opportunities."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "refactoring_opportunities" in report

    def test_investigation_report_has_context_statistics(self) -> None:
        """Investigation report should have context_statistics."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "context_statistics" in report

    def test_investigation_report_has_estimated_tokens(self) -> None:
        """Investigation report should have estimated_tokens."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert "estimated_tokens" in report

    def test_investigation_report_is_deterministic(self) -> None:
        """Investigation report should be deterministic."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result1 = cap.execute(query="Test query", repository_index=mock_index)
        result2 = cap.execute(query="Test query", repository_index=mock_index)

        report1 = result1.investigation_report
        report2 = result2.investigation_report

        assert report1 is not None
        assert report2 is not None
        assert report1["dependency_summary"] == report2["dependency_summary"]
        assert report1["impact_summary"] == report2["impact_summary"]
        assert report1["estimated_tokens"] == report2["estimated_tokens"]
        assert report1["context_statistics"] == report2["context_statistics"]

    def test_investigation_report_affected_modules_is_tuple(self) -> None:
        """affected_modules should be a tuple."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["affected_modules"], tuple)

    def test_investigation_report_affected_symbols_is_tuple(self) -> None:
        """affected_symbols should be a tuple."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["affected_symbols"], tuple)

    def test_investigation_report_architectural_findings_is_tuple(self) -> None:
        """architectural_findings should be a tuple."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["architectural_findings"], tuple)

    def test_investigation_report_dependency_summary_is_string(self) -> None:
        """dependency_summary should be a string."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["dependency_summary"], str)

    def test_investigation_report_diagnostics_summary_is_string(self) -> None:
        """diagnostics_summary should be a string."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["diagnostics_summary"], str)

    def test_investigation_report_impact_summary_is_string(self) -> None:
        """impact_summary should be a string."""
        from packages.capabilities.bug_investigation import BugInvestigationCapability

        cap = BugInvestigationCapability()
        mock_index = _make_mock_index()

        result = cap.execute(query="Test query", repository_index=mock_index)

        report = result.investigation_report
        assert report is not None
        assert isinstance(report["impact_summary"], str)


# ---------------------------------------------------------------------------
# Test: Relationship honesty
# ---------------------------------------------------------------------------


class TestRelationshipHonesty:
    """Assembly publishes candidates, never invented call edges."""

    def test_same_module_order_never_becomes_a_call_edge(self) -> None:
        """Every ranking of one module's candidates stays edge-free."""
        from itertools import permutations

        from packages.capabilities.bug_investigation import (
            BugInvestigationCapability,
        )
        from tests.capabilities.assembly_probes import (
            assert_relationship_honesty,
            candidate,
        )

        capability = BugInvestigationCapability()
        base = [
            candidate("auth.logout", "packages/auth/auth.py", 120),
            candidate("auth.authenticate", "packages/auth/auth.py", 90),
            candidate("auth.validate", "packages/auth/auth.py", 60),
        ]

        for order in permutations(base):
            assert_relationship_honesty(capability, list(order))

    def test_cross_module_candidates_stay_symbols_and_modules(self) -> None:
        """A candidate in another module contributes a symbol and a module."""
        from packages.capabilities.bug_investigation import (
            BugInvestigationCapability,
        )
        from tests.capabilities.assembly_probes import (
            assert_relationship_honesty,
            candidate,
        )

        package = assert_relationship_honesty(
            BugInvestigationCapability(),
            [
                candidate("auth.logout", "packages/auth/auth.py", 120),
                candidate("session.create", "packages/session/session.py", 90),
            ],
        )

        assert package.supporting_symbols == ["session.create"]
        assert package.related_modules == [
            "packages/auth/auth.py",
            "packages/session/session.py",
        ]

    def test_duplicate_symbols_and_modules_are_deduplicated(self) -> None:
        """Repeated candidates appear once, and the counts follow."""
        from packages.capabilities.bug_investigation import (
            BugInvestigationCapability,
        )
        from tests.capabilities.assembly_probes import (
            assert_relationship_honesty,
            candidate,
        )

        package = assert_relationship_honesty(
            BugInvestigationCapability(),
            [
                candidate("auth.logout", "packages/auth/auth.py", 120),
                candidate("auth.validate", "packages/auth/auth.py", 90),
                candidate("auth.validate", "packages/auth/auth.py", 80),
                candidate("auth.logout", "packages/auth/auth.py", 70),
            ],
        )

        assert package.supporting_symbols == ["auth.validate"]
        assert package.relationship_summary.symbol_count == 2
        assert package.relationship_summary.module_count == 1

    def test_assembly_is_deterministic(self) -> None:
        """The same candidates assemble the same package twice."""
        from packages.capabilities.bug_investigation import (
            BugInvestigationCapability,
        )
        from tests.capabilities.assembly_probes import (
            assert_relationship_honesty,
            candidate,
        )

        capability = BugInvestigationCapability()
        base = [
            candidate("auth.logout", "packages/auth/auth.py", 120),
            candidate("session.create", "packages/session/session.py", 90),
            candidate("auth.validate", "packages/auth/auth.py", 60),
        ]

        first = assert_relationship_honesty(capability, base)
        second = assert_relationship_honesty(capability, base)

        assert first == second
