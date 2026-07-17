"""Call relationship extractor.

Detects function and method calls between known symbols in the
RepositoryIndex and generates CALLS relationships.

Supported call patterns:

- function → function
- method → method
- function → method
- method → function

Not supported (ignored):

- dynamic dispatch
- monkey patching
- reflection
- eval() / exec()
- runtime imports
- metaprogramming

Only static analysis of the AST is performed.
"""

from __future__ import annotations

import ast

from packages.repository.index.models import RepositoryIndex
from packages.repository.relationships.base import RelationshipExtractor, RelationshipType
from packages.repository.symbols.models import (
    Relationship,
    Symbol,
    SymbolType,
)


class _CallVisitor(ast.NodeVisitor):
    """AST visitor that tracks call relationships.

    Maintains a stack of enclosing symbol scopes so that when a Call
    node is encountered, we know which symbol is doing the calling.
    """

    def __init__(
        self,
        symbol_lookup: dict[str, Symbol],
        module_symbol_lookup: dict[str, dict[str, list[Symbol]]],
        current_module: str,
    ) -> None:
        """Initialise the visitor.

        Args:
            symbol_lookup: Global symbol lookup by qualified_name.
            module_symbol_lookup: Per-module symbol lookup by short name.
            current_module: Current module path.
        """
        self._symbol_lookup = symbol_lookup
        self._module_symbol_lookup = module_symbol_lookup
        self._current_module = current_module
        self._scope_stack: list[Symbol] = []
        self._relationships: list[Relationship] = []

        # Build a short-name lookup for cross-module calls.
        # Maps short name -> list of qualified names.
        self._short_name_lookup: dict[str, list[str]] = {}
        for sym in symbol_lookup.values():
            if sym.name not in self._short_name_lookup:
                self._short_name_lookup[sym.name] = []
            self._short_name_lookup[sym.name].append(sym.qualified_name)

    @property
    def relationships(self) -> list[Relationship]:
        """Extracted relationships."""
        return self._relationships

    def _resolve_call_targets(
        self,
        call_node: ast.Call,
    ) -> list[str]:
        """Resolve a call target to known symbol qualified names.

        Args:
            call_node: The AST Call node.

        Returns:
            List of resolved qualified names.
        """
        targets: list[str] = []
        func = call_node.func

        if isinstance(func, ast.Name):
            # Simple call: helper()
            name = func.id
            if name in self._symbol_lookup:
                targets.append(name)
            elif name in self._module_symbol_lookup.get(
                self._current_module, {}
            ):
                for sym in self._module_symbol_lookup[self._current_module][name]:
                    if sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                        targets.append(sym.qualified_name)
            elif name in self._short_name_lookup:
                # Cross-module call: the short name matches a symbol in another module.
                for qname in self._short_name_lookup[name]:
                    if qname in self._symbol_lookup:
                        targets.append(qname)

        elif isinstance(func, ast.Attribute):
            # Attribute call: self.method() or obj.method()
            attr_name = func.attr
            value = func.value

            if isinstance(value, ast.Name):
                obj_name = value.id
                if obj_name == "self":
                    # self.method() — resolve to current class's method
                    for sym in reversed(self._scope_stack):
                        if sym.symbol_type == SymbolType.CLASS:
                            target = f"{sym.qualified_name}.{attr_name}"
                            if target in self._symbol_lookup:
                                targets.append(target)
                            break
                elif obj_name in self._symbol_lookup:
                    # Direct reference to a known symbol
                    target = f"{self._symbol_lookup[obj_name].qualified_name}.{attr_name}"
                    if target in self._symbol_lookup:
                        targets.append(target)
                    # Also check if it's a method call on a class
                    class_target = f"{obj_name}.{attr_name}"
                    if class_target in self._symbol_lookup:
                        targets.append(class_target)

            elif isinstance(value, ast.Attribute):
                # Chained attribute: self.service.method()
                # Try to resolve the attribute chain to a known symbol.
                # self.service -> Service (the class)
                # Then service.method -> Service.method
                attr_chain = self._get_attribute_chain(func)
                if attr_chain:
                    # Check if any prefix of the chain resolves to a known class
                    for i in range(len(attr_chain)):
                        prefix = ".".join(attr_chain[:i + 1])
                        if prefix in self._symbol_lookup:
                            class_sym = self._symbol_lookup[prefix]
                            if class_sym.symbol_type == SymbolType.CLASS:
                                target = f"{prefix}.{attr_name}"
                                if target in self._symbol_lookup:
                                    targets.append(target)
                                break

        return targets

    def _get_attribute_chain(self, node: ast.Attribute) -> list[str]:
        """Get the dotted name chain from an Attribute node.

        Args:
            node: The AST Attribute node.

        Returns:
            List of name components, or empty list if unrecognised.
        """
        names: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            names.append(current.id)
        names.reverse()
        return names

    def visit_Call(self, node: ast.Call) -> None:
        """Visit a Call node and record relationships."""
        targets = self._resolve_call_targets(node)

        # The innermost scope in the stack is the caller.
        if self._scope_stack and targets:
            caller = self._scope_stack[-1]
            for target in targets:
                if target in self._symbol_lookup:
                    self._relationships.append(Relationship(
                        source=caller.qualified_name,
                        target=target,
                        type=RelationshipType.CALLS,
                    ))

        # Continue visiting child nodes.
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Track function scope."""
        # Find the symbol for this function.
        func_sym = None
        for name, syms in self._module_symbol_lookup.get(
            self._current_module, {}
        ).items():
            for sym in syms:
                if sym.name == node.name and sym.symbol_type in (
                    SymbolType.FUNCTION,
                    SymbolType.METHOD,
                ):
                    func_sym = sym
                    break
            if func_sym:
                break

        if func_sym:
            self._scope_stack.append(func_sym)
            self.generic_visit(node)
            self._scope_stack.pop()
        else:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Track async function scope."""
        # Find the symbol for this function.
        func_sym = None
        for name, syms in self._module_symbol_lookup.get(
            self._current_module, {}
        ).items():
            for sym in syms:
                if sym.name == node.name and sym.symbol_type in (
                    SymbolType.FUNCTION,
                    SymbolType.METHOD,
                ):
                    func_sym = sym
                    break
            if func_sym:
                break

        if func_sym:
            self._scope_stack.append(func_sym)
            self.generic_visit(node)
            self._scope_stack.pop()
        else:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """Track class scope."""
        # Find the symbol for this class.
        class_sym = None
        for sym in self._symbol_lookup.values():
            if sym.name == node.name and sym.symbol_type == SymbolType.CLASS:
                class_sym = sym
                break

        if class_sym:
            self._scope_stack.append(class_sym)
            self.generic_visit(node)
            self._scope_stack.pop()
        else:
            self.generic_visit(node)


