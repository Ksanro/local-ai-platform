"""Focused tests for explicit, privacy-safe client session correlation.

The gateway half of the design recorded in
``build/session_correlation_investigation/REPORT.md`` is a receiver: it reads one
dedicated request header (``X-Cline-Session-ID``), validates it, and records the
validated value in the session log.  Nothing here is derived from a transcript,
nothing is hashed, nothing is forwarded upstream, and the whole feature is off
unless ``APP_SESSION_CORRELATION_ENABLED=true``.

Most of these drive the real chat endpoint and the real session-log middleware
over an in-process ASGI app, so what gets asserted is the line that would be
written to ``logs/sessions.jsonl`` rather than a function call made to look like
one.  No backend is contacted: the pipeline stops at a recording stage standing
where ``ProviderStage`` stands, and that capture is also how "never forwarded" is
checked instead of merely claimed.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import json
import re
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.gateway import session_correlation
from apps.gateway.api.chat import router as chat_router
from apps.gateway.core.config import Settings
from apps.gateway.middleware import RequestMiddleware
from apps.gateway.session_correlation import (
    MAX_SESSION_ID_LENGTH,
    SESSION_CORRELATION_HEADER,
    SESSION_CORRELATION_SCHEMA,
    SESSION_CORRELATION_SCOPE_KEY,
    SOURCE_ABSENT,
    SOURCE_CLIENT,
    absent_session,
    client_session,
    is_valid_client_session_id,
    resolve_client_session,
    session_record_field,
)
from apps.gateway.session_log import SessionLoggerMiddleware
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.normalized import NormalizedRequest
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.planning_stage import PlanningStage
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.providers.exceptions import ProviderResponseError
from packages.repository.index.models import (
    Module,
    RepositoryIndex,
    RepositoryStatistics,
    Symbol,
)
from packages.repository.symbols.models import SymbolType

#: A value of the shape Cline generates today: ``<unix-ms>_<5 base36>``.
VALID_ID = "1763302548123_a3k9z"
#: A second one, differing only in what the client's own clock and RNG produced.
OTHER_VALID_ID = "1763302599999_zz9k3"
MAX_VALID_ID = "a" * MAX_SESSION_ID_LENGTH
TOO_LONG_ID = "a" * (MAX_SESSION_ID_LENGTH + 1)

#: The fields a record carried before this feature existed.  Off by default means
#: a default record is still exactly this set and nothing more.
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

#: Everything the endpoint and the engine put on the pipeline's own metadata:
#: the keys a stage could read a session value from.  The endpoint is the only
#: place that could add one, so the set is pinned exactly rather than checked for
#: the absence of one name.
PIPELINE_METADATA_KEYS = {
    "provider_name",
    "model",
    "context_enabled",
    "history_cap_enabled",
    "history_cap_tokens",
    "history_shape_log_enabled",
    "max_tokens_override",
}


class _NeverInspected:
    """A value that reports being looked at.

    Used to show that a disabled feature does not merely discard the header, it
    never touches it: any dunder that reaches for the value raises.
    """

    def _trip(self) -> bool:
        """Fail the test, because a disabled path must not judge this at all."""
        raise AssertionError(
            "a disabled correlation inspected the value it was told not to read"
        )

    def __bool__(self) -> bool:
        """Truthiness is judgement, and a disabled path must not judge."""
        return self._trip()

    __len__ = __bool__
    __str__ = __bool__
    __eq__ = __bool__

    def __repr__(self) -> str:
        """Benign, because a test report rendering is not the code reading it."""
        return "<NeverInspected>"


def _messages(text: str = "Which module applies the cap?") -> list[dict[str, Any]]:
    """One user turn; the content is irrelevant to correlation on purpose."""
    return [{"role": "user", "content": text}]


def _settings(tmp_path: Path, *, enabled: bool, **overrides: Any) -> Settings:
    """The settings for one request: logging on, correlation as asked.

    ``overrides`` win over the defaults, so a test can change one knob without
    restating the six that stay at the shipping values.
    """
    values: dict[str, Any] = {
        "session_log_enabled": True,
        "session_log_path": str(tmp_path / "sessions.jsonl"),
        "session_correlation_enabled": enabled,
        "default_provider": "stub",
        "repository_context_enabled": True,
        "history_cap_enabled": False,
        "history_cap_tokens": 0,
    }
    values.update(overrides)
    return Settings(**values)


async def _sse() -> Any:
    """Two SSE chunks and a terminator, the shape a streaming provider yields."""
    yield 'data: {"id":"stub-1","choices":[{"delta":{"role":"assistant"}}]}\n'
    yield 'data: {"id":"stub-1","choices":[{"delta":{"content":"session_log.py"}}]}\n'
    yield "data: [DONE]\n"


class _ProviderStageDouble:
    """Stands where ``ProviderStage`` stands and captures what it would send.

    ``context.request`` and the payload built from ``context.normalized_request``
    are precisely what ``provider.chat(**kwargs)`` receives, so a value missing
    from both is a value that cannot reach a backend along this path.  Nothing is
    ever sent anywhere: the answer is fabricated here.
    """

    def __init__(self, captured: dict[str, Any], *, outcome: str = "ok") -> None:
        """Record what the pipeline would hand to a provider."""
        self._captured = captured
        self._outcome = outcome

    @property
    def name(self) -> str:
        """Match the real stage's name so the endpoint reads this one."""
        return "provider"

    async def before(self, context: Any) -> Any:
        """Nothing short-circuits here."""
        return None

    async def execute(self, context: Any) -> Any:
        """Capture the upstream shape, then answer as ``outcome`` says."""
        self._captured["request"] = dict(context.request)
        self._captured["context_metadata"] = dict(context.metadata)
        normalized = context.normalized_request
        self._captured["payload"] = (
            normalized.to_provider_payload("backend-model")
            if isinstance(normalized, NormalizedRequest)
            else dict(context.request)
        )

        if self._outcome == "stage_error":
            return PipelineStageResult(
                stage_name="provider",
                success=False,
                error="upstream 500",
                exception=ProviderResponseError("upstream 500", status_code=500),
            )
        if self._outcome == "stream":
            return PipelineStageResult(
                stage_name="provider",
                success=True,
                data={"generator": _sse, "media_type": "text/event-stream"},
            )
        return PipelineStageResult(
            stage_name="provider",
            success=True,
            data={
                "choices": [
                    {"message": {"role": "assistant", "content": "session_log.py"}}
                ]
            },
        )

    async def after(self, context: Any, result: Any) -> Any:
        """Keep the stage's own result."""
        return None


