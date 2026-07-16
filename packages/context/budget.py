"""Context Budget Engine.

Estimates whether assembled context fits within a token budget using
fixed constants.  No tokenization is performed — this is a lightweight
deterministic estimate suitable for budgeting decisions.

Architecture
------------

Ranked Candidates
        │
        ▼
ContextBudget
        │
        ▼
ContextBudgetResult

The Budget Engine is independent of ranking.  It consumes only ranked
candidates and never accesses source files.

Estimation Model
----------------

| Constant | Value |
|---|---:|
| Tokens per symbol | 80 |
| Tokens per module | 150 |

Formula::

    estimated_tokens = symbols * 80 + modules * 150

Constraints
-----------

- No filesystem access.
- No source code parsing.
- No AST, LLM, embedding, or DSPARK usage.
- No model-specific tokenizers.
- Pure function: same input always produces same output.

Public API
----------

.. code-block:: python

    engine = ContextBudget()
    budget = engine.estimate(candidates, modules, max_tokens=4096)
"""

from __future__ import annotations

from packages.context.models import ContextBudgetResult, ContextCandidate

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

TOKENS_PER_SYMBOL: int = 80
TOKENS_PER_MODULE: int = 150


class ContextBudget:
    """Estimate context size against a token budget.

    Attributes:
        None — the engine is stateless.
    """

    def estimate(
        self,
        candidates: list[ContextCandidate],
        modules: list[str],
        max_tokens: int,
    ) -> ContextBudgetResult:
        """Estimate whether the context fits within the token budget.

        Counts unique symbols and modules from the candidate list,
        applies fixed estimation constants, and reports whether the
        result fits within ``max_tokens``.

        Args:
            candidates: Ranked candidate symbols.
            modules: Unique module names selected for the context.
            max_tokens: Maximum allowed token count.

        Returns:
            A ``ContextBudgetResult`` with estimates and budget status.
        """
        # Count unique symbols by their symbol_id.
        seen_ids: set[str] = set()
        symbol_count = 0
        for candidate in candidates:
            if candidate.symbol_id not in seen_ids:
                seen_ids.add(candidate.symbol_id)
                symbol_count += 1

        module_count = len(modules)

        estimated_tokens = symbol_count * TOKENS_PER_SYMBOL + module_count * TOKENS_PER_MODULE

        return ContextBudgetResult(
            estimated_tokens=estimated_tokens,
            estimated_symbols=symbol_count,
            estimated_modules=module_count,
            within_budget=estimated_tokens <= max_tokens,
            truncated=estimated_tokens > max_tokens,
        )
