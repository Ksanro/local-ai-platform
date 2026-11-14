"""Which empty path a request took must read back from the session log.

The repository-context stage already says the reason on its log line, but a log
line is not what gets counted: the question "how many of the 200 November
requests retrieved for nothing?" is answered out of
``logs/cline_sessions.jsonl``, so the reason travels from the stage result
through the endpoint scope into the record, exactly as the changed-file counters
do.  Both gateway ends are checked against the same strings, so a rename cannot
pass one side and fail the other.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

from apps.gateway.api.chat import _surface_session_metadata
from apps.gateway.session_log import SessionLoggerMiddleware
from packages.pipeline.result import PipelineStageResult

#: The reasons the stage can state, in the words it uses.
BOOKKEEPING_ONLY = "client_bookkeeping_only"
NO_RELEVANT_SYMBOLS = "no_relevant_symbols"
NON_TASK = "non_task"


def _stage_result(data: dict[str, Any]) -> PipelineStageResult:
    """A repository-context result, as the engine hands it to the endpoint."""
    return PipelineStageResult(stage_name="repository_context", success=True, data=data)


def _empty_data(reason: str) -> dict[str, Any]:
    """The counts an empty path returns, with the reason beside them."""
    return {
        "symbols_selected": 0,
        "symbols_new": 0,
        "symbols_suppressed": 0,
        "max_context_tokens": 4096,
        "changed_baseline_ms": 0.0,
        "empty_reason": reason,
    }


def _surface(result: PipelineStageResult) -> dict[str, Any]:
    """Run the endpoint's metadata surfacing over a minimal scope."""
    scope: dict[str, Any] = {
        "request_data": {
            "model": "test-model",
            "stream": False,
            "messages": [{"role": "user", "content": "how does the store work"}],
        },
        "session_id": "test-session",
    }
    response = SimpleNamespace(
        stage_results={"repository_context": result},
        metadata={},
    )
    _surface_session_metadata(  # type: ignore[arg-type]
        SimpleNamespace(scope=scope),  # type: ignore[arg-type]
        None,
        response,
    )
    return scope


def _record(scope: dict[str, Any]) -> dict[str, Any]:
    """Build the session record for a scope, the way the middleware writes it."""
    return SessionLoggerMiddleware._build_record(
        scope=scope,
        start_time=time.time() - 0.05,
        response_status=200,
        response_body=[
            json.dumps(
                {
                    "choices": [{"message": {"content": "It keeps widgets."}}],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 8},
                }
            ).encode("utf-8")
        ],
    )


def test_the_stage_reason_survives_the_endpoint_into_the_scope() -> None:
    """The reason is copied, not recomputed, and the status stays ``empty``."""
    scope = _surface(_stage_result(_empty_data(BOOKKEEPING_ONLY)))

    assert scope["session_context_status"] == "empty"
    assert scope["session_context_empty_reason"] == BOOKKEEPING_ONLY


def test_the_record_states_which_empty_path_the_request_took() -> None:
    """A reader can tell the three empties apart without opening a log file."""
    bookkeeping = _record(_surface(_stage_result(_empty_data(BOOKKEEPING_ONLY))))["context"]
    ranked = _record(_surface(_stage_result(_empty_data(NO_RELEVANT_SYMBOLS))))["context"]
    greeting = _record(_surface(_stage_result(_empty_data(NON_TASK))))["context"]

    assert bookkeeping["empty_reason"] == BOOKKEEPING_ONLY
    assert ranked["empty_reason"] == NO_RELEVANT_SYMBOLS
    assert greeting["empty_reason"] == NON_TASK


def test_an_assembled_request_states_no_reason() -> None:
    """Nothing was skipped, so there is nothing to state."""
    data = _empty_data("")
    data["package"] = SimpleNamespace(primary_symbol="widget.Store", estimated_tokens=90)
    data["symbols_selected"] = 3
    scope = _surface(_stage_result(data))

    assert scope["session_context_status"] == "assembled"
    assert scope["session_context_empty_reason"] == ""
    assert _record(scope)["context"]["empty_reason"] == ""


def test_a_record_always_carries_the_field() -> None:
    """A request the stage never finished reads as no reason, not as a missing key."""
    context = _record(_surface(_stage_result(_empty_data(""))))["context"]

    assert "empty_reason" in context
    assert context["empty_reason"] == ""


def test_a_degraded_request_leaves_the_reason_empty() -> None:
    """``degraded`` is a failure, not an empty path; it must not borrow the field."""
    result = PipelineStageResult(
        stage_name="repository_context",
        success=False,
        data=None,
        error="simulated stage failure",
    )
    scope = _surface(result)

    assert scope["session_context_status"] == "degraded"
    assert scope["session_context_empty_reason"] == ""