def _index() -> RepositoryIndex:
    """A one-symbol index, so the repository-context stage really runs."""
    path = "packages/context/builder.py"
    symbol = Symbol(
        id="packages.context.builder.ContextBuilder",
        name="ContextBuilder",
        qualified_name="packages.context.builder.ContextBuilder",
        symbol_type=SymbolType.CLASS,
        module=path,
        lineno=1,
    )
    return RepositoryIndex(
        modules={path: Module(path=path, symbols=[symbol])},
        _symbols=[symbol],
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=1,
            class_count=1,
            function_count=0,
            method_count=0,
            symbol_count=1,
        ),
    )


def _app(
    captured: dict[str, Any],
    *,
    outcome: str = "ok",
    stages: list[Any] | None = None,
    pipeline: Any = None,
) -> FastAPI:
    """A gateway app wired the way ``create_app`` wires it, minus the lifespan.

    The session-log middleware is the real one, so the record under test is the
    record a deployment writes.
    """
    app = FastAPI()
    app.include_router(chat_router)
    app.add_middleware(RequestMiddleware)
    app.add_middleware(SessionLoggerMiddleware)

    if pipeline is not None:
        app.state.pipeline = pipeline
    else:
        engine = PipelineEngine()
        default_stages = [_ProviderStageDouble(captured, outcome=outcome)]
        for stage in stages if stages is not None else default_stages:
            engine.register(stage)  # type: ignore[arg-type]
        app.state.pipeline = engine
    return app


def _record_of(tmp_path: Path) -> tuple[dict[str, Any], str]:
    """The one line the middleware wrote, parsed and raw."""
    lines = (tmp_path / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0]), lines[0]


def _run(
    tmp_path: Path,
    *,
    enabled: bool = True,
    headers: Any = None,
    messages: list[dict[str, Any]] | None = None,
    stream: bool = False,
    outcome: str = "ok",
    stage_plan: Any = None,
    settings: Settings | None = None,
    pipeline: Any = None,
) -> tuple[dict[str, Any], str, dict[str, Any], int]:
    """Send one real request through the endpoint and the session logger.

    Args:
        tmp_path: Where this request's ``sessions.jsonl`` lives.
        enabled: ``session_correlation_enabled`` for the run.
        headers: Request headers, as a mapping or as a list of pairs so that a
            duplicated header can be sent.
        messages: The transcript to send; correlation must not care about it.
        stream: Whether to ask for a streamed completion.
        outcome: What the default provider-shaped stage returns - ``ok``,
            ``stream`` or ``stage_error``.
        stage_plan: A callable taking the capture dict and returning the stages
            to register, for runs that need more than the provider double.
        settings: A fully built settings object, overriding ``enabled``.
        pipeline: A pipeline to install verbatim instead of building an engine.

    Returns:
        ``(record, raw_line, captured_upstream, http_status)``.
    """
    chosen = settings or _settings(tmp_path, enabled=enabled)
    if stream and outcome == "ok":
        outcome = "stream"

    captured: dict[str, Any] = {}
    stages = stage_plan(captured) if stage_plan is not None else None
    app = _app(captured, outcome=outcome, stages=stages, pipeline=pipeline)
    body = {"messages": messages or _messages(), "model": "qwen38-27b", "stream": stream}

    with (
        patch("apps.gateway.api.chat.get_settings", return_value=chosen),
        patch("apps.gateway.session_log.get_settings", return_value=chosen),
    ):
        response = TestClient(app).post(
            "/v1/chat/completions", json=body, headers=headers or []
        )

    record, line = _record_of(tmp_path)
    return record, line, captured, response.status_code


