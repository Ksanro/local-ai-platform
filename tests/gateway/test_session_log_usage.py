"""Tests for session log usage extraction (Fix 1 end-to-end).

Verifies that the session logger correctly extracts usage data from
the final SSE chunk of a streamed response.
"""

from __future__ import annotations

import json

from apps.gateway.session_log import SessionLoggerMiddleware


class TestSessionLogUsageExtraction:
    """Tests for session log usage extraction from SSE responses."""

    def _make_response_body(self, chunks: list[dict[str, object]]) -> list[bytes]:
        """Build a list of SSE body bytes from chunks with newlines."""
        return [
            f"data: {json.dumps(c)}\n".encode("utf-8") for c in chunks
        ] + [b"data: [DONE]\n"]

    def test_streaming_final_chunk_contains_usage(self) -> None:
        """Verify the session logger extracts usage from the final SSE chunk."""
        # Simulate a streaming response where the final chunk contains usage.
        chunks = [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " world"}}]},
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 25,
                },
            },
        ]
        response_body = self._make_response_body(chunks)

        # Build a minimal record like _build_record would.
        record = SessionLoggerMiddleware._build_record(
            scope={
                "request_data": {
                    "model": "test-model",
                    "stream": True,
                    "messages": [{"role": "user", "content": "test"}],
                },
                "session_context_status": "assembled",
                "session_symbols_selected": 1,
                "session_symbols_new": 1,
                "session_symbols_suppressed": 0,
            },
            start_time=0.0,
            response_status=200,
            response_body=response_body,
        )

        assert record["usage"]["prompt_tokens"] == 50
        assert record["usage"]["completion_tokens"] == 25
        assert record["answer_preview"] == "Hello world"

    def test_non_streaming_response_contains_usage(self) -> None:
        """Verify non-streaming JSON responses also extract usage."""
        response_body = [
            json.dumps({
                "choices": [{"message": {"content": "Hello world"}}],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 10,
                },
            }).encode("utf-8"),
        ]

        record = SessionLoggerMiddleware._build_record(
            scope={
                "request_data": {
                    "model": "test-model",
                    "stream": False,
                    "messages": [{"role": "user", "content": "test"}],
                },
                "session_context_status": "assembled",
                "session_symbols_selected": 1,
                "session_symbols_new": 1,
                "session_symbols_suppressed": 0,
            },
            start_time=0.0,
            response_status=200,
            response_body=response_body,
        )

        assert record["usage"]["prompt_tokens"] == 42
        assert record["usage"]["completion_tokens"] == 10
        assert record["answer_preview"] == "Hello world"

    def test_no_usage_defaults_to_none(self) -> None:
        """Verify usage defaults to None when no usage chunk present."""
        response_body = [
            b"data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}\n",
            b"data: [DONE]\n",
        ]

        record = SessionLoggerMiddleware._build_record(
            scope={
                "request_data": {
                    "model": "test-model",
                    "stream": True,
                    "messages": [{"role": "user", "content": "test"}],
                },
                "session_context_status": "assembled",
                "session_symbols_selected": 1,
                "session_symbols_new": 1,
                "session_symbols_suppressed": 0,
            },
            start_time=0.0,
            response_status=200,
            response_body=response_body,
        )

        assert record["usage"]["prompt_tokens"] is None
        assert record["usage"]["completion_tokens"] is None
        assert record["answer_preview"] == "Hello"

    def test_streaming_answer_preview_accumulates_delta_content(self) -> None:
        """Verify streamed delta content is accumulated into answer_preview."""
        response_body = [
            b'data: {"choices": [{"delta": {"role": "assistant"}}]}\n',
            b'data: {"choices": [{"delta": {"content": "The callable is "}}]}\n',
            b'data: {"choices": [{"delta": {"content": "`build_record`."}}]}\n',
            b'data: {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 6}}\n',
            b"data: [DONE]\n",
        ]

        record = SessionLoggerMiddleware._build_record(
            scope={
                "request_data": {
                    "model": "test-model",
                    "stream": True,
                    "messages": [{"role": "user", "content": "test"}],
                },
                "session_context_status": "assembled",
                "session_symbols_selected": 1,
                "session_symbols_new": 1,
                "session_symbols_suppressed": 0,
            },
            start_time=0.0,
            response_status=200,
            response_body=response_body,
        )

        assert record["answer_preview"] == "The callable is `build_record`."

    def test_streaming_answer_preview_truncates_accumulated_content(self) -> None:
        """Verify streamed answer_preview is truncated after accumulation."""
        response_body = self._make_response_body([
            {"choices": [{"delta": {"content": "x" * 300}}]},
            {"choices": [{"delta": {"content": "y" * 300}}]},
        ])

        record = SessionLoggerMiddleware._build_record(
            scope={
                "request_data": {
                    "model": "test-model",
                    "stream": True,
                    "messages": [{"role": "user", "content": "test"}],
                },
                "session_context_status": "assembled",
                "session_symbols_selected": 1,
                "session_symbols_new": 1,
                "session_symbols_suppressed": 0,
            },
            start_time=0.0,
            response_status=200,
            response_body=response_body,
        )

        assert record["answer_preview"] == ("x" * 300) + ("y" * 200)
        assert len(record["answer_preview"]) == 500
