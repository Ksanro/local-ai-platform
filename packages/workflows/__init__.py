"""Workflows package.

Workflow Engine v1 - Deterministic workflow orchestration.

Architecture
------------

Workflows compose Tasks into reusable engineering workflows.

They never:
- Perform repository analysis
- Perform planning themselves
- Invoke providers
- Edit source code

Public API
----------

.. code-block:: python

    from packages.workflows.base import Workflow
    from packages.workflows.factory import WorkflowFactory
    from packages.workflows.engine import WorkflowEngine
    from packages.workflows.models import (
        WorkflowMetrics,
        WorkflowNode,
        WorkflowPlan,
        WorkflowStep,
    )
    from packages.workflows.registry import WorkflowRegistry

    # Create registry and register workflows
    registry = WorkflowRegistry()
    registry.register("implement-feature", ImplementFeatureWorkflow)

    # Create factory
    factory = WorkflowFactory(registry)

    # Create workflow instance
    workflow = factory.create("implement-feature")

    # Create engine
    engine = WorkflowEngine()

    # Generate plan
    plan = engine.generate_plan(
        workflow=workflow,
        repository_index=repository_index,
        request=request,
    )

Workflow Engine v1
------------------

- **Workflow** — ABC that defines the interface for all workflows.
- **WorkflowNode** — DAG node with id, task, and dependencies.
- **WorkflowGraph** — DAG validation and topological sorting.
- **WorkflowRegistry** — manages registration, lookup, and discovery.
- **WorkflowFactory** — creates workflow instances through the registry.
- **WorkflowEngine** — orchestrates task planning in deterministic order.
- **WorkflowPlan** — complete execution plan for a workflow.

Future workflows
----------------

- PR Review
- Large Refactoring
- Feature Implementation
- API Migration
- Test Generation
- Security Audit
- Documentation Generation
- DSPARK

All new workflows require only one Workflow class + registration.
"""

from packages.workflows.base import Workflow
from packages.workflows.engine import WorkflowEngine
from packages.workflows.factory import WorkflowFactory
from packages.workflows.models import (
    WorkflowMetrics,
    WorkflowNode,
    WorkflowPlan,
    WorkflowStep,
)
from packages.workflows.registry import WorkflowRegistry

__all__ = [
    "Workflow",
    "WorkflowEngine",
    "WorkflowFactory",
    "WorkflowMetrics",
    "WorkflowNode",
    "WorkflowPlan",
    "WorkflowStep",
    "WorkflowRegistry",
]
