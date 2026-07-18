"""Change Impact Analyzer package.

Provides deterministic impact analysis for repository symbols.

Usage
-----

.. code-block:: python

    from packages.repository.impact import ChangeImpactAnalyzer, ImpactReport

    analyzer = ChangeImpactAnalyzer()

    report: ImpactReport = analyzer.analyze(
        symbols=["providers.factory.ProviderFactory"],
        repository_index=index,
    )

    for node in report.impacted_symbols:
        print(f"{node.qualified_name} ({node.reason})")

See packages/repository/impact/analyzer.py for full documentation.
"""

from __future__ import annotations

from packages.repository.impact.analyzer import ChangeImpactAnalyzer
from packages.repository.impact.models import ImpactNode, ImpactReport

__all__ = [
    "ChangeImpactAnalyzer",
    "ImpactNode",
    "ImpactReport",
]