def _session_header(value: str) -> dict[str, str]:
    """The one header this feature reads, carrying ``value``."""
    return {SESSION_CORRELATION_HEADER: value}


def _strings(value: Any, found: set[str] | None = None) -> set[str]:
    """Every string inside a decoded record section, keys excluded."""
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


class TestConfiguration:
    """One boolean knob, off until somebody asks for it."""

    def test_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No knob means the gateway does not read the header at all."""
        monkeypatch.delenv("APP_SESSION_CORRELATION_ENABLED", raising=False)

        assert Settings().session_correlation_enabled is False

    def test_app_prefix_enables_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The knob is configured like every other gateway setting."""
        monkeypatch.setenv("APP_SESSION_CORRELATION_ENABLED", "true")

        assert Settings().session_correlation_enabled is True

    def test_explicit_false_keeps_it_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit ``false`` is the default stated, not a different reading."""
        monkeypatch.setenv("APP_SESSION_CORRELATION_ENABLED", "false")

        assert Settings().session_correlation_enabled is False

    def test_the_header_name_is_fixed(self) -> None:
        """A dedicated header keeps the contract narrow.

        A configurable header name would turn this into a general header-copying
        feature, which is the shape the accepted investigation rejected.
        """
        assert SESSION_CORRELATION_HEADER == "X-Cline-Session-ID"
        settings = Settings()
        assert not hasattr(settings, "session_correlation_header"), "the name is not a knob"
        assert not hasattr(settings, "session_correlation_max_length")


class TestValidation:
    """The rules the helper applies before anything is written down."""

    @pytest.mark.parametrize(
        "value",
        [
            VALID_ID,
            OTHER_VALID_ID,
            "a",
            "A1",
            "session.2026-11-17",
            "task:74c2-1_beef",
            "0_0",
            MAX_VALID_ID,
        ],
    )
    def test_valid_values_are_recorded_exactly_as_sent(self, value: str) -> None:
        """Letters, digits and ``. _ : -`` in any mix, up to the cap, pass."""
        assert is_valid_client_session_id(value) is True
        assert resolve_client_session(enabled=True, header_value=value) == client_session(
            value
        )

    def test_boundary_length_is_accepted_and_one_more_is_not(self) -> None:
        """The cap refuses rather than cuts, so a longer value can never share a
        shorter one's identifier."""
        assert len(MAX_VALID_ID) == MAX_SESSION_ID_LENGTH
        assert is_valid_client_session_id(MAX_VALID_ID) is True
        assert is_valid_client_session_id(TOO_LONG_ID) is False
        assert resolve_client_session(enabled=True, header_value=TOO_LONG_ID) == (
            absent_session()
        )

    @pytest.mark.parametrize(
        "value",
        [
            "",
            " ",
            "  ",
            f" {VALID_ID}",
            f"{VALID_ID} ",
            "a b",
            "\t1763302548123_a3k9z",
            "1763302548123_a3k9z\n",
            "a\r\nb",
            "\x00abc",
            "abc\x1f",
            "abc\x7f",
            "caf\u00e9",
            "\uff41\uff42",
            "\u0661\u0662",
            "a\U0001f600b",
            "a/b",
            "a+b",
            "a=b",
            "a,b",
            "a;b",
            "a@b",
            "a#b",
            "a%b",
            'a"b',
            "a'b",
            "a\\b",
            "a<b>",
            "a{b}",
            "a|b",
            "a?b",
            "a*b",
        ],
    )
    def test_unacceptable_values_become_absent(self, value: str) -> None:
        """Empty, over-long, whitespace, control, Unicode and disallowed
        punctuation are all one unavailable state, and none is repaired first."""
        assert is_valid_client_session_id(value) is False
        resolved = resolve_client_session(enabled=True, header_value=value)
        assert resolved == absent_session()
        assert resolved is not None and "id" not in resolved

    @pytest.mark.parametrize(
        "value",
        [
            None,
            12345,
            True,
            1.5,
            VALID_ID.encode(),
            [VALID_ID, OTHER_VALID_ID],
            (VALID_ID,),
            {"id": VALID_ID},
        ],
    )
    def test_non_string_values_are_unavailable(self, value: Any) -> None:
        """A header channel can hand over anything; only a string states a session."""
        assert is_valid_client_session_id(value) is False
        assert resolve_client_session(enabled=True, header_value=value) == (
            absent_session()
        )

    def test_a_value_that_is_too_long_is_never_cut_down(self) -> None:
        """Truncating a 65-character value would hand two sessions one id."""
        resolved = resolve_client_session(enabled=True, header_value=TOO_LONG_ID)

        assert resolved is not None
        assert "id" not in resolved
        assert TOO_LONG_ID[:MAX_SESSION_ID_LENGTH] not in json.dumps(resolved)

    def test_a_padded_value_is_never_trimmed(self) -> None:
        """Stripping whitespace would collapse a padded id onto the bare one."""
        resolved = resolve_client_session(enabled=True, header_value=f" {VALID_ID} ")

        assert resolved is not None
        assert "id" not in resolved
        assert VALID_ID not in json.dumps(resolved)

    def test_disabled_returns_no_object_even_for_a_valid_value(self) -> None:
        """Off is not "record nothing"; it is "have nothing to say"."""
        assert resolve_client_session(enabled=False, header_value=VALID_ID) is None
        assert resolve_client_session(enabled=False, header_value=None) is None

    def test_disabled_does_not_even_look_at_the_value(self) -> None:
        """The disabled path returns before the value is judged in any way."""
        assert resolve_client_session(enabled=False, header_value=_NeverInspected()) is None

    def test_the_only_two_shapes_this_schema_has(self) -> None:
        """Nothing else is expressible, and there is no ``inferred`` source."""
        assert set(client_session(VALID_ID)) == {"schema", "source", "id"}
        assert set(absent_session()) == {"schema", "source"}
        assert client_session(VALID_ID)["source"] == SOURCE_CLIENT
        assert absent_session()["source"] == SOURCE_ABSENT
        assert SESSION_CORRELATION_SCHEMA == "session-correlation-v1"


