"""Session-log tests for the opt-in history-shape summary.

The summary reaches a session record as ``history.shape``, built by
:py:func:`packages.pipeline.history.summarize_history_shape` and surfaced by
``apps.gateway.api.chat`` from pipeline metadata.  These fixtures are native
OpenAI chat-form messages - the shape ``cap_history`` consumes - and the
sentinels planted in them are searched for in the serialized line, because a
record is what a later cap-policy measurement is made from.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from apps.gateway.api.chat import _surface_session_metadata
from apps.gateway.core.config import Settings
from apps.gateway.session_log import SessionLoggerMiddleware
from packages.pipeline.history_shape import SHAPE_SCHEMA_VERSION, summarize_history_shape
from packages.pipeline.response import PipelineResponse

USER_SECRET = "SENTINEL-IN-USER-CONTENT"
SYSTEM_SECRET = "SENTINEL-IN-SYSTEM-PROMPT"
ASSISTANT_SECRET = "SENTINEL-IN-ASSISTANT-CONTENT"
REASONING_SECRET = "SENTINEL-IN-REASONING-CONTENT"
TOOL_NAME_SECRET = "SENTINEL-IN-TOOL-NAME"
ARGUMENT_SECRET = "SENTINEL-IN-TOOL-ARGUMENTS"
CALL_ID_SECRET = "SENTINEL-IN-TOOL-CALL-ID"
RESULT_SECRET = "SENTINEL-IN-TOOL-RESULT-CONTENT"
PATH_SECRET = "packages/SENTINEL-IN-module.py"

ALL_SECRETS = (
    USER_SECRET,
    SYSTEM_SECRET,
    ASSISTANT_SECRET,
    REASONING_SECRET,
    TOOL_NAME_SECRET,
    ARGUMENT_SECRET,
    CALL_ID_SECRET,
    RESULT_SECRET,
    PATH_SECRET,
)

#: The fields a record carried before this feature existed.  The shape knob is
#: off by default, so a default record is still exactly this and nothing more.
RECORD_FIELDS = {
    "timestamp",
    "request_id",
    "conversation_key",
    "model",
    "backend_model",
    "stream",
    "n_messages",
    "last_user_message",
    "context",
    "intent",
    "planning",
    "usage",
    "timing",
    "history",
    "status",
    "error",
    "answer_preview",
}

LEGACY_HISTORY_FIELDS = {
    "cap_enabled",
    "cap_applied",
    "budget",
    "dropped_count",
    "tokens_after",
}

#: The newest user message in the fixture below, deliberately free of any
#: sentinel: the session log has always stored a preview of it, and this feature
#: neither changes that nor depends on it.
BENIGN_QUESTION = "Which file applies the cap?"


def _messages() -> list[dict[str, Any]]:
    """A native transcript whose sentinel text sits only where nothing stores it."""
    return [
        {"role": "system", "content": SYSTEM_SECRET},
        {
            "role": "assistant",
            "content": ASSISTANT_SECRET,
            "reasoning_content": REASONING_SECRET,
            "tool_calls": [
                {
                    "id": CALL_ID_SECRET,
                    "type": "function",
                    "function": {
                        "name": TOOL_NAME_SECRET,
                        "arguments": json.dumps({"path": PATH_SECRET}),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": CALL_ID_SECRET, "content": RESULT_SECRET},
        {"role": "user", "content": BENIGN_QUESTION},
    ]


def _settings(tmp_path: Path, *, session_log_enabled: bool = True) -> Settings:
    """Settings for one middleware run; the shape knob defaults to off."""
    return Settings(
        session_log_enabled=session_log_enabled,
        session_log_path=str(tmp_path / "sessions.jsonl"),
    )


def _run_middleware(
    tmp_path: Path,
    *,
    scope_extra: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], str]:
    """Drive the real middleware over one request and return what it logged.

    Args:
        tmp_path: Where to write the JSONL file.
        scope_extra: Extra ``session_*`` scope entries the endpoint would have
            populated - the channel the shape summary arrives on.
        settings: The settings to run under, defaulting to an enabled logger
            with every opt-in observation off.

    Returns:
        The parsed record and the raw line that was written.
    """
    chosen = settings or _settings(tmp_path)
    scope: dict[str, Any] = {
        "type": "http",
        "path": "/v1/chat/completions",
        "request_id": "shape-req-1",
        "request_data": {
            "model": "qwen38-27b",
            "stream": False,
            "messages": _messages(),
        },
        "session_intent": "DEFAULT",
        "session_context_status": "disabled",
    }
    scope.update(scope_extra or {})

    async def _receive() -> dict[str, Any]:
        """A body the endpoint has already consumed."""
        return {"type": "http.request", "body": b"{}"}

    async def _send(_message: dict[str, Any]) -> None:
        """Nothing to do with the response on the way through."""
        return None

    async def _inner_app(_scope: Any, _recv: Any, send: Any) -> None:
        """Answer with one non-streaming completion."""
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {
                "type": "http.response.body",
                "body": b'{"choices":[{"message":{"role":"assistant","content":"history.py"}}]}',
            }
        )

    middleware = SessionLoggerMiddleware(_inner_app)
    with patch("apps.gateway.session_log.get_settings", return_value=chosen):
        asyncio.run(middleware(scope, _receive, _send))

    lines = (tmp_path / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0]), lines[0]


def _strings(value: Any, found: set[str] | None = None) -> set[str]:
    """Every string value inside a decoded record section, keys excluded."""
    collected: set[str] = set() if found is None else found
    if isinstance(value, str):
        collected.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, collected)
    elif isinstance(value, list):
        for item in value:
            _strings(item, collected)
    return collected


class TestFeatureDisabled:
    """Default off means the record is the record it always was."""

    def test_no_history_shape_field(self, tmp_path: Path) -> None:
        """With the knob off, ``history`` has no ``shape`` key - not a null one."""
        record, _ = _run_middleware(tmp_path)

        assert "shape" not in record["history"]
        assert set(record["history"]) == LEGACY_HISTORY_FIELDS

    def test_record_shape_is_unchanged(self, tmp_path: Path) -> None:
        """Every other field of the record is the one that already existed."""
        record, _ = _run_middleware(tmp_path)

        assert set(record) == RECORD_FIELDS
        assert record["n_messages"] == 4
        assert record["last_user_message"] == BENIGN_QUESTION
        assert record["history"] == {
            "cap_enabled": False,
            "cap_applied": False,
            "budget": 0,
            "dropped_count": 0,
            "tokens_after": 0,
        }

    def test_a_shape_that_never_arrived_is_not_invented(self, tmp_path: Path) -> None:
        """A null or non-dict channel value writes no key rather than a half one."""
        for index, placeholder in enumerate((None, "", 0)):
            slot = tmp_path / f"case-{index}"
            slot.mkdir()

            record, _ = _run_middleware(
                slot, scope_extra={"session_history_shape": placeholder}
            )

            assert "shape" not in record["history"]


class TestFeatureEnabled:
    """The summary is nested in ``history``, beside the cap fields it describes."""

    def test_summary_lands_under_history(self, tmp_path: Path) -> None:
        """The recorded section is the summary of the inbound messages."""
        summary = summarize_history_shape(_messages(), chars_per_token=3.5)

        record, line = _run_middleware(
            tmp_path, scope_extra={"session_history_shape": summary}
        )

        assert record["history"]["shape"] == summary
        assert record["history"]["shape"]["schema"] == SHAPE_SCHEMA_VERSION
        assert record["history"]["shape"]["chars_per_token"] == 3.5
        assert json.dumps(summary) in line

    def test_existing_history_fields_are_unchanged(self, tmp_path: Path) -> None:
        """Adding the summary moves nothing else in the record."""
        off_dir = tmp_path / "off"
        on_dir = tmp_path / "on"
        off_dir.mkdir()
        on_dir.mkdir()

        off, _ = _run_middleware(off_dir)
        on, _ = _run_middleware(
            on_dir,
            scope_extra={"session_history_shape": summarize_history_shape(_messages())},
        )

        assert set(on["history"]) == LEGACY_HISTORY_FIELDS | {"shape"}
        for field in LEGACY_HISTORY_FIELDS:
            assert on["history"][field] == off["history"][field]
        assert set(on) == set(off)

    def test_no_sentinel_appears_anywhere_in_the_line(self, tmp_path: Path) -> None:
        """The whole serialized line is clean, not only the new field."""
        _, line = _run_middleware(
            tmp_path,
            scope_extra={
                "session_history_shape": summarize_history_shape(_messages())
            },
        )

        assert not any(secret in line for secret in ALL_SECRETS)

    def test_the_shape_states_only_structure(self, tmp_path: Path) -> None:
        """Every string in the recorded section is a schema, status or role token."""
        record, _ = _run_middleware(
            tmp_path,
            scope_extra={
                "session_history_shape": summarize_history_shape(_messages())
            },
        )

        assert _strings(record["history"]["shape"]) <= {
            SHAPE_SCHEMA_VERSION,
            "measured",
            "assistant",
            "developer",
            "function",
            "system",
            "tool",
            "user",
            "other",
        }


class _FakeRequest:
    """The minimum slice of a request the surfacing helper reads."""

    def __init__(self, scope: dict[str, Any]) -> None:
        """Hold a mutable scope and empty headers."""
        self.scope = scope
        self.headers: dict[str, str] = {}


class TestEndpointWiring:
    """The endpoint forwards a recorded summary and nothing that was not recorded."""

    def test_a_recorded_shape_reaches_the_scope(self) -> None:
        """``history_shape`` in response metadata becomes ``session_history_shape``."""
        scope: dict[str, Any] = {"type": "http", "request_id": "shape-req-1"}
        summary = summarize_history_shape(_messages(), chars_per_token=3.5)
        response = PipelineResponse(
            data={"choices": []},
            metadata={"history_shape": summary, "history_cap_enabled": False},
        )

        _surface_session_metadata(
            _FakeRequest(scope),  # type: ignore[arg-type]
            AsyncMock(),
            response,
        )

        assert scope["session_history_shape"] == summary

    def test_an_unrecorded_shape_leaves_the_scope_alone(self) -> None:
        """Disabled means the key is never written, so the logger writes no field."""
        scope: dict[str, Any] = {"type": "http", "request_id": "shape-req-1"}
        response = PipelineResponse(data={"choices": []}, metadata={})

        _surface_session_metadata(
            _FakeRequest(scope),  # type: ignore[arg-type]
            AsyncMock(),
            response,
        )

        assert "session_history_shape" not in scope
        assert "history_shape" not in response.metadata
