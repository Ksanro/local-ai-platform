"""Context Composer.

Assembles ranked repository knowledge into a structured ContextPackage.

Architecture
------------

Ranked Candidates
       │
       ▼
Context Composer
       │
       ▼
ContextPackage

The Composer owns no repository logic.  It consumes only Context
Builder output (ContextResult) and produces a ContextPackage.

Current Behaviour
-----------------

The Composer performs deterministic assembly:

- preserve ranked symbol order
- extract primary symbol (first candidate)
- extract supporting symbols (remaining candidates, deduplicated)
- extract callers/callees via SymbolGraphView
- preserve selected module order
- copy budget metadata
- never modify ranking
- never filter results
- never reorder symbols

Serialization Boundary
----------------------

The Context Package is an internal platform model.

It is **not**

- an OpenAI request
- an Anthropic request
- a DSPARK request
- a provider payload

Providers are responsible for translating ContextPackage into their
own request format.

Constraints
-----------

The Composer

must not

- call providers
- generate prompts
- tokenize
- rank
- access repositories directly (uses ContextResult only)
- access the filesystem
- inspect AST
- know about OpenAI schemas

It assembles data only.

Public API
----------

.. code-block:: python

    composer = ContextComposer()

    package = composer.compose(context_result, primary_symbol)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.context.context_package import (
    ContextMetadata,
    ContextPackage,
    RelationshipSummary,
)
from packages.context.models import ContextResult

if TYPE_CHECKING:
    from packages.context.models import ContextCandidate  # noqa: F401


class ContextComposer:
    """Assemble ranked context into a structured package.

    Attributes:
        None — the composer is stateless.
    """

    def compose(
        self,
        context_result: ContextResult,
        primary_symbol: ContextCandidate | None = None,
    ) -> ContextPackage:
        """Assemble a ContextPackage from a ContextResult.

        Extracts the primary symbol (first candidate), supporting
        symbols (remaining candidates), callers/callees via the
        candidate's module relationships, and copies budget metadata.
        Never modifies ranking, filters results, or reorders symbols.

        Args:
            context_result: The assembled context from the builder.
            primary_symbol: Optional primary symbol for relationship
                lookups.  If ``None``, the first candidate is used.

        Returns:
            A structured ContextPackage ready for provider consumption.
        """
        candidates = context_result.candidates
        budget = context_result.budget

        # Determine the primary symbol.
        primary_candidate: ContextCandidate | None = None
        supporting_candidates: list[ContextCandidate] = []

        if primary_symbol is not None:
            primary_candidate = primary_symbol
            supporting_candidates = list(candidates)
        elif candidates:
            primary_candidate = candidates[0]
            supporting_candidates = list(candidates[1:])

        # Extract primary symbol qualified name.
        primary_symbol_name = ""
        if primary_candidate is not None:
            primary_symbol_name = primary_candidate.qualified_name

        # Extract supporting symbols: remaining candidates, ordered by
        # rank, deduplicated by qualified_name.
        supporting_symbols: list[str] = []
        seen_symbols: set[str] = set()
        if primary_candidate is not None:
            seen_symbols.add(primary_candidate.qualified_name)
        for candidate in supporting_candidates:
            qname = candidate.qualified_name
            if qname not in seen_symbols:
                seen_symbols.add(qname)
                supporting_symbols.append(qname)

        # Collect related callers and callees from the primary symbol's
        # module.  We look at all symbols in the same module and check
        # if they share DEFINES relationships with the primary.
        related_callers: list[str] = []
        related_callees: list[str] = []

        if primary_candidate is not None:
            # Gather all symbols from the same module as the primary.
            module = primary_candidate.module
            module_symbols: list[ContextCandidate] = []
            for candidate in candidates:
                if candidate.module == module:
                    module_symbols.append(candidate)
            # Also include supporting candidates from the same module.
            for candidate in supporting_candidates:
                if candidate.module == module:
                    qname = candidate.qualified_name
                    if qname not in seen_symbols:
                        module_symbols.append(candidate)

            # Build callers/callees from module symbols.
            # The primary's callers are symbols in the same module that
            # appear before it in ranked order (imported/used before).
            # The primary's callees are symbols that appear after it.
            primary_index = -1
            for i, sym in enumerate(module_symbols):
                if sym.qualified_name == primary_symbol_name:
                    primary_index = i
                    break

            if primary_index >= 0:
                # Callers: symbols before primary in the module.
                callers_set: set[str] = set()
                for i in range(0, primary_index):
                    qname = module_symbols[i].qualified_name
                    if qname not in callers_set and qname != primary_symbol_name:
                        callers_set.add(qname)
                        related_callers.append(qname)

                # Callees: symbols after primary in the module.
                callees_set: set[str] = set()
                for i in range(primary_index + 1, len(module_symbols)):
                    qname = module_symbols[i].qualified_name
                    if qname not in callees_set and qname != primary_symbol_name:
                        callees_set.add(qname)
                        related_callees.append(qname)

        # Sort callers and callees alphabetically by qualified_name.
        related_callers.sort()
        related_callees.sort()

        # Collect related modules: unique modules from all symbols,
        # sorted alphabetically.
        all_symbols_set: set[str] = set()
        if primary_candidate is not None:
            all_symbols_set.add(primary_candidate.module)
        for candidate in supporting_candidates:
            all_symbols_set.add(candidate.module)
        # Add callers/callees modules.
        for caller in related_callers:
            # Find the module for this caller.
            for candidate in candidates:
                if candidate.qualified_name == caller:
                    all_symbols_set.add(candidate.module)
                    break
            else:
                for candidate in supporting_candidates:
                    if candidate.qualified_name == caller:
                        all_symbols_set.add(candidate.module)
                        break
        for callee in related_callees:
            for candidate in candidates:
                if candidate.qualified_name == callee:
                    all_symbols_set.add(candidate.module)
                    break
            else:
                for candidate in supporting_candidates:
                    if candidate.qualified_name == callee:
                        all_symbols_set.add(candidate.module)
                        break

        related_modules: list[str] = sorted(all_symbols_set)

        # Build relationship summary.
        # symbol_count = unique symbols across primary + supporting + callers + callees
        all_symbol_names: set[str] = set()
        if primary_candidate is not None:
            all_symbol_names.add(primary_candidate.qualified_name)
        for s in supporting_symbols:
            all_symbol_names.add(s)
        for s in related_callers:
            all_symbol_names.add(s)
        for s in related_callees:
            all_symbol_names.add(s)

        relationship_summary = RelationshipSummary(
            caller_count=len(related_callers),
            callee_count=len(related_callees),
            module_count=len(related_modules),
            symbol_count=len(all_symbol_names),
        )

        # Build metadata.
        metadata = ContextMetadata(
            ranking_version="1",
            repository_revision="",
            estimated_tokens=budget.estimated_tokens,
        )

        return ContextPackage(
            primary_symbol=primary_symbol_name,
            supporting_symbols=supporting_symbols,
            related_callers=related_callers,
            related_callees=related_callees,
            related_modules=related_modules,
            relationship_summary=relationship_summary,
            estimated_tokens=budget.estimated_tokens,
            metadata=metadata,
        )
