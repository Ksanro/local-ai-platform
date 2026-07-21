"""Context Budget Engine.

Estimates whether assembled context fits within a token budget using
actual content analysis rather than fixed per-unit estimates.

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

Context Quality v2
------------------

The budget engine now estimates tokens from the ACTUAL assembled content
(source code, signatures, docstrings) rather than using fixed constants.
This provides much more accurate estimates that closely match provider
usage.

Future work: integrate a proper tokenizer for language-aware estimation.

Estimation Model
----------------

| Constant | Value |
|---|---:|
| Characters per token | 4.0 |

Formula::

    estimated_tokens = total_content_chars / 4.0

Where total_content_chars includes source code, signatures, docstrings,
and module paths from all candidates.

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

# Character-to-token ratio for estimation.
# For English text and Python code, approximately 4 characters per token.
# This is a rough heuristic — future tokenizer integration will improve accuracy.
CHARS_PER_TOKEN: float = 4.0


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

        Estimates token count from the ACTUAL assembled content:

        - Source code bodies (primary symbols)
        - Source previews (supporting symbols)
        - Signatures and docstrings
        - Module paths and metadata

        Args:
            candidates: Ranked candidate symbols (enriched with source data).
            modules: Unique module names selected for the context.
            max_tokens: Maximum allowed token count.

        Returns:
            A ``ContextBudgetResult`` with estimates and budget status.
        """
        # Estimate tokens from actual content (Context Quality v2).
        total_chars = 0

        for candidate in candidates:
            # Source body (primary symbols have full source).
            if candidate.source:
                total_chars += len(candidate.source)

            # Source preview (supporting symbols).
            if candidate.source_preview:
                total_chars += len(candidate.source_preview)

            # Signature and docstring.
            if candidate.signature:
                total_chars += len(candidate.signature)
            if candidate.docstring:
                total_chars += len(candidate.docstring)

            # Symbol name and module path.
            total_chars += len(candidate.qualified_name)
            total_chars += len(candidate.module)

        # Add module path overhead.
        for module in modules:
            total_chars += len(module)

        # Convert characters to estimated tokens.
        estimated_tokens = (
            int(total_chars / CHARS_PER_TOKEN) if total_chars > 0 else 0
        )

        # Count unique symbols.
        seen_ids: set[str] = set()
        symbol_count = 0
        for candidate in candidates:
            if candidate.symbol_id not in seen_ids:
                seen_ids.add(candidate.symbol_id)
                symbol_count += 1

        module_count = len(modules)

        return ContextBudgetResult(
            estimated_tokens=estimated_tokens,
            estimated_symbols=symbol_count,
            estimated_modules=module_count,
            within_budget=estimated_tokens <= max_tokens,
            truncated=estimated_tokens > max_tokens,
        )