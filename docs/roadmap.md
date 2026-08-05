# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-08-01.

## Done Enough For Now

- OpenAI-compatible gateway
- vLLM provider
- provider registry and factory
- model registry
- model router
- client `model` to upstream `backend_model` mapping
- normalized request boundary
- OpenAI protocol compatibility tests
- repository index at startup
- planning stage and deterministic intent detection
- Cline list-form content support in planning
- repository-context injection
- delta context injection
- structured session logs
- session analyzer
- history capping
- measured Cline/vLLM A/B flow proving capping can reduce latency
- explicit per-request context intent override
- configurable custom context intent rules
- live quality harness with context-on/context-off comparison

## Immediate Goals

### 1. Dormant-Code Inventory And Activation — first candidates DONE

Use the dormant packages as a backlog, not as assumed runtime behavior. For
each candidate, decide whether it should be wired into the live gateway,
adapted as a script/tool, or left dormant. See
`docs/dormant-code-backlog.md` for the activated slices and what remains
dormant in each package.

First candidates, all activated as narrow, script-reachable slices:

- `packages.evaluation` - `quality_harness_report.py` scores quality-harness runs
- `packages.engineering_memory` - `quality_harness_records.py` persists deterministic run summaries
- `packages.observability` - `quality_history.py` reuses the persisted records for trend summaries

Remaining dormant packages stay on hold per `docs/dormant-code-backlog.md`'s
"Hold For Later" list until there is a concrete product need.

### 2. Quality Harness Expansion

The fixed probe set now proves repository context adds answer-quality signal
(`15/15` with context versus `2/15` without context in the latest run, on the
6 single-turn probes; needs a fresh live run to include the 2 new multi-turn
probes below).

Done in this area:

- deterministic style/compliance signal for unwanted reasoning preambles and
  tool/thinking chatter, carried through quality-harness JSON,
  `evaluate_quality_harness.py`, and `QualityRun`
- two multi-turn Cline-like probes (`multiturn_history_cap_budget`,
  `multiturn_config_systems`) — `QualityProbe.history` carries prior
  user/assistant turns, sent before the scored final prompt
- compare-run trend tracking, via `scripts/evaluate_quality_harness.py
  --persist` (writes each run to `EngineeringMemory`) and
  `scripts/quality_history.py` (reads back best/worst/average score ratio,
  latest context delta, recent missing facts)

Next improvements:

- run `--compare-context` live to confirm the two multi-turn probes hold up
  the same way the single-turn set does
- consider probes that exercise delta context injection (repeated symbols
  suppressed across turns), not just plain history recall

### 3. Repository Context Budgeting And Ranking

History capping works, but repository context often dominates total prompt
tokens. Next performance work should:

- continue tuning selected symbols/modules by intent
- compare `REFACTOR` and `EXPLAIN` budgets with the quality harness
- add tokenizer-aware estimates when the current character estimate becomes a
  practical blocker

### 4. CI Realignment

CI currently represents the old "whole repo is equally live" worldview. Choose
one path:

- live-path CI only, focused on gateway/pipeline/providers/planning/context/repository
- or full cleanup/quarantine of dormant packages until whole-repo CI is honest

## Next After That

### True Multi-Provider

Routing and model registry exist, but only vLLM is implemented. Add a second
real provider when there is a concrete backend to exercise. A generic
OpenAI-compatible provider is likely the lowest-friction next provider.

### Tokenizer Registry

`ModelDefinition.tokenizer` exists as metadata only. Token estimates still use
`CHARS_PER_TOKEN = 4.0`. Add tokenizer-aware accounting when budget precision
becomes a practical problem.

### Engineering Memory

`packages.engineering_memory` exists but is not wired into the gateway. Revisit
after session logs and repo-context budgeting are stable. The likely first
useful version is not "semantic memory"; it is deterministic summaries of
successful/failed live sessions.

### Git Integration

Useful later for change-aware context, memory, and measuring which files were
actually touched. Not urgent for the current latency/retrieval loop.

## Deferred

- DSPARK adapter
- DFlash adapter
- autonomous engineering loop
- controller/execution/verification/evaluation runtime
- agent orchestration
- semantic/vector search

These may become valuable, but they should not pull focus from the proven live
gateway path without a concrete measurement or product need.

## Definition Of Live

A feature should be documented as live only when all are true:

- reachable from `apps/gateway/main.py` or a gateway endpoint
- visible in session logs or response behavior
- covered by focused tests
- validated by live measurement when it affects latency or agent behavior

Otherwise it is dormant, planned, or experimental.
