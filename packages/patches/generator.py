"""Patch Generator.

Consumes existing public APIs and produces PatchSet objects. The generator
never calls providers, parses repositories, builds context, or performs
planning.

Architecture
------------

WorkflowPlan      -->  \
ExecutionPlan     -->  PatchGenerator  -->  PatchSet
EvaluationReport  -->  /

Responsibilities
----------------

- Validate input types (public API compliance).
- Build deterministic PatchFile list from engineering artifacts.
- Compute statistics (files_changed, hunks, added_lines, removed_lines).
- Generate warnings for edge cases.
- Return immutable PatchSet.
- Eliminate duplicates.
- Produce deterministic ordering (sorted by file_path).

Non-responsibilities
--------------------

- No provider calls.
- No repository inspection.
- No AST parsing.
- No context building.
- No planning.
- No file writing.
- No git operations.
- No semantic evaluation.

Public API
----------

.. code-block:: python

    from packages.patches.generator import PatchGenerator

    patch_set = PatchGenerator.generate(
        workflow_plan=workflow_plan,
        execution_plan=execution_plan,
        evaluation_report=None,
    )

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
)

if TYPE_CHECKING:
    from packages.evaluation.models import EvaluationReport  # noqa: F401
    from packages.workflows.models import WorkflowPlan  # noqa: F401
    from packages.execution.models import ExecutionPlan  # noqa: F401

__all__ = [
    "PatchGenerator",
]


# ---------------------------------------------------------------------------
# PatchGenerator
# ---------------------------------------------------------------------------


class PatchGenerator:
    """Generates PatchSet from engineering artifacts.

    The generator consumes only public interfaces. It never knows
    which implementation is behind any input.

    Constraints
    -----------

    - Must NOT call providers.
    - Must NOT inspect repositories.
    - Must NOT parse AST.
    - Must NOT build context.
    - Must NOT perform planning.
    - Must NOT write files.
    - Must NOT execute git.
    - Must NOT modify inputs.
    - Must consume only public interfaces.
    - Must produce deterministic output.
    - Must eliminate duplicates.

    Usage
    -----

    .. code-block:: python

        from packages.patches.generator import PatchGenerator
        from packages.workflows.models import WorkflowPlan
        from packages.execution.models import ExecutionPlan

        patch_set = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
    """

    @staticmethod
    def generate(
        workflow_plan: Any,
        execution_plan: Any,
        evaluation_report: Any = None,
    ) -> PatchSet:
        """Generate a PatchSet from engineering artifacts.

        This is the main entry point for the PatchGenerator. It
        validates input types, extracts artifact information, builds
        deterministic PatchFile list, computes statistics, and returns
        an immutable PatchSet.

        Args:
            workflow_plan: A WorkflowPlan-like object with:
                - workflow_name: str
                - task_plans: tuple
                - workflow_steps: tuple
            execution_plan: An ExecutionPlan-like object with:
                - workflow_name: str
                - objective: str
                - execution_steps: tuple
                - context_package: object
            evaluation_report: Optional EvaluationReport-like object with:
                - workflow_name: str
                - task_name: str
                - overall_score: float
                - summary: str

        Returns:
            An immutable PatchSet with computed patches and statistics.

        Raises:
            ValueError: If required inputs are missing or invalid.
        """
        # Validate inputs
        if workflow_plan is None:
            raise ValueError("workflow_plan is required")
        if execution_plan is None:
            raise ValueError("execution_plan is required")

        # Extract workflow name
        workflow_name = _get_workflow_name(workflow_plan, execution_plan)

        # Extract execution ID
        execution_id = _get_execution_id(execution_plan)

        # Extract originating artifact references
        generated_from = _extract_artifact_references(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
            evaluation_report=evaluation_report,
        )

        # Build patch files from execution plan
        files = _build_patch_files(execution_plan)

        # Sort files deterministically by path
        files = tuple(sorted(files, key=lambda f: f.path))

        # Eliminate duplicate files (same path + same hunks)
        files = _eliminate_duplicates(files)

        # Compute statistics
        statistics = _compute_statistics(files)

        # Generate warnings
        warnings = _generate_warnings(files, statistics)

        # Convert files to tuple for immutability
        files_tuple = tuple(files)

        return PatchSet(
            workflow_name=workflow_name,
            execution_id=execution_id,
            generated_from=generated_from,
            files=files_tuple,
            statistics=statistics,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _get_workflow_name(
    workflow_plan: Any,
    execution_plan: Any,
) -> str:
    """Extract workflow name from available sources.

    Args:
        workflow_plan: WorkflowPlan-like object.
        execution_plan: ExecutionPlan-like object.

    Returns:
        Workflow name string.
    """
    name = getattr(workflow_plan, "workflow_name", None)
    if name:
        return name
    return getattr(execution_plan, "workflow_name", "unknown")


def _get_execution_id(execution_plan: Any) -> str:
    """Extract or generate execution ID from execution plan.

    Args:
        execution_plan: ExecutionPlan-like object.

    Returns:
        Execution ID string.
    """
    execution_id = getattr(execution_plan, "execution_id", None)
    if execution_id:
        return str(execution_id)

    # Generate a deterministic ID from workflow name + objective
    workflow_name = getattr(execution_plan, "workflow_name", "unknown")
    objective = getattr(execution_plan, "objective", "")
    return f"{workflow_name}-{objective}"


def _extract_artifact_references(
    workflow_plan: Any,
    execution_plan: Any,
    evaluation_report: Any = None,
) -> tuple[str, ...]:
    """Extract originating engineering artifact references.

    Args:
        workflow_plan: WorkflowPlan-like object.
        execution_plan: ExecutionPlan-like object.
        evaluation_report: Optional EvaluationReport-like object.

    Returns:
        Tuple of artifact reference strings.
    """
    references: list[str] = []

    # Workflow plan reference
    workflow_name = getattr(workflow_plan, "workflow_name", None)
    if workflow_name:
        references.append(f"workflow:{workflow_name}")

    # Execution plan reference
    execution_id = getattr(execution_plan, "execution_id", None)
    if execution_id:
        references.append(f"execution:{execution_id}")

    # Evaluation report reference (if provided)
    if evaluation_report is not None:
        eval_workflow = getattr(evaluation_report, "workflow_name", None)
        eval_task = getattr(evaluation_report, "task_name", None)
        if eval_workflow:
            references.append(f"evaluation:workflow:{eval_workflow}")
        if eval_task:
            references.append(f"evaluation:task:{eval_task}")

    return tuple(references)


def _build_patch_files(execution_plan: Any) -> list[PatchFile]:
    """Build PatchFile list from execution plan.

    Extracts patch information from the execution plan's steps
    and transforms them into deterministic PatchFile objects.

    Args:
        execution_plan: ExecutionPlan-like object.

    Returns:
        List of PatchFile objects.
    """
    files: list[PatchFile] = []

    # Extract steps from execution plan
    execution_steps = getattr(execution_plan, "execution_steps", ())
    constraints = getattr(execution_plan, "constraints", ())
    validation_requirements = getattr(execution_plan, "validation_requirements", ())

    # Group steps by file path to build hunks
    file_hunks: dict[str, list[PatchHunk]] = {}
    file_operations: dict[str, PatchOperation] = {}

    for step in execution_steps:
        # Extract file path from step
        file_path = getattr(step, "file_path", None)
        if file_path is None:
            continue

        # Extract operation type
        operation_str = getattr(step, "operation", "MODIFY")
        if isinstance(operation_str, str):
            try:
                operation = PatchOperation(operation_str.upper())
            except ValueError:
                operation = PatchOperation.MODIFY
        else:
            operation = PatchOperation.MODIFY

        # Extract diff lines
        diff_lines_raw = getattr(step, "diff_lines", ())
        if isinstance(diff_lines_raw, (list, tuple)):
            diff_lines = tuple(str(line) for line in diff_lines_raw)
        else:
            diff_lines = ()

        # Create hunk
        old_start = getattr(step, "old_start", 1)
        old_count = getattr(step, "old_count", 0)
        new_start = getattr(step, "new_start", 1)
        new_count = getattr(step, "new_count", 0)

        hunk = PatchHunk(
            file_path=file_path,
            old_start=int(old_start) if old_start else 1,
            old_count=int(old_count) if old_count else 0,
            new_start=int(new_start) if new_start else 1,
            new_count=int(new_count) if new_count else 0,
            diff_lines=diff_lines,
        )

        # Accumulate hunks by file
        if file_path not in file_hunks:
            file_hunks[file_path] = []
            file_operations[file_path] = operation
        file_hunks[file_path].append(hunk)

    # Build PatchFile objects
    for file_path in sorted(file_hunks.keys()):
        hunks = tuple(file_hunks[file_path])
        operation = file_operations[file_path]

        # Estimate changed lines from hunks
        estimated_changed_lines = 0
        for hunk in hunks:
            estimated_changed_lines += len(hunk.diff_lines)

        # Build metadata from constraints and validation requirements
        metadata: dict[str, Any] = {}
        if constraints:
            metadata["constraints"] = tuple(str(c) for c in constraints)
        if validation_requirements:
            metadata["validation_requirements"] = tuple(
                str(r) for r in validation_requirements
            )

        patch_file = PatchFile(
            path=file_path,
            operation=operation,
            hunks=hunks,
            estimated_changed_lines=estimated_changed_lines,
            metadata=metadata,
        )
        files.append(patch_file)

    return files


def _eliminate_duplicates(files: list[PatchFile]) -> list[PatchFile]:
    """Eliminate duplicate PatchFile entries.

    Two files are considered duplicates if they have the same path
    and identical hunks.

    Args:
        files: List of PatchFile objects.

    Returns:
        Deduplicated list of PatchFile objects.
    """
    seen: set[tuple[str, tuple]] = set()
    unique: list[PatchFile] = []

    for file in files:
        # Create a dedup key from path and hunk signatures
        hunk_signature = tuple(
            (h.file_path, h.old_start, h.old_count, h.new_start, h.new_count, h.diff_lines)
            for h in file.hunks
        )
        key = (file.path, hunk_signature)

        if key not in seen:
            seen.add(key)
            unique.append(file)

    return unique


def _compute_statistics(files: list[PatchFile]) -> PatchStatistics:
    """Compute aggregate statistics for a list of PatchFiles.

    Args:
        files: List of PatchFile objects.

    Returns:
        PatchStatistics with computed values.
    """
    files_changed = len(files)
    total_hunks = 0
    added_lines = 0
    removed_lines = 0
    modified_lines = 0

    for file in files:
        # Count hunks
        total_hunks += len(file.hunks)

        # Count modified lines (files with hunks are considered modified)
        if len(file.hunks) > 0:
            modified_lines += 1

        # Count added and removed lines from diff_lines
        for hunk in file.hunks:
            for line in hunk.diff_lines:
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed_lines += 1

    return PatchStatistics(
        files_changed=files_changed,
        hunks=total_hunks,
        added_lines=added_lines,
        removed_lines=removed_lines,
        modified_lines=modified_lines,
    )


def _generate_warnings(
    files: list[PatchFile],
    statistics: PatchStatistics,
) -> tuple[str, ...]:
    """Generate warnings for edge cases and potential issues.

    Args:
        files: List of PatchFile objects.
        statistics: Computed PatchStatistics.

    Returns:
        Tuple of warning message strings.
    """
    warnings: list[str] = []

    # Warn about empty patch set
    if len(files) == 0:
        warnings.append("PatchSet contains no files")
        return tuple(warnings)

    # Warn about files with no hunks
    for file in files:
        if len(file.hunks) == 0:
            warnings.append(f"File '{file.path}' has no hunks")

    # Warn about files with many hunks
    for file in files:
        if len(file.hunks) > 100:
            warnings.append(
                f"File '{file.path}' has {len(file.hunks)} hunks (consider splitting)"
            )

    # Warn about large changes
    if statistics.added_lines > 10000:
        warnings.append(
            f"PatchSet adds {statistics.added_lines} lines (consider smaller patches)"
        )
    if statistics.removed_lines > 10000:
        warnings.append(
            f"PatchSet removes {statistics.removed_lines} lines (consider smaller patches)"
        )

    return tuple(warnings)