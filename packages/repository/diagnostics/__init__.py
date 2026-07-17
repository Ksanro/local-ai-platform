"""Repository Diagnostics package.

Provides static analysis of the RepositoryIndex — dead code,
orphan modules, and statistics — without modifying the index or
performing any side effects.

Architecture
------------

::

    RepositoryIndex
        |
        v
    DiagnosticsEngine
        |
        +-- DeadCodeAnalyzer
        +-- LargeModuleAnalyzer
        +-- OrphanAnalyzer
        +-- ModuleStatisticsAnalyzer
        +-- GraphStatisticsAnalyzer
        |
        v
    RepositoryDiagnostics

Usage
---

Build a diagnostics result::

    from packages.repository.diagnostics.engine import DiagnosticsEngine
    from packages.repository.diagnostics.analyzers import (
        DeadCodeAnalyzer,
        LargeModuleAnalyzer,
        OrphanAnalyzer,
        ModuleStatisticsAnalyzer,
        GraphStatisticsAnalyzer,
    )

    engine = DiagnosticsEngine()
    engine.register(DeadCodeAnalyzer())
    engine.register(LargeModuleAnalyzer())
    engine.register(OrphanAnalyzer())
    engine.register(ModuleStatisticsAnalyzer())
    engine.register(GraphStatisticsAnalyzer())

    diagnostics = engine.analyze(repository_index)

    # Access results
    print(diagnostics.dead_symbols)       # tuple[DeadSymbol, ...]
    print(diagnostics.orphan_modules)     # tuple[OrphanModule, ...]
    print(diagnostics.large_modules)      # tuple[LargeModule, ...]
    print(diagnostics.module_statistics)  # ModuleStatistics
    print(diagnostics.graph_statistics)   # GraphStatistics

Extension
---------

Custom analyzers are added by subclassing :class:`.analyzers.base.DiagnosticsAnalyzer`
and registering with the engine::

    from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
    from packages.repository.diagnostics.models import RepositoryDiagnostics
    from packages.repository.index.models import RepositoryIndex

    class MyCustomAnalyzer(DiagnosticsAnalyzer):
        @property
        def name(self) -> str:
            return "my_custom"

        def analyze(self, repository_index: RepositoryIndex) -> RepositoryDiagnostics:
            # ... analysis logic ...
            return RepositoryDiagnostics()

    engine.register(MyCustomAnalyzer())

Deterministic guarantees
------------------------

All collections in ``RepositoryDiagnostics`` are sorted deterministically:

- ``dead_symbols`` — sorted by ``(qualified_name, module, lineno)``.
- ``orphan_modules`` — sorted by ``path``.
- ``large_modules`` — sorted by ``path``.
- ``warnings`` — sorted alphabetically.

Repeated execution on the same ``RepositoryIndex`` always produces
identical results.
"""

from __future__ import annotations

from packages.repository.diagnostics.engine import DiagnosticsEngine
from packages.repository.diagnostics.models import (
    DeadSymbol,
    DependencyCycle,
    GraphStatistics,
    LargeModule,
    ModuleStatistics,
    OrphanModule,
    RepositoryDiagnostics,
)

__all__ = [
    "DiagnosticsEngine",
    "DeadSymbol",
    "DependencyCycle",
    "GraphStatistics",
    "LargeModule",
    "ModuleStatistics",
    "OrphanModule",
    "RepositoryDiagnostics",
]
