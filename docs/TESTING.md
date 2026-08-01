# Testing strategy

| Layer          | Location                                              | Purpose                                                                      |
| -------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| Unit           | `packages/**/tests`, `services/**/tests`              | Pure schemas, crypto, redaction, authorization, chunking, team policy        |
| Integration    | `test_*_integration.py`                               | PostgreSQL, Redis, sessions, portal CRUD, OCR, payments, tenant denial       |
| Agent quality  | `test_agent_quality.py`, `scripts/evaluate_agents.py` | Offline safety/authorization invariants and optional live routing golden set |
| API contract   | `test_openapi_contract.py`, generated OpenAPI         | Endpoint presence, response declarations, schema compatibility               |
| Load           | `tests/load/healthos.js`                              | Arrival-rate behavior and p95/p99/error SLO thresholds                       |
| Infrastructure | Helm/Kustomize/Terraform CI jobs                      | Rendering, schema conformance, formatting, provider validation               |
| Supply chain   | Trivy, Gitleaks, pip-audit, pnpm audit, SBOM, Cosign  | Secrets, dependencies, filesystem and image provenance                       |

Integration tests require disposable PostgreSQL/pgvector and Redis. Live agent evaluation is intentionally separate because it consumes provider capacity and may process prompts; run it only with synthetic data in an approved environment.

```bash
RUN_INTEGRATION_TESTS=1 uv run pytest --cov
ACCESS_TOKEN=... HEALTHOS_URL=https://staging.example.com uv run python scripts/evaluate_agents.py
ACCESS_TOKEN=... BASE_URL=https://staging.example.com k6 run tests/load/healthos.js
```
