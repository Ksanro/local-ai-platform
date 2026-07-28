# Documentation Index

This index separates runtime documentation from older design and scaffold
documents. When files disagree, prefer the runtime docs below.

## Authoritative Runtime Docs

- [README](../README.md) - human quick start and project overview
- [CLAUDE](../CLAUDE.md) - operating rules for agents and contributors
- [TESTING](../TESTING.md) - live measurement and test protocol
- [Current Status](STATUS.md) - current live gateway snapshot
- [Roadmap](roadmap.md) - current goals and deferred work
- [Execution Flow](execution-flow.mmd) - live gateway pipeline diagram

## Live Gateway Internals

These docs describe components that are in or directly support the live path.
Some may still contain older wording, but the components are reachable.

- [Context Builder](context-builder.md)
- [Context Package](context-package.md)
- [Context Planning](context-planning.md)
- [Planner Rules](planner-rules.md)
- [Scoring Rules](scoring-rules.md)
- [Serialization](serialization.md)
- [Symbol Graph](symbol-graph.md)
- [Relationship Ranking](relationship-ranking.md)
- [Relationship Extraction](relationship-extraction.md)
- [Repository Diagnostics](repository-diagnostics.md)
- [Workspace Dependency Graph](workspace-dependency-graph.md)
- [Change Impact](change-impact.md)

## Dormant Or Future Architecture Docs

These documents describe scaffolding or future architecture that is not wired
into the live gateway path. They are useful background, not runtime truth.

- [Architecture](architecture.md)
- [Capabilities](capabilities.md)
- [Tasks](tasks.md)
- [Workflows](workflows.md)
- [Controller](controller.md)
- [Engineering Controller v2](engineering-controller-v2.md)
- [Engineering Controller Flow](engineering-controller-flow.mmd)
- [Engineering Session](engineering-session.md)
- [Autonomous Engineering](autonomous-engineering.md)
- [Execution Engine](execution-engine.md)
- [Execution Planner](execution-planner.md)
- [Self Verification](self-verification.md)
- [Evaluation Framework](evaluation-framework.md)
- [Code Modification Engine](code-modification-engine.md)
- [Patch Generator](patch-generator.md)
- [Observability](observability.md)
- [Bootstrap](bootstrap.md)
- [Platform Validation](platform-validation.md)
- [Benchmark Framework](benchmark-framework.md)
- [Refactoring Advisor](advisors-refactoring.md)
- [Architecture Review](architecture-review.md)
- [Bug Investigation](bug-investigation.md)
- [Pull Request Review](pull-request-review.md)
- [Planning v2](planning-v2.md)
- [Ranking v2](ranking-v2.md)

## Archive Policy

Dormant docs do not need to be deleted. Before reviving one, first answer:

- Is the corresponding code reachable from `apps/gateway/main.py`?
- Is behavior visible in session logs or API responses?
- Is there a focused test for the live path?
- Does `docs/STATUS.md` list it as live?

If not, keep it marked dormant or move it under `docs/archive/`.
