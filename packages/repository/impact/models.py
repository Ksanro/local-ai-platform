"""Data models for the Change Impact Analyzer.

Defines immutable dataclasses that represent the output of impact analysis.
All collections are deterministic — sorted by qualified_name or distance
so consumers never depend on iteration order.

No source files are reparsed. No filesystem access. No AST inspection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

__all__ = [
    "ImpactNode",
    "ImpactReport",
]

# Allowed reason values for impact analysis relationships.
ImpactReason = Literal[
    "CALLER",
    "CALLEE",
    "IMPORT",
    "DEPENDENCY",
    "INHERITANCE",
    "TEST",
]


# ---------------------------------------------------------------------------
# ImpactNode
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImpactNode:
    """A single impacted symbol in the impact graph.

    Attributes:
        qualified_name: Fully qualified name of the symbol.
        module: Source file path relative to the repository root.
        distance: Hop distance from the root symbol (1 = direct, 2 = transitive).
        reason: Category of the relationship. One of CALLER, CALLEE, IMPORT,
            DEPENDENCY, INHERITANCE, TEST.
    """

    qualified_name: str
    module: str
    distance: int
    reason: ImpactReason

    def __lt__(self, other: ImpactNode) -> bool:
        """Support deterministic ordering by (distance, qualified_name).

        Args:
            other: Another ImpactNode to compare against.

        Returns:
            True if this node should precede other.
        """
        if self.distance != other.distance:
            return self.distance < other.distance
        return self.qualified_name < other.qualified_name


# ---------------------------------------------------------------------------
# ImpactReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImpactReport:
    """Complete impact analysis report for one or more root symbols.

    Attributes:
        root_symbols: Input symbols that were analyzed.
        impacted_symbols: All impacted symbols sorted by (distance, qualified_name).
        impacted_modules: Unique module paths sorted alphabetically.
        impacted_tests: Test module paths linked to impacted symbols.
        dependency_distance: Maximum distance in the impact graph.
        confidence: Deterministic confidence value 0.0-1.0.
        generated_at: ISO 8601 timestamp when the report was generated.

    Confidence Formula
    ------------------
    The confidence is computed deterministically based on:

    - Direct relationships (distance=1) receive base_score=1.0
    - Transitive relationships (distance=2) receive base_score=0.8
    - Deeper relationships (distance>2) receive base_score=0.6
    - Zero relationships produce 0.0

    confidence = base_score / (1 + (relationship_count - 1) * 0.1)

    The final value is clamped to [0.0, 1.0].

    Higher confidence means:
    - Closer relationship (lower distance)
    - Fewer relationships (more focused impact)
    """

    root_symbols: tuple[str, ...]
    impacted_symbols: tuple[ImpactNode, ...]
    impacted_modules: tuple[str, ...]
    impacted_tests: tuple[str, ...]
    dependency_distance: int
    confidence: float
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Ensure deterministic ordering and valid confidence range."""
        # Validate confidence range
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")

        # Ensure impacted_symbols are sorted by (distance, qualified_name)
        sorted_symbols = sorted(self.impacted_symbols)
        object.__setattr__(self, "impacted_symbols", tuple(sorted_symbols))

        # Ensure impacted_modules are sorted
        sorted_modules = tuple(sorted(self.impacted_modules))
        object.__setattr__(self, "impacted_modules", sorted_modules)

        # Ensure impacted_tests are sorted
        sorted_tests = tuple(sorted(self.impacted_tests))
        object.__setattr__(self, "impacted_tests", sorted_tests)

        # Ensure root_symbols are sorted
        sorted_roots = tuple(sorted(self.root_symbols))
        object.__setattr__(self, "root_symbols", sorted_roots)
