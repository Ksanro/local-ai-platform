"""JSONL session logger for the gateway.

Records every ``/v1/chat/completions`` request/response as a structured
JSON object per line.  Enables post-request analysis of actual inputs
and outputs during agentic sessions.

Configuration
-------------

All settings live in the application ``Settings`` object
(:py:class:`apps.gateway.core.config.Settings`):

* ``session_log_enabled`` (bool, default ``False``) — when ``False``
  the logger is a complete no-op with zero overhead on the request path.
* ``session_log_path`` (str, default ``"logs/sessions.jsonl"``) — path
  to the JSONL log file.  The parent directory is created automatically.

Usage
-----

.. code-block:: python

    from apps.gateway.session_log import SessionLoggerMiddleware

    app.add_middleware(SessionLoggerMiddleware)

The middleware reads context metadata from ``request.scope`` (populated
by the chat endpoint handler) and appends one JSON line per completed
request.  Write failures are silently dropped so they never affect the
response.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.gateway.core.config import get_settings

logger = logging.getLogger(__name__)


def _truncate(value: Any, max_length: int = 500) -> str:
    """Truncate a value to ``max_length`` characters.

    Args:
        value: The value to truncate.
        max_length: Maximum number of characters.

    Returns:
        The string value truncated to ``max_length`` characters.
    """
    if value is None:
        return ""
    text = str(value)
    if len(text) > max_length:
        return text[:500]
    return text


def _utc_timestamp() -> str:
    """Return the current UTC time in ISO-8601 with trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class SessionLogger:
    """Append-only JSONL logger.

    Creates the parent directory if absent.  Flushes after each write
    so a crash does not lose the tail.  Thread-safe via a lock.

    Attributes:
        path: Path to the JSONL file.
        _lock: Thread lock for safe concurrent writes.
        _file: Open file handle in append mode.
    """

    def __init__(self, path: str) -> None:
        """Initialize the session logger.

        Creates the parent directory if absent and opens the file in
        append mode.

        Args:
            path: Path to the JSONL log file.
        """
        self._path = path
        self._lock = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115

    def write(self, record: dict[str, Any]) -> None:
        """Append a single JSON record to the log file.

        Flushes after each write.  The caller must NOT hold ``_lock`` —
        this method acquires it internally.

        Args:
            record: The session record to write.
        """
        line = json.dumps(record, default=str) + "\n"
        with self._lock:
            self._file.write(line)
            self._file.flush()

    def close(self) -> None:
        """Close the log file handle."""
        if self._file is not None and not self._file.closed:
            self._file.close()

    def __del__(self) -> None:
        """Ensure the file handle is closed on garbage collection."""
        try:
            self.close()
        except Exception:
            pass


