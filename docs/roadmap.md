# Roadmap

This roadmap is based on the current live gateway, not on dormant scaffolding.

Last reviewed: 2026-07-28.

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

## Immediate Goals

### 1. Documentation Realignment

Make docs match the runtime:

- keep `CLAUDE.md` as agent/contributor operational truth
- keep `README.md` as the human quick start
- keep `docs/STATUS.md` as current runtime snapshot
- keep `TESTING.md` as measurement protocol
- label dormant/future docs visibly

### 2. Live Intent Validation

The planning stage now handles list-form Cline content. Run a fresh live Cline
session and verify session logs no longer show `100% DEFAULT` for prompts that
clearly contain explain/debug/test/search/refactor intent.

### 3. Repository Context Budgeting

History capping works, but repository context often dominates total prompt
tokens. Next performance work should:

- log repository-context token contribution separately from history
- apply model-aware repository-context budgets
- tune selected symbols/modules by intent
- measure prompt-token and latency impact with live Cline traffic

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
