"""Tests for PatchGenerator.

Verifies:
- Deterministic generation
- Deterministic ordering
- Duplicate elimination
- Statistics correctness
- Warning generation
- Empty inputs
- Multiple files
- Multiple hunks
- Serialization compatibility
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from packages.patches.generator import PatchGenerator
from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
)


# ---------------------------------------------------------------------------
# Helpers — Mock objects that behave like real API objects
# ---------------------------------------------------------------------------


def _make_execution_step(
    file_path: str = "src/main.py",
    operation: str = "MODIFY",
    diff_lines: tuple[str, ...] = (),
    old_start: int = 1,
    old_count: int = 0,
    new_start: int = 1,
    new_count: int = 0,
) -> MagicMock:
    """Create a mock execution step."""
    step = MagicMock()
    step.file_path = file_path
    step.operation = operation
    step.diff_lines = diff_lines
    step.old_start = old_start
    step.old_count = old_count
    step.new_start = new_start
    step.new_count = new_count
    return step


def _make_workflow_plan(workflow_name: str = "test_workflow") -> MagicMock:
    """Create a mock WorkflowPlan."""
    plan = MagicMock()
    plan.workflow_name = workflow_name
    plan.task_plans = ()
    plan.workflow_steps = ()
    return plan


def _make_execution_plan(
    workflow_name: str = "test_workflow",
    objective: str = "test objective",
    steps: tuple[MagicMock, ...] = (),
    execution_id: str = "exec-001",
    constraints: tuple = (),
    validation_requirements: tuple = (),
) -> MagicMock:
    """Create a mock ExecutionPlan."""
    plan = MagicMock()
    plan.workflow_name = workflow_name
    plan.objective = objective
    plan.execution_steps = steps
    plan.execution_id = execution_id
    plan.constraints = constraints
    plan.validation_requirements = validation_requirements
    plan.context_package = None
    return plan


def _make_evaluation_report(
    workflow_name: str = "test_workflow",
    task_name: str = "test-task",
) -> MagicMock:
    """Create a mock EvaluationReport."""
    report = MagicMock()
    report.workflow_name = workflow_name
    report.task_name = task_name
    report.overall_score = 0.85
    report.summary = "Good execution."
    return report


# ---------------------------------------------------------------------------
# Test: Input Validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Tests for input validation."""

    def test_none_workflow_plan_raises(self) -> None:
        """generate should raise ValueError if workflow_plan is None."""
        with pytest.raises(ValueError, match="workflow_plan is required"):
            PatchGenerator.generate(
                workflow_plan=None,
                execution_plan=_make_execution_plan(),
            )

    def test_none_execution_plan_raises(self) -> None:
        """generate should raise ValueError if execution_plan is None."""
        with pytest.raises(ValueError, match="execution_plan is required"):
            PatchGenerator.generate(
                workflow_plan=_make_workflow_plan(),
                execution_plan=None,
            )


# ---------------------------------------------------------------------------
# Test: Deterministic Generation
# ---------------------------------------------------------------------------


class TestDeterministicGeneration:
    """Tests for deterministic generation."""

    def test_deterministic_output(self) -> None:
        """Same inputs should produce identical PatchSets."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ new line\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps1 = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
        ps2 = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps1.workflow_name == ps2.workflow_name
        assert ps1.execution_id == ps2.execution_id
        assert len(ps1.files) == len(ps2.files)
        assert ps1.files[0].path == ps2.files[0].path
        assert ps1.files[0].operation == ps2.files[0].operation

    def test_deterministic_ordering(self) -> None:
        """Files should be sorted by path."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(file_path="src/z_file.py", operation="MODIFY"),
            _make_execution_step(file_path="src/a_file.py", operation="MODIFY"),
            _make_execution_step(file_path="src/m_file.py", operation="MODIFY"),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        paths = [f.path for f in ps.files]
        assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# Test: Duplicate Elimination
# ---------------------------------------------------------------------------


class TestDuplicateElimination:
    """Tests for duplicate elimination."""

    def test_duplicate_files_eliminated(self) -> None:
        """Duplicate file entries should be eliminated."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line1\n",),
            ),
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line1\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        # Should have only one file
        assert len(ps.files) == 1
        assert ps.files[0].path == "src/main.py"

    def test_different_hunks_preserved(self) -> None:
        """Files with different hunks should both be preserved."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line1\n",),
            ),
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line2\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        # Both should be preserved (different hunks)
        assert len(ps.files) == 1
        assert len(ps.files[0].hunks) == 2


# ---------------------------------------------------------------------------
# Test: Statistics Correctness
# ---------------------------------------------------------------------------


