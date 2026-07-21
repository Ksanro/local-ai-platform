"""Data models for the Context Builder.

Defines the query, candidate, and result types that flow through the
Context Builder pipeline.  These models are the stable public contract
between the Builder and its consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.context.scoring import RankingReason


@dataclass(frozen=True)
class ContextQuery:
    """Parameters for a context-building request.

    Attributes:
        text: Natural-language description of the desired context.
        max_symbols: Maximum number of symbols to return.
        max_modules: Maximum number of unique modules in the result.
        max_tokens: Maximum token budget for the assembled context.
        maximum_depth: Maximum relationship traversal depth (from ContextPlan).
        relationship_expansion: Whether to expand relationships (from ContextPlan).
    """

    text: str
    max_symbols: int = 20
    max_modules: int = 10
    max_tokens: int = 4096
    maximum_depth: int = 1
    relationship_expansion: bool = True


@dataclass
class ContextCandidate:
    """A single symbol candidate for inclusion in context.

    Attributes:
        symbol_id: Canonical identifier for the symbol (equals ``qualified_name``).
        qualified_name: Fully qualified name relative to the repository root.
        module: Source file path relative to the repository root.
        score: Relevance score assigned by the ranking engine.
        reasons: Explainability signals for the assigned score.
        signature: Function/class signature line (Context Quality v2).
        docstring: Docstring content (Context Quality v2).
        decorators: List of decorator names (Context Quality v2).
        source: Complete source body for primary symbols, truncated preview for supporting.
        source_preview: Short excerpt for supporting symbols.
        location: Tuple of (module_path, start_line, end_line).
    """

    symbol_id: str
    qualified_name: str
    module: str
    score: int = 0
    reasons: list[RankingReason] = field(default_factory=list)
    signature: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    source: str = ""
    source_preview: str = ""
    location: tuple[str, int, int | None] | None = None


def _default_budget() -> ContextBudgetResult:
    """Return a zero-budget estimate for empty context."""
    return ContextBudgetResult(
        estimated_tokens=0,
        estimated_symbols=0,
        estimated_modules=0,
        within_budget=True,
        truncated=False,
    )


@dataclass(frozen=True)
class ContextBudgetResult:
    """Estimate of context size against a token budget.

    Attributes:
        estimated_tokens: Estimated token count for the context.
        estimated_symbols: Number of symbols in the context.
        estimated_modules: Number of unique modules in the context.
        within_budget: Whether the estimate fits within the budget.
        truncated: Whether the estimate exceeds the budget.
    """

    estimated_tokens: int = 0
    estimated_symbols: int = 0
    estimated_modules: int = 0
    within_budget: bool = True
    truncated: bool = False


@dataclass(frozen=True)
class ContextResult:
    """The result of a context-building request.

    Attributes:
        candidates: Ordered list of candidate symbols.
        selected_modules: Unique module names in insertion order, bounded by ``max_modules``.
        budget: Token budget estimate for the assembled context.
    """

    candidates: list[ContextCandidate] = field(default_factory=list)
    selected_modules: list[str] = field(default_factory=list)
    budget: ContextBudgetResult = field(default_factory=ContextBudgetResult)
