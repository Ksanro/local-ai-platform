"""Patch Generator package.

Deterministic transformation of engineering artifacts into immutable patch
descriptions. The Patch Generator is an engineering artifact generator.

Architecture
------------

WorkflowPlan      -->  \
ExecutionPlan     -->  PatchGenerator  -->  PatchSet
EvaluationReport  -->  /

This framework converts engineering artifacts (WorkflowPlan, ExecutionPlan,
EvaluationReport) into immutable patch descriptions (PatchSet) that become
the ONLY contract consumed later by the Code Modification Engine.

Responsibilities
----------------

- Transform engineering artifacts into PatchSet
- Produce deterministic, ordered output
- Compute patch statistics
- Generate warnings for edge cases
- Eliminate duplicates

Non-responsibilities
--------------------

- Must NOT modify source code
- Must NOT parse repositories
- Must NOT execute providers
- Must NOT execute shell commands
- Must NOT duplicate repository intelligence

Public API
----------

.. code-block:: python

    from packages.patches import (
        PatchFile,
        PatchHunk,
        PatchOperation,
        PatchSet,
        PatchStatistics,
        ValidationResult,
        PatchGenerator,
        PatchFormatter,
        PatchValidator,
    )

    # Generate
    patch_set = PatchGenerator.generate(
        workflow_plan=workflow_plan,
        execution_plan=execution_plan,
        evaluation_report=None,
    )

    # Format
    diff_text = PatchFormatter.format(patch_set)

    # Validate
    result = PatchValidator.validate(patch_set)

"""

from __future__ import annotations

from packages.patches.formatter import PatchFormatter
from packages.patches.generator import PatchGenerator
from packages.patches.models import (
    PatchFile,
    PatchHunk,
    PatchOperation,
    PatchSet,
    PatchStatistics,
    ValidationResult,
)
from packages.patches.validator import PatchValidator

__all__ = [
    # Models
    "PatchFile",
    "PatchHunk",
    "PatchOperation",
    "PatchSet",
    "PatchStatistics",
    "ValidationResult",
    # Generator
    "PatchGenerator",
    # Formatter
    "PatchFormatter",
    # Validator
    "PatchValidator",
]