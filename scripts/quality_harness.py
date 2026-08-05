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
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_MODEL = "qwen36"
DEFAULT_MAX_TOKENS = 400
QUALITY_SYSTEM_PROMPT = (
    "Answer only with the requested repository facts. "
    "Do not include reasoning, analysis, or step-by-step text."
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
    in `history` are fixed canned text, not model output — only the final
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
            "its file, and the env var used to force a specific token budget "
            "instead of deriving one from the model's context window."
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
    id="delta_answer_preview_followup",
    first=QualityProbe(
        id="delta_answer_preview_primer",
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
    followup=QualityProbe(
        id="delta_answer_preview_followup",
        intent="DEBUG",
        prompt=(
            "For the same answer_preview extraction area, name the helper that "
            "reads streaming chunks and the OpenAI streaming field it should read."
        ),
        expect=(
            fact("_choice_content"),
            fact("delta.content", "delta", 'delta.get("content"'),
            fact("apps/gateway/session_log.py", "apps/gateway/session_log"),
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

    records = _read_session_log_records(session_log_path, offset=offset)
    first_record = _record_for_last_user(records, probe.first.prompt)
    followup_record = _record_for_last_user(records, probe.followup.prompt)
    result.first_context = first_record.get("context", {}) if first_record else {}
    result.followup_context = (
        followup_record.get("context", {}) if followup_record else {}
    )

    if not first_record or not followup_record:
        result.error = "session_log_records_not_found"
        return result

    result.ok = (
        first.score == first.maximum
        and followup.score == followup.maximum
        and int(result.followup_context.get("symbols_suppressed", 0) or 0) > 0
    )
    return result


def print_table(results: list[QualityResult]) -> None:
    """Print a compact quality table."""
    print("\n" + "=" * 100)
    print(
        f"{'id':<28}{'intent':<11}{'score':>8}{'style':>8}{'ptok':>9}"
        f"{'ctok':>8}{'sec':>8}  misses"
    )
    print("-" * 100)
    total_score = 0
    total_max = 0
    for result in results:
        total_score += result.score
        total_max += result.maximum
        score = f"{result.score}/{result.maximum}"
        style = "ok" if result.style_ok else "bad"
        misses = ", ".join(result.misses) if result.misses else "-"
        if result.error:
            misses = result.error
        print(
            f"{result.id:<28}{result.intent:<11}{score:>8}{style:>8}"
            f"{result.prompt_tokens:>9}{result.completion_tokens:>8}"
            f"{result.seconds:>8.1f}  {misses[:40]}"
        )
    print("-" * 100)
    print(f"{'TOTAL':<39}{f'{total_score}/{total_max}':>8}")
    print("=" * 100)


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
    return parser.parse_args(argv)


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

    use_intent_overrides = not args.no_intent_overrides
    context_enabled = not args.no_context

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
        context_results = [
            run_probe(
                probe,
                base_url=args.base_url,
                model=args.model,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                use_intent_overrides=use_intent_overrides,
                context_enabled=True,
            )
            for probe in PROBES
        ]
        no_context_results = [
            run_probe(
                probe,
                base_url=args.base_url,
                model=args.model,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                use_intent_overrides=use_intent_overrides,
                context_enabled=False,
            )
            for probe in PROBES
        ]

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

    results = [
        run_probe(
            probe,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=use_intent_overrides,
            context_enabled=context_enabled,
        )
        for probe in PROBES
    ]

    if args.json:
        print(json.dumps([result.__dict__ for result in results], indent=2))
    else:
        print_table(results)
        if args.verbose:
            print_verbose(results)

    total_score = sum(result.score for result in results)
    if args.fail_under and total_score < args.fail_under:
        return 1
    if any(result.error for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