class TestStatisticsCorrectness:
    """Tests for statistics correctness."""

    def test_empty_patch_set_statistics(self) -> None:
        """Empty PatchSet should have zero statistics."""
        workflow_plan = _make_workflow_plan()
        execution_plan = _make_execution_plan(steps=())

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps.statistics.files_changed == 0
        assert ps.statistics.hunks == 0
        assert ps.statistics.added_lines == 0
        assert ps.statistics.removed_lines == 0
        assert ps.statistics.modified_lines == 0

    def test_single_file_statistics(self) -> None:
        """Single file statistics should be correct."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ added\n", "- removed\n", " context\n"),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps.statistics.files_changed == 1
        assert ps.statistics.hunks == 1
        assert ps.statistics.added_lines == 1
        assert ps.statistics.removed_lines == 1
        assert ps.statistics.modified_lines == 1

    def test_multiple_files_statistics(self) -> None:
        """Multiple files statistics should be correct."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line1\n",),
            ),
            _make_execution_step(
                file_path="src/other.py",
                operation="MODIFY",
                diff_lines=("+ line2\n", "+ line3\n"),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps.statistics.files_changed == 2
        assert ps.statistics.hunks == 2
        assert ps.statistics.added_lines == 3
        assert ps.statistics.removed_lines == 0
        assert ps.statistics.modified_lines == 2


# ---------------------------------------------------------------------------
# Test: Warning Generation
# ---------------------------------------------------------------------------


class TestWarningGeneration:
    """Tests for warning generation."""

    def test_empty_patch_set_warning(self) -> None:
        """Empty PatchSet should generate a warning."""
        workflow_plan = _make_workflow_plan()
        execution_plan = _make_execution_plan(steps=())

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert "PatchSet contains no files" in ps.warnings

    def test_no_warning_for_valid_patch(self) -> None:
        """Valid PatchSet should have no warnings."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        # No warnings for valid small patch
        assert len(ps.warnings) == 0


# ---------------------------------------------------------------------------
# Test: Artifact References
# ---------------------------------------------------------------------------


class TestArtifactReferences:
    """Tests for artifact reference extraction."""

    def test_generated_from_without_evaluation(self) -> None:
        """generated_from should include workflow and execution references."""
        workflow_plan = _make_workflow_plan(workflow_name="my-workflow")
        execution_plan = _make_execution_plan(
            workflow_name="my-workflow",
            execution_id="exec-123",
        )

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert "workflow:my-workflow" in ps.generated_from
        assert "execution:exec-123" in ps.generated_from

    def test_generated_from_with_evaluation(self) -> None:
        """generated_from should include evaluation reference when provided."""
        workflow_plan = _make_workflow_plan(workflow_name="my-workflow")
        execution_plan = _make_execution_plan(
            workflow_name="my-workflow",
            execution_id="exec-123",
        )
        eval_report = _make_evaluation_report(
            workflow_name="my-workflow",
            task_name="test-task",
        )

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
            evaluation_report=eval_report,
        )

        assert "workflow:my-workflow" in ps.generated_from
        assert "execution:exec-123" in ps.generated_from
        assert "evaluation:workflow:my-workflow" in ps.generated_from
        assert "evaluation:task:test-task" in ps.generated_from


# ---------------------------------------------------------------------------
# Test: Multiple Files
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    """Tests for multiple file handling."""

    def test_multiple_files_sorted(self) -> None:
        """Multiple files should be sorted by path."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(file_path="z.py", operation="ADD"),
            _make_execution_step(file_path="a.py", operation="ADD"),
            _make_execution_step(file_path="m.py", operation="MODIFY"),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        paths = [f.path for f in ps.files]
        assert paths == ["a.py", "m.py", "z.py"]

    def test_multiple_hunks_per_file(self) -> None:
        """Multiple hunks for the same file should be accumulated."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line1\n",),
            ),
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line2\n",),
            ),
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line3\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 1
        assert len(ps.files[0].hunks) == 3


# ---------------------------------------------------------------------------
# Test: Stable Ordering
# ---------------------------------------------------------------------------


class TestStableOrdering:
    """Tests for stable ordering."""

    def test_stable_ordering_across_calls(self) -> None:
        """Ordering should be stable across multiple calls."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(file_path="c.py", operation="ADD"),
            _make_execution_step(file_path="a.py", operation="ADD"),
            _make_execution_step(file_path="b.py", operation="ADD"),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps1 = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
        ps2 = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
        ps3 = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert [f.path for f in ps1.files] == [f.path for f in ps2.files]
        assert [f.path for f in ps2.files] == [f.path for f in ps3.files]


# ---------------------------------------------------------------------------
# Test: Workflow Name Extraction
# ---------------------------------------------------------------------------


class TestWorkflowNameExtraction:
    """Tests for workflow name extraction."""

    def test_workflow_name_from_workflow_plan(self) -> None:
        """Workflow name should be extracted from workflow_plan."""
        workflow_plan = _make_workflow_plan(workflow_name="my-workflow")
        execution_plan = _make_execution_plan(workflow_name="other-workflow")

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps.workflow_name == "my-workflow"

    def test_workflow_name_fallback(self) -> None:
        """Workflow name should fall back to execution_plan."""
        workflow_plan = _make_workflow_plan()
        workflow_plan.workflow_name = ""
        execution_plan = _make_execution_plan(workflow_name="fallback")

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert ps.workflow_name == "fallback"


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_execution_steps(self) -> None:
        """Empty execution steps should produce empty PatchSet."""
        workflow_plan = _make_workflow_plan()
        execution_plan = _make_execution_plan(steps=())

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 0

    def test_step_without_file_path(self) -> None:
        """Steps without file_path should be skipped."""
        workflow_plan = _make_workflow_plan()
        step = MagicMock()
        step.file_path = None
        step.operation = "MODIFY"
        step.diff_lines = ()
        step.old_start = 0
        step.old_count = 0
        step.new_start = 0
        step.new_count = 0

        execution_plan = _make_execution_plan(steps=(step,))

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 0

    def test_unicode_in_file_path(self) -> None:
        """Unicode in file paths should be handled."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/\u4f60\u597d.py",
                operation="ADD",
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 1
        assert ps.files[0].path == "src/\u4f60\u597d.py"

    def test_all_operations_supported(self) -> None:
        """All PatchOperation values should be supported."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(file_path="add.py", operation="ADD"),
            _make_execution_step(file_path="delete.py", operation="DELETE"),
            _make_execution_step(file_path="modify.py", operation="MODIFY"),
            _make_execution_step(file_path="rename.py", operation="RENAME"),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 4
        operations = {f.operation for f in ps.files}
        assert operations == {PatchOperation.ADD, PatchOperation.DELETE, PatchOperation.MODIFY, PatchOperation.RENAME}

    def test_invalid_operation_defaults_to_modify(self) -> None:
        """Invalid operation should default to MODIFY."""
        workflow_plan = _make_workflow_plan()
        step = _make_execution_step(file_path="test.py", operation="INVALID_OP")
        # The generator tries to parse the operation, falls back to MODIFY
        execution_plan = _make_execution_plan(steps=(step,))

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        assert len(ps.files) == 1
        # Should be MODIFY since INVALID_OP is not a valid PatchOperation
        assert ps.files[0].operation == PatchOperation.MODIFY

    def test_constraints_in_metadata(self) -> None:
        """Constraints should appear in PatchFile metadata."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ content\n",),
            ),
        )
        execution_plan = _make_execution_plan(
            steps=steps,
            constraints=("constraint-a", "constraint-b"),
            validation_requirements=("requirement-x",),
        )

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
        assert len(ps.files) == 1
        file_meta = ps.files[0].metadata
        assert "constraints" in file_meta
        assert "validation_requirements" in file_meta

    def test_validation_requirements_in_metadata(self) -> None:
        """Validation requirements should appear in PatchFile metadata."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ content\n",),
            ),
        )
        execution_plan = _make_execution_plan(
            steps=steps,
            validation_requirements=("req-1", "req-2"),
        )

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )
        assert len(ps.files) == 1
        file_meta = ps.files[0].metadata
        assert "validation_requirements" in file_meta


