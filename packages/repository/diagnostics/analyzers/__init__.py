"""Diagnostics analyzers package.

Provides all built-in diagnostics analyzers.

Analyzers
---------

- ``DeadCodeAnalyzer`` — detects functions/methods with no callers.
- ``LargeModuleAnalyzer`` — detects modules with excessive symbol count.
- ``OrphanAnalyzer`` — detects orphaned modules.
- ``ModuleStatisticsAnalyzer`` — calculates module-level statistics.
- ``GraphStatisticsAnalyzer`` — calculates graph-level statistics.

Extension mechanism
-------------------

New analyzers are added by subclassing :class:`DiagnosticsAnalyzer`
and registering with the :class:`DiagnosticsEngine`:

    from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
    from packages.repository.diagnostics.models import RepositoryDiagnostics
    from packages.repository.index.models import RepositoryIndex

    class MyAnalyzer(DiagnosticsAnalyzer):
        @property
        def name(self) -> str:
            return "my_analyzer"

        def analyze(self, repository_index: RepositoryIndex) -> RepositoryDiagnostics:
            # ... analysis logic ...
            return RepositoryDiagnostics()

    engine = DiagnosticsEngine()
    engine.register(MyAnalyzer())
"""

from __future__ import annotations

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
from packages.repository.diagnostics.analyzers.graph_statistics import GraphStatisticsAnalyzer
from packages.repository.diagnostics.analyzers.large_modules import LargeModuleAnalyzer
from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer
from packages.repository.diagnostics.analyzers.statistics import ModuleStatisticsAnalyzer

__all__ = [
    "DiagnosticsAnalyzer",
    "DeadCodeAnalyzer",
    "LargeModuleAnalyzer",
    "OrphanAnalyzer",
    "ModuleStatisticsAnalyzer",
    "GraphStatisticsAnalyzer",
]
