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
    .\uv.exe run python scripts\quality_harness.py --changed-file-probe
    .\uv.exe run python scripts\quality_harness.py --changed-file-probe --changed-file-weight 5
    .\uv.exe run python scripts\quality_harness.py --changed-file-sweep
    .\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_contextbuilder
    .\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_repository_index
    .\uv.exe run python scripts\quality_harness.py --probe explain_changed_files_history_cap

Run any of the last three with `--repeat 3` against two gateways configured
differently - `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED` off on one, on on the
other, over the same working tree, and over a tree in which the pair's own module is the
only dirty indexed module either gateway can see.  A benefit claim needs that isolation,
because the flag is global: over a workspace with eighteen dirty indexed modules the
enabled arm takes the bonus across eighteen, not across the one under test, and a
detached worktree of the commit - add it, mark the pair's file, remove it afterwards - is
how it was obtained.  A worktree has no `.env`, so every setting has to be given to the
process, `REQUEST_TIMEOUT=300` among them: the provider layer aborts a backend call at
its own default 60 s and the arm would otherwise record an HTTP 503 where it meant to
measure an answer.  The `--changed-file-*` modes above are the
offline retrieval diagnostics for the same decisions.  Each pair - offline case and
scored probe - asks one identical prompt and checks one identical set of facts, held
in the shared constants (`CONTEXT_BUILDER_BUDGET_QUERY`, `REPOSITORY_INDEX_BUILD_QUERY`,
`HISTORY_CAP_QUERY`) and enumerated in `CHANGED_FILE_AB_PAIRS`, because two
arms that ask different questions measure different retrievals and no answer
difference can be attributed to the bonus; an answer-quality claim needs the live
scored run.  `explain_changed_files_history_cap` is the pair the opt-in is offered for:
its offline case measures facts the changed arm can support and the other arm cannot,
with nothing given up, so the two arms differ by the gain alone.
`explain_changed_files_repository_index` is the pair whose offline case measures a
context the changed arm cannot support - the cost side, which is why the opt-in is off
by default; `explain_changed_files_contextbuilder` is the negative control, where
retrieval moves and nothing is lost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The offline probes below import platform packages; a script run as
# `python scripts\quality_harness.py` has `scripts/` on sys.path, not the root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_MODEL = os.environ.get("APP_DEFAULT_MODEL") or os.environ.get(
    "DEFAULT_MODEL", "default-model"
)
DEFAULT_MAX_TOKENS = 400
DEFAULT_REASONING_MIN_TOKENS = 2048
DEFAULT_TIMEOUT = 120.0
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


#: The retrieval reorder case, kept in a constant so the offline diagnostic
#: (``CHANGED_FILE_PROBES`` id ``named_in_query``) and the scored live probe
#: (``PROBES`` id ``explain_changed_files_contextbuilder``) ask the same question.
#: This pair is reported as **context-neutral**: the bonus moves the primary, and
#: every fact below is still in the text of both arms, so it cannot separate two
#: answers.  It is registered because an A/B that shows nothing must be able to
#: show nothing for the right reason; the pair that can discriminate is
#: ``REPOSITORY_INDEX_BUILD_QUERY`` below.
CONTEXT_BUILDER_BUDGET_QUERY = "How does ContextBuilder enforce the token budget?"
CONTEXT_BUILDER_BUDGET_FACTS: tuple[ExpectedFact, ...] = (
    fact("ContextBuilder"),
    fact("_enforce_budget"),
    fact("packages/context/builder.py", "packages/context/builder"),
)

#: The pair that can discriminate, and the one the live A/B is run with.  The
#: prompt asks about one file and injects a second as locally modified, and the
#: facts are the ones only the asked-about file can support.  Measured offline on
#: this repository's index at the configured 4096-token budget: with the bonus off
#: the context sends 14 symbols from both files and all three facts reach the
#: prompt; with `packages/repository/index/models` dirty at the shipped `+25` it
#: sent 10 symbols from one file, because the whole of
#: `packages/repository/index/builder.py` was evicted and none of the three
#: survived.  That is what the Phase B1 promotion guard in
#: `packages/context/ranking.py` changed: the builder's best symbol is restored to
#: the supporting slot the preview budget is spent on, so the primary still moves
#: and the three facts now reach both arms.  The query, the injected module and the
#: facts are constants because the offline diagnostic (``CHANGED_FILE_PROBES``
#: id ``evicts_the_asked_about_file``) and the scored live probe (``PROBES`` id
#: ``explain_changed_files_repository_index``) have to be measuring the same
#: retrieval: an A/B whose arms ask different questions cannot attribute an answer
#: difference to the ranking bonus, which is the flaw that made the first version of
#: this comparison uninterpretable.
REPOSITORY_INDEX_BUILD_QUERY = (
    "How does the repository index builder construct the index, including its "
    "collaborators for files and models?"
)
REPOSITORY_INDEX_BUILD_DIRTY_MODULE = "packages/repository/index/models"
REPOSITORY_INDEX_BUILD_TARGET_MODULE = "packages/repository/index/builder"
REPOSITORY_INDEX_BUILD_FACTS: tuple[ExpectedFact, ...] = (
    fact("PythonAstExtractor"),
    fact("RelationshipRegistry"),
    fact("CallExtractor"),
)

