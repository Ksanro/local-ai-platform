"""Architecture Review models.

Defines the immutable dataclasses that represent the architectural assessment
of a repository.  These models are the stable public contract for the
ArchitectureAnalyzer output.

Architecture
------------

RepositoryIndex
        │
        ▼
ModuleSummary (per module)
        │
        ▼
ArchitectureReview (composed)

Constraints
-----------

- Immutable (frozen=True, slots=True).
- No mutable state.
- No provider fields.
- No AI-generated content.

Public API
----------

.. code-block:: python

    from packages.architecture.models import ArchitectureReview, ModuleSummary

    review = ArchitectureReview(
        modules=(
            ModuleSummary(
                module="packages/architecture/models.py",
                symbol_count=5,
                dependency_count=2,
                dependent_count=3,
                instability_score=0.4,
            ),
        ),
        dependency_summary={"IMPORTS": 10, "INHERITS": 3},
        dependency_cycles=(),
        layering_violations=(),
        orphan_modules=(),
        high_coupling_modules=(),
        largest_components=(),
        diagnostics={"module_count": 50, "symbol_count": 200},
        impact_summary={},
        repository_statistics={"module_count": 50, "symbol_count": 200},
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ModuleSummary:
    """Summary of a single module's architectural properties.

    Attributes:
        module: File path relative to the repository root.
        symbol_count: Number of symbols defined in this module.
        dependency_count: Number of outgoing relationships (this module depends on others).
        dependent_count: Number of incoming relationships (other modules depend on this).
        instability_score: Ratio of outgoing to total relationships.
            0.0 = stable (all dependents, no dependencies).
            1.0 = unstable (all dependencies, no dependents).
            0.0-1.0 range.
    """

    module: str
    symbol_count: int
    dependency_count: int
    dependent_count: int
    instability_score: float

    def __post_init__(self) -> None:
        """Validate instability_score is in [0.0, 1.0]."""
        if not 0.0 <= self.instability_score <= 1.0:
            raise ValueError(
                f"ModuleSummary.instability_score must be in [0.0, 1.0], "
                f"got {self.instability_score}"
            )


@dataclass(frozen=True, slots=True)
class ArchitectureReview:
    """Complete architectural assessment of a repository.

    All collections are sorted deterministically — by module name or
    qualified name — so repeated execution produces identical output.

    Attributes:
        modules: All module summaries, sorted by module name.
        dependency_summary: Count of relationships by type.
        dependency_cycles: Detected circular dependency paths.
        layering_violations: Detected layering constraint violations.
        orphan_modules: Modules with zero relationships.
        high_coupling_modules: Modules with above-average total connections.
        largest_components: Modules with the most symbols.
        diagnostics: Repository diagnostic statistics.
        impact_summary: Change impact analysis summary.
        repository_statistics: Aggregate repository statistics.
    """

    modules: tuple[ModuleSummary, ...] = ()
    dependency_summary: dict[str, int] = field(default_factory=dict)
    dependency_cycles: tuple[str, ...] = ()
    layering_violations: tuple[str, ...] = ()
    orphan_modules: tuple[str, ...] = ()
    high_coupling_modules: tuple[ModuleSummary, ...] = ()
    largest_components: tuple[ModuleSummary, ...] = ()
    diagnostics: dict[str, int] = field(default_factory=dict)
    impact_summary: dict[str, object] = field(default_factory=dict)
    repository_statistics: dict[str, int] = field(default_factory=dict)
