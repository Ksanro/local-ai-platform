"""Tests for the live gateway quality harness helpers."""

from __future__ import annotations

from scripts.quality_harness import (
    PROBES,
    QualityProbe,
    QualityResult,
    build_payload,
    detect_style_violations,
    extract_answer,
    fact,
    print_comparison_table,
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