class TestChannelIsRebuiltNotEchoed:
    """The scope is a channel, so the record re-validates what it carries."""

    def test_a_valid_channel_value_is_rebuilt(self) -> None:
        assert session_record_field(client_session(VALID_ID)) == client_session(VALID_ID)
        assert session_record_field(absent_session()) == absent_session()

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            VALID_ID,
            0,
            {},
            {"source": "client", "id": VALID_ID},
            {"schema": "session-correlation-v2", "source": "absent"},
            {"schema": SESSION_CORRELATION_SCHEMA, "source": "inferred", "id": VALID_ID},
            {"schema": SESSION_CORRELATION_SCHEMA, "source": "client", "id": TOO_LONG_ID},
            {"schema": SESSION_CORRELATION_SCHEMA, "source": "client", "id": " padded "},
            {"schema": SESSION_CORRELATION_SCHEMA, "source": "client", "id": ""},
            {"schema": SESSION_CORRELATION_SCHEMA, "source": "client", "id": None},
        ],
    )
    def test_nothing_else_on_the_channel_becomes_a_field(self, value: Any) -> None:
        """A half-built or foreign object writes no key rather than a wrong one."""
        assert session_record_field(value) is None

    def test_extra_keys_on_the_channel_are_not_carried_into_the_record(self) -> None:
        """Only the three documented keys can ever be serialized."""
        padded = dict(client_session(VALID_ID))
        padded["raw"] = f" {VALID_ID} "
        padded["transcript"] = "SENTINEL-NOT-A-SESSION-VALUE"

        field = session_record_field(padded)

        assert field == client_session(VALID_ID)
        assert field is not None and set(field) == {"schema", "source", "id"}


