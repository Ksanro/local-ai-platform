"""Measure context behaviour across a multi-turn agentic conversation.

`RepositoryContextStage` runs on every request. In a one-shot Q&A that is fine.
In an agentic loop (Cline, Claude Code) a session is 10-40 turns, so context is
re-assembled and re-injected every turn. This script measures what that costs
and how much of it is redundant.

Run from the repo root:

    uv run python scripts/bench_multiturn.py
    uv run python scripts/bench_multiturn.py --turns 12
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logging.disable(logging.INFO)

# A realistic agentic session: the user narrows in on one area, the way a
# coding agent does. Turns build on each other.
TURNS: tuple[str, ...] = (
    "What does ModelRouter.resolve() do in this codebase?",
    "Where is that called from?",
    "What happens if the model isn't in the registry?",
    "Show me how ModelDefinition stores the backend model name.",
    "Does the provider get created per request or once?",
    "How does ProviderStage get the provider instance?",
    "What does it send upstream as the model name?",
    "Is there a test covering that translation?",
    "What would break if backend_model were removed?",
    "Summarise the model routing design.",
)


@dataclass
class Turn:
    """One turn of the simulated session."""

    index: int
    prompt: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    est_tokens: int = 0
    symbols: list[str] = field(default_factory=list)
    error: str = ""


def _usage(payload: Any) -> tuple[int, int]:
    """Return (prompt_tokens, completion_tokens) from a provider response."""
    if not isinstance(payload, dict):
        return 0, 0
    usage = payload.get("usage") or {}
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def _context_symbols(stage_results: dict[str, Any] | None) -> tuple[list[str], int]:
    """Return (retrieved symbol names, estimated tokens) for one turn."""
    for name, result in (stage_results or {}).items():
        if "repository" not in name:
            continue
        pkg = getattr(result, "data", None)
        if pkg is None or isinstance(pkg, dict):
            continue
        names: list[str] = []
        primary = getattr(pkg, "primary_symbol", "") or ""
        if primary:
            names.append(primary)
        for attr in ("supporting_symbols", "related_callers", "related_callees"):
            names.extend(getattr(pkg, attr, []) or [])
        return names, int(getattr(pkg, "estimated_tokens", 0) or 0)
    return [], 0


async def run_session(engine: Any, model: str, prompts: tuple[str, ...]) -> list[Turn]:
    """Run a multi-turn conversation, carrying history forward each turn."""
    from packages.pipeline.request import PipelineRequest

    history: list[dict[str, str]] = []
    turns: list[Turn] = []

    for i, prompt in enumerate(prompts, start=1):
        turn = Turn(index=i, prompt=prompt)
        history.append({"role": "user", "content": prompt})

        request = PipelineRequest(
            provider_name="vllm",
            model=model,
            messages=list(history),
            stream=False,
            kwargs={"max_tokens": 300, "temperature": 0.0},
            metadata={"request_id": f"mt-{i}", "context_enabled": True},
        )

        start = time.perf_counter()
        try:
            response = await engine.execute(request)
        except Exception as exc:  # noqa: BLE001 - measurement must not abort
            turn.error = f"{type(exc).__name__}: {exc}"
            turn.seconds = time.perf_counter() - start
            turns.append(turn)
            continue
        turn.seconds = time.perf_counter() - start

        if not response.success:
            turn.error = response.error or "pipeline failed"
            turns.append(turn)
            continue

        turn.prompt_tokens, turn.completion_tokens = _usage(response.data)
        turn.symbols, turn.est_tokens = _context_symbols(response.stage_results)

        answer = ""
        choices = (response.data or {}).get("choices") or []
        if choices:
            answer = (choices[0].get("message") or {}).get("content") or ""
        history.append({"role": "assistant", "content": answer})

        turns.append(turn)
        print(
            f"  turn {i:>2}: ptok={turn.prompt_tokens:>6} "
            f"ctx_syms={len(turn.symbols):>3} est={turn.est_tokens:>6} "
            f"{turn.seconds:>6.1f}s"
        )

    return turns


def report(turns: list[Turn]) -> None:
    """Print per-turn table and redundancy analysis."""
    print("\n" + "=" * 78)
    print(f"{'turn':>5}{'ptok':>9}{'ctok':>8}{'ctx syms':>10}{'new syms':>10}"
          f"{'est tok':>9}{'sec':>8}")
    print("-" * 78)

    seen: set[str] = set()
    total_ctx = 0
    total_new = 0
    total_est = 0
    total_ptok = 0
    total_sec = 0.0

    for t in turns:
        new = [s for s in t.symbols if s not in seen]
        seen.update(t.symbols)
        total_ctx += len(t.symbols)
        total_new += len(new)
        total_est += t.est_tokens
        total_ptok += t.prompt_tokens
        total_sec += t.seconds
        print(f"{t.index:>5}{t.prompt_tokens:>9}{t.completion_tokens:>8}"
              f"{len(t.symbols):>10}{len(new):>10}{t.est_tokens:>9}{t.seconds:>8.1f}")

    print("-" * 78)
    print(f"{'TOT':>5}{total_ptok:>9}{'':>8}{total_ctx:>10}{total_new:>10}"
          f"{total_est:>9}{total_sec:>8.1f}")
    print("=" * 78)

    redundant = total_ctx - total_new
    pct = (redundant / total_ctx * 100) if total_ctx else 0.0
    print(f"\ndistinct symbols across session : {len(seen)}")
    print(f"symbol injections               : {total_ctx}")
    print(f"redundant re-injections         : {redundant}  ({pct:.0f}%)")
    print(f"estimated context tokens spent  : {total_est}")
    if turns:
        print(f"prompt tokens, turn 1 -> turn {turns[-1].index}      : "
              f"{turns[0].prompt_tokens} -> {turns[-1].prompt_tokens}")

    errors = [(t.index, t.error) for t in turns if t.error]
    if errors:
        print("\nERRORS:")
        for i, err in errors:
            print(f"  turn {i}: {err}")

    print("\nInterpretation:")
    print("  High redundancy means context is re-assembled and re-sent each turn")
    print("  with little new information. If so, injecting once per session (or")
    print("  only when the query shifts) would cut cost with no loss of signal.")


async def main(n_turns: int) -> int:
    from apps.gateway.core.config import get_settings
    from apps.gateway.main import create_app

    settings = get_settings()
    app = create_app()

    async with app.router.lifespan_context(app):
        engine = app.state.pipeline
        prompts = TURNS[:n_turns]
        print(f"model : {settings.default_model}")
        print(f"turns : {len(prompts)}\n")
        turns = await run_session(engine, settings.default_model, prompts)

    report(turns)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=len(TURNS))
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.turns)))