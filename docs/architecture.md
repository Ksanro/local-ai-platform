# Local AI Platform Architecture

Version: 0.1
Status: Draft
License: Apache 2.0

---

# Vision

Local AI Platform is a self-hosted developer intelligence platform that improves coding agents through repository intelligence, context optimization, long-term memory and a unified inference gateway.

The platform is model agnostic, provider agnostic and agent agnostic.

---

# Design Principles

- Local First
- Production Ready
- Simple Before Smart
- Performance First
- Measurable Improvements
- Provider Agnostic
- Agent Agnostic
- Stateless Components Where Possible
- Composition Over Coupling

---

# Goals

## Current

- OpenAI compatible Gateway
- Multiple Provider Support
- Repository Intelligence
- Context Builder
- Long-term Memory
- Metrics
- Benchmarks

## Future

- DSPARK Integration
- Semantic Retrieval
- Agent Orchestration
- Multi-model Routing
- Prompt Optimization

---

# High Level Architecture

```
                VS Code

                   │

          Cline / Claude Code

                   │

        Local AI Platform Gateway

                   │

        ┌──────────┴──────────┐

        │                     │

 Context Engine        Provider Layer

        │                     │

 Repository        vLLM / Ollama / OpenAI

        │

     Memory
```

---

# Components

## Gateway

Responsibilities

- REST API
- Authentication
- Validation
- Streaming
- Metrics
- Logging

Contains no business logic.

---

## Provider Layer

Responsibilities

- Unified inference interface
- Provider registration
- Health checks
- Model discovery
- Request forwarding

Supported providers

- vLLM
- OpenAI
- Ollama
- LM Studio

Future

- llama.cpp
- TensorRT-LLM

---

## Context Engine

Responsibilities

- Build optimized prompts
- Remove redundant context
- Compress history
- Assemble repository information

Future feature.

---

## Repository Intelligence

Responsibilities

- Repository indexing
- Symbol graph
- Dependency graph
- Code search
- Metadata extraction

Future feature.

---

## Memory

Responsibilities

- Long-term conversation memory
- Project memory
- User preferences
- Repository knowledge

Future feature.

---

# Request Flow

```
Agent

↓

Gateway

↓

Provider

↓

LLM

↓

Response

↓

Gateway

↓

Agent
```

Future

```
Agent

↓

Gateway

↓

Context Builder

↓

Repository Intelligence

↓

Memory

↓

Provider

↓

LLM
```

---

# Package Structure

```
apps/

packages/

tests/

docs/
```

Applications contain entry points only.

Business logic belongs inside packages.

---

# Dependency Rules

Allowed

Gateway

↓

Packages

↓

Providers

Forbidden

Providers importing Gateway

Applications importing Applications

Circular imports

---

# Configuration

Environment variables only.

Configuration is loaded through Pydantic Settings.

---

# Logging

Structured logging.

Every request includes

- request_id
- duration
- provider
- model

---

# Metrics

Prometheus compatible.

Future metrics include

- latency
- tokens/sec
- cache hits
- context size
- provider health

---

# Testing Strategy

- Unit tests
- Integration tests
- Gateway tests
- Provider tests
- Benchmark tests

---

# Roadmap

Sprint 0

- Bootstrap
- Gateway
- Provider

Sprint 1

- Repository Indexer
- Context Builder

Sprint 2

- Memory
- Semantic Search

Sprint 3

- DSPARK

Sprint 4

- Multi-model Routing

---

# Non Goals

The platform is not

- an LLM
- a training framework
- a vector database
- a Kubernetes platform
- a cloud service

---

# Definition of Done

A feature is complete only if

- tests pass
- typed
- documented
- benchmarked
- reviewed

---

# Architecture Decision Record

Major architectural decisions are recorded in `/docs/adr`.

This document describes the current architecture.

ADRs explain why decisions were made.