class TestSessionLogRecord:
    """What the middleware writes, over the real endpoint and the real logger."""

    def test_disabled_writes_no_session_field(self, tmp_path: Path) -> None:
        """Off is the absent key, not a null one, so old records are old records."""
        record, line, _, status = _run(
            tmp_path, enabled=False, headers=_session_header(VALID_ID)
        )

        assert status == 200
        assert "session" not in record
        assert set(record) == RECORD_FIELDS
        assert VALID_ID not in line

    def test_disabled_is_byte_compatible_with_a_request_that_sent_nothing(
        self, tmp_path: Path
    ) -> None:
        """The only differences are the timestamp and the request id.

        A disabled gateway must not even notice that the header arrived, so the
        two records it writes - one to a client that sends it, one to a client
        that does not - have to be the same record.
        """
        sent_dir = tmp_path / "sent"
        quiet_dir = tmp_path / "quiet"
        sent_dir.mkdir()
        quiet_dir.mkdir()

        sent, _, _, _ = _run(sent_dir, enabled=False, headers=_session_header(VALID_ID))
        quiet, _, _, _ = _run(quiet_dir, enabled=False)

        for record in (sent, quiet):
            record.pop("timestamp")
            record.pop("request_id")

        # ``timing`` is a measurement of this run's wall clock rather than a
        # behavior, so the seconds in it are dropped; its shape is checked first,
        # because a disabled feature must not have added a timing field either.
        assert set(sent["timing"]) == set(quiet["timing"])
        sent.pop("timing")
        quiet.pop("timing")

        assert sent == quiet

    def test_enabled_and_valid_records_the_exact_value(self, tmp_path: Path) -> None:
        """The validated value reaches the line byte for byte, and nothing else does."""
        record, line, _, status = _run(
            tmp_path, enabled=True, headers=_session_header(VALID_ID)
        )

        assert status == 200
        assert record["session"] == {
            "schema": SESSION_CORRELATION_SCHEMA,
            "source": "client",
            "id": VALID_ID,
        }
        assert json.dumps(record["session"]) in line

    def test_enabled_and_missing_records_absent(self, tmp_path: Path) -> None:
        """A client that says nothing is recorded as saying nothing."""
        record, _, _, status = _run(tmp_path, enabled=True)

        assert status == 200
        assert record["session"] == {"schema": SESSION_CORRELATION_SCHEMA, "source": "absent"}
        assert "id" not in record["session"]

    @pytest.mark.parametrize(
        "value",
        ["", TOO_LONG_ID, " ", f" {VALID_ID}", f"{VALID_ID}\t", "a b", "a/b", "\x1b[0m"],
    )
    def test_enabled_and_invalid_records_absent_without_the_value(
        self, tmp_path: Path, value: str
    ) -> None:
        """An invalid value is unavailable, and it is not echoed back either."""
        record, line, _, status = _run(
            tmp_path, enabled=True, headers=_session_header(value)
        )

        assert status == 200
        assert record["session"] == {"schema": SESSION_CORRELATION_SCHEMA, "source": "absent"}
        assert "id" not in record["session"]
        # Checked both ways: raw, and in the JSON-escaped form a control character
        # would otherwise reach the line in.  A value with no visible content of its
        # own (empty, or nothing but spaces) has nothing to echo, so the substring
        # question does not apply to it.
        if value.strip():
            assert value not in line
            assert json.dumps(value) not in line

    def test_the_header_is_found_whatever_its_case(self, tmp_path: Path) -> None:
        """HTTP header names are case-insensitive, so the contract is one name."""
        record, _, _, _ = _run(
            tmp_path, enabled=True, headers={"x-cline-session-id": VALID_ID}
        )

        assert record["session"] == client_session(VALID_ID)

    def test_a_header_sent_twice_takes_the_first_value(self, tmp_path: Path) -> None:
        """Repeated header lines resolve the way ``X-Request-ID`` already does.

        ``RequestMiddleware`` reads the first match of a repeated header, and this
        reader does the same.  What must never happen is a merge or a join of the
        two: the recorded value is one the client actually sent, whole.
        """
        record, line, _, _ = _run(
            tmp_path,
            enabled=True,
            headers=[
                (SESSION_CORRELATION_HEADER, VALID_ID),
                (SESSION_CORRELATION_HEADER, OTHER_VALID_ID),
            ],
        )

        assert record["session"] == client_session(VALID_ID)
        assert OTHER_VALID_ID not in line
        assert f"{VALID_ID}," not in line

    def test_a_header_sent_twice_with_a_refused_first_value_is_absent(
        self, tmp_path: Path
    ) -> None:
        """Nothing is silently taken from a second line to build an identifier."""
        record, _, _, _ = _run(
            tmp_path,
            enabled=True,
            headers=[
                (SESSION_CORRELATION_HEADER, f" {VALID_ID} "),
                (SESSION_CORRELATION_HEADER, OTHER_VALID_ID),
            ],
        )

        assert record["session"] == {"schema": SESSION_CORRELATION_SCHEMA, "source": "absent"}

    def test_streamed_and_non_streamed_records_agree(self, tmp_path: Path) -> None:
        """Streaming is a different transport, not a different contract."""
        plain_dir = tmp_path / "plain"
        stream_dir = tmp_path / "stream"
        plain_dir.mkdir()
        stream_dir.mkdir()

        plain, _, _, plain_status = _run(
            plain_dir, enabled=True, headers=_session_header(VALID_ID)
        )
        streamed, _, _, stream_status = _run(
            stream_dir,
            enabled=True,
            headers=_session_header(VALID_ID),
            stream=True,
        )

        assert (plain_status, stream_status) == (200, 200)
        assert streamed["stream"] is True and plain["stream"] is False
        assert streamed["session"] == plain["session"] == client_session(VALID_ID)


