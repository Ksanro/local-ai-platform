"""Regression tests for shared list-form content normalization."""

from __future__ import annotations

import time

from apps.gateway.session_log import SessionLoggerMiddleware
from packages.context.delta import conversation_key, store_key
from packages.pipeline.context import PipelineContext
from packages.pipeline.history import cap_history
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage


def _list_content(text: str) -> list[dict[str, object]]:
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
    ]


def test_list_content_text_view_reaches_internal_consumers() -> None:
    """Internal consumers read text while provider-bound content remains raw."""
    messages = [
        {"role": "user", "content": _list_content("first debug request")},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": _list_content("<task>debug streaming issue</task>")},
    ]
    context = PipelineContext(request={"messages": messages})

    planning_messages = PlanningStage._extract_messages(context)
    assert planning_messages == ["debug streaming issue"]

    assert RepositoryContextStage._extract_query(context) == "debug streaming issue"

    prior_as_string = [{"role": "user", "content": "first debug request"}]
    assert conversation_key(messages) == store_key(prior_as_string)

    record = SessionLoggerMiddleware._build_record(
        scope={
            "request_data": {
                "model": "qwen36",
                "stream": False,
                "messages": messages,
            },
        },
        start_time=time.perf_counter(),
        response_status=200,
        response_body=[b'{"choices":[{"message":{"content":"answer"}}]}'],
    )
    assert record["last_user_message"] == "<task>debug streaming issue</task>"
    assert record["answer_preview"] == "answer"

    capped, dropped = cap_history(messages, max_history_tokens=0)
    assert dropped > 0
    assert capped[-1]["content"] == messages[-1]["content"]
    assert isinstance(capped[-1]["content"], list)


def test_followup_query_includes_previous_clean_user_task() -> None:
    """Anaphoric follow-ups should carry recent user task text into retrieval."""
    messages = [
        {
            "role": "user",
            "content": (
                "Which component caps forwarded chat history, and where does "
                "that happen relative to repository-context injection?"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "History capping runs inside PipelineEngine, right after the "
                "repository_context stage and before the provider stage."
            ),
        },
        {
            "role": "user",
            "content": (
                "For that capping logic: name the function that applies the "
                "cap and the env var used to force a token budget."
            ),
        },
    ]
    context = PipelineContext(request={"messages": messages})

    query = RepositoryContextStage._extract_query(context)

    assert "Which component caps forwarded chat history" in query
    assert "For that capping logic" in query


def test_non_followup_query_still_uses_last_task_only() -> None:
    """Ordinary multi-turn chats should not drag unrelated prior tasks into retrieval."""
    messages = [
        {"role": "user", "content": "first unrelated request"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "Find answer_preview extraction."},
    ]
    context = PipelineContext(request={"messages": messages})

    assert RepositoryContextStage._extract_query(context) == "Find answer_preview extraction."
