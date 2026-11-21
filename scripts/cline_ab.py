r"""Real-Cline A/B: the quality probes through the gateway vs straight to the backend.

The single-shot harness (``scripts/quality_harness.py``) measures what repository
context adds when the model cannot look anything up (``57/66`` vs ``3/66``). A
client like Cline *can* look things up, so that gap says little about Cline. This
script runs the actual ``cline`` CLI once per probe and arm:

- ``gateway`` - Cline's OpenAI-compatible provider pointed at the gateway alias;
- ``direct``  - the same provider pointed at the backend's own model name.

Each run is ``cline --plan --json`` with a per-arm ``--config``/``--data-dir`` under
the work directory, so the user's ``~/.cline`` setup is never touched. Each arm reads
its own detached worktree at ``HEAD``. The files that hold the probes' expected
answers (any tracked path containing ``quality_harness`` or ``probe_replay``) are
deleted from both worktrees, so Cline cannot grep the answer key. The gateway's
index still covers the checkout it was started on; see the runbook caveat.

Plan mode does not stop Cline from running shell commands: with auto-approve on
(the CLI default) it runs ``git grep`` and the like. The worktrees are what keep a
run off the main checkout. After the runs, a worktree with any change beyond the
answer-key deletions is reported, and both are removed.

The answer is scored with ``quality_harness.score_answer`` against the probe's
facts. A multi-turn probe's canned history is folded into the prompt, because the
CLI takes a single prompt.

Usage
-----

.. code-block:: powershell

    .\uv.exe run python scripts\cline_ab.py --out build\cline_ab\run1.jsonl
    .\uv.exe run python scripts\cline_ab.py --out build\cline_ab\one.jsonl `
        --probe search_answer_preview
    .\uv.exe run python scripts\cline_ab.py --summarize build\cline_ab\run1.jsonl

The gateway must already be running. Every gateway-arm request is written to the
gateway's session log, wherever ``.env`` points ``APP_SESSION_LOG_PATH``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# `python scripts\cline_ab.py` has `scripts/` on sys.path, not the root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.quality_harness import PROBES, QualityProbe, score_answer  # noqa: E402

ARMS: tuple[str, ...] = ("gateway", "direct")
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8001/v1"
DEFAULT_GATEWAY_MODEL = "qwen38-27b"
DEFAULT_DIRECT_URL = "http://100.106.236.88:18300/v1"
DEFAULT_DIRECT_MODEL = "qwen3.8-flash-next"
DEFAULT_TIMEOUT = 900
#: Tracked paths containing one of these hold the probes' expected answers.
ANSWER_KEY_MARKERS: tuple[str, ...] = ("quality_harness", "probe_replay")
#: The integer metrics summarized per arm, in report order.
METRICS: tuple[str, ...] = (
    "iterations",
    "tool_calls",
    "input_tokens",
    "output_tokens",
    "duration_s",
)


@dataclass(frozen=True)
class Arm:
    """One side of the comparison: where Cline's provider points."""

    name: str
    base_url: str
    model: str


@dataclass(frozen=True)
class ClineRun:
    """What one ``cline --json`` run reported."""

    answer: str
    finish: str
    iterations: int
    input_tokens: int
    output_tokens: int
    duration_s: float
    tools: dict[str, int]


def default_cline_entry() -> Path:
    """Return the npm-installed CLI entry script.

    The script is run with ``node`` directly rather than through ``cline.cmd``,
    because cmd.exe would read ``<`` and ``>`` in a probe prompt as redirections.
    """
    return Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "cline" / "bin" / "cline"


def prompt_for(probe: QualityProbe) -> str:
    """Return the single CLI prompt for a probe, with any history folded in."""
    if not probe.history:
        return probe.prompt
    lines = ["Context from earlier in this conversation:"]
    lines.extend(f"[{turn['role']}]: {turn['content']}" for turn in probe.history)
    lines.extend(["", "Current request:", probe.prompt])
    return "\n".join(lines)