class CallExtractor(RelationshipExtractor):
    """Extract CALLS relationships from a RepositoryIndex.

    Scans all modules in the index, parses their source code, and
    detects function/method call patterns.  Only calls where BOTH
    the caller and callee are known symbols in the index are emitted.

    Attributes:
        relationship_type: Always ``RelationshipType.CALLS``.
    """

    @property
    def relationship_type(self) -> RelationshipType:
        """The relationship type produced by this extractor."""
        return RelationshipType.CALLS

    def extract(
        self,
        repository_index: RepositoryIndex,
    ) -> list[Relationship]:
        """Extract CALLS relationships from the repository index.

        For each module in the index, the source code is parsed and
        all Call nodes are traversed.  When a call target resolves to
        a known symbol in the index, a CALLS relationship is created.

        Args:
            repository_index: The fully built ``RepositoryIndex`` to analyse.

        Returns:
            A sorted, deduplicated list of ``Relationship`` objects with
            type ``CALLS``.
        """
        # Build a lookup of all known symbols by qualified_name.
        symbol_lookup: dict[str, Symbol] = {}
        for sym in repository_index.symbols():
            symbol_lookup[sym.qualified_name] = sym

        # Build a lookup of all known symbols by short name within each module.
        module_symbol_lookup: dict[str, dict[str, list[Symbol]]] = {}
        for sym in repository_index.symbols():
            mod = sym.module
            if mod not in module_symbol_lookup:
                module_symbol_lookup[mod] = {}
            if sym.name not in module_symbol_lookup[mod]:
                module_symbol_lookup[mod][sym.name] = []
            module_symbol_lookup[mod][sym.name].append(sym)

        relationships: list[Relationship] = []

        for module in repository_index.modules_list():
            if not module.source:
                continue

            try:
                tree = ast.parse(module.source)
            except SyntaxError:
                continue

            visitor = _CallVisitor(
                symbol_lookup=symbol_lookup,
                module_symbol_lookup=module_symbol_lookup,
                current_module=module.path,
            )
            visitor.visit(tree)
            relationships.extend(visitor.relationships)

        # Deduplicate and sort by (source, target) for determinism.
        seen: set[tuple[str, str]] = set()
        unique: list[Relationship] = []
        for rel in relationships:
            key = (rel.source, rel.target)
            if key not in seen:
                seen.add(key)
                unique.append(rel)

        return sorted(unique, key=lambda r: (r.source, r.target))
