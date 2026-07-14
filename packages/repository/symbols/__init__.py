"""Symbol graph package.

Provides a language-independent representation of symbols and their
relationships extracted from source code.

Architecture
------------
Python AST → SymbolExtractor → SymbolGraph

The public API never exposes Python AST nodes. AST is strictly an
implementation detail of language-specific extractors.
"""

from packages.repository.symbols.extractor import SymbolExtractor
from packages.repository.symbols.graph import SymbolGraphView
from packages.repository.symbols.models import (
    Language,
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolGraph,
    SymbolType,
)
from packages.repository.symbols.python_ast import PythonAstExtractor

__all__ = [
    "Language",
    "Module",
    "PythonAstExtractor",
    "Relationship",
    "RelationshipType",
    "Symbol",
    "SymbolExtractor",
    "SymbolGraph",
    "SymbolGraphView",
    "SymbolType",
]
