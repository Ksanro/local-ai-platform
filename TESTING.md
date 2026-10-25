# TESTING.md — how to run and request tests

This file defines how tests and measurements are handed off in this project. It exists so a testing
request produces something runnable top-to-bottom, not prose to interpret.

## Format contract (for whoever writes the test steps)

When providing a test or measurement, always give, in this order:

1. **Exact commands, in run order.** PowerShell (Windows). Every `uv` call starts with `.\uv.exe`. No
   "then do X" prose between commands that could be folded into a command.
2. **One exact Cline task string** (verbatim, in a code block) when the test needs a live agent
   session — never "run a real task". The same string is reused across compared runs so results are
   comparable.
3. **The specific numbers to read** from the output, and the pass/fail line to watch.
4. **Minimal surrounding text.** Extra context invites unplanned variation. Say what to run, what to
   look for, stop.

Two runs that are being compared must differ in **exactly one variable** (e.g. one env flag). Same
Cline task, same files, same order. If two things change, the comparison is meaningless.

## Environment facts

- Config uses Pydantic with `env_prefix = "APP_"`. A field `history_cap_enabled` is set via the env
  var `APP_HISTORY_CAP_ENABLED`. Set these in `.env` (loaded with `override=true`, so `.env` beats
  shell env).
- Settings are read at **startup** and cached. Any `.env` change requires a **gateway restart** to
  take effect.
- Relevant flags:
  - `APP_SESSION_LOG_ENABLED` (default false) — must be `true` to capture anything to analyze.
  - `APP_SESSION_LOG_PATH` (default `logs/sessions.jsonl`).
  - `APP_HISTORY_CAP_ENABLED` (default **true** - verify current default in `config.py`).
  - `APP_HISTORY_CAP_TOKENS` (default 0 = derive from context window; set a number to force a budget).
  - `APP_REPOSITORY_CONTEXT_ENABLED` (default true).
- Per request, `/v1/chat/completions` accepts `repository_context_enabled` to override repository
  context for that call. The quality harness uses this for context-on/context-off comparison.

## Log hygiene — always

- **Delete the log before every measurement run:**
  `Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue`
- A mixed log (old + new records) silently corrupts every average. One run = one clean log.
- Redirect each run's analysis to its own file (`> run_A.txt`) so runs are not overwritten.

## Deterministic checks (no gateway, no vLLM, no model)

Use these to confirm code is correct before any live run. Fast, repeatable, no noise.

```powershell
.\uv.exe run python -m pytest -q
.\uv.exe run python -m pytest tests\pipeline tests\gateway tests\test_protocol_invariant.py -q
.\uv.exe run python -m ruff check packages apps
.\uv.exe run python -m mypy packages\providers packages\pipeline apps\gateway
.\uv.exe run python scripts\check_fixes.py
.\uv.exe run python scripts\bench_context.py
.\uv.exe run python scripts\git_change_snapshot.py --json .
.\uv.exe run python scripts\ab_launcher.py template
.\uv.exe run python scripts\quality_harness.py
.\uv.exe run python -m pytest tests\evaluation tests\scripts tests\engineering_memory tests\observability\test_quality_harness.py tests\observability\test_quality_history.py -q
```

