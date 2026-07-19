"""Built-in workflows.

Predefined workflow implementations that compose existing tasks.

Architecture
------------

Each workflow is a simple composition of tasks:

- ImplementFeatureWorkflow: Architecture → Impact → Implementation
- ReviewWorkflow: Architecture → Diagnostics → Review
- RefactorWorkflow: Impact Analysis → Refactoring Advisor → Refactor

Constraints
-----------

- Workflows are immutable (nodes tuple is fixed).
- Workflows are stateless (no instance attributes).
- Workflows orchestrate existing public APIs only.

Public API
----------

.. code-block:: python

    from packages.workflows.workflows.implement_feature import (
        ImplementFeatureWorkflow,
    )
    from packages.workflows.workflows.review import ReviewWorkflow
    from packages.workflows.workflows.refactor import RefactorWorkflow
"""

from packages.workflows.workflows.implement_feature import ImplementFeatureWorkflow
from packages.workflows.workflows.pull_request_review import (
    PullRequestReviewWorkflow,
)
from packages.workflows.workflows.refactor import RefactorWorkflow
from packages.workflows.workflows.review import ReviewWorkflow

__all__ = [
    "ImplementFeatureWorkflow",
    "PullRequestReviewWorkflow",
    "RefactorWorkflow",
    "ReviewWorkflow",
]
