"""Advisors package.

Provides deterministic analysis and recommendations for repository code.

Subpackages
-----------

.. code-block:: python

    from packages.advisors import refactoring

    # Refactoring recommendations based on repository analysis
    from packages.advisors.refactoring import RefactoringAdvisor

Public API
----------

.. code-block:: python

    from packages.advisors.refactoring import (
        RefactoringAdvisor,
        RefactoringReport,
        RefactoringCategory,
        Severity,
    )
"""

from __future__ import annotations

__all__ = ["refactoring"]