class TestPlacementAndIndependence:
    """The field is written before the pipeline and depends on no stage."""

    def test_the_header_is_read_before_the_pipeline_runs(self, tmp_path: Path) -> None:
        """A pipeline that fails on entry still leaves a correlated record.

        ``engine.execute`` is replaced by something that raises before any stage
        can run.  If the endpoint resolved the header after that call - or only
        from what the pipeline handed back - this record would carry no session.
        """
        broken = AsyncMock()
        broken.execute = AsyncMock(side_effect=PipelineError("vLLM unreachable"))

        record, _, _, status = _run(
            tmp_path,
            enabled=True,
            headers=_session_header(VALID_ID),
            pipeline=broken,
        )

        assert status == 501
        assert record["status"] == "error"
        assert record["session"] == client_session(VALID_ID)

    def test_a_provider_error_after_endpoint_entry_keeps_it(self, tmp_path: Path) -> None:
        """A stage failure is returned, not raised, and the record keeps both."""
        record, _, _, status = _run(
            tmp_path,
            enabled=True,
            headers=_session_header(VALID_ID),
            outcome="stage_error",
        )

        assert status == 502
        assert record["status"] == "error"
        assert record["session"] == client_session(VALID_ID)

    def test_an_error_record_with_no_header_keeps_the_absent_form(
        self, tmp_path: Path
    ) -> None:
        """The error path invents nothing and still states what it can."""
        record, _, _, status = _run(tmp_path, enabled=True, outcome="stage_error")

        assert status == 502
        assert record["status"] == "error"
        assert record["session"] == {"schema": SESSION_CORRELATION_SCHEMA, "source": "absent"}

    def test_repository_context_disabled_does_not_remove_it(self, tmp_path: Path) -> None:
        """The real repository-context stage runs, and says "disabled"."""

        def _stages(captured: dict[str, Any]) -> list[Any]:
            return [
                PlanningStage(),
                RepositoryContextStage(index=_index(), context_delta_injection=True),
                _ProviderStageDouble(captured),
            ]

        log_dir = tmp_path / "repo-off"
        chosen = _settings(log_dir, enabled=True, repository_context_enabled=False)
        record, _, _, status = _run(
            log_dir,
            settings=chosen,
            headers=_session_header(VALID_ID),
            stage_plan=_stages,
        )

        assert status == 200
        assert record["context"]["status"] == "disabled"
        assert record["session"] == client_session(VALID_ID)

    def test_delta_injection_disabled_does_not_remove_it(self, tmp_path: Path) -> None:
        """What the delta tracker remembers is not what this record depends on."""

        def _plan(on: bool) -> Any:
            def _stages(captured: dict[str, Any]) -> list[Any]:
                return [
                    PlanningStage(),
                    RepositoryContextStage(index=_index(), context_delta_injection=on),
                    _ProviderStageDouble(captured),
                ]

            return _stages

        on_dir = tmp_path / "delta-on"
        off_dir = tmp_path / "delta-off"

        on, _, _, _ = _run(
            on_dir,
            settings=_settings(on_dir, enabled=True),
            headers=_session_header(VALID_ID),
            stage_plan=_plan(True),
        )
        off, _, _, _ = _run(
            off_dir,
            settings=_settings(off_dir, enabled=True),
            headers=_session_header(VALID_ID),
            stage_plan=_plan(False),
        )

        assert on["session"] == off["session"] == client_session(VALID_ID)

    def test_the_value_changes_nothing_the_client_can_observe(self, tmp_path: Path) -> None:
        """Correlation is a log field: same status, same upstream payload, same
        pipeline metadata - whether the client stated a session, said nothing, or
        said something this gateway refuses to record."""
        reference_record, _, reference, reference_status = _run(
            tmp_path / "quiet", enabled=True
        )

        cases = {
            "stated": _session_header(VALID_ID),
            "absent": None,
            "refused": _session_header(" not a session id "),
        }

        for name, headers in cases.items():
            record, _, captured, status = _run(
                tmp_path / name, enabled=True, headers=headers
            )

            assert status == reference_status == 200, name
            assert record["status"] == "ok", name
            assert captured["request"] == reference["request"], name
            assert captured["payload"] == reference["payload"], name
            assert (
                set(captured["context_metadata"]) == set(reference["context_metadata"])
            ), name
            assert record["context"] == reference_record["context"], name


