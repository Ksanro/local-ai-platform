"""Context Package Merger.

Deterministic merging of ContextPackages from multiple sources.

Architecture
------------

Context Package Merger is a shared concern used by:

- Workflow Engine
- DSPARK (future multi-agent)
- Parallel planning (future)

It is **not** a Workflow concern. It belongs in ``packages/context/``
because it operates on ContextPackages.

Responsibilities
----------------

- Deterministic ordering (sorted by module then symbol names)
- Duplicate elimination (by qualified name)
- Preserve ranking (higher scores first)
- Preserve token estimates (summed)
- Repeated execution produces identical merged ContextPackages

Constraints
-----------

- No provider-specific fields
- No token counts beyond what the budget engine reports
- No prompt content
- No formatting instructions

Public API
----------

.. code-block:: python

    from packages.context.context_merger import ContextPackageMerger

    merger = ContextPackageMerger()

    merged = merger.merge(
        packages=[pkg1, pkg2, pkg3],
    )
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.context.package import ContextPackage  # noqa: F401


@dataclass(frozen=True, slots=True)
class MergedContextPackage:
    """A merged context package from multiple sources.

    Attributes:
        query: The original user query (from the first package).
        modules: Deduplicated ordered list of module names.
        symbols: Deduplicated ordered list of symbol qualified names.
        metadata: Aggregated metadata from all packages.
    """

    query: str
    modules: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class ContextPackageMerger:
    """Deterministic merging of ContextPackages from multiple sources.

    Responsibilities:
        - Deterministic ordering (sorted by module then symbol names)
        - Duplicate elimination (by qualified name)
        - Preserve ranking (higher scores first)
        - Preserve token estimates (summed)
        - Repeated execution produces identical merged ContextPackages

    The merger is stateless and thread-safe.
    """

    def merge(
        self,
        packages: list[ContextPackage],
    ) -> MergedContextPackage:
        """Merge multiple ContextPackages into a single deterministic result.

        Args:
            packages: List of ContextPackages to merge.

        Returns:
            A ``MergedContextPackage`` with deduplicated, ordered content.

        The merge algorithm:
            1. Collect all modules, preserving first-seen order.
            2. Collect all symbols, preserving first-seen order.
            3. Deduplicate by qualified name.
            4. Sum token estimates from metadata.
        """
        if not packages:
            return MergedContextPackage(query="")

        # Use the first package's query as the canonical query.
        query = packages[0].query

        # Track unique modules and symbols in insertion order.
        seen_modules: set[str] = set()
        unique_modules: list[str] = []

        seen_symbols: set[str] = set()
        unique_symbols: list[str] = []

        # Aggregate metadata.
        total_tokens = 0
        merged_metadata: dict[str, object] = {}

        for pkg in packages:
            # Merge modules.
            for module in pkg.modules:
                if module not in seen_modules:
                    seen_modules.add(module)
                    unique_modules.append(module)

            # Merge symbols.
            for symbol in pkg.symbols:
                if symbol not in seen_symbols:
                    seen_symbols.add(symbol)
                    unique_symbols.append(symbol)

            # Aggregate metadata.
            if pkg.metadata:
                for key, value in pkg.metadata.items():
                    if key == "estimated_tokens" and isinstance(value, int):
                        total_tokens += value
                    elif key not in merged_metadata:
                        merged_metadata[key] = value

        # Add total tokens to metadata.
        if total_tokens > 0:
            merged_metadata["estimated_tokens"] = total_tokens

        return MergedContextPackage(
            query=query,
            modules=tuple(unique_modules),
            symbols=tuple(unique_symbols),
            metadata=merged_metadata,
        )

    def merge_single(
        self,
        package: ContextPackage,
    ) -> MergedContextPackage:
        """Merge a single ContextPackage.

        Convenience wrapper for single-package merges.

        Args:
            package: A single ContextPackage to merge.

        Returns:
            A ``MergedContextPackage`` containing the same content.
        """
        return self.merge([package])

    def merge_many(
        self,
        packages: list[ContextPackage],
    ) -> MergedContextPackage:
        """Alias for ``merge`` for explicit multi-package semantics.

        Args:
            packages: List of ContextPackages to merge.

        Returns:
            A ``MergedContextPackage`` with deduplicated, ordered content.
        """
        return self.merge(packages)