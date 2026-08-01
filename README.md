# HealthOS

Production-oriented healthcare and insurance AI operating system with role-based portals, authentication, governed agent teams, integrations, observability, and cloud-native delivery infrastructure.

## Architecture

```text
Browser -> Next.js 15 -> API Gateway -> Core FastAPI API -> PostgreSQL + pgvector
                              |
                              +---------> AI API -> Redis Streams -> AI Workers
                                             |             LangGraph + DeepAgents
                                             +---------> LiteLLM -> OpenAI / Anthropic / Gemini
                                             +---------> PostgreSQL + pgvector
```

The gateway owns the public API origin and forwards only allowlisted headers. The API owns authentication and durable transactional data. The AI runtime is isolated so model workloads can scale and fail independently. Shared packages contain wire contracts, UI primitives, configuration, logging, and request context—not business rules.

## Project structure

```text
.
├── apps/
│   └── web/                         # Next.js 15 App Router, React 19, Tailwind, shadcn/ui
├── services/
│   ├── gateway/                     # Edge routing, CORS, aggregate health
│   ├── api/                         # Core FastAPI, JWT/OAuth, SQLAlchemy, Alembic
│   └── ai/                          # FastAPI, LangGraph/DeepAgents, RAG, memory, MCP, workers
├── packages/
│   ├── python/healthos_platform/    # Config, structured logs, middleware, common models
│   └── typescript/
│       ├── api-types/               # Shared HTTP contracts
│       ├── ui/                      # Shared shadcn/ui primitives
│       └── utils/                   # Shared TypeScript utilities
├── infra/
│   ├── docker/                      # Hardened multi-stage service images
│   ├── litellm/                     # Provider routing, retry, fallback, and cache policy
│   ├── kubernetes/                  # Kustomize base + development/production overlays
│   ├── observability/               # Prometheus, alerts, Grafana, OpenTelemetry
│   └── terraform/aws/               # Multi-AZ EKS, RDS, Redis, KMS, backup, secrets
├── deploy/
│   ├── helm/healthos/               # Production workload chart
│   └── argocd/                      # GitOps project, applications, platform add-ons
├── tests/load/                      # k6 SLO and capacity test
├── docs/                            # Architecture, API, compliance, operations, developer guides
├── .github/workflows/               # CI, signed releases, protected promotion
├── docker-compose.yml               # Full local stack
├── pyproject.toml                   # uv Python workspace and quality policy
├── pnpm-workspace.yaml              # pnpm JavaScript workspace
└── turbo.json                       # Monorepo task graph
```

## Quick start

Prerequisites: Node.js 20.9+, pnpm 10, Python 3.12, uv, Docker, and kubectl/Kustomize.

```bash
cp .env.example .env
# Replace JWT_SECRET_KEY and POSTGRES_PASSWORD in .env.
make bootstrap
make dev
```

For a complete synthetic demo—including database creation, migrations, five login accounts,
and linked records for every portal module—run:

```bash
cp .env.example .env
make demo
```

Demo credentials and a table-by-table data inventory are in the
[synthetic demo database guide](docs/DEMO_DATA.md).

Useful commands:

```bash
make lint       # TypeScript + Python lint
make typecheck  # TypeScript + strict mypy
make test       # All test suites
make build      # Application and container builds
make migrate    # Alembic upgrade in Docker Compose
make seed-demo  # Idempotently load all synthetic sample data
make kustomize  # Render both Kubernetes overlays
make openapi    # Regenerate checked API contracts
make helm       # Lint and render the Helm chart
make terraform  # Format and validate AWS infrastructure
make verify     # Run the local pre-merge quality gate
```

## API endpoints

| Service    | Liveness              | Readiness              |
| ---------- | --------------------- | ---------------------- |
| Gateway    | `/health/live`        | `/health/ready`        |
| Core API   | `/api/v1/health/live` | `/api/v1/health/ready` |
| AI runtime | `/ai/v1/health/live`  | `/ai/v1/health/ready`  |
| Web        | `/healthz`            | `/healthz`             |

