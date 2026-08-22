r"""Live gateway quality smoke test for repository-aware answers.

Runs a fixed set of low-token prompts against the OpenAI-compatible gateway
and scores each answer by deterministic expected fact matches.

Usage
-----

.. code-block:: powershell

    .\uv.exe run python scripts\quality_harness.py
    .\uv.exe run python scripts\quality_harness.py --verbose
    .\uv.exe run python scripts\quality_harness.py --no-context
    .\uv.exe run python scripts\quality_harness.py --compare-context
    .\uv.exe run python scripts\quality_harness.py --no-intent-overrides
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_MODEL = os.environ.get("APP_DEFAULT_MODEL") or os.environ.get(
    "DEFAULT_MODEL", "default-model"
)
DEFAULT_MAX_TOKENS = 400
DEFAULT_REASONING_MIN_TOKENS = 2048
QUALITY_SYSTEM_PROMPT = (
    "You are a repository fact oracle. Answer with only the requested "
    "repository facts: file paths, function names, variable names, or "
    "ordered stage lists. Do not include reasoning, analysis, planning "
    "text, or step-by-step narration. Do not start with phrases like "
    "\"Let me\", \"I will\", \"I'll\", \"I need to\", \"I'm going to\", "
    "\"The user\", \"We need to\", or \"First,\". Do not emit XML tags "
    "such as <thinking>, <read_file>, <search_files>, <list_files>, "
    "<execute_command>, <attempt_completion>, or closing thinking tags. "
    "Do not emit <tool_call> or </tool_call> wrappers, "
    "fake tool calls, or JSON tool invocations. "
    "Begin directly with the answer."
)
REASONING_PREAMBLE_PREFIXES: tuple[str, ...] = (
    "i need to",
    "i will",
    "i'll",
    "let me",
    "i'm going to",
    "the user",
    "we need to",
    "first,",
)
TOOL_CHATTER_MARKERS: tuple[str, ...] = (
    "<thinking>",
    "</thinking>",
    "<read_file>",
    "<search_files>",
    "<list_files>",
    "<execute_command>",
    "<attempt_completion>",
    "<tool_call>",
    "</tool_call>",
)


@dataclass(frozen=True)
class ExpectedFact:
    """A required fact with acceptable textual variants."""

    label: str
    variants: tuple[str, ...]


def fact(label: str, *variants: str) -> ExpectedFact:
    """Create an expected fact from a canonical label and optional aliases."""
    return ExpectedFact(label=label, variants=(label, *variants))


def turn(role: str, content: str) -> dict[str, str]:
    """Create one conversation-history message for a multi-turn probe."""
    return {"role": role, "content": content}


@dataclass(frozen=True)
class QualityProbe:
    """A fixed quality prompt with deterministic expected answer facts.

    `history` holds prior conversation turns (role/content dicts) sent before
    `prompt`, simulating a Cline-like multi-turn session. The assistant turns
    in `history` are fixed canned text, not model output - only the final
    `prompt` response is scored. Single-turn probes leave `history` empty.
    """

    id: str
    intent: str
    prompt: str
    expect: tuple[ExpectedFact, ...]
    history: tuple[dict[str, str], ...] = ()


@dataclass
class QualityResult:
    """One probe execution result."""

    id: str
    intent: str
    ok: bool = False
    answer: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    seconds: float = 0.0
    hits: tuple[str, ...] = ()
    misses: tuple[str, ...] = ()
    style_violations: tuple[str, ...] = ()
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> int:
        """Return number of expected facts found in the answer."""
        return len(self.hits)

    @property
    def maximum(self) -> int:
        """Return maximum possible score for this result."""
        return len(self.hits) + len(self.misses)

    @property
    def style_ok(self) -> bool:
        """Return whether the answer avoided known reasoning/tool preambles."""
        return not self.style_violations


@dataclass(frozen=True)
class DeltaContextProbe:
    """A two-request probe that exercises server-side delta context."""

    id: str
    first: QualityProbe
    followup: QualityProbe


@dataclass
class DeltaContextResult:
    """Result of a two-request delta-context probe."""

    id: str
    ok: bool = False
    first: QualityResult | None = None
    followup: QualityResult | None = None
    first_context: dict[str, Any] = field(default_factory=dict)
    followup_context: dict[str, Any] = field(default_factory=dict)
    error: str = ""


PROBES: tuple[QualityProbe, ...] = (
    QualityProbe(
        id="search_answer_preview",
        intent="SEARCH",
        prompt=(
            "In this codebase, where is session log answer_preview extracted? "
            "Name the file and the callable that extracts it."
        ),
        expect=(
            fact("apps/gateway/session_log.py", "apps/gateway/session_log"),
            fact("_extract_answer_preview"),
        ),
    ),
    QualityProbe(
        id="debug_streaming_preview",
        intent="DEBUG",
        prompt=(
            "A streamed chat response is logged with an empty answer_preview. "
            "Which helper should I inspect, and which OpenAI streaming field "
            "should it read?"
        ),
        expect=(
            fact("_choice_content"),
            fact("delta.content", "delta", 'delta.get("content"'),
            fact("apps/gateway/session_log.py", "apps/gateway/session_log"),
        ),
    ),
    QualityProbe(
        id="test_list_content",
        intent="TEST",
        prompt=(
            "Which regression test validates list-form OpenAI message content "
            "normalization reaching internal consumers?"
        ),
        expect=(
            fact(
                "tests/pipeline/test_list_content_normalization.py",
                "tests/pipeline/test_list_content_normalization",
            ),
            fact("test_list_content_text_view_reaches_internal_consumers"),
        ),
    ),
    QualityProbe(
        id="explain_live_path",
        intent="EXPLAIN",
        prompt=(
            "Explain the live gateway request path from /v1/chat/completions "
            "to the provider. Name the main stages in order."
        ),
        expect=(
            fact("modelresolutionstage", "ModelResolutionStage"),
            fact("planningstage", "PlanningStage"),
            fact("repositorycontextstage", "RepositoryContextStage"),
            fact("providerstage", "ProviderStage"),
        ),
    ),
    QualityProbe(
        id="refactor_repository_context",
        intent="REFACTOR",
        prompt=(
            "Refactor investigation only. Which repository context stage file "
            "is the live implementation, and which helper extracts the last "
            "task text?"
        ),
        expect=(
            fact(
                "packages/pipeline/stages/repository_context.py",
                "packages/pipeline/stages/repository_context",
            ),
            fact("select_last_task_text"),
        ),
    ),
    QualityProbe(
        id="implement_health_flag",
        intent="IMPLEMENT",
        prompt=(
            "Implementation task. If adding a repository_context_enabled field "
            "to the health response, which endpoint file and field name are "
            "involved?"
        ),
        expect=(
            fact("apps/gateway/api/health.py", "apps/gateway/api/health"),
            fact("repository_context_enabled"),
        ),
    ),
    QualityProbe(
        id="multiturn_history_cap_budget",
        intent="EXPLAIN",
        history=(
            turn(
                "user",
                "Which component caps forwarded chat history so it does not "
                "grow unbounded, and where does that happen relative to "
                "repository-context injection?",
            ),
            turn(
                "assistant",
                "History capping runs inside PipelineEngine, right after the "
                "repository_context stage and before the provider stage.",
            ),
        ),
        prompt=(
            "For that capping logic: name the function that applies the cap, "
            "its file, and the APP_ environment variable used to force a "
            "specific history-cap token budget instead of deriving one from "
            "the model's context window. Do not name the Python "
            "max_tokens_override argument."
        ),
        expect=(
            fact("_apply_history_cap"),
            fact("packages/pipeline/engine.py", "packages/pipeline/engine"),
            fact("APP_HISTORY_CAP_TOKENS"),
        ),
    ),
    QualityProbe(
        id="multiturn_config_systems",
        intent="EXPLAIN",
        history=(
            turn(
                "user",
                "How many separate configuration systems does this gateway "
                "use for provider settings?",
            ),
            turn(
                "assistant",
                "Two: a Pydantic Settings object with an APP_ prefix, and a "
                "raw-env system with no prefix used by the vLLM provider.",
            ),
        ),
        prompt=(
            "Given that split: which file defines the raw-env DEFAULT_MODEL "
            "variable, and which file defines the Pydantic default_model "
            "field set via APP_DEFAULT_MODEL?"
        ),
        expect=(
            fact("packages/providers/vllm.py", "packages/providers/vllm"),
            fact("apps/gateway/core/config.py", "apps/gateway/core/config"),
        ),
    ),
)

DELTA_CONTEXT_PROBE = DeltaContextProbe(
    id="delta_history_cap_followup",
    first=QualityProbe(
        id="delta_history_cap_primer",
        intent="EXPLAIN",
        prompt=(
            "Which function caps the chat history to a token budget? "
            "Name the function and its file."
        ),
        expect=(
            fact("cap_history"),
            fact("packages/pipeline/history.py", "packages/pipeline/history"),
        ),
    ),
    followup=QualityProbe(
        id="delta_history_cap_followup",
        intent="EXPLAIN",
        prompt=(
            "In packages/pipeline/history.py, cap_history delegates token "
            "counting through one per-message helper that calls one string "
            "estimator helper, and uses one grouping helper for atomic "
            "tool-call groups. Name those three helper functions."
        ),
        expect=(
            fact("_message_token_count"),
            fact("_estimate_tokens"),
            fact("_build_cap_groups"),
        ),
    ),
)


def _normalized(text: str) -> str:
    """Normalize answer text for deterministic fact matching."""
    return text.lower().replace("\\", "/")


def score_answer(
    answer: str,
    expected: tuple[ExpectedFact, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return expected facts found and missing in an answer."""
    normalized_answer = _normalized(answer)
    hits: list[str] = []
    misses: list[str] = []
    for expected_fact in expected:
        if any(
            _normalized(variant) in normalized_answer
            for variant in expected_fact.variants
        ):
            hits.append(expected_fact.label)
        else:
            misses.append(expected_fact.label)
    return tuple(hits), tuple(misses)


