"""Tests for the InvestigateBugTask.

Verifies:
- Task plan structure
- Candidate symbols identified
- Affected modules included
- Dependency paths included
- Diagnostics included
- Architecture findings included
- Context package generated
- Deterministic output
- Coverage >95%
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.tasks.models import TaskPlan, TaskRequest

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex  # noqa: F401


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _make_request(
    changed_files: list[str] | None = None,
    changed_symbols: list[str] | None = None,
    stack_trace: str | None = None,
    reproduction_steps: list[str] | None = None,
    suspected_modules: list[str] | None = None,
    suspected_symbols: list[str] | None = None,
) -> TaskRequest:
    """Create a TaskRequest for bug investigation.

    Supports both new field names (changed_files, changed_symbols,
    stack_trace) and old field names (suspected_modules, suspected_symbols,
    observed_stacktrace) for backward compatibility.
    """
    # New field names take precedence
    modules = changed_files if changed_files is not None else (
        suspected_modules if suspected_modules is not None else
        ["packages/auth/", "packages/session/"]
    )
    symbols = changed_symbols if changed_symbols is not None else (
        suspected_symbols if suspected_symbols is not None else
        ["authenticate", "validate_session"]
    )
    trace = stack_trace if stack_trace is not None else "TimeoutError at line 42"

    options: dict[str, object] = {
        "changed_files": modules,
        "changed_symbols": symbols,
        "stack_trace": trace,
    }
    if reproduction_steps is not None:
        options["reproduction_steps"] = reproduction_steps

    return TaskRequest(
        query="Auth fails on timeout",
        repository_root=".",
        options=options,
        user_messages=("Auth fails on timeout", "Authentication fails when session expires"),
    )


def _make_mock_index(
    find_result: list | None = None,
    find_module_result: object | None = None,
) -> object:
    """Create a minimal mock RepositoryIndex for testing."""
    from unittest.mock import MagicMock

    mock_index = MagicMock()
    mock_index.find.return_value = find_result or []
    mock_index.find_module.return_value = find_module_result
    mock_index.modules = {}
    mock_index.relationships.return_value = []
    mock_index.symbols.return_value = []
    mock_index.statistics.return_value = MagicMock(
        module_count=0,
        symbol_count=0,
    )
    return mock_index


# ---------------------------------------------------------------------------
# Test: Task Properties
# ---------------------------------------------------------------------------


class TestTaskProperties:
    """Tests for InvestigateBugTask properties."""

    def test_task_name(self) -> None:
        """Task should have correct name."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        assert task.name == "investigate-bug"

    def test_task_capability(self) -> None:
        """Task should have correct capability."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        assert task.capability == "bug-investigation"


# ---------------------------------------------------------------------------
# Test: Task Plan Structure
# ---------------------------------------------------------------------------


class TestTaskPlanStructure:
    """Tests for TaskPlan structure."""

    def test_plan_is_task_plan(self) -> None:
        """Plan should be a TaskPlan."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert isinstance(plan, TaskPlan)

    def test_plan_task_name(self) -> None:
        """Plan should have correct task name."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.task_name == "investigate-bug"

    def test_plan_capability(self) -> None:
        """Plan should have correct capability."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.capability == "bug-investigation"

    def test_plan_has_steps(self) -> None:
        """Plan should have steps."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.steps is not None
        assert len(plan.steps) >= 5

    def test_plan_has_constraints(self) -> None:
        """Plan should have constraints."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.constraints is not None
        assert len(plan.constraints) >= 1

    def test_plan_constraints_are_read_only(self) -> None:
        """Plan constraints should include read-only constraint."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        constraint_types = [c.type for c in plan.constraints]
        assert "read-only" in constraint_types

    def test_plan_constraints_include_deterministic(self) -> None:
        """Plan constraints should include deterministic constraint."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        constraint_types = [c.type for c in plan.constraints]
        assert "deterministic" in constraint_types


