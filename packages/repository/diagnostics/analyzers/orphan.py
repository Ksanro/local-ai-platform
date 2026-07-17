"""Orphan analyzer.

Detects modules that are never imported and disconnected from the
repository graph — no IMPORTS relationships connecting them to other
modules.

Modules excluded from orphan detection:
- ``__init__.py`` files (package roots).
- Top-level Python packages (e.g. ``package/__init__.py``).
- Modules directly under the repository root (no directory component).

Reason: Root modules are commonly imported by external code outside
the repository.

Algorithm: O(E + S) where E is the number of IMPORTS relationships
and S is the total number of symbols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.repository.diagnostics.analyzers.base import DiagnosticsAnalyzer
from packages.repository.diagnostics.models import OrphanModule, RepositoryDiagnostics
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import RelationshipType

if TYPE_CHECKING:
    pass


class OrphanAnalyzer(DiagnosticsAnalyzer):
    """Detects orphaned modules.

    A module is considered orphaned if:
    - It is never imported by any other module (no IMPORTS target).
    - It does not import any module (no IMPORTS source).
    - It is not an ``__init__.py`` file.
    - It is not a root-level module.

    Complexity: O(E + S) where E is the number of IMPORTS relationships
    and S is the total number of symbols.
    """

    @property
    def name(self) -> str:
        """Analyzer name."""
        return "orphan"

    def analyze(
        self,
        repository_index: RepositoryIndex,
    ) -> RepositoryDiagnostics:
        """Run orphan detection analysis.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A ``RepositoryDiagnostics`` with orphan findings.
        """
        # Determine which modules are __init__.py files (excluded).
        init_modules: set[str] = set()
        for mod in repository_index.modules_list():
            path = mod.path
            if path.endswith("/__init__.py") or path.endswith("\\__init__.py"):
                init_modules.add(path)

        # Determine root-level modules (no directory component).
        # These are excluded because they are commonly imported by
        # external code outside the repository.
        root_modules: set[str] = set()
        for mod in repository_index.modules_list():
            path = mod.path
            if "/" not in path and "\\" not in path:
                root_modules.add(path)

        # Build a set of all symbol qualified names and names that
        # participate in IMPORTS relationships.
        # Pre-build the set in O(E) then look up in O(1).
        connected_symbol_names: set[str] = set()
        for rel in repository_index.relationships():
            if rel.type == RelationshipType.IMPORTS:
                connected_symbol_names.add(rel.source)
                connected_symbol_names.add(rel.target)

        # Find orphan modules.
        orphans: list[OrphanModule] = []
        seen: set[str] = set()

        for mod in repository_index.modules_list():
            path = mod.path

            # Skip if already seen (dedup)
            if path in seen:
                continue
            seen.add(path)

            # Skip __init__.py files
            if path in init_modules:
                continue

            # Skip root-level modules
            if path in root_modules:
                continue

            # Check if any symbol in this module is connected via
            # IMPORTS relationships (by symbol name or qualified name).
            is_connected = any(
                sym.qualified_name in connected_symbol_names
                or sym.name in connected_symbol_names
                for sym in mod.symbols
            )

            if is_connected:
                continue

            orphans.append(OrphanModule(
                path=path,
                symbol_count=len(mod.symbols),
            ))

        # Sort by path for deterministic output.
        orphans.sort(key=lambda o: o.path)

        return RepositoryDiagnostics(
            orphan_modules=tuple(orphans),
        )