def detect_style_violations(answer: str) -> tuple[str, ...]:
    """Detect deterministic answer-style violations.

    This intentionally checks only high-confidence cases: reasoning preambles
    at the start of the answer, and explicit tool/thinking markers anywhere in
    the answer. It is not a language model and does not try to grade prose.
    """
    normalized_answer = answer.strip().lower()
    violations: list[str] = []
    if any(
        normalized_answer.startswith(prefix)
        for prefix in REASONING_PREAMBLE_PREFIXES
    ):
        violations.append("reasoning_preamble")
    if any(marker in normalized_answer for marker in TOOL_CHATTER_MARKERS):
        violations.append("tool_chatter")
    return tuple(violations)


def extract_answer(payload: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Extract assistant text and usage counts from an OpenAI-shaped response."""
    text = ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            text = message["content"]

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    return text, {
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }


def build_payload(
    probe: QualityProbe,
    *,
    model: str,
    max_tokens: int,
    use_intent_overrides: bool,
    context_enabled: bool,
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat completion payload for a probe."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
            *probe.history,
            {"role": "user", "content": probe.prompt},
        ],
        "stream": False,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "repository_context_enabled": context_enabled,
    }
    if use_intent_overrides:
        payload["context_intent"] = probe.intent
    return payload


def post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    """POST JSON with stdlib urllib and return parsed JSON."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("gateway returned non-object JSON")
    return data


def _split_model_list(value: str) -> tuple[str, ...]:
    """Parse a comma-separated model list."""
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _configured_reasoning_models(extra_models: list[str] | None = None) -> tuple[str, ...]:
    """Return model names configured as reasoning-heavy for harness warnings."""
    models = list(_split_model_list(os.environ.get("APP_QUALITY_REASONING_MODELS", "")))
    if extra_models:
        models.extend(extra_models)
    seen: set[str] = set()
    configured: list[str] = []
    for model in models:
        key = model.lower()
        if key not in seen:
            seen.add(key)
            configured.append(model)
    return tuple(configured)


def _warn_low_reasoning_budget(
    model: str,
    max_tokens: int,
    *,
    reasoning_models: tuple[str, ...],
    min_tokens: int = DEFAULT_REASONING_MIN_TOKENS,
) -> None:
    """Emit a stderr warning for configured reasoning models with low budgets.

    Does not change exit code. Output goes to stderr so it cannot contaminate
    machine-readable JSON stdout.
    """
    if not any(model.lower() == configured.lower() for configured in reasoning_models):
        return
    if max_tokens >= min_tokens:
        return
    print(
        f"WARN: model {model!r} is configured as reasoning-heavy but "
        f"max_tokens={max_tokens} is below {min_tokens}. Visible answer may be "
        f"empty or truncated. Use --max-tokens {min_tokens} or higher for "
        f"reliable quality scores.",
        file=sys.stderr,
    )


def _compute_truncation_risk(
    answer: str,
    completion_tokens: int,
    max_tokens: int,
) -> bool:
    """Return True when the model likely hit the completion budget before answering.

    Truncation risk is flagged when the model consumed nearly the entire budget
    (completion_tokens >= max_tokens - 1) but the visible answer is empty or
    very short (fewer than 20 characters after stripping).
    """
    if completion_tokens >= max_tokens - 1:
        if len(answer.strip()) < 20:
            return True
    return False


def run_probe(
    probe: QualityProbe,
    *,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    use_intent_overrides: bool,
    context_enabled: bool,
) -> QualityResult:
    """Run one quality probe against the live gateway."""
    result = QualityResult(id=probe.id, intent=probe.intent)
    result.metadata["max_tokens_requested"] = max_tokens
    result.metadata["truncation_risk"] = False
    payload = build_payload(
        probe,
        model=model,
        max_tokens=max_tokens,
        use_intent_overrides=use_intent_overrides,
        context_enabled=context_enabled,
    )
    url = f"{base_url.rstrip('/')}/chat/completions"
    start = time.perf_counter()
    try:
        response = post_json(url, payload, timeout=timeout)
    except (OSError, TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        result.seconds = time.perf_counter() - start
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.seconds = time.perf_counter() - start
    result.ok = True
    result.answer, usage = extract_answer(response)
    result.prompt_tokens = usage["prompt_tokens"]
    result.completion_tokens = usage["completion_tokens"]
    result.total_tokens = usage["total_tokens"]
    result.hits, result.misses = score_answer(result.answer, probe.expect)
    result.style_violations = detect_style_violations(result.answer)
    result.metadata["truncation_risk"] = _compute_truncation_risk(
        result.answer, result.completion_tokens, max_tokens
    )
    return result


def _session_log_offset(path: str) -> int:
    """Return the current byte offset of a session JSONL file."""
    log_path = Path(path)
    if not log_path.exists():
        return 0
    return log_path.stat().st_size


def _read_session_log_records(path: str, *, offset: int) -> list[dict[str, Any]]:
    """Read JSONL session records appended after `offset`."""
    log_path = Path(path)
    if not log_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
    return records


def _read_session_log_records_with_retry(
    path: str,
    *,
    offset: int,
    expected_min: int,
    max_wait_seconds: float = 5.0,
    sleep_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    """Read JSONL session records appended after `offset` with a short retry loop.

    The session-log middleware flushes *after* the HTTP response reaches the
    client, so the harness may read before the follow-up record is visible on
    disk.  This helper retries until *expected_min* records appear or the
    timeout expires.

    Args:
        path: Path to the session JSONL file.
        offset: Byte offset to start reading from.
        expected_min: Minimum number of records to wait for.
        max_wait_seconds: Maximum total seconds to retry.
        sleep_seconds: Sleep interval between retries.

    Returns:
        All records found after the offset (up to the timeout).
    """
    deadline = time.monotonic() + max_wait_seconds
    records: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        records = _read_session_log_records(path, offset=offset)
        if len(records) >= expected_min:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(sleep_seconds, remaining))
    return records


def _record_for_last_user(
    records: list[dict[str, Any]],
    last_user_message: str,
) -> dict[str, Any]:
    """Find the newest session record for a final user message."""
    for record in reversed(records):
        if record.get("last_user_message") == last_user_message:
            return record
    return {}


def run_delta_context_probe(
    probe: DeltaContextProbe,
    *,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    use_intent_overrides: bool,
    session_log_path: str,
) -> DeltaContextResult:
    """Run a two-request probe and inspect session logs for delta suppression."""
    result = DeltaContextResult(id=probe.id)
    offset = _session_log_offset(session_log_path)

    first = run_probe(
        probe.first,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        use_intent_overrides=use_intent_overrides,
        context_enabled=True,
    )
    result.first = first
    if first.error:
        result.error = first.error
        return result

    followup_probe = QualityProbe(
        id=probe.followup.id,
        intent=probe.followup.intent,
        prompt=probe.followup.prompt,
        expect=probe.followup.expect,
        history=(
            turn("user", probe.first.prompt),
            turn("assistant", first.answer),
        ),
    )
    followup = run_probe(
        followup_probe,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        use_intent_overrides=use_intent_overrides,
        context_enabled=True,
    )
    result.followup = followup
    if followup.error:
        result.error = followup.error
        return result

    records = _read_session_log_records_with_retry(
        session_log_path,
        offset=offset,
        expected_min=2,
    )
    first_record = _record_for_last_user(records, probe.first.prompt)
    followup_record = _record_for_last_user(records, probe.followup.prompt)
    result.first_context = first_record.get("context", {}) if first_record else {}
    result.followup_context = (
        followup_record.get("context", {}) if followup_record else {}
    )

    if not first_record or not followup_record:
        result.error = (
            f"session_log_records_not_found: found {len(records)} record(s) "
            f"after offset {offset}"
        )
        return result

    result.ok = (
        first.score == first.maximum
        and followup.score == followup.maximum
        and int(result.followup_context.get("symbols_suppressed", 0) or 0) > 0
    )
    return result


def print_table(results: list[QualityResult]) -> None:
    """Print a compact quality table with truncation-risk indicators."""
    print("\n" + "=" * 106)
    print(
        f"{'id':<28}{'intent':<11}{'score':>8}{'style':>8}{'ptok':>9}"
        f"{'ctok':>8}{'sec':>8}{'trunc':>6}  misses"
    )
    print("-" * 106)
    total_score = 0
    total_max = 0
    for result in results:
        total_score += result.score
        total_max += result.maximum
        score = f"{result.score}/{result.maximum}"
        style = "ok" if result.style_ok else "bad"
        trunc = "!" if result.metadata.get("truncation_risk") else ""
        misses = ", ".join(result.misses) if result.misses else "-"
        if result.error:
            misses = result.error
        print(
            f"{result.id:<28}{result.intent:<11}{score:>8}{style:>8}"
            f"{result.prompt_tokens:>9}{result.completion_tokens:>8}"
            f"{result.seconds:>8.1f}{trunc:>6}  {misses[:40]}"
        )
    print("-" * 106)
    print(f"{'TOTAL':<39}{f'{total_score}/{total_max}':>8}")
    print("=" * 106)


def print_comparison_table(
    context_results: list[QualityResult],
    no_context_results: list[QualityResult],
) -> None:
    """Print a side-by-side context-on/context-off quality table."""
    print("\n" + "=" * 110)
    print(
        f"{'id':<28}{'intent':<11}{'ctx':>8}{'raw':>8}"
        f"{'dscore':>8}{'ptok ctx':>10}{'ptok raw':>10}{'sec ctx':>9}{'sec raw':>9}"
    )
    print("-" * 110)

    total_ctx = 0
    total_raw = 0
    total_max = 0
    for ctx, raw in zip(context_results, no_context_results, strict=True):
        total_ctx += ctx.score
        total_raw += raw.score
        total_max += ctx.maximum
        print(
            f"{ctx.id:<28}{ctx.intent:<11}{ctx.score:>4}/{ctx.maximum:<3}"
            f"{raw.score:>4}/{raw.maximum:<3}{ctx.score - raw.score:>8}"
            f"{ctx.prompt_tokens:>10}{raw.prompt_tokens:>10}"
            f"{ctx.seconds:>9.1f}{raw.seconds:>9.1f}"
        )

    print("-" * 110)
    print(
        f"{'TOTAL':<39}{total_ctx:>4}/{total_max:<3}"
        f"{total_raw:>4}/{total_max:<3}{total_ctx - total_raw:>8}"
    )
    print("=" * 110)


def print_verbose(results: list[QualityResult]) -> None:
    """Print answer previews for inspection."""
    for result in results:
        print("\n" + "=" * 100)
        print(
            f"{result.id} [{result.intent}] "
            f"hits={list(result.hits)} misses={list(result.misses)}"
        )
        if result.error:
            print(result.error)
        else:
            print(_console_safe(result.answer[:1200]))


def _console_safe(text: str) -> str:
    """Return text printable on Windows consoles using legacy code pages."""
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--fail-under", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="print answer previews")
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="disable repository context injection for this run",
    )
    parser.add_argument(
        "--compare-context",
        action="store_true",
        help="run each probe with repository context on and off",
    )
    parser.add_argument(
        "--no-intent-overrides",
        action="store_true",
        help="let the gateway detect intent instead of sending context_intent",
    )
    parser.add_argument(
        "--delta-context",
        action="store_true",
        help=(
            "run a two-request delta-context probe and inspect the session log "
            "for follow-up symbol suppression"
        ),
    )
    parser.add_argument(
        "--session-log-path",
        default="logs/sessions.jsonl",
        help="session JSONL file to inspect for --delta-context",
    )
    parser.add_argument(
        "--probe",
        action="append",
        default=None,
        metavar="<id>",
        help="run only the named fixed probe(s); may be repeated",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "repeat normal probe runs N times (default 1); "
            "incompatible with --delta-context and --compare-context"
        ),
    )
    parser.add_argument(
        "--reasoning-model",
        action="append",
        default=None,
        metavar="<model>",
        help=(
            "mark a model as reasoning-heavy for low --max-tokens warnings; "
            "may be repeated. APP_QUALITY_REASONING_MODELS also accepts a "
            "comma-separated list"
        ),
    )
    parser.add_argument(
        "--reasoning-min-tokens",
        type=int,
        default=int(os.environ.get(
            "APP_QUALITY_REASONING_MIN_TOKENS",
            str(DEFAULT_REASONING_MIN_TOKENS),
        )),
        help=(
            "minimum recommended --max-tokens for configured reasoning-heavy "
            f"models (default {DEFAULT_REASONING_MIN_TOKENS})"
        ),
    )
    return parser.parse_args(argv)


