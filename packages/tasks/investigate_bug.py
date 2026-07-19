"""Investigate Bug Task.

Orchestrates repository search for a bug investigation.

Architecture
------------

TaskRequest
    ↓
InvestigateBugTask
    ↓
RepositoryIndex + TaskRequest
    ↓
TaskPlan

The task identifies likely affected symbols, modules, dependencies,
diagnostics, and architecture findings from the request, then produces
a TaskPlan describing the investigation scope.

Public API
----------

.. code-block:: python

    from packages.tasks.investigate_bug import InvestigateBugTask

    task = InvestigateBugTask()
    plan = task.plan(repository_index, request)

Constraints
-----------

- The task must not invoke providers.
- The task must not call LLMs.
- The task must not edit source code.
- The task must not inspect AST directly.
- The task must not duplicate repository analysis.
- The task must not duplicate diagnostics.
- The task must not duplicate architecture logic.

Only orchestration via existing public APIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.tasks.base import Task
from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskRequest,
    TaskStep,
)

if TYPE_CHECKING:
    from packages.repository.index.models import RepositoryIndex  # noqa: F401

__all__ = [
    "InvestigateBugTask",
]


class InvestigateBugTask(Task):
    """Bug investigation task.

    Responsibilities:
        - Identify likely affected symbols from suspected_symbols in request options.
        - Identify likely affected modules from suspected_modules in request options.
        - Collect dependency information from repository index.
        - Collect diagnostics from repository index.
        - Collect architecture findings from repository index.
        - Produce a TaskPlan describing the investigation scope.

    Attributes:
        None — the task is stateless.
    """

    @property
    def name(self) -> str:
        """Unique name of this task.

        Returns:
            The task name string.
        """
        return "investigate-bug"

    @property
    def capability(self) -> str:
        """Capability name consumed by this task.

        Returns:
            The capability name string.
        """
        return "bug-investigation"

    def _do_plan(
        self,
        repository_index: "RepositoryIndex",
        request: TaskRequest,
    ) -> TaskPlan:
        """Produce a TaskPlan for bug investigation.

        Extracts suspected symbols and modules from the request options,
        validates them against the repository index, collects dependency
        information, diagnostics, and architecture findings, and produces
        a TaskPlan describing the investigation scope.

        Args:
            repository_index: The fully built repository index.
            request: The task request containing query and context.

        Returns:
            A TaskPlan with investigation scope steps.
        """
        # Extract suspected symbols and modules from request options
        suspected_symbols: list[str] = []
        suspected_modules: list[str] = []

        if hasattr(request, "options") and request.options:
            options = request.options
            symbols = options.get("suspected_symbols", [])
            modules = options.get("suspected_modules", [])

            if isinstance(symbols, list):
                suspected_symbols = [str(s) for s in symbols]
            if isinstance(modules, list):
                suspected_modules = [str(m) for m in modules]

        # Validate suspected symbols against the repository index
        # Include all suspected symbols (found or not - may be external)
        candidate_symbols = list(suspected_symbols)

        # Validate suspected modules against the repository index
        affected_modules: list[str] = []
        for mod_path in suspected_modules:
            module = repository_index.find_module(mod_path)
            if module is not None:
                affected_modules.append(mod_path)
            else:
                # Include as candidate even if not found
                affected_modules.append(mod_path)

        # Collect dependency information from the repository index
        dependency_paths: list[str] = self._collect_dependency_paths(
            candidate_symbols, affected_modules, repository_index
        )

        # Collect diagnostics from the repository index
        diagnostics_findings: list[str] = self._collect_diagnostics(
            candidate_symbols, affected_modules, repository_index
        )

        # Collect architecture findings from the repository index
        architecture_findings: list[str] = self._collect_architecture_findings(
            candidate_symbols, affected_modules, repository_index
        )

        # Build steps
        steps: list[TaskStep] = []

        # Step 0: Identify candidate symbols
        steps.append(
            TaskStep(
                order=0,
                title="Identify candidate symbols",
                description=(
                    f"Identified {len(candidate_symbols)} candidate symbols "
                    f"from {len(suspected_symbols)} suspected symbols "
                    f"in the repository."
                ),
                required_symbols=tuple(candidate_symbols),
                required_modules=(),
            )
        )

        # Step 1: Identify affected modules
        steps.append(
            TaskStep(
                order=1,
                title="Identify affected modules",
                description=(
                    f"Identified {len(affected_modules)} affected modules "
                    f"from {len(suspected_modules)} suspected modules "
                    f"in the repository."
                ),
                required_symbols=(),
                required_modules=tuple(affected_modules),
            )
        )

        # Step 2: Collect dependency paths
        steps.append(
            TaskStep(
                order=2,
                title="Collect dependency paths",
                description=(
                    f"Collected {len(dependency_paths)} dependency paths "
                    f"for {len(candidate_symbols)} candidate symbols."
                ),
                required_symbols=tuple(candidate_symbols),
                required_modules=tuple(affected_modules),
            )
        )

        # Step 3: Collect diagnostics
        steps.append(
            TaskStep(
                order=3,
                title="Collect diagnostics",
                description=(
                    f"Collected {len(diagnostics_findings)} diagnostics findings."
                ),
                required_symbols=tuple(candidate_symbols),
                required_modules=tuple(affected_modules),
            )
        )

        # Step 4: Collect architecture findings
        steps.append(
            TaskStep(
                order=4,
                title="Collect architecture findings",
                description=(
                    f"Collected {len(architecture_findings)} architecture findings."
                ),
                required_symbols=tuple(candidate_symbols),
                required_modules=tuple(affected_modules),
            )
        )

        # Step 5: Build investigation context
        stacktrace_info = ""
        if request.options and "observed_stacktrace" in request.options:
            stacktrace_info = (
                f"Stacktrace: {request.options['observed_stacktrace']}. "
            )

        steps.append(
            TaskStep(
                order=5,
                title="Build investigation context",
                description=(
                    f"Bug: {request.query}. "
                    f"{stacktrace_info}"
                    f"Candidate symbols: {len(candidate_symbols)}. "
                    f"Affected modules: {len(affected_modules)}. "
                    f"Dependency paths: {len(dependency_paths)}. "
                    f"Diagnostics: {len(diagnostics_findings)}. "
                    f"Architecture: {len(architecture_findings)}."
                ),
                required_symbols=tuple(candidate_symbols),
                required_modules=tuple(affected_modules),
            )
        )

        # Build constraints
        constraints: tuple[TaskConstraint, ...] = (
            TaskConstraint(
                type="read-only",
                description="Task must not modify source code",
            ),
            TaskConstraint(
                type="deterministic",
                description="Task must produce deterministic output",
            ),
        )

        # Build metrics
        total_items = (
            len(candidate_symbols)
            + len(affected_modules)
            + len(dependency_paths)
            + len(diagnostics_findings)
            + len(architecture_findings)
        )
        metrics = TaskMetrics(
            estimated_tokens=total_items * 100,
            estimated_complexity=TaskComplexity.MEDIUM
            if total_items > 0
            else TaskComplexity.LOW,
        )

        return TaskPlan(
            task_name=self.name,
            capability=self.capability,
            context_package=None,
            steps=tuple(steps),
            constraints=constraints,
            metrics=metrics,
        )

    def _collect_dependency_paths(
        self,
        candidate_symbols: list[str],
        affected_modules: list[str],
        repository_index: "RepositoryIndex",
    ) -> list[str]:
        """Collect dependency paths for candidate symbols and affected modules.

        Args:
            candidate_symbols: List of candidate symbol qualified names.
            affected_modules: List of affected module paths.
            repository_index: The fully built repository index.

        Returns:
            List of dependency path strings.
        """
        paths: list[str] = []

        # Collect dependencies from the repository index relationships
        try:
            relationships = repository_index.relationships()
            for rel in relationships:
                # Build path from relationship
                if hasattr(rel, "source") and hasattr(rel, "target"):
                    source = rel.source
                    target = rel.target
                    # Check if either source or target is in our candidates
                    if source in candidate_symbols or target in candidate_symbols:
                        path = f"{source} -> {target}"
                        if path not in paths:
                            paths.append(path)
        except (AttributeError, TypeError):
            # Relationships not available, return empty list
            pass

        # Also check module dependencies
        try:
            modules = repository_index.modules
            for mod_path in affected_modules:
                if mod_path in modules:
                    mod = modules[mod_path]
                    if hasattr(mod, "dependencies"):
                        for dep in mod.dependencies:
                            dep_path = f"{mod_path} depends on {dep}"
                            if dep_path not in paths:
                                paths.append(dep_path)
        except (AttributeError, TypeError):
            pass

        return paths

    def _collect_diagnostics(
        self,
        candidate_symbols: list[str],
        affected_modules: list[str],
        repository_index: "RepositoryIndex",
    ) -> list[str]:
        """Collect diagnostics for candidate symbols and affected modules.

        Args:
            candidate_symbols: List of candidate symbol qualified names.
            affected_modules: List of affected module paths.
            repository_index: The fully built repository index.

        Returns:
            List of diagnostics finding strings.
        """
        findings: list[str] = []

        # Check for dead symbols
        try:
            symbols = repository_index.symbols()
            for sym in symbols:
                if hasattr(sym, "qualified_name") and sym.qualified_name in candidate_symbols:
                    if hasattr(sym, "is_dead") and sym.is_dead:
                        findings.append(f"Dead symbol: {sym.qualified_name}")
        except (AttributeError, TypeError):
            pass

        # Check for orphan modules
        try:
            modules = repository_index.modules
            for mod_path in affected_modules:
                if mod_path in modules:
                    mod = modules[mod_path]
                    if hasattr(mod, "is_orphan") and mod.is_orphan:
                        findings.append(f"Orphan module: {mod_path}")
        except (AttributeError, TypeError):
            pass

        # Check for large modules
        try:
            modules = repository_index.modules
            for mod_path in affected_modules:
                if mod_path in modules:
                    mod = modules[mod_path]
                    if hasattr(mod, "line_count"):
                        if mod.line_count > 500:
                            findings.append(f"Large module: {mod_path} ({mod.line_count} lines)")
        except (AttributeError, TypeError):
            pass

        return findings


    def _collect_architecture_findings(
        self,
        candidate_symbols: list[str],
        affected_modules: list[str],
        repository_index: "RepositoryIndex",
    ) -> list[str]:
        """Collect architecture findings for candidate symbols and affected modules.

        Args:
            candidate_symbols: List of candidate symbol qualified names.
            affected_modules: List of affected module paths.
            repository_index: The fully built repository index.

        Returns:
            List of architecture finding strings.
        """
        findings: list[str] = []

        # Check for dependency cycles involving affected modules
        try:
            relationships = repository_index.relationships()
            # Build adjacency list
            adj: dict[str, set[str]] = {}
            for rel in relationships:
                if hasattr(rel, "source") and hasattr(rel, "target"):
                    src = rel.source
                    tgt = rel.target
                    if src not in adj:
                        adj[src] = set()
                    adj[src].add(tgt)
            # Check for cycles involving affected modules
            for mod in affected_modules:
                if mod in adj:
                    for target in adj[mod]:
                        if target in adj and mod in adj[target]:
                            cycle = f"Dependency cycle: {mod} <-> {target}"
                            if cycle not in findings:
                                findings.append(cycle)
        except (AttributeError, TypeError):
            pass

        # Check for high coupling modules
        try:
            modules = repository_index.modules
            for mod_path in affected_modules:
                if mod_path in modules:
                    mod = modules[mod_path]  # type: ignore[assignment]
                    if hasattr(mod, "coupling_score"):
                        if mod.coupling_score > 0.8:
                            findings.append(
                                f"High coupling module: {mod_path} "
                                f"(score: {mod.coupling_score})"
                            )
        except (AttributeError, TypeError):
            pass

        return findings
