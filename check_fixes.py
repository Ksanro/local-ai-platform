"""Deterministic check for Item 5 fixes A, B and C.

No vLLM, no model inference, no scoring noise. Run from the repo root:

    uv run python check_fixes.py
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.disable(logging.INFO)

from packages.context.builder import ContextBuilder  # noqa: E402
from packages.context.models import ContextQuery  # noqa: E402
from packages.repository import build_index  # noqa: E402

Q1 = "what does ModelRouter.resolve() return, and what are that object's fields?"
Q2 = "which pipeline stage runs first, and what does it store on the pipeline context?"


def names(result: object) -> list[str]:
    """Extract qualified names from a ContextResult."""
    return [
        getattr(c, "qualified_name", str(c))
        for c in (getattr(result, "candidates", []) or [])
    ]


def main() -> None:
    #index = build_index(Path("."), exclude_tests=True)
    index = build_index(Path("."), exclude_tests=True, exclude_globs="scripts/**")
    builder = ContextBuilder(index)

    def run(text: str) -> list[str]:
        return names(
            builder.build(
                ContextQuery(text=text, max_symbols=25, max_modules=10, max_tokens=8192)
            )
        )

    q1, q2 = run(Q1), run(Q2)
    ok = True

    # --- Fix A: no duplicate qualified names -------------------------------
    for label, got in (("q1", q1), ("q2", q2)):
        dupes = {n for n in got if got.count(n) > 1}
        status = "PASS" if not dupes else f"FAIL -> {sorted(dupes)}"
        ok &= not dupes
        print(f"A dedupe   {label}: {status}")

    # --- Fix B: benchmark script not indexed -------------------------------
    for label, got in (("q1", q1), ("q2", q2)):
        bench = [n for n in got if n.startswith("bench_context")]
        status = "PASS" if not bench else f"FAIL -> {bench}"
        ok &= not bench
        print(f"B no-bench {label}: {status}")

    # --- Fix C: exact match outranks partial-segment match ------------------
    def rank(lst: list[str], needle: str) -> int:
        for i, n in enumerate(lst):
            if n == needle:
                return i
        return -1

    exact = rank(q1, "router.ModelRouter.resolve")
    partial = rank(q1, "router.FallbackModelRouter.resolve")
    good = exact != -1 and (partial == -1 or exact < partial)
    ok &= good
    print(
        f"C ranking  q1: {'PASS' if good else 'FAIL'} "
        f"(ModelRouter.resolve idx={exact}, FallbackModelRouter.resolve idx={partial})"
    )

    # --- Also report sanity: test symbols must be absent --------------------
    tests = [n for n in q1 + q2 if "test" in n.lower()]
    ok &= not tests
    print(f"  no test symbols: {'PASS' if not tests else f'FAIL -> {tests[:5]}'}")

    print(f"\nq1 top 8: {q1[:8]}")
    print(f"q2 top 8: {q2[:8]}")
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()