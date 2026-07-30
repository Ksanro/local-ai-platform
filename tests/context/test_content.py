"""Tests for OpenAI message content normalization."""

from __future__ import annotations

from packages.context.content import content_to_text


def test_content_to_text_returns_string_as_is() -> None:
    assert content_to_text("hello") == "hello"


def test_content_to_text_joins_list_text_parts() -> None:
    content = [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
        {"type": "text", "text": "world"},
    ]

    assert content_to_text(content) == "hello world"


def test_content_to_text_includes_bare_string_items() -> None:
    content = [
        {"type": "text", "text": "hello"},
        "middle",
        {"text": "world"},
    ]

    assert content_to_text(content) == "hello middle world"


def test_content_to_text_ignores_non_text_parts() -> None:
    content = [
        {"type": "text", "text": 123},
        {"type": "image_url", "text": None},
        {"type": "input_audio", "audio": "ignored"},
        42,
    ]

    assert content_to_text(content) == ""


def test_content_to_text_returns_empty_for_other_shapes() -> None:
    assert content_to_text(None) == ""
    assert content_to_text({"type": "text", "text": "hello"}) == ""
    assert content_to_text(123) == ""
