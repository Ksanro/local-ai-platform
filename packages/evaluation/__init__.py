"""Evaluation Framework package.

Deterministic evaluation of engineering workflow executions.

Architecture
------------

Engineering Workflow
    ↓
Execution
    ↓
Provider Response
    ↓
EvaluationReport

This framework measures quality of actual workflow executions.
It does NOT call providers, parse repositories, or perform planning.
It consumes only existing public APIs.

The EvaluationReport becomes the canonical quality artifact for every
engineering operation. Future Engineering Knowledge Graph versions
will persist these reports.

Public API
----------

.. code-block:: python

    from packages.evaluation import (
        EvaluationMetric,
        EvaluationScore,
        EvaluationReport,
        WorkflowEvaluator,
        register_metric,
        register_category,
    )

    report = WorkflowEvaluator.evaluate(
        workflow_plan=workflow_plan,
        execution_report=execution_report,
        capability_result=capability_result,
    )

Constraints
-----------

- Must NOT call providers
- Must NOT inspect repositories
- Must NOT perform AST analysis
- Must NOT duplicate diagnostics
- Must NOT duplicate architecture analysis
- Must NOT duplicate planning
- Must NOT duplicate workflows
- Everything must consume existing public APIs only

"""

from __future__ import annotations

from packages.evaluation.evaluator import WorkflowEvaluator
from packages.evaluation.models import (
    EvaluationMetric,
    EvaluationReport,
    EvaluationScore,
)
from packages.evaluation.registry import (
    register_category,
    register_metric,
)

__all__ = [
    # Models
    "EvaluationMetric",
    "EvaluationReport",
    "EvaluationScore",
    # Evaluator
    "WorkflowEvaluator",
    # Registry
    "register_category",
    "register_metric",
]