def _resolve_probes(probe_ids: list[str] | None) -> tuple[QualityProbe, ...]:
    """Return the subset of PROBES matching *probe_ids*, or all PROBES if *probe_ids* is None/empty.

    Duplicate ids are deduplicated while preserving first-requested order.
    Raises ``ValueError`` for unknown ids.
    """
    if not probe_ids:
        return PROBES
    probe_map = {p.id: p for p in PROBES}
    seen: set[str] = set()
    selected: list[QualityProbe] = []
    for pid in probe_ids:
        if pid not in probe_map:
            known = ", ".join(sorted(probe_map.keys()))
            raise ValueError(f"unknown probe id: {pid!r}. Known: {known}")
        if pid not in seen:
            seen.add(pid)
            selected.append(probe_map[pid])
    return tuple(selected)


def _run_probe_set(
    probes: tuple[QualityProbe, ...],
    *,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float,
    use_intent_overrides: bool,
    context_enabled: bool,
) -> list[QualityResult]:
    """Run *probes* once and return the results in probe order."""
    return [
        run_probe(
            probe,
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            use_intent_overrides=use_intent_overrides,
            context_enabled=context_enabled,
        )
        for probe in probes
    ]


def _aggregate_repeat_runs(
    probes: tuple[QualityProbe, ...],
    runs: list[list[QualityResult]],
) -> dict[str, dict[str, Any]]:
    """Compute per-probe aggregates across repeated runs.

    Returns a dict keyed by probe id with ``score_sum``, ``score_max``,
    ``score_min``, and per-fact ``hit_rates`` (list of bool, one per run).
    """
    if not runs:
        return {}
    aggregate: dict[str, dict[str, Any]] = {}
    for probe in probes:
        scores: list[int] = []
        all_facts = [f.label for f in probe.expect]
        hit_rates: dict[str, list[bool]] = {f: [] for f in all_facts}
        for run in runs:
            r = next((x for x in run if x.id == probe.id), None)
            if r is None:
                continue
            scores.append(r.score)
            for f in all_facts:
                hit_rates[f].append(f in r.hits)
        aggregate[probe.id] = {
            "score_sum": sum(scores),
            "score_max": max(scores) if scores else 0,
            "score_min": min(scores) if scores else 0,
            "hit_rates": hit_rates,
        }
    return aggregate