`scripts\ab_launcher.py` builds and checks the configuration the two isolated-worktree
A/B arms start with; `template` with no `--out` prints the experiment it would write, and
the script never starts a gateway or harness and never contacts the backend, so it is a
deterministic check rather than a live probe. It also declares
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true` in the block both arms
share: since roadmap B4 the gateway builds the no-bonus counterfactual only when asked,
and a changed-file pair whose enabled arm never asked would report
`changed_baseline_status=not_sampled` and leave `changed_context_differs`,
`changed_primary_promoted` and `changed_symbols_promoted` as placeholders. The launcher
refuses such a pair rather than rendering it, so a run it produces keeps the promotion
fields readable; `tests\scripts\test_ab_launcher.py` pins that, and
`test_both_arms_opt_into_the_counterfactual_comparison` pins that the setting is identical
in both arms and so never appears in `show --diff`.

The same opt-in is what makes an ordinary enabled request cheap. A gateway started with
only `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED=true` composes and sends its
change-aware context once, and the requests whose bonus fired are exactly the ones that
read `not_sampled`: the directly observable counters (`changed_files_signal`,
`changed_files_count`, `changed_symbols_selected`) are still measurements, and the three
that need a comparison are not. A log of that traffic can therefore say nothing about
whether the bonus changed anything, and `scripts\analyze_sessions.py` counts those records
as `unmeasured` rather than as `present but inert`, and keeps them out of the
`changed_primary_promoted` count and its rate, which are taken over the records whose
comparison was actually made (`built`) or proved unnecessary (`skipped_no_bonus`).
`tests\scripts\test_ab_launcher.py` keeps that property: its
`test_the_launcher_never_starts_a_process_or_opens_a_connection` replaces every
`subprocess` and `os.exec`/`os.spawn` entry point with one that fails the test, then runs
each command.

`scripts\git_change_snapshot.py` is a read-only Git utility: it runs
`git rev-parse --show-toplevel` and
`git --no-optional-locks status --porcelain=v2 -z --branch
--untracked-files=all`, prints a table (or `--json`), exits nonzero on an
operational error, and never stages, commits, resets, checks out, cleans,
fetches, or pushes. Pass a path to snapshot another repository; the default is
the current directory.

Baseline: the full suite has a known failure count (all in unreachable dead-code packages; 43 on
Python 3.13 - see the "Pre-commit hook" section below). A clean change must **not increase** it.
Confirm the current baseline number before claiming a change is clean.

## Pre-commit hook

The local git hook (`.git/hooks/pre-commit`, untracked and machine-local)
delegates to the tracked `scripts/precommit_test_gate.sh`:

- **Default mode (what the hook runs):** the live-path test set only
  (`tests/pipeline`, `tests/gateway`, `tests/providers`, `tests/planning`,
  `tests/context`, `tests/repository`, `tests/evaluation`, `tests/scripts`,
  `tests/engineering_memory`, `tests/test_protocol_invariant.py`, plus the
  three activated `tests/observability` quality files). The commit is
  blocked on pytest's exit code - any live-path failure blocks. No
  failure-count parsing.
- **Full-suite baseline (opt-in):** the known dormant-package failures are
  not paid for on every commit. Check them explicitly with the `--full`
  forms below. Baseline: **43 failures on Python 3.13** (49 on Python 3.12
  - six immutability tests depend on a CPython fix for
  `@dataclass(frozen=True, slots=True)`). `--full` blocks only when the
  count exceeds the baseline, and also fails when the run cannot be
  interpreted safely (collection/internal errors).

The known failures are all in dormant packages: `autonomous` (26), dormant
`observability` telemetry (12), `integration/test_engineering_flow` (4),
and `modification/test_engine.py::TestInvalidPatchSet::test_nonexistent_workspace_raises` (1).
Do not reduce the count with xfail/skip; see `CLAUDE.md` "Test baseline".

Run the gate manually from the repo root. From Git Bash:

```bash
bash scripts/precommit_test_gate.sh          # live-path gate (what the hook runs)
bash scripts/precommit_test_gate.sh --full   # full-suite baseline check
```

From PowerShell on this machine, use Git's bundled bash - a bare `bash`
resolves to the WSL stub, which has no distro installed:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh           # live-path gate
& 'C:\Program Files\Git\bin\bash.exe' scripts/precommit_test_gate.sh --full   # full-suite baseline
```

## Live measurement (gateway + vLLM required)

Start the gateway (leave running in its own terminal):

```powershell
.\uv.exe run uvicorn apps.gateway.main:create_app --factory --port 8001
```

Confirm it is up (second terminal):

```powershell
curl http://localhost:8001/v1/models
```

Drive traffic, then analyze:

```powershell
.\uv.exe run python scripts\analyze_sessions.py logs\sessions.jsonl
```

The `CONTEXT COST` section includes a `By intent` table. Use it to compare
REFACTOR versus EXPLAIN repository-context budget behavior: median estimated
context tokens, configured budget, budget utilization, and share of prompt.

Run deterministic answer-quality probes:

```powershell
.\uv.exe run python scripts\quality_harness.py
.\uv.exe run python scripts\quality_harness.py --compare-context
.\uv.exe run python scripts\quality_harness.py --delta-context --session-log-path logs\sessions.jsonl
```

