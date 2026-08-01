# Deployment guide

## Local

Copy `.env.example` to `.env`, replace local secrets, and run `make dev`. The gateway is available at `http://localhost:8080`, the UI at `http://localhost:3000`, core API docs at `http://localhost:8000/docs`, and AI docs at `http://localhost:8001/docs`.

## Kubernetes

Render either overlay with `kubectl kustomize infra/kubernetes/overlays/<environment>`. The development overlay includes single-node PostgreSQL and Redis for disposable clusters. Production intentionally expects managed data services.

Before applying production manifests:

1. Replace the generated `healthos-secrets` with External Secrets, Sealed Secrets, or your cloud secrets controller.
2. Set registry names and immutable image tags/digests.
3. Set the public hostname, TLS issuer/secret, OAuth redirect URI, CORS policy, and ingress class.
4. Run both API and AI Alembic histories before rollout. The base includes an `ai-migrations` Job; production delivery should wait for it before deploying API/worker pods.
5. Verify network policies against the cluster CNI and managed database endpoints.

GitHub Actions publishes versioned images on `v*` tags. Cluster rollout is intentionally environment-owned because credentials, promotion rules, and deployment controllers differ by organization.

Authentication additionally requires distinct access-JWT, refresh-JWT, and OTP HMAC secrets; Google OAuth credentials and exact redirect URIs; and SMTP credentials. Production configuration validation deliberately prevents API startup when secrets remain placeholders, cookies are not secure, or SMTP delivery is absent.

AI deployments additionally require a valid Fernet key (`AI_DATA_ENCRYPTION_KEY`), a 16/24/32-byte LangGraph AES key, the LiteLLM master key, and at least one provider credential. Scale `ai` for HTTP traffic and `ai-worker` for queue depth/model throughput. LiteLLM and both AI workloads are stateless; PostgreSQL checkpoints, pgvector data, and Redis Streams carry durable state.