def main(argv: list[str]) -> int:
    """Run all quality probes."""
    args = parse_args(argv)
    if args.compare_context and args.no_context:
        print("ERROR: --compare-context and --no-context are mutually exclusive", file=sys.stderr)
        return 2
    if args.delta_context and (args.compare_context or args.no_context):
        print(
            "ERROR: --delta-context cannot be combined with --compare-context or --no-context",
            file=sys.stderr,
        )
        return 2

    # --probe with --delta-context is disallowed
    if args.probe and args.delta_context:
        print(
            "ERROR: --probe cannot be combined with --delta-context",
            file=sys.stderr,
        )
        return 2

    # --repeat validation
    if args.repeat < 1:
        print("ERROR: --repeat must be >= 1", file=sys.stderr)
        return 2
    if args.repeat > 1 and args.delta_context:
        print(
            "ERROR: --repeat cannot be combined with --delta-context",
            file=sys.stderr,
        )
        return 2
    if args.repeat > 1 and args.compare_context:
        print(
            "ERROR: --repeat cannot be combined with --compare-context",
            file=sys.stderr,
        )
        return 2

    # Resolve probe selection (may raise ValueError for unknown ids)
    try:
        selected_probes = _resolve_probes(args.probe)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    use_intent_overrides = not args.no_intent_overrides
    context_enabled = not args.no_context
    repeat_count = args.repeat

    # Warn when a configured reasoning model is run with a low completion budget.
    # This warning goes to stderr and does not affect exit code or JSON stdout.
    _warn_low_reasoning_budget(
        args.model,
        args.max_tokens,
        reasoning_models=_configured_reasoning_models(args.reasoning_model),
        min_tokens=args.reasoning_min_tokens,
    )

    if args.delta_context:
        delta_result = run_delta_context_probe(
            DELTA_CONTEXT_PROBE,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=use_intent_overrides,
            session_log_path=args.session_log_path,
        )
        if args.json:
            print(json.dumps({
                "id": delta_result.id,
                "ok": delta_result.ok,
                "first": delta_result.first.__dict__ if delta_result.first else None,
                "followup": (
                    delta_result.followup.__dict__
                    if delta_result.followup
                    else None
                ),
                "first_context": delta_result.first_context,
                "followup_context": delta_result.followup_context,
                "error": delta_result.error,
            }, indent=2))
        else:
            print("\n" + "=" * 100)
            print("DELTA CONTEXT")
            print("-" * 100)
            print(f"id: {delta_result.id}")
            print(f"ok: {delta_result.ok}")
            first_score = (
                f"{delta_result.first.score}/{delta_result.first.maximum}"
                if delta_result.first
                else "-"
            )
            followup_score = (
                f"{delta_result.followup.score}/{delta_result.followup.maximum}"
                if delta_result.followup
                else "-"
            )
            print(f"first score: {first_score}")
            print(f"followup score: {followup_score}")
            print(
                "followup symbols_suppressed: "
                f"{delta_result.followup_context.get('symbols_suppressed', 0)}"
            )
            if delta_result.error:
                print(f"error: {delta_result.error}")
            print("=" * 100)
        return 0 if delta_result.ok else 1

    if args.compare_context:
        context_results = _run_probe_set(
            selected_probes,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=use_intent_overrides,
            context_enabled=True,
        )
        no_context_results = _run_probe_set(
            selected_probes,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=use_intent_overrides,
            context_enabled=False,
        )

        if args.json:
            print(json.dumps({
                "context": [result.__dict__ for result in context_results],
                "no_context": [result.__dict__ for result in no_context_results],
            }, indent=2))
        else:
            print_comparison_table(context_results, no_context_results)
            if args.verbose:
                print("\nWITH CONTEXT")
                print_verbose(context_results)
                print("\nWITHOUT CONTEXT")
                print_verbose(no_context_results)

        all_results = context_results + no_context_results
        if any(result.error for result in all_results):
            return 1
        if args.fail_under:
            total_score = sum(result.score for result in context_results)
            if total_score < args.fail_under:
                return 1
        return 0

    # Normal probe runs (with optional --repeat)
    if repeat_count > 1:
        all_runs: list[list[QualityResult]] = []
        for _ in range(repeat_count):
            run_results = _run_probe_set(
                selected_probes,
                base_url=args.base_url,
                model=args.model,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                use_intent_overrides=use_intent_overrides,
                context_enabled=context_enabled,
            )
            all_runs.append(run_results)

        if args.json:
            aggregate = _aggregate_repeat_runs(selected_probes, all_runs)
            print(json.dumps({
                "repeat": repeat_count,
                "runs": [[r.__dict__ for r in run] for run in all_runs],
                "aggregate": aggregate,
            }, indent=2))
        else:
            for run_idx, run_results in enumerate(all_runs, 1):
                print(f"\nRUN {run_idx}/{repeat_count}")
                print_table(run_results)
                if args.verbose:
                    print_verbose(run_results)
            # Compact aggregate summary
            aggregate = _aggregate_repeat_runs(selected_probes, all_runs)
            print("\nAGGREGATE")
            print("=" * 80)
            for probe in selected_probes:
                agg = aggregate.get(probe.id, {})
                rates = ", ".join(
                    f"{f}: {sum(v)}/{repeat_count}"
                    for f, v in agg.get("hit_rates", {}).items()
                )
                print(
                    f"{probe.id}: sum={agg.get('score_sum', 0)}  "
                    f"max={agg.get('score_max', 0)}  "
                    f"min={agg.get('score_min', 0)}  "
                    f"{rates}"
                )
            print("=" * 80)

        check_results = all_runs[-1] if all_runs else []
    else:
        # Single run (default behavior, with probe selection)
        results = _run_probe_set(
            selected_probes,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=use_intent_overrides,
            context_enabled=context_enabled,
        )

        if args.json:
            print(json.dumps([result.__dict__ for result in results], indent=2))
        else:
            print_table(results)
            if args.verbose:
                print_verbose(results)

        check_results = results

    total_score = sum(result.score for result in check_results)
    if args.fail_under and total_score < args.fail_under:
        return 1
    if repeat_count > 1:
        if any(r.error for run in all_runs for r in run):
            return 1
    else:
        if any(result.error for result in check_results):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