#: The benefit-side pair, and the mirror of the eviction case.  The eviction case
#: dirties a file the prompt never mentions and watches the asked-about file leave the
#: prompt; this one dirties the file the prompt *is* about, and asks the ranking to do
#: what the opt-in is offered for.  The prompt is prose and names no symbol, so nothing
#: in it hands the dirty module the primary: `history` and `gateway` reach the relevance
#: gate as segments of `packages/pipeline/history`, the same path token the
#: `path_token_gate` case records as the gate's behaviour.  Measured offline on this
#: repository's index at the configured 4096-token budget: with the bonus off the token
#: `model` name-matches `apps/gateway/api/models.list_models`, takes the primary, and 20
#: symbols from ten modules are sent - two of them from `packages/pipeline/history`, and
#: neither is `cap_history`, so the only place the four facts below reach the prompt is
#: the call sites in the pipeline stages: that arm can say history is capped without
#: saying how.  With the file dirty at the shipped `+25` the budget buys it instead: 7
#: symbols, 6 of them from the changed file, `changed_symbols_promoted` 4 and
#: `changed_primary_promoted` True.  The four newly sent symbols are the cap's own
#: definitions - `cap_history`, `_build_cap_groups`, `_cap_current_tool_result`,
#: `_estimate_tokens` - and with them the other three facts, the per-message budget, the
#: envelope detector and the truncation marker, are in the text.  Nothing the off arm had
#: is lost, so `facts_lost` is empty.  This is the case where the bonus adds an answer
#: rather than moving one, and the pair whose two arms can separate.  The verdict names it
#: MOVE because the primary does move, into the changed file; the symbol counts say 20
#: became 7, and the facts line says what the difference is worth.
HISTORY_CAP_QUERY = (
    "How does the gateway cap conversation history before sending it to the model?"
)
#: The index module key the stage matches a dirty symbol against, so this is the form
#: both arms take: offline the case injects it directly, and a live working tree dirties
#: `packages/pipeline/history.py`, whose symbols the index files under this key.
HISTORY_CAP_DIRTY_MODULE = "packages/pipeline/history"
HISTORY_CAP_PRIMARY = "apps/gateway/api/models.list_models"
#: The primary the changed arm reaches: `find` inside `_build_cap_groups`, the first
#: symbol of the changed file in the stage's own order.  The module test is the claim;
#: pinning the whole name keeps this honest if the bonus ever stops reaching the file.
HISTORY_CAP_CHANGED_PRIMARY = "packages/pipeline/history._build_cap_groups.find"
HISTORY_CAP_FACTS: tuple[ExpectedFact, ...] = (
    fact("cap_history"),
    fact("max_current_tool_result_tokens"),
    fact("_looks_like_cline_tool_result_message"),
    fact("[... truncated by gateway history cap ...]", "truncated by gateway history cap"),
)


