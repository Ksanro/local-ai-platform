"""Tests for changed-file promotion fields in session metadata and JSONL.

Promotion is only observable if it survives all the way to the session record,
and it is only safe to record if it carries counts.  These tests pin both ends:
the gateway mapping from the ``repository_context`` stage result onto the ASGI
scope, and the record the session logger writes.

The fields are counterfactual.  The stage re-ranks the same request without the
working-tree bonus and compares the two contexts, so a test that could pass on
"changed files were present" would be pinning the wrong contract.  No Git,
model, or network is involved; the stage result is handed over directly.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

from apps.gateway.api.chat import _surface_changed_file_promotion, _surface_session_metadata
from apps.gateway.session_log import SessionLoggerMiddleware
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages.repository_context import INERT_PROMOTION

#: The promotion fields exactly as the stage emits them.  Both gateway ends are
#: checked against this, so a rename cannot pass one side and fail the other.
PROMOTION_FIELDS = tuple(INERT_PROMOTION)

PROMOTION_SCOPE_KEYS = tuple(f"session_{field}" for field in PROMOTION_FIELDS)

#: Anything that must never reach a session record: a repository path, an index
#: module key, and a symbol name a promotion counter could name.
FORBIDDEN_STRINGS = (
    "C:\\Users\\dev\\repo",
    "modules/widget.py",
    "modules/widget",
    "widget.WidgetStore",
)

#: A fully populated stage result: the bonus moved the primary and sent one
#: symbol the no-bonus context did not contain, against a comparison that ran.
OBSERVED: dict[str, Any] = {
    "changed_files_count": 2,
    "changed_symbols_selected": 3,
    "changed_primary_promoted": True,
    "changed_symbols_promoted": 1,
    "changed_context_differs": True,
    "changed_baseline_status": "built",
    "changed_files_signal": "ok",
}


def _scope(**overrides: Any) -> dict[str, Any]:
    """Build a minimal ASGI scope for the session logger."""
    scope: dict[str, Any] = {
        "request_data": {
            "model": "test-model",
            "stream": False,
            "messages": [{"role": "user", "content": "how does the store work"}],
        },
        "session_id": "test-session",
        "session_context_status": "assembled",
        "session_symbols_selected": 3,
        "session_symbols_new": 2,
        "session_symbols_suppressed": 1,
        "session_estimated_tokens": 120,
        "session_context_latency_ms": 5.0,
        "session_context_max_tokens": 4096,
        "session_primary_symbol": "",
        "session_supporting_symbols": [],
    }
    # chat.py pre-initialises the promotion on every request, so a real scope
    # never lacks the keys; the record must not depend on that either.
    for key, value in INERT_PROMOTION.items():
        scope[f"session_{key}"] = value
    scope.update(overrides)
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


# ------------------------------------------------------------------
# The contract itself
# ------------------------------------------------------------------


def test_field_names_describe_change_not_presence() -> None:
    """The old presence-only names must not return under a new spelling."""
    assert set(PROMOTION_FIELDS) == {
        "changed_files_count",
        "changed_symbols_selected",
        "changed_primary_promoted",
        "changed_symbols_promoted",
        "changed_context_differs",
        "changed_baseline_status",
        "changed_files_signal",
    }
    assert "changed_primary_selected" not in PROMOTION_FIELDS
    assert "changed_supporting_symbols_selected" not in PROMOTION_FIELDS
    # The cost of the counterfactual is a log field, never a recorded one.
    assert "changed_baseline_ms" not in PROMOTION_FIELDS
    # The difference is recorded as one boolean, never as the packages behind it.
    assert "changed_baseline_package" not in PROMOTION_FIELDS
    assert PROMOTION_FIELDS.count("changed_context_differs") == 1


# ------------------------------------------------------------------
# Stage result -> scope
# ------------------------------------------------------------------


def test_surface_promotion_copies_every_field() -> None:
    """A stage result lands in the scope under the ``session_`` prefix."""
    scope: dict[str, Any] = {}

    _surface_changed_file_promotion(scope, dict(OBSERVED))

    assert set(scope) == set(PROMOTION_SCOPE_KEYS)
    for field in PROMOTION_FIELDS:
        assert scope[f"session_{field}"] == OBSERVED[field], field


def test_surface_promotion_states_defaults_when_result_omits_them() -> None:
    """An empty stage result still states every field."""
    scope: dict[str, Any] = {}

    _surface_changed_file_promotion(scope, {})

    assert {key: scope[key] for key in PROMOTION_SCOPE_KEYS} == {
        f"session_{field}": value for field, value in INERT_PROMOTION.items()
    }


def test_surface_promotion_coerces_types_to_the_contract() -> None:
    """A truthy leftover int is not promotion, and a null signal is not "ok"."""
    scope: dict[str, Any] = {}

    _surface_changed_file_promotion(
        scope,
        {
            "changed_primary_promoted": 1,
            "changed_symbols_promoted": True,
            "changed_files_signal": None,
            "changed_context_differs": 2,
            "changed_baseline_status": 7,
        },
    )

    assert scope["session_changed_primary_promoted"] is True
    assert scope["session_changed_symbols_promoted"] == INERT_PROMOTION["changed_symbols_promoted"]
    assert scope["session_changed_files_signal"] == "off"
    assert scope["session_changed_context_differs"] is True
    assert scope["session_changed_baseline_status"] == "none"


def test_surface_promotion_of_a_reorder_only_change_reads_as_a_change() -> None:
    """The pair the analyzer needs: differs without either detail field.

    A flat bonus usually only reorders, so the context differs while neither the
    primary nor the membership moved.  Both halves must survive to the scope or
    the record would claim the bonus did nothing.
    """
    scope: dict[str, Any] = {}

    _surface_changed_file_promotion(
        scope,
        {
            "changed_files_count": 1,
            "changed_symbols_selected": 2,
            "changed_primary_promoted": False,
            "changed_symbols_promoted": 0,
            "changed_context_differs": True,
            "changed_baseline_status": "built",
            "changed_files_signal": "ok",
        },
    )

    assert scope["session_changed_context_differs"] is True
    assert scope["session_changed_primary_promoted"] is False
    assert scope["session_changed_symbols_promoted"] == 0
    record = _record(_scope(**scope))["context"]
    assert record["changed_context_differs"] is True
    assert record["changed_baseline_status"] == "built"


def test_surface_promotion_never_records_a_path() -> None:
    """Nothing but the counters crosses over from the stage result."""
    scope: dict[str, Any] = {}
    result = dict(OBSERVED)
    result["changed_paths"] = [FORBIDDEN_STRINGS[1]]
    result["changed_modules"] = [FORBIDDEN_STRINGS[2]]
    result["changed_baseline_ms"] = 0.4

    _surface_changed_file_promotion(scope, result)

    assert set(scope) == set(PROMOTION_SCOPE_KEYS)
    assert not any(forbidden in json.dumps(scope) for forbidden in FORBIDDEN_STRINGS)



# ------------------------------------------------------------------
# Scope -> session record
# ------------------------------------------------------------------


def test_record_always_states_every_promotion_field() -> None:
    """Every written record carries all five fields under ``context``."""
    context = _record(_scope())["context"]

    assert all(field in context for field in PROMOTION_FIELDS)
    assert {field: context[field] for field in PROMOTION_FIELDS} == dict(INERT_PROMOTION)


def test_record_carries_observed_promotion() -> None:
    """A promoted request reads back as promotion, not as an absent feature."""
    overrides = {f"session_{field}": value for field, value in OBSERVED.items()}
    context = _record(_scope(**overrides))["context"]

    for field in PROMOTION_FIELDS:
        assert context[field] == OBSERVED[field], field
    # A promotion cannot exceed what the bonus touched, nor what was sent.
    assert context["changed_symbols_promoted"] <= context["changed_symbols_selected"]
    assert context["changed_symbols_selected"] <= context["symbols_selected"]


def test_clean_tree_and_disabled_signal_stay_distinguishable() -> None:
    """``ok`` with no modified files is not the same record as ``off``."""
    clean = _record(_scope(session_changed_files_signal="ok"))["context"]
    disabled = _record(_scope())["context"]

    assert clean["changed_files_signal"] == "ok"
    assert clean["changed_files_count"] == 0
    assert disabled["changed_files_signal"] == "off"


def test_unavailable_signal_is_recorded_as_itself() -> None:
    """A failed source must not read as a clean tree or as a disabled feature."""
    context = _record(
        _scope(
            session_changed_files_signal="unavailable",
            session_changed_files_count=0,
            session_changed_symbols_selected=0,
            session_changed_symbols_promoted=0,
            session_changed_primary_promoted=False,
        )
    )["context"]

    assert context["changed_files_signal"] == "unavailable"
    assert context["changed_primary_promoted"] is False


def test_record_promotion_is_json_serialisable_and_count_only() -> None:
    """The counters are numbers and a state token, and the line stays valid JSON."""
    record = _record(_scope(session_changed_files_count=4, session_changed_symbols_selected=1))

    decoded = json.loads(json.dumps(record))

    for field in PROMOTION_FIELDS:
        value = decoded["context"][field]
        if field == "changed_files_signal":
            assert value in ("ok", "off", "unavailable"), field
        elif field == "changed_baseline_status":
            assert value in ("none", "built", "skipped_no_bonus", "failed"), field
        else:
            assert isinstance(value, (int, bool)) and not isinstance(value, str), field
    assert "changed_paths" not in decoded["context"]


def test_record_leaks_nothing_about_which_files_changed() -> None:
    """No path, module key, or file-derived name enters the record."""
    overrides = {f"session_{field}": value for field, value in OBSERVED.items()}
    record = _record(_scope(**overrides))

    serialized = json.dumps(record)
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in serialized, forbidden


# ------------------------------------------------------------------
# A stage that assembled nothing
# ------------------------------------------------------------------


def _degraded_scope(signal: str | None) -> dict[str, Any]:
    """Run the real surfacing over a stage result that carries no data.

    That is what the no-index path and the stage's own exception path return, so
    the gateway has no counters to copy - only whatever state the stage managed to
    record for itself.
    """
    scope: dict[str, Any] = {
        "request_data": {
            "model": "test-model",
            "stream": False,
            "messages": [{"role": "user", "content": "how does the store work"}],
        },
        "session_id": "test-session",
    }
    response = SimpleNamespace(
        stage_results={
            "repository_context": PipelineStageResult(
                stage_name="repository_context",
                success=True,
                data=None,
                error="simulated stage failure",
            )
        },
        metadata={} if signal is None else {"changed_files_signal": signal},
    )

    _surface_session_metadata(  # type: ignore[arg-type]
        SimpleNamespace(scope=scope),  # type: ignore[arg-type]
        None,
        response,
    )
    return scope


def test_a_degraded_request_records_the_signal_it_read() -> None:
    """A configured source must not record as ``off`` because nothing was sent."""
    scope = _degraded_scope("ok")
    context = _record(scope)["context"]

    assert context["status"] == "disabled"
    assert context["changed_files_signal"] == "ok"
    # Nothing was assembled, so nothing is attributable - unmeasured, not inert.
    assert context["changed_files_count"] == 0
    assert context["changed_context_differs"] is False
    assert context["changed_baseline_status"] == "none"
    assert "simulated stage failure" not in json.dumps(context)


def test_a_degraded_request_reports_a_failed_read_as_unavailable() -> None:
    """The stage's own fallback state survives to the record unchanged."""
    context = _record(_degraded_scope("unavailable"))["context"]

    assert context["changed_files_signal"] == "unavailable"
    assert context["changed_files_count"] == 0


def test_a_stage_that_never_ran_records_off() -> None:
    """No result at all really is a signal that was never read."""
    scope: dict[str, Any] = {
        "request_data": {"model": "test-model", "messages": [{"role": "user", "content": "x"}]},
    }
    _surface_session_metadata(  # type: ignore[arg-type]
        SimpleNamespace(scope=scope),  # type: ignore[arg-type]
        None,
        SimpleNamespace(stage_results={}, metadata={}),
    )

    assert scope["session_changed_files_signal"] == "off"
    assert scope["session_changed_baseline_status"] == "none"