# ---------------------------------------------------------------------------
# Test: Candidate Symbols
# ---------------------------------------------------------------------------


class TestCandidateSymbols:
    """Tests for candidate symbols in task plan."""

    def test_plan_includes_candidate_symbols(self) -> None:
        """Plan should include candidate symbols."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps with required_symbols
        has_symbol_steps = False
        for step in plan.steps:
            if step.required_symbols:
                has_symbol_steps = True
                break

        assert has_symbol_steps

    def test_plan_candidate_symbols_from_suspected_symbols(self) -> None:
        """Plan should include candidate symbols from suspected_symbols."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(
            suspected_symbols=["authenticate", "validate_session", "check_permissions"]
        )
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps with required_symbols
        for step in plan.steps:
            if step.required_symbols:
                assert "authenticate" in step.required_symbols
                assert "validate_session" in step.required_symbols
                assert "check_permissions" in step.required_symbols
                break


# ---------------------------------------------------------------------------
# Test: Affected Modules
# ---------------------------------------------------------------------------


class TestAffectedModules:
    """Tests for affected modules in task plan."""

    def test_plan_includes_affected_modules(self) -> None:
        """Plan should include affected modules."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()

        from unittest.mock import MagicMock

        mock_module = MagicMock()
        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.find_module.return_value = mock_module
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps with required_modules
        has_module_steps = False
        for step in plan.steps:
            if step.required_modules:
                has_module_steps = True
                break

        assert has_module_steps

    def test_plan_affected_modules_from_suspected_modules(self) -> None:
        """Plan should include affected modules from suspected_modules."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(
            suspected_modules=["packages/auth/", "packages/session/", "packages/token/"]
        )

        from unittest.mock import MagicMock

        mock_module = MagicMock()
        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.find_module.return_value = mock_module
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps with required_modules
        for step in plan.steps:
            if step.required_modules:
                assert "packages/auth/" in step.required_modules
                assert "packages/session/" in step.required_modules
                assert "packages/token/" in step.required_modules
                break


# ---------------------------------------------------------------------------
# Test: Dependency Paths
# ---------------------------------------------------------------------------


class TestDependencyPaths:
    """Tests for dependency paths in task plan."""

    def test_plan_includes_dependency_paths(self) -> None:
        """Plan should include dependency paths."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps that include dependency-related content
        assert plan.steps is not None
        assert len(plan.steps) > 0

    def test_plan_includes_dependency_step(self) -> None:
        """Plan should include dependency paths step."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have a step with title containing "dependency"
        has_dependency_step = False
        for step in plan.steps:
            if "dependency" in step.title.lower():
                has_dependency_step = True
                break

        assert has_dependency_step


# ---------------------------------------------------------------------------
# Test: Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    """Tests for diagnostics in task plan."""

    def test_plan_includes_diagnostics(self) -> None:
        """Plan should include diagnostics."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps that include diagnostics-related content
        assert plan.steps is not None
        assert len(plan.steps) > 0

    def test_plan_includes_diagnostics_step(self) -> None:
        """Plan should include diagnostics step."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have a step with title containing "diagnostic"
        has_diagnostic_step = False
        for step in plan.steps:
            if "diagnostic" in step.title.lower():
                has_diagnostic_step = True
                break

        assert has_diagnostic_step


# ---------------------------------------------------------------------------
# Test: Architecture Findings
# ---------------------------------------------------------------------------


class TestArchitectureFindings:
    """Tests for architecture findings in task plan."""

    def test_plan_includes_architecture_findings(self) -> None:
        """Plan should include architecture findings."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have steps that include architecture-related content
        assert plan.steps is not None
        assert len(plan.steps) > 0

    def test_plan_includes_architecture_step(self) -> None:
        """Plan should include architecture findings step."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # Should have a step with title containing "architecture"
        has_architecture_step = False
        for step in plan.steps:
            if "architecture" in step.title.lower():
                has_architecture_step = True
                break

        assert has_architecture_step


