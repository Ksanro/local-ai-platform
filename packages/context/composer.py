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

Context Quality v2
------------------

The Composer now builds source-aware context:

- ``primary_symbol_context``: Full ``SymbolContext`` for the primary symbol
- ``supporting_symbol_contexts``: ``SymbolContext`` list for supporting symbols
- ``module_descriptions``: Purpose summaries for related modules

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
    ModuleDescription,
    RelationshipSummary,
    SymbolContext,
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

        Context Quality v2: also builds source-aware context from
        enriched candidates (signature, docstring, source, location).

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

        # Context Quality v2: Build source-aware context.
        primary_symbol_context: SymbolContext | None = None
        supporting_symbol_contexts: list[SymbolContext] = []

        if primary_candidate is not None:
            primary_symbol_context = SymbolContext(
                qualified_name=primary_candidate.qualified_name,
                signature=primary_candidate.signature or "",
                docstring=primary_candidate.docstring or "",
                decorators=primary_candidate.decorators or [],
                source=primary_candidate.source or "",
                source_preview=primary_candidate.source_preview or "",
                location=primary_candidate.location,
            )

        for candidate in supporting_candidates:
            supporting_symbol_contexts.append(
                SymbolContext(
                    qualified_name=candidate.qualified_name,
                    signature=candidate.signature or "",
                    docstring=candidate.docstring or "",
                    decorators=candidate.decorators or [],
                    source=candidate.source or "",
                    source_preview=candidate.source_preview or "",
                    location=candidate.location,
                )
            )

        # Build module descriptions.
        module_descriptions: list[ModuleDescription] = []
        for mod_path in related_modules:
            # Count symbols from this module.
            mod_symbol_count = 0
            if primary_candidate and primary_candidate.module == mod_path:
                mod_symbol_count += 1
            for candidate in supporting_candidates:
                if candidate.module == mod_path:
                    mod_symbol_count += 1
            for candidate in candidates:
                if candidate.module == mod_path:
                    mod_symbol_count += 1

            # Determine purpose from module path.
            purpose = self._infer_module_purpose(mod_path)
            relationship_summary_text = self._infer_module_relationship(
                mod_path, primary_candidate, candidates, supporting_candidates
            )

            module_descriptions.append(
                ModuleDescription(
                    module_path=mod_path,
                    purpose=purpose,
                    relationship_summary=relationship_summary_text,
                    symbol_count=mod_symbol_count,
                )
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
            primary_symbol_context=primary_symbol_context,
            supporting_symbol_contexts=supporting_symbol_contexts,
            module_descriptions=module_descriptions,
        )

    @staticmethod
    def _infer_module_purpose(module_path: str) -> str:
        """Infer a brief purpose description from a module path.

        Args:
            module_path: Source file path relative to repository root.

        Returns:
            A brief purpose description.
        """
        # Simple heuristic: derive purpose from filename.
        filename = module_path.rsplit("/", 1)[-1] if "/" in module_path else module_path
        filename_stem = filename.rsplit(".", 1)[0]

        purpose_map: dict[str, str] = {
            "models": "Data models and schemas",
            "views": "Request handling and response rendering",
            "controllers": "Request routing and business logic",
            "services": "Core business logic and services",
            "repositories": "Data access and persistence",
            "middleware": "Request/response middleware",
            "utils": "Utility and helper functions",
            "helpers": "Helper functions and utilities",
            "config": "Configuration and settings",
            "main": "Application entry point and factory",
            "app": "Application factory and configuration",
            "auth": "Authentication and authorization",
            "tests": "Test files and fixtures",
            "types": "Type definitions and type aliases",
        }

        return purpose_map.get(filename_stem, f"Module: {filename}")

    @staticmethod
    def _infer_module_relationship(
        module_path: str,
        primary_candidate: ContextCandidate | None,
        candidates: list[ContextCandidate],
        supporting_candidates: list[ContextCandidate],
    ) -> str:
        """Infer how a module relates to the primary symbol.

        Args:
            module_path: Source file path.
            primary_candidate: The primary symbol candidate.
            candidates: All ranked candidates.
            supporting_candidates: Supporting symbol candidates.

        Returns:
            A relationship summary string.
        """
        if primary_candidate is None:
            return ""

        if module_path == primary_candidate.module:
            return "Contains the primary symbol"

        # Check if any candidate from this module is a caller/callee.
        has_caller = False
        has_callee = False
        for candidate in candidates + supporting_candidates:
            if candidate.module == module_path:
                # Check if it's in the same class scope as primary.
                if primary_candidate:
                    primary_class = ".".join(
                        primary_candidate.qualified_name.rsplit(".", 1)[:-1]
                    ) if "." in primary_candidate.qualified_name else ""
                    candidate_class = ".".join(
                        candidate.qualified_name.rsplit(".", 1)[:-1]
                    ) if "." in candidate.qualified_name else ""
                    if primary_class and candidate_class == primary_class:
                        return f"Shares class scope with primary symbol"

        return f"Supporting module with related symbols"
