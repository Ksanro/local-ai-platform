"""Context Builder package.

Assembles repository context for future coding agents by enumerating
symbols from a ``SymbolGraphView`` and returning them in a deterministic
order.

Architecture
------------

Repository
      │
      ▼
ContextBuilder
      │
      ▼
RankingEngine
      │
      ▼
ContextBudget
      │
      ▼
ContextResult
      │
      ▼
ContextComposer
      │
      ▼
ContextPackage
      │
      ▼
Provider

The Builder depends only on the public ``SymbolGraphView`` API.  It
never accesses the filesystem, parses source code, or touches AST
objects.

Current behaviour
-----------------

Symbols are scored against the query text using the ``RankingEngine``,
estimated against a token budget via ``ContextBudget``, and returned
in relevance order, bounded by ``max_symbols`` and ``max_modules``.
The ``ContextComposer`` then assembles the result into a structured
``ContextPackage`` for provider consumption.

Future extensions (semantic search, DSPARK, memory, Git awareness)
will replace the default ranking strategy without changing the public
API.
"""

from packages.context.budget import ContextBudget
from packages.context.builder import ContextBuilder
from packages.context.composer import ContextComposer
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextQuery,
    ContextResult,
)
from packages.context.package import ContextMetadata, ContextPackage
from packages.context.query import normalise_query
from packages.context.ranking import RankingEngine
from packages.context.scoring import RankingReason

__all__ = [
    "ContextBudget",
    "ContextBudgetResult",
    "ContextBuilder",
    "ContextCandidate",
    "ContextComposer",
    "ContextMetadata",
    "ContextPackage",
    "ContextQuery",
    "ContextResult",
    "RankingEngine",
    "RankingReason",
    "normalise_query",
]
