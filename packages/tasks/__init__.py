"""Tasks package.

Executable development workflow framework.

Architecture
------------

Tasks represent executable engineering workflows.

They consume existing capabilities and repository intelligence
to build deterministic execution plans.

Tasks do not invoke providers.
Tasks do not modify source code.
Tasks describe *what should happen*, not *how an LLM performs it*.

Public API
----------

.. code-block:: python

    from packages.tasks.base import Task
    from packages.tasks.factory import TaskFactory
    from packages.tasks.models import (
        TaskComplexity,
        TaskConstraint,
        TaskMetrics,
        TaskPlan,
        TaskRequest,
        TaskStep,
    )
    from packages.tasks.registry import TaskRegistry

    registry = TaskRegistry()
    registry.register("refactor", RefactorTask)

    factory = TaskFactory(registry)
    task = factory.create("refactor")

    request = TaskRequest(
        query="Refactor ProviderFactory",
        repository_root=".",
    )

    plan = task.plan(
        repository_index=index,
        request=request,
    )

Task Framework v1
-----------------

- **Task** — ABC that defines the interface for all tasks.
- **TaskRegistry** — manages registration, lookup, and discovery.
- **TaskFactory** — creates task instances through the registry.
- **TaskPlan** — immutable execution plan model.

Future tasks
------------

- Rename Symbol
- Move Class
- Extract Interface
- Generate Tests
- Review PR
- Implement Feature
- Migrate API
"""

from packages.tasks.base import Task
from packages.tasks.factory import TaskFactory
from packages.tasks.models import (
    TaskComplexity,
    TaskConstraint,
    TaskMetrics,
    TaskPlan,
    TaskRequest,
    TaskStep,
)
from packages.tasks.registry import TaskRegistry

__all__ = [
    "Task",
    "TaskComplexity",
    "TaskConstraint",
    "TaskFactory",
    "TaskMetrics",
    "TaskPlan",
    "TaskRequest",
    "TaskStep",
    "TaskRegistry",
]
