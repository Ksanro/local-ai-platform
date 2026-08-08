"""Emit repeatable local-agent coding workflow prompts and verification commands.

The tasks here are intentionally small and fixed. They are meant to keep one
local coding workflow coordinated across Codex, Cline, Claude extension, and
Claude CLI without losing track of who did what.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VerificationCommand:
    """A command that verifies an agent task after the agent has edited files."""

    argv: tuple[str, ...]
    description: str

    @property
    def display(self) -> str:
        """Return a copy/paste-friendly PowerShell command."""
        return " ".join(self.argv)


@dataclass(frozen=True)
class AgentStep:
    """One role-specific prompt in a local-agent coding workflow."""

    role: str
    actor: str
    purpose: str
    prompt: str


@dataclass(frozen=True)
class LocalAgentCodingTask:
    """A deterministic local-agent task specification."""

    id: str
    title: str
    objective: str
    workflow: tuple[AgentStep, ...]
    expected_files: tuple[str, ...]
    verification: tuple[VerificationCommand, ...]
    success_criteria: tuple[str, ...]


TASKS: tuple[LocalAgentCodingTask, ...] = (
    LocalAgentCodingTask(
        id="style_preamble_cleanup",
        title="Reduce Reasoning Preamble Chatter",
        objective=(
            "Improve local coding-agent answer quality by reducing visible reasoning/tool chatter "
            "without changing factual scoring or repository-context selection."
        ),
        workflow=(
            AgentStep(
                role="plan",
                actor="Cline with qwen3.6 27B dense",
                purpose="first review, planning, and architecture check",
                prompt=(
                    "You are reviewing local-ai-platform before implementation. Focus on the "
                    "quality-harness style issue: live answers often include visible reasoning "
                    "preambles even when all required repository facts are present.\n\n"
                    "Read scripts/quality_harness.py, packages/providers/vllm.py, provider tests, "
                    "and the relevant gateway serialization path. Do not edit files. Produce a "
                    "short implementation plan naming the safest code location, test cases to add, "
                    "and risks. Do not activate dormant workflow/controller/execution packages."
                ),
            ),
            AgentStep(
                role="code",
                actor="Claude extension with local qwen3.6 35B A3B",
                purpose="implementation",
                prompt=(
                    "You are coding in local-ai-platform. Implement a narrow fix for the current "
                    "quality-harness style issue: live answers often include visible reasoning "
                    "preambles even when all required repository facts are present.\n\n"
                    "Use the planning notes if present. Scope:\n"
                    "- Inspect scripts/quality_harness.py, packages/providers/vllm.py, and the "
                    "provider tests before editing.\n"
                    "- Preserve factual scoring behavior; do not loosen expected-fact matching to "
                    "hide bad answers.\n"
                    "- Prefer a deterministic cleanup or prompt/serialization guardrail that is "
                    "safe for OpenAI-compatible responses.\n"
                    "- Add focused tests for any cleanup/detection behavior you change.\n"
                    "- Do not activate dormant workflow/controller/execution packages.\n\n"
                    "After editing, run:\n"
                    ".\\uv.exe run python -m pytest tests\\observability\\test_quality_harness.py "
                    "tests\\providers -q\n"
                    ".\\uv.exe run python -m ruff check scripts\\quality_harness.py "
                    "packages\\providers tests\\observability\\test_quality_harness.py "
                    "tests\\providers\n\n"
                    "Report the changed files, test results, and remaining live-vLLM risk."
                ),
            ),
            AgentStep(
                role="review",
                actor="Claude CLI",
                purpose="code review and tests",
                prompt=(
                    "Review the current local-ai-platform changes for the style_preamble_cleanup "
                    "task. Prioritize bugs, regressions, over-broad cleanup, loosened scoring, and "
                    "missing tests. Run the focused verification commands if available. Report "
                    "findings first with file/line references, then test results. Do not make "
                    "unrelated edits."
                ),
            ),
            AgentStep(
                role="coordinate",
                actor="Codex",
                purpose="master planning, final review, and integration decision",
                prompt=(
                    "Coordinate the style_preamble_cleanup task: inspect Cline's plan, Claude "
                    "extension's patch, and Claude CLI's review/tests. Decide whether the patch is "
                    "ready, needs follow-up, or should be reverted/refined. Run final focused "
                    "checks and summarize the integration decision."
                ),
            ),
        ),
        expected_files=(
            "scripts/quality_harness.py",
            "packages/providers/vllm.py",
            "tests/observability/test_quality_harness.py",
            "tests/providers",
        ),
        verification=(
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "-m",
                    "pytest",
                    "tests\\observability\\test_quality_harness.py",
                    "tests\\providers",
                    "-q",
                ),
                description="focused style/provider regression tests",
            ),
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "-m",
                    "ruff",
                    "check",
                    "scripts\\quality_harness.py",
                    "packages\\providers",
                    "tests\\observability\\test_quality_harness.py",
                    "tests\\providers",
                ),
                description="focused lint for touched style/provider paths",
            ),
        ),
        success_criteria=(
            "Each agent uses its role-specific prompt on the same branch/workspace.",
            "The code step is the only expected implementation step.",
            "Focused tests and lint pass after implementation and review.",
            "The patch does not change required-fact scoring to mask style failures.",
            "Any remaining model-dependent live-vLLM behavior is reported explicitly.",
        ),
    ),
    LocalAgentCodingTask(
        id="delta_context_live_smoke",
        title="Run Delta-Context Live Smoke",
        objective=(
            "Verify the live gateway still suppresses repeated repository symbols on a "
            "follow-up request after repository-context, delta-injection, or session-log changes."
        ),
        workflow=(
            AgentStep(
                role="plan",
                actor="Cline with qwen3.6 27B dense",
                purpose="live smoke planning and risk check",
                prompt=(
                    "You are planning a live delta-context smoke check for local-ai-platform. "
                    "Do not edit files. Inspect scripts/quality_harness.py, docs/STATUS.md, "
                    "docs/roadmap.md, and the session-log/delta-context path if needed. Produce "
                    "a short run plan: required gateway state, exact commands, expected pass/fail "
                    "signals, and risks. Keep the plan focused on "
                    "scripts/quality_harness.py --delta-context."
                ),
            ),
            AgentStep(
                role="code",
                actor="Claude extension with local qwen3.6 35B A3B",
                purpose="operator-run live verification, no implementation unless blocked",
                prompt=(
                    "You are running a live verification task in local-ai-platform, not doing a "
                    "feature implementation. Use the planning notes if present. Goal: verify "
                    "`scripts/quality_harness.py --delta-context` against the local gateway and "
                    "session log.\n\n"
                    "Read docs/live-gateway-runbook.md and follow its Start Gateway, Check "
                    "Gateway, and Delta Context Smoke sections exactly. Do not paste the whole "
                    "runbook back; report only the commands you ran and their outcomes.\n\n"
                    "Do not edit files unless the smoke test exposes a concrete bug. If you do "
                    "edit files, keep the patch minimal and explain why verification could not "
                    "pass without it.\n\n"
                    "Report exact commands, pass/fail output, changed files if any, and whether "
                    "the live result is trustworthy."
                ),
            ),
            AgentStep(
                role="review",
                actor="Claude CLI",
                purpose="review live smoke output and any patch",
                prompt=(
                    "Review the delta_context_live_smoke handoff. Prioritize whether the live "
                    "delta-context run actually exercised session logging and repeated-symbol "
                    "suppression. If code changed, review for regressions and run focused tests. "
                    "Report findings first, then the final pass/fail assessment."
                ),
            ),
            AgentStep(
                role="coordinate",
                actor="Codex",
                purpose="final live-smoke decision and roadmap update",
                prompt=(
                    "Coordinate delta_context_live_smoke: inspect the plan, live output, session "
                    "log evidence, and review notes. Decide whether delta context is verified, "
                    "blocked by backend instability, or needs a code fix. Update docs only if the "
                    "live result is conclusive."
                ),
            ),
        ),
        expected_files=(
            "scripts/quality_harness.py",
            "apps/gateway/session_log.py",
            "packages/context",
            "packages/pipeline/stages/repository_context.py",
            "logs/sessions.jsonl",
        ),
        verification=(
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "scripts\\quality_harness.py",
                    "--delta-context",
                    "--session-log-path",
                    "logs\\sessions.jsonl",
                ),
                description="live delta-context probe against the running gateway",
            ),
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "-m",
                    "pytest",
                    "tests\\observability\\test_quality_harness.py",
                    "-q",
                ),
                description="delta-context harness regression tests",
            ),
        ),
        success_criteria=(
            "The gateway is running with session logging enabled and a fresh session log.",
            "`quality_harness.py --delta-context` reports an OK follow-up result.",
            "The follow-up session record contains suppressed repeated symbols.",
            "Any backend crash or context-window failure is reported as blocked, not as success.",
            "No code is changed unless the live smoke exposes a concrete bug.",
        ),
    ),
    LocalAgentCodingTask(
        id="context_budget_ranking",
        title="Repository Context Budgeting And Ranking",
        objective=(
            "Reduce repository-context token cost for REFACTOR and EXPLAIN intents without "
            "losing quality-harness fact coverage, using measured --compare-context runs and "
            "session-log context-cost-by-intent data to decide whether a budget or ranking "
            "change is actually justified before writing one."
        ),
        workflow=(
            AgentStep(
                role="plan",
                actor="Cline with qwen3.6 27B dense",
                purpose="measurement-driven budget/ranking plan, no edits",
                prompt=(
                    "You are planning repository-context budget and ranking tuning for "
                    "local-ai-platform. This is planning/architecture only: do not edit "
                    "files.\n\n"
                    "Focus: REFACTOR and EXPLAIN intents still use the default repository-"
                    "context token budget. SEARCH, TEST, and DEBUG already have measured "
                    "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS overrides; REFACTOR and EXPLAIN do "
                    "not, and repository context still dominates total prompt tokens for "
                    "them.\n\n"
                    "Inspect, in this order:\n"
                    "- docs/roadmap.md (section 3, Repository Context Budgeting And Ranking) "
                    "and docs/STATUS.md (RepositoryContextStage) for the current tuning "
                    "baseline and how SEARCH/TEST/DEBUG were tuned\n"
                    "- scripts/quality_harness.py and scripts/evaluate_quality_harness.py for "
                    "how --compare-context measures context cost against fact coverage\n"
                    "- scripts/analyze_sessions.py, specifically _print_context_cost, for the "
                    "existing context-cost-by-intent session view\n"
                    "- packages/context/budget.py, packages/context/ranking.py, "
                    "packages/context/ranking_config.py, and packages/context/builder.py for "
                    "how token budgets and ranking currently work\n"
                    "- packages/pipeline/stages/repository_context.py for how the intent "
                    "budget map is applied\n"
                    "- ranking/budget tests under tests/context (test_budget.py, "
                    "test_ranking.py, test_ranking_v2.py, test_builder.py) for the invariants "
                    "a change must not break\n\n"
                    "Produce a short plan: what REFACTOR/EXPLAIN budget values or ranking "
                    "changes to try, how to measure before/after (--compare-context, session-"
                    "log context-cost-by-intent), what could regress fact coverage or the "
                    "existing SEARCH/TEST/DEBUG tuning, and what tests would need to change. "
                    "Do not propose activating dormant workflow/controller/execution/"
                    "evaluation packages."
                ),
            ),
            AgentStep(
                role="code",
                actor="Claude extension with local qwen3.6 35B A3B",
                purpose="implement the measured budget/ranking change",
                prompt=(
                    "You are coding in local-ai-platform. Implement the REFACTOR/EXPLAIN "
                    "repository-context budget or ranking change from the plan step, not a "
                    "redesign.\n\n"
                    "Use the planning notes if present. Scope:\n"
                    "- Change only what the plan calls for in packages/context/budget.py, "
                    "packages/context/ranking.py, packages/context/ranking_config.py, "
                    "packages/pipeline/stages/repository_context.py, or "
                    "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS defaults.\n"
                    "- Preserve the existing SEARCH/TEST/DEBUG tuning unless the plan "
                    "explicitly calls for changing it.\n"
                    "- Add or update tests under tests/context for any budget/ranking "
                    "behavior you change.\n"
                    "- Do not activate dormant workflow/controller/execution/evaluation "
                    "packages.\n\n"
                    "After editing, run:\n"
                    ".\\uv.exe run python -m pytest tests\\context tests\\pipeline -q\n"
                    ".\\uv.exe run python -m ruff check packages\\context "
                    "packages\\pipeline\\stages\\repository_context.py tests\\context\n"
                    ".\\uv.exe run python scripts\\quality_harness.py --compare-context\n\n"
                    "Report the changed files, test results, and the before/after "
                    "--compare-context numbers for REFACTOR and EXPLAIN."
                ),
            ),
            AgentStep(
                role="review",
                actor="Claude CLI",
                purpose="review the budget/ranking change and live measurement",
                prompt=(
                    "Review the current local-ai-platform changes for the "
                    "context_budget_ranking task. Prioritize whether the REFACTOR/EXPLAIN "
                    "token reduction is real rather than budget truncation hiding lost facts, "
                    "whether SEARCH/TEST/DEBUG tuning regressed, and whether tests actually "
                    "cover the new behavior. Run the focused verification commands and the "
                    "live --compare-context comparison if available. Report findings first "
                    "with file/line references, then the measured before/after numbers."
                ),
            ),
            AgentStep(
                role="coordinate",
                actor="Codex",
                purpose="final integration decision and doc/roadmap update",
                prompt=(
                    "Coordinate the context_budget_ranking task: inspect Cline's plan, Claude "
                    "extension's patch, and Claude CLI's review/measurement. Decide whether "
                    "the budget/ranking change is ready, needs another tuning pass, or should "
                    "be reverted. Update docs/STATUS.md and docs/roadmap.md only if the live "
                    "result is conclusive, using the same measured-numbers style as the "
                    "existing SEARCH/TEST/DEBUG tuning notes."
                ),
            ),
        ),
        expected_files=(
            "packages/context/budget.py",
            "packages/context/ranking.py",
            "packages/context/ranking_config.py",
            "packages/pipeline/stages/repository_context.py",
            "tests/context",
        ),
        verification=(
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "-m",
                    "pytest",
                    "tests\\context",
                    "tests\\pipeline",
                    "-q",
                ),
                description="focused context/pipeline regression tests",
            ),
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "-m",
                    "ruff",
                    "check",
                    "packages\\context",
                    "packages\\pipeline\\stages\\repository_context.py",
                    "tests\\context",
                ),
                description="focused lint for touched context/pipeline paths",
            ),
            VerificationCommand(
                argv=(
                    ".\\uv.exe",
                    "run",
                    "python",
                    "scripts\\quality_harness.py",
                    "--compare-context",
                ),
                description="live before/after quality-harness comparison",
            ),
        ),
        success_criteria=(
            "The plan step produces measurement targets and risks, not implementation, and "
            "does not edit files.",
            "REFACTOR and EXPLAIN prompt/context tokens drop in a live --compare-context run "
            "without losing required-fact score.",
            "SEARCH/TEST/DEBUG budgets and quality-harness scores do not regress.",
            "Focused context/pipeline tests pass after implementation and review.",
            "docs/STATUS.md and docs/roadmap.md are updated only with measured, conclusive "
            "results.",
        ),
    ),
)


def _task_by_id(task_id: str) -> LocalAgentCodingTask:
    for task in TASKS:
        if task.id == task_id:
            return task
    known = ", ".join(task.id for task in TASKS)
    raise ValueError(f"Unknown task {task_id!r}. Known tasks: {known}")


def _as_dict(task: LocalAgentCodingTask) -> dict[str, object]:
    return {
        **dataclasses.asdict(task),
        "verification": [
            {
                "description": command.description,
                "argv": list(command.argv),
                "display": command.display,
            }
            for command in task.verification
        ],
    }


def print_task(task: LocalAgentCodingTask) -> None:
    """Print a human-readable task card."""
    print(f"{task.id}: {task.title}")
    print(task.objective)
    print()
    print("WORKFLOW")
    for index, step in enumerate(task.workflow, start=1):
        print(f"{index}. {step.role}: {step.actor}")
        print(f"   purpose: {step.purpose}")
    print()
    print("EXPECTED FILES")
    for path in task.expected_files:
        print(f"- {path}")
    print()
    print("VERIFY")
    for command in task.verification:
        print(f"- {command.display}  # {command.description}")
    print()
    print("SUCCESS")
    for criterion in task.success_criteria:
        print(f"- {criterion}")


def _read_notes(path: str | None) -> str:
    """Read optional handoff notes for the next workflow step."""
    if not path:
        return ""
    notes_path = Path(path)
    return notes_path.read_text(encoding="utf-8")


def _console_safe(text: str) -> str:
    """Return text printable on Windows consoles using legacy code pages."""
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def print_step(task: LocalAgentCodingTask, role: str, *, notes_file: str | None = None) -> None:
    """Print one role-specific prompt."""
    notes = _read_notes(notes_file)
    for step in task.workflow:
        if step.role == role:
            print(f"{task.id} / {step.role}: {step.actor}")
            print(step.purpose)
            print()
            print("PROMPT")
            print("```")
            print(step.prompt)
            if notes:
                print()
                print("Handoff notes from the previous step:")
                print(_console_safe(notes.rstrip()))
            print("```")
            return
    known = ", ".join(step.role for step in task.workflow)
    raise ValueError(f"Unknown role {role!r}. Known roles for {task.id}: {known}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list available local-agent coding tasks")

    show = subparsers.add_parser("show", help="print one task")
    show.add_argument("task_id", help="task id to print")
    show.add_argument("--json", action="store_true", help="emit task as JSON")

    step = subparsers.add_parser("step", help="print one role-specific prompt")
    step.add_argument("task_id", help="task id")
    step.add_argument(
        "role",
        choices=("plan", "code", "review", "coordinate"),
        help="workflow role to print",
    )
    step.add_argument(
        "--notes-file",
        default=None,
        help="optional previous-step notes file to append inside the prompt block",
    )

    verify = subparsers.add_parser("verify", help="run or print verification commands")
    verify.add_argument("task_id", help="task id to verify")
    verify.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands without executing them",
    )
    return parser.parse_args(argv)


def run_verification(task: LocalAgentCodingTask, *, dry_run: bool) -> int:
    """Run static verification commands for a task."""
    for command in task.verification:
        print(command.display)
        if dry_run:
            continue
        completed = subprocess.run(command.argv, cwd=Path(__file__).resolve().parent.parent)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main(argv: list[str]) -> int:
    """Run the local-agent coding task CLI."""
    args = parse_args(argv)
    if args.command == "list":
        for task in TASKS:
            print(f"{task.id}\t{task.title}")
        return 0

    task = _task_by_id(args.task_id)
    if args.command == "show":
        if args.json:
            print(json.dumps(_as_dict(task), indent=2))
        else:
            print_task(task)
        return 0
    if args.command == "step":
        print_step(task, args.role, notes_file=args.notes_file)
        return 0
    if args.command == "verify":
        return run_verification(task, dry_run=args.dry_run)

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