Prometheus metrics are exposed internally at `/metrics` by the gateway, core API, and AI runtime. Interactive FastAPI documentation is enabled outside production; stable generated contracts live in [`docs/api`](docs/api/README.md).

### Domain API

Beyond authentication and the generic portal, the core API exposes seven routers over the
normalized clinical and insurance schema — 144 OpenAPI paths in total.

| Router                 | Covers                                                                          |
| ---------------------- | ------------------------------------------------------------------------------- |
| `/api/v1/clinical`     | Visit timeline, encounters, conditions, allergies, vitals, growth percentiles, immunizations and certificates, patient summary |
| `/api/v1/medications`  | Prescriptions with safety checks, dosage instructions, schedules, reminder generation, adherence |
| `/api/v1/scheduling`   | Real-time provider availability, race-safe booking, consultation payment, reschedule/cancel, telehealth |
| `/api/v1/labs`         | Test catalog, slot-and-test availability, orders, specimens, results, critical-result worklist |
| `/api/v1/coverage`     | Patient insurance: active policies, plain-language coverage, claims, ranked marketplace, purchase, loyalty |
| `/api/v1/payer`        | Insurer back office: products and plans, benefits, eligibility, claim adjudication, prior auth, cost estimation |
| `/api/v1/operations`   | Hospital operations, clinical documentation and coding, referrals, support cases, PHI access audit |

