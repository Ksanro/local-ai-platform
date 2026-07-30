"""Content normalization helpers for internal text consumers."""

from __future__ import annotations


def content_to_text(content: object) -> str:
    """Extract plain text from an OpenAI message ``content`` field.

    Content is either a string or a list of parts such as
    ``[{"type": "text", "text": "..."}]``. Non-text parts are ignored.
    Returns the concatenated text, or an empty string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""
