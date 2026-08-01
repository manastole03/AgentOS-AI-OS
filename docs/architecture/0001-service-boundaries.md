# ADR 0001: Initial service boundaries

- Status: Accepted
- Date: 2026-06-30

## Context

HealthOS needs an enterprise foundation without prematurely encoding healthcare or insurance domain assumptions. AI workloads also have different scaling, dependency, and failure characteristics than transactional APIs.

## Decision

Start with four deployable units: the Next.js web application, an edge API gateway, the core FastAPI API, and an isolated FastAPI AI runtime. Share only domain-agnostic platform primitives and wire contracts. PostgreSQL with pgvector is the durable system of record; Redis is ephemeral coordination and caching infrastructure.

The AI runtime exposes construction seams for LangGraph and DeepAgents but no executable domain graph. Future bounded contexts should own their graph state, tools, persistence schema, authorization policy, and evaluation suite.

## Consequences

- Services can scale and deploy independently.
- The gateway is the only public API origin.
- Shared packages must remain backward-compatible or be versioned with consumers.
- New services require clear operational or domain isolation; folders are not created merely for conceptual layers.
