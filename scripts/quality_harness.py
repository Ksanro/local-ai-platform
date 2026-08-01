r"""Live gateway quality smoke test for repository-aware answers.

Runs a fixed set of low-token prompts against the OpenAI-compatible gateway
and scores each answer by deterministic expected fact matches.

Usage
-----

.. code-block:: powershell

    .\uv.exe run python scripts\quality_harness.py
    .\uv.exe run python scripts\quality_harness.py --verbose
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
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_MODEL = "qwen36"
DEFAULT_MAX_TOKENS = 400
QUALITY_SYSTEM_PROMPT = (
    "Answer only with the requested repository facts. "
    "Do not include reasoning, analysis, or step-by-step text."
)


@dataclass(frozen=True)
class ExpectedFact:
    """A required fact with acceptable textual variants."""

    label: str
    variants: tuple[str, ...]


def fact(label: str, *variants: str) -> ExpectedFact:
    """Create an expected fact from a canonical label and optional aliases."""
    return ExpectedFact(label=label, variants=(label, *variants))


@dataclass(frozen=True)
class QualityProbe:
    """A fixed quality prompt with deterministic expected answer facts."""

    id: str
    intent: str
    prompt: str
    expect: tuple[ExpectedFact, ...]


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
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat completion payload for a probe."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
            {"role": "user", "content": probe.prompt},
        ],
        "stream": False,
        "temperature": 0.0,
        "max_tokens": max_tokens,
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
) -> QualityResult:
    """Run one quality probe against the live gateway."""
    result = QualityResult(id=probe.id, intent=probe.intent)
    payload = build_payload(
        probe,
        model=model,
        max_tokens=max_tokens,
        use_intent_overrides=use_intent_overrides,
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
    return result


def print_table(results: list[QualityResult]) -> None:
    """Print a compact quality table."""
    print("\n" + "=" * 100)
    print(
        f"{'id':<28}{'intent':<11}{'score':>8}{'ptok':>9}"
        f"{'ctok':>8}{'sec':>8}  misses"
    )
    print("-" * 100)
    total_score = 0
    total_max = 0
    for result in results:
        total_score += result.score
        total_max += result.maximum
        score = f"{result.score}/{result.maximum}"
        misses = ", ".join(result.misses) if result.misses else "-"
        if result.error:
            misses = result.error
        print(
            f"{result.id:<28}{result.intent:<11}{score:>8}{result.prompt_tokens:>9}"
            f"{result.completion_tokens:>8}{result.seconds:>8.1f}  {misses[:40]}"
        )
    print("-" * 100)
    print(f"{'TOTAL':<39}{f'{total_score}/{total_max}':>8}")
    print("=" * 100)


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
        "--no-intent-overrides",
        action="store_true",
        help="let the gateway detect intent instead of sending context_intent",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Run all quality probes."""
    args = parse_args(argv)
    results = [
        run_probe(
            probe,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            use_intent_overrides=not args.no_intent_overrides,
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
