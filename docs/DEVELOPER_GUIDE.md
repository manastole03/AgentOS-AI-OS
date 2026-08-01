# Developer guide

## Prerequisites

Node.js 22, pnpm 10, Python 3.12, uv, Docker, kubectl, Helm 3, and Terraform 1.9+.

```bash
cp .env.example .env
make bootstrap
make dev
```

The web application is at `http://localhost:3000`, the gateway at `http://localhost:8080`, Prometheus at `http://localhost:9090`, and Grafana at `http://localhost:3001`.

## Development workflow

1. Add database changes through a new Alembic revision. Never edit an applied migration.
2. Put cross-service runtime primitives in `healthos_platform`; business rules stay in their owning service.
3. Author authorization at the API boundary. Frontend route hiding is convenience, not access control.
4. Never log request bodies, prompts, document text, tokens, emails, patient identifiers, or integration payloads.
5. Add unit tests for pure logic, integration tests for persistence/security boundaries, and contract tests for every new API.
6. Regenerate OpenAPI contracts with `uv run python scripts/export_openapi.py`.
7. Run `make verify` before opening a pull request.

## Commands

```bash
make lint             # Ruff and ESLint
make typecheck        # strict mypy and TypeScript
make test             # Python and TypeScript tests
make build            # production frontend and containers
make helm             # lint and render the production chart
make terraform        # format and validate AWS infrastructure
make openapi          # regenerate API contracts
make kustomize        # render Kustomize overlays
```

## Service conventions

- FastAPI handlers return Pydantic response models and sanitized RFC 7807 errors.
- All state-changing browser calls require CSRF validation.
- PostgreSQL transactions own durable consistency; Redis is for rate limits, cache, and queues.
- External requests use explicit timeouts, authenticated clients, request digests, and metadata-only audit logs.
- AI changes need a deterministic golden case plus an optional live evaluation case.
- New metrics must avoid high-cardinality or PHI labels. Use route templates, never raw URLs or user IDs.

## Release process

Protected tags build multi-architecture images, SBOMs, provenance, and keyless signatures. Production deployment is an environment-protected GitHub workflow that changes the Argo CD Helm image parameter. PreSync migration hooks must succeed before workload rollout.
