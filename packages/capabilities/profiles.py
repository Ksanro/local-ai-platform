"""Retrieval Profiles v1.

Immutable configuration objects that describe *what* a capability needs
from the repository context, not *how* to orchestrate retrieval.

Architecture
------------

::

    User Request
        ↓
    Capability (defines intent via profile)
        ↓
    RetrievalProfile (configuration only)
        ↓
    ContextPlanner (orchestrates retrieval)
        ↓
    RepositoryIndex
        ↓
    ContextBuilder
        ↓
    Serializer

Profiles contain **zero business logic**.  They are pure data objects.

Public API
----------

.. code-block:: python

    from packages.capabilities.profiles import (
        RetrievalProfile,
        EXPLAIN_PROFILE,
        DEBUG_PROFILE,
        REFACTOR_PROFILE,
    )

    # Access via capability
    profile = capability.profile

Constraints
-----------

Profiles must **not**:

- execute retrieval
- call planner
- call context builder
- contain business logic

They are immutable configuration objects only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    """Immutable retrieval profile configuration.

    Describes *what* repository context a capability needs.  Contains
    no business logic — purely configuration.

    Attributes:
        name: Human-readable profile name.
        include_callers: Include caller symbols in retrieval.
        include_callees: Include callee symbols in retrieval.
        include_dependencies: Include dependency symbols in retrieval.
        include_dependents: Include dependent symbols in retrieval.
        include_tests: Include test files in retrieval.
        include_dead_code: Include dead/unreferenced code in retrieval.
        include_diagnostics: Include diagnostic information in retrieval.
        relationship_depth: Maximum traversal depth for relationship queries.
        max_context_tokens: Maximum token budget for context assembly.
    """

    name: str

    include_callers: bool = False
    include_callees: bool = False
    include_dependencies: bool = False
    include_dependents: bool = False
    include_tests: bool = False
    include_dead_code: bool = False
    include_diagnostics: bool = False
    relationship_depth: int = 1
    max_context_tokens: int = 4096


# ---------------------------------------------------------------------------
# Built-in Profiles
# ---------------------------------------------------------------------------

#: Explain profile — minimal context for code explanation.
#:
#: | Setting            | Value |
#: |-------------------|-------|
#: | include_callers   | False |
#: | include_callees   | False |
#: | include_diagnostics | False |
#: | relationship_depth | 1     |
EXPLAIN_PROFILE = RetrievalProfile(
    name="explain",
    include_callers=False,
    include_callees=False,
    include_dependencies=False,
    include_dependents=False,
    include_tests=False,
    include_dead_code=False,
    include_diagnostics=False,
    relationship_depth=1,
    max_context_tokens=4096,
)

#: Debug profile — diagnostic context with callers, callees, and dependencies.
#:
#: | Setting            | Value |
#: |-------------------|-------|
#: | include_callers   | True  |
#: | include_callees   | True  |
#: | include_diagnostics | True  |
#: | include_dependencies | True  |
#: | relationship_depth | 2     |
DEBUG_PROFILE = RetrievalProfile(
    name="debug",
    include_callers=True,
    include_callees=True,
    include_dependencies=True,
    include_dependents=False,
    include_tests=True,
    include_dead_code=False,
    include_diagnostics=True,
    relationship_depth=2,
    max_context_tokens=4096,
)

#: Refactor profile — comprehensive impact analysis context.
#:
#: | Setting            | Value |
#: |-------------------|-------|
#: | include_callers   | True  |
#: | include_callees   | True  |
#: | include_dependencies | True  |
#: | include_dependents | True  |
#: | include_tests     | True  |
#: | include_dead_code | True  |
#: | include_diagnostics | True  |
#: | relationship_depth | 3     |
REFACTOR_PROFILE = RetrievalProfile(
    name="refactor",
    include_callers=True,
    include_callees=True,
    include_dependencies=True,
    include_dependents=True,
    include_tests=True,
    include_dead_code=True,
    include_diagnostics=True,
    relationship_depth=3,
    max_context_tokens=4096,
)

#: Architecture review profile — comprehensive architectural analysis context.
#:
#: | Setting            | Value |
#: |-------------------|-------|
#: | include_callers   | True  |
#: | include_callees   | True  |
#: | include_dependencies | True  |
#: | include_dependents | True  |
#: | include_tests     | True  |
#: | include_dead_code | True  |
#: | include_diagnostics | True  |
#: | relationship_depth | 3     |
#: | max_context_tokens | 8192  |
ARCHITECTURE_REVIEW_PROFILE = RetrievalProfile(
    name="architecture-review",
    include_callers=True,
    include_callees=True,
    include_dependencies=True,
    include_dependents=True,
    include_tests=True,
    include_dead_code=True,
    include_diagnostics=True,
    relationship_depth=3,
    max_context_tokens=8192,
)