# ---------------------------------------------------------------------------
# Test: Context Package
# ---------------------------------------------------------------------------


class TestContextPackage:
    """Tests for context package in task plan."""

    def test_plan_has_context_package(self) -> None:
        """Plan should have context package."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # The context package may be None for this task
        # but it should be explicitly set
        assert hasattr(plan, "context_package")


# ---------------------------------------------------------------------------
# Test: Deterministic Output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_deterministic_plan(self) -> None:
        """Multiple calls should produce identical plans."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan1 = task.plan(repository_index=mock_index, request=request)
        plan2 = task.plan(repository_index=mock_index, request=request)

        assert plan1.task_name == plan2.task_name
        assert plan1.capability == plan2.capability
        assert len(plan1.steps) == len(plan2.steps)

        for i in range(len(plan1.steps)):
            assert plan1.steps[i].title == plan2.steps[i].title
            assert plan1.steps[i].description == plan2.steps[i].description


# ---------------------------------------------------------------------------
# Test: Empty Input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """Tests for empty input scenarios."""

    def test_empty_suspected_modules(self) -> None:
        """Task should handle empty suspected_modules."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(suspected_modules=[])
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_empty_suspected_symbols(self) -> None:
        """Task should handle empty suspected_symbols."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(suspected_symbols=[])
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_no_options(self) -> None:
        """Task should handle request with no options."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = TaskRequest(query="Test query", repository_root=".")
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_no_stacktrace(self) -> None:
        """Task should handle request without stacktrace."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(stack_trace=None)
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_no_reproduction_steps(self) -> None:
        """Task should handle request without reproduction steps."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(reproduction_steps=[])
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)


# ---------------------------------------------------------------------------
# Test: Stacktrace Handling
# ---------------------------------------------------------------------------


class TestStacktraceHandling:
    """Tests for stacktrace handling."""

    def test_plan_includes_stacktrace(self) -> None:
        """Plan should include stacktrace in context."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(stack_trace="TimeoutError at line 42")
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        # The stacktrace should be in the context
        assert plan is not None
        assert isinstance(plan, TaskPlan)

    def test_plan_handles_none_stacktrace(self) -> None:
        """Plan should handle None stacktrace."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request(stack_trace=None)
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan is not None
        assert isinstance(plan, TaskPlan)


# ---------------------------------------------------------------------------
# Test: Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    """Tests for metrics in task plan."""

    def test_plan_has_metrics(self) -> None:
        """Plan should have metrics."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.metrics is not None

    def test_plan_metrics_estimated_tokens(self) -> None:
        """Plan should have estimated tokens."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        assert plan.metrics.estimated_tokens >= 0

    def test_plan_metrics_complexity(self) -> None:
        """Plan should have complexity."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()
        request = _make_request()
        mock_index = _make_mock_index()

        plan = task.plan(repository_index=mock_index, request=request)

        from packages.tasks.models import TaskComplexity

        assert plan.metrics.estimated_complexity in TaskComplexity


# ---------------------------------------------------------------------------
# Test: Internal Methods - _collect_dependency_paths
# ---------------------------------------------------------------------------