Read the `TOTAL` line. `--compare-context` changes exactly one variable per
probe: repository context on versus off through the same gateway/provider path.
The current fixed probe set has 11 probes and 30 total expected facts
(`total_maximum` is `30`) - the original 6 single-turn probes, 2 multi-turn probes
(`multiturn_history_cap_budget`, `multiturn_config_systems`) that send prior
user/assistant turns before the scored final prompt, and the 3
`explain_changed_files_*` probes that carry the change-aware ranking decision.
The current baseline is the controlled `--compare-context` run completed
2026-10-24 at gateway commit `0371d64`, taken from a detached worktree with
changed-file ranking off against `qwen3.8-flash-next` on the vLLM backend:
`25/30` with repository context against `4/30` without it, style `11/11` ok in both
arms, 33109 prompt tokens in 129.6 seconds against 2221 in 532.1 seconds, no errored
and no timed-out request. Its JSON is
`logs\quality_compare_qwen38_vllm_20261024.json`, persisted as engineering-memory
session `quality_harness_compare-20261024T173757728411-2a4297e1` (exact commands:
`docs/live-gateway-runbook.md`, "Current controlled baseline, 2026-10-24 (roadmap
A1)"). The `20/20` figures - the qwen38-27b/SGLang full runs of 2026-08-22 (28013
prompt tokens, 144.6 seconds; `logs\quality_baseline_qwen38_27b_after_fixes.json`,
session `quality_harness-20260821T214629502370-6d519523`) and 2026-10-10 (25093
prompt tokens, 99.2 seconds;
`logs\quality_baseline_qwen3_8_flash_next_20261010.json`, session
`quality_harness-20261009T214258101237-9d6f90f9`) - were measured on the earlier
8-probe, 20-fact set and are historical; so are the
`14-15/15` with context and `2/15` without context from the original 6 single-turn
probes (`total_maximum` `15`).
The quality table also reports a separate style signal: `ok` means no known
reasoning preamble or tool/thinking marker was detected, while `bad` means the
answer still contained that chatter even if the required facts were present.

Use `--delta-context` for the server-side delta-context smoke test. It sends
two sequential live requests, then reads the session JSONL context metadata and
expects the follow-up request to report `symbols_suppressed > 0`. Keep session
logging enabled and point `--session-log-path` at the gateway's
`APP_SESSION_LOG_PATH` value.

Optionally, pipe `--json` output through `scripts\evaluate_quality_harness.py`
to get a structured evaluation (score, missing facts, prompt-token cost,
latency, style violations, and — in `--compare-context` mode — per-probe context delta) via
`packages.evaluation.quality_harness_report`:

```powershell
.\uv.exe run python scripts\quality_harness.py --json | .\uv.exe run python scripts\evaluate_quality_harness.py -
.\uv.exe run python scripts\quality_harness.py --compare-context --json | .\uv.exe run python scripts\evaluate_quality_harness.py -
.\uv.exe run python scripts\quality_harness.py --delta-context --json --session-log-path logs\sessions.jsonl
```

Add `--persist --model <name> [--gateway-commit <sha>] [--notes "..."]` to
store the evaluation as a deterministic `EngineeringSessionRecord` via
`packages.engineering_memory.quality_harness_records`, e.g.:

```powershell
.\uv.exe run python scripts\quality_harness.py --json | .\uv.exe run python scripts\evaluate_quality_harness.py - --persist --model qwen36 --notes "post history-cap tuning"
```

Records land in `data/engineering_memory/memory_v1.json` by default (override
with `--storage-path`).

Read persisted quality-harness history with:

```powershell
.\uv.exe run python scripts\quality_history.py
.\uv.exe run python scripts\quality_history.py --json
```

Add `--quality-run [--quality-run-path <file>]` instead to get a flat
`QualityRun` summary (run_id, model, mode, totals, per-probe rows with
context-delta fields when in `--compare-context` mode) printed as JSON or
written to a file — no dashboard, no `EngineeringMemory` involvement:

```powershell
.\uv.exe run python scripts\quality_harness.py --json | .\uv.exe run python scripts\evaluate_quality_harness.py - --quality-run --model qwen36
```

## A/B measurement recipe (the standard shape)

To measure the effect of one setting, run the identical Cline task twice, changing only that setting,
with a clean log each time.

