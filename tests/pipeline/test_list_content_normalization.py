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
