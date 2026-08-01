# AI operating system

## Runtime flow

1. The AI API revalidates the bearer token or access cookie through the core authentication service and derives authorized teams.
2. A run record stores an encrypted prompt, owner scope, execution policy, and SHA-256 digest. Async runs enter a Redis consumer-group stream.
3. LangGraph routes the request, creates a bounded action plan, retrieves tenant-scoped pgvector knowledge and user-scoped memories, executes the primary DeepAgents team and up to two collaborators, then synthesizes one response.
4. DeepAgents may delegate to named specialists and use only registered local or allowlisted remote MCP tools. Team messages are encrypted and durable for the run.
5. The response is encrypted before persistence. Prometheus/OpenTelemetry record operational telemetry; the append-only audit table records event metadata without prompt or tool-argument content.

## Teams and authorization

| Team                  | Primary purpose                        | Account access                      |
| --------------------- | -------------------------------------- | ----------------------------------- |
| Patient               | Navigation, education, coordination    | patient, doctor, hospital, admin    |
| Insurance             | Benefits, claims, prior authorization  | patient, hospital, insurance, admin |
| Clinical              | Clinician-facing evidence synthesis    | doctor, hospital, admin             |
| Administrative        | Operations and compliance support      | doctor, hospital, insurance, admin  |
| Infrastructure        | Reliability, security, data operations | admin                               |
| Document Intelligence | Classification, extraction, retrieval  | all authenticated account types     |

The safety prompt prohibits autonomous diagnosis, treatment, or final coverage decisions. Retrieval citations, uncertainty, minimum-necessary data, and qualified human review are mandatory for high-impact outputs.

## Persistence and isolation

- LangGraph PostgreSQL checkpoints provide resumable thread state and use AES serialization.
- `ai_knowledge_chunks` and `ai_long_term_memories` use 1536-dimensional pgvector embeddings.
- Knowledge is tenant-scoped; memory is additionally owner- and team-scoped.
- Durable memory writes require `memory_mode=read_write` on each run.
- Prompts, outputs, and inter-team messages use authenticated Fernet encryption.
- Redis Streams provide consumer-group delivery; workers reclaim stale pending entries after a crash.

## Provider and MCP boundary

Application code addresses `healthos-openai`, `healthos-anthropic`, `healthos-gemini`, and `healthos-embedding`. LiteLLM owns real provider model identifiers, secrets, fallback, retry, and cache configuration. This keeps provider credentials out of agent code.

Remote MCP servers are configured through `MCP_SERVERS` and filtered with `MCP_TOOL_ALLOWLIST`. The mounted HealthOS MCP server intentionally exposes only a non-sensitive team catalog and safety policy; authenticated execution remains behind REST authorization.

## Governed action proposals

Completed runs may create an allowlisted action proposal, but cannot directly perform the
mutation. Arguments are application-encrypted, while the proposal exposes only its SHA-256
digest, evidence references, warnings, affected resources, risk level, and expiry. Confirmation
requires both the exact digest and a proposal-specific single-use token. Confirmation and
cancellation are actor- and tenant-bound, row-locked, time-limited, and written to the sealed AI
audit chain. High-impact actions remain pending for execution through the core domain command
API and accountable human-review policy.

## Scaling

HTTP pods, queue workers, and LiteLLM replicas scale independently. The API does not run background tasks in-process. Runs are idempotent after completion, queue messages are acknowledged only after processing, and Kubernetes termination grace periods allow active workers to finish. In production, use a queue-depth external metric alongside the supplied CPU HPA.
