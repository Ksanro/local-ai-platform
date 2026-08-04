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
