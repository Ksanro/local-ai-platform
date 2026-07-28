"""Tests for the session logger middleware and analyzer."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from apps.gateway.core.config import Settings
from apps.gateway.session_log import SessionLogger, SessionLoggerMiddleware


def _make_settings(
    enabled: bool = False,
    path: str | None = None,
) -> Settings:
    """Create a Settings instance with session_log settings."""
    return Settings(
        session_log_enabled=enabled,
        session_log_path=path or "logs/sessions.jsonl",
    )


# ---------------------------------------------------------------------------
# Test: enabled logger writes records
# ---------------------------------------------------------------------------


def test_enabled_logger_writes_record(tmp_path: Path) -> None:
    """When session_log_enabled=True, a request to /v1/chat/completions
    writes one JSON line per request."""
    log_file = str(tmp_path / "sessions.jsonl")

    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=True, path=log_file)

        # Create a scope with the data that a real FastAPI request would have.
        scope_data = {
            "type": "http",
            "path": "/v1/chat/completions",
            "request_id": "test-req-001",
            "request_data": {
                "model": "qwen36",
                "stream": False,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            "session_intent": "DEFAULT",
            "session_context_status": "assembled",
            "session_symbols_selected": 5,
            "session_symbols_new": 2,
            "session_symbols_suppressed": 3,
            "session_estimated_tokens": 1000,
            "session_context_max_tokens": 4096,
            "session_primary_symbol": "test.symbol",
            "session_planning_user_message_count": 1,
            "session_planning_last_user_message": "Hello",
            "session_planning_matched_keyword": "",
            "session_backend_model": "unsloth/qwen36",
            "session_conversation_key": "__new__",
        }

        received_messages: list[dict] = []

        async def mock_receive():
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            received_messages.append(message)

        async def inner_app(scope, receive, send):
            if scope["type"] == "http":
                # Simulate a successful response.
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}',
                })

        middleware = SessionLoggerMiddleware(inner_app)
        import asyncio
        asyncio.run(middleware(scope_data, mock_receive, mock_send))

    # Check the log file.
    assert log_file
    lines = Path(log_file).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["request_id"] == "test-req-001"
    assert record["status"] == "ok"
    assert record["model"] == "qwen36"
    assert record["stream"] is False
    assert record["n_messages"] == 1
    assert record["last_user_message"] == "Hello"
    assert record["intent"] == "DEFAULT"
    assert record["planning"]["user_message_count"] == 1
    assert record["planning"]["last_user_message"] == "Hello"
    assert record["planning"]["matched_keyword"] == ""
    assert record["context"]["status"] == "assembled"
    assert record["context"]["symbols_selected"] == 5
    assert record["context"]["estimated_tokens"] == 1000
    assert record["context"]["max_tokens"] == 4096
    assert record["answer_preview"] == "ok"


# ---------------------------------------------------------------------------
# Test: disabled logger writes nothing
# ---------------------------------------------------------------------------


def test_disabled_logger_no_op(tmp_path: Path) -> None:
    """When session_log_enabled=False, the middleware is a no-op and
    the log file is never created."""
    log_file = str(tmp_path / "sessions.jsonl")

    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=False, path=log_file)

        received_messages: list[dict] = []

        async def mock_receive():
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            received_messages.append(message)

        async def inner_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}',
                })

        middleware = SessionLoggerMiddleware(inner_app)
        import asyncio
        scope = {
            "type": "http",
            "path": "/v1/chat/completions",
            "request_id": "test-req-002",
        }
        asyncio.run(middleware(scope, mock_receive, mock_send))

    # Log file should NOT exist.
    assert not Path(log_file).exists(), "Log file should not be created when disabled."


# ---------------------------------------------------------------------------
# Test: write failure does not break the response
# ---------------------------------------------------------------------------


def test_write_failure_does_not_break_response(tmp_path: Path) -> None:
    """When the log file write fails, the middleware catches the exception,
    logs a warning, and returns the response unaffected."""
    # Create a read-only file and use it as the log path.
    log_file = str(tmp_path / "readonly.jsonl")
    Path(log_file).write_bytes(b"")
    import os
    os.chmod(log_file, 0o444)  # read-only

    response_sent = False

    async def inner_app(scope: dict, receive: Any, send: Any) -> None:
        nonlocal response_sent
        if scope["type"] == "http":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}',
            })
        response_sent = True

    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=True, path=log_file)

        middleware = SessionLoggerMiddleware(inner_app)

        async def mock_receive() -> dict:
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            pass  # Not used by middleware

        scope = {
            "type": "http",
            "path": "/v1/chat/completions",
            "request_id": "test-req-003",
        }
        # This should NOT raise — the middleware handles all failures gracefully.
        asyncio.run(middleware(scope, mock_receive, mock_send))

    # The inner app was called (response was sent) despite write failure.
    assert response_sent


# ---------------------------------------------------------------------------
# Test: non-chat endpoints are skipped
# ---------------------------------------------------------------------------


def test_non_chat_endpoints_skipped(tmp_path: Path) -> None:
    """Requests to /health are not logged."""
    log_file = str(tmp_path / "sessions.jsonl")

    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=True, path=log_file)

        received_messages: list[dict] = []

        async def mock_receive():
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            received_messages.append(message)

        async def inner_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"status":"ok"}',
                })

        middleware = SessionLoggerMiddleware(inner_app)
        import asyncio
        scope = {
            "type": "http",
            "path": "/health",
            "request_id": "test-req-004",
        }
        asyncio.run(middleware(scope, mock_receive, mock_send))

    # Log file should not exist (no requests logged).
    assert not Path(log_file).exists()


# ---------------------------------------------------------------------------
# Test: answer_preview and last_user_message truncation
# ---------------------------------------------------------------------------


def test_truncation_to_500_chars(tmp_path: Path) -> None:
    """answer_preview and last_user_message are truncated to 500 characters."""
    log_file = str(tmp_path / "sessions.jsonl")

    long_text = "x" * 1000  # 1000 chars, should be truncated to 500
    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=True, path=log_file)

        received_messages: list[dict] = []

        async def mock_receive():
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            received_messages.append(message)

        async def inner_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                await send({
                    "type": "http.response.body",
                    # Simulate a response body with answer > 500 chars
                    "body": (
                        b'{"choices":[{"message":{"role":"assistant","content":"'
                        + long_text.encode()
                        + b'"}}]}'
                    ),
                })

        middleware = SessionLoggerMiddleware(inner_app)
        import asyncio
        scope = {
            "type": "http",
            "path": "/v1/chat/completions",
            "request_id": "test-req-005",
            "request_data": {
                "model": "qwen36",
                "stream": False,
                "messages": [{"role": "user", "content": long_text}],
            },
            "session_intent": "EXPLAIN",
            "session_context_status": "assembled",
            "session_symbols_selected": 10,
            "session_symbols_new": 3,
            "session_symbols_suppressed": 7,
            "session_estimated_tokens": 2000,
            "session_primary_symbol": "test.symbol",
            "session_backend_model": "unsloth/qwen36",
        }
        asyncio.run(middleware(scope, mock_receive, mock_send))

    lines = Path(log_file).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert len(record["last_user_message"]) <= 500
    assert len(record["answer_preview"]) <= 500


# ---------------------------------------------------------------------------
# Test: streaming request with null usage
# ---------------------------------------------------------------------------


def test_streaming_null_usage(tmp_path: Path) -> None:
    """Streaming responses with no usage data log null values, not fabricated ones."""
    log_file = str(tmp_path / "sessions.jsonl")

    with patch("apps.gateway.session_log.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings(enabled=True, path=log_file)

        received_messages: list[dict] = []

        async def mock_receive():
            return {"type": "http.request", "body": b'{}'}

        async def mock_send(message: dict) -> None:
            received_messages.append(message)

        async def inner_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                # Simulate a streaming response without usage.
                await send({
                    "type": "http.response.body",
                    "body": b'{"choices":[{"delta":{"content":"partial"}}]}\ndata: [DONE]',
                })

        middleware = SessionLoggerMiddleware(inner_app)
        import asyncio
        scope = {
            "type": "http",
            "path": "/v1/chat/completions",
            "request_id": "test-req-006",
            "request_data": {
                "model": "qwen36",
                "stream": True,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            "session_intent": "DEFAULT",
            "session_context_status": "disabled",
            "session_symbols_selected": 0,
            "session_symbols_new": 0,
            "session_symbols_suppressed": 0,
            "session_estimated_tokens": 0,
            "session_primary_symbol": "",
        }
        asyncio.run(middleware(scope, mock_receive, mock_send))

    lines = Path(log_file).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["stream"] is True
    assert record["usage"]["prompt_tokens"] is None
    assert record["usage"]["completion_tokens"] is None


# ---------------------------------------------------------------------------
# Test: concurrent writes
# ---------------------------------------------------------------------------


def test_concurrent_writes(tmp_path: Path) -> None:
    """Two threads writing concurrently produce two valid JSON lines."""
    log_file = str(tmp_path / "concurrent.jsonl")

    logger = SessionLogger(log_file)

    def _write(i: int) -> None:
        record = {
            "timestamp": "2026-07-25T10:00:00.000Z",
            "request_id": f"req-{i}",
            "conversation_key": "__new__",
            "model": "qwen36",
            "backend_model": "test",
            "stream": False,
            "n_messages": 1,
            "last_user_message": f"message {i}",
            "context": {"status": "disabled"},
            "intent": "DEFAULT",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "timing": {"total_ms": 1000.0, "ttft_ms": None},
            "status": "ok",
            "error": None,
            "answer_preview": f"answer {i}",
        }
        logger.write(record)

    import threading

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = Path(log_file).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4

    # Each line must be valid JSON.
    for line in lines:
        record = json.loads(line)
        assert "request_id" in record


# ---------------------------------------------------------------------------
# Test: analyzer produces correct counts
# ---------------------------------------------------------------------------


def test_analyzer_fixture_counts() -> None:
    """The analyzer parses the fixture log and produces correct counts.

    The fixture has:
    - 10 records total
    - 1 error, 9 ok
    - Intents: EXPLAIN=2, DEBUG=2, DEFAULT=2, SEARCH=1, REFACTOR=1, IMPLEMENT=1, TEST=1
    - Context: assembled=8, disabled=2
    - Conversation abc12345: 3 turns
    - Conversation def67890: 2 turns
    """
    from scripts.analyze_sessions import _load_records

    fixture_path = "tests/fixtures/session_log_fixture.jsonl"

    records = _load_records(fixture_path)
    assert len(records) == 10

    # ok/error split
    ok_count = sum(1 for r in records if r["status"] == "ok")
    error_count = sum(1 for r in records if r["status"] == "error")
    assert ok_count == 9
    assert error_count == 1

    # Intent distribution
    intents: dict[str, int] = {}
    for r in records:
        intent = r["intent"]
        intents[intent] = intents.get(intent, 0) + 1

    assert intents["EXPLAIN"] == 2
    assert intents["DEBUG"] == 2
    assert intents["DEFAULT"] == 2
    assert intents["SEARCH"] == 1
    assert intents["REFACTOR"] == 1
    assert intents["IMPLEMENT"] == 1
    assert intents["TEST"] == 1

    # Context status distribution
    context_statuses: dict[str, int] = {}
    for r in records:
        status = r["context"]["status"]
        context_statuses[status] = context_statuses.get(status, 0) + 1

    assert context_statuses["assembled"] == 8
    assert context_statuses["disabled"] == 2

    # Timing
    latencies = [
        r["timing"]["total_ms"]
        for r in records
        if r["timing"]["total_ms"] is not None
    ]
    assert len(latencies) == 10
    assert min(latencies) == 200
    assert max(latencies) == 8000

    # Prompt tokens
    tokens = [
        r["usage"]["prompt_tokens"]
        for r in records
        if r["usage"]["prompt_tokens"] is not None
    ]
    assert len(tokens) == 10
    assert min(tokens) == 529
    assert max(tokens) == 6029

    # Conversations
    conversations: dict[str, list] = {}
    for r in records:
        key = r["conversation_key"]
        conversations.setdefault(key, []).append(r)

    assert len(conversations) == 3  # abc12345, def67890, __new__
    assert len(conversations["abc12345"]) == 3
    assert len(conversations["def67890"]) == 2
    assert len(conversations["__new__"]) == 5


# ---------------------------------------------------------------------------
# Test: analyzer output format
# ---------------------------------------------------------------------------


def test_analyzer_output_format(capsys: pytest.CaptureFixture[str]) -> None:
    """The analyzer prints a formatted report with expected sections."""
    from scripts.analyze_sessions import _load_records
    from scripts.analyze_sessions import analyze as _analyze

    fixture_path = "tests/fixtures/session_log_fixture.jsonl"
    records = _load_records(fixture_path)
    _analyze(records)

    captured = capsys.readouterr()
    output = captured.out

    assert "SESSION LOG ANALYSIS" in output
    assert "Total requests:  10" in output
    assert "INTENT DISTRIBUTION" in output
    assert "CONTEXT STATUS DISTRIBUTION" in output
    assert "LATENCY" in output
    assert "PROMPT TOKENS" in output
    assert "DELTA INJECTION" in output
    assert "5 SLOWEST REQUESTS" in output
    assert "ERROR REQUESTS" in output
    assert "END OF REPORT" in output
