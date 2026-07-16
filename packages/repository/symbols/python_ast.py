"""Python AST-based symbol extractor.

Parses Python source using the standard library ``ast`` module and
produces a ``SymbolGraph`` following the language-independent data
model.

Only the standard library is used (ast, pathlib, typing, dataclasses).
No third-party parsing libraries are permitted.
"""

from __future__ import annotations

import ast
from pathlib import Path

from packages.repository.symbols.extractor import SymbolExtractor
from packages.repository.symbols.models import (
    Language,
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolGraph,
    SymbolType,
)


class PythonAstExtractor(SymbolExtractor):
    """Extracts symbols from Python source files using the AST.

    Attributes:
        language: Always ``Language.PYTHON``.
    """

    @property
    def language(self) -> Language:
        return Language.PYTHON

    def extract(self, path: Path) -> SymbolGraph:
        """Extract symbols from a single file or directory.

        Args:
            path: Path to a Python source file or a directory.

        Returns:
            A ``SymbolGraph`` containing all discovered symbols.

        Raises:
            FileNotFoundError: If the path does not exist.
            NotADirectoryError: If a directory path is given as a file.
        """
        path = path.resolve()

        if path.is_file():
            return self._extract_file(path)

        if path.is_dir():
            return self._extract_directory(path)

        raise FileNotFoundError(f"No such file or directory: {path}")

    # ------------------------------------------------------------------
    # File / directory extraction
    # ------------------------------------------------------------------

    def _extract_file(self, path: Path) -> SymbolGraph:
        """Parse a single Python file and return its ``SymbolGraph``.

        Args:
            path: Absolute path to the Python source file.

        Returns:
            A ``SymbolGraph`` with one module for this file.
        """
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        # Module path is relative to the scan root.
        # For a single file the path is just the stem (e.g. "main").
        module_path = path.stem

        symbols: list[Symbol] = []
        relationships: list[Relationship] = []
        imports: list[str] = []

        self._extract_definitions(
            tree,
            parent_name="",
            parent_type=None,
            parent_qualified=module_path,
            module_path=module_path,
            symbols=symbols,
            relationships=relationships,
            imports=imports,
        )

        module = Module(
            path=module_path,
            symbols=symbols,
            relationships=relationships,
            imports=imports,
            source=source,
        )

        return SymbolGraph(modules={module_path: module})

    def _extract_directory(self, root: Path) -> SymbolGraph:
        """Extract symbols from all Python files under ``root``.

        Args:
            root: Path to the directory to scan.

        Returns:
            A merged ``SymbolGraph`` containing all modules.
        """
        all_modules: dict[str, Module] = {}

        for py_file in sorted(root.rglob("*.py")):
            # Skip __pycache__ and hidden directories.
            if any(part.startswith("__") and part.endswith("__") for part in py_file.parts):
                continue
            if any(part.startswith(".") for part in py_file.parts):
                continue

            graph = self._extract_file(py_file)
            all_modules.update(graph.modules)

        return SymbolGraph(modules=all_modules)

    # ------------------------------------------------------------------
    # AST traversal helpers
    # ------------------------------------------------------------------

    def _extract_definitions(
        self,
        node: ast.AST,
        parent_name: str,
        parent_type: SymbolType | None,
        parent_qualified: str,
        module_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        imports: list[str],
    ) -> None:
        """Recursively extract definitions from an AST node.

        Args:
            node: The AST node to process.
            parent_name: Short name of the parent scope.
            parent_type: SymbolType of the parent scope (None for module level).
            parent_qualified: Fully qualified name of the parent scope.
            module_path: File path relative to repository root.
            symbols: Mutable list to collect symbols.
            relationships: Mutable list to collect relationships.
            imports: Mutable list to collect import text.
        """
        if isinstance(node, ast.Module):
            self._extract_module(
                node, module_path, symbols, relationships, imports
            )
            return

        if isinstance(node, (ast.ClassDef,)):
            self._extract_class(
                node, parent_type, parent_qualified,
                module_path, symbols, relationships, imports
            )
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._extract_function(
                node, parent_type, parent_qualified,
                module_path, symbols, relationships, imports
            )
            return

        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"import {alias.name}")
            return

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(
                a.name if not a.asname else f"{a.name} as {a.asname}"
                for a in node.names
            )
            imports.append(f"from {module} import {names}")
            return

        # Recurse into child nodes for nested definitions.
        for child in ast.iter_child_nodes(node):
            self._extract_definitions(
                child,
                parent_name,
                parent_type,
                parent_qualified,
                module_path,
                symbols,
                relationships,
                imports,
            )

    def _extract_module(
        self,
        node: ast.Module,
        module_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        imports: list[str],
    ) -> None:
        """Extract top-level module-level definitions."""
        for child in node.body:
            self._extract_definitions(
                child,
                parent_name="",
                parent_type=None,
                parent_qualified=module_path,
                module_path=module_path,
                symbols=symbols,
                relationships=relationships,
                imports=imports,
            )

    def _extract_class(
        self,
        node: ast.ClassDef,
        parent_type: SymbolType | None,
        parent_qualified: str,
        module_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        imports: list[str],
    ) -> None:
        """Extract a class and its nested definitions.

        Args:
            node: The ClassDef AST node.
            parent_type: SymbolType of the parent scope.
            parent_qualified: Fully qualified name of the parent scope.
            module_path: File path relative to repository root.
            symbols: Mutable list to collect symbols.
            relationships: Mutable list to collect relationships.
            imports: Mutable list to collect import text.
        """
        class_name = node.name
        qualified_name = (
            f"{parent_qualified}.{class_name}"
            if parent_qualified
            else class_name
        )

        # Extract decorators.
        decorators: list[str] = []
        for dec in node.decorator_list:
            decorators.extend(self._extract_decorator_names(dec))

        symbol = Symbol(
            id=qualified_name,
            name=class_name,
            qualified_name=qualified_name,
            symbol_type=SymbolType.CLASS,
            module=module_path,
            lineno=node.lineno,
            decorators=decorators,
        )
        symbols.append(symbol)

        # Handle inheritance.
        for base in node.bases:
            base_name = self._get_name(base)
            if base_name:
                relationships.append(Relationship(
                    source=qualified_name,
                    target=base_name,
                    type=RelationshipType.INHERITS,
                ))

        # Extract nested definitions (creates DEFINES relationships).
        for child in node.body:
            self._extract_definitions(
                child,
                parent_name=class_name,
                parent_type=SymbolType.CLASS,
                parent_qualified=qualified_name,
                module_path=module_path,
                symbols=symbols,
                relationships=relationships,
                imports=imports,
            )

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_type: SymbolType | None,
        parent_qualified: str,
        module_path: str,
        symbols: list[Symbol],
        relationships: list[Relationship],
        imports: list[str],
    ) -> None:
        """Extract a function or method.

        Args:
            node: The FunctionDef or AsyncFunctionDef AST node.
            parent_type: SymbolType of the parent scope.
            parent_qualified: Fully qualified name of the parent scope.
            module_path: File path relative to repository root.
            symbols: Mutable list to collect symbols.
            relationships: Mutable list to collect relationships.
            imports: Mutable list to collect import text.
        """
        func_name = node.name
        qualified_name = (
            f"{parent_qualified}.{func_name}"
            if parent_qualified
            else func_name
        )

        # Determine symbol type.
        if parent_type == SymbolType.CLASS:
            symbol_type = SymbolType.METHOD
        else:
            symbol_type = SymbolType.FUNCTION

        # Extract decorators.
        decorators: list[str] = []
        for dec in node.decorator_list:
            decorators.extend(self._extract_decorator_names(dec))

        symbol = Symbol(
            id=qualified_name,
            name=func_name,
            qualified_name=qualified_name,
            symbol_type=symbol_type,
            module=module_path,
            lineno=node.lineno,
            decorators=decorators,
        )
        symbols.append(symbol)

        # Create DEFINES relationship from parent to this symbol.
        if parent_qualified:
            relationships.append(Relationship(
                source=parent_qualified,
                target=qualified_name,
                type=RelationshipType.DEFINES,
            ))

        # Recurse into the function body for nested definitions.
        for child in node.body:
            self._extract_definitions(
                child,
                parent_name=func_name,
                parent_type=symbol_type,
                parent_qualified=qualified_name,
                module_path=module_path,
                symbols=symbols,
                relationships=relationships,
                imports=imports,
            )

    def _extract_decorator_names(self, node: ast.AST) -> list[str]:
        """Extract decorator names from an AST node.

        Handles simple names (``@decorator``) and calls (``@decorator()``).

        Args:
            node: The decorator AST node.

        Returns:
            List of decorator name strings.
        """
        names: list[str] = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(self._get_name(node))
        elif isinstance(node, (ast.Call,)):
            # @decorator(args) — extract the callable name.
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(self._get_name(node.func))
        return names

    def _get_name(self, node: ast.AST) -> str:
        """Get the dotted name from an AST node.

        Handles Name and Attribute nodes.

        Args:
            node: The AST node.

        Returns:
            The dotted name string, or empty string if unrecognised.
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._get_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        return ""
