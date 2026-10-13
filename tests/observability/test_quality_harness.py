"""Tests for the live gateway quality harness helpers."""

from __future__ import annotations

import io
import json
import sys
import unittest.mock
from pathlib import Path

import pytest

from packages.context.ranking_config import RankingConfig
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.symbols.models import Module, Symbol, SymbolType
from scripts.quality_harness import (
    CHANGED_FILE_AB_PAIRS,
    CHANGED_FILE_PROBES,
    CONTEXT_BUILDER_BUDGET_FACTS,
    CONTEXT_BUILDER_BUDGET_QUERY,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    DELTA_CONTEXT_PROBE,
    HISTORY_CAP_CHANGED_PRIMARY,
    HISTORY_CAP_DIRTY_MODULE,
    HISTORY_CAP_FACTS,
    HISTORY_CAP_PRIMARY,
    HISTORY_CAP_QUERY,
    PROBES,
    QUALITY_SYSTEM_PROMPT,
    REASONING_PREAMBLE_PREFIXES,
    REPOSITORY_INDEX_BUILD_DIRTY_MODULE,
    REPOSITORY_INDEX_BUILD_FACTS,
    REPOSITORY_INDEX_BUILD_QUERY,
    REPOSITORY_INDEX_BUILD_TARGET_MODULE,
    TOOL_CHATTER_MARKERS,
    ChangedFileOutcome,
    ChangedFileProbe,
    ExpectedFact,
    QualityProbe,
    QualityResult,
    _compute_truncation_risk,
    _configured_reasoning_models,
    _read_session_log_records,
    _read_session_log_records_with_retry,
    _record_for_last_user,
    _resolve_probes,
    _stage_arm,
    _warn_default_timeout_for_reasoning_model,
    _warn_low_reasoning_budget,
    build_payload,
    changed_file_flip_weight,
    changed_file_probe_outcome,
    changed_file_sweep,
    changed_file_verdict,
    context_facts_available,
    detect_style_violations,
    extract_answer,
    fact,
    main,
    parse_args,
    print_changed_file_sweep,
    print_changed_file_table,
    print_comparison_table,
    repository_index_settings,
    resolve_changed_file_case,
    run_changed_file_probe,
    run_delta_context_probe,
    run_probe,
    score_answer,
    turn,
)


def test_score_answer_matches_paths_with_backslashes() -> None:
    """Expected POSIX paths should match Windows-style answer paths."""
    answer = r"The file is apps\gateway\session_log.py."

    hits, misses = score_answer(
        answer,
        (
            fact("apps/gateway/session_log.py"),
            fact("_missing"),
        ),
    )

    assert hits == ("apps/gateway/session_log.py",)
    assert misses == ("_missing",)


def test_score_answer_is_case_insensitive() -> None:
    """Expected facts should match regardless of answer casing."""
    answer = "Inspect _EXTRACT_ANSWER_PREVIEW for DELTA.CONTENT chunks."

    hits, misses = score_answer(
        answer,
        (
            fact("_extract_answer_preview"),
            fact("delta.content"),
        ),
    )

    assert hits == ("_extract_answer_preview", "delta.content")
    assert misses == ()


def test_score_answer_accepts_fact_aliases() -> None:
    """Expected facts can define acceptable textual aliases."""
    answer = "The module is apps/gateway/session_log."

    hits, misses = score_answer(
        answer,
        (fact("apps/gateway/session_log.py", "apps/gateway/session_log"),),
    )

    assert hits == ("apps/gateway/session_log.py",)
    assert misses == ()


def test_detect_style_violations_finds_reasoning_preamble() -> None:
    """Answers that start with internal reasoning should be flagged."""
    answer = "I need to inspect the code. The file is apps/gateway/session_log.py."

    assert detect_style_violations(answer) == ("reasoning_preamble",)


def test_detect_style_violations_finds_tool_chatter() -> None:
    """Tool/thinking markers should be flagged anywhere in the answer."""
    answer = "The answer is below.\n<thinking>I should inspect files.</thinking>"

    assert detect_style_violations(answer) == ("tool_chatter",)


def test_detect_style_violations_ignores_clean_fact_answer() -> None:
    """A concise repository-fact answer should not be penalized."""
    answer = "apps/gateway/session_log.py, _extract_answer_preview"

    assert detect_style_violations(answer) == ()


def test_quality_system_prompt_covers_reasoning_preamble_prefixes() -> None:
    """The live quality prompt should tell the model not to emit known preambles."""
    prompt = QUALITY_SYSTEM_PROMPT.lower()

    for prefix in REASONING_PREAMBLE_PREFIXES:
        assert prefix in prompt


def test_quality_system_prompt_covers_tool_chatter_markers() -> None:
    """The live quality prompt should tell the model not to emit tool chatter."""
    prompt = QUALITY_SYSTEM_PROMPT.lower()

    for marker in TOOL_CHATTER_MARKERS:
        marker_name = marker.removeprefix("<").removeprefix("/").removesuffix(">")
        assert marker_name in prompt


def test_tool_call_markers_tracked() -> None:
    """Literal tool_call wrappers should be tracked style markers."""
    lt, gt = chr(60), chr(62)

    assert lt + "tool_call" + gt in TOOL_CHATTER_MARKERS
    assert lt + "/tool_call" + gt in TOOL_CHATTER_MARKERS


def test_detect_style_violations_flags_tool_call_chatter() -> None:
    """An answer containing a tool_call wrapper should be flagged as chatter."""
    lt, gt = chr(60), chr(62)
    answer = (
        "Result: " + lt + "tool_call" + gt + " inspect_files " + lt + "/tool_call" + gt
    )

    assert detect_style_violations(answer) == ("tool_chatter",)


def test_quality_system_prompt_forbids_tool_call_wrappers() -> None:
    """The prompt should forbid tool_call wrappers and fake tool calls."""
    prompt = QUALITY_SYSTEM_PROMPT.lower()

    assert "tool_call" in prompt
    assert "fake tool call" in prompt


def test_build_payload_uses_quality_system_prompt() -> None:
    """Gateway payloads should carry the strengthened quality system prompt."""
    probe = QualityProbe("p1", "SEARCH", "Find the thing", (fact("thing"),))

    payload = build_payload(
        probe,
        model="test-model",
        max_tokens=50,
        use_intent_overrides=True,
        context_enabled=True,
    )

    assert payload["messages"][0] == {"role": "system", "content": QUALITY_SYSTEM_PROMPT}


def test_extract_answer_reads_openai_shape() -> None:
    """OpenAI-shaped responses provide answer text and token usage."""
    payload = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        },
    }

    answer, usage = extract_answer(payload)

    assert answer == "ok"
    assert usage == {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
    }


def test_build_payload_can_include_intent_override() -> None:
    """Harness can force one context intent per probe."""
    probe = QualityProbe("p1", "SEARCH", "Find the thing", (fact("thing"),))

    payload = build_payload(
        probe,
        model="test-model",
        max_tokens=50,
        use_intent_overrides=True,
        context_enabled=True,
    )

    assert payload["model"] == "test-model"
    assert payload["max_tokens"] == 50
    assert payload["context_intent"] == "SEARCH"
    assert payload["repository_context_enabled"] is True
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "Find the thing"


def test_build_payload_can_omit_intent_override() -> None:
    """Harness can exercise detector behavior directly."""
    probe = QualityProbe("p1", "SEARCH", "Find the thing", (fact("thing"),))

    payload = build_payload(
        probe,
        model="test-model",
        max_tokens=50,
        use_intent_overrides=False,
        context_enabled=False,
    )

    assert "context_intent" not in payload
    assert payload["repository_context_enabled"] is False


def test_probe_set_covers_live_intents() -> None:
    """The default probe set covers every non-default live intent."""
    intents = {probe.intent for probe in PROBES}

    assert intents == {"SEARCH", "DEBUG", "TEST", "EXPLAIN", "REFACTOR", "IMPLEMENT"}


def test_probe_set_fixed_maximum_is_documented() -> None:
    """The quality baseline denominator should change only intentionally.

    20 while the fixed set was 8 probes; 23 since
    ``explain_changed_files_contextbuilder`` joined it as the scored half of the
    change-aware ranking decision; 26 since ``explain_changed_files_repository_index``
    joined it as the scored half of the case where the bonus costs context rather
    than merely reordering it; 30 since ``explain_changed_files_history_cap`` joined it
    as the scored half of the case on the other side of that ledger, where the changed
    file is the file the prompt asks about and the bonus buys the mechanism the answer
    needs.  The ``20/20`` figures in ``docs/`` are historical
    runs against the earlier set, not a ceiling.
    """
    total_maximum = sum(len(probe.expect) for probe in PROBES)

    assert total_maximum == 30


def test_debug_streaming_preview_probe_keeps_choice_content_fact() -> None:
    """The DEBUG probe must still require the lowest-level choice helper."""
    probe = next(item for item in PROBES if item.id == "debug_streaming_preview")

    assert "answer_preview" in probe.prompt
    assert "lowest-level helper" in probe.prompt
    assert tuple(expected.label for expected in probe.expect) == (
        "_choice_content",
        "delta.content",
        "apps/gateway/session_log.py",
    )

    choice_fact = next(
        expected for expected in probe.expect if expected.label == "_choice_content"
    )
    assert choice_fact.variants == ("_choice_content",)


class TestMultiTurnProbes:
    """Multi-turn Cline-like probes exercise conversation history handling."""

    def test_at_least_two_multiturn_probes_are_defined(self) -> None:
        multiturn = [probe for probe in PROBES if probe.history]

        assert len(multiturn) >= 2

    def test_multiturn_probes_have_at_least_two_history_turns(self) -> None:
        multiturn = [probe for probe in PROBES if probe.history]

        for probe in multiturn:
            assert len(probe.history) >= 2
            assert probe.history[0]["role"] == "user"

    def test_single_turn_probes_have_empty_history(self) -> None:
        single_turn = [probe for probe in PROBES if not probe.id.startswith("multiturn_")]

        assert single_turn
        for probe in single_turn:
            assert probe.history == ()

    def test_expected_fact_variants_do_not_collide_across_facts(self) -> None:
        """A variant of one expected fact must not be a substring of another.

        score_answer matches by substring, so overlapping variants (e.g.
        "DEFAULT_MODEL" inside "APP_DEFAULT_MODEL") would let a probe pass
        without the model actually producing the more specific fact.
        """
        for probe in PROBES:
            variants_by_label = {
                expected.label: [variant.lower() for variant in expected.variants]
                for expected in probe.expect
            }
            labels = list(variants_by_label)
            for i, label_a in enumerate(labels):
                for label_b in labels[i + 1 :]:
                    for variant_a in variants_by_label[label_a]:
                        for variant_b in variants_by_label[label_b]:
                            assert variant_a not in variant_b, (
                                f"{probe.id}: {label_a!r} variant {variant_a!r} "
                                f"is a substring of {label_b!r} variant {variant_b!r}"
                            )
                            assert variant_b not in variant_a, (
                                f"{probe.id}: {label_b!r} variant {variant_b!r} "
                                f"is a substring of {label_a!r} variant {variant_a!r}"
                            )


