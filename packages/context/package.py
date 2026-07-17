"""Context Package models.

Defines the structured representation produced by the Context Builder.
This is the internal platform model — not a provider payload.

Architecture
------------

Context Builder
       |
       v
Context Package v2
       |
       v
Serializer
       |
       v
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

    from packages.context.context_package import ContextPackage

    package = ContextPackage(
        primary_symbol="auth.AuthenticationMiddleware",
        supporting_symbols=["auth.middleware.JWTAuth"],
        related_callers=["main.create_app"],
        related_callees=["auth.Tokens.create_token"],
        related_modules=["auth.py", "main.py"],
        estimated_tokens=230,
    )

Backward-Compatible Legacy API
------------------------------

The legacy ``ContextPackage`` (with ``query``, ``modules``, ``symbols``,
``metadata``) is still exported for consumers that have not yet migrated.
It is a thin wrapper around the structured model.

.. code-block:: python

    from packages.context.package import ContextPackage

    package = ContextPackage(
        query="authentication middleware",
        modules=["auth.py", "main.py"],
        symbols=["auth.AuthenticationMiddleware", "main.App"],
        metadata={"estimated_tokens": 230},
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.context.context_package import (
    ContextMetadata,
    RelationshipSummary,
)
from packages.context.context_package import (
    ContextPackage as ContextPackageStructured,
)

# Re-export the new models for direct import.
__all__ = [
    "ContextMetadata",
    "ContextPackage",
    "ContextPackageStructured",
    "RelationshipSummary",
]


# ------------------------------------------------------------------
# Legacy alias — backward compatible
# ------------------------------------------------------------------


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
