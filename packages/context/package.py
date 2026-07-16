"""Context Package models.

Defines the structured representation produced by the Context Composer.
This is the internal platform model — not a provider payload.

Architecture
------------

Context Builder
       │
       ▼
Ranking Engine
       │
       ▼
Context Budget
       │
       ▼
Context Composer
       │
       ▼
ContextPackage
       │
       ▼
Provider (serialises)

The Context Package is **not**

- an OpenAI request
- an Anthropic request
- a DSPARK request
- a provider payload

Providers are responsible for translating ContextPackage into their
own request format.

Constraints
-----------

- No provider-specific fields.
- No token counts beyond what the budget engine already reports.
- No prompt content.
- No formatting instructions.

Public API
----------

.. code-block:: python

    package = ContextPackage(
        query="authentication middleware",
        modules=["auth.py", "main.py"],
        symbols=["auth.AuthenticationMiddleware", "main.App"],
        metadata={
            "estimated_tokens": 230,
            "estimated_symbols": 2,
            "estimated_modules": 2,
            "truncated": False,
        },
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextMetadata:
    """Budget metadata attached to a context package.

    Attributes:
        estimated_tokens: Estimated token count for the context.
        estimated_symbols: Number of unique symbols in the context.
        estimated_modules: Number of unique modules in the context.
        truncated: Whether the context was truncated to fit the budget.
    """

    estimated_tokens: int = 0
    estimated_symbols: int = 0
    estimated_modules: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class ContextPackage:
    """A structured context package produced by the Context Composer.

    This is the internal platform model.  Providers translate this
    into their own request format.

    Attributes:
        query: The original user query that drove context assembly.
        modules: Ordered list of unique module names.
        symbols: Ordered list of unique symbol qualified names.
        metadata: Budget metadata from the context budget engine.
    """

    query: str
    modules: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
