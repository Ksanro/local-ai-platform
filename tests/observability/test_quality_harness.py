"""Tests for the live gateway quality harness helpers."""

from __future__ import annotations

import unittest.mock

from scripts.quality_harness import (
    DELTA_CONTEXT_PROBE,
    PROBES,
    QUALITY_SYSTEM_PROMPT,
    REASONING_PREAMBLE_PREFIXES,
    TOOL_CHATTER_MARKERS,
    QualityProbe,
    QualityResult,
    _read_session_log_records,
    _read_session_log_records_with_retry,
    _record_for_last_user,
    build_payload,
    detect_style_violations,
    extract_answer,
    fact,
    print_comparison_table,
    run_delta_context_probe,
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


def test_build_payload_uses_quality_system_prompt() -> None:
    """Gateway payloads should carry the strengthened quality system prompt."""
    probe = QualityProbe("p1", "SEARCH", "Find the thing", (fact("thing"),))

    payload = build_payload(
        probe,
        model="qwen36",
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
        model="qwen36",
        max_tokens=50,
        use_intent_overrides=True,
        context_enabled=True,
    )

    assert payload["model"] == "qwen36"
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
        model="qwen36",
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
        model="qwen36",
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
        model="qwen36",
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
            model="qwen36",
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
