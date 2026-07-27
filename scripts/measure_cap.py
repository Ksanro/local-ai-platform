"""Controlled measurement of history capping: OFF vs ON(derived) vs ON(aggressive).

Drives the SAME multi-turn conversation through the in-process pipeline three
times under three cap settings, writing a separate log for each, then prints a
side-by-side comparison. Identical input each run, so differences are the cap,
not the task.

This measures the pipeline + provider path (it calls the real vLLM backend via
the provider), but does NOT go through the HTTP server — so it needs no running
gateway. It writes its own JSONL logs in the same format the analyzer reads.

Run from the repo root:

    uv run python scripts/measure_cap.py

Requires the vLLM backend reachable (same as bench_multiturn.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

logging.disable(logging.INFO)

# One fixed conversation, replayed identically under every setting. Turns build
# on each other and reference earlier context, the way a real coding session
# does — so history accumulates and capping has something to act on.
TURNS: tuple[str, ...] = (
    "What does the ModelRouter class do in this codebase?",
    "How does it resolve a model name to a backend?",
    "What is the difference between model and backend_model?",
    "Where is the router constructed at startup?",
    "How does the pipeline decide which stage runs first?",
    "What does RepositoryContextStage attach to the context?",
    "How is repository context assembled into the prompt?",
    "What does delta injection suppress, and how?",
    "How is the conversation key computed for delta injection?",
    "Summarize the full request flow from client to provider.",
)

RESERVE = 12000  # tokens reserved for the current turn + generation headroom


async def run_one(
    label: str,
    cap_enabled: bool,
    cap_tokens: int,
    log_path: Path,
) -> list[dict[str, Any]]:
    """Run the fixed conversation once under one cap setting; write a log."""
    # Import inside so settings pick up env before construction.
    from apps.gateway.core.config import get_settings
    from apps.gateway.main import create_app
    from packages.pipeline.request import PipelineRequest

    get_settings.cache_clear()  # settings are lru_cached; force a fresh read
    settings = get_settings()
    # Override in-memory for this run (no .env editing needed).
    object.__setattr__(settings, "history_cap_enabled", cap_enabled)
    object.__setattr__(settings, "history_cap_tokens", cap_tokens)

    app = create_app()
    records: list[dict[str, Any]] = []

    async with app.router.lifespan_context(app):
        engine = app.state.pipeline
        model = settings.default_model
        history: list[dict[str, str]] = []

        for i, prompt in enumerate(TURNS, start=1):
            history.append({"role": "user", "content": prompt})
            req = PipelineRequest(
                provider_name="vllm",
                model=model,
                messages=list(history),
                stream=False,
                kwargs={"max_tokens": 300, "temperature": 0.0},
                metadata={
                    "request_id": f"{label}-{i}",
                    "context_enabled": True,
                    "history_cap_enabled": cap_enabled,
                    "history_cap_tokens": cap_tokens,
                },
            )
            start = time.perf_counter()
            try:
                resp = await engine.execute(req)
            except Exception as exc:  # noqa: BLE001
                records.append({"turn": i, "error": f"{type(exc).__name__}: {exc}"})
                continue
            elapsed_ms = (time.perf_counter() - start) * 1000

            usage = {}
            answer = ""
            if resp.success and isinstance(resp.data, dict):
                usage = resp.data.get("usage") or {}
                choices = resp.data.get("choices") or []
                if choices:
                    answer = (choices[0].get("message") or {}).get("content") or ""
                    history.append({"role": "assistant", "content": answer})

            rec = {
                "turn": i,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_ms": round(elapsed_ms, 1),
                "history_dropped": (resp.metadata or {}).get("history_dropped_count") if resp.success else None,
                "ok": resp.success,
            }
            records.append(rec)
            print(
                f"  [{label}] turn {i:>2}: "
                f"ptok={rec['prompt_tokens']} "
                f"dropped={rec['history_dropped']} "
                f"{rec['total_ms']:.0f}ms"
            )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return records


def _med(values: list[float]) -> float:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else 0.0


def summarize(label: str, records: list[dict[str, Any]]) -> dict[str, float]:
    ptok = [r.get("prompt_tokens") for r in records if r.get("prompt_tokens")]
    lat = [r.get("total_ms") for r in records if r.get("total_ms")]
    dropped = [r.get("history_dropped") or 0 for r in records]
    errors = sum(1 for r in records if r.get("error") or r.get("ok") is False)
    return {
        "median_ptok": _med(ptok),
        "median_latency_ms": _med(lat),
        "max_latency_ms": max(lat) if lat else 0.0,
        "total_dropped": sum(dropped),
        "errors": errors,
    }


async def main() -> int:
    from apps.gateway.core.config import get_settings

    get_settings.cache_clear()
    window = 0
    try:
        # Best-effort read of the model window for the aggressive setting note.
        s = get_settings()
        window = 0  # informational only
    except Exception:  # noqa: BLE001
        pass

    runs = [
        ("off", False, 0, Path("logs/cap_off.jsonl")),
        ("derived", True, 0, Path("logs/cap_derived.jsonl")),
        ("aggressive", True, 3000, Path("logs/cap_30k.jsonl")),
    ]

    results: dict[str, dict[str, float]] = {}
    for label, enabled, tokens, path in runs:
        print(f"\n=== RUN: {label} (enabled={enabled}, tokens={tokens or 'derived'}) ===")
        recs = await run_one(label, enabled, tokens, path)
        results[label] = summarize(label, recs)

    print("\n" + "=" * 72)
    print(f"{'setting':<12}{'med ptok':>10}{'med lat ms':>12}{'max lat ms':>12}"
          f"{'dropped':>9}{'errors':>8}")
    print("-" * 72)
    for label, _e, _t, _p in runs:
        r = results[label]
        print(f"{label:<12}{r['median_ptok']:>10.0f}{r['median_latency_ms']:>12.0f}"
              f"{r['max_latency_ms']:>12.0f}{r['total_dropped']:>9.0f}"
              f"{r['errors']:>8.0f}")
    print("=" * 72)
    print("\nRead: 'dropped'=0 on a cap-on run means the budget never triggered")
    print("(conversation stayed under it). Compare med ptok and med lat across")
    print("rows — a drop in ptok with a drop in latency confirms prefill was the")
    print("bottleneck. Any errors on a cap-on run = capping broke a conversation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))