def parse_cline_events(stdout: str) -> ClineRun | None:
    """Parse ``cline --json`` output; ``None`` when no ``run_result`` was emitted."""
    tools: Counter[str] = Counter()
    result: dict[str, Any] | None = None
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        event = record.get("event")
        if (
            isinstance(event, dict)
            and event.get("type") == "content_start"
            and event.get("contentType") == "tool"
        ):
            tools[str(event.get("toolName", "?"))] += 1
        if record.get("type") == "run_result":
            result = record
    if result is None:
        return None
    usage = result.get("aggregateUsage") or result.get("usage") or {}
    return ClineRun(
        answer=str(result.get("text") or ""),
        finish=str(result.get("finishReason") or "none"),
        iterations=int(result.get("iterations") or 0),
        input_tokens=int(usage.get("inputTokens") or 0),
        output_tokens=int(usage.get("outputTokens") or 0),
        duration_s=round(float(result.get("durationMs") or 0) / 1000, 1),
        tools=dict(tools),
    )


def build_record(
    arm: str,
    probe: QualityProbe,
    run: ClineRun | None,
    *,
    error: str = "",
    wall_s: float = 0.0,
) -> dict[str, Any]:
    """Score one run and return its JSONL record."""
    answer = run.answer if run else ""
    hits, misses = score_answer(answer, probe.expect)
    if run is None and not error:
        error = "no run_result"
    return {
        "arm": arm,
        "id": probe.id,
        "intent": probe.intent,
        "error": error,
        "wall_s": wall_s,
        "finish": run.finish if run else "none",
        "iterations": run.iterations if run else 0,
        "input_tokens": run.input_tokens if run else 0,
        "output_tokens": run.output_tokens if run else 0,
        "duration_s": run.duration_s if run else 0.0,
        "tool_calls": sum(run.tools.values()) if run else 0,
        "tools": run.tools if run else {},
        "hits": list(hits),
        "misses": list(misses),
        "score": len(hits),
        "max": len(probe.expect),
        "answer": answer[:2000],
    }


def answer_key_paths(tracked: Iterable[str]) -> list[str]:
    """Return the tracked paths that hold the probes' expected answers."""
    return [path for path in tracked if any(m in path for m in ANSWER_KEY_MARKERS)]


def unexpected_changes(porcelain: str) -> list[str]:
    """Return ``git status --porcelain`` lines other than plain deletions."""
    return [line for line in porcelain.splitlines() if line.strip() and not line.startswith(" D ")]


def summarize(records: Sequence[dict[str, Any]]) -> list[str]:
    """Return the per-arm totals and the per-probe side-by-side table."""
    lines: list[str] = []
    for arm in ARMS:
        rows = [r for r in records if r["arm"] == arm]
        if not rows:
            continue
        tools: Counter[str] = Counter()
        for row in rows:
            tools.update(row["tools"])
        finishes = dict(Counter(row["finish"] for row in rows))
        lines += [
            f"== {arm} ({len(rows)} runs)",
            f"facts            {sum(r['score'] for r in rows)}/{sum(r['max'] for r in rows)}",
            f"full-score       {sum(r['score'] == r['max'] for r in rows)}",
            f"errors           {sum(bool(r['error']) for r in rows)}   finish {finishes}",
        ]
        for key in METRICS:
            values = [r[key] for r in rows]
            lines.append(
                f"{key:17}median {statistics.median(values):>10.1f}   total {sum(values):>11.1f}"
            )
        lines += [f"tools            {dict(tools.most_common())}", ""]

    by_probe: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in records:
        by_probe[row["id"]][row["arm"]] = row

    def cell(row: dict[str, Any] | None) -> str:
        if row is None:
            return "-"
        flag = " ERR" if row["error"] else ""
        return (
            f"{row['score']}/{row['max']} i{row['iterations']:>2} c{row['tool_calls']:>2} "
            f"{row['input_tokens']:>7} {row['duration_s']:>6}s{flag}"
        )

    lines.append("per probe: id  gateway(score iters tools in_tok s) | direct(...)")
    for probe_id, arms in by_probe.items():
        lines.append(f"{probe_id:45} {cell(arms.get('gateway'))} | {cell(arms.get('direct'))}")
    return lines


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _prepare_arm(arm: Arm, work_dir: Path, cline: list[str]) -> Path:
    """Create the arm's worktree (answer key removed) and its isolated Cline config."""
    worktree = work_dir / f"wt-{arm.name}"
    _git("worktree", "add", "--detach", str(worktree), "HEAD")
    for rel in answer_key_paths(_git("ls-files", cwd=worktree).splitlines()):
        (worktree / rel).unlink()
    subprocess.run(
        [
            *cline,
            "auth",
            "-p",
            "openai-compatible",
            "-k",
            "unused",
            "-m",
            arm.model,
            "-b",
            arm.base_url,
            "--config",
            str(work_dir / arm.name / "config"),
            "--data-dir",
            str(work_dir / arm.name / "data"),
        ],
        check=True,
        capture_output=True,
    )
    return worktree


