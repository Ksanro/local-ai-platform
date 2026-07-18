"""Change Impact Analyzer.

Analyzes which repository elements are affected by modifying one or more
symbols. Uses only public Repository APIs — never parses Python, inspects
AST, performs filesystem traversal, or calls providers.

Architecture
------------

Changed Symbol
  ↓
Dependency Graph (RepositoryIndex relationships)
  ↓
Cross References (IMPORTS, INHERITS, DEFINES, CALLS)
  ↓
Impact Analyzer (BFS traversal, max_depth)
  ↓
Impact Report (ImpactReport with confidence)

Usage
-----

.. code-block:: python

    from packages.repository.impact.analyzer import ChangeImpactAnalyzer

    analyzer = ChangeImpactAnalyzer()

    report = analyzer.analyze(
        symbols=[
            "providers.factory.ProviderFactory"
        ],
        repository_index=index,
    )

    for node in report.impacted_symbols:
        print(f"{node.qualified_name} ({node.reason})")

Constraints
-----------

- Analysis only — no mutation of RepositoryIndex
- No Python parsing or AST inspection
- No filesystem traversal outside Repository public APIs
- No provider calls
- Deterministic traversal order (distance, qualified_name)
- Configurable maximum depth (default: 2)
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import RelationshipType

if TYPE_CHECKING:
    from collections.abc import Sequence

from packages.repository.impact.models import ImpactNode, ImpactReason, ImpactReport

# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------


def _compute_confidence(
    relationship_count: int,
    max_distance: int,
) -> float:
    """Compute a deterministic confidence value based on relationship properties.

    Confidence Formula
    ------------------
    - Direct relationships (distance=1) receive base_score=1.0
    - Transitive relationships (distance=2) receive base_score=0.8
    - Deeper relationships (distance>2) receive base_score=0.6
    - Zero relationships return 0.0 immediately

    confidence = base_score / (1 + (relationship_count - 1) * 0.1)

    The final value is clamped to [0.0, 1.0].

    Higher confidence means:
    - Closer relationship (lower distance)
    - Fewer relationships (more focused impact)

    Args:
        relationship_count: Total number of relationships in the impact set.
        max_distance: Maximum distance from root symbols.

    Returns:
        A float between 0.0 and 1.0 representing analysis confidence.
    """
    # Zero relationships means no impact, confidence is 0.0
    if relationship_count == 0:
        return 0.0

    # Determine base score by max distance
    if max_distance <= 1:
        base_score = 1.0
    elif max_distance <= 2:
        base_score = 0.8
    else:
        base_score = 0.6

    # Relationship count factor — more relationships = less confident
    penalty = 1 + (relationship_count - 1) * 0.1

    confidence = base_score / penalty

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, confidence))


# ---------------------------------------------------------------------------
# ChangeImpactAnalyzer
# ---------------------------------------------------------------------------


class ChangeImpactAnalyzer:
    """Analyzes which repository elements are affected by modifying symbols.

    Uses only public Repository APIs to traverse the dependency graph,
    cross-reference relationships, and produce an ImpactReport.

    The analyzer performs BFS traversal starting from root symbols through
    DEFINES, IMPORTS, INHERITS, and CALLS relationships up to a configurable
    maximum depth.

    Attributes:
        max_depth: Maximum BFS traversal depth. Default is 2.
            Use -1 for unlimited depth.
    """

    def __init__(self, max_depth: int = 2) -> None:
        """Initialize the analyzer.

        Args:
            max_depth: Maximum BFS traversal depth. Default is 2.
                Use -1 for unlimited depth.
        """
        if max_depth != -1 and max_depth < 1:
            raise ValueError("max_depth must be >= 1 or -1 for unlimited")
        self.max_depth = max_depth

    def analyze(
        self,
        symbols: Sequence[str],
        repository_index: RepositoryIndex,
    ) -> ImpactReport:
        """Analyze the impact of modifying one or more symbols.

        For each root symbol, the analyzer:
        1. Finds the symbol in the repository index
        2. Traverses DEFINES, IMPORTS, INHERITS, and CALLS relationships
        3. Computes transitive impacts up to max_depth
        4. Discovers linked test modules
        5. Computes deterministic confidence

        Args:
            symbols: List of fully qualified symbol names to analyze.
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            An ``ImpactReport`` with all impacted symbols, modules, tests,
            and confidence score.

        Raises:
            ValueError: If ``symbols`` is empty.
        """
        if not symbols:
            raise ValueError("symbols must contain at least one qualified name")

        # Validate and resolve root symbols
        resolved_roots: list[str] = []
        for name in symbols:
            found = repository_index.find(name)
            if found:
                resolved_roots.append(name)

        # If no symbols found, return empty report
        if not resolved_roots:
            return ImpactReport(
                root_symbols=tuple(symbols),
                impacted_symbols=tuple(),
                impacted_modules=tuple(),
                impacted_tests=tuple(),
                dependency_distance=0,
                confidence=0.0,
            )

        # BFS traversal — shared impacted dict so shorter paths win
        # Map: qualified_name -> (distance, reason)
        impacted: dict[str, tuple[int, ImpactReason]] = {}

        # Collect all relationship types to traverse
        rel_types = [
            RelationshipType.CALLS,
            RelationshipType.IMPORTS,
            RelationshipType.INHERITS,
            RelationshipType.DEFINES,
        ]

        for root_name in resolved_roots:
            for rel_type in rel_types:
                self._bfs_traverse(
                    start_name=root_name,
                    rel_type=rel_type,
                    direction="outgoing",
                    initial_distance=1,
                    repository_index=repository_index,
                    impacted=impacted,
                    max_depth=self.max_depth,
                )

                self._bfs_traverse(
                    start_name=root_name,
                    rel_type=rel_type,
                    direction="incoming",
                    initial_distance=1,
                    repository_index=repository_index,
                    impacted=impacted,
                    max_depth=self.max_depth,
                )

        # Build impact nodes
        impact_nodes: list[ImpactNode] = []
        modules: set[str] = set()

        for qname, (distance, reason) in impacted.items():
            # Get module info from the index
            symbol_list = repository_index.find(qname)
            module = symbol_list[0].module if symbol_list else ""

            node = ImpactNode(
                qualified_name=qname,
                module=module,
                distance=distance,
                reason=reason,
            )
            impact_nodes.append(node)
            if module:
                modules.add(module)

        # Sort by (distance, qualified_name)
        impact_nodes.sort()

        # Discover test modules
        test_modules = self._discover_tests(
            impacted, resolved_roots, repository_index
        )

        # Compute confidence
        max_distance = max((n.distance for n in impact_nodes), default=0)
        confidence = _compute_confidence(len(impacted), max_distance)

        # Compute dependency distance
        dependency_distance = max_distance

        return ImpactReport(
            root_symbols=tuple(resolved_roots),
            impacted_symbols=tuple(impact_nodes),
            impacted_modules=tuple(sorted(modules)),
            impacted_tests=tuple(sorted(test_modules)),
            dependency_distance=dependency_distance,
            confidence=confidence,
        )

    def _bfs_traverse(
        self,
        start_name: str,
        rel_type: RelationshipType,
        direction: str,
        initial_distance: int,
        repository_index: RepositoryIndex,
        impacted: dict[str, tuple[int, ImpactReason]],
        max_depth: int,
    ) -> None:
        """BFS traversal through relationships.

        Args:
            start_name: The qualified name to start from.
            rel_type: The relationship type to traverse.
            direction: ``"outgoing"`` or ``"incoming"``.
            initial_distance: The distance to assign to direct neighbors.
            repository_index: The repository index.
            impacted: Mutable dict of impacted symbols.
            max_depth: Maximum traversal depth.
        """
        relationships = repository_index.relationships()

        # Determine reason based on relationship type and direction
        if rel_type == RelationshipType.CALLS:
            reason: ImpactReason = "CALLEE" if direction == "outgoing" else "CALLER"
        elif rel_type == RelationshipType.IMPORTS:
            reason = "IMPORT"
        elif rel_type == RelationshipType.INHERITS:
            reason = "INHERITANCE"
        elif rel_type == RelationshipType.DEFINES:
            reason = "DEPENDENCY"
        else:
            reason = "DEPENDENCY"

        # BFS queue: (node_name, current_distance)
        queue: deque[tuple[str, int]] = deque()
        queue.append((start_name, 0))

        # Track visited nodes to avoid cycles.
        # Use the shared impacted dict as the visited set so that
        # shorter paths discovered in later traversals can still
        # propagate — nodes already in impacted are skipped here,
        # but _bfs_traverse callers update impacted directly when
        # they find a shorter path through the initial neighbors.
        visited: set[str] = set()

        while queue:
            current_name, current_dist = queue.popleft()

            if current_name in visited:
                continue
            visited.add(current_name)

            # Check if we've exceeded max depth
            if max_depth != -1 and current_dist >= max_depth:
                continue

            next_dist = current_dist + 1
            if next_dist > max_depth and max_depth != -1:
                continue

            # Find all matching relationships
            for rel in relationships:
                target_name = None

                if direction == "outgoing":
                    if rel.source == current_name and rel.type == rel_type:
                        target_name = rel.target
                else:  # incoming
                    if rel.target == current_name and rel.type == rel_type:
                        target_name = rel.source

                if target_name and target_name not in visited:
                    # Only add if not already in impacted, or if we found
                    # a shorter path to this node
                    if target_name not in impacted or next_dist < impacted[target_name][0]:
                        impacted[target_name] = (next_dist, reason)
                        queue.append((target_name, next_dist))

    def _discover_tests(
        self,
        impacted: dict[str, tuple[int, ImpactReason]],
        root_symbols: list[str],
        repository_index: RepositoryIndex,
    ) -> list[str]:
        """Discover test modules linked to impacted symbols.

        Uses existing Repository relationships only. No filename scanning.

        Args:
            impacted: Dict of impacted symbol names.
            root_symbols: List of root symbol names.
            repository_index: The repository index.

        Returns:
            List of test module paths.
        """
        test_modules: set[str] = set()

        # Check all relationships for connections to test modules
        for rel in repository_index.relationships():
            # Check if source is impacted or a root symbol
            source_in_scope = rel.source in impacted or rel.source in root_symbols
            target_in_scope = rel.target in impacted or rel.target in root_symbols

            if source_in_scope or target_in_scope:
                # Check both ends for test module paths
                for name in [rel.source, rel.target]:
                    symbol_list = repository_index.find(name)
                    if symbol_list:
                        for sym in symbol_list:
                            if self._is_test_path(sym.module):
                                test_modules.add(sym.module)

        return sorted(test_modules)

    @staticmethod
    def _is_test_path(module_path: str) -> bool:
        """Check if a module path appears to be a test module.

        Uses Repository relationship metadata only — no filesystem scanning.

        Args:
            module_path: The module path to check.

        Returns:
            True if the module appears to be a test module.
        """
        # Check if the module contains test-related symbol types
        # This is a heuristic based on Repository naming conventions
        return "/tests/" in module_path or module_path.startswith("tests/")
