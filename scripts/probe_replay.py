r"""Offline replay of the quality probes through the live context stages.

Every probe in ``scripts/quality_harness.py`` ``REPLAY_PROBES`` is sent through
``PlanningStage`` and ``RepositoryContextStage``, built the way the gateway
builds them and configured like the controlled live runs (H1 configuration:
context max 4096 tokens, the per-intent budgets below, delta injection on,
relationship ranking and expansion on, ``exclude_globs="scripts/**,build/**"``).
``REPLAY_PROBES`` is ``PROBES`` - the set the live harness scores, and the
66-fact denominator every published run reports - plus the replay-only pairs that
measure a conversation shape instead of an answer, so a replay file written before
such a pair existed simply has fewer rows; ``--compare`` reports those as
``only in new`` and does not count them against the older set.
No gateway, backend, or network is involved.

For each probe it records the symbols sent (primary first) and how many of the
probe's expected facts are present in the serialized context
(``quality_harness.context_facts_available``).  That is the objective half of a
live score: a fact whose text never reaches the prompt cannot be answered from
context.  It does not say whether the model would use a fact that is present, so
an accepted change still needs live runs.

Index a clean worktree, not the main checkout: untracked files that are not
gitignored would otherwise be indexed and the numbers would not match a
controlled live run.

Usage
-----

.. code-block:: powershell

    git worktree add --detach C:\Users\ovidi\lap-replay-<commit> <commit>
    .\uv.exe run python scripts\probe_replay.py --index-root C:\Users\ovidi\lap-replay-<commit> ^
        --out build\probe_replay\<commit>.json

    .\uv.exe run python scripts\probe_replay.py --compare build\probe_replay\a23faa2.json ^
        build\probe_replay\<commit>.json

The replay uses the code of the checkout it runs from and the index of
``--index-root``; run it from the checkout that holds the change under test.
``--compare`` exits 1 when any probe has fewer facts present than in the base
file, so it can serve as the offline acceptance check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# `python scripts\probe_replay.py` has `scripts/` on sys.path, not the root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: Per-intent context budgets of the controlled live configuration
#: (``APP_REPOSITORY_CONTEXT_INTENT_BUDGETS`` in ``build\*\run_all.ps1``).
INTENT_BUDGETS: dict[str, int] = {
    "SEARCH": 2048,
    "TEST": 2048,
    "DEBUG": 2048,
    "REFACTOR": 4096,
    "IMPLEMENT": 4096,
    "EXPLAIN": 4096,
}
MAX_CONTEXT_TOKENS = 4096
EXCLUDE_GLOBS = "scripts/**,build/**"


def replay(index_root: Path) -> dict[str, dict[str, Any]]:
    """Run every probe through the stages; return one row per probe id."""
    os.environ["RELATIONSHIP_EXPANSION_ENABLED"] = "true"
    os.environ["RELATIONSHIP_RANKING_ENABLED"] = "true"

    from packages.pipeline.context import PipelineContext
    from packages.pipeline.stages.planning_stage import PlanningStage
    from packages.pipeline.stages.repository_context import RepositoryContextStage
    from packages.repository.index.builder import RepositoryIndexBuilder
    from scripts import quality_harness as qh

    index = RepositoryIndexBuilder(exclude_tests=False, exclude_globs=EXCLUDE_GLOBS).build(
        index_root
    )

    rows: dict[str, dict[str, Any]] = {}
    for probe in qh.REPLAY_PROBES:
        messages = [
            {"role": "system", "content": qh.QUALITY_SYSTEM_PROMPT},
            *probe.history,
            {"role": "user", "content": probe.prompt},
        ]
        context = PipelineContext(request_id=f"replay-{probe.id}", request={"messages": messages})
        context.set_metadata("context_intent", probe.intent)
        asyncio.run(PlanningStage().execute(context))
        stage = RepositoryContextStage(
            index=index,
            context_delta_injection=True,
            context_delta_cache_size=256,
            max_context_tokens=MAX_CONTEXT_TOKENS,
            intent_context_budgets=INTENT_BUDGETS,
        )
        result = asyncio.run(stage.execute(context))
        package = (result.data or {}).get("package")
        present = qh.context_facts_available(package, probe.prompt, probe.expect)
        rows[probe.id] = {
            "intent": probe.intent,
            "primary": package.primary_symbol if package else None,
            "sent": [package.primary_symbol, *package.supporting_symbols] if package else [],
            "facts_present": sorted(present),
            "facts": len(present),
            "max": len(probe.expect),
        }
    return rows


def compare(base: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> list[str]:
    """Return report lines; the first line is the verdict (``OK`` or ``REGRESSION``)."""
    lines: list[str] = []
    regressed: list[str] = []
    for probe_id in sorted(set(base) | set(new)):
        old_row = base.get(probe_id)
        new_row = new.get(probe_id)
        if old_row is None or new_row is None:
            lines.append(f"{probe_id}: only in {'new' if old_row is None else 'base'}")
            if new_row is None:
                regressed.append(probe_id)
            continue
        if new_row["facts"] < old_row["facts"]:
            regressed.append(probe_id)
        if new_row["facts"] != old_row["facts"] or new_row["sent"] != old_row["sent"]:
            lost = sorted(set(old_row["facts_present"]) - set(new_row["facts_present"]))
            gained = sorted(set(new_row["facts_present"]) - set(old_row["facts_present"]))
            lines.append(
                f"{probe_id}: facts {old_row['facts']}->{new_row['facts']}/{new_row['max']}"
                f" sent {len(old_row['sent'])}->{len(new_row['sent'])}"
                f" primary {old_row['primary']} -> {new_row['primary']}"
                f" gained={gained} lost={lost}"
            )
    base_total = sum(row["facts"] for row in base.values())
    new_total = sum(row["facts"] for row in new.values())
    maximum = sum(row["max"] for row in new.values())
    unchanged = sum(
        1
        for probe_id in base
        if probe_id in new and base[probe_id]["sent"] == new[probe_id]["sent"]
    )
    verdict = "REGRESSION " + ",".join(regressed) if regressed else "OK"
    summary = (
        f"{verdict}: facts present {base_total} -> {new_total} of {maximum};"
        f" {unchanged} of {len(base)} probes send identical symbols"
    )
    return [summary, *lines]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--index-root", type=Path, help="clean worktree to index")
    parser.add_argument("--out", type=Path, help="write the replay JSON here (default stdout)")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASE", "NEW"),
        type=Path,
        help="compare two replay files instead of replaying",
    )
    args = parser.parse_args(argv)

    if args.compare:
        base_path, new_path = args.compare
        lines = compare(
            json.loads(base_path.read_text(encoding="utf-8")),
            json.loads(new_path.read_text(encoding="utf-8")),
        )
        print("\n".join(lines))
        return 1 if lines[0].startswith("REGRESSION") else 0

    if args.index_root is None:
        parser.error("--index-root is required unless --compare is given")
    rows = replay(args.index_root.resolve())
    text = json.dumps(rows, indent=1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        total = sum(row["facts"] for row in rows.values())
        maximum = sum(row["max"] for row in rows.values())
        print(f"wrote {args.out}: facts present {total}/{maximum}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