def test_build_payload_includes_history_before_final_prompt() -> None:
    """Multi-turn probes should send history turns, then the final prompt."""
    probe = QualityProbe(
        id="p1",
        intent="EXPLAIN",
        prompt="final question",
        expect=(fact("thing"),),
        history=(turn("user", "turn one"), turn("assistant", "reply one")),
    )

    payload = build_payload(
        probe,
        model="test-model",
        max_tokens=50,
        use_intent_overrides=False,
        context_enabled=True,
    )

    roles = [message["role"] for message in payload["messages"]]
    contents = [message["content"] for message in payload["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert contents[1:3] == ["turn one", "reply one"]
    assert contents[-1] == "final question"


def test_build_payload_without_history_matches_single_turn_shape() -> None:
    """Single-turn probes keep the original two-message payload shape."""
    probe = QualityProbe("p1", "SEARCH", "Find the thing", (fact("thing"),))

    payload = build_payload(
        probe,
        model="test-model",
        max_tokens=50,
        use_intent_overrides=False,
        context_enabled=True,
    )

    assert len(payload["messages"]) == 2


class TestDeltaContextProbe:
    """Delta-context probes use two live requests plus session-log metadata."""

    def test_delta_probe_has_distinct_primer_and_followup(self) -> None:
        assert DELTA_CONTEXT_PROBE.first.id.endswith("primer")
        assert DELTA_CONTEXT_PROBE.followup.id.endswith("followup")
        assert DELTA_CONTEXT_PROBE.first.prompt != DELTA_CONTEXT_PROBE.followup.prompt

    def test_delta_probe_targets_history_cap_area(self) -> None:
        """The live delta smoke should target a dense multi-symbol code area."""
        assert "history" in DELTA_CONTEXT_PROBE.first.prompt.lower()
        assert "cap" in DELTA_CONTEXT_PROBE.first.prompt.lower()
        assert DELTA_CONTEXT_PROBE.first.expect[0].label == "cap_history"
        assert DELTA_CONTEXT_PROBE.first.expect[1].label == "packages/pipeline/history.py"

    def test_delta_followup_requests_multiple_helpers(self) -> None:
        """The follow-up should ask for multiple helper symbols to suppress."""
        expected_labels = {expected.label for expected in DELTA_CONTEXT_PROBE.followup.expect}

        assert expected_labels == {
            "_message_token_count",
            "_estimate_tokens",
            "_build_cap_groups",
        }

    def test_read_session_log_records_from_offset(self, tmp_path) -> None:
        log_path = tmp_path / "sessions.jsonl"
        old_line = (
            '{"last_user_message":"old","context":{"symbols_suppressed":0}}\n'
        )
        new_line = (
            '{"last_user_message":"new","context":{"symbols_suppressed":2}}\n'
        )
        log_path.write_text(old_line, encoding="utf-8")
        offset = log_path.stat().st_size
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(new_line)

        records = _read_session_log_records(str(log_path), offset=offset)

        assert len(records) == 1
        assert records[0]["last_user_message"] == "new"
        assert records[0]["context"]["symbols_suppressed"] == 2

    def test_read_session_log_records_skips_malformed_lines(self, tmp_path) -> None:
        log_path = tmp_path / "sessions.jsonl"
        log_path.write_text(
            "not json\n"
            '{"last_user_message":"ok","context":{"symbols_suppressed":1}}\n',
            encoding="utf-8",
        )

        records = _read_session_log_records(str(log_path), offset=0)

        assert len(records) == 1
        assert records[0]["last_user_message"] == "ok"

    def test_record_for_last_user_returns_newest_match(self) -> None:
        records = [
            {"last_user_message": "target", "context": {"symbols_suppressed": 1}},
            {"last_user_message": "other", "context": {"symbols_suppressed": 0}},
            {"last_user_message": "target", "context": {"symbols_suppressed": 3}},
        ]

        record = _record_for_last_user(records, "target")

        assert record["context"]["symbols_suppressed"] == 3


class TestReadSessionLogRecordsWithRetry:
    """Tests for the retry wrapper around _read_session_log_records."""

    def test_returns_records_immediately_when_present(self, tmp_path) -> None:
        """When records are already on disk, return them without waiting."""
        log_path = tmp_path / "sessions.jsonl"
        log_path.write_text(
            '{"last_user_message":"a","context":{}}\n'
            '{"last_user_message":"b","context":{}}\n',
            encoding="utf-8",
        )
        offset = 0

        records = _read_session_log_records_with_retry(
            str(log_path), offset=offset, expected_min=2
        )

        assert len(records) == 2
        assert records[0]["last_user_message"] == "a"
        assert records[1]["last_user_message"] == "b"

    def test_returns_partial_records_when_some_missing(self, tmp_path) -> None:
        """When only one record exists, return it rather than failing."""
        log_path = tmp_path / "sessions.jsonl"
        log_path.write_text(
            '{"last_user_message":"only_one","context":{}}\n',
            encoding="utf-8",
        )

        records = _read_session_log_records_with_retry(
            str(log_path), offset=0, expected_min=2, max_wait_seconds=0.15
        )

        assert len(records) == 1
        assert records[0]["last_user_message"] == "only_one"

    def test_returns_empty_when_file_missing(self, tmp_path) -> None:
        """A non-existent log file returns zero records quickly."""
        records = _read_session_log_records_with_retry(
            str(tmp_path / "nope.jsonl"),
            offset=0,
            expected_min=1,
            max_wait_seconds=0.1,
        )

        assert records == []

    def test_retries_and_succeeds_when_records_appear_later(self, tmp_path) -> None:
        """Records written mid-retry should be picked up."""
        log_path = tmp_path / "sessions.jsonl"
        log_path.write_text(
            '{"last_user_message":"early","context":{}}\n',
            encoding="utf-8",
        )

        def _write_later() -> None:
            import time

            time.sleep(0.15)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write('{"last_user_message":"later","context":{}}\n')

        import threading

        t = threading.Thread(target=_write_later)
        t.start()

        records = _read_session_log_records_with_retry(
            str(log_path), offset=0, expected_min=2, max_wait_seconds=2.0
        )
        t.join(timeout=5)

        assert len(records) == 2
        assert records[1]["last_user_message"] == "later"


def test_delta_context_probe_reports_record_count_on_failure(tmp_path) -> None:
    """When session-log records are missing, the error includes the count."""
    log_path = tmp_path / "sessions.jsonl"
    # File exists but has no records matching our probe prompts.
    log_path.write_text(
        '{"last_user_message":"some unrelated prompt","context":{}}\n',
        encoding="utf-8",
    )

    # Patch post_json so both probe requests succeed and the real
    # session-log path is exercised.
    _fake_response = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    with unittest.mock.patch(
        "scripts.quality_harness.post_json", return_value=_fake_response
    ):
        result = run_delta_context_probe(
            DELTA_CONTEXT_PROBE,
            base_url="http://127.0.0.1:9999",
            model="test-model",
            max_tokens=50,
            timeout=1.0,
            use_intent_overrides=True,
            session_log_path=str(log_path),
        )

    assert result.error is not None
    assert "session_log_records_not_found" in result.error
    # The file has 1 record that doesn't match either probe prompt,
    # so found should be 1 (or 0 if the record is filtered by last_user_message).
    assert "record(s)" in result.error


def test_print_comparison_table_shows_context_delta(capsys) -> None:
    """Comparison output should show context-vs-raw score deltas."""
    context_results = [
        QualityResult(
            id="p1",
            intent="SEARCH",
            prompt_tokens=100,
            seconds=1.0,
            hits=("a", "b"),
            misses=(),
        )
    ]
    no_context_results = [
        QualityResult(
            id="p1",
            intent="SEARCH",
            prompt_tokens=20,
            seconds=0.5,
            hits=("a",),
            misses=("b",),
        )
    ]

    print_comparison_table(context_results, no_context_results)

    output = capsys.readouterr().out
    assert "dscore" in output
    assert "TOTAL" in output
    assert "   1" in output
    # Clean comparisons must not gain error/invalid noise.
    assert "ERRORS:" not in output
    assert "delta invalid" not in output
    assert "ERR" not in output


def test_print_comparison_table_marks_arm_errors_and_prints_footer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Errored arms must render as ERR with an ERRORS footer, not as 0/0."""
    context_results = [
        QualityResult(
            id="implement_health_flag",
            intent="IMPLEMENT",
            ok=True,
            prompt_tokens=4000,
            seconds=10.0,
            hits=("a", "b"),
            misses=(),
        )
    ]
    no_context_results = [
        QualityResult(
            id="implement_health_flag",
            intent="IMPLEMENT",
            seconds=120.0,
            error=(
                "TimeoutError: timed out after 120.0s "
                "(harness client timeout; gateway/backend may still be generating)"
            ),
        )
    ]

    print_comparison_table(context_results, no_context_results)

    output = capsys.readouterr().out
    assert "ERR" in output
    assert "0/0" not in output
    assert "delta invalid" in output
    assert "ERRORS:" in output
    assert (
        "no_context:implement_health_flag -> TimeoutError: timed out after 120.0s"
        in output
    )


def test_run_probe_timeout_records_descriptive_error_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harness client timeout must be tagged, not look like a plain miss."""

    def failing_post_json(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("scripts.quality_harness.post_json", failing_post_json)
    probe = QualityProbe("p1", "IMPLEMENT", "prompt", (fact("x"),))
    result = run_probe(
        probe,
        base_url="http://nowhere",
        model="test-model",
        max_tokens=400,
        timeout=300.0,
        use_intent_overrides=True,
        context_enabled=False,
    )

    assert result.ok is False
    assert result.error == (
        "TimeoutError: timed out after 300.0s "
        "(harness client timeout; gateway/backend may still be generating)"
    )
    assert result.metadata["timed_out"] is True
    assert result.metadata["timeout_seconds"] == 300.0
    assert result.hits == ()
    assert result.misses == ()


def test_run_probe_non_timeout_error_keeps_plain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-timeout errors keep the legacy '<ExcType>: <msg>' shape and no tags."""

    def failing_post_json(*_args, **_kwargs):
        raise ValueError("gateway returned non-object JSON")

    monkeypatch.setattr("scripts.quality_harness.post_json", failing_post_json)
    probe = QualityProbe("p1", "SEARCH", "prompt", (fact("x"),))
    result = run_probe(
        probe,
        base_url="http://nowhere",
        model="test-model",
        max_tokens=400,
        timeout=1.0,
        use_intent_overrides=True,
        context_enabled=True,
    )

    assert result.ok is False
    assert result.error == "ValueError: gateway returned non-object JSON"
    assert "timed_out" not in result.metadata
    assert "timeout_seconds" not in result.metadata


def test_warn_default_timeout_for_reasoning_model_prints_hint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reasoning models on the default timeout get a stderr hint."""
    _warn_default_timeout_for_reasoning_model(
        "qwen38-27b",
        DEFAULT_TIMEOUT,
        reasoning_models=("qwen38-27b",),
    )

    err = capsys.readouterr().err
    assert "--timeout 300" in err
    assert "REQUEST_TIMEOUT=300" in err
    assert "restart the gateway" in err.lower()


def test_warn_default_timeout_for_reasoning_model_silent_when_overridden(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-default --timeout suppresses the hint."""
    _warn_default_timeout_for_reasoning_model(
        "qwen38-27b",
        300.0,
        reasoning_models=("qwen38-27b",),
    )

    assert capsys.readouterr().err == ""


def test_warn_default_timeout_for_reasoning_model_silent_for_other_models(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-reasoning models never get the hint."""
    _warn_default_timeout_for_reasoning_model(
        "other-model",
        120.0,
        reasoning_models=("qwen38-27b",),
    )

    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Probe selection (--probe) and --repeat tests
# ---------------------------------------------------------------------------


class TestProbeSelection:
    """_resolve_probes filters PROBES without mutating the global tuple."""

    def test_resolve_probes_none_returns_all(self) -> None:
        assert _resolve_probes(None) is PROBES

    def test_resolve_probes_empty_returns_all(self) -> None:
        assert _resolve_probes([]) is PROBES

    def test_resolve_probes_single_id(self) -> None:
        result = _resolve_probes(["multiturn_history_cap_budget"])
        assert len(result) == 1
        assert result[0].id == "multiturn_history_cap_budget"

    def test_resolve_probes_multiple_ids(self) -> None:
        result = _resolve_probes(["search_answer_preview", "multiturn_history_cap_budget"])
        assert len(result) == 2
        ids = [p.id for p in result]
        assert "search_answer_preview" in ids
        assert "multiturn_history_cap_budget" in ids

    def test_resolve_probes_unknown_id_raises(self, capsys) -> None:
        with pytest.raises(ValueError, match="unknown probe id"):
            _resolve_probes(["nonexistent_probe"])

    def test_resolve_probes_preserves_first_request_order(self) -> None:
        """Selection order follows the --probe argument order, not PROBES order."""
        result = _resolve_probes(["multiturn_config_systems", "search_answer_preview"])
        assert result[0].id == "multiturn_config_systems"
        assert result[1].id == "search_answer_preview"

    def test_resolve_probes_deduplicates(self) -> None:
        """Duplicate --probe ids should not run duplicate probes."""
        result = _resolve_probes(["search_answer_preview", "search_answer_preview"])
        assert len(result) == 1
        assert result[0].id == "search_answer_preview"


class TestExistingBehaviorUnchanged:
    """Prove that new flags do not change existing default behavior."""

    def test_probe_set_covers_live_intents_unchanged(self) -> None:
        """PROBES tuple must still cover all 6 live intents."""
        intents = {probe.intent for probe in PROBES}
        assert intents == {"SEARCH", "DEBUG", "TEST", "EXPLAIN", "REFACTOR", "IMPLEMENT"}

    def test_probe_set_fixed_maximum_unchanged(self) -> None:
        """Total expected-fact count must stay pinned.

        Pinned so a new probe is always a deliberate edit: registering
        ``explain_changed_files_contextbuilder`` took this from 20 to 23,
        ``explain_changed_files_repository_index`` took it to 26, and
        ``explain_changed_files_history_cap`` - the first pair registered on the side
        where the bonus *adds* context - takes it to 30.
        """
        total_maximum = sum(len(probe.expect) for probe in PROBES)
        assert total_maximum == 30

    def test_probe_tuple_length_unchanged(self) -> None:
        """PROBES must stay pinned; the changed-file A/B pairs made it 11."""
        assert len(PROBES) == 11


class TestParseArgsProbe:
    """parse_args handles --probe and --repeat correctly."""

    def test_probe_single(self) -> None:
        args = parse_args(["--probe", "multiturn_history_cap_budget"])
        assert args.probe == ["multiturn_history_cap_budget"]

    def test_probe_multiple(self) -> None:
        args = parse_args(["--probe", "a", "--probe", "b"])
        assert args.probe == ["a", "b"]

    def test_repeat_default_is_one(self) -> None:
        args = parse_args([])
        assert args.repeat == 1

    def test_repeat_value(self) -> None:
        args = parse_args(["--repeat", "5"])
        assert args.repeat == 5


class TestInvalidFlagCombinations:
    """Invalid flag combinations should return exit code 2."""

    def test_probe_with_delta_context_returns_2(self, capsys) -> None:
        rc = main(["--probe", "search_answer_preview", "--delta-context"])
        assert rc == 2
        _, err = capsys.readouterr()
        assert "--probe cannot be combined with --delta-context" in err

    def test_repeat_zero_returns_2(self, capsys) -> None:
        rc = main(["--repeat", "0"])
        assert rc == 2
        _, err = capsys.readouterr()
        assert "--repeat must be >= 1" in err

    def test_repeat_gt1_with_delta_context_returns_2(self, capsys) -> None:
        rc = main(["--repeat", "3", "--delta-context"])
        assert rc == 2
        _, err = capsys.readouterr()
        assert "--repeat cannot be combined with --delta-context" in err

    def test_repeat_gt1_with_compare_context_returns_2(self, capsys) -> None:
        rc = main(["--repeat", "3", "--compare-context"])
        assert rc == 2
        _, err = capsys.readouterr()
        assert "--repeat cannot be combined with --compare-context" in err

    def test_unknown_probe_id_returns_2(self, capsys) -> None:
        rc = main(["--probe", "nonexistent_probe"])
        assert rc == 2
        _, err = capsys.readouterr()
        assert "unknown probe id" in err


class TestRepeatJsonShape:
    """Verify repeat mode JSON envelope is backward-compatible."""

    _FAKE_RESPONSE = {
        "choices": [{"message": {"role": "assistant", "content": "_apply_history_cap"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }

    def test_repeat_one_produces_flat_array(self, monkeypatch) -> None:
        """--repeat 1 must produce the same flat array as no --repeat."""
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)

        main([
            "--probe", "multiturn_history_cap_budget",
            "--repeat", "1",
            "--json",
            "--base-url", "http://nowhere",
        ])
        output = json.loads(captured.getvalue())

        assert isinstance(output, list)
        assert len(output) == 1

    def test_repeat_three_produces_envelope(self, monkeypatch) -> None:
        """--repeat 3 must produce the new envelope shape."""
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)

        main([
            "--probe", "multiturn_history_cap_budget",
            "--repeat", "3",
            "--json",
            "--base-url", "http://nowhere",
        ])
        output = json.loads(captured.getvalue())

        assert isinstance(output, dict)
        assert output["repeat"] == 3
        assert len(output["runs"]) == 3
        assert "aggregate" in output

    def test_probe_with_compare_context_filters_both_sides(self, monkeypatch) -> None:
        """--probe with --compare-context should filter both context and no_context results."""
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)

        main([
            "--probe", "multiturn_history_cap_budget",
            "--compare-context",
            "--json",
            "--base-url", "http://nowhere",
        ])
        output = json.loads(captured.getvalue())

        assert isinstance(output, dict)
        assert "context" in output
        assert "no_context" in output
        assert len(output["context"]) == 1
        assert len(output["no_context"]) == 1
        assert output["context"][0]["id"] == "multiturn_history_cap_budget"


# ---------------------------------------------------------------------------
# Truncation-risk and reasoning-model budget warning tests
# ---------------------------------------------------------------------------


class TestDefaultMaxTokens:
    """DEFAULT_MAX_TOKENS must remain 400."""

    def test_default_max_tokens_is_400(self) -> None:
        assert DEFAULT_MAX_TOKENS == 400


class TestReasoningModelLowBudgetWarning:
    """Reasoning-model warnings are configuration-driven, not model-name hardcoded."""

    def test_configured_reasoning_model_below_min_emits_warning(self, capsys) -> None:
        _warn_low_reasoning_budget(
            "local-reasoner",
            900,
            reasoning_models=("local-reasoner",),
            min_tokens=2048,
        )
        _, err = capsys.readouterr()
        assert "local-reasoner" in err.lower()
        assert "max_tokens=900" in err
        assert "2048" in err

    def test_configured_reasoning_model_at_min_no_warning(self, capsys) -> None:
        _warn_low_reasoning_budget(
            "local-reasoner",
            2048,
            reasoning_models=("local-reasoner",),
            min_tokens=2048,
        )
        _, err = capsys.readouterr()
        assert err.strip() == ""

    def test_configured_reasoning_model_above_min_no_warning(self, capsys) -> None:
        _warn_low_reasoning_budget(
            "local-reasoner",
            4096,
            reasoning_models=("local-reasoner",),
            min_tokens=2048,
        )
        _, err = capsys.readouterr()
        assert err.strip() == ""

    def test_unconfigured_model_below_min_no_warning(self, capsys) -> None:
        _warn_low_reasoning_budget(
            "ordinary-model",
            900,
            reasoning_models=("local-reasoner",),
            min_tokens=2048,
        )
        _, err = capsys.readouterr()
        assert err.strip() == ""

    def test_case_insensitive_reasoning_model_match(self, capsys) -> None:
        _warn_low_reasoning_budget(
            "Local-Reasoner",
            500,
            reasoning_models=("local-reasoner",),
            min_tokens=2048,
        )
        _, err = capsys.readouterr()
        assert "2048" in err

    def test_reasoning_models_can_come_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_QUALITY_REASONING_MODELS", "alpha, beta, alpha")
        assert _configured_reasoning_models(["gamma"]) == ("alpha", "beta", "gamma")


class TestComputeTruncationRisk:
    """_compute_truncation_risk flags budget exhaustion with empty/short answers."""

    def test_empty_answer_at_budget_is_risk(self) -> None:
        assert _compute_truncation_risk("", 400, 400) is True

    def test_short_answer_near_budget_is_risk(self) -> None:
        assert _compute_truncation_risk("short", 399, 400) is True

    def test_empty_answer_below_budget_is_not_risk(self) -> None:
        assert _compute_truncation_risk("", 100, 400) is False

    def test_normal_answer_at_budget_is_not_risk(self) -> None:
        assert _compute_truncation_risk("This is a sufficiently long answer.", 400, 400) is False

    def test_short_answer_well_below_budget_is_not_risk(self) -> None:
        assert _compute_truncation_risk("short", 100, 400) is False

    def test_answer_exactly_19_chars_at_budget_is_risk(self) -> None:
        assert _compute_truncation_risk("1234567890123456789", 400, 400) is True

    def test_answer_exactly_20_chars_at_budget_is_not_risk(self) -> None:
        assert _compute_truncation_risk("12345678901234567890", 400, 400) is False


class TestRunProbeTruncationMetadata:
    """run_probe stores max_tokens_requested and truncation_risk in metadata."""

    _FAKE_RESPONSE = {
        "choices": [{"message": {"role": "assistant", "content": ""}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 400, "total_tokens": 410},
    }

    def test_run_probe_stores_max_tokens_requested(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        probe = QualityProbe("p1", "SEARCH", "prompt", (fact("x"),))
        result = run_probe(
            probe,
            base_url="http://nowhere",
            model="test-model",
            max_tokens=400,
            timeout=1.0,
            use_intent_overrides=True,
            context_enabled=True,
        )
        assert result.metadata["max_tokens_requested"] == 400

    def test_empty_answer_at_budget_marks_truncation_risk(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        probe = QualityProbe("p1", "SEARCH", "prompt", (fact("x"),))
        result = run_probe(
            probe,
            base_url="http://nowhere",
            model="test-model",
            max_tokens=400,
            timeout=1.0,
            use_intent_overrides=True,
            context_enabled=True,
        )
        assert result.metadata["truncation_risk"] is True

    def test_normal_answer_below_budget_no_truncation_risk(self, monkeypatch) -> None:
        response = {
            "choices": [
                {"message": {"role": "assistant", "content": "This is a sufficiently long answer."}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
        }
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: response,
        )
        probe = QualityProbe("p1", "SEARCH", "prompt", (fact("x"),))
        result = run_probe(
            probe,
            base_url="http://nowhere",
            model="test-model",
            max_tokens=400,
            timeout=1.0,
            use_intent_overrides=True,
            context_enabled=True,
        )
        assert result.metadata["truncation_risk"] is False


class TestJsonShapeCompatibility:
    """JSON output must not have new top-level fields beyond metadata."""

    _FAKE_RESPONSE = {
        "choices": [{"message": {"role": "assistant", "content": "answer"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    def test_json_output_metadata_contains_truncation_fields(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            lambda *a, **kw: self._FAKE_RESPONSE,
        )
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)

        main([
            "--probe", "search_answer_preview",
            "--json",
            "--base-url", "http://nowhere",
        ])
        output = json.loads(captured.getvalue())

        assert isinstance(output, list)
        assert len(output) == 1
        result = output[0]
        # metadata is the existing field; new keys are inside it
        assert "metadata" in result
        assert "max_tokens_requested" in result["metadata"]
        assert "truncation_risk" in result["metadata"]
        # No new top-level keys beyond the existing set
        expected_keys = {
            "id", "intent", "ok", "answer", "prompt_tokens",
            "completion_tokens", "total_tokens", "seconds",
            "hits", "misses", "style_violations", "error", "metadata",
        }
        assert set(result.keys()) == expected_keys

    def test_json_output_metadata_contains_timeout_fields(self, monkeypatch) -> None:
        """Timeouts add metadata keys only; top-level result keys stay fixed."""

        def failing_post_json(*_args, **_kwargs):
            raise TimeoutError("timed out")

        monkeypatch.setattr(
            "scripts.quality_harness.post_json",
            failing_post_json,
        )
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)

        main([
            "--probe", "search_answer_preview",
            "--json",
            "--base-url", "http://nowhere",
            "--timeout", "55.5",
        ])
        output = json.loads(captured.getvalue())

        assert isinstance(output, list)
        assert len(output) == 1
        result = output[0]
        expected_keys = {
            "id", "intent", "ok", "answer", "prompt_tokens",
            "completion_tokens", "total_tokens", "seconds",
            "hits", "misses", "style_violations", "error", "metadata",
        }
        assert set(result.keys()) == expected_keys
        assert result["error"].startswith("TimeoutError: timed out after 55.5s")
        assert result["metadata"]["timed_out"] is True
        assert result["metadata"]["timeout_seconds"] == 55.5


# ---------------------------------------------------------------------------
# Changed-file ranking probes (offline: no gateway, no model)
#
# Each probe runs the real ``RepositoryContextStage`` over a fixture index with a
# changed-module source injected, exactly as
# ``tests/pipeline/test_changed_file_promotion_counts.py`` does, and reads the
# stage's own counterfactual counters back out of the result.  The dirty module is
# a fixture value, never a Git query, so these tests pass identically on a clean
# checkout and never depend on what the working tree happens to hold.
#
# Fixture scores for ``PROBE_QUERY``, read from the implementation:
#
#     165  packages/context/builder.ContextBuilder   named in the query
#     155  packages/context/budget.ContextBudget     name match on "budget"
#     125  packages/context/composer.ContextComposer name match on "context"
#     125  packages/context/session.ContextSession   name match on "context"
#
# so the dirty file is ten points behind the leader it competes with, and two
# symbols are exactly tied below it - one for the primary case, one for the
# reorder-only case a set difference cannot see.
# ---------------------------------------------------------------------------

PROBE_QUERY = "How does ContextBuilder enforce the token budget?"
PROBE_NAMED_SYMBOL = "packages/context/builder.ContextBuilder"
PROBE_NAMED_MODULE = "packages/context/builder"
PROBE_DIRTY_SYMBOL = "packages/context/budget.ContextBudget"
PROBE_DIRTY_MODULE = "packages/context/budget"
PROBE_TIED_SYMBOL = "packages/context/composer.ContextComposer"
PROBE_TIED_MODULE = "packages/context/composer"
PROBE_LATE_SYMBOL = "packages/context/session.ContextSession"
PROBE_LATE_MODULE = "packages/context/session"

#: Pins the budget instead of reading a developer's ``.env``; the probe CLI uses
#: the gateway's own settings so it measures the budget a request would get.
PROBE_STAGE_KWARGS: dict[str, object] = {
    "context_delta_injection": False,
    "max_context_tokens": 4096,
}


def _probe(
    *,
    probe_id: str = "fixture",
    query: str = PROBE_QUERY,
    dirty_module: str = PROBE_DIRTY_MODULE,
    expected_primary: str = PROBE_NAMED_SYMBOL,
    expected_changed_primary: str = PROBE_NAMED_SYMBOL,
    names_primary: bool = True,
    facts: tuple[ExpectedFact, ...] = (),
    note: str = "",
) -> ChangedFileProbe:
    """One changed-file probe with every field filled in."""
    return ChangedFileProbe(
        id=probe_id,
        query=query,
        dirty_module=dirty_module,
        expected_primary=expected_primary,
        expected_changed_primary=expected_changed_primary,
        names_primary=names_primary,
        facts=facts,
        note=note,
    )


def _probe_index() -> RepositoryIndex:
    """Four symbols: named, competitor in a dirty file, and an exactly tied pair."""
    specs = (
        (PROBE_NAMED_SYMBOL, PROBE_NAMED_MODULE, SymbolType.CLASS, 12),
        (PROBE_DIRTY_SYMBOL, PROBE_DIRTY_MODULE, SymbolType.CLASS, 8),
        (PROBE_TIED_SYMBOL, PROBE_TIED_MODULE, SymbolType.CLASS, 4),
        (PROBE_LATE_SYMBOL, PROBE_LATE_MODULE, SymbolType.CLASS, 6),
    )
    symbols = [
        Symbol(
            id=qname,
            name=qname.rsplit(".", 1)[-1],
            qualified_name=qname,
            symbol_type=symbol_type,
            module=module,
            lineno=lineno,
        )
        for qname, module, symbol_type, lineno in specs
    ]
    modules: dict[str, Module] = {}
    for symbol in symbols:
        modules.setdefault(symbol.module, Module(path=symbol.module, symbols=[])).symbols.append(
            symbol
        )
    return RepositoryIndex(
        modules=modules,
        _symbols=symbols,
        _relationships=[],
        _statistics=RepositoryStatistics(
            module_count=len(modules),
            class_count=len(symbols),
            function_count=0,
            method_count=0,
            symbol_count=len(symbols),
        ),
    )


def _fixture_flip_weight() -> int:
    """The smallest bonus that hands the fixture's primary to the dirty file."""
    rows = changed_file_sweep(_probe_index(), [PROBE_QUERY])
    assert rows, "the fixture index must rank something"
    return rows[0].flip_weight


def test_probe_fixture_sends_every_symbol_with_the_named_one_first() -> None:
    """Guard the fixture: all four symbols are sent, the named one leads."""
    outcome = run_changed_file_probe(
        _probe(), _probe_index(), weight=1, stage_kwargs=PROBE_STAGE_KWARGS
    )

    assert outcome.baseline_symbols == 4
    assert outcome.baseline_primary == PROBE_NAMED_SYMBOL
    assert outcome.max_context_tokens == 4096


def test_context_facts_available_scores_the_serialized_context_of_one_arm() -> None:
    """The metric reads the text a request would have carried, and only that.

    A package that names a symbol puts that symbol's qualified name into the
    serialized context, so a fact about it is available there, and a module path
    fact is available when the package carries the module.  A fact whose text
    appears nowhere in the package is unavailable whether or not the repository
    contains it.  This is the whole reason ``facts_lost`` can report a loss the
    symbol counters cannot see: each arm is scored on its own text, with the same
    matcher the live scored probe uses.
    """
    from packages.context.context_package import ContextPackage

    facts = (
        fact("ContextBuilder"),
        fact("ContextSession"),
        fact("packages/context/builder.py", "packages/context/builder"),
        fact("NeverRanked"),
    )
    sent = ContextPackage(
        primary_symbol=PROBE_NAMED_SYMBOL,
        supporting_symbols=[PROBE_LATE_SYMBOL],
        related_modules=[PROBE_NAMED_MODULE],
    )

    assert context_facts_available(sent, PROBE_QUERY, facts) == (
        "ContextBuilder",
        "ContextSession",
        "packages/context/builder.py",
    )
    assert context_facts_available(None, PROBE_QUERY, facts) == ()
    assert context_facts_available(sent, PROBE_QUERY, ()) == ()


def test_changed_file_probe_facts_are_checked_against_the_context_of_each_arm() -> None:
    """What the ``*_facts`` fields mean, on a fixture whose content is known.

    The probe serializes each arm's package the way the gateway would and asks the
    same matcher the scored live probe asks.  A fact only counts as available if
    its text reaches the prompt - which is why ``NeverRanked`` stays out of both
    arms even though it is a plausible symbol name, and why a probe can report a
    loss that the symbol counters cannot see.
    """
    probe = _probe(facts=(fact("ContextBuilder"), fact("ContextSession"), fact("NeverRanked")))
    outcome = run_changed_file_probe(
        probe, _probe_index(), weight=1, stage_kwargs=PROBE_STAGE_KWARGS
    )

    assert outcome.baseline_facts == ("ContextBuilder", "ContextSession")
    assert outcome.changed_facts == ("ContextBuilder", "ContextSession")
    assert outcome.facts_lost == ()


def test_changed_file_probe_outcome_reports_the_facts_the_changed_arm_lost() -> None:
    """A fact present off and absent on is the loss, and is named as one."""
    outcome = changed_file_probe_outcome(
        _probe(probe_id="registry_case"),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={},
        weight=25,
        baseline_facts=("ContextBuilder", "_enforce_budget"),
        changed_facts=("_enforce_budget",),
    )

    assert outcome.baseline_facts == ("ContextBuilder", "_enforce_budget")
    assert outcome.changed_facts == ("_enforce_budget",)
    assert outcome.facts_lost == ("ContextBuilder",)


def test_print_changed_file_table_shows_the_facts_each_arm_could_support(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The table reports the context loss, because the counters alone hide it."""
    outcome = changed_file_probe_outcome(
        _probe(probe_id="registry_case"),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={"changed_context_differs": True},
        weight=25,
        baseline_facts=("ContextBuilder", "_enforce_budget"),
        changed_facts=("_enforce_budget",),
    )

    print_changed_file_table([outcome])

    printed = capsys.readouterr().out
    assert "facts available off=2 on=1" in printed
    assert "lost=ContextBuilder" in printed


def test_print_changed_file_table_omits_the_facts_line_without_facts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A case with no registered facts does not print an empty claim."""
    print_changed_file_table(
        [
            changed_file_probe_outcome(
                _probe(probe_id="registry_case"),
                baseline=[PROBE_NAMED_SYMBOL],
                changed=[PROBE_DIRTY_SYMBOL],
                promotion={},
                weight=25,
            )
        ]
    )

    assert "facts available" not in capsys.readouterr().out


def test_changed_file_probe_holds_the_named_primary_below_the_flip_weight() -> None:
    """What the registry asserts about a request: the named symbol stays first."""
    outcome = run_changed_file_probe(
        _probe(),
        _probe_index(),
        weight=_fixture_flip_weight() - 1,
        stage_kwargs=PROBE_STAGE_KWARGS,
    )

    assert outcome.ok
    assert outcome.baseline_primary == PROBE_NAMED_SYMBOL
    assert outcome.changed_primary == PROBE_NAMED_SYMBOL
    assert outcome.symbols_promoted == 0
    assert not outcome.context_differs


def test_changed_file_probe_reports_a_swap_at_the_flip_weight() -> None:
    """The probe measures something: reach the gap and it says the primary moved."""
    outcome = run_changed_file_probe(
        _probe(),
        _probe_index(),
        weight=_fixture_flip_weight(),
        stage_kwargs=PROBE_STAGE_KWARGS,
    )

    assert not outcome.ok
    assert outcome.baseline_primary == PROBE_NAMED_SYMBOL
    assert outcome.changed_primary == PROBE_DIRTY_SYMBOL
    assert outcome.primary_promoted
    assert outcome.context_differs
    assert outcome.baseline_status == "built"


def test_changed_file_probe_sees_a_reorder_a_set_difference_could_not() -> None:
    """The counters come from the stage, which compares the composed packages.

    Two fixture symbols are exactly tied, so promoting the dirty one rearranges
    the supporting list without changing its membership or the primary.  The set
    difference this harness used to compute as its own ``churn`` reads that as
    "nothing changed"; the stage's ``changed_context_differs`` is the reason the
    claim has to come from the stage.
    """
    outcome = run_changed_file_probe(
        _probe(probe_id="reorder", dirty_module=PROBE_LATE_MODULE, names_primary=False),
        _probe_index(),
        weight=1,
        stage_kwargs=PROBE_STAGE_KWARGS,
    )

    assert outcome.ok
    assert outcome.context_differs
    assert not outcome.primary_promoted
    assert outcome.symbols_promoted == 0


def test_changed_file_probe_reports_the_gate_when_the_query_ignores_the_file() -> None:
    """A dirty file the query never reaches is inert, and says so by status.

    ``changed_symbols_selected`` would read zero here too, which is exactly the
    ambiguity the counterfactual was added to remove: the file is dirty, nothing
    in it is relevant, so the two arms are identical by construction.
    """
    outcome = run_changed_file_probe(
        _probe(probe_id="inert", dirty_module="packages/monitoring/metrics_server"),
        _probe_index(),
        weight=1000,
        stage_kwargs=PROBE_STAGE_KWARGS,
    )

    assert outcome.ok
    assert outcome.symbols_promoted == 0
    assert not outcome.context_differs
    assert outcome.baseline_status == "skipped_no_bonus"


def test_run_changed_file_probe_uses_the_configured_weight_by_default() -> None:
    """Without an override the probe runs the value the code ships with."""
    configured = RankingConfig.WEIGHT_CHANGED_FILE

    outcome = run_changed_file_probe(_probe(), _probe_index(), stage_kwargs=PROBE_STAGE_KWARGS)

    assert outcome.weight == configured


def test_run_changed_file_probe_restores_the_configured_weight() -> None:
    """The override is for one run, not for the process."""
    configured = RankingConfig.WEIGHT_CHANGED_FILE

    run_changed_file_probe(
        _probe(), _probe_index(), weight=configured + 100, stage_kwargs=PROBE_STAGE_KWARGS
    )

    assert RankingConfig.WEIGHT_CHANGED_FILE == configured


def test_run_changed_file_probe_reports_a_broken_index_without_raising() -> None:
    """A sweep of probes must not be ended by one unusable case."""
    outcome = run_changed_file_probe(_probe(), None, stage_kwargs=PROBE_STAGE_KWARGS)

    assert not outcome.ok
    assert outcome.error


def test_changed_file_probe_outcome_reads_the_stage_counters() -> None:
    """Which primary is sent is the verdict; the stage's fields are the detail."""
    outcome = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_NAMED_SYMBOL, PROBE_DIRTY_SYMBOL],
        changed=[PROBE_NAMED_SYMBOL, PROBE_TIED_SYMBOL, PROBE_DIRTY_SYMBOL],
        promotion={
            "changed_context_differs": True,
            "changed_primary_promoted": False,
            "changed_symbols_promoted": 0,
            "changed_baseline_status": "built",
        },
        weight=5,
        max_context_tokens=4096,
    )

    assert outcome.ok
    assert outcome.context_differs
    assert not outcome.primary_promoted
    assert outcome.symbols_promoted == 0
    assert outcome.baseline_status == "built"
    assert outcome.baseline_symbols == 2
    assert outcome.changed_symbols == 3


def test_changed_file_probe_outcome_fails_when_nothing_is_sent() -> None:
    """An empty changed arm cannot have kept a primary."""
    outcome = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[],
        promotion={},
        weight=5,
    )

    assert not outcome.ok
    assert outcome.changed_primary == ""
    assert outcome.symbols_promoted == 0
    assert outcome.baseline_status == ""


def test_changed_file_probe_outcome_fails_when_the_baseline_was_already_wrong() -> None:
    """A changed arm agreeing proves nothing when the off arm did not agree.

    The regression: ``ok`` used to read the changed arm alone, so a case whose
    bonus-off primary was some other symbol reported a hold the moment the dirty
    arm happened to match.  What a case claims is that its symbol *survives* the
    bonus, and an arm that never sent it demonstrates nothing about survival.
    """
    outcome = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_DIRTY_SYMBOL, PROBE_NAMED_SYMBOL],
        changed=[PROBE_NAMED_SYMBOL, PROBE_DIRTY_SYMBOL],
        promotion={
            "changed_context_differs": True,
            "changed_primary_promoted": True,
            "changed_symbols_promoted": 1,
            "changed_baseline_status": "built",
        },
        weight=25,
    )

    assert outcome.baseline_primary == PROBE_DIRTY_SYMBOL
    assert outcome.changed_primary == PROBE_NAMED_SYMBOL
    assert not outcome.ok
    assert changed_file_verdict(outcome) == "BAD_BASELINE"


def test_changed_file_verdict_distinguishes_the_four_ways_a_case_can_read() -> None:
    """``HOLD``, ``MOVE``, ``SWAP`` and ``BAD_BASELINE`` name four different arms.

    One word per outcome, and the word has to blame the right side: a reorder that
    kept the primary is a hold, a dirty arm that lost it where the case expected it to
    be held is the bonus's doing, and a baseline that never sent it is a case stated
    wrong - which is also the outcome that would make a "measurable loss" claim about an
    arm that had nothing to lose.  ``MOVE`` is the fourth, and it is not a failure: it is
    a gain case, where the primary was expected to arrive with the changed file.  The
    last two outcomes here are the same measurement read against two different
    documents, which is the whole difference between costing an answer and buying one.
    """
    held = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_NAMED_SYMBOL, PROBE_TIED_SYMBOL],
        changed=[PROBE_NAMED_SYMBOL, PROBE_DIRTY_SYMBOL],
        promotion={"changed_context_differs": True},
        weight=25,
    )
    swapped = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={"changed_context_differs": True, "changed_primary_promoted": True},
        weight=25,
    )
    moved = changed_file_probe_outcome(
        _probe(expected_changed_primary=PROBE_DIRTY_SYMBOL),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={"changed_context_differs": True, "changed_primary_promoted": True},
        weight=25,
    )
    bad_baseline = changed_file_probe_outcome(
        _probe(),
        baseline=[PROBE_DIRTY_SYMBOL],
        changed=[PROBE_NAMED_SYMBOL],
        promotion={},
        weight=25,
    )
    bad_gain_baseline = changed_file_probe_outcome(
        _probe(expected_changed_primary=PROBE_DIRTY_SYMBOL),
        baseline=[PROBE_TIED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={"changed_context_differs": True, "changed_primary_promoted": True},
        weight=25,
    )

    assert changed_file_verdict(held) == "HOLD"
    assert changed_file_verdict(swapped) == "SWAP"
    assert changed_file_verdict(moved) == "MOVE"
    assert changed_file_verdict(bad_baseline) == "BAD_BASELINE"
    assert changed_file_verdict(bad_gain_baseline) == "BAD_BASELINE"
    # A move is not a swap: the same arm is one or the other depending on what the case
    # documents, so `ok` cannot be read as "the primary held" and never was.
    assert moved.ok is True
    assert swapped.ok is False


def test_print_changed_file_table_blames_the_right_arm_for_a_bad_premise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wrong baseline is reported as a broken premise, never as a swap."""
    outcome = changed_file_probe_outcome(
        _probe(probe_id="bad_premise"),
        baseline=[PROBE_DIRTY_SYMBOL],
        changed=[PROBE_NAMED_SYMBOL],
        promotion={},
        weight=25,
    )

    print_changed_file_table([outcome])

    printed = capsys.readouterr().out
    assert "BAD_BASELINE" in printed
    assert "SWAP" not in printed


# ---------------------------------------------------------------------------
# The live half of the same decisions.  ``CHANGED_FILE_PROBES`` says what the
# bonus does to retrieval; whether that changes an answer is a claim about the
# gateway, so each case's query is also registered as an ordinary scored probe and
# run with `--probe <id> --repeat 3` against a feature-off and a feature-on gateway.
# A pair is only interpretable if both halves ask the identical question and check
# the identical facts, which is what the equality assertions below pin - the first
# version of this comparison had the scored probe append extra wording the offline
# diagnostic never sent, so the two arms retrieved different things and no answer
# difference could be attributed to the bonus.  A pair is only worth running at all
# if its two arms differ in what they can *support*, and that is settled below
# against this repository's real index and the real ``RepositoryContextStage``.  It
# cannot be settled by writing two answers by hand and scoring them: that proves the
# matcher works, not that a live A/B can tell the arms apart.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

CHANGED_FILE_AB_PROBE_ID = "explain_changed_files_contextbuilder"
CHANGED_FILE_AB_EVICTION_PROBE_ID = "explain_changed_files_repository_index"

#: The scored probe of the benefit pair, named the same way: the id is the claim that
#: the changed file helps, so the tests that discriminate cost from gain take it as a
#: parameter instead of hard-coding a second pair of registries.
CHANGED_FILE_AB_BENEFIT_PROBE_ID = "explain_changed_files_history_cap"

#: The budget the eviction case is stated at.  The stage default,
#: ``APP_REPOSITORY_CONTEXT_MAX_TOKENS`` and the EXPLAIN intent budget this probe is
#: planned into all agree on 4096, and the budget decides whether a whole file fits
#: beside the dirty one, so the loss below is pinned at it rather than discovered
#: through a developer's ``.env``.
CHANGED_FILE_AB_BUDGET_TOKENS = 4096


@pytest.fixture(scope="module")
def checked_out_index() -> RepositoryIndex:
    """This repository's real index, built once for the changed-file regressions.

    The exclusions are the fallbacks ``--changed-file-probe`` uses when it is pointed
    at a path, not a developer's ``.env``, so the case measures the same tree on any
    machine.  The dirty module is injected by the probe either way, never read from
    Git, so a clean checkout and a dirty one measure the same thing.
    """
    from packages.repository.index.builder import RepositoryIndexBuilder

    root, exclude_tests, exclude_globs = repository_index_settings(str(REPO_ROOT))
    builder = RepositoryIndexBuilder(exclude_tests=exclude_tests, exclude_globs=exclude_globs)
    return builder.build(root)


def _real_arms(
    index: RepositoryIndex,
    probe: ChangedFileProbe,
    *,
    weight: int | None = None,
    budget: int = CHANGED_FILE_AB_BUDGET_TOKENS,
) -> ChangedFileOutcome:
    """Run one real case with the signal off, then with its dirty module injected.

    ``weight=None`` means the shipped ``WEIGHT_CHANGED_FILE``, so a test that says
    nothing about weight measures what a gateway with the feature enabled would.
    """
    stage_kwargs: dict[str, object] = {
        "context_delta_injection": False,
        "max_context_tokens": budget,
    }
    return run_changed_file_probe(probe, index, weight=weight, stage_kwargs=stage_kwargs)


def _ab_probe(probe_id: str = CHANGED_FILE_AB_PROBE_ID) -> QualityProbe:
    """The scored probe registered for one offline changed-file case."""
    return next(probe for probe in PROBES if probe.id == probe_id)


def test_changed_file_ab_pairs_are_registered_on_both_sides() -> None:
    """Every offline case that a scored probe speaks for is in the pair table.

    The pairing is the whole claim that the offline table and the live run measure one
    retrieval, so it is checked in both directions: a pair naming a case or a probe
    that does not exist is a mistake, and a case carrying facts that no probe scores
    live is a measurement nobody can run.
    """
    offline_ids = [probe.id for probe in CHANGED_FILE_PROBES]
    scored_ids = [probe.id for probe in PROBES]

    assert len(set(CHANGED_FILE_AB_PAIRS)) == len(CHANGED_FILE_AB_PAIRS)
    for offline_id, probe_id in CHANGED_FILE_AB_PAIRS:
        assert offline_id in offline_ids, offline_id
        assert probe_id in scored_ids, probe_id

    # `facts` is what makes a case answerable rather than merely reorderable, and an
    # unpaired case must not pretend otherwise.
    paired_offline = {offline_id for offline_id, _ in CHANGED_FILE_AB_PAIRS}
    for probe in CHANGED_FILE_PROBES:
        if probe.facts:
            assert probe.id in paired_offline, probe.id
        if probe.id in paired_offline:
            assert len(probe.facts) >= 2, probe.id


def test_changed_file_ab_probe_selects_like_a_normal_probe() -> None:
    """Being in the fixed set is what makes `--probe`/`--repeat` reach it."""
    for offline_id, probe_id in CHANGED_FILE_AB_PAIRS:
        assert _resolve_probes([probe_id])[0] is _ab_probe(probe_id), offline_id
        assert _ab_probe(probe_id) is next(
            probe for probe in PROBES if probe.id == probe_id
        ), offline_id

        args = parse_args(["--probe", probe_id, "--repeat", "3"])
        assert args.probe == [probe_id]
        assert args.repeat == 3, probe_id


def test_changed_file_ab_probe_shares_the_offline_query() -> None:
    """The scored probe asks its case's question word for word, with nothing added.

    Both halves of a changed-file A/B run on the same machine, but over different
    retrieval states.  If they also asked different questions, an answer difference
    could never be attributed to the ranking bonus.  Each pair's prompt is one
    constant read by both halves, and the assertion is equality rather than
    containment: a probe may not pad the shared question with wording the offline
    arm never ranks.
    """
    for offline_id, probe_id in CHANGED_FILE_AB_PAIRS:
        offline = resolve_changed_file_case(offline_id, CHANGED_FILE_PROBES)
        assert offline.query == _ab_probe(probe_id).prompt, offline_id

    # The constants are the prompts, so neither half of a pair can be reworded
    # without editing the registry, which is where the fact-check tests look too.
    assert resolve_changed_file_case("named_in_query", CHANGED_FILE_PROBES).query == (
        CONTEXT_BUILDER_BUDGET_QUERY
    )
    assert PROBE_QUERY == CONTEXT_BUILDER_BUDGET_QUERY
    assert resolve_changed_file_case(
        "evicts_the_asked_about_file", CHANGED_FILE_PROBES
    ).query == REPOSITORY_INDEX_BUILD_QUERY
    assert resolve_changed_file_case(
        "gains_the_changed_file", CHANGED_FILE_PROBES
    ).query == HISTORY_CAP_QUERY
    # The benefit case is the eviction case turned around: it dirties the file the
    # question is *about*, and it still names no symbol.  Were that untrue, the extra
    # context the changed arm carries would be a name collision rather than a ranking,
    # and the gain could not be attributed to the bonus.
    assert HISTORY_CAP_DIRTY_MODULE not in HISTORY_CAP_QUERY
    assert "cap_history" not in HISTORY_CAP_QUERY
    assert all(
        name not in HISTORY_CAP_QUERY
        for name in (
            "CapHistorySettings",
            "cap_turns",
            "CapResult",
            "_cap_current_tool_result",
        )
    )
    # The eviction case asks about one file and dirties another, and the prompt is
    # prose: it quotes no symbol name, so the swap cannot be blamed on a name
    # collision between the query text and the injected file.
    assert REPOSITORY_INDEX_BUILD_DIRTY_MODULE not in REPOSITORY_INDEX_BUILD_QUERY
    assert all(
        name not in REPOSITORY_INDEX_BUILD_QUERY
        for name in (
            "RepositoryIndexBuilder",
            "RepositoryIndex",
            "PythonAstExtractor",
            "RelationshipRegistry",
            "CallExtractor",
        )
    )


def test_changed_file_ab_probe_facts_are_the_offline_case_facts() -> None:
    """The scored probes check the statements their offline case reports on.

    ``ChangedFileProbe.facts`` exists so the offline table's "facts available" line
    and the live probe's score are about the same claims.  If the two drift apart,
    the retrieval measurement stops describing the answer measurement.
    """
    paired = dict(CHANGED_FILE_AB_PAIRS)

    for case in CHANGED_FILE_PROBES:
        probe_id = paired.get(case.id)
        if probe_id is None:
            continue
        scored = _ab_probe(probe_id)
        assert scored.intent == "EXPLAIN", probe_id
        assert scored.expect == case.facts, probe_id

    # The names the offline case reports on are the names a scored arm can miss.
    assert resolve_changed_file_case(
        "evicts_the_asked_about_file", CHANGED_FILE_PROBES
    ).facts == REPOSITORY_INDEX_BUILD_FACTS
    assert resolve_changed_file_case("named_in_query", CHANGED_FILE_PROBES).facts == (
        CONTEXT_BUILDER_BUDGET_FACTS
    )
    # The gain case reports on the cap's own internals, which is what makes its two
    # arms differ in text and not only in order.
    assert resolve_changed_file_case("gains_the_changed_file", CHANGED_FILE_PROBES).facts == (
        HISTORY_CAP_FACTS
    )


def test_changed_file_ab_probe_facts_are_repository_truth() -> None:
    """The expected facts can be checked in the tree they are scored against."""
    context_builder_source = (REPO_ROOT / "packages/context/builder.py").read_text(
        encoding="utf-8"
    )
    index_builder_source = (REPO_ROOT / "packages/repository/index/builder.py").read_text(
        encoding="utf-8"
    )

    assert {expected.label for expected in _ab_probe().expect} == {
        "ContextBuilder",
        "_enforce_budget",
        "packages/context/builder.py",
    }
    assert "class ContextBuilder" in context_builder_source
    assert "def _enforce_budget" in context_builder_source

    assert {
        expected.label
        for expected in _ab_probe(CHANGED_FILE_AB_EVICTION_PROBE_ID).expect
    } == {
        "PythonAstExtractor",
        "RelationshipRegistry",
        "CallExtractor",
    }
    for implementation_fact in ("PythonAstExtractor", "RelationshipRegistry", "CallExtractor"):
        assert implementation_fact in index_builder_source

    # The benefit pair's facts are the same kind of claim: statements about one file,
    # checkable in that file.  `cap_history` is the entry point, and the three that
    # follow it are the mechanism - the per-message budget, the shape it recognizes, and
    # the marker the truncation leaves in the transcript - none of which a model can name
    # from the call sites the other arm sees.
    history_source = (REPO_ROOT / "packages/pipeline/history.py").read_text(encoding="utf-8")
    assert {
        expected.label
        for expected in _ab_probe(CHANGED_FILE_AB_BENEFIT_PROBE_ID).expect
    } == {
        "cap_history",
        "max_current_tool_result_tokens",
        "_looks_like_cline_tool_result_message",
        "[... truncated by gateway history cap ...]",
    }
    for cap_fact in (
        "def cap_history",
        "max_current_tool_result_tokens",
        "def _looks_like_cline_tool_result_message",
        "truncated by gateway history cap",
    ):
        assert cap_fact in history_source

    # The discriminating probe's question quotes none of its own answers, so every
    # fact has to come out of the context: that is what makes a context loss show up
    # as an answer loss.  Its negative control may name its subject - the case is
    # that the bonus loses a file the prompt never named.
    eviction = _ab_probe(CHANGED_FILE_AB_EVICTION_PROBE_ID)
    assert all(
        variant not in eviction.prompt
        for expected in eviction.expect
        for variant in expected.variants
    )


def test_changed_file_ab_discriminating_case_loses_the_file_that_carries_the_facts(
    checked_out_index: RepositoryIndex,
) -> None:
    """The eviction pair, measured on this repository's index with the real stage.

    This is the regression behind ``explain_changed_files_repository_index``.  With
    the signal off the context carries ``packages/repository/index/builder.py``; with
    ``packages/repository/index/models.py`` injected dirty at the shipped ``+25`` it
    carries none of it, and every fact the probe scores lives in the file that left.
    That is why this pair can separate two answers and the one it replaced could not:
    the arms were asserted apart, here they are measured apart.

    The premise is checked on the way.  The arm with the bonus off must lead with the
    asked-about file's class, or the changed arm losing it says nothing about a bonus
    that was never in the running.
    """
    case = resolve_changed_file_case("evicts_the_asked_about_file", CHANGED_FILE_PROBES)
    outcome = _real_arms(checked_out_index, case)

    # Premise: the feature-off arm leads with the fact-bearing file's class.
    assert outcome.baseline_status == "built"
    assert outcome.baseline_primary == case.expected_primary
    assert outcome.max_context_tokens == CHANGED_FILE_AB_BUDGET_TOKENS
    assert outcome.baseline_facts == tuple(
        expected.label for expected in REPOSITORY_INDEX_BUILD_FACTS
    )

    # The changed arm: the dirty module's symbols take the front of the order and the
    # budget runs out before the builder file is reached.
    assert changed_file_verdict(outcome) == "SWAP"
    assert outcome.changed_primary.startswith(f"{REPOSITORY_INDEX_BUILD_DIRTY_MODULE}.")
    assert outcome.changed_facts == ()
    assert outcome.facts_lost == outcome.baseline_facts

    # The loss is eviction rather than the dirty file contributing anything new: a
    # flat bonus reorders, and here reordering is what pushes a whole file out.
    assert outcome.context_differs is True
    assert outcome.primary_promoted is True
    assert outcome.symbols_promoted == 0
    assert outcome.changed_symbols < outcome.baseline_symbols



def test_changed_file_ab_benefit_case_gains_the_file_the_question_asks_about(
    checked_out_index: RepositoryIndex,
) -> None:
    """The gain pair, measured on this repository's index with the real stage.

    This is the regression behind ``explain_changed_files_history_cap``, and the case the
    opt-in exists for.  The prompt is prose and names no symbol, and the file it dirties
    is the file the prompt is *about*, so the bonus is not trading one answer for another
    the way the eviction pair does.  Measured at 4096 tokens: with the signal off, the
    token ``model`` name-matches a models-listing endpoint, that takes the primary, and
    the context meets ``cap_history`` only where it is called - the function's own
    definition is not sent at all.  With ``packages/pipeline/history`` injected dirty at
    the shipped ``+25``, the budget buys the file and the mechanism the question asks for
    arrives in the prompt.

    A gain has to be measured on both sides, because a gain that also costs something is
    the eviction case under another name: every fact the off arm could support must still
    be supported, and the facts it lacked must arrive.
    """
    case = resolve_changed_file_case("gains_the_changed_file", CHANGED_FILE_PROBES)
    outcome = _real_arms(checked_out_index, case)

    # Premise: the off arm can say that history is capped, and cannot say how.
    assert outcome.error == ""
    assert outcome.baseline_status == "built"
    assert outcome.baseline_primary == case.expected_primary == HISTORY_CAP_PRIMARY
    assert outcome.max_context_tokens == CHANGED_FILE_AB_BUDGET_TOKENS
    assert outcome.baseline_facts == (HISTORY_CAP_FACTS[0].label,)

    # The changed arm leads with the changed file.  `ok` here means the primary moved
    # where the case documents it moves, which is not what `ok` means for a survival case
    # - the reason the expectation is carried per arm rather than in one field.
    assert changed_file_verdict(outcome) == "MOVE"
    assert outcome.ok is True
    assert outcome.changed_primary == HISTORY_CAP_CHANGED_PRIMARY
    assert outcome.changed_primary == case.expected_changed_primary
    assert outcome.changed_primary.startswith(f"{HISTORY_CAP_DIRTY_MODULE}.")

    # The gain itself, in both directions: nothing the off arm had is lost, and the three
    # facts that live inside the cap arrive.
    assert outcome.changed_facts == tuple(
        expected.label for expected in HISTORY_CAP_FACTS
    )
    assert outcome.facts_lost == ()
    assert set(outcome.baseline_facts) < set(outcome.changed_facts)
    assert outcome.context_differs is True
    assert outcome.primary_promoted is True
    assert outcome.symbols_promoted == 4
    assert outcome.changed_symbols < outcome.baseline_symbols

    # Symbol by symbol, since a fact can survive a reorder.  The changed file contributes
    # two symbols even with the signal off, because `history` and `conversation` reach the
    # gate as path tokens; neither of them is the function asked about.  The signal trades
    # thirteen symbols of nine other modules for the four definitions that are the cap.
    stage_kwargs: dict[str, object] = {
        "context_delta_injection": False,
        "max_context_tokens": CHANGED_FILE_AB_BUDGET_TOKENS,
    }
    with unittest.mock.patch.object(RankingConfig, "WEIGHT_CHANGED_FILE", 25):
        off, _ = _stage_arm(checked_out_index, case.query, frozenset(), stage_kwargs=stage_kwargs)
        on, _ = _stage_arm(
            checked_out_index,
            case.query,
            frozenset({case.dirty_module}),
            stage_kwargs=stage_kwargs,
        )

    cap = f"{HISTORY_CAP_DIRTY_MODULE}.cap_history"
    assert cap not in off
    assert cap in on
    assert set(on) - set(off) == {
        f"{HISTORY_CAP_DIRTY_MODULE}.{name}"
        for name in (
            "cap_history",
            "_build_cap_groups",
            "_cap_current_tool_result",
            "_estimate_tokens",
        )
    }
    off_target = [name for name in off if _module_of(name) == HISTORY_CAP_DIRTY_MODULE]
    on_target = [name for name in on if _module_of(name) == HISTORY_CAP_DIRTY_MODULE]
    assert len(off_target) == 2
    assert len(on_target) == 6
    assert case.named_in_query() is False


def _module_of(qualified_name: str) -> str:
    """The index module key a qualified name lives in, as the index writes it."""
    last = qualified_name.rsplit("/", 1)[-1]
    prefix = qualified_name[: len(qualified_name) - len(last)]
    return f"{prefix}{last.split('.', 1)[0]}"


def test_changed_file_ab_discriminating_case_loses_symbols_not_just_position(
    checked_out_index: RepositoryIndex,
) -> None:
    """The changed arm is not reordered - the fact-bearing symbols are gone.

    A symbol that stays in the context stays available, whatever position it holds, so
    the loss is checked symbol by symbol instead of read off the primary: every symbol
    of the asked-about file the off arm sent has to be absent from the on arm, and the
    on arm may not be the off arm plus the dirty file.  Primary movement alone proves
    nothing, which is the mistake the first version of this comparison made.
    """
    case = resolve_changed_file_case("evicts_the_asked_about_file", CHANGED_FILE_PROBES)
    stage_kwargs: dict[str, object] = {
        "context_delta_injection": False,
        "max_context_tokens": CHANGED_FILE_AB_BUDGET_TOKENS,
    }
    with unittest.mock.patch.object(RankingConfig, "WEIGHT_CHANGED_FILE", 25):
        off, _ = _stage_arm(checked_out_index, case.query, frozenset(), stage_kwargs=stage_kwargs)
        on, _ = _stage_arm(
            checked_out_index,
            case.query,
            frozenset({case.dirty_module}),
            stage_kwargs=stage_kwargs,
        )

    off_target = [
        name for name in off if _module_of(name) == REPOSITORY_INDEX_BUILD_TARGET_MODULE
    ]
    on_target = [
        name for name in on if _module_of(name) == REPOSITORY_INDEX_BUILD_TARGET_MODULE
    ]

    assert off_target, "the off arm must send the asked-about file's symbols"
    assert _module_of(off[0]) == REPOSITORY_INDEX_BUILD_TARGET_MODULE
    assert on_target == []
    assert set(on) < set(off)


def test_changed_file_ab_negative_control_moves_the_primary_and_loses_nothing(
    checked_out_index: RepositoryIndex,
) -> None:
    """The contextbuilder pair cannot separate two answers, and must not claim to.

    The same measurement run on the pair this comparison started with.  ``+25`` does
    hand the primary to ``packages/context/budget.py``, so a reader who stopped at
    ``changed_primary_promoted`` would call that an effect, and the first version of
    this harness did.  It is not one: the bonus puts two symbols in front of the three
    the query named instead of replacing them, so all three facts are still in the
    text the changed arm would have sent and both arms should score 3/3.  It stays
    registered as the negative control precisely because the pair above does not tie.
    """
    case = resolve_changed_file_case("named_in_query", CHANGED_FILE_PROBES)
    held = _real_arms(checked_out_index, case, weight=5)
    swapped = _real_arms(checked_out_index, case)
    labels = tuple(expected.label for expected in CONTEXT_BUILDER_BUDGET_FACTS)

    assert case.names_primary and case.named_in_query()
    assert held.context_differs is False
    assert held.baseline_primary == held.changed_primary == case.expected_primary

    assert swapped.baseline_primary == case.expected_primary
    assert swapped.changed_primary != case.expected_primary
    assert changed_file_verdict(swapped) == "SWAP"
    assert swapped.symbols_promoted == 2
    assert swapped.changed_symbols > swapped.baseline_symbols
    assert swapped.facts_lost == ()
    assert swapped.baseline_facts == swapped.changed_facts == labels


def test_changed_file_ab_loss_is_not_removed_by_more_supporting_budget(
    checked_out_index: RepositoryIndex,
) -> None:
    """More budget restores symbols, not source detail omitted from support context.

    The case ships stated at ``+25`` because that is the configured weight and at 4096
    tokens because the stage default, ``APP_REPOSITORY_CONTEXT_MAX_TOKENS`` and the
    EXPLAIN intent budget all say 4096.  A bonus of ``+1`` costs exactly what ``+25``
    costs, so the number is not the lever.  At 6144 tokens all builder symbols fit
    again, but they are supporting context: the class summary mentions its default
    ``PythonAstExtractor``, while the constructor-body details
    ``RelationshipRegistry`` and ``CallExtractor`` remain unavailable.  This pins
    the distinction between a visible supporting symbol and implementation detail
    that its representation genuinely does not carry.
    """
    case = resolve_changed_file_case("evicts_the_asked_about_file", CHANGED_FILE_PROBES)
    labels = tuple(expected.label for expected in REPOSITORY_INDEX_BUILD_FACTS)
    at_one = _real_arms(checked_out_index, case, weight=1)
    roomier = _real_arms(
        checked_out_index, case, budget=CHANGED_FILE_AB_BUDGET_TOKENS + 2048
    )

    assert at_one.facts_lost == labels
    assert roomier.baseline_facts == labels
    assert roomier.changed_facts == ("PythonAstExtractor",)
    assert roomier.facts_lost == ("RelationshipRegistry", "CallExtractor")
    assert roomier.baseline_symbols == roomier.changed_symbols


def test_changed_file_probe_registry_is_well_formed() -> None:
    """Every registered case states a query, a file, and a symbol that must win."""
    ids = [probe.id for probe in CHANGED_FILE_PROBES]

    assert len(ids) == len(set(ids)), "probe ids must be unique"
    for probe in CHANGED_FILE_PROBES:
        assert probe.query.strip()
        # A module key, which is the form the changed-file signal is matched in.
        assert "/" in probe.dirty_module and "." not in probe.dirty_module
        module_of_primary = _module_of(probe.expected_primary)
        assert "/" in module_of_primary, "expected primary must be a qualified name"
        # A probe about name priority must not dirty the file it expects to win:
        # that case is a relevance tie, which the bonus is meant to decide.
        assert probe.dirty_module != module_of_primary
        # The claim a case makes about its own query text has to hold: "named in
        # the query" is the strict one, so a case cannot quietly claim it.
        assert probe.names_primary == probe.named_in_query(), (
            f"{probe.id}: names_primary disagrees with the query text"
        )


def test_changed_file_probe_registry_covers_both_name_conditions() -> None:
    """At least one case the query literally names, and one it only name matches."""
    assert any(probe.names_primary for probe in CHANGED_FILE_PROBES)
    assert any(not probe.names_primary for probe in CHANGED_FILE_PROBES)


def test_print_changed_file_table_reports_the_measured_flip(capsys) -> None:
    """The failing line says which file was dirty and what it displaced."""
    outcome = changed_file_probe_outcome(
        _probe(probe_id="registry_case"),
        baseline=[PROBE_NAMED_SYMBOL],
        changed=[PROBE_DIRTY_SYMBOL],
        promotion={
            "changed_context_differs": True,
            "changed_primary_promoted": True,
            "changed_symbols_promoted": 1,
            "changed_baseline_status": "built",
        },
        weight=25,
    )

    print_changed_file_table([outcome])

    printed = capsys.readouterr().out
    assert "CHANGED-FILE RANKING" in printed
    assert "registry_case" in printed
    assert "SWAP" in printed
    assert PROBE_DIRTY_MODULE in printed
    assert "weight=25" in printed
    assert PROBE_NAMED_SYMBOL in printed
    assert "symbols_promoted=1" in printed
    assert "baseline_status=built" in printed


def test_print_changed_file_table_states_the_query_language(capsys) -> None:
    """A line says whether the query named the symbol or merely matched it."""
    print_changed_file_table(
        [
            changed_file_probe_outcome(
                _probe(
                    probe_id="untyped",
                    expected_primary=PROBE_DIRTY_SYMBOL,
                    names_primary=False,
                ),
                baseline=[PROBE_NAMED_SYMBOL],
                changed=[PROBE_NAMED_SYMBOL],
                promotion={},
                weight=5,
            )
        ]
    )

    printed = capsys.readouterr().out
    assert "name match only" in printed
    assert "named in query" not in printed


def test_changed_file_flip_weight_matches_the_engine_order() -> None:
    """The sweep's arithmetic is the engine's order, not a guess at it."""
    from packages.context.models import ContextCandidate
    from packages.context.ranking import RankingEngine

    def candidate(qualified_name: str, module: str, score: int) -> ContextCandidate:
        item = ContextCandidate(
            symbol_id=qualified_name,
            qualified_name=qualified_name,
            module=module,
            symbol_type=SymbolType.CLASS.value,
        )
        item.score = score
        item.reasons = []
        return item

    def rank_with(leader: ContextCandidate, rival: ContextCandidate, weight: int) -> str:
        original = RankingConfig.WEIGHT_CHANGED_FILE
        RankingConfig.WEIGHT_CHANGED_FILE = weight
        try:
            ranked = RankingEngine(changed_modules=frozenset({rival.module})).rank(
                "context a", [candidate(leader.qualified_name, leader.module, 0), rival]
            )
        finally:
            RankingConfig.WEIGHT_CHANGED_FILE = original
        return ranked[0].qualified_name

    leader = candidate("packages/context/m.ContextA", "packages/context/m", 100)

    # A tie in another module is decided by the smallest step there is.
    tied = candidate("packages/context/z.ContextZ", "packages/context/z", 100)
    assert changed_file_flip_weight(leader, tied) == 1
    assert rank_with(leader, tied, 1) == tied.qualified_name

    # Behind, but sorting first on the tie-break: reaching the score is enough.
    before = candidate("packages/context/a.ContextA", "packages/context/a", 90)
    assert changed_file_flip_weight(leader, before) == 10
    assert rank_with(leader, before, 10) == before.qualified_name

    # Behind and sorting later: the step past the score is what moves it up.
    after = candidate("packages/context/zz.ContextZ", "packages/context/zz", 90)
    assert changed_file_flip_weight(leader, after) == 11
    assert rank_with(leader, after, 11) == after.qualified_name


def test_changed_file_sweep_reports_one_row_per_reachable_query() -> None:
    """The sweep ranks each query once and reads the flip weight off the scores."""
    rows = changed_file_sweep(_probe_index(), [PROBE_QUERY])

    assert len(rows) == 1
    row = rows[0]
    assert row.query == PROBE_QUERY
    assert row.leader == PROBE_NAMED_SYMBOL
    assert row.leader_module == PROBE_NAMED_MODULE
    assert row.relevant > 0
    assert row.flip_weight == _fixture_flip_weight()


def test_changed_file_sweep_skips_a_query_that_reaches_nothing() -> None:
    """A query with no candidate above the floor has no flip weight to report."""
    assert changed_file_sweep(_probe_index(), ["zzz qqq nothing"]) == []


def test_print_changed_file_sweep_names_the_flip(capsys) -> None:
    """The sweep line says which file would have to be dirty, and how briefly."""
    rows = changed_file_sweep(_probe_index(), [PROBE_QUERY])

    print_changed_file_sweep(rows)

    printed = capsys.readouterr().out
    assert "CHANGED-FILE FLIP WEIGHT" in printed
    assert PROBE_QUERY in printed
    assert f"flip_at={rows[0].flip_weight}" in printed
    assert PROBE_DIRTY_SYMBOL in printed


def test_changed_file_probe_flag_conflicts_with_gateway_modes() -> None:
    """The offline modes take no gateway, so mixing the two is refused."""
    assert main(["--changed-file-probe", "--delta-context"]) == 2
    assert main(["--changed-file-sweep", "--no-context"]) == 2


def test_changed_file_weight_override_needs_the_probe_mode() -> None:
    """The weight override is a probe diagnostic, not a global knob."""
    assert main(["--changed-file-weight", "5"]) == 2


def test_changed_file_probe_mode_runs_offline_and_reports_by_exit_code(
    tmp_path, monkeypatch, capsys
) -> None:
    """``--changed-file-probe`` dispatches to the probe over the configured root."""
    monkeypatch.setattr(
        "scripts.quality_harness.repository_index_settings",
        lambda repo_root=None: (tmp_path, False, ""),
    )

    code = main(["--changed-file-probe"])

    # An empty tree sends nothing, so no primary can be kept.
    assert code == 1
    assert "CHANGED-FILE RANKING" in capsys.readouterr().out


def test_changed_file_sweep_mode_is_informational(tmp_path, monkeypatch, capsys) -> None:
    """``--changed-file-sweep`` prints the arithmetic and does not fail on it."""
    monkeypatch.setattr(
        "scripts.quality_harness.repository_index_settings",
        lambda repo_root=None: (tmp_path, False, ""),
    )

    code = main(["--changed-file-sweep"])

    assert code == 0
    assert "CHANGED-FILE FLIP WEIGHT" in capsys.readouterr().out