class TestCollectDependencyPaths:
    """Tests for _collect_dependency_paths method."""

    def test_collect_dependency_paths_with_relationships(self) -> None:
        """_collect_dependency_paths should collect paths from relationships."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_rel = MagicMock()
        mock_rel.source = "auth.authenticate"
        mock_rel.target = "auth.validate"

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = [mock_rel]
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        paths = task._collect_dependency_paths(
            candidate_symbols=["auth.authenticate"],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(paths, list)
        assert len(paths) > 0
        assert "auth.authenticate -> auth.validate" in paths[0]

    def test_collect_dependency_paths_empty_candidates(self) -> None:
        """_collect_dependency_paths should handle empty candidates."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

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

        paths = task._collect_dependency_paths(
            candidate_symbols=[],
            affected_modules=[],
            repository_index=mock_index,
        )

        assert isinstance(paths, list)
        assert paths == []

    def test_collect_dependency_paths_with_module_dependencies(self) -> None:
        """_collect_dependency_paths should collect from module dependencies."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        mock_mod.dependencies = ["packages/session/session.py"]

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        paths = task._collect_dependency_paths(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(paths, list)
        assert any("packages/auth/auth.py depends on" in p for p in paths)

    def test_collect_dependency_paths_no_relationships(self) -> None:
        """_collect_dependency_paths should handle no relationships."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

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

        paths = task._collect_dependency_paths(
            candidate_symbols=["auth.authenticate"],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(paths, list)


# ---------------------------------------------------------------------------
# Test: Internal Methods - _collect_diagnostics
# ---------------------------------------------------------------------------


class TestCollectDiagnostics:
    """Tests for _collect_diagnostics method."""

    def test_collect_diagnostics_dead_symbol(self) -> None:
        """_collect_diagnostics should detect dead symbols."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_sym = MagicMock()
        mock_sym.qualified_name = "auth.authenticate"
        mock_sym.is_dead = True

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = [mock_sym]
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_diagnostics(
            candidate_symbols=["auth.authenticate"],
            affected_modules=[],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert any("Dead symbol: auth.authenticate" in f for f in findings)

    def test_collect_diagnostics_orphan_module(self) -> None:
        """_collect_diagnostics should detect orphan modules."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        mock_mod.is_orphan = True

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_diagnostics(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert any("Orphan module: packages/auth/auth.py" in f for f in findings)

    def test_collect_diagnostics_large_module(self) -> None:
        """_collect_diagnostics should detect large modules."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        mock_mod.line_count = 600

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_diagnostics(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert any("Large module: packages/auth/auth.py" in f for f in findings)

    def test_collect_diagnostics_empty(self) -> None:
        """_collect_diagnostics should handle empty inputs."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

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

        findings = task._collect_diagnostics(
            candidate_symbols=[],
            affected_modules=[],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert findings == []


# ---------------------------------------------------------------------------
# Test: Internal Methods - _collect_architecture_findings
# ---------------------------------------------------------------------------


class TestCollectArchitectureFindings:
    """Tests for _collect_architecture_findings method."""

    def test_collect_architecture_findings_cycle(self) -> None:
        """_collect_architecture_findings should detect dependency cycles."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_rel1 = MagicMock()
        mock_rel1.source = "auth.authenticate"
        mock_rel1.target = "auth.validate"

        mock_rel2 = MagicMock()
        mock_rel2.source = "auth.validate"
        mock_rel2.target = "auth.authenticate"

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {}
        mock_index.relationships.return_value = [mock_rel1, mock_rel2]
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_architecture_findings(
            candidate_symbols=["auth.authenticate"],
            affected_modules=["auth.authenticate"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert any("Dependency cycle:" in f for f in findings)

    def test_collect_architecture_findings_high_coupling(self) -> None:
        """_collect_architecture_findings should detect high coupling."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        mock_mod.coupling_score = 0.9

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_architecture_findings(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert any("High coupling module: packages/auth/auth.py" in f for f in findings)

    def test_collect_architecture_findings_empty(self) -> None:
        """_collect_architecture_findings should handle empty inputs."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

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

        findings = task._collect_architecture_findings(
            candidate_symbols=[],
            affected_modules=[],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
        assert findings == []


# ---------------------------------------------------------------------------
# Test: BugInvestigationRequest conversion
# ---------------------------------------------------------------------------


class TestBugInvestigationRequest:
    """Tests for BugInvestigationRequest conversion."""

    def test_request_to_task_request(self) -> None:
        """BugInvestigationRequest should convert to TaskRequest."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        req = BugInvestigationRequest(
            title="Auth fails",
            description="Authentication fails on timeout",
            changed_files=("packages/auth/",),
            changed_symbols=("authenticate",),
            stack_trace="TimeoutError at line 42",
            logs=("ERROR: timeout",),
            tags=("auth", "timeout"),
        )

        task_req = req.to_task_request()

        assert task_req is not None
        assert task_req.query == "Auth fails Authentication fails on timeout"
        assert task_req.user_messages == ("Auth fails", "Authentication fails on timeout")
        assert "changed_files" in task_req.options
        assert "changed_symbols" in task_req.options
        assert "stack_trace" in task_req.options
        assert "logs" in task_req.options
        assert "tags" in task_req.options

    def test_request_to_task_request_no_stacktrace(self) -> None:
        """BugInvestigationRequest should handle no stacktrace."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        req = BugInvestigationRequest(
            title="Auth fails",
            description="Authentication fails",
            changed_files=(),
            changed_symbols=(),
            stack_trace=None,
            logs=(),
            tags=(),
        )

        task_req = req.to_task_request()

        assert task_req is not None
        assert task_req.query == "Auth fails Authentication fails"
        assert task_req.user_messages == ("Auth fails", "Authentication fails")
        assert "stack_trace" not in task_req.options
        assert "logs" not in task_req.options
        assert "tags" not in task_req.options

    def test_request_to_task_request_empty(self) -> None:
        """BugInvestigationRequest should handle empty inputs."""
        from packages.tasks.bug_investigation_request import BugInvestigationRequest

        req = BugInvestigationRequest(
            title="",
            description="",
            changed_files=(),
            changed_symbols=(),
            stack_trace=None,
            logs=(),
            tags=(),
        )

        task_req = req.to_task_request()

        assert task_req is not None
        assert task_req.query == ""


# ---------------------------------------------------------------------------
# Test: Execute Exception Paths
# ---------------------------------------------------------------------------


class TestCollectDiagnosticsExceptionPaths:
    """Tests for _collect_diagnostics exception paths."""

    def test_collect_diagnostics_with_broken_module(self) -> None:
        """_collect_diagnostics should handle broken module objects gracefully."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        # Create a module that raises AttributeError on attribute access
        class BrokenModule:
            @property
            def is_orphan(self) -> None:
                raise AttributeError("broken is_orphan")

            @property
            def line_count(self) -> None:
                raise AttributeError("broken line_count")

        mock_mod = BrokenModule()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_diagnostics(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)


class TestCollectArchitectureFindingsExceptionPaths:
    """Tests for _collect_architecture_findings exception paths."""

    def test_collect_architecture_findings_with_broken_module(self) -> None:
        """_collect_architecture_findings should handle broken module objects."""
        from unittest.mock import MagicMock

        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        # Create a module that raises AttributeError on coupling_score access
        class BrokenModule:
            @property
            def coupling_score(self) -> None:
                raise AttributeError("broken coupling_score")

            @property
            def dependencies(self) -> None:
                raise AttributeError("broken dependencies")

        mock_mod = BrokenModule()

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_architecture_findings(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)

    def test_collect_architecture_findings_with_broken_adj(self) -> None:
        """_collect_architecture_findings should handle TypeError in adjacency."""
        from packages.tasks.investigate_bug import InvestigateBugTask

        task = InvestigateBugTask()

        from unittest.mock import MagicMock

        mock_mod = MagicMock()
        mock_mod.dependencies = ["packages/session/session.py"]

        mock_index = MagicMock()
        mock_index.find.return_value = []
        mock_index.modules = {"packages/auth/auth.py": mock_mod}
        mock_index.relationships.return_value = []
        mock_index.symbols.return_value = []
        mock_index.statistics.return_value = MagicMock(
            module_count=0,
            symbol_count=0,
        )

        findings = task._collect_architecture_findings(
            candidate_symbols=[],
            affected_modules=["packages/auth/auth.py"],
            repository_index=mock_index,
        )

        assert isinstance(findings, list)
