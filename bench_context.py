"""A/B benchmark: does repository context improve answer quality?

Runs each question twice through the same pipeline -- once with
``context_enabled=True`` and once with ``False`` -- against the real vLLM
backend, and reports tokens, latency, retrieved symbols, and a ground-truth
keyword score.

Run from the repo root:

    uv run python bench_context.py
    uv run python bench_context.py --verbose      # also print answers + retrieval

Questions have verifiable answers drawn from this repository, so scoring is
objective: each expected keyword found in the answer earns a point.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Silence pipeline logging so the table stays readable.
logging.disable(logging.INFO)


@dataclass(frozen=True)
class Question:
    """A benchmark question with ground-truth keywords."""

    id: str
    prompt: str
    expect: tuple[str, ...]


QUESTIONS: tuple[Question, ...] = (
    Question(
        "q1",
        "In this codebase, what does ModelRouter.resolve() return, and what "
        "are that object's fields?",
        ("resolvedmodel", "definition", "provider"),
    ),
    Question(
        "q2",
        "In this codebase, which pipeline stage runs first, and what does it "
        "store on the pipeline context?",
        ("modelresolution", "resolved_model"),
    ),
    Question(
        "q3",
        "In this codebase's ModelDefinition, what is the difference between "
        "the 'model' field and the 'backend_model' field?",
        ("backend_model", "upstream", "routing"),
    ),
    Question(
        "q4",
        "In this codebase, what HTTP status code does the gateway return when "
        "a client requests a model that is not configured?",
        ("404", "model_not_found"),
    ),
    Question(
        "q5",
        "In this codebase, what does FallbackModelRouter.available_models() "
        "return?",
        ("default_model", "settings"),
    ),
    Question(
        "q6",
        "In this codebase, how does the context budget estimator convert "
        "content into a token estimate?",
        ("chars_per_token", "estimate"),
    ),
)


@dataclass
class Run:
    """One question executed under one condition."""

    ok: bool = False
    answer: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    est_tokens: int = 0
    primary: str = ""
    retrieved: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    error: str = ""
    hits: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        """Number of expected keywords found in the answer."""
        return len(self.hits)

    @property
    def n_retrieved(self) -> int:
        """Total symbols pulled into the context package."""
        return len(self.retrieved)


def _extract_answer(payload: Any) -> tuple[str, int, int]:
    """Pull answer text and token counts from a provider response."""
    if not isinstance(payload, dict):
        return "", 0, 0
    text = ""
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        text = (choices[0].get("message") or {}).get("content") or ""
    usage = payload.get("usage") or {}
    return (
        text,
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


def _extract_context(run: Run, stage_results: dict[str, Any] | None) -> None:
    """Populate retrieval fields on ``run`` from the repository stage result.

    ``ContextPackage`` exposes ``primary_symbol``, ``supporting_symbols``,
    ``related_callers``, ``related_callees``, ``related_modules`` and
    ``estimated_tokens``.
    """
    for name, result in (stage_results or {}).items():
        if "repository" not in name:
            continue
        pkg = getattr(result, "data", None)
        if pkg is None or isinstance(pkg, dict):
            continue
        run.primary = getattr(pkg, "primary_symbol", "") or ""
        run.est_tokens = int(getattr(pkg, "estimated_tokens", 0) or 0)
        run.modules = list(getattr(pkg, "related_modules", []) or [])
        symbols: list[str] = []
        if run.primary:
            symbols.append(run.primary)
        for attr in ("supporting_symbols", "related_callers", "related_callees"):
            symbols.extend(getattr(pkg, attr, []) or [])
        run.retrieved = symbols
        return


async def _ask(engine: Any, model: str, q: Question, *, context: bool) -> Run:
    """Execute one question through the pipeline under one condition."""
    from packages.pipeline.request import PipelineRequest

    run = Run()
    request = PipelineRequest(
        provider_name="vllm",
        model=model,
        messages=[{"role": "user", "content": q.prompt}],
        stream=False,
        kwargs={"max_tokens": 400, "temperature": 0.0},
        metadata={
            "request_id": f"bench-{q.id}-{'on' if context else 'off'}",
            "context_enabled": context,
        },
    )

    start = time.perf_counter()
    try:
        response = await engine.execute(request)
    except Exception as exc:  # noqa: BLE001 - a benchmark must not abort
        run.error = f"{type(exc).__name__}: {exc}"
        run.seconds = time.perf_counter() - start
        return run
    run.seconds = time.perf_counter() - start

    if not response.success:
        run.error = response.error or "pipeline failed"
        return run

    run.ok = True
    run.answer, run.prompt_tokens, run.completion_tokens = _extract_answer(response.data)
    _extract_context(run, response.stage_results)

    lowered = run.answer.lower()
    run.hits = [kw for kw in q.expect if kw.lower() in lowered]
    return run


def _print_table(rows: list[tuple[Question, Run, Run]]) -> None:
    """Print the comparison table and totals."""
    print("\n" + "=" * 86)
    print(
        f"{'q':<4}{'score on':>10}{'score off':>11}{'ptok on':>10}"
        f"{'ptok off':>10}{'sec on':>9}{'sec off':>9}{'syms':>7}{'est tok':>9}"
    )
    print("-" * 86)

    tot_on = tot_off = max_score = 0
    ptok_on = ptok_off = 0
    sec_on = sec_off = 0.0

    for q, on, off in rows:
        n = len(q.expect)
        max_score += n
        tot_on += on.score
        tot_off += off.score
        ptok_on += on.prompt_tokens
        ptok_off += off.prompt_tokens
        sec_on += on.seconds
        sec_off += off.seconds
        print(
            f"{q.id:<4}{on.score:>7}/{n}{off.score:>8}/{n}{on.prompt_tokens:>10}"
            f"{off.prompt_tokens:>10}{on.seconds:>9.1f}{off.seconds:>9.1f}"
            f"{on.n_retrieved:>7}{on.est_tokens:>9}"
        )

    print("-" * 86)
    print(
        f"{'TOT':<4}{tot_on:>7}/{max_score}{tot_off:>8}/{max_score}"
        f"{ptok_on:>10}{ptok_off:>10}{sec_on:>9.1f}{sec_off:>9.1f}"
    )
    print("=" * 86)
    print(
        f"\ncontext delta : {tot_on - tot_off:+d} points "
        f"({tot_on}/{max_score} with context, {tot_off}/{max_score} without)"
    )
    print(f"token cost    : {ptok_on - ptok_off:+d} prompt tokens")
    print(f"latency cost  : {sec_on - sec_off:+.1f} s total")


def _print_verbose(rows: list[tuple[Question, Run, Run]]) -> None:
    """Print retrieval and full answers for each question."""
    for q, on, off in rows:
        print("\n" + "=" * 86)
        print(f"{q.id}: {q.prompt}")
        print(f"expect: {', '.join(q.expect)}")
        print(f"\nPRIMARY SYMBOL : {on.primary or '(none)'}")
        print(f"RETRIEVED ({on.n_retrieved}): {', '.join(on.retrieved[:25]) or '(none)'}")
        print(f"MODULES  ({len(on.modules)}): {', '.join(on.modules[:15]) or '(none)'}")
        print(f"\n--- WITH CONTEXT (hits: {on.hits or 'none'}) ---")
        print(on.answer[:1200] or f"(error: {on.error})")
        print(f"\n--- WITHOUT CONTEXT (hits: {off.hits or 'none'}) ---")
        print(off.answer[:1200] or f"(error: {off.error})")


async def main(verbose: bool) -> int:
    """Run the benchmark and print results."""
    from apps.gateway.core.config import get_settings
    from apps.gateway.main import create_app

    settings = get_settings()
    model = settings.default_model
    app = create_app()

    async with app.router.lifespan_context(app):
        engine = app.state.pipeline
        stage = next(
            (s for s in engine._stages if type(s).__name__ == "RepositoryContextStage"),
            None,
        )
        index = getattr(stage, "_index", None) if stage else None

        print(f"model      : {model}")
        print(f"index      : {'built' if index else 'NONE - context will be empty'}")
        print(f"questions  : {len(QUESTIONS)}\n")

        rows: list[tuple[Question, Run, Run]] = []
        for q in QUESTIONS:
            print(f"  running {q.id} ...", end="", flush=True)
            on = await _ask(engine, model, q, context=True)
            off = await _ask(engine, model, q, context=False)
            rows.append((q, on, off))
            print(
                f" on={on.score}/{len(q.expect)}  off={off.score}/{len(q.expect)}"
                f"  retrieved={on.n_retrieved}"
            )

    _print_table(rows)

    errors = [(q.id, r.error) for q, on, off in rows for r in (on, off) if r.error]
    if errors:
        print("\nERRORS:")
        for qid, err in errors:
            print(f"  {qid}: {err}")

    if verbose:
        _print_verbose(rows)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="print full answers")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.verbose)))