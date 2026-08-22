"""Tests for the live gateway quality harness helpers."""

from __future__ import annotations

import io
import json
import sys
import unittest.mock

import pytest

from scripts.quality_harness import (
    DEFAULT_MAX_TOKENS,
    DELTA_CONTEXT_PROBE,
    PROBES,
    QUALITY_SYSTEM_PROMPT,
    REASONING_PREAMBLE_PREFIXES,
    TOOL_CHATTER_MARKERS,
    QualityProbe,
    QualityResult,
    _compute_truncation_risk,
    _configured_reasoning_models,
    _read_session_log_records,
    _read_session_log_records_with_retry,
    _record_for_last_user,
    _resolve_probes,
    _warn_low_reasoning_budget,
    build_payload,
    detect_style_violations,
    extract_answer,
    fact,
    main,
    parse_args,
    print_comparison_table,
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
    """The quality baseline denominator should change only intentionally."""
    total_maximum = sum(len(probe.expect) for probe in PROBES)

    assert total_maximum == 20


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
        """Total expected-fact count must remain 20."""
        total_maximum = sum(len(probe.expect) for probe in PROBES)
        assert total_maximum == 20

    def test_probe_tuple_length_unchanged(self) -> None:
        """PROBES must still have 8 entries."""
        assert len(PROBES) == 8


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