def _run_one(
    arm: Arm, probe: QualityProbe, work_dir: Path, cline: list[str], timeout: int
) -> dict[str, Any]:
    command = [
        *cline,
        "--plan",
        "--json",
        "-t",
        str(timeout),
        "--config",
        str(work_dir / arm.name / "config"),
        "--data-dir",
        str(work_dir / arm.name / "data"),
        "-c",
        str(work_dir / f"wt-{arm.name}"),
        prompt_for(probe),
    ]
    started = time.monotonic()
    error = ""
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 60,
        )
        stdout = proc.stdout
        if proc.returncode:
            error = f"exit {proc.returncode}: {(proc.stderr or '')[-300:]}"
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout
        stdout = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
        error = "timeout"
    wall_s = round(time.monotonic() - started, 1)
    return build_record(arm.name, probe, parse_cline_events(stdout), error=error, wall_s=wall_s)


def run_ab(args: argparse.Namespace) -> int:
    """Run every selected probe on both arms, then clean up the worktrees."""
    probes = [p for p in PROBES if not args.probe or p.id in args.probe]
    unknown = set(args.probe or ()) - {p.id for p in PROBES}
    if unknown:
        print(f"ERROR: unknown probe id(s): {sorted(unknown)}", file=sys.stderr)
        return 2
    if shutil.which("node") is None or not Path(args.cline_entry).is_file():
        print(f"ERROR: need node and the Cline entry script {args.cline_entry}", file=sys.stderr)
        return 2
    cline = ["node", str(args.cline_entry)]
    arms = (
        Arm("gateway", args.gateway_url, args.gateway_model),
        Arm("direct", args.direct_url, args.direct_model),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir or out.with_suffix("")).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    worktrees: list[Path] = []
    records: list[dict[str, Any]] = []
    try:
        for arm in arms:
            worktrees.append(_prepare_arm(arm, work_dir, cline))
        jobs = [(arm, probe) for probe in probes for arm in arms]  # interleaved: shared load
        with (
            ThreadPoolExecutor(max_workers=args.workers) as pool,
            out.open("a", encoding="utf-8") as handle,
        ):
            for record in pool.map(
                lambda job: _run_one(job[0], job[1], work_dir, cline, args.timeout), jobs
            ):
                records.append(record)
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                print(
                    f"{record['arm']:8} {record['id']:45} {record['score']}/{record['max']} "
                    f"it={record['iterations']} tools={record['tool_calls']} "
                    f"in={record['input_tokens']} {record['duration_s']}s {record['error'][:80]}",
                    flush=True,
                )
    finally:
        for worktree in worktrees:
            changed = unexpected_changes(_git("status", "--porcelain", cwd=worktree))
            if changed:
                print(f"WARNING: {worktree} was modified by a run: {changed}", file=sys.stderr)
            _git("worktree", "remove", "--force", str(worktree))

    print()
    print("\n".join(summarize(records)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--out", help="JSONL file the per-run records are appended to")
    parser.add_argument("--summarize", metavar="JSONL", help="only print the summary of a run file")
    parser.add_argument(
        "--probe", action="append", help="probe id to run (repeatable; default all)"
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="per-run seconds")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--gateway-model", default=DEFAULT_GATEWAY_MODEL)
    parser.add_argument("--direct-url", default=DEFAULT_DIRECT_URL)
    parser.add_argument("--direct-model", default=DEFAULT_DIRECT_MODEL)
    parser.add_argument("--cline-entry", default=str(default_cline_entry()))
    parser.add_argument(
        "--work-dir", help="worktrees and Cline configs (default: --out without its suffix)"
    )
    args = parser.parse_args(argv)

    if args.summarize:
        with open(args.summarize, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        print("\n".join(summarize(records)))
        return 0
    if not args.out:
        parser.error("--out is required unless --summarize is given")
    return run_ab(args)


if __name__ == "__main__":
    raise SystemExit(main())
