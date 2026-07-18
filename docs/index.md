# Documentation Index

Documentation for Local AI Platform.

## Core Architecture

- [Status & Architecture Overview](STATUS.md) — Comprehensive status, architecture, features, and roadmap
- [Architecture](architecture.md) — Detailed architecture documentation

## Repository Intelligence

- [Symbol Graph](symbol-graph.md) — Language-independent symbol representation, Python AST extractor, 82 tests
- [Repository Index Service](STATUS.md#9-repository-index-service) — Structured index with symbol graph, relationships, statistics
- [Repository Scanner](STATUS.md#5-repository-scanner) — Directory walking, language detection, gitignore filtering
- [Relationship-Aware Ranking](relationship-ranking.md) — Relationship signals for context ranking
- [Relationship Extraction](relationship-extraction.md) — Language-independent extractors (CallExtractor), registry pattern
- [Workspace Dependency Graph](workspace-dependency-graph.md) — Immutable graph from RepositoryIndex with deterministic traversal
- [Repository Diagnostics](repository-diagnostics.md) — Dead code, orphan modules, large modules, graph statistics
- [Change Impact Analysis](change-impact.md) — Deterministic impact analysis with confidence scoring

## Context & Planning

- [Context Builder](context-builder.md) — Ranking engine, budget estimation, context composer
- [Context Package](context-package.md) — Context Package v2 documentation
- [Context Planning Engine](context-planning.md) — Intent detection, ContextPlan, PlanningStage
- [Planning Rules](planner-rules.md) — PlanningRule dataclass, RuleEngine, BUILTIN_RULES
- [Scoring Rules](scoring-rules.md) — RankingReason, score_candidate(), score_relationship(), additive scoring model

## Capabilities

- [Capability Framework](capabilities.md) — ExplainCapability, DebugCapability, RefactorCapability, CapabilityRegistry, CapabilityFactory, RetrievalProfile

## Advisors

- [Refactoring Advisor](advisors-refactoring.md) — Deterministic refactoring recommendations, confidence scoring, immutable models

## Serialization

- [Serialization Layer](serialization.md) — ProviderSerializer ABC, SerializerFactory, OpenAISerializer

## Benchmarking

- [Benchmark Framework](benchmark-framework.md) — Deterministic pipeline benchmarking without LLM calls

## Package Reference

| Package | Purpose | Key Exports |
|---------|---------|-------------|
| `packages.providers` | Provider abstraction | Provider, create_provider, register |
| `packages.providers.vllm` | vLLM provider | VLLMProvider |
| `packages.repository` | Repository scanner | scan, SourceFile, Directory, Statistics |
| `packages.repository.index` | Repository index | RepositoryIndex, IndexBuilder |
| `packages.repository.symbols` | Symbol graph | SymbolGraphView, Symbol, SymbolType |
| `packages.repository.relationships` | Relationship extraction | RelationshipExtractor, RelationshipRegistry, CallExtractor |
| `packages.repository.dependencies` | Dependency graph | DependencyGraphBuilder, WorkspaceDependencyGraph |
| `packages.repository.diagnostics` | Diagnostics | DiagnosticsEngine, analyzers |
| `packages.repository.impact` | Impact analysis | ChangeImpactAnalyzer, ImpactNode, ImpactReport |
| `packages.context` | Context builder | ContextBuilder, RankingEngine, ContextBudget, ContextComposer |
| `packages.context.scoring` | Scoring | score_candidate, score_relationship, RankingReason |
| `packages.capabilities` | Capability framework | Capability, CapabilityRegistry, CapabilityFactory |
| `packages.planning` | Context planning | ContextPlanner, ContextPlan, Intent |
| `packages.planning.rules` | Planning rules | PlanningRule, RuleEngine, BUILTIN_RULES |
| `packages.serializers` | Serialization | ProviderSerializer, SerializerFactory, ProviderRequest |
| `packages.pipeline` | Pipeline engine | PipelineEngine, PipelineStage, ProviderStage |
| `packages.benchmark` | Benchmarking | BenchmarkRunner, BenchmarkCase, BenchmarkReport |
| `packages.config` | Configuration | load_config, get_env_or_config |
