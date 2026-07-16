"""Data models for the symbol graph.

Defines a language-independent representation of symbols and their
relationships.  These models are the stable public contract — future
language extractors (Tree-sitter, Scala, Java, Rust, etc.) must produce
exactly the same structure without requiring consumer changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Language(str, Enum):
    """Programming language identifier.

    Intentionally minimal — extended by future language extractors.
    """

    PYTHON = "python"


class SymbolType(str, Enum):
    """Category of a symbol within source code.

    Classification rules:
    - ``def`` directly inside a class → ``METHOD``
    - nested ``def`` (not inside a class) → ``FUNCTION``
    - nested ``class`` → ``CLASS``
    - ``async def`` follows the same rule as ``def``
    - decorators never change ``SymbolType``
    """

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class RelationshipType(str, Enum):
    """Type of relationship between two symbols.

    Rules:
    - ``DEFINES`` represents containment (parent → child).
    - ``IMPORTS`` represents module references.
    - ``INHERITS`` represents inheritance.
    - ``CALLS`` exists only as a reserved type and is not populated in v1.

    Only ``DEFINES`` relationships are traversed by ``children()`` and
    ``parents()`` on ``SymbolGraph``.
    """

    DEFINES = "defines"
    IMPORTS = "imports"
    INHERITS = "inherits"
    CALLS = "calls"  # reserved


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """A single symbol extracted from source code.

    Attributes:
        id: Canonical identifier — always identical to ``qualified_name``.
        name: Short name (e.g. ``"run"`` for ``main.App.run``).
        qualified_name: Fully qualified name relative to the repository root
            (e.g. ``"main.App.run"``).
        symbol_type: Category of the symbol.
        module: Source file path relative to the repository root.
        lineno: 1-based line number where the symbol is defined.
        decorators: List of decorator names (empty list when none).
    """

    id: str
    name: str
    qualified_name: str
    symbol_type: SymbolType
    module: str
    lineno: int
    decorators: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Enforce the invariant that ``id`` equals ``qualified_name``."""
        if self.id != self.qualified_name:
            raise ValueError(
                "Symbol.id must be identical to Symbol.qualified_name"
            )


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Relationship:
    """A directed relationship between two symbols.

    Attributes:
        source: The symbol that originates the relationship.
        target: The symbol that the relationship points to.
        type: The kind of relationship.
    """

    source: str
    target: str
    type: RelationshipType


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Module:
    """All symbols and relationships discovered in a single source file.

    Attributes:
        path: File path relative to the repository root.
        symbols: All symbols defined in this file.
        relationships: All relationships within this file.
        imports: Raw import text as written in the source.
        source: Raw source code of the file (used by relationship extractors).
    """

    path: str
    symbols: list[Symbol] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    source: str = ""


# ---------------------------------------------------------------------------
# SymbolGraph
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolGraph:
    """Complete symbol graph for a repository (or directory).

    Contains one ``Module`` per source file.  Modules are isolated —
    relationships never cross module boundaries except ``IMPORTS``.

    Attributes:
        modules: All discovered modules keyed by file path.
    """

    modules: dict[str, Module] = field(default_factory=dict)