#: The offline case and the scored probe of each changed-file A/B, paired by id.
#: Both halves of a pair must ask one question and check one set of facts, and a
#: test walks this table rather than the two registries separately, so a case can
#: not be added on one side and forgotten on the other.
CHANGED_FILE_AB_PAIRS: tuple[tuple[str, str], ...] = (
    ("named_in_query", "explain_changed_files_contextbuilder"),
    ("evicts_the_asked_about_file", "explain_changed_files_repository_index"),
    ("gains_the_changed_file", "explain_changed_files_history_cap"),
)

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
            "Which lowest-level helper reads the streamed text out of a choice, "
            "and which OpenAI streaming field does that helper read? Name the "
            "helper symbol and give the full module path of the implementation "
            "file so I can open it. Answer concisely. No preamble."
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
    QualityProbe(
        # The context-neutral half of the changed-file decision: this pair is the
        # negative control.  Run it with `--repeat 3` against a gateway started with
        # `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false` and one started with
        # it `true`, over a working tree that has `packages/context/budget.py`
        # dirty - the condition the offline `named_in_query` case measures, and at
        # the shipped `+25` it does report a swap: `ContextBudget` takes the
        # primary.  What the measurement below showed is that the swap costs
        # nothing.  `ContextBuilder`, `_enforce_budget` and
        # `packages/context/builder.py` are all in the text of both arms (the
        # builder symbols simply drop from positions 0-2 to 2-4 of five), so an
        # answer built on the changed context can still be perfectly correct.
        # Expect the two arms to score the same here.  They do not in
        # `explain_changed_files_repository_index`, and that contrast - one pair
        # where retrieval moves and the answer cannot follow, one where a file
        # leaves the prompt entirely - is what makes the positive result mean
        # something.
        id="explain_changed_files_contextbuilder",
        intent="EXPLAIN",
        prompt=CONTEXT_BUILDER_BUDGET_QUERY,
        expect=CONTEXT_BUILDER_BUDGET_FACTS,
    ),
    QualityProbe(
        # The scored half of the eviction case below, and the measurement the
        # changed-file decision actually turns on.  Run it with `--repeat 3` against
        # a gateway started with
        # `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false` and one started with it
        # `true`, over a working tree that has ``packages/repository/index/models.py``
        # dirty.  Both arms are sent the identical prompt - this probe's text is the
        # same constant the offline case runs - so a score difference is attributable
        # to the bonus and to nothing else.  With the bonus at zero the context carries
        # ``packages/repository/index/builder.py``; with it on, the dirty module's
        # symbols take the budget and the builder file is not in the prompt at all, so
        # all three implementation collaborators have to come from the model's own
        # knowledge of a file it was never shown.  Measured live on 2026-10-12 that is
        # what happened: feature off scored 3/3 on each of three repeats, feature on
        # 0/3 on each of three, 11 symbols sent with the flag off against 8 with it on.
        # Per-repeat numbers, counters and the confounds that belong to the run are in
        # `docs/live-gateway-runbook.md`.
        id="explain_changed_files_repository_index",
        intent="EXPLAIN",
        prompt=REPOSITORY_INDEX_BUILD_QUERY,
        expect=REPOSITORY_INDEX_BUILD_FACTS,
    ),
    QualityProbe(
        # The scored half of the benefit case `gains_the_changed_file`, and the pair
        # the changed-file opt-in is meant to win.  Run it with `--repeat 3` against a
        # gateway started with `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=false` and
        # one started with it `true`, over a working tree whose only modified file is
        # `packages/pipeline/history.py`.  Both arms are sent this identical prompt, so
        # a score difference belongs to the bonus alone.  With the bonus off the
        # question's token `model` hands the primary to a models-listing endpoint and
        # the prompt carries `cap_history` only where it is called; with the bonus on,
        # the file under edit is what the budget buys, and the mechanism -
        # `max_current_tool_result_tokens`, `_looks_like_cline_tool_result_message` and
        # the truncation marker - is in front of the model.  Measured offline on the
        # checked-out index, the arm with the flag off can be answered from 1 fact of the
        # 4 and the arm with it on from all 4, so the two prompts are not equal in what
        # they let a model say.  This is the case that answers the question the negative
        # control cannot: whether the signal ever helps an answer.
        id="explain_changed_files_history_cap",
        intent="EXPLAIN",
        prompt=HISTORY_CAP_QUERY,
        expect=HISTORY_CAP_FACTS,
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


def _warn_default_timeout_for_reasoning_model(
    model: str,
    timeout: float,
    *,
    reasoning_models: tuple[str, ...],
) -> None:
    """Emit a one-per-invocation stderr hint for reasoning models on the default timeout.

    No-context probes on reasoning-heavy models can exceed the default
    per-probe timeout; the hint suggests raising both the harness client
    timeout and the gateway/provider REQUEST_TIMEOUT. Does not change the
    effective timeout or exit code. Output goes to stderr so it cannot
    contaminate machine-readable JSON stdout.
    """
    if not any(model.lower() == configured.lower() for configured in reasoning_models):
        return
    if timeout != DEFAULT_TIMEOUT:
        return
    print(
        f"WARN: model {model!r} is configured as reasoning-heavy but uses the "
        f"default per-probe timeout of {DEFAULT_TIMEOUT:g}s. No-context probes "
        f"can exceed it; consider --timeout 300 plus a matching gateway "
        f"REQUEST_TIMEOUT=300 in .env (restart the gateway after changing "
        f".env).",
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
        if isinstance(exc, TimeoutError):
            result.error = (
                f"TimeoutError: timed out after {timeout}s "
                f"(harness client timeout; gateway/backend may still be generating)"
            )
            result.metadata["timed_out"] = True
            result.metadata["timeout_seconds"] = timeout
        else:
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


def _comparison_score_cell(result: QualityResult) -> str:
    """Return the score cell for one arm of the comparison table.

    Errored probes render as ERR so a timeout does not read like a normal
    0/0 comparison result.
    """
    if result.error:
        return "ERR"
    return f"{result.score}/{result.maximum}"


def print_comparison_table(
    context_results: list[QualityResult],
    no_context_results: list[QualityResult],
) -> None:
    """Print a side-by-side context-on/context-off quality table.

    When an arm errors, its score cell shows ERR, that probe's delta is
    marked invalid with ``*``, and an ``ERRORS:`` footer lists every arm
    error. Clean comparisons print without the extra lines.
    """
    print("\n" + "=" * 110)
    print(
        f"{'id':<28}{'intent':<11}{'ctx':>8}{'raw':>8}"
        f"{'dscore':>8}{'ptok ctx':>10}{'ptok raw':>10}{'sec ctx':>9}{'sec raw':>9}"
    )
    print("-" * 110)

    total_ctx = 0
    total_raw = 0
    total_max = 0
    errors: list[str] = []
    for ctx, raw in zip(context_results, no_context_results, strict=True):
        total_ctx += ctx.score
        total_raw += raw.score
        total_max += ctx.maximum
        if ctx.error:
            errors.append(f"context:{ctx.id} -> {ctx.error}")
        if raw.error:
            errors.append(f"no_context:{raw.id} -> {raw.error}")
        delta = ctx.score - raw.score
        delta_cell = f"{delta:>7}*" if ctx.error or raw.error else f"{delta:>8}"
        print(
            f"{ctx.id:<28}{ctx.intent:<11}"
            f"{_comparison_score_cell(ctx):>8}"
            f"{_comparison_score_cell(raw):>8}"
            f"{delta_cell}"
            f"{ctx.prompt_tokens:>10}{raw.prompt_tokens:>10}"
            f"{ctx.seconds:>9.1f}{raw.seconds:>9.1f}"
        )

    print("-" * 110)
    print(
        f"{'TOTAL':<39}{total_ctx:>4}/{total_max:<3}"
        f"{total_raw:>4}/{total_max:<3}{total_ctx - total_raw:>8}"
    )
    if errors:
        print(
            "* delta invalid: an arm errored; the other arm remains a valid "
            "standalone result"
        )
        print("ERRORS:")
        for line in errors:
            print(f"  {line}")
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

# ---------------------------------------------------------------------------
# Changed-file ranking probes (deterministic: no gateway, no model, no tokens)
#
# ``repository_context_changed_files_enabled`` is off by default and unresolved,
# which makes the opt-in a guess rather than a measurement.  These probes answer
# the question the ranking arithmetic cannot: does the bonus change the context a
# request would send, and can it take the primary away from the symbol the query
# named?  Each probe runs the real ``RepositoryContextStage`` twice over an index
# built from this checkout - once with no changed-module source, once with one
# module injected as dirty - and reads the stage's own counterfactual fields, so
# the verdict is the measurement the session log reports rather than a
# re-derivation of it.  Nothing here touches Git: the dirty module is injected, so
# the working tree is irrelevant and a clean checkout measures the same thing.
#
# Two terms are kept apart on purpose, because they are not the same condition:
#
# * **name match** - some segment of the qualified name equals a query token
#   (``packages/context/scoring.py``, ``EXACT_SYMBOL_NAME``).  The segments
#   include the module-path segments, so ``packages/context/builder``
#   ``.ContextBuilder`` name-matches the token ``builder`` without the prompt
#   having named anything.
# * **named in the query** - the query text contains the symbol's own name, e.g.
#   ``ContextBuilder``.  This is the case a working-tree bonus has no business
#   losing, and ``ChangedFileProbe.named_in_query`` is how a probe says it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedFileProbe:
    """A retrieval case in which one module is injected as locally modified.

    ``expected_primary`` is the symbol that must stay first in the arm where
    ``dirty_module`` is dirty; ``expected_changed_primary``, when it is set, is the
    symbol that must be first in that arm instead, on a case whose claim is that the
    bonus moves the primary into the changed file.  ``names_primary`` is what the author
    of the case claims about it - the stricter **named in the query** rather than the weaker
    **name match** - and ``named_in_query()`` below is the check on that claim, so
    a probe cannot quietly assert a preference its own query text does not
    support.  A ``False`` case documents an effect; it does not claim the ranking
    rules grant a preference.  ``dirty_module`` is never read from Git, so the
    case measures the same way on any checkout.  ``facts`` are the facts the scored
    live probe will ask the same question about: they are checked for availability
    in the text each arm would have sent, so an outcome reports what the bonus cost
    in context rather than only where it moved the primary.
    """

    id: str
    query: str
    dirty_module: str
    expected_primary: str
    # Set on a case whose claim is that the bonus *moves* the primary - the gain
    # cases - and empty on the survival cases, where both arms must keep the same
    # first symbol.  A case that documents a move cannot be judged by the survival
    # rule: it would fail for showing exactly the effect it was written to show.
    expected_changed_primary: str = ""
    names_primary: bool = False

    facts: tuple[ExpectedFact, ...] = ()
    note: str = ""

    def named_in_query(self) -> bool:
        """Whether this query text contains the expected primary's own name.

        The stricter of the two terms, and the check on ``names_primary``: the
        module path and the module stem are dropped, so only the symbol's own name
        and the names it is nested in are looked for.  ``packages/context/
        builder.ContextBuilder`` is named by a prompt that says ``ContextBuilder``
        and is merely **name matched** by one that says ``context builder``,
        because ``EXACT_SYMBOL_NAME`` also reads the module-path segments.
        """
        own = self.expected_primary.rsplit("/", 1)[-1].split(".")
        parts = own[1:] if len(own) > 1 else own
        return any(part.lower() in self.query.lower() for part in parts if part)


@dataclass
class ChangedFileOutcome:
    """What one changed-file probe measured, bonus off then on.

    The four ``changed_*`` fields are the stage's own counterfactual counters,
    copied out of ``PipelineStageResult.data``.  There is deliberately no set
    difference in here: a flat bonus reorders, and ``len(set(new) - set(old))``
    cannot see a reorder, which is why the stage compares the composed packages.

    The ``*_facts`` fields measure something the counters cannot: which of the
    probe's facts appear in the text each arm would have sent to a model.  A bonus
    can leave every symbol of a case's expected primary intact and still cost a
    whole file's context, and that is the difference a changed-file A/B is meant to
    detect, so it is reported next to the counters rather than inferred from them.

    ``ok`` is the case's own claim, and a claim comes in two shapes: on a survival
    case both arms must lead with ``expected_primary``, and on a gain case the arm with
    the dirty module must lead with ``expected_changed_primary`` instead.  Judging a
    move by the rule that fits a hold would fail a case for showing the effect it was
    written to show.
    """

    id: str
    ok: bool = False
    expected_primary: str = ""
    # What the arm with the dirty module was expected to lead with.  Equal to
    # `expected_primary` on a survival case, different on a gain case, and never left
    # blank here: the table and the session record both print the two primaries, and a
    # reader has to be able to tell "moved as claimed" from "moved somewhere".
    expected_changed_primary: str = ""
    dirty_module: str = ""
    weight: int = 0
    names_primary: bool = False
    baseline_primary: str = ""
    changed_primary: str = ""
    baseline_symbols: int = 0
    changed_symbols: int = 0
    max_context_tokens: int = 0
    context_differs: bool = False
    primary_promoted: bool = False
    symbols_promoted: int = 0
    baseline_facts: tuple[str, ...] = ()
    changed_facts: tuple[str, ...] = ()
    facts_lost: tuple[str, ...] = ()
    baseline_status: str = ""
    error: str = ""


CHANGED_FILE_PROBES: tuple[ChangedFileProbe, ...] = (
    ChangedFileProbe(
        id="named_in_query",
        query=CONTEXT_BUILDER_BUDGET_QUERY,
        dirty_module="packages/context/budget",
        expected_primary="packages/context/builder.ContextBuilder._enforce_budget",
        names_primary=True,
        facts=CONTEXT_BUILDER_BUDGET_FACTS,
        note=(
            "The query contains the name ContextBuilder, and the injected file "
            "genuinely competes - ContextBudget name-matches the token 'budget'. "
            "Measured here: the named symbol holds at +5 (nothing differs at all), "
            "the supporting symbols differ from +10 with the primary held, and "
            "ContextBudget takes the primary from +15, because it sits 15 points "
            "behind and sorts first on the tie-break. So +25 loses the case the "
            "constant is supposed to protect and +5 does not. What this case cannot "
            "do is stand in for an answer claim: at every weight from +10 up, the "
            "three facts stay available in both arms, because the bonus adds the "
            "budget file's two symbols in front of the builder file's three rather "
            "than replacing them. The primary moves and the context needed to answer "
            "does not, so probe explain_changed_files_contextbuilder is a negative "
            "control - both arms should score 3/3 - and never the evidence that the "
            "bonus costs an answer anything."
        ),
    ),
    ChangedFileProbe(
        id="path_token_gate",
        query="how does model resolution pick a backend",
        dirty_module="packages/repository/index/models",
        expected_primary="packages/pipeline/stages/model_resolution.ModelResolutionStage",
        names_primary=False,
        note=(
            "A known effect of the relevance gate, recorded rather than fixed. "
            "The token 'model' is a segment of the injected module path, so every "
            "symbol in that file clears the gate and the bonus moves a dozen of "
            "them into the sent set: changed_symbols_promoted is 12 at +5 and +10 "
            "and 13 at +25, with the primary unchanged at every weight. The size "
            "of the weight is not what changes the context here - the gate is, and "
            "shrinking the bonus to +5 does not undo it."
        ),
    ),
    ChangedFileProbe(
        id="evicts_the_asked_about_file",
        query=REPOSITORY_INDEX_BUILD_QUERY,
        dirty_module=REPOSITORY_INDEX_BUILD_DIRTY_MODULE,
        expected_primary="packages/repository/index/builder.RepositoryIndexBuilder",
        names_primary=False,
        facts=REPOSITORY_INDEX_BUILD_FACTS,
        note=(

            "The case the size of the bonus is not about, and the one the live A/B "
            "runs on. The prompt asks how the index builder constructs the index and "
            "names the models file second, so both files clear the relevance gate on "
            "a path token. At the configured 4096-token budget the bonus lifts the "
            "dirty module's ten symbols to the front of the order - "
            "changed_symbols_promoted is 0, because none of them was absent from the "
            "context before, and changed_primary_promoted is 1 - and 14 symbols "
            "become 10. It used to cost a file: "
            "packages/repository/index/builder.py left the context outright and its "
            "PythonAstExtractor, RelationshipRegistry and CallExtractor collaborators "
            "were available with the bonus off and unavailable with it on, at +1 "
            "exactly as at +25. Since the Phase B1 promotion guard in "
            "packages/context/ranking.py the builder's own best symbol is restored to "
            "the supporting slot the shared preview budget is spent on, so the three "
            "facts stay available on both arms and facts_lost is empty while the "
            "primary still moves. That is the difference between retaining a symbol "
            "and retaining what it contributes: the version of this rule that only "
            "kept a symbol of the file in the list measured 1/3, because past the two "
            "rendered positions a candidate keeps its signature and docstring but "
            "loses its source body or preview, and these are body facts. At 6144 tokens "
            "both arms now send 20 symbols and agree on all three facts. The case is "
            "stated at 4096 - the "
            "stage default, APP_REPOSITORY_CONTEXT_MAX_TOKENS and the EXPLAIN intent "
            "budget this probe asks under, all of which agree. Scored live by probe "
            "explain_changed_files_repository_index, which asks this same prompt and "
            "checks these same facts, and which the guard now expects to tie."
        ),
    ),
    ChangedFileProbe(
        id="gains_the_changed_file",
        query=HISTORY_CAP_QUERY,
        dirty_module=HISTORY_CAP_DIRTY_MODULE,
        expected_primary=HISTORY_CAP_PRIMARY,
        expected_changed_primary=HISTORY_CAP_CHANGED_PRIMARY,
        names_primary=False,
        facts=HISTORY_CAP_FACTS,
        note=(
            "The benefit side, and the mirror of `evicts_the_asked_about_file`: there "
            "the dirty file is one the prompt never mentions and the asked-about file is "
            "what the budget loses; here the dirty file is the file the prompt is about, "
            "and the budget spends itself on it. The prompt is prose and names no symbol, "
            "so the `+25` arrives only through the gate - `history` and `gateway` as path "
            "segments - and not from a name written in the question. Measured at the "
            "configured 4096 tokens: off, 20 symbols from ten modules are sent, led by "
            "`apps/gateway/api/models.list_models` because the token `model` name-matches "
            "it, and two of the twenty come from the changed file without being "
            "`cap_history`, so of the four facts only that one reaches the prompt, and "
            "only at its call sites. On, 7 symbols are sent and 6 of them come from the "
            "changed file: `changed_symbols_promoted` 4, `changed_primary_promoted` True, "
            "and the four newly sent symbols are the cap's own definitions - "
            "`cap_history`, `_build_cap_groups`, `_cap_current_tool_result`, "
            "`_estimate_tokens` - which is where the other three facts live: the "
            "per-message budget, the envelope detector, the `truncated by gateway history "
            "cap` marker. `facts_lost` is empty: the on arm gives up nothing the off arm "
            "had, which is what makes this a gain rather than the swap the other case "
            "measures. The verdict says MOVE, because the primary moves into the changed "
            "file, and a rule that graded that as a failure would grade this case's whole "
            "claim as one; the symbol counts say 20 out, 7 in. The facts line is the "
            "measurement. It is the only pair of the five registered here whose changed "
            "arm can support a fact the baseline arm cannot, so it is the live A/B's "
            "subject: probe `explain_changed_files_history_cap`, which asks this prompt "
            "and checks these facts. Unlike the eviction case this one is "
            "weight-dependent, because the primary is a contest with a name match rather "
            "than a pure gate effect: at +25 the changed file wins it, and the table "
            "prints that weight with the row so a reader can see which bonus the sentence "
            "describes. All of it is measured on the checked-out index by the run, not "
            "asserted from a transcript."
        ),
    ),
    ChangedFileProbe(
        id="dirty_file_the_query_ignores",
        query="Where is cap_history defined?",
        dirty_module="packages/repository/index/models",
        expected_primary="packages/pipeline/history.cap_history",
        names_primary=True,
        note=(
            "A dirty file the prompt never mentioned. Nothing in it carries a "
            "query reason, so no candidate receives the bonus, "
            "changed_baseline_status is 'skipped_no_bonus' and the two arms are "
            "identical by construction at every weight. This is the gate doing "
            "its job, and it is the one changed-file behaviour that is fully "
            "settled."
        ),
    ),
)


def repository_index_settings(repo_root: str | None = None) -> tuple[Path, bool, str]:
    """Return what to index for a changed-file probe: root, test exclusion, globs.

    The gateway's own settings are used when they can be loaded, because a probe
    that ranked a different tree than a request would would be measuring a
    repository nobody queries.  ``repository_path`` is relative to the working
    directory, as the gateway resolves it.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    exclude_tests = False
    exclude_globs = "scripts/**"
    if repo_root is None:
        try:
            from apps.gateway.core.config import get_settings

            settings = get_settings()
            configured = Path(settings.repository_path)
            root = configured if configured.is_absolute() else root / configured
            exclude_tests = settings.repository_exclude_tests
            exclude_globs = settings.repository_exclude_globs
        except Exception as exc:  # noqa: BLE001 - settings are optional here
            print(
                f"note: using default index settings, settings unavailable: {exc}",
                file=sys.stderr,
            )
    return root.resolve(), exclude_tests, exclude_globs


class _InjectedDirtyModule:
    """A changed-module source that answers with what the probe injected.

    The same pattern ``tests/pipeline/test_changed_file_promotion_counts.py``
    uses: the stage sees a real ``ChangedModuleSource``, and no Git command runs
    anywhere near it.
    """

    def __init__(self, modules: frozenset[str]) -> None:
        self._modules = modules

    def module_paths(self) -> frozenset[str]:
        """Return the injected index module keys."""
        return self._modules


def _probe_stage(
    index: Any,
    source: Any,
    *,
    stage_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Build ``RepositoryContextStage`` the way the gateway builds it.

    The budget the probe measures is the budget a request would have used, so it
    comes from the stage's own resolution of the configured values rather than
    from a number written into this file.  When settings cannot be loaded the
    stage's defaults apply, which is the same fallback a bare import has.
    ``stage_kwargs`` overrides that for a caller that must not depend on a
    developer's ``.env`` - the tests, which run the same code path on a fixture
    index.
    """
    from packages.pipeline.stages.repository_context import RepositoryContextStage

    kwargs: dict[str, Any] = {"index": index, "changed_files": source}
    if stage_kwargs is None:
        try:
            from apps.gateway.core.config import get_settings

            settings = get_settings()
            kwargs.update(
                context_delta_injection=settings.context_delta_injection,
                context_delta_cache_size=settings.context_delta_cache_size,
                max_context_tokens=settings.repository_context_max_tokens,
                intent_context_budgets=settings.repository_context_intent_budget_map,
            )
        except Exception as exc:  # noqa: BLE001 - settings are optional here
            print(
                f"note: using stage default budgets, settings unavailable: {exc}",
                file=sys.stderr,
            )
    else:
        kwargs.update(stage_kwargs)
    return RepositoryContextStage(**kwargs)


def _stage_arm(
    index: Any,
    query: str,
    modules: frozenset[str],
    *,
    stage_kwargs: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Send one query through the stage; return (sent symbols, result data).

    Args:
        index: The built ``RepositoryIndex``.
        query: The user turn, as a request would carry it.
        modules: Module keys to inject as locally modified; empty means the
            signal is off, which is the arm a disabled feature runs.

    Returns:
        The symbols the stage actually sent, primary first, and the stage
        result's data - where the promotion counters live.
    """
    import asyncio

    from packages.pipeline.context import PipelineContext

    stage = _probe_stage(
        index, _InjectedDirtyModule(modules) if modules else None, stage_kwargs=stage_kwargs
    )
    context = PipelineContext(
        request_id="changed-file-probe",
        request={"messages": [{"role": "user", "content": query}]},
    )
    result = asyncio.run(stage.execute(context))
    data = dict(result.data or {})
    package = data.get("package")
    sent = [
        name
        for name in ((package.primary_symbol, *package.supporting_symbols) if package else ())
        if name
    ]
    return sent, data


def context_facts_available(
    package: Any,
    query: str,
    facts: tuple[ExpectedFact, ...],
) -> tuple[str, ...]:
    """Which of ``facts`` the context of one arm could actually support.

    The package is serialized into messages the way the gateway serializes it, and
    the same ``score_answer`` matching the live probe uses decides availability.  So
    this is not a claim about what a model would say - it is the objective half of
    that claim: a fact whose text never reaches the prompt cannot be answered from
    the context, in either arm of an A/B.
    """
    if package is None or not facts:
        return ()

    from packages.serializers.openai import OpenAISerializer

    request = OpenAISerializer().serialize(package, [{"role": "user", "content": query}])
    text = "\n".join(str(message.get("content", "")) for message in request.messages)
    hits, _misses = score_answer(text, facts)
    return tuple(hits)


def changed_file_probe_outcome(
    probe: ChangedFileProbe,
    *,
    baseline: list[str],
    changed: list[str],
    promotion: dict[str, Any],
    weight: int,
    max_context_tokens: int = 0,
    baseline_facts: tuple[str, ...] = (),
    changed_facts: tuple[str, ...] = (),
) -> ChangedFileOutcome:
    """Judge one probe from the two arms and the stage's own counters.  Pure.

    Args:
        probe: The case, including the primary that must survive.
        baseline: Symbols sent with the signal off.
        changed: Symbols sent with ``probe.dirty_module`` injected as dirty.
        promotion: The ``changed_*`` fields read off the changed arm's stage
            result - the same fields that land in a session record.
        weight: The ``WEIGHT_CHANGED_FILE`` the changed arm used.
        max_context_tokens: The budget the stage resolved for both arms.
        baseline_facts: Facts available in the context of the arm with the signal
            off, as reported by ``context_facts_available``.
        changed_facts: The same for the arm that ran with the dirty module.

    Returns:
        The outcome.  ``ok`` is ``True`` only when **both** arms sent the symbol that
        case expects of them - ``expected_primary`` for the arm with the signal off,
        and ``expected_changed_primary`` (which is the same symbol on a survival case)
        for the arm that ran dirty.  The rule holds on both arms because an arm that
        was already wrong before the bonus was switched on cannot demonstrate that the
        bonus fixed anything, so a mismatching ``baseline_primary`` fails the case as
        surely as a mismatching ``changed_primary``.  How much else moved is read from
        the stage's counters rather than from a set difference:
        ``len(set(new) - set(old))`` cannot see a reorder, and a flat bonus is mostly a
        reorder.
    """
    changed_expected = probe.expected_changed_primary or probe.expected_primary
    return ChangedFileOutcome(
        id=probe.id,
        ok=(
            bool(baseline)
            and bool(changed)
            and baseline[0] == probe.expected_primary
            and changed[0] == changed_expected
        ),
        expected_primary=probe.expected_primary,
        expected_changed_primary=changed_expected,
        dirty_module=probe.dirty_module,
        weight=weight,
        names_primary=probe.named_in_query(),
        baseline_primary=baseline[0] if baseline else "",
        changed_primary=changed[0] if changed else "",
        baseline_symbols=len(baseline),
        changed_symbols=len(changed),
        max_context_tokens=max_context_tokens,
        context_differs=bool(promotion.get("changed_context_differs", False)),
        primary_promoted=bool(promotion.get("changed_primary_promoted", False)),
        symbols_promoted=int(promotion.get("changed_symbols_promoted", 0) or 0),
        baseline_facts=baseline_facts,
        changed_facts=changed_facts,
        facts_lost=tuple(fact for fact in baseline_facts if fact not in changed_facts),
        baseline_status=str(promotion.get("changed_baseline_status", "") or ""),
    )


def run_changed_file_probe(
    probe: ChangedFileProbe,
    index: Any,
    *,
    weight: int | None = None,
    stage_kwargs: dict[str, Any] | None = None,
) -> ChangedFileOutcome:
    """Run one query through the stage with the signal off, then with a dirty file.

    Args:
        probe: The case to run.
        index: A built ``RepositoryIndex``.  Callers hold it; building one takes
            seconds, and a probe sweep should pay that once.
        weight: Override ``WEIGHT_CHANGED_FILE`` for the run.  Diagnostic only -
            it is how a probe is shown to be sensitive to the number under test,
            and the configured value is restored in a ``finally`` block.
        stage_kwargs: Passed to the stage instead of the configured budget, for a
            caller that must not depend on a developer's ``.env``.

    Returns:
        The measured outcome.  An exception from the stage is reported in
        ``error`` with ``ok`` left ``False``, so one bad case cannot end a sweep.
    """
    from packages.context.ranking_config import RankingConfig

    effective = RankingConfig.WEIGHT_CHANGED_FILE if weight is None else weight
    original = RankingConfig.WEIGHT_CHANGED_FILE
    RankingConfig.WEIGHT_CHANGED_FILE = effective
    try:
        baseline, baseline_data = _stage_arm(
            index, probe.query, frozenset(), stage_kwargs=stage_kwargs
        )
        changed, data = _stage_arm(
            index, probe.query, frozenset({probe.dirty_module}), stage_kwargs=stage_kwargs
        )
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        return ChangedFileOutcome(
            id=probe.id,
            expected_primary=probe.expected_primary,
            expected_changed_primary=probe.expected_changed_primary,
            dirty_module=probe.dirty_module,
            weight=effective,
            names_primary=probe.named_in_query(),
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        RankingConfig.WEIGHT_CHANGED_FILE = original

    if data.get("package") is None:
        return ChangedFileOutcome(
            id=probe.id,
            expected_primary=probe.expected_primary,
            expected_changed_primary=probe.expected_changed_primary,
            dirty_module=probe.dirty_module,
            weight=effective,
            names_primary=probe.named_in_query(),
            error="the stage assembled no context for this query",
        )
    return changed_file_probe_outcome(
        probe,
        baseline=baseline,
        changed=changed,
        promotion=data,
        weight=effective,
        max_context_tokens=int(data.get("max_context_tokens", 0) or 0),
        baseline_facts=context_facts_available(
            baseline_data.get("package"), probe.query, probe.facts
        ),
        changed_facts=context_facts_available(data.get("package"), probe.query, probe.facts),
    )


def resolve_changed_file_case(
    probe_id: str,
    probes: tuple[ChangedFileProbe, ...] = CHANGED_FILE_PROBES,
) -> ChangedFileProbe:
    """Look one offline changed-file case up by id.

    A case and the scored probe that asks its question are two halves of one
    measurement, and the pairing is held by id rather than by adjacency in a tuple,
    so a test or a CLI filter that names a case that does not exist gets this error
    instead of a bare ``StopIteration`` from a generator expression.
    """
    for probe in probes:
        if probe.id == probe_id:
            return probe
    known = ", ".join(sorted(item.id for item in probes))
    raise KeyError(f"unknown changed-file case '{probe_id}'; registered: {known}")


def run_changed_file_probes(
    probes: tuple[ChangedFileProbe, ...],
    index: Any,
    *,
    weight: int | None = None,
    stage_kwargs: dict[str, Any] | None = None,
) -> list[ChangedFileOutcome]:
    """Run each changed-file probe over one shared index."""
    return [
        run_changed_file_probe(probe, index, weight=weight, stage_kwargs=stage_kwargs)
        for probe in probes
    ]


def changed_file_verdict(outcome: ChangedFileOutcome) -> str:
    """One word for what an outcome measured.

    ``HOLD``, ``SWAP`` and ``MOVE`` are all verdicts about the bonus.  ``MOVE`` is the
    gain case's pass: the primary left the arm with the signal off for the symbol the
    case says it must land on, which is the effect that case was written to show, and
    printing it as a HOLD would describe a move as a survival.  ``BAD_BASELINE`` is
    neither: the arm with the signal off did not send the symbol the case says it
    must, so the case does not measure what it claims, and the changed arm agreeing
    proves nothing about the bonus.  It must not be printed as a pass, and printing
    it as a swap would blame the wrong arm.
    """
    if outcome.baseline_primary != outcome.expected_primary:
        return "BAD_BASELINE"
    if outcome.ok:
        if outcome.expected_changed_primary not in ("", outcome.expected_primary):
            return "MOVE"
        return "HOLD"
    return "SWAP"


def print_changed_file_table(outcomes: list[ChangedFileOutcome]) -> None:
    """Render changed-file probe outcomes.

    Symbol names and module keys are printed on purpose: this is an offline
    developer tool that sends no request and writes no session record, so the
    rule that keeps names out of the promotion fields does not apply here.
    """
    print("\n" + "=" * 100)
    print("CHANGED-FILE RANKING (bonus off, then one injected dirty module)")
    print("-" * 100)
    for outcome in outcomes:
        named = "named in query" if outcome.names_primary else "name match only"
        print(
            f"{outcome.id:<28} {changed_file_verdict(outcome):<13}"
            f"weight={outcome.weight:<4} dirty={outcome.dirty_module} [{named}]"
        )
        print(f"{'':<28} off={outcome.baseline_primary or '-'}")
        print(
            f"{'':<28} on ={outcome.changed_primary or '-'} "
            f"budget={outcome.max_context_tokens} "
            f"symbols={outcome.baseline_symbols}->{outcome.changed_symbols}"
        )
        print(
            f"{'':<28} differs={outcome.context_differs} "
            f"primary_promoted={outcome.primary_promoted} "
            f"symbols_promoted={outcome.symbols_promoted} "
            f"baseline_status={outcome.baseline_status or '-'}"
        )
        if outcome.baseline_facts or outcome.changed_facts:
            print(
                f"{'':<28} facts available off={len(outcome.baseline_facts)} "
                f"on={len(outcome.changed_facts)} "
                f"lost={','.join(outcome.facts_lost) or '-'}"
            )
        if outcome.error:
            print(f"{'':<28} error: {outcome.error}")
    print("=" * 100)


@dataclass(frozen=True)
class ChangedFileSweepRow:
    """How much bonus a fixed query needs before another file takes its primary.

    ``flip_weight`` is the smallest nonzero ``WEIGHT_CHANGED_FILE`` that puts a
    symbol from a different module ahead of the query's leader.  It is arithmetic
    rather than a search: a competitor that is exactly as relevant as the leader
    needs only ``+1``, because the documented tie-break then has nothing to fall
    back on, and a competitor ``gap`` points behind needs ``gap`` if it sorts
    before the leader by qualified name (it wins the tie) or ``gap + 1``
    otherwise.
    """

    query: str
    leader: str
    leader_module: str
    leader_score: int
    flip_weight: int
    flip_candidate: str
    flip_gap: int
    ties: int
    relevant: int


#: The fixed sweep set.  It includes the probe queries, and is otherwise made of
#: questions about this repository that name nothing, so the arithmetic is not
#: read only through the cases the probes already assert.
CHANGED_FILE_SWEEP_QUERIES: tuple[str, ...] = (
    "How does ContextBuilder enforce the token budget?",
    "how does model resolution pick a backend",
    "Where is cap_history defined?",
    "what does the session logger middleware record",
    "how are repository index modules built",
    "how does the planning stage choose a ranking profile",
    "what controls the context token budget",
    "how does the gateway write the session log",
    "where is the provider request serialized",
    "how does the chat endpoint map errors to statuses",
    "how are symbols enriched with source data",
    "which helper extracts the last task text",
)


def _tie_break_key(candidate: Any) -> tuple[str, int, str]:
    """The documented tie-break, without the score: name, type, module."""
    from packages.context.ranking_config import RankingConfig

    return (
        candidate.qualified_name,
        -RankingConfig.SYMBOL_TYPE_RANK.get(str(candidate.symbol_type).upper(), 0),
        candidate.module,
    )


def changed_file_flip_weight(leader: Any, competitor: Any) -> int:
    """Smallest bonus that hands ``leader``'s slot to ``competitor``."""
    gap = int(leader.score) - int(competitor.score)
    if gap <= 0:
        return 1
    return gap if _tie_break_key(competitor) < _tie_break_key(leader) else gap + 1


def changed_file_sweep(
    index: Any,
    queries: Sequence[str],
    *,
    max_tokens: int = 4096,
) -> list[ChangedFileSweepRow]:
    """Measure each query's flip weight from one ranking pass, with no bonus on.

    One ranking pass answers the whole "every indexed module dirty in turn"
    question, because the bonus is applied to a single candidate at a time: the
    module that takes the primary cheapest is the one holding the candidate with
    the smallest flip weight.  Ranking matches what ``ContextBuilder`` feeds the
    engine - all index symbols, relationship signals on - so the arithmetic is
    read off the same scores a request would have ranked.

    Args:
        index: A built ``RepositoryIndex``.
        queries: The fixed query set to measure.
        max_tokens: Token budget handed to the ranking pass, as the stage does.

    Returns:
        One row per query that reached any symbol, in the order given.
    """
    from packages.context.models import ContextCandidate
    from packages.context.ranking import RankingEngine
    from packages.context.scoring import carries_query_relevance
    from packages.repository.symbols.graph import SymbolGraph, SymbolGraphView

    graph_view = SymbolGraphView(SymbolGraph(modules=index.modules))

    def _pool() -> list[Any]:
        return [
            ContextCandidate(
                symbol_id=symbol.id,
                qualified_name=symbol.qualified_name,
                module=symbol.module,
                symbol_type=(
                    symbol.symbol_type.value
                    if hasattr(symbol.symbol_type, "value")
                    else str(symbol.symbol_type)
                ),
            )
            for symbol in index.symbols()
        ]

    rows: list[ChangedFileSweepRow] = []
    for query in queries:
        ranked = RankingEngine(symbol_graph_view=graph_view).rank(
            query, _pool(), max_tokens=max_tokens
        )
        relevant = [c for c in ranked if carries_query_relevance(c.reasons)]
        if not relevant:
            continue
        leader = relevant[0]
        others = [c for c in relevant[1:] if c.module != leader.module]
        if not others:
            continue
        best_flip = min(changed_file_flip_weight(leader, c) for c in others)
        via = min(
            (c.qualified_name for c in others if changed_file_flip_weight(leader, c) == best_flip)
        )
        rows.append(
            ChangedFileSweepRow(
                query=query,
                leader=leader.qualified_name,
                leader_module=leader.module,
                leader_score=leader.score,
                flip_weight=best_flip,
                flip_candidate=via,
                flip_gap=leader.score
                - next(c.score for c in others if c.qualified_name == via),
                ties=sum(1 for c in others if c.score == leader.score),
                relevant=len(relevant),
            )
        )
    return rows


def print_changed_file_sweep(rows: list[ChangedFileSweepRow]) -> None:
    """Render the flip-weight sweep, symbol names included."""
    print("\n" + "=" * 100)
    print("CHANGED-FILE FLIP WEIGHT (arithmetic from one ranking pass per query)")
    print("-" * 100)
    for row in rows:
        print(f"{row.query}")
        print(
            f"{'':<4} leader={row.leader} ({row.leader_score}) in {row.leader_module}"
        )
        print(
            f"{'':<4} flip_at={row.flip_weight} gap={row.flip_gap} "
            f"other-module ties={row.ties} via={row.flip_candidate}"
        )
    if rows:
        flips = [row.flip_weight for row in rows]
        print(
            f"{'':<4} over {len(rows)} queries: smallest flip weight "
            f"{min(flips)}, queries decided by a tie {sum(1 for f in flips if f == 1)}"
        )
    print("=" * 100)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
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
        "--changed-file-probe",
        action="store_true",
        help=(
            "run the fixed query through the repository-context stage with the "
            "signal off and with one module injected as dirty, and report whether "
            "the expected primary survived; offline, no gateway, no Git"
        ),
    )
    parser.add_argument(
        "--changed-file-sweep",
        action="store_true",
        help=(
            "report, for a fixed query set, the smallest changed-file bonus that "
            "would hand the primary to a symbol in another file; offline "
            "arithmetic from one ranking pass per query"
        ),
    )
    parser.add_argument(
        "--changed-file-weight",
        type=int,
        default=None,
        metavar="<points>",
        help=(
            "score RankingConfig.WEIGHT_CHANGED_FILE uses during "
            "--changed-file-probe (default: whatever the code ships with). "
            "Diagnostic - it shows what the probe is sensitive to"
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="<path>",
        help="repository to index for the changed-file modes (default: gateway setting)",
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


def _run_changed_file_mode(args: argparse.Namespace) -> int:
    """Index the repository once and run the changed-file modes over it.

    The dirty modules are injected by the probes, never read from Git, so the
    working tree does not affect what either mode prints.
    """
    from packages.repository.index.builder import RepositoryIndexBuilder

    root, exclude_tests, exclude_globs = repository_index_settings(args.repo_root)
    started = time.perf_counter()
    try:
        index = RepositoryIndexBuilder(
            exclude_tests=exclude_tests, exclude_globs=exclude_globs
        ).build(root)
    except Exception as exc:  # noqa: BLE001 - the probe cannot rank what it cannot read
        print(f"ERROR: could not index {root}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    payload: dict[str, Any] = {}
    failed = False
    if args.changed_file_probe:
        outcomes = run_changed_file_probes(
            CHANGED_FILE_PROBES, index, weight=args.changed_file_weight
        )
        payload["probes"] = [outcome.__dict__ for outcome in outcomes]
        failed = not outcomes or not all(outcome.ok for outcome in outcomes)
        if not args.json:
            print(f"indexed {root} in {time.perf_counter() - started:.1f}s")
            print_changed_file_table(outcomes)
            for outcome in outcomes:
                probe = resolve_changed_file_case(outcome.id)
                if probe.note:
                    print(f"{outcome.id}: {probe.note}")
    if args.changed_file_sweep:
        rows = changed_file_sweep(index, CHANGED_FILE_SWEEP_QUERIES)
        payload["sweep"] = [row.__dict__ for row in rows]
        if args.json:
            print(json.dumps(payload, indent=2))
            return 1 if failed else 0
        print(f"indexed {root} in {time.perf_counter() - started:.1f}s")
        print_changed_file_sweep(rows)
    if args.json:
        print(json.dumps(payload, indent=2))
    return 1 if failed else 0


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
    offline_changed_file = args.changed_file_probe or args.changed_file_sweep
    if offline_changed_file and (args.compare_context or args.no_context or args.delta_context):
        print(
            "ERROR: the changed-file modes are offline ranking; they cannot be "
            "combined with gateway modes",
            file=sys.stderr,
        )
        return 2
    if args.changed_file_weight is not None and not args.changed_file_probe:
        print(
            "ERROR: --changed-file-weight only applies to --changed-file-probe",
            file=sys.stderr,
        )
        return 2

    # The changed-file modes need no gateway and no model, so they dispatch before
    # the warnings about completion budgets would mean anything.
    if offline_changed_file:
        return _run_changed_file_mode(args)

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

    # One-per-invocation stderr hint: reasoning models on the default timeout
    # are the common source of confusing no-context probe timeouts.
    _warn_default_timeout_for_reasoning_model(
        args.model,
        args.timeout,
        reasoning_models=_configured_reasoning_models(args.reasoning_model),
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
