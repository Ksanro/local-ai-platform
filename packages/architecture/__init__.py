"""Architecture package.

Public API
----------

.. code-block:: python

    from packages.architecture import ArchitectureAnalyzer, ArchitectureReview, ModuleSummary

    analyzer = ArchitectureAnalyzer()
    review = analyzer.analyze(repository_index)
"""

from __future__ import annotations

from packages.architecture.analyzer import ArchitectureAnalyzer
from packages.architecture.models import ArchitectureReview, ModuleSummary

__all__ = [
    "ArchitectureAnalyzer",
    "ArchitectureReview",
    "ModuleSummary",
]