# ---------------------------------------------------------------------------
# Test: Serialization Compatibility
# ---------------------------------------------------------------------------


class TestSerializationCompatibility:
    """Tests for serialization compatibility."""

    def test_patch_set_is_serializable(self) -> None:
        """PatchSet should be serializable (all fields are basic types)."""
        workflow_plan = _make_workflow_plan()
        steps = (
            _make_execution_step(
                file_path="src/main.py",
                operation="MODIFY",
                diff_lines=("+ line\n",),
            ),
        )
        execution_plan = _make_execution_plan(steps=steps)

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        # All fields should be basic types that are JSON-serializable
        assert isinstance(ps.workflow_name, str)
        assert isinstance(ps.execution_id, str)
        assert isinstance(ps.generated_from, tuple)
        assert isinstance(ps.files, tuple)
        assert isinstance(ps.statistics, PatchStatistics)
        assert isinstance(ps.warnings, tuple)

        # Check file fields
        for f in ps.files:
            assert isinstance(f.path, str)
            assert isinstance(f.operation, PatchOperation)
            assert isinstance(f.hunks, tuple)
            assert isinstance(f.estimated_changed_lines, int)
            assert isinstance(f.metadata, dict)

    def test_patch_set_dataclass_fields(self) -> None:
        """PatchSet should have all expected dataclass fields."""
        workflow_plan = _make_workflow_plan()
        execution_plan = _make_execution_plan()

        ps = PatchGenerator.generate(
            workflow_plan=workflow_plan,
            execution_plan=execution_plan,
        )

        # Verify all required fields exist
        assert hasattr(ps, "workflow_name")
        assert hasattr(ps, "execution_id")
        assert hasattr(ps, "generated_from")
        assert hasattr(ps, "files")
        assert hasattr(ps, "statistics")
        assert hasattr(ps, "warnings")