"""Chat-template control tags in repository context are escaped (roadmap Phase H, H2).

On the live Qwen tokenizer a literal ``<think>`` or ``<|im_start|>`` inside message
text is parsed as the control token itself, so repository source that merely
mentions one injected a real control token and cut answers short.  The serializer
escapes those tags in the text it authors - the repository-context block - and
nowhere else.
"""

from __future__ import annotations

import pytest

from packages.context.context_package import ContextPackage, SymbolContext
from packages.serializers import openai as openai_serializer
from packages.serializers.openai import OpenAISerializer, escape_chat_template_tags

LEGEND = openai_serializer._CHAT_TAG_LEGEND

# Tags built from parts so this file's own text never needs the raw form spelled
# in one piece where a reader might mistake it for test input.
LT = "<"
ESC = "&lt;"


def _package(source: str, preview: str = "", docstring: str = "") -> ContextPackage:
    return ContextPackage(
        primary_symbol="pkg/mod.primary",
        primary_symbol_context=SymbolContext(
            qualified_name="pkg/mod.primary",
            signature="def primary() -> None:",
            source=source,
            location=("pkg/mod", 1, 3),
        ),
        supporting_symbols=["pkg/mod.helper"],
        supporting_symbol_contexts=[
            SymbolContext(
                qualified_name="pkg/mod.helper",
                signature="def helper() -> None:",
                docstring=docstring,
                source_preview=preview,
                location=("pkg/mod", 5, 7),
            )
        ],
    )


def _system_text(package: ContextPackage, messages: list[dict[str, object]] | None = None) -> str:
    msgs = messages or [{"role": "user", "content": "question"}]
    return str(OpenAISerializer().serialize(package, msgs).messages[0]["content"])


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        (LT + "think>", ESC + "think>"),
        (LT + "/think>", ESC + "/think>"),
        (LT + "tool_call>", ESC + "tool_call>"),
        (LT + "/tool_call>", ESC + "/tool_call>"),
        (LT + "tool_response>", ESC + "tool_response>"),
        (LT + "/tool_response>", ESC + "/tool_response>"),
        (LT + "|im_start|>", ESC + "|im_start|>"),
        (LT + "|im_end|>", ESC + "|im_end|>"),
        (LT + "|endoftext|>", ESC + "|endoftext|>"),
        (LT + "|file_sep|>", ESC + "|file_sep|>"),
        # The broad <|name|> alphabet: capitals, digits, dot, colon and dash.
        (LT + "|START_OF_TURN.v2:user-1|>", ESC + "|START_OF_TURN.v2:user-1|>"),
    ],
)
def test_each_tag_shape_is_escaped(raw: str, escaped: str) -> None:
    assert escape_chat_template_tags(f"x = '{raw}'") == (f"x = '{escaped}'", 1)


def test_multiple_occurrences_are_all_escaped_and_counted() -> None:
    text = f"{LT}think>a{LT}/think> b {LT}|im_start|>user {LT}|im_end|> {LT}think>"
    out, count = escape_chat_template_tags(text)

    assert count == 5
    assert out == (
        f"{ESC}think>a{ESC}/think> b {ESC}|im_start|>user {ESC}|im_end|> {ESC}think>"
    )


@pytest.mark.parametrize(
    "text",
    [
        "if a < b and c > d:",
        "List<int>",
        "<div class='x'>",
        "<thinking>",
        "<think >",
        "< think>",
        "<|>",
        "<| im_start |>",
        "<|im start|>",
        "a <- b",
        "x << 2",
        "",
    ],
)
def test_ordinary_angle_bracket_text_is_unchanged(text: str) -> None:
    assert escape_chat_template_tags(text) == (text, 0)


def test_already_escaped_text_is_not_escaped_again() -> None:
    once, _ = escape_chat_template_tags(f"{LT}think> {LT}|im_end|>")

    assert escape_chat_template_tags(once) == (once, 0)


def test_tags_in_primary_source_preview_and_docstring_reach_the_prompt_escaped() -> None:
    package = _package(
        source=f'PATTERN = r"^{LT}think>\\s*{LT}/think>"',
        preview=f"text.startswith('{LT}|im_start|>')",
        docstring=f"Wraps the reply in {LT}tool_call> tags.",
    )

    text = _system_text(package)

    for raw in (LT + "think>", LT + "/think>", LT + "|im_start|>", LT + "tool_call>"):
        assert raw not in text
    assert f"{ESC}think>" in text
    assert f"{ESC}/think>" in text
    assert f"{ESC}|im_start|>" in text
    assert f"{ESC}tool_call>" in text


def test_legend_is_added_once_when_something_was_escaped() -> None:
    text = _system_text(_package(source=f"a = '{LT}think>'"))

    assert text.count(LEGEND) == 1
    # The legend sits at the head of the repository context, before the sections.
    assert text.index(LEGEND) < text.index("Primary symbol:")


def test_legend_and_text_are_unchanged_when_nothing_was_escaped() -> None:
    package = _package(source="if a < b:\n    return List<int>")

    text = _system_text(package)

    assert LEGEND not in text
    assert "if a < b:" in text
    assert "List<int>" in text


def test_legend_contains_no_raw_tag() -> None:
    assert escape_chat_template_tags(LEGEND) == (LEGEND, 0)
    assert "<" not in LEGEND
    assert ESC in LEGEND


def test_client_system_user_and_tool_messages_are_not_escaped() -> None:
    tag = LT + "think>"
    struct = LT + "|im_start|>"
    messages: list[dict[str, object]] = [
        {"role": "system", "content": f"Client rules mention {tag} and {struct}."},
        {"role": "user", "content": f"Why does {tag} appear?"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_files", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": f"file text {struct}user"},
        {"role": "user", "content": f"And {LT}/think>?"},
    ]
    package = _package(source=f"a = '{tag}'")

    result = OpenAISerializer().serialize(package, messages)
    system = str(result.messages[0]["content"])

    # The client's system text survives verbatim, ahead of the escaped context.
    assert system.startswith(f"Client rules mention {tag} and {struct}.")
    assert f"a = '{ESC}think>'" in system
    # Every conversation message is byte-for-byte what the client sent.
    assert result.messages[1:] == messages[1:]