```powershell
# --- RUN A (control) ---
notepad .env                                              # set the ONE flag to its A value, save
Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue
.\uv.exe run uvicorn apps.gateway.main:create_app --factory --port 8001
#   -> paste the exact Cline task, let it finish, Ctrl+C the gateway
.\uv.exe run python scripts\analyze_sessions.py logs\sessions.jsonl > run_A.txt
type run_A.txt

# --- RUN B (treatment) ---
notepad .env                                              # flip the ONE flag to its B value, save
Remove-Item logs\sessions.jsonl -ErrorAction SilentlyContinue
.\uv.exe run uvicorn apps.gateway.main:create_app --factory --port 8001
#   -> paste the SAME Cline task, let it finish, Ctrl+C the gateway
.\uv.exe run python scripts\analyze_sessions.py logs\sessions.jsonl > run_B.txt
type run_B.txt
```

Compare `run_A.txt` and `run_B.txt` on the specific metrics named in the test request.

When the one flag is `APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED`, set
`APP_REPOSITORY_CONTEXT_CHANGED_FILES_COMPARISON_ENABLED=true` in **both** runs
(roadmap B4 default: off). It changes nothing about what either arm sends - that is
pinned by `test_the_comparison_setting_never_changes_what_is_sent` - and it is the only
way the enabled arm's `changed_context_differs`, `changed_primary_promoted` and
`changed_symbols_promoted` become measurements instead of `not_sampled` placeholders.
Skipping it costs the second build out of the run, which is exactly what a latency
measurement wants and exactly what a promotion measurement cannot read.

## Cline task strings - rules

- Provide the task as a verbatim code block; the operator pastes it unchanged.
- Reference specific files by path so the token load is reproducible across runs.
- Keep it a fixed, bounded task (read these files, explain this) - not open-ended ("improve the
  code"), whose token load varies run to run and breaks the comparison.
- After a live run, note in prose whether Cline **completed the task correctly** - tool calls
  executed, answer coherent. A latency win that breaks Cline's behaviour is not a win.

## Local agent coding workflow

Use `scripts/local_agent_coding.py` to coordinate one local coding branch across
the current agent roles:

- Cline with qwen3.6 27B dense: first review, planning, architecture
- Claude extension with local qwen3.6 35B A3B: implementation
- Claude CLI: code review and tests
- Codex: master planning, final review, integration decision

The script owns the role-specific prompts and verifier commands:

```powershell
.\uv.exe run python scripts\local_agent_coding.py list
.\uv.exe run python scripts\local_agent_coding.py show style_preamble_cleanup
.\uv.exe run python scripts\local_agent_coding.py show style_preamble_cleanup --json
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup plan
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup code
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup review
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup coordinate
.\uv.exe run python scripts\local_agent_coding.py verify style_preamble_cleanup --dry-run
```

For live gateway setup, agents should read `docs/live-gateway-runbook.md`
instead of rediscovering how to start the gateway, align session log paths, and
run delta-context probes.

Run the steps on one branch in this order:

```powershell
git switch -c agent-style-preamble-cleanup
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup plan
# paste PROMPT into Cline, then save its output to a handoff note file
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup code --notes-file logs\agent_handoffs\style_preamble_cleanup_plan.md
# paste PROMPT into Claude extension with local qwen3.6 35B A3B
.\uv.exe run python scripts\local_agent_coding.py verify style_preamble_cleanup
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup review
# paste PROMPT into Claude CLI
.\uv.exe run python scripts\local_agent_coding.py step style_preamble_cleanup coordinate
# Codex performs the final integration review
```

After the implementation and review steps, run:

```powershell
.\uv.exe run python scripts\local_agent_coding.py verify style_preamble_cleanup
```

Do not run the same task independently in multiple branches unless the goal is
an explicit A/B comparison. The default workflow is one branch, staged handoffs.

## The core discipline

The recurring failure mode in this project is **green tests certifying inert code** - a feature wired
to the wrong slot passes every test and does nothing. The reliable way to catch it is to demand a
**measurable effect** (a number that must move), not to ask the suite whether the code is correct.
Every live measurement should name, in advance, the number that proves the feature ran at all
(e.g. `history_dropped_count > 0`). If that number does not move, the feature did not run — regardless
of a green suite.