class SessionLoggerMiddleware:
    """ASGI middleware that logs completed ``/v1/chat/completions`` requests.

    Reads context metadata from ``request.scope`` (populated by the
    chat endpoint handler) and appends one JSON line per completed
    request.  Write failures are silently dropped so they never affect
    the response.

    Only logs requests to ``/v1/chat/completions`` — skips
    ``/health``, ``/version``, ``/v1/models``.
    """

    def __init__(self, app: Any) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application.
        """
        self._app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Process the request and log the response.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        settings = get_settings()
        if not settings.session_log_enabled:
            await self._app(scope, receive, send)
            return

        # Only log /v1/chat/completions requests.
        path = scope.get("path", "")
        if path != "/v1/chat/completions":
            await self._app(scope, receive, send)
            return

        response_body: list[bytes] = []
        response_status: int = 0
        logger_instance: SessionLogger | None = None

        try:
            # Capture timing start.
            start_time = time.perf_counter()

            async def _send(message: dict[str, Any]) -> None:
                nonlocal response_status
                if message["type"] == "http.response.start":
                    response_status = message.get("status", response_status)
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        response_body.append(body)
                # ALWAYS forward the event downstream, or the client never
                # receives the response.
                await send(message)

            # Call the next app in the chain.
            await self._app(scope, receive, _send)

            # Read metadata from request.scope (populated by chat.py).
            record = self._build_record(
                scope,
                start_time,
                response_status,
                response_body,
            )

            logger_instance = SessionLogger(settings.session_log_path)

            try:
                logger_instance.write(record)
            except Exception:
                logger.warning(
                    "session_log write failed",
                    exc_info=True,
                )
                # Drop the record — never affect the response.
        except Exception:
            logger.warning(
                "session_log middleware failed",
                exc_info=True,
            )
        finally:
            if logger_instance is not None:
                logger_instance.close()

    @staticmethod
    def _build_record(
        scope: dict[str, Any],
        start_time: float,
        response_status: int,
        response_body: list[bytes],
    ) -> dict[str, Any]:
        """Build a session log record from the request/response metadata.

        Args:
            scope: The ASGI scope.
            start_time: perf_counter timestamp before the request.
            response_status: HTTP response status code.
            response_body: Raw response body bytes.

        Returns:
            A session log record dict.
        """
        # --- basic fields ---
        request_id = scope.get("request_id", "")
        now = _utc_timestamp()

        # Request body from scope (populated by FastAPI).
        request_data = scope.get("request_data", {})

        model = request_data.get("model", "")
        stream = request_data.get("stream", False)

        messages = request_data.get("messages", [])
        n_messages = len(messages)

        # Last user message.
        last_user_message = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_user_message = _truncate(content, 500)
                elif isinstance(content, list):
                    # Handle multimodal content.
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(str(part.get("text", "")))
                    last_user_message = _truncate(" ".join(text_parts), 500)
                break

        # Conversation key.
        conversation_key = scope.get("session_conversation_key", "__new__")

        # --- context metadata (from RepositoryContextStage) ---
        context = {
            "status": scope.get("session_context_status", "disabled"),
            "symbols_selected": scope.get("session_symbols_selected", 0),
            "symbols_new": scope.get("session_symbols_new", 0),
            "symbols_suppressed": scope.get("session_symbols_suppressed", 0),
            "estimated_tokens": scope.get("session_estimated_tokens", 0),
            "primary_symbol": scope.get("session_primary_symbol", ""),
        }

        # Intent from PlanningStage.
        intent = scope.get("session_intent", "DEFAULT")

        # Backend model.
        backend_model = scope.get("session_backend_model", model)

        # --- usage (from provider response) ---
        usage: dict[str, Any] = {"prompt_tokens": None, "completion_tokens": None}
        if response_body:
            try:
                body_str = b"".join(response_body).decode("utf-8")
                # For streaming responses, the last data line contains usage.
                # For non-streaming, it's the full JSON.
                for line in body_str.split("\n"):
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str != "[DONE]":
                            try:
                                chunk = json.loads(data_str)
                                if "usage" in chunk:
                                    usage = {
                                        "prompt_tokens": chunk["usage"].get(
                                            "prompt_tokens"
                                        ),
                                        "completion_tokens": chunk["usage"].get(
                                            "completion_tokens"
                                        ),
                                    }
                            except (json.JSONDecodeError, KeyError):
                                pass
                    elif line and not line.startswith("data:"):
                        # Try parsing as direct JSON (non-streaming).
                        try:
                            parsed = json.loads(line)
                            if "usage" in parsed:
                                usage = {
                                    "prompt_tokens": parsed["usage"].get(
                                        "prompt_tokens"
                                    ),
                                    "completion_tokens": parsed["usage"].get(
                                        "completion_tokens"
                                    ),
                                }
                                break
                        except json.JSONDecodeError:
                            pass
            except UnicodeDecodeError:
                pass

        # --- timing ---
        total_ms = round((time.perf_counter() - start_time) * 1000, 1)
        ttft_ms = scope.get("session_ttft_ms")
        if ttft_ms is not None:
            ttft_ms = round(ttft_ms, 1)

        # Timing breakdown from stage durations.
        stage_durations_ms = scope.get("session_stage_durations_ms", {})
        pipeline_ms = scope.get("session_pipeline_ms")
        provider_wait_ms = scope.get("session_provider_wait_ms")

        # Build the stages sub-dict with the expected keys.
        _known_stages = [
            "model_resolution_ms",
            "planning_ms",
            "repository_context_ms",
            "workflow_ms",
            "provider_ms",
        ]
        stages_breakdown: dict[str, float] = {}
        for key in _known_stages:
            val = stage_durations_ms.get(key)
            if val is not None:
                stages_breakdown[key] = round(float(val), 1)
        # Capture any extra stages not in the known list.
        for key, val in stage_durations_ms.items():
            if key not in stages_breakdown:
                stages_breakdown[key] = round(float(val), 1)

        # --- status and error ---
        status = "ok" if response_status < 400 else "error"
        error = None
        if status == "error" and response_body:
            try:
                body_str = b"".join(response_body).decode("utf-8")
                for line in body_str.split("\n"):
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str != "[DONE]":
                            try:
                                chunk = json.loads(data_str)
                                if "error" in chunk:
                                    error = _truncate(str(chunk["error"]), 500)
                                    break
                            except json.JSONDecodeError:
                                pass
                    else:
                        try:
                            parsed = json.loads(line)
                            if "error" in parsed:
                                error = _truncate(str(parsed["error"]), 500)
                                break
                        except json.JSONDecodeError:
                            pass
            except UnicodeDecodeError:
                pass

        # --- answer preview ---
        answer_preview = ""
        if response_body and status == "ok":
            try:
                body_str = b"".join(response_body).decode("utf-8")
                # Non-streaming: full JSON response.
                for line in body_str.split("\n"):
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str != "[DONE]":
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices", [])
                                if choices:
                                    message = choices[0].get("message", {})
                                    content = message.get("content", "")
                                    answer_preview = _truncate(content, 500)
                            except json.JSONDecodeError:
                                pass
                    elif line and not line.startswith("data:"):
                        try:
                            parsed = json.loads(line)
                            choices = parsed.get("choices", [])
                            if choices:
                                message = choices[0].get("message", {})
                                content = message.get("content", "")
                                answer_preview = _truncate(content, 500)
                            break
                        except json.JSONDecodeError:
                            pass
            except UnicodeDecodeError:
                pass

        return {
            "timestamp": now,
            "request_id": request_id,
            "conversation_key": conversation_key,
            "model": model,
            "backend_model": backend_model,
            "stream": stream,
            "n_messages": n_messages,
            "last_user_message": last_user_message,
            "context": context,
            "intent": intent,
            "usage": usage,
            "timing": {
                "total_ms": total_ms,
                "ttft_ms": ttft_ms,
                "pipeline_ms": pipeline_ms,
                "provider_wait_ms": provider_wait_ms,
                "stages": stages_breakdown,
            },
            "status": status,
            "error": error,
            "answer_preview": answer_preview,
        }
