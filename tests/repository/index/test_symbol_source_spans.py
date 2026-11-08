"""Tests for symbol source spans in the repository index.

Every symbol in these tests is produced by the real AST extractor through
``RepositoryIndexBuilder``, so the ``RepositoryIndex`` accessors take the
span-aware path.  The hand-built ``Symbol`` fixtures elsewhere keep covering
the span-less legacy fallback, where a symbol's "source" is still the whole
module.
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.index.models import RepositoryIndex
from packages.repository.symbols.models import Module, Symbol, SymbolType

TRUNCATION_MARKER = "\n    # ... (truncated)"

MODULE_SOURCE = '''"""Module docstring marker."""

import os

CONSTANT = "module header constant"


def module_helper(value):
    """Return the module helper value."""
    return value


@registry_register
@retry(attempts=3)
def decorated_function(flag):
    """Decorated function docstring.

    Second paragraph.
    """
    if flag:
        return "decorated body"
    return None


async def coroutine_function(items):
    """Await every item."""
    return [item for item in items]


class Widget:
    """Widget class docstring."""

    def first_method(self):
        """First method docstring."""
        return "first method body"

    def second_method(
        self,
        offset,
    ):
        """Second method docstring."""
        return offset + 1

    def outer_method(self):
        def inner_helper(value):
            """Inner helper docstring."""
            return value * 2

        return inner_helper(2)


class Bare:
    def only_method(self):
        return "bare"
'''


def _index(tmp_path: Path) -> RepositoryIndex:
    """Index ``MODULE_SOURCE`` through the production parser and builder."""
    path = tmp_path / "widgets.py"
    path.write_text(MODULE_SOURCE, encoding="utf-8")
    return RepositoryIndexBuilder().build(path)


def _symbol(index: RepositoryIndex, qualified_name: str) -> Symbol:
    matches = [s for s in index.symbols() if s.qualified_name == qualified_name]
    assert matches, f"{qualified_name} is not in the index"
    return matches[0]


def _line_of(text: str, needle: str) -> int:
    """1-based line number of the first line containing ``needle``."""
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found in the module source")


def _slice_lines(text: str, start: int, end: int) -> str:
    lines = text.splitlines(keepends=True)
    return "".join(lines[start - 1 : end])



# ---------------------------------------------------------------------------
# The parser records spans
# ---------------------------------------------------------------------------


class TestParserRecordsSpans:
    """Every extracted symbol carries its own decorator-inclusive span."""

    def test_every_symbol_has_end_and_start_lineno(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        symbols = (
            list(index.classes()) + list(index.functions()) + list(index.methods())
        )
        assert symbols
        for symbol in symbols:
            assert symbol.end_lineno is not None
            assert symbol.start_lineno is not None
            assert symbol.start_lineno <= symbol.lineno <= symbol.end_lineno

    def test_span_start_is_the_earliest_decorator(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        symbol = _symbol(index, "widgets.decorated_function")
        assert symbol.lineno == _line_of(MODULE_SOURCE, "def decorated_function(")
        assert symbol.start_lineno == _line_of(MODULE_SOURCE, "@registry_register")
        assert symbol.end_lineno == _line_of(MODULE_SOURCE, "    return None")

    def test_span_start_is_the_def_line_without_decorators(
        self, tmp_path: Path
    ) -> None:
        index = _index(tmp_path)
        symbol = _symbol(index, "widgets.module_helper")
        assert symbol.start_lineno == symbol.lineno


# ---------------------------------------------------------------------------
# get_symbol_source returns the span, never the module
# ---------------------------------------------------------------------------


class TestSymbolSourceSpan:
    """``get_symbol_source`` slices the module down to the symbol."""

    def test_method_in_a_long_module(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.Widget.first_method"
        symbol = _symbol(index, name)
        source = index.get_symbol_source(name)
        assert source is not None

        lines = source.splitlines()
        assert lines[0] == "    def first_method(self):"
        assert lines[-1] == '        return "first method body"'
        assert source == _slice_lines(
            MODULE_SOURCE, symbol.start_lineno, symbol.end_lineno
        )
        # Original indentation and the file's trailing newline are kept.
        assert source.startswith("    ")
        assert source.endswith("\n")
        # Nothing from the module header or a neighbouring method leaks in.
        for foreign in (
            "Module docstring marker",
            "CONSTANT",
            "import os",
            "class Widget",
            "second_method",
            "outer_method",
            "module_helper",
        ):
            assert foreign not in source

    def test_decorated_function_span_starts_at_the_decorator(
        self, tmp_path: Path
    ) -> None:
        index = _index(tmp_path)
        source = index.get_symbol_source("widgets.decorated_function")
        assert source is not None
        assert source.startswith("@registry_register\n@retry(attempts=3)\ndef ")
        assert 'return "decorated body"' in source
        assert "Module docstring marker" not in source

    def test_class_span_contains_its_methods(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        source = index.get_symbol_source("widgets.Widget")
        assert source is not None
        assert source.startswith("class Widget:")
        for member in (
            "def first_method(self):",
            "def second_method(",
            "def outer_method(self):",
            "def inner_helper(value):",
        ):
            assert member in source
        # The class span stops before the next top-level class.
        assert "class Bare" not in source

    def test_not_found_symbol_returns_none(self, tmp_path: Path) -> None:
        assert _index(tmp_path).get_symbol_source("widgets.absent") is None


# ---------------------------------------------------------------------------
# signature / docstring / location / decorators
# ---------------------------------------------------------------------------


class TestSymbolFieldSpans:
    """The derived fields describe the symbol, not its module."""

    def test_signature_is_the_def_line(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_signature("widgets.Widget.first_method") == (
            "def first_method(self):"
        )
        assert index.get_symbol_signature("widgets.decorated_function") == (
            "def decorated_function(flag):"
        )

    def test_signature_of_a_multi_line_def_is_its_first_line(
        self, tmp_path: Path
    ) -> None:
        index = _index(tmp_path)
        signature = index.get_symbol_signature("widgets.Widget.second_method")
        assert signature == "def second_method("

    def test_signature_is_the_class_line(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_signature("widgets.Widget") == "class Widget:"

    def test_docstring_is_the_symbols_own_not_the_modules(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_docstring("widgets.module_helper") == (
            "Return the module helper value."
        )
        assert index.get_symbol_docstring("widgets.Widget") == (
            "Widget class docstring."
        )
        assert index.get_symbol_docstring("widgets.Widget.first_method") == (
            "First method docstring."
        )
        for name in ("widgets.module_helper", "widgets.Widget.first_method"):
            docstring = index.get_symbol_docstring(name) or ""
            assert "Module docstring marker" not in docstring

    def test_multiline_docstring_is_dedented(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        docstring = index.get_symbol_docstring("widgets.decorated_function")
        assert docstring == "Decorated function docstring.\n\nSecond paragraph."

    def test_symbol_without_a_docstring_returns_none(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_docstring("widgets.Bare") is None
        assert index.get_symbol_docstring("widgets.Bare.only_method") is None

    def test_location_is_the_symbols_own_lines(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.Widget.first_method"
        symbol = _symbol(index, name)
        module_path, start_line, end_line = index.get_symbol_location(name) or ()
        assert module_path == "widgets"
        assert start_line == symbol.lineno
        assert end_line == symbol.end_lineno
        assert end_line != len(MODULE_SOURCE.splitlines())

    def test_decorators_are_the_ast_names(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_decorators("widgets.decorated_function") == (
            ["registry_register", "retry"]
        )

    def test_decorators_are_none_when_the_symbol_has_none(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        assert index.get_symbol_decorators("widgets.module_helper") is None
        assert index.get_symbol_decorators("widgets.Widget") is None

    def test_full_context_describes_the_symbol(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.decorated_function"
        symbol = _symbol(index, name)
        context = index.get_symbol_full_context(name)
        assert context["signature"] == "def decorated_function(flag):"
        assert context["docstring"] == (
            "Decorated function docstring.\n\nSecond paragraph."
        )
        assert context["decorators"] == ["registry_register", "retry"]
        assert context["location"] == ("widgets", symbol.lineno, symbol.end_lineno)
        source = context["source"]
        assert isinstance(source, str)
        assert source.startswith("@registry_register\n")


# ---------------------------------------------------------------------------
# nested and async definitions
# ---------------------------------------------------------------------------


class TestNestedAndAsyncSpans:
    """Nested and coroutine definitions get their own spans."""

    def test_nested_function_span(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.Widget.outer_method.inner_helper"
        source = index.get_symbol_source(name)
        assert source is not None
        assert source.startswith("        def inner_helper(value):")
        assert "return value * 2" in source
        assert "return inner_helper(2)" not in source
        assert index.get_symbol_docstring(name) == "Inner helper docstring."

    def test_enclosing_span_contains_the_nested_def(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        source = index.get_symbol_source("widgets.Widget.outer_method")
        assert source is not None
        assert "def inner_helper(value):" in source
        assert "return inner_helper(2)" in source

    def test_async_def_span(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.coroutine_function"
        source = index.get_symbol_source(name)
        assert source is not None
        assert source.startswith("async def coroutine_function(items):")
        assert "Module docstring marker" not in source
        assert index.get_symbol_signature(name) == (
            "async def coroutine_function(items):"
        )
        assert index.get_symbol_docstring(name) == "Await every item."



# ---------------------------------------------------------------------------
# excerpts of spans
# ---------------------------------------------------------------------------


class TestSourceExcerptsOfSpans:
    """``get_symbol_source_excerpts`` slices the span, not the module."""

    def test_short_span_is_returned_untruncated(self, tmp_path: Path) -> None:
        index = _index(tmp_path)
        name = "widgets.Widget.first_method"
        excerpt = index.get_symbol_source_excerpts(name, max_tokens=256)
        assert excerpt == index.get_symbol_source(name)
        assert excerpt is not None
        assert TRUNCATION_MARKER not in excerpt

    def test_long_span_is_truncated_from_the_start_of_the_span(
        self, tmp_path: Path
    ) -> None:
        index = _index(tmp_path)
        excerpt = index.get_symbol_source_excerpts(
            "widgets.Widget", max_tokens=20, chars_per_token=4.0
        )
        assert excerpt is not None
        assert excerpt.startswith("class Widget:")
        assert excerpt.endswith(TRUNCATION_MARKER)
        assert len(excerpt) <= 20 * 4 + len(TRUNCATION_MARKER)
        assert "Module docstring marker" not in excerpt


# ---------------------------------------------------------------------------
# The span-less legacy fallback
# ---------------------------------------------------------------------------


def _legacy_index() -> RepositoryIndex:
    """An index whose symbol carries no span, as a hand-built fixture would."""
    source = '"""Legacy module docstring."""\n\n\ndef foo():\n    pass\n'
    symbol = Symbol(
        id="mod.foo",
        name="foo",
        qualified_name="mod.foo",
        symbol_type=SymbolType.FUNCTION,
        module="mod.py",
        lineno=4,
    )
    module = Module(path="mod.py", symbols=[symbol], source=source)
    return RepositoryIndex(
        modules={"mod.py": module},
        _symbols=[symbol],
        _relationships=[],
    )


class TestLegacyFallbackWithoutSpans:
    """A span-less symbol keeps today's whole-module behaviour."""

    def test_span_fields_default_to_none(self) -> None:
        symbol = Symbol(
            id="mod.foo",
            name="foo",
            qualified_name="mod.foo",
            symbol_type=SymbolType.FUNCTION,
            module="mod.py",
            lineno=4,
        )
        assert symbol.end_lineno is None
        assert symbol.start_lineno is None

    def test_source_is_the_whole_module(self) -> None:
        index = _legacy_index()
        assert index.get_symbol_source("mod.foo") == (
            '"""Legacy module docstring."""\n\n\ndef foo():\n    pass\n'
        )

    def test_docstring_is_the_first_triple_quoted_string(self) -> None:
        index = _legacy_index()
        assert index.get_symbol_docstring("mod.foo") == "Legacy module docstring."

    def test_location_end_is_the_end_of_the_module(self) -> None:
        index = _legacy_index()
        module_path, start_line, end_line = index.get_symbol_location("mod.foo") or ()
        assert module_path == "mod.py"
        assert start_line == 4
        assert end_line == 5

    def test_decorators_are_scanned_after_the_def(self) -> None:
        index = _legacy_index()
        assert index.get_symbol_decorators("mod.foo") is None

    def test_full_context_uses_the_whole_module(self) -> None:
        index = _legacy_index()
        context = index.get_symbol_full_context("mod.foo")
        assert context["signature"] == '"""Legacy module docstring."""'
        assert context["source"] == (
            '"""Legacy module docstring."""\n\n\ndef foo():\n    pass\n'
        )



# ---------------------------------------------------------------------------
# a span holding its own unindented text
# ---------------------------------------------------------------------------


class TestSpanWithUnindentedStringContent:
    """A symbol whose body carries column-zero text still yields its fields."""

    SOURCE = (
        '"""Module docstring."""\n'
        "\n"
        "\n"
        "def embed():\n"
        '    """Embed docstring."""\n'
        "    text = '''\n"
        "column zero text inside a string literal\n"
        "    indented tail\n"
        "'''\n"
        "    return text\n"
    )

    def test_docstring_survives_the_unindented_body(self, tmp_path: Path) -> None:
        path = tmp_path / "embed.py"
        path.write_text(self.SOURCE, encoding="utf-8")
        index = RepositoryIndexBuilder().build(path)

        assert index.get_symbol_docstring("embed.embed") == "Embed docstring."
        assert index.get_symbol_signature("embed.embed") == "def embed():"
        assert index.get_symbol_source("embed.embed") == self.SOURCE.split("\n", 3)[3]