class TestDeterminismAcrossInstances:
    """The value is the client's, so nothing about this process can move it."""

    def test_two_independent_app_instances_log_the_same_id(self, tmp_path: Path) -> None:
        """Two separately built settings objects, two separately built apps."""
        first_dir = tmp_path / "instance-a"
        second_dir = tmp_path / "instance-b"

        first, _, _, _ = _run(
            first_dir,
            settings=_settings(first_dir, enabled=True),
            headers=_session_header(VALID_ID),
        )
        second, _, _, _ = _run(
            second_dir,
            settings=_settings(second_dir, enabled=True),
            headers=_session_header(VALID_ID),
        )

        assert first["session"] == second["session"] == client_session(VALID_ID)

    def test_two_helper_instances_agree_without_any_app(self) -> None:
        """The helper is a function, not an object: repeated calls are repeated."""
        assert resolve_client_session(enabled=True, header_value=VALID_ID) == (
            resolve_client_session(enabled=True, header_value=VALID_ID)
        )
        assert session_record_field(client_session(VALID_ID)) == client_session(VALID_ID)

    def test_different_client_ids_stay_different(self, tmp_path: Path) -> None:
        """No two stated sessions are made to look like one."""
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"

        a, _, _, _ = _run(a_dir, enabled=True, headers=_session_header(VALID_ID))
        b, _, _, _ = _run(b_dir, enabled=True, headers=_session_header(OTHER_VALID_ID))

        assert a["session"]["id"] != b["session"]["id"]

    def test_the_value_is_never_repeated_across_two_sessions_by_construction(
        self, tmp_path: Path
    ) -> None:
        """Distinct client statements stay distinct, including near-misses."""
        seen: set[str] = set()
        for index, value in enumerate(
            [VALID_ID, OTHER_VALID_ID, MAX_VALID_ID, "session.2026-11-17", "task:1-2_3"]
        ):
            record, _, _, _ = _run(
                tmp_path / f"case-{index}", enabled=True, headers=_session_header(value)
            )
            seen.add(str(record["session"]["id"]))

        assert len(seen) == 5

    def test_the_helper_imports_nothing_that_could_pseudonymise_or_remember(
        self,
    ) -> None:
        """No hashing, no randomness, no clock, no secret, no state module."""
        origin = Path(session_correlation.__file__).resolve()
        imported: set[str] = set()
        for node in ast.walk(ast.parse(origin.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        assert imported <= {"__future__", "re", "typing"}

    def test_the_helper_holds_nothing_between_requests(self) -> None:
        """No container, no instance of anything it defines, no closure.

        A cache, a map, a lock or a counter here would make the logged
        identifier depend on which worker or which restart answered, which is the
        instability the design was corrected to remove.  What remains in the
        module's globals is constants, functions, the compiled pattern and the
        imports that carry them.
        """
        globals_ = {
            name: value
            for name, value in vars(session_correlation).items()
            if not name.startswith("__") and name != "annotations"
        }

        assert not [
            name
            for name, value in globals_.items()
            if isinstance(value, (dict, list, set, frozenset, bytearray))
        ], "the module binds a container, so it binds state"

        assert not [
            name
            for name, value in globals_.items()
            if type(value).__module__ == session_correlation.__name__
        ], "the module binds an instance of its own type"

        assert not [
            name
            for name, value in globals_.items()
            if callable(value) and getattr(value, "__closure__", None)
        ], "a function closes over shared state"


def _refuse(*args: Any, **kwargs: Any) -> str:
    """Fail loudly if the delta content keys are consulted for correlation."""
    raise AssertionError("session correlation consulted a transcript-derived key")


@contextmanager
def _delta_keys_forbidden() -> Any:
    """Poison every content-derived key so a fallback would trip.

    Patched in both the module that defines them and the module that imports
    them, because a fallback added later could reach either binding.
    """
    targets = [
        "packages.context.delta.conversation_key",
        "packages.context.delta.store_key",
        "packages.pipeline.stages.repository_context.conversation_key",
        "packages.pipeline.stages.repository_context.store_key",
    ]
    with ExitStack() as stack:
        for target in targets:
            module_path, _, attribute = target.rpartition(".")
            module = importlib.import_module(module_path)
            if hasattr(module, attribute):
                stack.enter_context(patch(target, side_effect=_refuse))
        yield


class TestNoTranscriptFallback:
    """If the client said nothing, the gateway knows nothing."""

    def test_changing_the_transcript_does_not_move_the_id(self, tmp_path: Path) -> None:
        """The identifier names the session, not what happened in it."""
        first, _, _, _ = _run(
            tmp_path / "short",
            enabled=True,
            headers=_session_header(VALID_ID),
            messages=_messages("Where is the cap applied?"),
        )
        second, _, _, _ = _run(
            tmp_path / "rewritten",
            enabled=True,
            headers=_session_header(VALID_ID),
            messages=[
                {"role": "system", "content": "A different system prompt."},
                {"role": "user", "content": "Now show me the streaming path instead."},
                {"role": "assistant", "content": "It lives in chat.py."},
                {"role": "user", "content": "And the record?"},
            ],
        )

        assert first["n_messages"] != second["n_messages"]
        assert first["session"] == second["session"] == client_session(VALID_ID)

    def test_the_same_transcript_under_two_client_ids_is_two_sessions(
        self, tmp_path: Path
    ) -> None:
        """Identical bytes on the wire are two different statements."""
        messages = _messages("Rank the symbols and explain the budget.")

        a, _, _, _ = _run(
            tmp_path / "a", enabled=True, headers=_session_header(VALID_ID), messages=messages
        )
        b, _, _, _ = _run(
            tmp_path / "b",
            enabled=True,
            headers=_session_header(OTHER_VALID_ID),
            messages=messages,
        )

        assert a["last_user_message"] == b["last_user_message"]
        assert a["session"]["id"] != b["session"]["id"]

    def test_no_id_is_invented_when_the_client_says_nothing(
        self, tmp_path: Path
    ) -> None:
        """No ``id`` key, no digest, no count, no near-match stands in."""
        with _delta_keys_forbidden():
            record, line, _, status = _run(tmp_path, enabled=True)

        assert status == 200
        assert "id" not in record["session"]
        assert record["session"] == {
            "schema": SESSION_CORRELATION_SCHEMA,
            "source": "absent",
        }
        # No digest of anything the client typed: a content fingerprint is what a
        # fallback would have to be, and 32+ hex characters is what one looks like.
        assert not re.search(r"[0-9a-f]{32,}", line)

    def test_the_delta_content_key_is_never_consulted(self, tmp_path: Path) -> None:
        """``conversation_key`` / ``store_key`` move with content, so they are not
        session identifiers and this feature must not reach for them."""
        with _delta_keys_forbidden():
            stated, _, _, _ = _run(
                tmp_path / "stated", enabled=True, headers=_session_header(VALID_ID)
            )
            quiet, _, _, _ = _run(tmp_path / "quiet", enabled=True)

        assert stated["session"] == client_session(VALID_ID)
        assert quiet["session"] == absent_session()

    def test_conversation_key_keeps_its_own_meaning(self, tmp_path: Path) -> None:
        """The existing top-level field is untouched, in both directions."""
        with _delta_keys_forbidden():
            stated, _, _, _ = _run(
                tmp_path / "stated", enabled=True, headers=_session_header(VALID_ID)
            )
            quiet, _, _, _ = _run(tmp_path / "quiet", enabled=True)
            disabled, _, _, _ = _run(
                tmp_path / "disabled", enabled=False, headers=_session_header(VALID_ID)
            )

        for record in (stated, quiet, disabled):
            assert record["conversation_key"] == "__new__"
            assert VALID_ID not in str(record["conversation_key"])


class TestNeverForwarded:
    """Nothing about this header may reach the backend, by any channel."""

    def test_the_upstream_request_carries_no_session_value(
        self, tmp_path: Path
    ) -> None:
        """The payload a provider would receive holds neither the header nor it."""
        _, _, captured, _ = _run(
            tmp_path, enabled=True, headers=_session_header(VALID_ID)
        )

        blob = json.dumps(captured, default=str)
        assert VALID_ID not in blob
        assert SESSION_CORRELATION_HEADER.lower() not in blob.lower()
        assert "cline" not in blob.lower()
        assert SESSION_CORRELATION_SCOPE_KEY not in blob

    def test_a_streamed_request_carries_no_session_value(self, tmp_path: Path) -> None:
        """Streaming builds its payload the same way, and leaks the same nothing."""
        _, _, captured, status = _run(
            tmp_path, enabled=True, headers=_session_header(VALID_ID), stream=True
        )

        assert status == 200
        blob = json.dumps(captured, default=str)
        assert VALID_ID not in blob
        assert "cline" not in blob.lower()

    def test_an_invalid_session_value_is_not_forwarded_as_a_fallback(
        self, tmp_path: Path
    ) -> None:
        """Refusing a value does not quietly turn it into something upstream."""
        _, _, captured, _ = _run(
            tmp_path, enabled=True, headers=_session_header(f" {VALID_ID} ")
        )

        assert VALID_ID not in json.dumps(captured, default=str)

    def test_the_endpoint_adds_nothing_to_the_pipeline_metadata(
        self, tmp_path: Path
    ) -> None:
        """Correlation is not a pipeline input, so it cannot become one later."""
        _, _, captured, _ = _run(
            tmp_path, enabled=True, headers=_session_header(VALID_ID)
        )

        assert set(captured["context_metadata"]) == PIPELINE_METADATA_KEYS
        assert set(captured["request"]) == {"messages", "model", "stream"}

    def test_the_provider_builds_its_own_request_headers(self) -> None:
        """No client header rides upstream, because none is ever copied.

        The providers construct their own header set, so there is no passthrough
        for this gateway to forget to strip.  Nothing here contacts a backend: the
        client is only built and then closed.
        """
        from packages.providers.openai import OpenAIProvider

        provider = OpenAIProvider(base_url="http://127.0.0.1:1/v1", api_key="test-key")
        try:
            client = provider._get_client()
            header_names = {name.lower() for name in client.headers}
            header_values = " ".join(str(value) for value in client.headers.values())

            assert SESSION_CORRELATION_HEADER.lower() not in header_names
            assert "x-task-id" not in header_names
            assert VALID_ID not in header_values
        finally:
            asyncio.run(provider.close())


class TestPrivacyOfTheRecordedObject:
    """The field says three things at most, and one of them is a version."""

    def test_the_client_object_holds_only_the_documented_keys(
        self, tmp_path: Path
    ) -> None:
        record, _, _, _ = _run(
            tmp_path, enabled=True, headers=_session_header(VALID_ID)
        )

        assert set(record["session"]) == {"schema", "source", "id"}
        assert _strings(record["session"]) <= {
            SESSION_CORRELATION_SCHEMA,
            SOURCE_CLIENT,
            SOURCE_ABSENT,
            VALID_ID,
        }

    def test_the_absent_object_holds_only_the_version_and_the_state(
        self, tmp_path: Path
    ) -> None:
        record, _, _, _ = _run(tmp_path, enabled=True)

        assert set(record["session"]) == {"schema", "source"}
        assert _strings(record["session"]) == {SESSION_CORRELATION_SCHEMA, SOURCE_ABSENT}

    @pytest.mark.parametrize(
        "value",
        [
            TOO_LONG_ID,
            f" {VALID_ID} ",
            f"{VALID_ID}\x00",
            "session/id",
            "sentinel-not-a-session-id!",
        ],
    )
    def test_a_refused_value_appears_in_no_field_of_the_line(
        self, tmp_path: Path, value: str
    ) -> None:
        """The log states that a value was refused, never what it was."""
        record, line, _, _ = _run(tmp_path, enabled=True, headers=_session_header(value))

        assert record["session"] == absent_session()
        assert value.strip() not in line
        assert json.dumps(value) not in line

