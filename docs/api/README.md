# API documentation

The authoritative machine-readable contracts are generated from FastAPI:

- `openapi-core.json` — authentication, profile, portal, administration, documents, payments, and integrations.
- `openapi-ai.json` — agents, runs, event streams, RAG documents, memory, and audit endpoints.

Regenerate after changing a route or schema:

```bash
uv run python scripts/export_openapi.py
```

CI publishes both contracts as the `openapi-contracts` artifact. Interactive Swagger documentation is available at `/docs` on the core and AI services outside production. Production disables interactive documentation to reduce public attack surface; publish the generated contracts through an authenticated developer portal instead.

All errors use `application/problem+json` and include a non-sensitive error ID, request ID, and distributed trace ID when tracing is active. Validation errors report locations and messages but never echo submitted values.
