"""Tests for the module import block delivered with repository context (Phase G3).

Whole-file source used to carry a module's ``import`` lines for free; per-symbol spans
do not, and that cost ``explain_live_path`` two of its four stage names (measured offline
at ``bc87179``).  ``ContextBuilder._enrich_with_source_data`` now prepends, once per
module, that module's top-level ``Import``/``ImportFrom`` statements to the first
candidate delivered from it, ON TOP of the existing cap.

Acceptance criteria
-------------------

- the block appears exactly once per module, on that module's first delivered candidate
  only, and every fresh request carries it again (state is per build call, not cached)
- the block is not counted against the source/preview cap: the body a candidate would
  have delivered is unchanged in length and still follows the block
- the block IS charged by ``_enforce_budget``: a package that fit without it stops
  fitting with it, and what disappears is a tail symbol, not the block's own candidate
- imports nested in a function body, a class body or an ``if TYPE_CHECKING:`` block are
  not module level and are not delivered; a repeated module-level statement is deduped
- a module that is not indexed, carries no source, or does not parse contributes nothing
  and raises nothing
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from packages.context.budget import CHARS_PER_TOKEN
from packages.context.builder import ContextBuilder
from packages.context.models import ContextCandidate, ContextQuery, ContextResult
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Module, Symbol, SymbolType
from packages.repository.symbols.python_ast import PythonAstExtractor

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

CORE_SOURCE = '''"""Core module."""

import json
import os
import os
from typing import Any

DEFAULT_NAME = "core"


class Widget:
    """A widget."""

    import nested_in_class_body

    if TYPE_CHECKING:
        import nested_in_conditional

    def build(self, spec: Any) -> str:
        """Build a widget from ``spec`` and serialize it."""
        import nested_in_function
        return json.dumps({"name": DEFAULT_NAME, "spec": repr(spec)})

    def name(self) -> str:
        """Return the default widget name."""
        return DEFAULT_NAME


def build_widget(spec: Any) -> Widget:
    """Construct a ``Widget`` and return it after building ``spec``."""
    widget = Widget()
    widget.build(spec)
    return widget
'''

EXTRA_SOURCE = '''"""Extra module."""

from dataclasses import dataclass


@dataclass
class Spec:
    """A widget spec."""

    name: str = "spec"
'''


def _index_from_sources(tmp_path: Path) -> RepositoryIndex:
    """Index two real files through the parser, the way the gateway indexes the repo.

    Symbols built this way carry ``start_lineno``/``end_lineno``, so the source the
    builder delivers for them is a span - the shape that stopped carrying imports.
    """
    modules: dict[str, Module] = {}
    symbols: list[Symbol] = []
    package = tmp_path / "pkg"
    package.mkdir()
    for name, source in (("core", CORE_SOURCE), ("extra", EXTRA_SOURCE)):
        path = package / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        graph = PythonAstExtractor().extract(path)
        for module in graph.modules.values():
            modules[module.path] = module
            symbols.extend(module.symbols)
    return RepositoryIndex(modules=modules, _symbols=symbols)


def _query(text: str, max_symbols: int = 20, max_tokens: int = 4096) -> ContextQuery:
    return ContextQuery(
        text=text, max_symbols=max_symbols, max_modules=10, max_tokens=max_tokens
    )


def _text(candidate: ContextCandidate) -> str:
    """The source text this candidate delivers: body for a primary, preview otherwise."""
    return candidate.source or candidate.source_preview


def _build(
    index: RepositoryIndex,
    query: ContextQuery,
    *,
    with_block: bool = True,
    **kwargs: object,
) -> ContextResult:
    """Build once, optionally with the import block suppressed for a reference run."""
    builder = ContextBuilder(index=index, **kwargs)
    if with_block:
        return builder.build(query)
    with patch.object(ContextBuilder, "_module_import_block", lambda self, module: ""):
        return builder.build(query)


def _block_for(index: RepositoryIndex, module: str) -> str:
    """The import block production would deliver for ``module``, without delivering it."""
    return ContextBuilder(index=index)._module_import_block(module)




# ------------------------------------------------------------------
# Once per module, on the first delivered candidate, every request
# ------------------------------------------------------------------


class TestBlockDeliveredOncePerModule:
    """A module's import block rides with exactly one candidate."""

    def _blocks(self, index: RepositoryIndex) -> dict[str, str]:
        return {
            module: _block_for(index, module)
            for module in index.modules
            if _block_for(index, module)
        }

    def test_block_appears_exactly_once_per_module(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        result = _build(index, _query("build_widget Widget build name Spec"))
        delivered = "\n".join(_text(c) for c in result.candidates)

        blocks = self._blocks(index)
        assert blocks, "the fixture modules carry no import block"
        for module, block in blocks.items():
            if not any(c.module == module and _text(c) for c in result.candidates):
                continue
            assert delivered.count(block) == 1, (
                f"{module}: block found {delivered.count(block)} times"
            )

    def test_block_lands_on_the_first_candidate_of_its_module(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        result = _build(index, _query("build_widget Widget build name Spec"))
        blocks = self._blocks(index)

        for module, block in blocks.items():
            of_module = [c for c in result.candidates if c.module == module]
            assert of_module, f"{module} delivered no candidate"
            carrier = next(c for c in of_module if _text(c).startswith(block))
            first_with_text = next(c for c in of_module if _text(c))
            assert carrier.qualified_name == first_with_text.qualified_name
            others = [
                c.qualified_name
                for c in of_module
                if c is not carrier and block and block in _text(c)
            ]
            assert not others, f"{module} sent its block more than once: {others}"

    def test_body_still_follows_the_block(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        result = _build(index, _query("build_widget Widget build name Spec"))
        blocks = self._blocks(index)

        for candidate in result.candidates:
            text = _text(candidate)
            block = blocks.get(candidate.module, "")
            if not text:
                continue
            if block and text.startswith(block):
                assert _text(candidate)[len(block):], (
                    f"{candidate.qualified_name}: block replaced the body"
                )
            assert "def " in text or "class " in text, (
                f"{candidate.qualified_name}: delivered no implementation of its own"
            )

    def test_every_request_carries_the_block_again(self, tmp_path: Path) -> None:
        """Nothing is cached across build calls: the block is rebuilt every request."""
        index = _index_from_sources(tmp_path)
        query = _query("build_widget Widget build name Spec")
        first = _build(index, query)
        second = _build(index, query)

        assert [_text(c) for c in first.candidates] == [_text(c) for c in second.candidates]
        for module, block in self._blocks(index).items():
            joined = "\n".join(_text(c) for c in second.candidates if c.module == module)
            assert joined.count(block) == 1

    def test_block_is_the_module_level_statements_in_order(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        core = next(k for k in index.modules if k.endswith("core"))
        block = _block_for(index, core)

        assert block == "import json\nimport os\nfrom typing import Any\n"
        assert block.endswith("\n")
        assert block.count("import os") == 1, "module-level duplicates were not deduped"
        assert "import nested_in_class_body" not in block
        assert "import nested_in_conditional" not in block
        assert "import nested_in_function" not in block


# ------------------------------------------------------------------
# Cap semantics: on top of the cap, charged by the budget
# ------------------------------------------------------------------


class TestBlockSitsOnTopOfTheCap:
    """The block never eats into the source/preview cap it is added to."""

    def test_primary_body_keeps_its_capped_length(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        query = _query("build_widget", max_symbols=1)
        cap_tokens = 20
        with_block = _build(index, query, primary_symbol_max_tokens=cap_tokens)
        lean = _build(index, query, with_block=False, primary_symbol_max_tokens=cap_tokens)

        carrier = with_block.candidates[0]
        assert carrier.qualified_name == lean.candidates[0].qualified_name
        span = index.get_symbol_source(carrier.qualified_name) or ""
        block = _block_for(index, carrier.module)
        body = _text(carrier)[len(block):]

        assert len(span) > int(cap_tokens * CHARS_PER_TOKEN), "the cap must bind"
        assert _text(lean.candidates[0]) == span[: int(cap_tokens * CHARS_PER_TOKEN)]
        assert body == _text(lean.candidates[0])
        assert len(_text(carrier)) == len(block) + len(body)
        assert len(_text(carrier)) > len(body) > 0, "the block was not added on top"

    def test_supporting_previews_keep_their_length(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        query = _query("build_widget Widget build name Spec")
        with_block = _build(index, query, supporting_symbol_max_tokens=512)
        lean = _build(index, query, with_block=False, supporting_symbol_max_tokens=512)

        before = {c.qualified_name: _text(c) for c in lean.candidates}
        for candidate in with_block.candidates:
            text = _text(candidate)
            reference = before[candidate.qualified_name]
            block = _block_for(index, candidate.module)
            if not reference:
                assert text == "", f"{candidate.qualified_name}: block without a body"
                continue
            assert text.endswith(reference)
            assert len(text) - len(reference) in (0, len(block))

    def test_tight_budget_drops_a_tail_symbol_not_the_block_carrier(
        self, tmp_path: Path
    ) -> None:
        index = _index_from_sources(tmp_path)
        text = "build_widget Widget build name Spec"
        lean = _build(index, _query(text), with_block=False)
        full = _build(index, _query(text))

        assert full.budget.estimated_tokens > lean.budget.estimated_tokens, (
            "the import block never reached the token estimate"
        )

        # Ask for exactly what the package needed without the block: with the block
        # the builder has to give something up, and what goes is a tail symbol.
        tight = _query(text, max_tokens=lean.budget.estimated_tokens)
        squeezed = _build(index, tight)

        assert squeezed.budget.within_budget
        assert squeezed.budget.estimated_tokens <= tight.max_tokens
        assert len(squeezed.candidates) < len(lean.candidates)
        kept = [c.qualified_name for c in squeezed.candidates]
        assert kept == [c.qualified_name for c in lean.candidates][: len(kept)]
        assert _text(squeezed.candidates[0]).startswith(
            _block_for(index, squeezed.candidates[0].module)
        )


# ------------------------------------------------------------------
# What counts as module level, and when a module contributes nothing
# ------------------------------------------------------------------


class TestModuleLevelOnly:
    """Only direct children of the module are import lines worth delivering."""

    def test_nested_imports_are_not_in_the_block(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        core = next(k for k in index.modules if k.endswith("core"))
        block = _block_for(index, core)

        for nested in (
            "import nested_in_function",
            "import nested_in_class_body",
            "import nested_in_conditional",
        ):
            assert nested not in block, f"{nested} is not a module-level import"

    def test_module_level_imports_reach_the_prompt(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        result = _build(index, _query("build_widget Widget build name Spec"))
        delivered = "\n".join(_text(c) for c in result.candidates)

        assert "from typing import Any" in delivered
        assert "from dataclasses import dataclass" in delivered

    def test_unindexed_module_contributes_nothing(self, tmp_path: Path) -> None:
        index = _index_from_sources(tmp_path)
        assert _block_for(index, "pkg/not_in_the_index") == ""

    def test_module_without_source_contributes_nothing(self) -> None:
        symbol = Symbol(
            id="empty.helper",
            name="helper",
            qualified_name="empty.helper",
            symbol_type=SymbolType.FUNCTION,
            module="empty",
            lineno=1,
        )
        index = RepositoryIndex(
            modules={"empty": Module(path="empty", symbols=[symbol], source="")},
            _symbols=[symbol],
        )
        assert _block_for(index, "empty") == ""

    def test_syntax_error_contributes_nothing_and_raises_nothing(self) -> None:
        symbol = Symbol(
            id="broken.helper",
            name="helper",
            qualified_name="broken.helper",
            symbol_type=SymbolType.FUNCTION,
            module="broken",
            lineno=4,
        )
        source = "import json\n\n\ndef helper(:\n    return json\n"
        index = RepositoryIndex(
            modules={
                "broken": Module(
                    path="broken",
                    symbols=[symbol],
                    source=source,
                    imports=["import json"],
                )
            },
            _symbols=[symbol],
        )

        assert _block_for(index, "broken") == ""

        result = _build(index, _query("helper", max_symbols=1))
        assert len(result.candidates) == 1
        # An unparseable file keeps the legacy whole-module fallback for its source;
        # what it must not grow is a block.
        assert _text(result.candidates[0]) == source



