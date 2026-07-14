# Symbol Graph

A language-independent representation of symbols and their relationships
extracted from source code.

## Architecture

```
Python AST
        │
        ▼
SymbolExtractor  (abstract interface)
        │
        ▼
SymbolGraph      (immutable data model)
```

The public API never exposes Python AST nodes.  AST is strictly an
implementation detail of language-specific extractors.

## Data Model

### Symbol

| Field            | Type          | Description                           |
|------------------|---------------|---------------------------------------|
| `id`             | `str`         | Canonical identifier (= `qualified_name`) |
| `name`           | `str`         | Short name (e.g. `"run"`)             |
| `qualified_name` | `str`         | Fully qualified name (e.g. `"main.App.run"`) |
| `symbol_type`    | `SymbolType`  | Category of the symbol                |
| `module`         | `str`         | Source file path relative to repo root |
| `lineno`         | `int`         | 1-based line number                   |
| `decorators`     | `list[str]`   | Decorator names (empty when none)     |

**Invariant:** `id` is always identical to `qualified_name`.

### SymbolType

| Value      | Meaning                              |
|------------|--------------------------------------|
| `MODULE`   | Source file (reserved)               |
| `CLASS`    | Class definition                     |
| `FUNCTION` | Top-level or nested function         |
| `METHOD`   | `def` directly inside a class        |

Classification rules:

- `def` directly inside a class → `METHOD`
- nested `def` (not inside a class) → `FUNCTION`
- nested `class` → `CLASS`
- `async def` follows the same rule as `def`
- decorators never change `SymbolType`

### Relationship

| Field  | Type             | Description                        |
|--------|------------------|------------------------------------|
| `source` | `str`          | Symbol that originates the relationship |
| `target` | `str`          | Symbol that the relationship points to |
| `type`   | `RelationshipType` | Kind of relationship           |

### RelationshipType

| Value     | Meaning                          | Traversed by `children()`/`parents()` |
|-----------|----------------------------------|---------------------------------------|
| `DEFINES` | Containment (parent → child)     | Yes                                   |
| `IMPORTS` | Module references                | No                                    |
| `INHERITS`| Inheritance                      | No                                    |
| `CALLS`   | Reserved (not populated in v1)   | No                                    |

## Public API

### `SymbolGraphView`

Read-only view over a `SymbolGraph`.  All public collections are sorted
deterministically — by `qualified_name` first, then by `lineno` — so
consumers never depend on filesystem traversal order.

| Method             | Returns                    | Description                              |
|--------------------|----------------------------|------------------------------------------|
| `modules()`        | `Sequence[Module]`         | All modules, sorted by path              |
| `module(path)`     | `Module \| None`           | Module by path                           |
| `classes()`        | `Sequence[Symbol]`         | All CLASS symbols, sorted                |
| `functions()`      | `Sequence[Symbol]`         | All FUNCTION symbols, sorted             |
| `methods()`        | `Sequence[Symbol]`         | All METHOD symbols, sorted               |
| `symbols()`        | `Sequence[Symbol]`         | All symbols, sorted                      |
| `find(name)`       | `Sequence[Symbol]`         | Match against `name` or `qualified_name` |
| `children(symbol)` | `Sequence[Symbol]`         | Direct children via DEFINES only         |
| `parents(symbol)`  | `Sequence[Symbol]`         | Direct parents via DEFINES only          |
| `imports(module)`  | `Sequence[str]`            | Raw import text for a module             |

**Rules:**

- `find()` always returns a list (never `None`).
- Matching is performed against both `name` and `qualified_name`.
- Only `DEFINES` relationships are traversed by `children()` and `parents()`.

## Relationship Model

### DEFINES (containment)

Created automatically when a symbol is nested inside another:

```
main.py
class App:          ← main.App DEFINES main.App.run
    def run():      ← main.App.run
        pass
```

### INHERITS

Created when a class has base classes:

```
class App(Base):    ← main.App INHERITS Base
```

### IMPORTS

Stored as raw text exactly as written in the source.  No resolution is
performed — imported modules or symbols are not resolved.

```python
from typing import List  →  "from typing import List"
import os                →  "import os"
```

## Known Limitations

1. **No call resolution** — CALLS relationships are not populated.
2. **No import resolution** — imports are stored as raw text.
3. **No type inference** — parameter and return types are not extracted.
4. **No control-flow analysis** — only syntactic structure is captured.
5. **Python only** — only `Language.PYTHON` is implemented; the interface
   supports future extractors (Tree-sitter, Scala, Java, Rust, etc.).
6. **Single-file module paths** — for single-file extraction the module
   path is the file stem (e.g. `"main"`).  For directory extraction the
   module path is the relative path from the scan root.

## Future: Tree-sitter Integration

The `SymbolExtractor` interface is designed to be language-independent.
A Tree-sitter-based extractor would:

1. Implement `SymbolExtractor.language` → `Language.TREESITTER` (or a
   language-specific enum value).
2. Implement `extract(path)` → parse with Tree-sitter, walk the syntax
   tree, and produce the same `SymbolGraph` structure.
3. Produce identical `Symbol` and `Relationship` objects — consumers
   would not need any changes.

The data model (`Symbol`, `Relationship`, `SymbolGraph`) is the stable
contract.  Extractors are free to use any parsing technology as long as
they produce the same output structure.

## File Layout

```
packages/repository/symbols/
    __init__.py       # Package exports
    models.py         # Data model (Symbol, SymbolGraph, etc.)
    extractor.py      # Abstract extractor interface
    python_ast.py     # Python AST implementation
    graph.py          # SymbolGraph public API (SymbolGraphView)

tests/repository/symbols/
    fixtures/python_project/  # Test fixture project
    test_python_ast.py        # Extractor unit tests
    test_graph.py             # API unit tests
```