The scoping rules these routers follow — tenant, consent, and discovery — are described in the
[domain model guide](docs/architecture/domain-model.md#access-scoping--three-different-rules).
Getting them wrong is the most likely source of a bug, so read that section before adding an
endpoint.

## Authentication

HealthOS provides one identity service with role-specific registration and login for patients, doctors, hospitals, insurers, and administrators. Public administrator registration is intentionally unavailable.

| Capability             | Endpoint                                                                          |
| ---------------------- | --------------------------------------------------------------------------------- |
| Patient registration   | `POST /api/v1/auth/signup/patient`                                                |
| Doctor registration    | `POST /api/v1/auth/signup/doctor`                                                 |
| Hospital registration  | `POST /api/v1/auth/signup/hospital`                                               |
| Insurance registration | `POST /api/v1/auth/signup/insurance`                                              |
| Role-specific login    | `POST /api/v1/auth/login/{account_type}`                                          |
| Verify/resend OTP      | `POST /api/v1/auth/otp/verify`, `POST /api/v1/auth/otp/resend` (email and mobile) |
| Google OpenID Connect  | `GET /api/v1/auth/google/{account_type}`                                          |
| Refresh/logout         | `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`                           |
| Password reset         | `POST /api/v1/auth/password/forgot`, `POST /api/v1/auth/password/reset`           |
| Profile                | `GET/PATCH /api/v1/users/me`                                                      |
| Sessions               | `GET/DELETE /api/v1/auth/sessions`                                                |

Run migrations and create the first administrator through the non-public operational command:

```bash
uv run alembic -c services/api/alembic.ini upgrade head
uv run healthos-create-admin --email admin@example.com
```

Passwords use Argon2id. OTPs and refresh tokens are stored only as hashes. Browser refresh tokens are HttpOnly, session-scoped, rotated on every use, and protected by double-submit CSRF validation. API authorization revalidates user state, token version, session revocation, roles, and permissions against PostgreSQL.

Google OAuth is inactive until client credentials are supplied. A new Google identity may create a patient account; professional and organization identities must first register their licensing or registration details and then link Google using the same verified email.

## AI operating system

The AI API authenticates every request against the core API's revocable session endpoint. Team access is RBAC-scoped by account type. Prompts, results, and agent messages are application-encrypted; audit records contain metadata and digests, never prompt bodies.

| Capability                | Endpoint                                                  |
| ------------------------- | --------------------------------------------------------- |
| Authorized team catalog   | `GET /ai/v1/agents`                                       |
| Synchronous or queued run | `POST /ai/v1/runs`                                        |
| Run state/result          | `GET /ai/v1/runs/{id}`                                    |
| Run event stream          | `GET /ai/v1/runs/{id}/events`                             |
| Knowledge ingestion       | `POST /ai/v1/documents`                                   |
| Long-term memory          | `GET/POST /ai/v1/memories`, `DELETE /ai/v1/memories/{id}` |
| Administrative audit      | `GET /ai/v1/audit`                                        |
| MCP catalog server        | `/mcp`                                                    |

`execution_mode=async` writes to a Redis Stream consumed by independently scalable workers. `memory_mode=read_write` is an explicit opt-in; the default allows retrieval but not autonomous durable writes. Provider selection uses stable internal aliases and LiteLLM handles credentials, retry, fallback, and caching.

See the [AI architecture guide](docs/architecture/ai-operating-system.md) for team boundaries, data flow, safety controls, and extension points.

## Application portals

The authenticated web application now provides complete, responsive workspaces for patients, doctors, hospitals, insurers, and platform administrators. Each workspace includes live dashboard metrics, searchable operational records, create/update/delete workflows, status management, notifications, and secure documents.

Integrated workflows include local or external OCR, FHIR patient synchronization, payer eligibility/claims operations, idempotent payment intents with signed webhooks, SMTP/webhook notifications, governed AI assistance, user administration, audit trails, and dependency monitoring.

Portal APIs are rooted at `/api/v1/portal`; the role-aware web routes are rooted at `/portal/{module}`. See the [portal and integration architecture](docs/architecture/application-portals.md) for the resource model, access boundaries, and provider configuration.

Navigation, forms, dashboards, content, and workflow state machines are published as
versioned database definitions. Authenticated clients load `/api/v1/app-manifest`; tenant
overrides take precedence over global defaults without weakening server-side authorization.
Typed consent grants can authorize an individual or an organization and are checked before
legacy portal consent records during the additive migration period.

## Production operations

The local stack includes Prometheus at `http://localhost:9090`, Grafana at `http://localhost:3001`, and an OpenTelemetry collector. Production uses three-replica, zone-spread workloads with HPA, disruption budgets, default-deny network policy, managed Multi-AZ data services, External Secrets, Argo CD reconciliation, immutable signed images, and pre-deployment database migrations.

Start with the [production architecture](docs/architecture/production.md), [developer guide](docs/DEVELOPER_GUIDE.md), [testing strategy](docs/TESTING.md), [backup/recovery runbook](docs/operations/BACKUP_RECOVERY.md), and [incident response runbook](docs/operations/INCIDENT_RESPONSE.md). AWS provisioning instructions are in the [Terraform guide](infra/terraform/aws/README.md); GitOps bootstrap is in the [Argo CD guide](deploy/argocd/README.md).

The [HIPAA readiness matrix](docs/compliance/HIPAA_READINESS.md) maps technical evidence to required operational controls. It is deliberately a readiness baseline—not a certification or substitute for risk analysis, policies, workforce controls, vendor BAAs, and legal/compliance review.

## Engineering guardrails

- Configuration is environment-driven and validated at process start.
- Secrets use `SecretStr` and are not included in structured log events.
- JSON logs, correlation IDs, dependency probes, non-root containers, read-only Kubernetes filesystems, resource limits, network policies, HPA, and disruption budgets are provided.
- PostgreSQL schema changes go through Alembic. The initial migration enables pgvector.
- CI gates formatting, lint, strict type checks, unit/integration/agent/API tests, builds, Helm/Kustomize/Terraform validation, load-test contracts, dependency audit, secret scanning, and container scanning.

Read the [service-boundary ADR](docs/architecture/0001-service-boundaries.md), [deployment guide](docs/architecture/deployment.md), [security baseline](docs/architecture/security.md), and [portal architecture](docs/architecture/application-portals.md) before extending domain code.
