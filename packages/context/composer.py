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

The Composer performs only deterministic assembly:

- preserve ranked symbol order
- preserve selected module order
- copy budget metadata
- never modify ranking
- never filter results
- never reorder symbols

The Composer is intentionally "dumb".

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
- access repositories
- access the filesystem
- inspect AST
- know about OpenAI schemas

It assembles data only.

Public API
----------

.. code-block:: python

    composer = ContextComposer()

    package = composer.compose(context_result)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.context.models import ContextResult
from packages.context.package import ContextPackage

if TYPE_CHECKING:
    from packages.context.models import ContextCandidate  # noqa: F401


class ContextComposer:
    """Assemble ranked context into a structured package.

    Attributes:
        None — the composer is stateless.
    """

    def compose(self, context_result: ContextResult) -> ContextPackage:
        """Assemble a ContextPackage from a ContextResult.

        Preserves ranked symbol order, selected module order, and
        copies budget metadata.  Never modifies ranking, filters
        results, or reorders symbols.

        Args:
            context_result: The assembled context from the builder.

        Returns:
            A structured ContextPackage ready for provider consumption.
        """
        # Extract symbols in ranked order.
        symbols: list[str] = [
            candidate.qualified_name for candidate in context_result.candidates
        ]

        # Preserve selected module order.
        modules: list[str] = list(context_result.selected_modules)

        # Copy budget metadata.
        metadata: dict[str, Any] = {
            "estimated_tokens": context_result.budget.estimated_tokens,
            "estimated_symbols": context_result.budget.estimated_symbols,
            "estimated_modules": context_result.budget.estimated_modules,
            "truncated": context_result.budget.truncated,
        }

        return ContextPackage(
            query="",
            modules=modules,
            symbols=symbols,
            metadata=metadata,
        )
