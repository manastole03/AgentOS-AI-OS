

<!-- ===== raw scout: a38c9a0f8cdf10beb ===== -->

## 1. Alembic migration file conventions

Directory: `/Users/manastole/Projects/Healthcare/services/api/migrations/versions/` — files `0001_enable_vector.py` … `0008_job_watch.py`.

**Revision id format:** zero-padded 4-digit string, `"0001"`…`"0008"`, matching the filename prefix `NNNN_snake_case_slug.py`. Not hashes. `alembic.ini` sets no `file_template`, so filenames are written by hand.

**File header (identical in every file):**
```python
"""<One-line imperative summary ending in a period.>

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql   # only when UUID/JSONB/CITEXT used

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```
Note the docstring has **no** `Create Date:` line even though `/Users/manastole/Projects/Healthcare/services/api/migrations/script.py.mako` emits one — hand-written files drop it. Both `upgrade() -> None` and `downgrade() -> None` are always defined and annotated.

**Shared helper repeated verbatim in 0003 and 0008** (copied per-file, not imported):
```python
def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]
```
Splatted into `create_table` as `*timestamps()` at the end of the column list. Append-only tables (`portal_notifications`, `integration_events`, `job_watch_alert_deliveries`) declare only `created_at` inline instead.

**Tables:** `op.create_table("name", sa.Column(...), ..., *timestamps(), sa.UniqueConstraint(...), sa.CheckConstraint(...))` — constraints are passed positionally inside `create_table`, not added afterward. PKs are `sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)` with **no** server-side default (app supplies `uuid4`); only raw-SQL seed inserts use `gen_random_uuid()`. FKs are inline on the column: `sa.ForeignKey("users.id", ondelete="CASCADE" | "SET NULL" | "RESTRICT")`.

**Indexes:** explicit `op.create_index("<name>", "<table>", ["col", ...])`, names always written out. Two styles both in use: a dict-loop for bulk (0003) —
```python
for name, columns in {"ix_portal_records_tenant_id": ["tenant_id"], ...}.items():
    op.create_index(name, "portal_records", columns)
```
— and one call per index (0008). Naming: single-column FK/scalar indexes are `ix_<table>_<column>`; composite/query-shaped ones get a short semantic name (`ix_portal_records_scope`, `ix_job_watch_posting_active`, `ix_notifications_recipient`). The declarative `NAMING_CONVENTION` in `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/base.py` (`ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_...`, `pk_...`) is NOT what migrations use for indexes — migrations name them literally.

**String lengths:** 0003 uses positional `sa.String(64)`; 0008 uses keyword `sa.String(length=32)`. Both accepted; be consistent within one file.

**server_default style:**
- timestamps → `sa.func.now()`
- booleans → `sa.false()` / `sa.true()`
- integers → string literal, e.g. `server_default="0"`, `server_default="5"`
- JSONB → string literal `"{}"` or `"[]"`
- strings → bare literal, e.g. `server_default="active"`, `"in_app"`, `"stored"`, `"email"`

**Enum handling: no PostgreSQL native ENUM types anywhere.** Enum-valued columns are `sa.String(32)` plus a named `sa.CheckConstraint` listing the allowed values:
```python
sa.CheckConstraint("account_type IN ('patient','doctor','hospital','insurance','admin')", name="valid_account_type")
sa.CheckConstraint("source_type IN ('greenhouse', 'lever', 'ashby')", name="job_watch_source_type")
```
Widening a value set = `op.drop_constraint(...)` / `op.create_check_constraint(name, table, condition)` (see 0004, 0005). ORM side matches: `Enum(UserStatus, values_callable=enum_values, native_enum=False, length=32)` in `db/models.py`.

**Data seeding:** two patterns — `op.bulk_insert(sa.table(...), [dicts])` with lightweight `sa.table`/`sa.column` shells (0003, permissions/role_permissions), and `bind = op.get_bind()` + `bind.execute(sa.text("INSERT ..."), {params})` with `CAST(:x AS jsonb)` and `json.dumps()` for JSONB (0007). Raw DDL/DML via `op.execute("...")` for extensions (`CREATE EXTENSION IF NOT EXISTS vector | citext | pgcrypto`), triggers/functions, and seed cleanup.

**downgrade():** exact inverse, reverse order. 0003 drops tables in reverse dependency order via a list loop and deletes seeded rows first. 0008 explicitly `op.drop_index(name, table_name=...)` before each `op.drop_table(...)`. 0007 (data-only) downgrades with a single scoped `DELETE`.

## 2. CURRENT HEAD REVISION

**`"0008"`** — file `/Users/manastole/Projects/Healthcare/services/api/migrations/versions/0008_job_watch.py`.

Full chain traced from `revision`/`down_revision` in all eight files, strictly linear, no branches, no duplicate ids:

`0001` (down_revision `None`) → `0002` → `0003` → `0004` → `0005` → `0006` → `0007` → `0008`

No revision declares `0008` as its `down_revision`, so 0008 is the sole head. **A new migration must use `revision: str = "0009"`, `down_revision: str | None = "0008"`, filename `0009_<slug>.py`.**

(Separate, unrelated Alembic tree for the AI service at `/Users/manastole/Projects/Healthcare/services/ai/alembic.ini` with its own `0001`–`0003`; head there is `0003`. `make migrate` runs `alembic upgrade head` in both.)

## 3. Settings / config

Two classes, both pydantic-settings.

**Base — `/Users/manastole/Projects/Healthcare/packages/python/healthos_platform/src/healthos_platform/config.py`:**
```python
class Environment(StrEnum):  LOCAL="local" TEST="test" DEVELOPMENT="development" STAGING="staging" PRODUCTION="production"
class LogFormat(StrEnum):    CONSOLE="console" JSON="json"

class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=False)
```
No `env_prefix`, so **env var name = field name upper-cased**. Fields: `service_name` (required, no default), `environment: Environment = LOCAL`, `log_level: str = "INFO"`, `log_format: LogFormat = CONSOLE`, `cors_origins: list[str] = ["http://localhost:3000"]`, `otel_exporter_otlp_endpoint: str = ""`, `otel_trace_sample_ratio: float = 0.1` (`ge=0, le=1`). A `@model_validator(mode="after") validate_production_baseline` rejects non-JSON log format and wildcard CORS in production.

**Service — `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/config.py`, `class Settings(BaseServiceSettings)`.** Every field (env var = UPPER_SNAKE of the name):

| field / env var | type | default |
|---|---|---|
| SERVICE_NAME | str | `"healthos-api"` |
| DATABASE_URL | SecretStr | `postgresql+asyncpg://healthos:change-me@localhost:5432/healthos` |
| REDIS_URL | SecretStr | `redis://localhost:6379/0` |
| JWT_SECRET_KEY | SecretStr | `local-development-secret-must-be-32-chars` |
| JWT_REFRESH_SECRET_KEY | SecretStr | `local-refresh-secret-must-also-be-32-chars` |
| JWT_ALGORITHM | str | `HS256` |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | int | 15 |
| JWT_REFRESH_TOKEN_EXPIRE_DAYS | int | 30 |
| REFRESH_ROTATION_GRACE_SECONDS | int | 5 |
| JWT_ISSUER | str | `healthos` |
| JWT_AUDIENCE | str | `healthos-api` |
| OTP_SECRET_KEY | SecretStr | `local-otp-secret-must-also-be-32-characters` |
| OTP_EXPIRE_MINUTES | int | 10 |
| OTP_MAX_ATTEMPTS | int | 5 |
| AUTH_COOKIE_SECURE | bool | False |
| AUTH_COOKIE_DOMAIN | str \| None | None |
| ALLOWED_HOSTS | list[str] | `["localhost","127.0.0.1","testserver"]` |
| ACCESS_COOKIE_NAME | str | `healthos_access` |
| REFRESH_COOKIE_NAME | str | `healthos_refresh` |
| CSRF_COOKIE_NAME | str | `healthos_csrf` |
| GOOGLE_CLIENT_ID | str | `""` |
| GOOGLE_CLIENT_SECRET | SecretStr | `""` |
| GOOGLE_REDIRECT_URI | AnyHttpUrl | `http://localhost:8000/api/v1/auth/google/callback` |
| FRONTEND_AUTH_CALLBACK_URL | AnyHttpUrl | `http://localhost:3000/auth/callback` |
| SMTP_HOST / SMTP_USERNAME / SMTP_FROM_EMAIL | str | `""` |
| SMTP_PORT | int | 587 |
| SMTP_PASSWORD | SecretStr | `""` |
| SMTP_USE_TLS | bool | True |
| SMS_WEBHOOK_URL | str | `""` |
| SMS_WEBHOOK_TOKEN | SecretStr | `""` |
| DOCUMENT_MAX_BYTES | int | 10_485_760 |
| OCR_API_URL / FHIR_BASE_URL / INSURANCE_API_URL / NOTIFICATION_WEBHOOK_URL | str | `""` |
| OCR_API_KEY / FHIR_ACCESS_TOKEN / INSURANCE_API_KEY / STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET | SecretStr | `""` |
| STRIPE_API_URL | str | `https://api.stripe.com/v1` |
| JOB_WATCH_SCAN_INTERVAL_SECONDS | int | 300 |

Plus inherited ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, CORS_ORIGINS, OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_TRACE_SAMPLE_RATIO. `@model_validator(mode="after") reject_placeholder_production_secret` enforces, in production only: no `replace`/`local-` substring and ≥32 chars in the three secrets, `AUTH_COOKIE_SECURE` true, SMTP host+from configured, SMS webhook configured, `JWT_ALGORITHM in {RS256, ES256}`, `"ssl=require"` present in DATABASE_URL, REDIS_URL starting with `rediss://`. Accessor: `@lru_cache def get_settings() -> Settings`. List-valued env vars are JSON-encoded in `.env` (see `/Users/manastole/Projects/Healthcare/.env.example`).

**How the DB URL is built:** it is NOT assembled from host/port/user/password parts. `DATABASE_URL` is one whole DSN string (`postgresql+asyncpg://...`) read into a `SecretStr`. Consumers call `get_settings().database_url.get_secret_value()`. `/Users/manastole/Projects/Healthcare/services/api/migrations/env.py` does exactly that at import time: `config.set_main_option("sqlalchemy.url", get_settings().database_url.get_secret_value())`, overriding the placeholder in `alembic.ini`. The runtime engine comes from `create_database_engine(url)` in `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/session.py` (`pool_pre_ping=True, pool_size=10, max_overflow=20`).

**How to add a new setting:** add a typed, defaulted attribute on `Settings` (use `SecretStr` for any credential, `Field(default_factory=...)` for mutable defaults); add the UPPER_SNAKE name to `/Users/manastole/Projects/Healthcare/.env.example` (and `.env`); if it must be present in production, add the check inside `reject_placeholder_production_secret`. Nothing else — `BaseSettings` picks it up automatically, and `get_settings()` is `lru_cache`d (call `get_settings.cache_clear()` in tests).

**alembic.ini** (`/Users/manastole/Projects/Healthcare/services/api/alembic.ini`): `script_location = %(here)s/migrations`, `prepend_sys_path = %(here)s/src`, placeholder `sqlalchemy.url` (overridden by env.py), plus standard logging sections (root WARN, sqlalchemy WARN, alembic INFO). No `file_template`, `version_locations`, or `timezone`. **env.py** uses `async_engine_from_config` + `asyncio.run(run_migrations_online())`, `target_metadata = Base.metadata`, `compare_type=True`, `poolclass=NullPool`, and imports `healthos_api.db.models  # noqa: F401` for autogenerate — so any new table's ORM model must be importable from `db/models.py`.

## 4. healthos_platform logging + middleware helpers

Package root `/Users/manastole/Projects/Healthcare/packages/python/healthos_platform/src/healthos_platform/`. `__init__.py` re-exports only `BaseServiceSettings`, `Environment`, `ErrorDetail`, `ErrorResponse`, `HealthResponse`; everything else is imported from its submodule.

**`logging.py`** (structlog + stdlib unified pipeline)
- `configure_logging(*, level: str, log_format: LogFormat) -> None` — processors: `merge_contextvars`, `add_log_level`, `add_logger_name`, ISO/UTC `TimeStamper`, `_drop_color_message`, `_redact_sensitive_data`, `StackInfoRenderer`, `format_exc_info`, then `JSONRenderer()` or `ConsoleRenderer(colors=isatty)`.
- `get_logger(name: str = "healthos") -> structlog.stdlib.BoundLogger`
- Automatic PHI/secret redaction: keys matching `SENSITIVE_KEY = re.compile(r"(authorization|cookie|token|secret|password|otp|email|phone|patient|prompt|content|body|key)", re.IGNORECASE)` are replaced with `"[REDACTED]"`, recursing through mappings and sequences. Practical consequence: any log kwarg whose name contains `key`, `patient`, `body`, `content`, etc. will be redacted — name fields accordingly (e.g. `board_key` would be redacted).

**`middleware.py`** — `RequestContextMiddleware(app: ASGIApp)`; pure-ASGI. Reads/creates `X-Request-ID`, sets `scope["state"]["request_id"]`, binds `request_id` into structlog contextvars, echoes `X-Request-ID` on the response, and emits one `request_completed` info log per request with `method`, `route`, `status_code`, `duration_ms`; clears contextvars in `finally`.

**`observability.py`** — `PrometheusMiddleware(app, *, service_name: str)` (skips `/metrics`); metrics `healthos_http_requests_total{service,method,route,status}`, `healthos_http_request_duration_seconds{service,method,route}`, `healthos_http_requests_in_flight{service}`; `metrics_response() -> Response`; `configure_tracing(app: FastAPI, *, service_name: str, endpoint: str, sample_ratio: float) -> None` (no-op when endpoint empty; OTLP gRPC, `ParentBased(TraceIdRatioBased)`, FastAPI + HTTPX instrumentation, excludes `/health/live,/health/ready,/metrics`).

**`errors.py`** — `install_error_handlers(app: FastAPI) -> None` registering handlers for `HTTPException`, `RequestValidationError` (422 with per-field `errors[]`), and bare `Exception` (500, logs `unhandled_exception` with `error_id`). All responses are RFC 7807 `application/problem+json` with `type/title/status/detail/instance/error_id/request_id/trace_id`.

**`rate_limit.py`** — `DistributedRateLimitMiddleware(app, *, redis: Redis | None = None, service_name: str, default_limit: int = 300, window_seconds: int = 60)`; Redis Lua fixed-window keyed by client IP + path prefix, `limit_for(path)` returns 20 for auth/OTP/password and `/ai/v1/runs`, 60 for `/documents`, else default; fails open on `RedisError`; sets `X-RateLimit-Limit`/`-Remaining`, 429 + `Retry-After`. `RequestBodyLimitMiddleware(app, *, default_bytes=2_097_152, document_bytes=11_010_048)` → 413 problem+json.

**`security.py`** — `SecurityHeadersMiddleware(app, *, production: bool)`: nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, COOP/CORP `same-origin`, `Permissions-Policy`, CSP `default-src 'none'; frame-ancestors 'none'`, and HSTS `max-age=63072000; includeSubDomains; preload` in production.

**`models.py`** — `HealthResponse(service, status: Literal["ok","degraded"], version, timestamp, checks: dict[str,str])`, `ErrorDetail(code, message, context)`, `ErrorResponse(error, request_id)`.

## 5. `services/api/src/healthos_api/core/` contents

Only three files.

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/__init__.py`** — docstring `"""Core service concerns."""` only; no re-exports. Import from the submodules directly.

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/security.py`** — the auth dependency layer (this is where new routers get authn/authz):
```python
bearer_scheme = HTTPBearer(auto_error=False)

@dataclass(slots=True)
class AuthContext:
    user: User
    session: AuthSession
    claims: AccessTokenClaims
    tenant_id: UUID

async def current_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext

def require_permissions(*required: str) -> Callable[..., Awaitable[AuthContext]]
def require_roles(*required: str) -> Callable[..., Awaitable[AuthContext]]
async def enforce_csrf(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None
def client_context(request: Request) -> ClientContext
def _unauthorized() -> HTTPException          # 401 + WWW-Authenticate: Bearer
```
Behavior worth knowing: the token comes from the `Authorization` bearer header *or* the `settings.access_cookie_name` cookie; the session is validated against `user.status == ACTIVE`, `user.token_version == claims.ver`, `session.revoked_at is None`, `session.expires_at > now`; `tenant_id` resolves to the user's primary active `OrganizationMembership.organization_id`, falling back to `user.id`. `require_permissions` needs the required set to be a subset of granted (permission strings like `portal:read`, `portal:write`, `documents:manage`, `integrations:execute`, `system:admin` seeded in migration 0003); `require_roles` needs any intersection. `enforce_csrf` skips when a bearer header is present and no refresh cookie exists, else does `hmac.compare_digest` between the `csrf_cookie_name` cookie and the `X-CSRF-Token` header.

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/middleware.py`** — `SecurityHeadersMiddleware(app: ASGIApp, *, production: bool)`, a service-local near-duplicate of `healthos_platform.security.SecurityHeadersMiddleware`. Differences from the platform version: no COOP/CORP headers and HSTS `max-age=31536000; includeSubDomains` (no `preload`). Two implementations of the same class name exist — check `healthos_api/main.py` (or app factory) for which one is actually mounted before touching either.

There is no `core/exceptions.py`; error handling lives in `healthos_platform.errors.install_error_handlers`.


<!-- ===== raw scout: a3881908ad1757c2a ===== -->

I have everything needed.

# HealthOS repo reference

Root: `/Users/manastole/Projects/Healthcare`

---

## 1. Make targets (`/Users/manastole/Projects/Healthcare/Makefile`)

| Target | Runs |
|---|---|
| `bootstrap` | `corepack enable`; `pnpm install --frozen-lockfile=false`; `uv sync --all-packages --dev` |
| `dev` | `docker compose up --build` (foreground, all services) |
| `demo` | `docker compose up -d --build postgres redis api ai`; `docker compose run --rm api healthos-seed-demo`; `docker compose up -d --build` |
| `up` | `docker compose up -d --build` |
| `down` | `docker compose down --remove-orphans` (volumes preserved) |
| `format` | `pnpm format` (prettier --write .); `uv run ruff format .` |
| `lint` | `pnpm lint` (turbo run lint); `uv run ruff check .` |
| `test` | `pnpm test` (turbo run test); `uv run pytest --cov --cov-report=term-missing` |
| `test-integration` | `RUN_INTEGRATION_TESTS=1 uv run pytest -m integration` |
| `typecheck` | `pnpm typecheck`; `uv run mypy` |
| `build` | `pnpm build`; `docker compose build` |
| `migrate` | `docker compose run --rm api alembic upgrade head`; `docker compose run --rm ai alembic upgrade head` |
| `seed-demo` | depends on `migrate`, then `docker compose run --rm api healthos-seed-demo` |
| `openapi` | `uv run python scripts/export_openapi.py` |
| `kustomize` | `kubectl kustomize infra/kubernetes/overlays/{development,production} >/dev/null` |
| `helm` | `helm lint deploy/helm/healthos`; `helm template healthos deploy/helm/healthos --namespace healthos >/dev/null` |
| `terraform` | `terraform -chdir=infra/terraform/aws fmt -check -recursive`; `... init -backend=false`; `... validate` |
| `load-test` | `k6 run tests/load/healthos.js` |
| `job-watch-scan` | `docker compose run --rm job-watch-worker healthos-job-watch-scan` (one-shot, no `--loop`) |
| `verify` | `lint typecheck test openapi kustomize helm terraform` |
| `clean` | `pnpm clean`; `rm -rf .venv .pytest_cache .mypy_cache .ruff_cache` |

---

## 2. docker-compose (`/Users/manastole/Projects/Healthcare/docker-compose.yml`)

Project name `healthos`, single bridge network `healthos`. Named volumes: `postgres-data`, `redis-data`, `prometheus-data`, `grafana-data`.

| Service | Image / build | Host:container ports | Healthcheck | depends_on |
|---|---|---|---|---|
| `web` | `infra/docker/web.Dockerfile`, build arg `NEXT_PUBLIC_API_URL` | `3000:3000` | `wget -qO- http://localhost:3000/health`, 10s/3s/5 | gateway healthy |
| `gateway` | `python.Dockerfile` (`healthos-gateway`, `healthos_gateway.main:app`) | `8080:8000` | urllib GET `http://localhost:8000/health/live`, 10s/3s/5 | api healthy, ai healthy |
| `api` | `python.Dockerfile` (`healthos-api`), workdir `/app/services/api`, cmd `sh -c "alembic upgrade head && uvicorn healthos_api.main:app --host 0.0.0.0 --port 8000 --no-access-log"` | `8000:8000` | urllib GET `/api/v1/health/ready`, 10s/3s/**10** | postgres healthy, redis healthy |
| `ai` | `python.Dockerfile` (`healthos-ai`), workdir `/app/services/ai`, same `alembic upgrade head && uvicorn` pattern | `8001:8000` | urllib GET `/ai/v1/health/ready`, 10s/3s/**10** | postgres, redis, litellm, api (all healthy) |
| `ai-worker` | `healthos-ai` image, cmd `python -m healthos_ai.worker` | none | none | ai healthy; `deploy.replicas: 2` |
| `job-watch-worker` | `healthos-api` image, cmd `healthos-job-watch-scan --loop` | none | none | postgres, redis, api healthy |
| `litellm` | `ghcr.io/berriai/litellm:main-stable@sha256:19a879f9...` pinned by digest; cmd `--config /app/config.yaml --port 4000 --num_workers 2` | `4000:4000` | urllib GET `http://localhost:4000/health/liveliness`, 10s/5s/12 | postgres, redis healthy |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.128.0` | `4317:4317`, `4318:4318`, `9464:9464` | none | none |
| `prometheus` | `prom/prometheus:v3.4.1`, 15d retention | `9090:9090` | none | none |
| `grafana` | `grafana/grafana:12.0.2` | `3001:3000` | none | prometheus |
| `postgres` | `pgvector/pgvector:pg17` | `127.0.0.1:${POSTGRES_HOST_PORT:-55432}:5432` (loopback only) | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`, 5s/3s/10 | none |
| `redis` | `redis:7.4-alpine`, `--appendonly yes --maxmemory-policy noeviction` | `127.0.0.1:${REDIS_HOST_PORT:-56379}:6379` (loopback only) | `redis-cli ping`, 5s/3s/10 | none |

Volume mounts (all read-only bind mounts except data volumes):
- `litellm`: `./infra/litellm/config.yaml:/app/config.yaml:ro`
- `otel-collector`: `./infra/observability/otel-collector.yaml:/etc/otelcol/config.yaml:ro`
- `prometheus`: `./infra/observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro`, `./infra/observability/alerts.yml:/etc/prometheus/rules/alerts.yml:ro`, `prometheus-data:/prometheus`
- `grafana`: `./infra/observability/grafana/provisioning:/etc/grafana/provisioning:ro`, `./infra/observability/grafana/dashboards:/var/lib/grafana/dashboards:ro`, `grafana-data:/var/lib/grafana`
- `postgres`: `postgres-data:/var/lib/postgresql/data`, `./infra/docker/postgres/init.sql:/docker-entrypoint-initdb.d/01-vector.sql:ro`
- `redis`: `redis-data:/data`
- No source bind mounts anywhere — `make dev` rebuilds images; there is **no hot reload** for Python or the web app in compose.

Env wiring:
- YAML anchor `x-python-service` (`&python-service`) supplies `restart: unless-stopped`, `env_file: [{path: .env, required: false}]`, `networks: [healthos]`, plus an `environment` map with `ENVIRONMENT`, `LOG_FORMAT`, `DATABASE_URL`, `REDIS_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317`.
- **Gotcha:** every python service redefines `environment:`, and a YAML merge key replaces the whole map rather than deep-merging. Verified with `docker compose config`: `OTEL_EXPORTER_OTLP_ENDPOINT` is **absent from every service** — the anchor's OTLP endpoint is dead config. Traces only reach the collector if `OTEL_EXPORTER_OTLP_ENDPOINT` is set in `.env` (`.env.example` ships it empty). Same for `gateway`, which loses the anchor's `DATABASE_URL`/`REDIS_URL` (it does not need them, but they leak in from `.env` via `env_file`).
- Precedence: `environment:` > `env_file: .env` > image defaults. `${VAR:-default}` interpolation reads the root `.env` / shell env at compose parse time.
- `gateway` gets `API_SERVICE_URL=http://api:8000`, `AI_SERVICE_URL=http://ai:8000`, `CORS_ORIGINS='["http://localhost:3000","http://127.0.0.1:3000"]'`. Note `.env.example` sets `AI_SERVICE_URL=http://ai:8001`, which is wrong for in-network traffic (containers listen on 8000); the compose `environment:` override saves it, but anything reading `.env` directly gets the bad value.
- `api` and `job-watch-worker`: `ALLOWED_HOSTS='["localhost","127.0.0.1","testserver","api"]'`, `REDIS_URL=.../0`.
- `ai` and `ai-worker`: `REDIS_URL=.../1`, `LITELLM_BASE_URL=http://litellm:4000/v1`, plus local-only fallback secrets baked into compose: `LITELLM_MASTER_KEY:-local-litellm-master-key`, `AI_DATA_ENCRYPTION_KEY:-aGVhbHRob3MtbG9jYWwtYWkta2V5LTMyLWJ5dGVzISE=`, `LANGGRAPH_AES_KEY:-healthos-local-checkpoint-key-32`. `ai` additionally gets the LANGSMITH_* trio; `ai-worker` does not.
- `litellm` also receives `DATABASE_URL` in **sync** psycopg form (`postgresql://`), unlike the services' `postgresql+asyncpg://`.

---

## 3. Migrations and demo seed

Two independent Alembic histories against the **same** database:
- `/Users/manastole/Projects/Healthcare/services/api/alembic.ini` → 8 revisions, `0001_enable_vector` … `0008_job_watch`
- `/Users/manastole/Projects/Healthcare/services/ai/alembic.ini` → 3 revisions, `0001_ai_operating_system` … `0003_action_proposals`

Both `env.py` files ignore the `sqlalchemy.url` in the ini and override it from settings: `config.set_main_option("sqlalchemy.url", get_settings().database_url.get_secret_value())`, so `DATABASE_URL` is what actually matters.

Docker path (canonical):
```bash
make migrate     # docker compose run --rm api alembic upgrade head
                 # docker compose run --rm ai  alembic upgrade head
make seed-demo   # migrate, then: docker compose run --rm api healthos-seed-demo
```
The `api`/`ai` container `command` already runs `alembic upgrade head` on every start, so a plain `make up` self-migrates; `make migrate` is for running it out of band.

Host path (needs a reachable DB; loopback port is 55432):
```bash
export DATABASE_URL='postgresql+asyncpg://healthos:change-me@localhost:55432/healthos'
uv run alembic -c services/api/alembic.ini upgrade head
uv run alembic -c services/ai/alembic.ini  upgrade head
uv run healthos-seed-demo
```

New revision: `uv run alembic -c services/api/alembic.ini revision -m "..."` (guide rule: never edit an applied migration).

Full demo from scratch: `cp .env.example .env && make demo`.

---

## 4. pnpm workspace + turbo

`pnpm-workspace.yaml`: packages `apps/*` and `packages/typescript/*`; `onlyBuiltDependencies: [sharp]`. Root `package.json` is private, `packageManager: pnpm@10.12.4`, `engines.node >=20.9.0` (docs say Node 22), devDeps prettier + prettier-plugin-tailwindcss + turbo ^2.5.4 + typescript ^5.8.3, and a pnpm override pinning `postcss >=8.5.10 <9`.

Members:
- `/Users/manastole/Projects/Healthcare/apps/web` — `@healthos/web`, Next 15.5.19 + React 19, `dev: next dev --turbopack`, `test: node --test`, depends on all three workspace packages via `workspace:*`
- `/Users/manastole/Projects/Healthcare/packages/typescript/api-types` — `@healthos/api-types`
- `/Users/manastole/Projects/Healthcare/packages/typescript/ui` — `@healthos/ui`, subpath exports for badge/button/card/input/label/table/textarea, Radix slot + CVA
- `/Users/manastole/Projects/Healthcare/packages/typescript/utils` — `@healthos/utils`, clsx + tailwind-merge

Root scripts map 1:1 to turbo: `build|dev --parallel|lint|typecheck|test|clean`; `format` and `format:check` are direct prettier calls (not turbo).

`turbo.json` tasks:
- `build`: `dependsOn: ["^build"]`, outputs `.next/**`, `!.next/cache/**`, `dist/**`
- `dev`: `cache: false`, `persistent: true`
- `lint`: `dependsOn: ["^lint"]`
- `typecheck`: `dependsOn: ["^typecheck"]`
- `test`: `dependsOn: ["^build"]`, outputs `coverage/**`
- `clean`: `cache: false`

No `globalDependencies`/`inputs` and no `globalEnv` declared — env changes (e.g. `NEXT_PUBLIC_API_URL`) will not invalidate the turbo cache. The three library packages implement `build`/`lint` as `tsc --noEmit` and emit no `dist`, so their `outputs` globs never match.

---

## 5. pyproject (`/Users/manastole/Projects/Healthcare/pyproject.toml`)

- Root project `healthos-workspace` 0.1.0, `requires-python = ">=3.12,<3.14"`, no runtime deps.
- Single dependency group `dev`: `httpx>=0.28.1,<1`, `mypy>=1.15,<2`, `pytest>=8.3,<9`, `pytest-asyncio>=0.25,<1`, `pytest-cov>=6,<7`, `ruff>=0.11,<1`.
- `[tool.uv.workspace] members`: `packages/python/healthos_platform`, `services/api`, `services/ai`, `services/gateway`. `[tool.uv.sources] healthos-platform = {workspace = true}`.
- Ruff: `target-version = "py312"`, `line-length = 100`, `src = ["services/*/src","packages/python/*/src"]`. Lint select `E,F,I,UP,B,SIM,ASYNC,S` (pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify, async, **bandit**), `ignore = ["S101"]`, and `**/tests/**` ignores all `S`.
- Mypy: `python_version = "3.12"`, **`strict = true`**, `plugins = ["pydantic.mypy"]`, `packages = ["healthos_platform","healthos_api","healthos_ai","healthos_gateway"]` with matching `mypy_path`. Only override: `authlib.*` → `ignore_missing_imports = true`. Because `packages` is baked into config, bare `uv run mypy` checks everything.
- Pytest: `addopts = "-q --strict-markers --strict-config --import-mode=importlib"`, `asyncio_mode = "auto"`, testpaths `packages/python/healthos_platform/tests` + `services/*/tests`, marker `integration: requires PostgreSQL and Redis`, `pythonpath` covering all four src dirs.

Adding a dependency (uv workspace — no documented recipe in the docs, this is the mechanical answer):
```bash
uv add --package healthos-api <pkg>        # runtime dep for a specific service
uv add --dev <pkg>                         # root dev group
uv sync --all-packages --dev               # re-resolve into .venv
```
Equivalent manual route: edit the service's `pyproject.toml` `dependencies` then `uv sync --all-packages --dev`. CI runs `uv sync --all-packages --dev --frozen`, so `uv.lock` must be committed or CI fails. If the dep is needed inside containers, remember `infra/docker/python.Dockerfile` runs `uv sync --frozen --no-dev --no-editable --package "${SERVICE_PACKAGE}"` — dev-group deps are never in the image.

Per-service dependency files: `services/api/pyproject.toml` (FastAPI, SQLAlchemy async, asyncpg, alembic, pgvector, authlib, pwdlib[argon2], pyjwt, pypdf, redis), `services/ai/pyproject.toml` (langgraph 1.2, deepagents, langchain-openai, langgraph-checkpoint-postgres, mcp, openai, pycryptodome, psycopg), `services/gateway/pyproject.toml` (fastapi/httpx/uvicorn only), `packages/python/healthos_platform/pyproject.toml` (pydantic-settings, structlog, otel, prometheus).

Console scripts (these are the `healthos-*` commands compose invokes):
- `healthos-api`: `healthos-create-admin`, `healthos-job-watch-scan`, `healthos-seed-demo`
- `healthos-ai`: `healthos-ai-worker`

---

## 6. `.env.example` — every variable and default

`/Users/manastole/Projects/Healthcare/.env.example` (82 lines, 60 variables). Empty value = intentionally blank.

Runtime: `ENVIRONMENT=local`, `LOG_LEVEL=INFO`, `LOG_FORMAT=console`, `CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]`

PostgreSQL/pgvector: `POSTGRES_DB=healthos`, `POSTGRES_USER=healthos`, `POSTGRES_PASSWORD=change-me`, `POSTGRES_HOST_PORT=55432`, `DATABASE_URL=postgresql+asyncpg://healthos:change-me@postgres:5432/healthos`

Redis: `REDIS_URL=redis://redis:6379/0`, `REDIS_HOST_PORT=56379`

JWT/auth: `JWT_SECRET_KEY=replace-this-with-at-least-32-random-characters`, `JWT_REFRESH_SECRET_KEY=replace-this-with-a-different-32-character-secret`, `OTP_SECRET_KEY=replace-this-with-another-32-character-secret`, `JWT_ALGORITHM=HS256`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS=30`, `JWT_ISSUER=healthos`, `JWT_AUDIENCE=healthos-api`, `AUTH_COOKIE_SECURE=false`, `AUTH_COOKIE_DOMAIN=` (empty), `ALLOWED_HOSTS=["localhost","127.0.0.1","testserver"]`

Google OAuth: `GOOGLE_CLIENT_ID=`, `GOOGLE_CLIENT_SECRET=`, `GOOGLE_REDIRECT_URI=http://localhost:8080/api/v1/auth/google/callback`, `FRONTEND_AUTH_CALLBACK_URL=http://localhost:3000/auth/callback`

OTP delivery: `SMTP_HOST=`, `SMTP_PORT=587`, `SMTP_USERNAME=`, `SMTP_PASSWORD=`, `SMTP_FROM_EMAIL=`, `SMTP_USE_TLS=true`, `SMS_WEBHOOK_URL=`, `SMS_WEBHOOK_TOKEN=`

Integrations: `OCR_API_URL=`, `OCR_API_KEY=`, `FHIR_BASE_URL=`, `FHIR_ACCESS_TOKEN=`, `INSURANCE_API_URL=`, `INSURANCE_API_KEY=`, `STRIPE_SECRET_KEY=`, `STRIPE_WEBHOOK_SECRET=`, `NOTIFICATION_WEBHOOK_URL=`, `JOB_WATCH_SCAN_INTERVAL_SECONDS=300`, `DOCUMENT_MAX_BYTES=10485760`

Service discovery: `API_SERVICE_URL=http://api:8000`, `AI_SERVICE_URL=http://ai:8001` (see gotcha above — should be `:8000` in-network)

AI gateway/encryption: `OPENAI_API_KEY=`, `ANTHROPIC_API_KEY=`, `GEMINI_API_KEY=`, `OPENAI_MODEL=openai/gpt-5.4`, `ANTHROPIC_MODEL=anthropic/claude-sonnet-4-6`, `GEMINI_MODEL=gemini/gemini-2.5-pro`, `LITELLM_MASTER_KEY=replace-with-at-least-32-random-characters`, `LITELLM_BASE_URL=http://litellm:4000/v1`, `AI_DATA_ENCRYPTION_KEY=replace-with-a-valid-fernet-key`, `LANGGRAPH_AES_KEY=replace-with-a-32-byte-aes-key`, `LANGSMITH_API_KEY=`, `LANGSMITH_TRACING=false`, `LANGSMITH_PROJECT=healthos`, `OTEL_EXPORTER_OTLP_ENDPOINT=` (empty)

Browser: `NEXT_PUBLIC_API_URL=http://localhost:8080`

Not in `.env.example` but consumed by compose/tooling: `GRAFANA_ADMIN_PASSWORD` (compose default `local-grafana-admin`) and `HEALTHOS_DEMO_PASSWORD` (seed default `Demo@HealthOS2026!`).

An actual `.env` exists at `/Users/manastole/Projects/Healthcare/.env` with a real generated `POSTGRES_PASSWORD`; it is missing 22 keys present in `.env.example` (all of the model/integration/OTEL/host-port group), so those fall back to compose defaults or to the app's own defaults.

---

## 7. Seed script

Yes. `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/cli/seed_demo.py` (1198 lines), exposed as console script `healthos-seed-demo` via `services/api/pyproject.toml`.

- Entry point `main()` uses argparse with a single `--password` flag defaulting to `os.getenv("HEALTHOS_DEMO_PASSWORD", DEMO_PASSWORD)`; `DEMO_PASSWORD = "Demo@HealthOS2026!"` (line 40). Rejects passwords under 12 chars.
- `async def seed_demo(password)` runs one transaction: `_seed_users` → `_seed_identity_examples` → `_seed_documents` → `_seed_portal_records` → `_seed_supporting_tables` → flush → `_seed_ai_tables` → commit, then disposes the engine. Prints a JSON summary (`users`, `portal_records`, `documents`, `notifications`, `integrations`, `ai_runs`) and the account list.
- Idempotent — safe to re-run; updates the same deterministic rows and leaves non-demo rows alone.
- Seeds 5 users + 60 portal records across patient/doctor/hospital/insurance/admin, plus `document_assets`, `portal_notifications`, `integration_events`, `system_settings`, `audit_events`, and the AI tables (`ai_agent_runs`, `ai_agent_messages`, `ai_knowledge_documents`/`_chunks`, `ai_long_term_memories`, `ai_agent_audit_events`) with pgvector embeddings.
- Demo accounts: `{patient,doctor,hospital,insurance,admin}.demo@healthos.example.com`, password `Demo@HealthOS2026!`; patient HealthOS ID `PATDEMO00000001`. Full inventory: `/Users/manastole/Projects/Healthcare/docs/DEMO_DATA.md`.
- Test coverage: `/Users/manastole/Projects/Healthcare/services/api/tests/test_demo_seed.py`.
- Other CLIs alongside it: `create_admin.py` (`healthos-create-admin`), `job_watch_scan.py` (`healthos-job-watch-scan`).

---

## 8. Bring the stack up and verify

```bash
cd /Users/manastole/Projects/Healthcare
cp .env.example .env          # then replace JWT_SECRET_KEY / JWT_REFRESH_SECRET_KEY /
                              # OTP_SECRET_KEY / POSTGRES_PASSWORD / LITELLM_MASTER_KEY /
                              # AI_DATA_ENCRYPTION_KEY (Fernet) / LANGGRAPH_AES_KEY (32 bytes)
make bootstrap                # corepack + pnpm install + uv sync --all-packages --dev
make demo                     # build, migrate both histories, seed, start everything
# or: make up                 # same stack without the demo data
```

Verify:
```bash
docker compose ps                                     # every service should be running/healthy
curl -fsS http://localhost:8080/health/live            # gateway liveness
curl -fsS http://localhost:8080/health/ready           # gateway readiness (fans out to api + ai)
curl -fsS http://localhost:8000/api/v1/health/ready    # core API
curl -fsS http://localhost:8001/ai/v1/health/ready     # AI runtime
curl -fsS http://localhost:3000/health                 # web
curl -fsS http://localhost:4000/health/liveliness      # litellm
open http://localhost:3000  http://localhost:9090  http://localhost:3001   # web, prometheus, grafana
```

Verify seeded data:
```bash
docker compose exec postgres psql -U healthos -d healthos -c \
  "SELECT account_type, email, status FROM users WHERE email LIKE '%.demo@healthos.example.com';"
```
Log in at `http://localhost:3000/patient/login` as `patient.demo@healthos.example.com` / `Demo@HealthOS2026!`.

Tear down: `make down` (keeps volumes) — add `docker compose down -v` to drop the database.

Health endpoint map (README lines 95-98): gateway `/health/{live,ready}`, core API `/api/v1/health/{live,ready}`, AI `/ai/v1/health/{live,ready}`, web `/health`. `/metrics` is exposed internally by gateway, api, and ai.

---

## docs/ contents

- `/Users/manastole/Projects/Healthcare/docs/DEMO_DATA.md` — demo accounts + per-table seed inventory
- `/Users/manastole/Projects/Healthcare/docs/DEVELOPER_GUIDE.md` — prerequisites, workflow rules, command list, service conventions, release process
- `/Users/manastole/Projects/Healthcare/docs/TESTING.md`
- `/Users/manastole/Projects/Healthcare/docs/SPECIFICATION_COVERAGE.md`
- `/Users/manastole/Projects/Healthcare/docs/api/README.md`, `openapi-core.json`, `openapi-ai.json` (checked-in contracts regenerated by `make openapi`)
- `/Users/manastole/Projects/Healthcare/docs/architecture/` — `0001-service-boundaries.md`, `ai-operating-system.md`, `application-portals.md`, `deployment.md`, `production.md`, `security.md`
- `/Users/manastole/Projects/Healthcare/docs/compliance/HIPAA_READINESS.md`
- `/Users/manastole/Projects/Healthcare/docs/operations/BACKUP_RECOVERY.md`, `INCIDENT_RESPONSE.md`

Note: `/Users/manastole/Projects/Healthcare/README.md` around lines 61-64 has corrupted text — a stray prompt fragment ("Create a system end-to-end which solves the given problem cvreate accurate db api use any latest tech...") is spliced into the middle of the quickstart sentence, breaking the paragraph before the `make demo` block.


<!-- ===== raw scout: adee290dd085920de ===== -->

Files read: `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/models.py` (692 lines, 29 model classes), `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/base.py`, `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/session.py`, plus `db/dependencies.py`, `migrations/env.py`, and all 8 migrations for convention cross-checks.

---

## 1. Base + TimestampMixin

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/base.py` (entire file, 14 lines):

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

`TimestampMixin` (models.py:55-61) — a plain mixin class, NOT a Base subclass, and always listed FIRST in the MRO (`class X(TimestampMixin, Base)`):

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

Rule observed: append-only / log-style tables do NOT use the mixin; they declare only `created_at` inline as the LAST column of the class:

```python
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```
(used by `OtpChallenge`, `AuthSession`, `AuditEvent`, `PortalNotification`, `JobWatchPosting`, `JobWatchAlertDelivery`, `IntegrationEvent`, `IdempotencyRecord`, `OutboxEvent`). `Role`, `Permission`, `UserRole`, `RolePermission` have no timestamps at all.

## 2. SQLAlchemy version / style

- SQLAlchemy **2.0.51** installed; pin in `/Users/manastole/Projects/Healthcare/services/api/pyproject.toml`: `"sqlalchemy[asyncio]>=2.0,<3"`. Alembic 1.18.5 (`"alembic>=1.15,<2"`). Python `>=3.12,<3.14`; ruff `line-length = 100`, `target-version = "py312"`, lint select `["E","F","I","UP","B","SIM","ASYNC","S"]`.
- Full modern 2.0 declarative: `DeclarativeBase` + `Mapped[...]` annotations + `mapped_column(...)` everywhere. **Zero** legacy `Column(...)` usage, zero `declarative_base()`, no `__mapper_args__`, no `server_onupdate`, no `deferred`, no `TypeDecorator`, no `@declared_attr`.
- `from __future__ import annotations` at line 1 → forward refs in relationships are written bare (`Mapped[PatientProfile | None]`, `Mapped[list[Role]]`), never quoted.
- Async everywhere: `create_async_engine` / `AsyncSession` / `async_sessionmaker` in session.py. No sync engine anywhere.
- Nullability is stated **explicitly and redundantly**: `nullable=False` is always written even though `Mapped[str]` implies it; nullable columns use `Mapped[X | None]` and simply omit `nullable`.
- Optional/nullable columns with no other args still call `mapped_column()` with empty parens when there's no type arg: `date_of_birth: Mapped[date | None] = mapped_column()`.
- `id`/UUID columns have **no explicit type**: `Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)` (relies on SA 2.0 `uuid.UUID` → `Uuid`; migrations spell it `postgresql.UUID(as_uuid=True)`).
- Python-side `default=` in models (`default=uuid4`, `default=dict`, `default=list`, `default=0`, `default="active"`); the matching migration supplies `server_default=` (`sa.func.now()`, `sa.true()`, `sa.false()`, `"{}"`, `"[]"`, `"5"`, `"active"`). Models never use `server_default` except on the timestamp columns.
- `JSON` (generic, imported from `sqlalchemy`) is used in models; migrations create the same columns as `postgresql.JSONB()`. Follow that split exactly for new tables.

session.py (entire file):
```python
def create_database_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)

def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```
`db/dependencies.py` exposes `get_db(request)` reading `request.app.state.session_factory` (no commit; rollback on exception).

## 3. Enums / Literals for status, category, role, account_type

Only **three** DB enums exist, all `StrEnum`, all at the top of models.py (lines 29-52), plus a shared `values_callable` helper:

```python
class AccountType(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    HOSPITAL = "hospital"
    INSURANCE = "insurance"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class OtpPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    MOBILE_VERIFICATION = "mobile_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]
```

Canonical enum column form (exact, used in 4 places: `User.account_type`, `User.status`, `OrganizationProfile.account_type`, `OtpChallenge.purpose`):

```python
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        index=True,
        nullable=False,
    )
```
`native_enum=False` → rendered as VARCHAR + CHECK, so no PG enum types exist in the DB.

**Everything else is a bare string column, not an enum.** All `status`, `category`, `role`, `channel`, `severity`, `kind`, `source_type` fields are `Mapped[str] = mapped_column(String(N), ... default="...")`:
- status widths: `String(32)` (most), `String(64)` for `PortalRecord.status` and `WorkflowInstance.status`.
- status defaults seen: `"active"` (PortalRecord, Organization, OrganizationMembership, ConsentGrant), `"stored"` (DocumentAsset), `"draft"` (ApplicationDefinition), `"open"` (WorkflowTask), `"pending"` (OutboxEvent), `"sent"` (JobWatchAlertDelivery).
- category: `String(64)` (`PortalRecord.category` indexed; `DocumentAsset.category` default `"general"`).
- role: `OrganizationMembership.role: Mapped[str] = mapped_column(String(64), nullable=False)`; `WorkflowTask.assigned_role: Mapped[str | None] = mapped_column(String(64))`.
- Vocabularies are enforced either by `CheckConstraint("col IN ('a', 'b')", name=...)` (see `job_watch_source_type`, `job_watch_posting_source_type`, `organization_account_type`) or by Python-side allowlists.

Literals live only in Pydantic schemas, never in models: `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/platform/schemas.py:7-8`
```python
DefinitionKind = Literal["module", "form", "dashboard", "workflow", "content"]
DefinitionStatus = Literal["draft", "review", "published", "retired"]
```
The category vocabulary is a Python dict, not a DB enum: `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/portal/access.py` → `PORTAL_MODULES: dict[AccountType, tuple[str, ...]]` mapping each `AccountType` to allowed `category` strings (patient: medical_history, vitals, allergies, vaccinations, visits, medications, appointments, telemedicine, lab_reports, lab_bookings, insurance, buy_insurance, loyalty_points, claims, cost_estimates, payments, notifications, health_reminders, consents, documents, ai_assistant; doctor: schedule, patients, prescriptions, documentation, medical_coding, referrals, care_coordination, telemedicine, lab_reports, appointments, ai_assistant, documents; hospital: staff, departments, beds, resources, service_catalog, lab_slots, billing, revenue_cycle, eligibility, reports, appointments, documents; insurance: policies, eligibility, claims, prior_authorization, cost_estimates, fraud_detection, documents; admin: analytics, audit_logs, user_management, monitoring, system_settings, escalations, support, documents), enforced by `authorize_module(account_type, category)`.

RBAC role/permission rows are seeded data, not enums (migration 0002 `_seed_rbac()`): roles `patient|doctor|hospital|insurance|admin` (ids 1-5); permissions `profile:read`, `profile:write`, `sessions:read`, `sessions:revoke`, `users:manage`, `rbac:manage` (ids 1-6), extended by later migrations.

## 4. User + all Profile models (verbatim, models.py:64-167)

```python
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        index=True,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, values_callable=enum_values, native_enum=False, length=32),
        default=UserStatus.PENDING_VERIFICATION,
        index=True,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    patient_profile: Mapped[PatientProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    doctor_profile: Mapped[DoctorProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    organization_profile: Mapped[OrganizationProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class PatientProfile(TimestampMixin, Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (
        CheckConstraint("char_length(patient_id) = 15", name="patient_id_length"),
        CheckConstraint("patient_id ~ '^PAT[A-Z0-9]{12}$'", name="patient_id_format"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    patient_id: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    date_of_birth: Mapped[date | None] = mapped_column()
    sex_at_birth: Mapped[str | None] = mapped_column(String(32))
    blood_type: Mapped[str | None] = mapped_column(String(8))
    emergency_contact: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="patient_profile")


class DoctorProfile(TimestampMixin, Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    license_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    license_jurisdiction: Mapped[str | None] = mapped_column(String(100))
    specialty: Mapped[str | None] = mapped_column(String(150))
    affiliation: Mapped[str | None] = mapped_column(String(255))
    credentials_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="doctor_profile")


class OrganizationProfile(TimestampMixin, Base):
    __tablename__ = "organization_profiles"
    __table_args__ = (
        UniqueConstraint("account_type", "registration_number"),
        CheckConstraint(
            "account_type IN ('hospital', 'insurance')", name="organization_account_type"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100))
    organization_type: Mapped[str | None] = mapped_column(String(100))
    product_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    credentials_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="organization_profile")
```

Profile pattern to copy: one-to-one satellite tables keyed by `user_id` as the **PK and FK simultaneously** (no surrogate `id`), `TimestampMixin`, parent side `uselist=False, cascade="all, delete-orphan", lazy="selectin"`, child side `user: Mapped[User] = relationship(back_populates=...)`. Common field widths: names `String(100)`, phone `String(32)`, license/registration `String(100)`, legal/emergency/affiliation `String(255)`, urls `String(2048)`.

## 5. tenant_id / organization scoping

- **There is no `tenants` table and no FK on `tenant_id`.** Every tenant-scoped table declares a bare, untyped, indexed UUID with no ForeignKey:
  ```python
      tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
  ```
  Nullable variant only on `ApplicationDefinition` (null = global/platform-level definition): `tenant_id: Mapped[UUID | None] = mapped_column(index=True)`.
- Tables carrying `tenant_id`: `PortalRecord`, `DocumentAsset`, `PortalNotification`, `JobWatchProfile`, `IntegrationEvent`, `ApplicationDefinition`, `WorkflowInstance`, `WorkflowTask`, `IdempotencyRecord`, `OutboxEvent`. (Deliberately absent from: `AuditEvent`, `ConsentGrant`, `AuthSession`, `OtpChallenge`, `JobWatchSource/Posting/AlertDelivery`, `SystemSetting`, profiles.)
- The tenant value is resolved at request time, not stored on `users`. `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/security.py`:
  ```python
  @dataclass(slots=True)
  class AuthContext:
      user: User
      session: AuthSession
      claims: AccessTokenClaims
      tenant_id: UUID
  ```
  ```python
      primary_tenant = await db.scalar(
          select(OrganizationMembership.organization_id)
          .where(
              OrganizationMembership.user_id == user.id,
              OrganizationMembership.status == "active",
          )
          .order_by(OrganizationMembership.is_primary.desc(), OrganizationMembership.created_at)
          .limit(1)
      )
      return AuthContext(user=user, session=session, claims=claims, tenant_id=primary_tenant or user.id)
  ```
  So `tenant_id` == the primary active `organizations.id`, **falling back to the user's own `users.id`** for solo/patient accounts. That's why it cannot be a FK.
- Row filtering is application-level (no RLS). Canonical pattern, `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/portal/service.py:29-74`:
  ```python
  def tenant_id(context: AuthContext) -> UUID:
      return context.tenant_id

  def scoped_records(context: AuthContext) -> Any:
      query = select(PortalRecord)
      if context.user.account_type == AccountType.ADMIN:
          return query
      if context.user.account_type == AccountType.PATIENT:
          return query.where(
              or_(
                  PortalRecord.owner_user_id == context.user.id,
                  PortalRecord.patient_user_id == context.user.id,
              )
          )
      return query.where(PortalRecord.tenant_id == tenant_id(context))
  ```
  Global-then-tenant lookups use `or_(Model.tenant_id.is_(None), Model.tenant_id == context.tenant_id)` with `.order_by(Model.tenant_id.desc().nullslast())` (routes/platform.py:85-95).
- Companion user-scoping columns on tenant tables (always FKs to `users.id`): `owner_user_id` (CASCADE, NOT NULL, indexed), `patient_user_id` (SET NULL, nullable, indexed), `assigned_user_id` / `recipient_user_id` / `actor_user_id`.
- Every tenant-scoped table also carries a composite covering index leading with `tenant_id` (see §7).
- Cross-tenant/patient access is gated by `ConsentGrant` via `has_patient_consent(db, *, patient_user_id, grantee_user_id, category)` in portal/service.py.

## 6. ConsentGrant, AuditEvent, OutboxEvent, IdempotencyRecord (verbatim)

```python
class ConsentGrant(TimestampMixin, Base):
    __tablename__ = "consent_grants"
    __table_args__ = (
        Index("ix_consent_patient_status", "patient_user_id", "status"),
        Index("ix_consent_grantee_scope", "grantee_user_id", "grantee_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    grantee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    grantee_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    subject_user_id: Mapped[UUID | None] = mapped_column(index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "actor_user_id", "operation", "key"),
        Index("ix_idempotency_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_delivery", "status", "available_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Important behavioral note for `AuditEvent`: `previous_hash` / `event_hash` are NOT NULL with **no Python default** — they are filled by a Postgres BEFORE-INSERT trigger created in `0004_registration_and_consent.py`:
```sql
CREATE FUNCTION healthos_seal_audit_event() ... -- sets NEW.previous_hash / NEW.event_hash (sha256 chain, pg_advisory_xact_lock)
CREATE TRIGGER seal_audit_event BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION healthos_seal_audit_event()
CREATE TRIGGER reject_audit_mutation BEFORE UPDATE OR DELETE ON audit_events ... RAISE EXCEPTION 'audit events are append-only'
```
Call sites construct it as `AuditEvent(actor_user_id=..., event_type=f"portal.{category}.created", subject_user_id=..., event_data={...})` and `db.add(...)`; `event_type` is dotted-lowercase (`portal.<category>.<verb>`, `platform.*`).

## 7. Naming conventions

**Table names**: snake_case, plural nouns, no schema qualifier, no prefix in this service (`users`, `patient_profiles`, `doctor_profiles`, `organization_profiles`, `roles`, `permissions`, `user_roles`, `role_permissions`, `oauth_identities`, `otp_challenges`, `auth_sessions`, `audit_events`, `portal_records`, `document_assets`, `portal_notifications`, `job_watch_profiles`, `job_watch_sources`, `job_watch_postings`, `job_watch_alert_deliveries`, `integration_events`, `system_settings`, `organizations`, `organization_memberships`, `consent_grants`, `application_definitions`, `workflow_instances`, `workflow_tasks`, `idempotency_records`, `outbox_events`). Feature families share a prefix (`job_watch_*`, `portal_*`, `workflow_*`). The sibling AI service uses an `ai_` prefix (`ai_agent_runs`), but healthos_api does not.

**Column names**: snake_case; FK columns are `<entity>_user_id` / `<entity>_id`; timestamps end in `_at`; booleans are `is_*` / `<verb>ed` (`is_primary`, `is_active`, `enabled`, `email_verified`, `credentials_verified`); money as `amount_cents: Mapped[int | None] = mapped_column(Integer)` + `currency: Mapped[str | None] = mapped_column(String(3))`; hashes/digests `String(64)`; reserved-word workaround: `metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)` (attribute suffixed with `_`, DB name passed positionally first).

**Index names**: two tiers.
1. Single-column indexes are declared inline with `index=True` and get auto-named by `NAMING_CONVENTION["ix"] = "ix_%(column_0_label)s"` → `ix_<table>_<column>` (e.g. `ix_users_account_type`, `ix_outbox_events_tenant_id`).
2. Composite indexes go in `__table_args__` with an **explicit, hand-shortened name** that drops the table prefix redundancy — pattern `ix_<short_domain>_<purpose>`, singular domain word: `ix_portal_records_scope`, `ix_portal_records_patient`, `ix_documents_scope`, `ix_notifications_recipient`, `ix_integration_scope`, `ix_consent_patient_status`, `ix_consent_grantee_scope`, `ix_definition_lookup`, `ix_workflow_scope`, `ix_workflow_task_queue`, `ix_idempotency_expiry`, `ix_outbox_delivery`, `ix_membership_user_status`, `ix_otp_active_lookup`, `ix_auth_session_family`, `ix_job_watch_profile_enabled`, `ix_job_watch_source_enabled`, `ix_job_watch_posting_active`, `ix_job_watch_delivery_recipient`. Composite index column order is always `tenant_id, <discriminator>, <time-or-status>`.

**Constraint names**:
- `UniqueConstraint` is usually written **without** a name and relies on `uq_%(table_name)s_%(column_0_name)s` (e.g. `UniqueConstraint("provider", "provider_subject")`, `UniqueConstraint("tenant_id", "actor_user_id", "operation", "key")`). Two exceptions name it explicitly with a full `uq_`-prefixed name: `name="uq_organization_membership"`, `name="uq_application_definition_version"`.
- `CheckConstraint` **always** gets `name=` with the prefix omitted (the convention prepends `ck_<table>_`): `name="patient_id_length"`, `"patient_id_format"`, `"organization_account_type"`, `"job_watch_interval_bounds"`, `"job_watch_source_type"`, `"job_watch_posting_source_type"`.
- FK names are never written by hand; convention yields `fk_<table>_<column>_<referred_table>`.
- `__table_args__` is always a tuple with a trailing comma even for a single element: `__table_args__ = (Index(...),)`. Order inside: `UniqueConstraint`s, then `CheckConstraint`s, then `Index`es (see `JobWatchProfile`, `JobWatchSource`).

**FK `ondelete` choices** (strictly consistent semantics):
- `CASCADE` — owning/child relationship where the row is meaningless without the parent: all `user_id` on profiles, `user_roles`/`role_permissions`, `oauth_identities.user_id`, `otp_challenges.user_id`, `auth_sessions.user_id`, `portal_records.owner_user_id`, `document_assets.owner_user_id`, `portal_notifications.recipient_user_id`, `integration_events.actor_user_id`, `organization_memberships.*`, `consent_grants.*`, `workflow_tasks.workflow_instance_id`, all `job_watch_*` parents.
- `SET NULL` — nullable references that should survive deletion: `audit_events.actor_user_id`, `portal_records.patient_user_id`, `portal_records.assigned_user_id`, `document_assets.patient_user_id`, `workflow_tasks.assigned_user_id`, `application_definitions.supersedes_id`.
- `RESTRICT` — protect referenced config/authorship rows: `system_settings.updated_by_user_id`, `application_definitions.created_by_user_id`, `workflow_instances.definition_id`.
- **No `ondelete` at all** (default NO ACTION) on: `auth_sessions.replaced_by_id` (self-FK) and `idempotency_records.actor_user_id` (`ForeignKey("users.id")`).
- FK style: `ForeignKey("<table>.<col>", ondelete="X")` passed as the first positional arg of `mapped_column`, then `index=True`, then `nullable=False`. Argument order in `mapped_column` throughout: type/FK → `default=` → `index=True` → `nullable=` (with small local variations, e.g. `String(64), index=True, nullable=False`).

**Migration conventions** (`/Users/manastole/Projects/Healthcare/services/api/migrations/versions/`, numeric revisions `0001`..`0008`, filename `NNNN_snake_case_topic.py`): module docstring `"""<Sentence describing change>.\n\nRevision ID: 000N\nRevises: 000N-1\n"""`; typed globals `revision: str`, `down_revision: str | None`, `branch_labels: str | Sequence[str] | None`, `depends_on: str | Sequence[str] | None`; a local helper `def timestamps() -> list[sa.Column]` splatted as `*timestamps()`; hand-written (never autogenerated) `op.create_table` with `postgresql.UUID(as_uuid=True)`, `postgresql.JSONB()`, `postgresql.CITEXT()`; explicit `op.create_index("ix_<table>_<col>", "<table>", ["<col>"])` for every `index=True` column plus each composite; `downgrade()` iterates a reverse-ordered list of table names calling `op.drop_table(table)`. `migrations/env.py` uses `target_metadata = Base.metadata`, `compare_type=True`, async engine — so the naming convention propagates to `op.*` operations too.

## 8. Exact import block (models.py:1-26)

```python
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from healthos_api.db.base import Base
```

Notes for extending it: imports are ruff/isort-sorted (`I` rule enabled), the `sqlalchemy` block is a parenthesized multi-line list in that exact order, `CITEXT` is the only postgresql-dialect import (no `JSONB`, no `ARRAY`, no `UUID` from the dialect), and everything is imported at module top — there are no `TYPE_CHECKING` blocks, no `__all__`, and only three docstrings in the whole file (`PortalRecord`, `Organization`, `ApplicationDefinition` — one-line, purpose-stating, placed before `__tablename__`).


<!-- ===== raw scout: aca1a3f63760d4a81 ===== -->

# HealthOS API conventions — exhaustive reference

All paths absolute. Line numbers are from the files as they exist now.

---

## 1. Router construction

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/routes/portal.py:73`**
```python
router = APIRouter(prefix="/portal", tags=["portal"])
```

Every route module declares exactly one module-level `router` named `router`, immediately after imports, with no `dependencies=`, no `responses=`, no `route_class`:

| File | Declaration |
|---|---|
| `portal.py:73` | `APIRouter(prefix="/portal", tags=["portal"])` |
| `users.py:22` | `APIRouter(prefix="/users", tags=["users"])` |
| `auth.py:66` | `APIRouter(prefix="/auth", tags=["authentication"])` |
| `platform.py:34` | `APIRouter(tags=["application-platform"])` — no prefix; paths are top-level (`/app-manifest`, `/configuration`, `/consents`, `/workflows`) |
| `health.py:9` | `APIRouter(tags=["health"])` — prefix supplied at include time |

Tags are lowercase kebab/single-word strings. Prefix has no trailing slash. Route paths never end in `/`.

### Decorator style

Read endpoints — one line when short:
```python
@router.get("/overview", response_model=DashboardResponse)
@router.get("/resources/{category}", response_model=list[RecordResponse])
@router.get("/notifications", response_model=list[NotificationResponse])
@router.get("/documents", response_model=list[DocumentResponse])
```

Mutating endpoints — always multi-line, always with `dependencies=[Depends(enforce_csrf)]`:
```python
@router.post(
    "/resources/{category}",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
@router.patch(
    "/resources/{category}/{record_id}",
    response_model=RecordResponse,
    dependencies=[Depends(enforce_csrf)],
)
@router.delete(
    "/resources/{category}/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
```

Key rules observed without exception in `portal.py`:
- **Every** POST/PATCH/PUT/DELETE carries `dependencies=[Depends(enforce_csrf)]`. The only exception is the Stripe webhook (`portal.py:914`), which is `@router.post("/webhooks/payments", include_in_schema=False)` and authenticates by HMAC signature instead.
- POST that creates a row → `status_code=status.HTTP_201_CREATED`. POST that performs an action/sync/intent (`/integrations/fhir`, `/integrations/insurance`, `/payments/intents`, `/notifications/{id}/read`) → default 200.
- DELETE → `status_code=status.HTTP_204_NO_CONTENT` and handler annotated `-> None`.
- `response_model=` is set only when the return type is a Pydantic model or `list[Model]`. Endpoints returning `dict[str, Any]` / `list[dict[str, Any]]` omit `response_model` and rely on the return annotation (`portal.py:443, 503, 554, 653, 734, 866, 955, 975, 1009, 1032, 1054, 1071`).
- `status` is always the FastAPI `status` module constant, never a bare int.
- Status constants in use: `HTTP_201_CREATED`, `HTTP_204_NO_CONTENT`, `HTTP_400_BAD_REQUEST`, `HTTP_403_FORBIDDEN`, `HTTP_404_NOT_FOUND`, `HTTP_409_CONFLICT`, `HTTP_413_CONTENT_TOO_LARGE`, `HTTP_422_UNPROCESSABLE_CONTENT` (note: `_CONTENT`, not `_ENTITY`), `HTTP_503_SERVICE_UNAVAILABLE`, plus `HTTP_401_UNAUTHORIZED`, `HTTP_429_TOO_MANY_REQUESTS`, `HTTP_202_ACCEPTED`, `HTTP_307_TEMPORARY_REDIRECT` elsewhere.

### Handler signature ordering (strict, observed everywhere)

1. path params (`category: str`, `record_id: UUID`)
2. body payload (`payload: RecordCreate`)
3. `request: Request` (only if needed for `app.state.http` / `app.state.redis` / headers)
4. `context: Annotated[AuthContext, Depends(require_permissions(...))]`
5. `db: Annotated[AsyncSession, Depends(get_db)]`
6. `settings: Annotated[Settings, Depends(get_settings)]`
7. defaulted query/form params last

Example (`portal.py:233-239`):
```python
async def create_notification(
    payload: NotificationCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationResponse:
```

The auth dependency parameter is **always named `context`** and is declared even when unused in the body (e.g. `admin_users` at `portal.py:956`, `admin_audit` at `portal.py:1010`) — it is the authorization gate. Every handler has an explicit return annotation; `async def` universally.

---

## 2. Auth dependency chain

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/security.py`** — the only auth module. Exact contents:

```python
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthContext:
    user: User
    session: AuthSession
    claims: AccessTokenClaims
    tenant_id: UUID


async def current_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
```

`current_auth_context` (security.py:30-77) does, in order:
1. token = bearer credential **or** `request.cookies.get(settings.access_cookie_name)` — dual bearer/cookie auth.
2. `decode_access_token(token, settings)`; `InvalidTokenError` → `_unauthorized()`.
3. Loads `User` with `select(User).options(*USER_LOAD_OPTIONS)` (eager-loads roles→permissions and all three profiles) and the `AuthSession` by `claims.sid`.
4. Rejects (401) if: user missing, session missing, `user.status != UserStatus.ACTIVE`, `user.token_version != claims.ver`, `session.revoked_at is not None`, or `session.expires_at <= now`.
5. Resolves tenant:
```python
    primary_tenant = await db.scalar(
        select(OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .order_by(OrganizationMembership.is_primary.desc(), OrganizationMembership.created_at)
        .limit(1)
    )
    return AuthContext(user=user, session=session, claims=claims, tenant_id=primary_tenant or user.id)
```
**Tenant fallback: a user with no active org membership is their own tenant (`tenant_id == user.id`).**

### Permission / role gates (factories returning a dependency)

```python
def require_permissions(*required: str) -> Callable[..., Awaitable[AuthContext]]:
    async def dependency(
        context: Annotated[AuthContext, Depends(current_auth_context)],
    ) -> AuthContext:
        granted = set(permission_names(context.user))
        if not set(required).issubset(granted):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context

    return dependency


def require_roles(*required: str) -> Callable[..., Awaitable[AuthContext]]:
    async def dependency(
        context: Annotated[AuthContext, Depends(current_auth_context)],
    ) -> AuthContext:
        granted = {role.name for role in context.user.roles}
        if not granted.intersection(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not authorized",
            )
        return context

    return dependency
```
`require_permissions` = **AND** (subset). `require_roles` = **OR** (intersection). Both return the same `AuthContext`.

### CSRF

```python
async def enforce_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if request.headers.get("authorization") and settings.refresh_cookie_name not in request.cookies:
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
    header_token = request.headers.get("x-csrf-token", "")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
```
Pure bearer clients are exempt; cookie sessions require the double-submit token. Used exclusively via `dependencies=[Depends(enforce_csrf)]`, never as a named parameter.

### Client fingerprint + 401 helper

```python
def client_context(request: Request) -> ClientContext:
    return ClientContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512] or None,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
```
`client_context` is a plain function called inline (`users.py:43`: `update_profile(db, context.user, payload, client_context(request))`), not a `Depends`.

### Permission catalog (seeded in migrations)

`0002_authentication.py`: `profile:read` (1), `profile:write` (2).
`0003_portal_domain.py:196-219`: `portal:read` (7), `portal:write` (8), `documents:manage` (9), `integrations:execute` (10), `system:admin` (11). Grants: perms 7/8/9 → roles 1-5 (all account types); perm 10 → roles 2,3,4,5; perm 11 → role 5 (admin) only. Role IDs map to `AccountType` values (`patient`, `doctor`, `hospital`, `insurance`, `admin`).

Observed usage in `portal.py`: `require_permissions("portal:read")`, `("portal:write")`, `("documents:manage")`, `("system:admin")`; `require_roles("patient")`, `("patient","doctor","hospital","admin")`, `("patient","hospital","insurance","admin")`, `("patient","hospital","admin")`.

### DB session dependency

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/dependencies.py`**
```python
async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```
No auto-commit — handlers/services commit explicitly.

**`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/dependencies/__init__.py`** is a stub containing only `"""Reusable FastAPI dependencies."""`. Nothing lives there; auth deps are in `core/security.py`, DB dep in `db/dependencies.py`, settings in `config.get_settings` (`@lru_cache`).

---

## 3. Pydantic schema conventions

Schemas live in a **domain package**, not in the routes module: `healthos_api/portal/schemas.py`, `healthos_api/platform/schemas.py`, `healthos_api/auth/schemas.py`, `healthos_api/job_watch/schemas.py`.

- **No `ConfigDict` / `model_config` anywhere in the API service.** Plain `class X(BaseModel):`. (`SettingsConfigDict` is used once, in `healthos_platform/config.py`, for `BaseSettings` only.)
- No `from_attributes` on classes; ORM conversion is done either by explicit hand-written mappers (dominant style) or, in one spot, ad-hoc: `platform.py:58` → `ConsentResponse.model_validate(item, from_attributes=True)`.
- Import line is always `from pydantic import BaseModel, Field, field_validator` (or `model_validator`).
- Naming: `<Noun>Create`, `<Noun>Update`, `<Noun>Response`; request-only helpers like `SyncRequest`, `SettingUpdate`, `UserStatusUpdate`.
- Optional fields use PEP 604 unions (`str | None`) and `Field(default=None, ...)` — never `Optional[...]`, never bare `= None` when other `Field` constraints are needed.
- Collections use `Field(default_factory=dict)` / `default_factory=list`.
- Response models declare fields **without defaults** (all required), so a missing mapper field is a hard error.

Representative (`portal/schemas.py:8-54`):
```python
class RecordCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", min_length=1, max_length=64)
    patient_user_id: UUID | None = None
    assigned_user_id: UUID | None = None
    external_reference: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def bound_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 50_000:
            raise ValueError("Structured payload is too large")
        return value
```

**Constraint style:** enum-ish strings use regex patterns rather than `Enum`:
```python
channel: str = Field(default="in_app", pattern="^(in_app|email|webhook)$")
severity: str = Field(default="info", pattern="^(info|success|warning|critical)$")
status: str = Field(pattern="^(active|suspended|disabled)$")            # UserStatusUpdate
amount_cents: int = Field(gt=49, le=100_000_000)                        # PaymentIntentCreate
loyalty_points: int = Field(default=0, ge=0, le=10_000_000)
```
`platform/schemas.py` additionally uses `Literal` type aliases and identifier patterns:
```python
DefinitionKind = Literal["module", "form", "dashboard", "workflow", "content"]
DefinitionStatus = Literal["draft", "review", "published", "retired"]
key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
locale: str = Field(default="en-US", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
```
`auth/schemas.py` defines reusable `Annotated` + `StringConstraints` aliases:
```python
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=7, max_length=32, pattern=r"^\+?[0-9() .-]+$")]
```

**Aliases** are used only to dodge Python/BaseModel name clashes — there is no global alias generator, no camelCase, no `populate_by_name`:
```python
# platform/schemas.py:16 (request side)
schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
# platform/schemas.py:43 (response side)
schema_: dict[str, Any] = Field(serialization_alias="schema")
```
Same trick for SQLAlchemy's reserved `metadata`: the model attribute is `metadata_` and the response field is plain `metadata` (`portal.py:87` `metadata=item.metadata_`).

**Validators:** `@field_validator("x") @classmethod def name(cls, value) -> T` for single fields; `@model_validator(mode="after") def name(self) -> "Model"` for cross-field rules, raising `ValueError` with a user-facing sentence:
```python
@model_validator(mode="after")
def exactly_one_grantee(self) -> "ConsentCreate":
    if (self.grantee_user_id is None) == (self.grantee_organization_id is None):
        raise ValueError("Provide exactly one user or organization grantee")
    return self
```
Payload-size guards are a house pattern (`len(str(value)) > 50_000`, `> 250_000`).

**Mappers:** each route/service module defines module-level `def <thing>_response(item: Model) -> ThingResponse` returning an explicit kwargs construction. In `portal.py` these are `document_response` (`:76`) and `notification_response` (`:92`); `record_response` lives in `portal/service.py:44` and is imported by the route module.

---

## 4. Pagination / filtering / sorting

**There is no offset/cursor pagination and no envelope.** Lists return bare JSON arrays with a hard server cap.

- Query params via `Query(...)`, both positional-default and `default=` forms appear:
```python
status_filter: str | None = Query(None, alias="status"),   # portal.py:138
limit: int = Query(100, ge=1, le=200),                     # portal.py:139
specialty: str | None = Query(default=None, max_length=150),   # portal.py:558
test_code: str | None = Query(default=None, max_length=100),   # portal.py:657
locale: str = Query("en-US", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$"),  # platform.py:113
kind: str | None = None,                                   # platform.py:149 (plain default, no Query)
```
- The user-supplied `limit` is re-clamped in the service: `.limit(min(limit, 200))` (`portal/service.py:86`).
- Hard caps inline in routes: `.limit(200)` for notifications and documents, `.limit(100)` for availability searches, `.limit(500)` for admin users/audit, `.limit(6)` for dashboard "recent".
- Sorting is fixed per endpoint, never client-controlled: `.order_by(X.created_at.desc())` is the default; `.order_by(PortalRecord.occurred_at)` for slot searches; `.order_by(PortalRecord.amount_cents, PortalRecord.created_at.desc())` for the marketplace; `.order_by(SystemSetting.key)`.
- Filtering is applied by conditional query building:
```python
query = select(DocumentAsset)
if context.user.account_type.value != "admin":
    query = query.where(DocumentAsset.tenant_id == tenant_id(context))
items = (await db.scalars(query.order_by(DocumentAsset.created_at.desc()).limit(200))).all()
```
- In-Python post-filtering is acceptable for JSON-blob fields (`specialty` at `portal.py:573-578`, `test_code` at `:672-673`).
- Row-fetch idiom: `(await db.scalars(query)).all()`, wrapped in `list(...)` when a `list` is required for typing; single row via `await db.scalar(...)`; PK fetch via `await db.get(Model, pk)`; counts via `await db.scalar(select(func.count()).select_from(Model)) or 0` cast to `int`.
- Row locking for booking/state transitions: `.with_for_update()` (`portal.py:614, 709`; `platform.py:215, 358, 454`).

---

## 5. Error handling

### In-route
`HTTPException` is raised with **positional** `(status, detail)` in route modules, and with keyword args in `core/security.py` / `auth/rate_limit.py`:
```python
raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
raise HTTPException(status.HTTP_409_CONFLICT, "This appointment slot is unavailable")
raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Document exceeds upload limit")
raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Document is empty")
raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payment webhook is not configured")
```
`detail` is a complete, user-facing sentence with no trailing period in most cases, never a code/enum.

### Service → HTTP translation
The service layer raises **built-in exceptions only** (`PermissionError`, `ValueError`); there are no custom domain exception classes in the portal domain. Routes translate them, always chaining with `from exc`:
```python
    try:
        records = await list_records(db, context, category, status_filter, limit)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
```
```python
    try:
        record = await create_record(db, context, category, payload)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
```
Mapping: `PermissionError → 403`, `ValueError → 422`, `None` result → 404.

Custom exception classes that do exist elsewhere (for reference): `InvalidTokenError` (`auth/tokens.py`), `OtpDeliveryError` (`auth/delivery.py`), `OAuthLinkError` (`auth/service.py`) — same translate-at-the-route pattern.

### Shared 404 helper inside the route module
```python
async def authorized_document(
    db: AsyncSession, context: AuthContext, document_id: UUID
) -> DocumentAsset:
    query = select(DocumentAsset).where(DocumentAsset.id == document_id)
    if context.user.account_type.value != "admin":
        query = query.where(DocumentAsset.tenant_id == tenant_id(context))
    item = await db.scalar(query)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return item
```
Helpers that raise `HTTPException` live in the **routes** module; helpers that raise `PermissionError`/`ValueError` live in the **service** module.

### Global error shape — RFC 7807
`/Users/manastole/Projects/Healthcare/packages/python/healthos_platform/src/healthos_platform/errors.py`, installed by `install_error_handlers(app)` in `main.py:80`. Every error becomes `application/problem+json`:
```python
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "error_id": error_id,
        "request_id": getattr(request.state, "request_id", None),
        "trace_id": _trace_id(),
    }
```
- `HTTPException` → `title="Request failed"`, `detail=exc.detail` (non-str detail collapses to `"The request could not be completed"`), `exc.headers` merged onto the response.
- `RequestValidationError` → 422, `title="Validation failed"`, `detail="One or more fields are invalid"`, plus `"errors": [{"location": "body.field", "message": ..., "type": ...}]`.
- Bare `Exception` → 500, logged via `logger.exception("unhandled_exception", error_id=..., error_type=...)`, detail `"An unexpected error occurred. Contact support with the error ID."`.

---

## 6. Idempotency, audit, and outbox at write sites

### Audit
`AuditEvent` rows are **added to the same session as the mutation and flushed by the shared `await db.commit()`** — never a separate transaction:
```python
    db.add(appointment)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="portal.appointment.booked",
            subject_user_id=context.user.id,
            event_data={"slot_id": str(slot.id), "appointment_id": str(appointment.id)},
        )
    )
    await db.commit()
    await db.refresh(appointment)
```
Conventions:
- `event_type` is dotted lowercase: `portal.<category>.created` / `portal.<category>.updated` (service.py, f-string built), `portal.appointment.booked`, `portal.policy.purchase_initiated`, `document.downloaded`, `document.deleted`, `admin.user_status_changed`, `consent.granted`, `consent.revoked`, `configuration.published`, `workflow.transitioned`.
- `actor_user_id=context.user.id`; `subject_user_id` = the patient/affected user (may be `None`).
- `event_data` values are JSON-safe — UUIDs always `str(...)`.
- **Never set `previous_hash` / `event_hash` in application code.** A Postgres `BEFORE INSERT` trigger `seal_audit_event` → `healthos_seal_audit_event()` computes the hash chain under `pg_advisory_xact_lock('healthos-audit-chain')` (migration `0004_registration_and_consent.py:86-105`), and `reject_audit_mutation` blocks UPDATE/DELETE on `audit_events`.
- Auth flows use the helper in `auth/service.py:646` instead, which also captures IP/UA:
```python
async def record_audit_event(
    db: AsyncSession, *, event_type: str, client: ClientContext,
    actor_user_id: UUID | None = None, subject_user_id: UUID | None = None,
    event_data: dict[str, Any] | None = None,
) -> None:
    _audit(db, event_type, actor_user_id, subject_user_id, client, event_data)
    await db.commit()
```
Portal/platform routes do **not** use it — they construct `AuditEvent(...)` inline and omit `ip_address`/`user_agent`.

Audit is recorded for: record create/update (service layer), document download/delete, appointment booking, policy purchase, admin status change, consent grant/revoke, configuration publish, workflow transition. It is *not* recorded for notification create/read, lab booking, or resource delete.

### Outbox
Exactly one call site today — **`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/routes/platform.py:476-497`**, added alongside the `AuditEvent` in the same commit:
```python
    db.add(
        OutboxEvent(
            tenant_id=context.tenant_id,
            aggregate_type="workflow",
            aggregate_id=item.id,
            event_type="workflow.transitioned",
            payload={"from": previous, "to": item.status, "action": payload.action},
        )
    )
    db.add(AuditEvent(...))
    await db.commit()
```
Model (`db/models.py:673`): `tenant_id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `status` (default `"pending"`), `attempts`, `available_at`, `delivered_at`, `last_error_code`. Defaults cover everything except the five fields above. No dispatcher/relay exists in this service yet.

### Idempotency
`IdempotencyRecord` (`db/models.py:652`, unique on `(tenant_id, actor_user_id, operation, key)` with `request_digest`, `response_status`, `response_body`, `expires_at`) **exists in the schema but has zero application call sites.** The only live idempotency handling is header pass-through in the payment intent endpoint (`portal.py:874-904`):
```python
    key = request.headers.get("idempotency-key") or request_digest(
        (context.user.id, payload.model_dump())
    )
    result = await PaymentGateway(settings, request.app.state.http).create_intent(
        payload.amount_cents, payload.currency, payload.description, key
    )
    ...
    db.add(
        IntegrationEvent(
            tenant_id=tenant_id(context),
            actor_user_id=context.user.id,
            provider=result.provider,
            operation="create_payment_intent",
            status=result.status,
            external_reference=result.external_reference,
            request_digest=key,
            response_metadata={"amount_cents": payload.amount_cents, "currency": payload.currency},
        )
    )
```
`request_digest` (`integrations/clients.py:130`) is `hashlib.sha256(repr(value).encode()).hexdigest()`.

### Third-party call audit — `IntegrationEvent`
Every outbound integration writes one `IntegrationEvent` in the same commit (`portal.py:360`, `:487`, `:538`, `:893`) with `tenant_id`, `actor_user_id`, `provider`, `operation`, `status`, optional `external_reference`, `request_digest=request_digest(payload.model_dump())`, and `response_metadata={...}` summary counters.

### Write transaction template
```python
db.add(entity)
db.add(AuditEvent(...))        # and/or IntegrationEvent / OutboxEvent
await db.commit()
await db.refresh(entity)       # only when the response needs server defaults
return entity_response(entity)
```
For updates: mutate the loaded ORM object, `db.add(AuditEvent(...))`, `await db.commit()`, `await db.refresh(item)`. For deletes: `db.add(AuditEvent(...))`, `await db.delete(item)`, `await db.commit()`, return `None`.

---

## 7. Service layer vs routes

`healthos_api/portal/` is the domain package: `__init__.py` (`"""Role-scoped portal domain."""`), `access.py` (authorization policy data), `schemas.py`, `service.py`.

**`access.py`** — pure policy, no I/O:
```python
PORTAL_MODULES: dict[AccountType, tuple[str, ...]] = { AccountType.PATIENT: (...), ... }

def authorize_module(account_type: AccountType, category: str) -> None:
    if category not in PORTAL_MODULES[account_type]:
        raise PermissionError(f"{category} is not available to {account_type.value} accounts")
```

**`service.py`** — async functions taking `(db: AsyncSession, context: AuthContext, ...)` positionally as the first two args; owns the tenant-scoping query builder, business rules, consent checks, derived data, audit, and the commit:
```python
def tenant_id(context: AuthContext) -> UUID:
    return context.tenant_id


def scoped_records(context: AuthContext) -> Any:
    query = select(PortalRecord)
    if context.user.account_type == AccountType.ADMIN:
        return query
    if context.user.account_type == AccountType.PATIENT:
        return query.where(
            or_(
                PortalRecord.owner_user_id == context.user.id,
                PortalRecord.patient_user_id == context.user.id,
            )
        )
    return query.where(PortalRecord.tenant_id == tenant_id(context))


async def list_records(db, context, category: str, status: str | None, limit: int) -> list[PortalRecord]
async def create_record(db, context, category: str, payload: RecordCreate) -> PortalRecord
async def find_record(db, context, category: str, record_id: UUID) -> PortalRecord | None
async def update_record(db, context, record: PortalRecord, payload: RecordUpdate) -> PortalRecord
async def has_patient_consent(db, *, patient_user_id, grantee_user_id, category) -> bool
async def dashboard(db, context, integrations: dict[str, bool]) -> DashboardResponse
def record_response(record: PortalRecord) -> RecordResponse
def display_name(context: AuthContext) -> str
def _consent_scopes(data: dict[str, Any]) -> set[str]          # private helpers underscore-prefixed
def _add_medication_reminders(db, medication, context, data) -> None
```

**Division of responsibility, as actually practiced:**

| Concern | Location |
|---|---|
| HTTP verb/path/status/`response_model` | route |
| Auth gate (`require_permissions` / `require_roles`), CSRF | route decorator/signature |
| `HTTPException` raising and exception translation | route (plus route-local helpers like `authorized_document`) |
| Multipart/file handling, `Response` construction, headers | route |
| `request.app.state.http` / `.redis` access, integration client instantiation | route (clients take `(settings, httpx.AsyncClient)`) |
| Module authorization (`authorize_module`) | service (`create_record`, `list_records`, `find_record` call it first) |
| Tenant scoping query builder | service (`scoped_records`) |
| Consent enforcement, derived fields (BMI), cascading rows (medication reminders) | service |
| ORM→schema mapping | service for shared entities (`record_response`), route for route-local ones (`document_response`, `notification_response`) |
| `db.add` + `AuditEvent` + `commit` + `refresh` | whichever layer owns the mutation — service for `PortalRecord` create/update, route for notifications/documents/bookings/admin |

Note the pragmatic split: many portal write endpoints (notifications, documents, bookings, purchase, payments, admin) do their persistence **directly in the route** and only fall back to the service for the generic `PortalRecord` CRUD. `platform.py` has no service module at all — all logic is in the route file with module-private `_helpers`. Both are native; the service module is warranted when logic is shared or non-trivial.

Return-type discipline: service functions return ORM objects or Pydantic models, never `HTTPException`, never `Response`.

Style constraints (`pyproject.toml`): ruff `line-length = 100`, `target-version = "py312"`, `select = ["E","F","I","UP","B","SIM","ASYNC","S"]`; mypy `strict = true` with the pydantic plugin over package `healthos_api` — so all params and returns must be annotated, and `cast(...)` is used where SQLAlchemy typing is loose (`service.py:169`, `dependencies.py:9`).

---

## 8. Exact import block of `portal.py` and router registration

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/routes/portal.py:1-73` verbatim:
```python
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.config import Settings, get_settings
from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    DocumentAsset,
    IntegrationEvent,
    PortalNotification,
    PortalRecord,
    SystemSetting,
    User,
    UserStatus,
)
from healthos_api.integrations.clients import (
    FHIRClient,
    InsuranceClient,
    OCRService,
    PaymentGateway,
    request_digest,
)
from healthos_api.integrations.notifications import NotificationDispatcher
from healthos_api.portal.access import PORTAL_MODULES
from healthos_api.portal.schemas import (
    AppointmentBookingCreate,
    DashboardResponse,
    DocumentResponse,
    LabBookingCreate,
    NotificationCreate,
    NotificationResponse,
    PaymentIntentCreate,
    PolicyPurchaseCreate,
    RecordCreate,
    RecordResponse,
    RecordUpdate,
    SettingUpdate,
    SyncRequest,
    UserStatusUpdate,
)
from healthos_api.portal.service import (
    create_record,
    dashboard,
    find_record,
    list_records,
    record_response,
    tenant_id,
    update_record,
)

router = APIRouter(prefix="/portal", tags=["portal"])
```
Import rules: stdlib → third-party → first-party, ruff-`I` sorted; **absolute `healthos_api.*` imports only** (no relative imports anywhere in the service); multi-name imports use parenthesized, one-per-line, alphabetized blocks; `datetime` always imported as `from datetime import UTC, datetime` and timestamps built as `datetime.now(UTC)`.

### Registration

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/router.py` — complete file:
```python
from fastapi import APIRouter

from healthos_api.api.routes import auth, health, platform, portal, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(portal.router)
api_router.include_router(platform.router)
```
Modules are imported as modules and referenced as `<module>.router`. Only `health` gets a prefix at include time. `api/__init__.py` is `"""HTTP API package."""`; `api/routes/__init__.py` is `"""Versioned route modules."""` — **no re-exports, nothing to update in either file.**

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/main.py:78` mounts the aggregate:
```python
    app.include_router(api_router, prefix="/api/v1")
    app.add_api_route("/metrics", metrics_response, include_in_schema=False)
    install_error_handlers(app)
```
So a portal path is `/api/v1/portal/...`. App title `"HealthOS Core API"`; `/docs` disabled in production; middleware stack (outermost-last added): `SessionMiddleware`, `CORSMiddleware` (`allow_credentials=True`), `TrustedHostMiddleware`, `SecurityHeadersMiddleware`, `DistributedRateLimitMiddleware(default_limit=600)`, `RequestBodyLimitMiddleware`, `PrometheusMiddleware`, `RequestContextMiddleware`. Shared clients live on `app.state`: `db_engine`, `session_factory`, `redis`, `http` (`httpx.AsyncClient(timeout=Timeout(60))`).

### Checklist for a new domain router to look native
1. Create `healthos_api/<domain>/{__init__.py (one-line docstring), schemas.py, service.py, access.py?}`.
2. Create `healthos_api/api/routes/<domain>.py` with `router = APIRouter(prefix="/<domain>", tags=["<domain>"])`.
3. Add `<domain>` to the `from healthos_api.api.routes import ...` line and one `api_router.include_router(<domain>.router)` in `api/router.py`.
4. Gate every endpoint with `context: Annotated[AuthContext, Depends(require_permissions("..."))]`; add `dependencies=[Depends(enforce_csrf)]` to every mutating route.
5. Seed any new permission name in a new Alembic migration under `services/api/migrations/versions/` following `0003_portal_domain.py:196-219` (explicit integer ids + `role_permissions` rows).
6. Scope reads by `context.tenant_id` with an `account_type.value != "admin"` bypass; write `AuditEvent` (never its hash columns) in the same `db.commit()` as the mutation.
7. `services/api/tests/test_openapi_contract.py` asserts that every mutating `/api/v1/portal*` operation declares a 2xx response — keep explicit `status_code=` on new mutating routes.


<!-- ===== raw scout: a3bc6a3c1007a50be ===== -->

# HealthOS AI service — extension map

## 1. Agent teams registered today

Source of truth: `/Users/manastole/Projects/Healthcare/services/ai/src/healthos_ai/teams/definitions.py`. Six teams, `TeamName(StrEnum)` — the enum *value* is the wire id used in the API, DB, RBAC, and knowledge/memory scoping.

| id (`TeamName` value) | enum member | model setting attr | allowed account_types | specialists (subagent names) |
|---|---|---|---|---|
| `patient` | `PATIENT` | `patient_model` | patient, doctor, hospital, admin | patient_assistant, symptom_assessment, medical_records, medication, appointment, telemedicine |
| `insurance` | `INSURANCE` | `insurance_model` | patient, hospital, insurance, admin | benefits_analyst, eligibility_verification, claims, prior_authorization, policy, cost_estimation |
| `clinical` | `CLINICAL` | `clinical_model` | doctor, hospital, admin | physician_assistant, nurse_assistant, care_coordinator, referral_coordinator, clinical_documentation, medical_coding |
| `administrative` | `ADMINISTRATIVE` | `administrative_model` | doctor, hospital, insurance, admin | billing, revenue_cycle, insurance_verification, scheduling_coordination, customer_support, escalation |
| `infrastructure` | `INFRASTRUCTURE` | `infrastructure_model` | admin | workflow_orchestrator, planner, router, memory_manager, knowledge_retrieval, tool_executor, guardrails, security_compliance, audit_logger, monitoring |
| `document_intelligence` | `DOCUMENT_INTELLIGENCE` | `document_model` | patient, doctor, hospital, insurance, admin | ocr, extraction, classification, validation, summarization |

There is no separate "agent registry": `agents/` is nearly empty (`agents/factory.py` only exposes `new_workflow()` returning an uncompiled `StateGraph(AgentOSState)`; `agents/state.py` re-exports `AgentOSState`). Specialists are DeepAgents subagents created on the fly from `TeamDefinition.specialists`.

## 2. How to add a team / agent (exact pattern)

Everything is data-driven from one dict. **Primary file to edit: `services/ai/src/healthos_ai/teams/definitions.py`.**

```python
class TeamName(StrEnum):
    ...
    PAYER_OPERATIONS = "payer_operations"          # 1. add enum member (value <= 64 chars: DB columns are String(64))

TEAM_DEFINITIONS = {
    ...
    TeamName.PAYER_OPERATIONS: TeamDefinition(     # 2. add dict entry
        TeamName.PAYER_OPERATIONS,
        "Payer-side claim adjudication support",
        frozenset({"insurance", "admin"}),         # 3. RBAC lives here
        "payer_operations_model",                  # 4. MUST be an attribute name on Settings
        (
            _specialist("claim_adjudication", "Prepare adjudication evidence for human review"),
            _specialist("appeals", "Draft appeal packets for reviewer attestation"),
        ),
    ),
}
```

Then:
- **`services/ai/src/healthos_ai/config.py`** — add `payer_operations_model: str = "healthos-openai"` (env var `PAYER_OPERATIONS_MODEL`, case-insensitive, `.env` loaded, `extra="ignore"`). `TeamAgentFactory.create` does `getattr(self._settings, definition.model_setting)`, so a missing attr is an `AttributeError` at first run.
- Adding a specialist to an existing team = append one `_specialist(name, purpose)` tuple entry. Nothing else.
- **Ordering matters**: `allowed_teams()` preserves `TEAM_DEFINITIONS` insertion order, and both `RunService.execute` (`permitted[0]`, `queue/runs.py:88`) and `AgentOrchestrator._route` fallback (`orchestration/graph.py:90`) use index 0 as the default team. Append new teams at the end; do not insert at the top.
- Optional but expected by tests: add a `RoutingCase` in `services/ai/src/healthos_ai/evaluation/cases.py`.
- Tests that constrain you: `services/ai/tests/test_agent_quality.py` (every team needs >=2 specialists, non-empty `allowed_account_types`, non-empty instructions; every routing case's expected team must be RBAC-allowed) and `tests/test_operating_system.py::test_rbac_restricts_clinical_and_infrastructure_teams` (asserts `set(allowed_teams("admin")) == set(TeamName)` — a new team must include `admin`).
- `TeamName` is embedded in the public Pydantic schemas, so regenerate the spec: `make openapi` → `scripts/export_openapi.py` → `docs/api/openapi-ai.json`. `make verify` runs it.
- Doc table to update: `docs/architecture/ai-operating-system.md`.

Team graph construction (`services/ai/src/healthos_ai/teams/factory.py`) — DeepAgents, cached per `(TeamName, provider)`:

```python
graph = create_deep_agent(
    name=f"{team_name.value}_team",
    model=model,                       # ChatOpenAI via LiteLLM
    tools=self._tools,                 # global tool list (local + MCP)
    subagents=cast(Any, subagents),    # [{"name","description","system_prompt","tools","model"}]
    context_schema=RuntimeContext,
    system_prompt=f"{SAFETY_PROMPT}\nYou lead the {team_name.value} team. Mission: ...",
)
```

`SAFETY_PROMPT` is prepended to the lead prompt and to every specialist prompt; `tests/test_agent_quality.py` asserts on three substrings in it ("autonomous clinical decisions", "coverage determinations", "tenant-authorized") — keep them if you edit it.

## 3. How tools are defined and bound

File: `services/ai/src/healthos_ai/tools/catalog.py`. Pattern is a closure factory `build_tools(knowledge, memories, messages, audit) -> list[Any]` containing `@tool`-decorated async functions with a **`ToolRuntime[RuntimeContext]` injected parameter named `runtime`** (`from langchain.tools import ToolRuntime, tool`):

```python
@tool
async def search_knowledge(query: str, runtime: ToolRuntime[RuntimeContext]) -> str:
    """Docstring is the tool description shown to the model."""
    async def operation() -> str: ...
    return str(await audited("search_knowledge", runtime, operation))
```

Conventions to copy for new domain tools:
- Return `str` (callers wrap in `str(...)`); guard on context (`runtime.context.memory_mode`, `.team`, `.account_type`, `.allowed_teams`) and return a denial *string* rather than raising for policy refusals.
- Wrap the body in the local `audited(name, runtime, operation)` helper — it increments `AI_TOOL_CALLS.labels(name, "success"|"failure")` and writes `tool.completed` / `tool.failed` metadata-only audit rows (never log args/PHI: `AuditLogger` docstring in `observability/audit.py`).
- Append the tool to the returned list at the end of `build_tools`.

Binding (`services/ai/src/healthos_ai/bootstrap.py:73-75`):
```python
mcp_tools = await load_mcp_tools(settings)          # remote MCP, filtered by settings.mcp_tool_allowlist
tools = build_tools(knowledge, memories, message_repository, audit)
teams = TeamAgentFactory(settings, llm, tools, mcp_tools)
```

**Important gap for domain tools:** there is no per-team tool allowlist. `TeamAgentFactory.__init__` flattens `[*tools, *mcp_tools]` and hands the identical list to every team lead *and* every specialist. Scoping an insurance-only tool today means either (a) checking `runtime.context.team` / `account_type` inside the tool, or (b) extending `TeamDefinition` with a `tool_names: frozenset[str]` field and filtering in `TeamAgentFactory.create`. Also note tools are constructed once at process start (both API and worker go through `build_runtime`), so any HTTP client a tool needs must be created in `bootstrap.py` and passed into `build_tools`.

Writes are not done by tools. The mutation path is human-in-the-loop `ActionProposal`: allowed action types are a regex allowlist in `api/schemas.py:96` (`hold_slot|book|reschedule|verify_eligibility|estimate_cost|submit_claim|submit_prior_authorization|purchase_policy|draft_clinical_document|draft_medical_codes`) plus `HIGH_RISK_ACTIONS` in `api/routes.py:34`. New domain actions must be added to both.

The mounted MCP server (`mcp/server.py`, `app.mount("/mcp", mcp_app)`) deliberately exposes only `list_agent_teams` and `healthcare_ai_safety_policy` — no execution.

## 4. `POST /ai/v1/runs` contract

Router: `services/ai/src/healthos_ai/api/routes.py:88`, mounted with prefix `/ai/v1` in `main.py:63`. Schemas: `services/ai/src/healthos_ai/api/schemas.py`.

```python
class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=30_000)
    team: TeamName | None = None                          # explicit team; 403 if not RBAC-allowed
    execution_mode: ExecutionMode = ExecutionMode.SYNC     # "sync" | "async"
    provider: ProviderPreference = ProviderPreference.AUTO # "auto"|"openai"|"anthropic"|"gemini"
    memory_mode: MemoryMode = MemoryMode.READ              # "none"|"read"|"read_write"
    thread_id: UUID | None = None                          # reuse for LangGraph checkpoint continuity

class RunResponse(BaseModel):
    id: UUID
    thread_id: UUID
    status: str                                            # queued|running|completed|failed
    selected_team: TeamName | None = None
    collaborators: list[TeamName] = []
    response: str | None = None                            # decrypted final answer
    error_code: str | None = None                          # exception class name, <=100 chars
    created_at: datetime
    completed_at: datetime | None = None
```

Behavior: `201 CREATED` always on success (both modes). Auth via `CurrentIdentity`. `403` if `payload.team` not in `allowed_teams(account_type)` (`PermissionError` from `RunService.create`). Sync mode runs the graph inline and returns the completed run; a graph failure → `502 "Agent execution failed"`. Async mode returns `status="queued"` after `XADD` to Redis stream `healthos:ai:runs` (worker: `healthos-ai-worker` → `worker.py`).

Related endpoints on the same router: `GET /ai/v1/agents` (`list[AgentCatalogEntry]`, RBAC-filtered), `GET /ai/v1/runs/{run_id}`, `GET /ai/v1/runs/{run_id}/events` (SSE over Redis pub/sub `healthos:ai:run:{run_id}`), `POST /ai/v1/documents`, `POST|GET|DELETE /ai/v1/memories`, `GET /ai/v1/audit` (admin), `POST /ai/v1/action-proposals[/{id}/confirm|/cancel]`.

Client path: browser → gateway `/ai/{path}` proxy (`services/gateway/src/healthos_gateway/api/proxy.py:76`, forwards only accept/authorization/content-type/cookie/x-request-id) → AI service. Web caller: `apps/web/components/portal/ai-assistant.tsx:42`.

## 5. How the AI service authenticates to the core API

`services/ai/src/healthos_ai/auth/identity.py` — this is the *only* outbound call to core today:

```python
response = await client.get(
    f"{str(settings.api_service_url).rstrip('/')}/api/v1/auth/session",
    headers={"Authorization": f"Bearer {token}"}, timeout=5)
```

- Token source: `Authorization: Bearer …` header, else `healthos_access` cookie (`_credential`), i.e. **the end user's token is simply relayed**. There is no service account, API key, mTLS, or client-credentials flow anywhere in the repo (grepped `service_token|internal_api_key|x-service|client_credentials` across `services/` and `packages/` — zero hits).
- Client: `httpx.AsyncClient` created in `main.py` lifespan as `app.state.http`. Config: `api_service_url` (`API_SERVICE_URL`, default `http://localhost:8000`).
- Response is core's `UserSummary` (`services/api/src/healthos_api/auth/schemas.py:110`): `id, email, account_type, status, email_verified, phone_verified, roles, patient_id, tenant_id`. AI maps a subset into `Identity` and caches JSON in Redis under `healthos:ai:identity:{sha256(token)}` for `identity_cache_ttl_seconds` (5s). `401` → 401; any other 4xx/5xx or transport error → 503.
- `Identity.tenant_id` is `str(user.id)` — tenancy today is per-user, not per-org (core's `tenant_id` claim is ignored).

**Blockers you must solve to have tools call core endpoints:**
1. `RuntimeContext` (`orchestration/context.py`) carries no credential — run_id, thread_id, actor_user_id, tenant_id, account_type, team, allowed_teams, memory_mode only. Tools therefore have nothing to authenticate with.
2. Async runs execute in `worker.py`, long after the request; `RuntimeResources` (`bootstrap.py:27`) has no `http` field at all. Even sync runs never pass the token down into the graph.
   → Options: add a field to `RuntimeContext` + store the user token encrypted on `AgentRun` via `DataCipher` (short TTL), or add a real service-to-service credential to core and an on-behalf-of header.
3. Core mutation endpoints depend on `enforce_csrf` (`services/api/src/healthos_api/core/security.py:110`), but it **short-circuits when an `Authorization` header is present and no refresh cookie is sent** — so a pure bearer call from the AI service is CSRF-exempt. Read endpoints need the relevant permission/role (`require_permissions("portal:read")`, `require_roles("patient", …)`).
4. Useful core targets (all under `/api/v1`, `portal` router prefix `/portal`): `/portal/overview`, `/portal/resources/{category}`, `/portal/documents`, `/portal/patient/providers/availability`, `/portal/patient/appointments/book`, `/portal/patient/labs/availability`, `/portal/patient/labs/book`, `/portal/patient/insurance/marketplace`, `/portal/patient/insurance/purchase`, `/portal/integrations/fhir`, `/portal/integrations/insurance`, `/portal/payments/intents`.

## 6. LangGraph / DeepAgents versions and usage

Declared in `services/ai/pyproject.toml`; resolved in `/Users/manastole/Projects/Healthcare/uv.lock`:

| package | constraint | locked |
|---|---|---|
| `deepagents` | `>=0.6,<1` | **0.6.12** |
| `langgraph` | `>=1.2,<2` | **1.2.7** |
| `langchain` (transitive via deepagents) | — | **1.3.11** |
| `langgraph-checkpoint-postgres` | `>=3.1,<4` | — |
| `langchain-mcp-adapters` | `>=0.3,<1` | — |
| `langchain-openai` | `>=1.1,<2` | — |

Two-layer pattern:
- **Outer graph** (hand-written LangGraph, `orchestration/graph.py`): `StateGraph(AgentOSState, context_schema=RuntimeContext)` with linear nodes `route → plan → retrieve → execute → synthesize`, compiled with an `AsyncPostgresSaver` checkpointer using `EncryptedSerializer.from_pycryptodome_aes()` (key from `LANGGRAPH_AES_KEY`; checkpointer failure is non-fatal, surfaced via `/health/ready`). State is a `TypedDict` (`orchestration/state.py`); context is a frozen dataclass. Routing/planning use `model.with_structured_output(RouteDecision|Plan)`. Invocation: `graph.ainvoke(state, context=ctx, config={"configurable": {"thread_id": str(thread_id)}})`. Team fan-out is bounded by `asyncio.Semaphore(settings.max_concurrent_team_agents)` (default 3) and at most 2 collaborators.
- **Inner agents**: `deepagents.create_deep_agent(...)` per team (section 2), invoked the same way with `context=RuntimeContext`. `deepagents 0.6.12` `SubAgent` TypedDict keys: required `name`, `description`, `system_prompt`; optional `tools`, `model`, `middleware`, `response_format`. Note built-ins are always merged in (`write_todos`, filesystem tools, `execute`, `task`) — dropping one requires a `HarnessProfile` with `excluded_tools`.
- Models are provider-neutral through LiteLLM: `LLMGateway.chat(model, provider)` returns `ChatOpenAI` pointed at `litellm_base_url` with `litellm_master_key`; a non-`auto` provider preference rewrites the model alias to `healthos-{provider}`.

## 7. RBAC: account_type → allowed teams

Derived from `allowed_teams()` (`teams/definitions.py:146`), evaluated in insertion order. `account_type` values come from core's `AccountType` StrEnum (`services/api/src/healthos_api/db/models.py:29`): patient, doctor, hospital, insurance, admin.

| account_type | allowed teams (in order) |
|---|---|
| `patient` | patient, insurance, document_intelligence |
| `doctor` | patient, clinical, administrative, document_intelligence |
| `hospital` | patient, insurance, clinical, administrative, document_intelligence |
| `insurance` | insurance, administrative, document_intelligence |
| `admin` | patient, insurance, clinical, administrative, infrastructure, document_intelligence (all) |

Enforcement points: `RunService.create` (403 on explicit team), `AgentOrchestrator._route` (raises `PermissionError` for a disallowed `requested_team`; clamps LLM-chosen team/collaborators to the allowed set), `GET /ai/v1/agents` filtering, `POST /ai/v1/documents` and `POST /ai/v1/memories` (403), and `AgentMessageRepository.send` (rejects recipients outside `context.allowed_teams`). `Identity.is_admin` is `account_type == "admin" or "admin" in roles` and only gates `/ai/v1/audit` and cross-owner run reads.


<!-- ===== raw scout: ac407ecf5b961c059 ===== -->

# HealthOS web app — design/architecture audit

Repo root: `/Users/manastole/Projects/Healthcare` (pnpm + turbo monorepo, `apps/*` + `packages/typescript/*`)

---

## 1. Tailwind version + full theme config

**Version: Tailwind CSS v3.4.19** (spec `^3.4.17` in `/Users/manastole/Projects/Healthcare/apps/web/package.json`, resolved `3.4.19` in `pnpm-lock.yaml`). Classic v3 setup: `postcss.config.mjs` + `autoprefixer` + `tailwind.config.ts`.

`/Users/manastole/Projects/Healthcare/apps/web/postcss.config.mjs`:
```js
const config = { plugins: { tailwindcss: {}, autoprefixer: {} } };
export default config;
```

`/Users/manastole/Projects/Healthcare/apps/web/tailwind.config.ts` (complete):
```ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/typescript/ui/src/**/*.{ts,tsx}",
  ],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary:   { DEFAULT: "hsl(var(--primary))",   foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted:     { DEFAULT: "hsl(var(--muted))",     foreground: "hsl(var(--muted-foreground))" },
        accent:    { DEFAULT: "hsl(var(--accent))",    foreground: "hsl(var(--accent-foreground))" },
        card:      { DEFAULT: "hsl(var(--card))",      foreground: "hsl(var(--card-foreground))" },
      },
    },
  },
  plugins: [animate],
};
export default config;
```

Notes:
- `theme.extend` contains **only `colors`**. There is **no `borderRadius` mapping** — so `--radius: 0.9rem` is a **dead token** (nothing consumes it; `rounded-lg` = Tailwind default 0.5rem).
- **Dark mode strategy: `["class"]`, but completely unimplemented.** There is no `.dark {}` block in `globals.css`, no theme toggle, and `grep "dark:"` across `apps/web` + `packages/typescript/ui/src` returns **zero matches**. Dark mode is configured-but-dead.
- Related deps: `tailwindcss-animate@1.0.7`, `postcss@8.5.16` (root override `"postcss": ">=8.5.10 <9"`), `autoprefixer@10.5.2`, `prettier-plugin-tailwindcss@^0.6.14` (no `.prettierrc` exists — plugin is only listed in root `devDependencies`, so it is **not actually loaded** by Prettier).

---

## 2. Exact design tokens (CSS custom properties)

`/Users/manastole/Projects/Healthcare/apps/web/app/globals.css` — the entire file is 58 lines:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 168 30% 98%;
    --foreground: 222 47% 11%;
    --card: 0 0% 100%;
    --card-foreground: 222 47% 11%;
    --primary: 171 77% 27%;
    --primary-foreground: 166 76% 97%;
    --secondary: 210 40% 96%;
    --secondary-foreground: 222 47% 11%;
    --muted: 210 40% 96%;
    --muted-foreground: 215 16% 47%;
    --accent: 166 76% 94%;
    --accent-foreground: 173 80% 20%;
    --border: 214 32% 91%;
    --input: 214 32% 91%;
    --ring: 173 80% 29%;
    --radius: 0.9rem;
  }

  * { @apply border-border; }
  body {
    @apply bg-background text-foreground antialiased;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  ::selection { @apply bg-primary/20 text-foreground; }
  button, a, input, select, textarea {
    @apply focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2;
  }
}

@layer utilities {
  .hero-glow {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(circle at 12% 18%, hsl(168 76% 91% / 0.75), transparent 32%),
      radial-gradient(circle at 88% 42%, hsl(201 92% 92% / 0.62), transparent 30%);
    pointer-events: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

**17 tokens total**, all bare HSL triplets (v3/shadcn-legacy format). Brand hue = teal/emerald (`--primary: 171 77% 27%`). `themeColor: "#10b981"` in `layout.tsx` and `manifest.ts`.

**Tokens that DO NOT exist** (shadcn/ui expects them): `--popover`, `--popover-foreground`, `--destructive`, `--destructive-foreground`, `--chart-1..5`, `--sidebar*`, and any `.dark` variants.

Design reality check: most of the UI **bypasses tokens and hardcodes palette classes** — `bg-slate-950`, `text-slate-100/300/400/500/600/900`, `bg-emerald-500`, `text-emerald-400/600/700`, `bg-teal-50`, `bg-red-50 text-red-700`, `bg-rose-500`, `bg-violet-500`, `bg-amber-500`, `bg-blue-500`, `bg-white`. E.g. `portal-shell.tsx` sidebar is entirely `bg-slate-950`/`bg-emerald-500`; `dashboard.tsx` metric stripes are literal `bg-emerald-500 / bg-blue-500 / bg-amber-500 / bg-violet-500`.

---

## 3. Server vs client split, auth session, cookie names

**There is NO server-side session read anywhere.** `grep "next/headers"`, `cookies()`, and `"use server"` across `apps/web` return **zero matches**. Auth is (a) an edge-middleware cookie-presence check and (b) client-side `useEffect` fetches.

**Server components** (no `"use client"`): `app/layout.tsx`, `app/page.tsx`, `app/manifest.ts`, `app/health/route.ts`, all `app/(auth)/**/page.tsx`, `app/(protected)/**/page.tsx`, `app/[role]/**/page.tsx`, `components/auth/auth-shell.tsx`, `components/auth/form-field.tsx`, `components/auth/account-chooser.tsx`, `components/marketing/role-landing.tsx`, `components/portal/page-heading.tsx`, and **every `@healthos/ui` primitive** (none carry `"use client"` — they work as RSC because they take no handlers, but `Button onClick` usage forces them into client trees).

**Client components** (22, all with `"use client"`): `components/pwa-registration.tsx`, `components/layout/portal-shell.tsx`, `components/layout/logout-button.tsx`, all 9 stateful `components/auth/*`, and all 9 stateful `components/portal/*` (`module-workspace`, `dashboard`, `record-workspace`, `admin-workspace`, `ai-assistant`, `documents-workspace`, `notifications-workspace`, `integration-actions`, `patient-booking-workspace`, `patient-insurance-workspace`).

Server pages are thin shells that immediately delegate:
```tsx
// app/(protected)/layout.tsx
export default function ProtectedLayout({ children }: { children: ReactNode }) {
  return <PortalShell>{children}</PortalShell>;   // PortalShell is "use client"
}
```

**Cookie names** — `healthos_access`, `healthos_refresh`, `healthos_csrf`. Only place cookies are read server-side is the edge middleware, and only for *presence*:

`/Users/manastole/Projects/Healthcare/apps/web/middleware.ts`:
```ts
const protectedPrefixes = ["/dashboard", "/profile", "/portal"];
export function middleware(request: NextRequest) {
  const isProtected = protectedPrefixes.some((p) => request.nextUrl.pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();
  const hasSession =
    request.cookies.has("healthos_access") || request.cookies.has("healthos_refresh");
  if (hasSession) return NextResponse.next();
  const loginUrl = new URL("/login/patient", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}
export const config = { matcher: ["/dashboard/:path*", "/profile/:path*", "/portal/:path*"] };
```

Backend contract (`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/auth/cookies.py` + `config.py`):
- `healthos_access` — HttpOnly, path `/`, SameSite=Lax, max-age 15 min
- `healthos_refresh` — HttpOnly, **path `/api/v1/auth`**, SameSite=Lax, max-age 30 d
- `healthos_csrf` — **`httponly=False`** (JS-readable by design), path `/`, SameSite=Lax
- `secure` driven by `AUTH_COOKIE_SECURE` (must be true in prod)

The client session shape is fetched, not decoded: `authenticatedFetch<UserSummary>("/api/v1/auth/session")` in both `portal-shell.tsx` and `module-workspace.tsx` (duplicated fetch — the same two requests fire twice per portal page load).

---

## 4. How the web app calls the backend — exact code

Single wrapper: `/Users/manastole/Projects/Healthcare/apps/web/lib/auth.ts`. Base URL from `/Users/manastole/Projects/Healthcare/apps/web/lib/env.ts`:
```ts
import { z } from "zod";
const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z.union([z.literal(""), z.string().url()]).default(""),
});
export const env = publicEnvSchema.parse({ NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL });
```
(`NEXT_PUBLIC_API_URL=http://localhost:8080` in `.env`/`.env.example`/`docker-compose.yml`; empty string = same-origin.)

```ts
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

let refreshInFlight: Promise<unknown> | null = null;

function getApiUrl(path: string): string { return `${env.NEXT_PUBLIC_API_URL}${path}`; }

function refreshSession(): Promise<unknown> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        return await apiFetch("/api/v1/auth/refresh", { method: "POST" });
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
        await new Promise((resolve) => setTimeout(resolve, 300));
        return apiFetch("/api/v1/auth/refresh", { method: "POST" });
      }
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const csrf = getCookie("healthos_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(getApiUrl(path), { ...init, headers, credentials: "include" });
  } catch {
    throw new Error(
      `Unable to reach the HealthOS API at ${getApiOriginLabel()}. Verify the gateway is running and NEXT_PUBLIC_API_URL is correct.`,
    );
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string" ? detail
      : Array.isArray(detail)
        ? detail.map((item) =>
            typeof item === "object" && item && "msg" in item ? String(item.msg) : "Invalid input",
          ).join(". ")
        : "Request failed";
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function authenticatedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    await refreshSession();
    return apiFetch<T>(path, init);
  }
}
```

Also in `lib/auth.ts`: `getCookie(name)` (reads `document.cookie`, SSR-safe returns `undefined`), `accountTypes`, `publicSignupTypes`, `isAccountType`, `accountLabel`.

Key characteristics:
- Cookie-based auth (`credentials: "include"`), **no `Authorization` header anywhere**.
- Double-submit CSRF: `X-CSRF-Token` on non-GET/HEAD only.
- Single-flight refresh on 401, with a 409-retry (refresh-rotation grace).
- Error handling is **per-component `useState<string|null>` + a red `<p>`** — no error boundary, no toast, no retry UI. Every workspace repeats:
  ```tsx
  {error ? <p className="mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
  ```
- Loading is ad-hoc `animate-pulse` divs; no shared Skeleton primitive.
- **One raw `fetch` bypasses the wrapper** — `components/portal/documents-workspace.tsx:67` (blob download):
  ```ts
  const response = await fetch(
    `${env.NEXT_PUBLIC_API_URL}/api/v1/portal/documents/${item.id}/content`,
    { credentials: "include", headers },
  );
  ```
- No data-fetching library (no SWR/React Query), no Server Actions, no `revalidate`.
- Endpoints in use: `/api/v1/auth/{login/:type,refresh,logout,session,sessions,otp/verify,password/reset}`, `/api/v1/app-manifest`, `/api/v1/users/me`, `/api/v1/users/me/job-watch`, `/api/v1/portal/{overview,documents,resources/:slug,notifications,payments/intents,admin/settings/:key}`, `/api/v1/portal/patient/{providers/availability,labs/availability,labs/book,appointments/book,insurance/marketplace,insurance/purchase}`, and the AI service at **`/ai/v1/runs`** (same base URL, different prefix).
- CSP `connect-src` is built in `next.config.ts` from `NEXT_PUBLIC_API_URL` origin + `'self' https: wss:` (+ localhost:8080 in non-prod).

---

## 5. Existing UI primitives API

Package `@healthos/ui` (`/Users/manastole/Projects/Healthcare/packages/typescript/ui/`). **No barrel/index** — subpath exports only:
```json
"exports": {
  "./badge": "./src/badge.tsx", "./button": "./src/button.tsx", "./card": "./src/card.tsx",
  "./input": "./src/input.tsx", "./label": "./src/label.tsx", "./table": "./src/table.tsx",
  "./textarea": "./src/textarea.tsx"
}
```
Deps: `@radix-ui/react-slot@^1.2.3`, `class-variance-authority@^0.7.1`, `@healthos/utils`. `tsconfig.json` `include: ["src/**/*.tsx"]` (a `.ts` file added here is **not typechecked**).

**`cn` helper lives in a separate package** — `/Users/manastole/Projects/Healthcare/packages/typescript/utils/src/index.ts`:
```ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]): string { return twMerge(clsx(inputs)); }
export function assertNever(value: never): never { throw new Error(`Unexpected value: ${String(value)}`); }
```
`clsx@^2.1.1` + **`tailwind-merge` spec `^3.3.0`, resolved `3.6.0`**.

**cva is used in exactly 2 files** — `button.tsx` and `badge.tsx`.

| Primitive | API |
|---|---|
| `Button` | `forwardRef<HTMLButtonElement, ButtonProps>`; `asChild?: boolean` (Radix `Slot`); `variant: "default" \| "outline" \| "ghost"`; `size: "default" \| "sm" \| "lg"`; exports `buttonVariants`. **No `secondary`/`destructive`/`link` variants, no `icon` size.** |
| `Badge` | plain function (no forwardRef, no `asChild`); `variant: "default" \| "secondary" \| "outline"`. **No `destructive`.** |
| `Card` | `Card`, `CardHeader`, `CardTitle` (`<h3>`), `CardDescription` (`<p>`), `CardContent` — all forwardRef, `cn(...)` only, no cva. **No `CardFooter`, no `CardAction`.** |
| `Input` | forwardRef, `React.ComponentProps<"input">`, no variants |
| `Label` | forwardRef, `React.ComponentProps<"label">`, plain `<label>` — **not Radix `@radix-ui/react-label`** |
| `Textarea` | forwardRef, `min-h-24` |
| `Table` | `Table/TableHeader/TableBody/TableRow/TableHead/TableCell` — **plain functions, no forwardRef, spread-then-className (`{...props} className={cn(..., props.className)}`)**. No `TableCaption`/`TableFooter`, no wrapper div. |

Exact cva definitions:
```ts
// button.tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  { variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
      size: { default: "h-10 px-4 py-2", sm: "h-9 rounded-md px-3", lg: "h-11 rounded-md px-8" },
    },
    defaultVariants: { variant: "default", size: "default" } },
);

// badge.tsx
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  { variants: { variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground" } },
    defaultVariants: { variant: "default" } },
);
```

Missing primitives that portal code hand-rolls today: Select (raw `<select className="h-10 w-full rounded-md border bg-background px-3 text-sm">` in `documents-workspace.tsx`), Dialog/Sheet (the mobile sidebar in `portal-shell.tsx` is a hand-rolled fixed div + backdrop `<button>`), Skeleton, Alert, Toast, Tabs, Avatar, DropdownMenu, Separator, Tooltip, Form.

---

## 6. Routing structure + what `/portal/[module]` renders

```
app/
├─ layout.tsx                          RootLayout (html/body, no shell, no ThemeProvider)
├─ page.tsx                            "/"  marketing landing (server)
├─ manifest.ts                         /manifest.webmanifest
├─ health/route.ts                     GET /health
├─ (auth)/                             no group layout; each page wraps <AuthShell>
│   ├─ login/page.tsx                  /login  (AccountChooser)
│   ├─ login/[accountType]/page.tsx    /login/{patient|doctor|hospital|insurance|admin}
│   ├─ signup/page.tsx                 /signup
│   ├─ signup/[accountType]/page.tsx   /signup/{...}  (admin -> notFound)
│   ├─ forgot-password | reset-password | verify-otp
├─ auth/callback/page.tsx              /auth/callback  (Google OAuth)
├─ [role]/                             marketing + role-scoped auth; roles map: patient, doctors->doctor, hospital, insurance, admin
│   ├─ page.tsx                        /patient, /doctors, /hospital, /insurance, /admin
│   ├─ login/page.tsx                  /{role}/login
│   └─ signup/page.tsx                 /{role}/signup
└─ (protected)/                        layout.tsx -> <PortalShell>
    ├─ dashboard/page.tsx              /dashboard -> <Dashboard />
    ├─ profile/page.tsx                /profile   -> <ProfileForm /> + <JobWatchForm />
    └─ portal/[module]/page.tsx        /portal/:module
```

Note: `[role]` is a catch-all-ish dynamic segment at the root that collides conceptually with `/login`, `/signup`, `/dashboard` etc.; `/login` wins because static segments beat dynamic ones, but `/{anything-else}` hits `[role]/page.tsx` → `notFound()`.

`app/(protected)/portal/[module]/page.tsx` (whole file):
```tsx
import { ModuleWorkspace } from "@/components/portal/module-workspace";
export default async function PortalModulePage({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  return <ModuleWorkspace slug={module} />;
}
```

`ModuleWorkspace` (client) fetches session + manifest, shows pulse skeleton, then **dispatches by slug**:
```tsx
const moduleDefinition = manifest.modules.find((item) => item.key === slug);
if (!moduleDefinition) return /* "This tool isn't available" card */;
const formDefinition = manifest.forms.find((item) => item.key === slug);
if (slug === "documents")   return <DocumentsWorkspace />;
if (slug === "notifications") return <NotificationsWorkspace />;
if (slug === "ai_assistant")  return <AIAssistant />;
if (slug === "lab_bookings")  return <PatientBookingWorkspace kind="labs" />;
if (slug === "buy_insurance") return <PatientInsuranceWorkspace marketplace />;
if (slug === "insurance")     return <PatientInsuranceWorkspace />;
if (slug === "appointments" && user?.account_type === "patient")
  return <PatientBookingWorkspace kind="appointments" />;
if (["analytics","audit_logs","user_management","monitoring","system_settings"].includes(slug))
  return <AdminWorkspace slug={slug} />;
return <RecordWorkspace slug={slug} moduleDefinition={moduleDefinition} formDefinition={formDefinition} />;
```

The default `RecordWorkspace` is a generic CRUD table driven by (a) the server manifest's JSON-Schema `formDefinition.schema.properties` or (b) the hardcoded fallback `workflowFields[slug]` in `lib/portal.ts`. `lib/portal.ts` (770 lines) holds `moduleCatalog` (~48 modules), `roleModules` (per-`AccountType` slug lists), `roleMeta`, `dashboardModule`, and `workflowFields` — icons come from `lucide-react@0.525.0`. `lib/app-manifest.ts` maps server manifest keys → Lucide icons with `FileText` fallback. **Sidebar nav is driven by the server manifest, not `roleModules`** (`roleModules` is currently only referenced by marketing/role-landing paths — `portal-shell.tsx` uses `manifestModules(manifest)`).

---

## 7. api-types contracts

`/Users/manastole/Projects/Healthcare/packages/typescript/api-types/src/index.ts` — a single hand-written 241-line `.ts` file, **no zod, no codegen** (there are OpenAPI dumps at `docs/api/openapi-core.json` and `docs/api/openapi-ai.json` but nothing generates from them).

Exported: `ServiceStatus`, `HealthResponse`, `ErrorDetail`, `ErrorResponse`, `AccessToken`, `AccountType` (`"patient"|"doctor"|"hospital"|"insurance"|"admin"`), `UserStatus` (`pending_verification|pending_review|active|suspended|disabled`), `UserSummary`, `DefinitionKind` (`module|form|dashboard|workflow|content`), `ApplicationDefinition`, `AppManifest`, `ConsentGrant`, `WorkflowInstance`, `AuthResponse`, `ProfileResponse`, `SessionResponse`, `JobWatchSource`, `JobWatchResponse`, `PortalRecord`, `DashboardMetric`, `PortalDashboard`, `PortalNotification`, `JobWatchUpdate`, `DocumentAsset`.

Load-bearing shapes:
```ts
export interface ApplicationDefinition {
  id: string; tenant_id?: string | null; kind: DefinitionKind; key: string; version: number;
  status: "draft" | "review" | "published" | "retired";
  account_types: AccountType[]; locale: string;
  schema: Record<string, unknown>;        // JSON Schema -> drives RecordWorkspace fields
  presentation: Record<string, unknown>;  // label/description/noun, all `unknown` -> cast at call sites
  rules: Array<Record<string, unknown>>;
  effective_at?: string | null; published_at?: string | null; created_at: string; updated_at: string;
}
export interface AppManifest {
  tenant_id: string; account_type: AccountType; locale: string; generated_at: string; version: string;
  modules: ApplicationDefinition[]; forms: ApplicationDefinition[]; dashboards: ApplicationDefinition[];
  workflows: ApplicationDefinition[]; content: ApplicationDefinition[];
}
export interface PortalRecord {
  id: string; category: string; title: string; status: string;
  patient_user_id?: string | null; assigned_user_id?: string | null; external_reference?: string | null;
  occurred_at?: string | null; due_at?: string | null;
  amount_cents?: number | null; currency?: string | null;
  data: Record<string, unknown>; created_at: string; updated_at: string;
}
export interface PortalDashboard {
  account_type: AccountType; display_name: string; metrics: DashboardMetric[];  // {label,value,trend,tone}
  recent: PortalRecord[]; unread_notifications: number; integrations: Record<string, boolean>;
}
```

**Contracts NOT in api-types** — locally re-declared interfaces that will drift: `PolicyOffer` (`patient-insurance-workspace.tsx:19`), `Slot` (`patient-booking-workspace.tsx:17`), `AIRun` + `Message` (`ai-assistant.tsx:17`), `Monitoring`/`AdminRow` (`admin-workspace.tsx`). Also `DashboardMetric.tone` is fetched but **never used** — `dashboard.tsx` ignores it and hardcodes stripe colors by index.

---

## 8. What breaks on Tailwind v4 / shadcn install

### Hard breaks on Tailwind v4 (build fails or renders wrong)

1. **`@tailwind base/components/utilities` is removed.** `globals.css:1-3` must become `@import "tailwindcss";`.
2. **PostCSS plugin moved.** `postcss.config.mjs` `{ tailwindcss: {} }` → must be `{ "@tailwindcss/postcss": {} }`; `autoprefixer` must be dropped (v4 bundles Lightning CSS). Leaving it as-is fails the build outright.
3. **JS config is not auto-loaded.** `tailwind.config.ts` is ignored unless you add `@config "../tailwind.config.ts";`. Without it *every* token color (`bg-primary`, `text-muted-foreground`, `border-border`, `bg-card`, …) stops existing → the app renders essentially unstyled.
4. **`theme.container` config was removed in v4.** `center: true, padding: "2rem", screens: { "2xl": "1400px" }` has no equivalent; `container` in v4 is just `width: 100%` + breakpoint maxes with **no centering and no padding**. `container` is used on 8 layout wrappers — `app/page.tsx` (header/hero/features/footer), `app/(protected)/profile/page.tsx`, `components/marketing/role-landing.tsx`. **All of them lose centering + 2rem padding.** Needs `@utility container { margin-inline: auto; padding-inline: 2rem; }`.
5. **`@layer base { * { @apply border-border } }`** requires `--color-border` to exist in `@theme`. Combined with v4's changed default border color (`gray-200` → `currentColor`), a botched migration produces text-colored borders everywhere.
6. **`darkMode: ["class"]` has no config equivalent** — needs `@custom-variant dark (&:is(.dark *));`. Low impact today (zero `dark:` usages, no `.dark` block) but it means **v4 migration is the moment to actually build dark mode, not preserve it.**
7. **`tailwindcss-animate@1.0.7` is a v3 plugin** and is not v4-compatible; must be swapped for `tw-animate-css`. (Currently it's loaded but no `animate-*` plugin utilities are used beyond core `animate-pulse`, so the swap is cheap.)
8. **Content detection changes.** v4 auto-detects sources but **ignores `node_modules`** — `@healthos/ui` is consumed via a pnpm workspace symlink into `node_modules`, so the explicit glob `"../../packages/typescript/ui/src/**/*.{ts,tsx}"` must be re-expressed as `@source "../../../packages/typescript/ui/src";` or **every class inside Button/Card/Badge/Input/Label/Table/Textarea gets purged.** This is the highest-risk silent failure.

### Visual regressions on v4 (compiles, looks different)

9. **Shadow scale renamed**: v3 `shadow-sm` → v4 `shadow-xs`, v3 `shadow` → v4 `shadow-sm`. Affected: `card.tsx:11` (`shadow-sm` on every Card), `textarea.tsx:11`, `module-workspace.tsx:43`, `auth-shell.tsx:29`, `app/page.tsx:55,64`, plus `shadow-sm shadow-primary/20` combos. All shadows get one step heavier.
10. **`outline-none` → `outline-hidden`.** `focus-visible:outline-none` appears in `globals.css:36` (applied to *every* `button, a, input, select, textarea`) and in `button.tsx:7`, `input.tsx:12`, `textarea.tsx:11`. In v4 `outline-none` means `outline-style: none`, losing the forced-colors-mode transparent outline — an **accessibility regression** across the whole app.
11. **Default `ring` width 3px → 1px** and `ring-offset-*`/`ring-offset-background` semantics changed. Focus rings use explicit `ring-2` so widths survive, but `ring-offset-background` (`button.tsx`, `input.tsx`) depends on the `background` token surviving step 3.
12. **`space-y-*` implementation changed** to `:not(:last-child)` — `CardHeader`'s `space-y-1.5` and several `space-y-*` stacks can shift when children are conditionally rendered (which the portal does constantly).
13. **`h-18` on `app/page.tsx:53`** (`className="container flex h-18 items-center..."`) is currently a **no-op** — Tailwind 3.4's default spacing scale has no `18` and the config adds no `spacing` extension, so the header has no fixed height today. Under v4's dynamic spacing scale, `h-18` suddenly resolves to `4.5rem` and the marketing header changes height. Silent behavior change hidden inside an existing bug.
14. **Browser support drops** to Safari 16.4+ / Chrome 111+ / Firefox 128+ — relevant for a patient-facing PWA (`public/sw.js`, `manifest.ts`).

### Toolchain/infra risks on v4

15. **`infra/docker/web.Dockerfile` is `node:22.17.0-alpine` (musl).** v4 needs the `@tailwindcss/oxide-linux-*-musl` + Lightning CSS musl native binaries. The build runs `pnpm install --frozen-lockfile`, so the lockfile must be regenerated with those optional platform deps present or the Docker build fails. Root `pnpm-workspace.yaml` also has `onlyBuiltDependencies: [sharp]`, which blocks postinstall scripts for anything else.
16. **`prettier-plugin-tailwindcss@0.6.14` with v4** requires the `tailwindStylesheet` option — and there is **no Prettier config file at all** in the repo (only `.prettierignore`), so the plugin is currently inert. `pnpm format` behavior will change once a config appears.

### Pre-existing mismatch worth flagging now

17. **`tailwind-merge` resolved to `3.6.0` while Tailwind is `3.4.19`.** tailwind-merge v3 is built against Tailwind **v4's** class taxonomy. Since `cn()` wraps `twMerge` and is called by *every* primitive and dozens of `className` overrides, v3-only classes that v4 removed or renamed can fail to be recognized as conflicting and won't dedupe correctly (e.g. `shadow` vs `shadow-sm` groups, `flex-grow`, `overflow-ellipsis`, `bg-opacity-*`). This is a latent bug **today**, and it self-resolves when you go to v4. File: `packages/typescript/utils/src/index.ts`.

### What breaks / needs work when installing shadcn/ui

18. **`components.json` aliases are not resolvable by the shadcn CLI.**
    ```json
    "aliases": { "components": "@/components", "utils": "@healthos/utils",
                 "ui": "@healthos/ui", "lib": "@/lib", "hooks": "@/hooks" }
    ```
    The CLI resolves aliases through **tsconfig `paths`**, and `apps/web/tsconfig.json` declares only `{"@/*": ["./*"]}`. `@healthos/ui` and `@healthos/utils` resolve via node_modules workspace symlinks, not paths → the CLI errors on alias resolution, or worse writes files through the symlink into `packages/typescript/ui`. Also `@/hooks` **does not exist** as a directory.
19. **Missing CSS tokens will make new components invisible.** shadcn `dialog`/`dropdown-menu`/`popover`/`select`/`command`/`tooltip` emit `bg-popover text-popover-foreground`; `alert`/`toast`/`button variant="destructive"` emit `bg-destructive text-destructive-foreground`; charts emit `--chart-1..5`; `sidebar` emits `--sidebar-*`. **None of these exist in `globals.css` or in `tailwind.config.ts` colors.** The classes simply won't compile → transparent popovers over transparent backgrounds.
20. **`--radius` is defined (`0.9rem`) but unwired.** shadcn components assume `borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" }` in the config. It's absent, so new components will render at Tailwind's default radii while existing ones use ad-hoc `rounded-xl`/`rounded-2xl`/`rounded-[2rem]`. Design will look inconsistent immediately.
21. **The CLI will overwrite `globals.css` and `tailwind.config.ts`** with `baseColor: "slate"` defaults, destroying the teal `--primary: 171 77% 27%` brand and the `.hero-glow` utility + `prefers-reduced-motion` block. Back these up before running `shadcn add`.
22. **Existing primitives will conflict.** `@healthos/ui` already ships `button`/`badge`/`card`/`input`/`label`/`table`/`textarea` with **narrower variant sets** (no `secondary`/`destructive`/`link` button variants, no `icon` size, no `destructive` badge, no `CardFooter`, no forwardRef on Table). Overwriting them with canonical shadcn versions is safe for consumers *except*: shadcn's `Table` wraps in `<div className="relative w-full overflow-auto">` (layout shift in `record-workspace.tsx`), and shadcn's `Label` pulls in `@radix-ui/react-label` (new dep in the ui package).
23. **Each new component needs a manual `exports` entry** in `packages/typescript/ui/package.json` — there is no barrel and no wildcard `"./*": "./src/*.tsx"`. The shadcn CLI won't do this.
24. **Radix deps must be added to `packages/typescript/ui`, not `apps/web`** (only `@radix-ui/react-slot` is present today). `next.config.ts` already has `transpilePackages: ["@healthos/api-types", "@healthos/ui", "@healthos/utils"]`, so that part is fine.
25. **`packages/typescript/ui/tsconfig.json` `include: ["src/**/*.tsx"]`** silently excludes `.ts` files — shadcn's `use-toast.ts`, `use-mobile.ts`, `chart` helpers would go untypechecked by `pnpm typecheck`.
26. **`"rsc": true` + no `"use client"` in current primitives.** shadcn's interactive components ship their own `"use client"`, so they're fine, but the existing ones being client/server-agnostic means mixing them is currently accidental, not designed.
27. **CSP is compatible** — `style-src 'self' 'unsafe-inline'` and `script-src 'self' 'unsafe-inline'` in `next.config.ts` allow Radix's inline styles/portals. No change needed.

### Recommended sequencing
`components.json` says `style: "new-york"`, `baseColor: "slate"`, `cssVariables: true` — but the actual theme is teal-primary with a slate-950 chrome and **17 of the ~30 shadcn tokens missing**. Do the v4 migration and the shadcn adoption as **one** change (v4 + `tw-animate-css` + `@theme inline` tokens + `@source` for the workspace package + `@utility container`), because doing shadcn on v3 first means writing the token set twice in two incompatible formats.


<!-- ===== raw scout: a72500bc765c3bf37 ===== -->

# HealthOS CONVENTION MAP

Monorepo root `/Users/manastole/Projects/Healthcare` — pnpm+turbo (`apps/*`, `packages/typescript/*`) + uv workspace (`services/{api,ai,gateway}`, `packages/python/healthos_platform`). Python `>=3.12,<3.14`, ruff `line-length=100` / `target-version=py312` / select `E,F,I,UP,B,SIM,ASYNC,S` (`S101` ignored, all `S` off in `**/tests/**`), mypy `strict=true` + pydantic plugin over `healthos_platform, healthos_api, healthos_ai, healthos_gateway`, pytest `asyncio_mode=auto`, `--strict-markers --strict-config --import-mode=importlib`.

---

## 1. SQLAlchemy model style (verbatim)

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/base.py` — entire file:

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/db/models.py:1-61` — import block + mixin + enums (extend this block in place; ruff-`I` sorted, no `TYPE_CHECKING`, no `__all__`):

```python
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from healthos_api.db.base import Base


class AccountType(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    HOSPITAL = "hospital"
    INSURANCE = "insurance"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class OtpPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    MOBILE_VERIFICATION = "mobile_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

Canonical mutable table — `PortalRecord` (`models.py:294-323`), the shape to copy for every new domain table:

```python
class PortalRecord(TimestampMixin, Base):
    """Tenant-scoped operational record with a stable envelope and typed payload."""

    __tablename__ = "portal_records"
    __table_args__ = (
        Index("ix_portal_records_scope", "tenant_id", "category", "created_at"),
        Index("ix_portal_records_patient", "patient_user_id", "category"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="active")
    external_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
```

Enum column form (only 4 uses: `User.account_type`, `User.status`, `OrganizationProfile.account_type`, `OtpChallenge.purpose`) — `native_enum=False` ⇒ VARCHAR+CHECK, **no PG enum types exist**:

```python
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        index=True,
        nullable=False,
    )
```

One-to-one profile satellite (PK **is** the FK, no surrogate id) — `PatientProfile` (`models.py:100-121`):

```python
class PatientProfile(TimestampMixin, Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (
        CheckConstraint("char_length(patient_id) = 15", name="patient_id_length"),
        CheckConstraint("patient_id ~ '^PAT[A-Z0-9]{12}$'", name="patient_id_format"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    patient_id: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    date_of_birth: Mapped[date | None] = mapped_column()
    sex_at_birth: Mapped[str | None] = mapped_column(String(32))
    blood_type: Mapped[str | None] = mapped_column(String(8))
    emergency_contact: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="patient_profile")
```

Parent side of a 1:1: `relationship(back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin")`.

**Hard rules**

- SQLAlchemy 2.0.51 (`sqlalchemy[asyncio]>=2.0,<3`), Alembic 1.18.5. 100% `DeclarativeBase` + `Mapped[...]` + `mapped_column`. Zero `Column(...)`, zero `declarative_base()`, no `__mapper_args__`, `TypeDecorator`, `@declared_attr`, `deferred`.
- `from __future__ import annotations` ⇒ relationship forward refs are **bare**, never quoted.
- Async only: `create_async_engine`/`AsyncSession`/`async_sessionmaker`.
- `nullable=False` always written explicitly even when `Mapped[str]` implies it; nullable = `Mapped[X | None]` with `nullable` omitted. Bare optional column = `mapped_column()` with empty parens.
- UUID PKs have **no explicit type**: `Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)`.
- Python-side `default=` in models; matching `server_default=` only in the migration. Models use `server_default` **only** on timestamp columns.
- `JSON` (generic) in models ⇔ `postgresql.JSONB()` in migrations. Follow that split.
- Money: `amount_cents: Mapped[int | None] = mapped_column(Integer)` + `currency: Mapped[str | None] = mapped_column(String(3))`. Hashes/digests: `String(64)`.
- Reserved word workaround: `metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)`.
- Append-only/log tables skip `TimestampMixin` and declare `created_at` inline as the **last** column (`OtpChallenge`, `AuthSession`, `AuditEvent`, `PortalNotification`, `JobWatchPosting`, `JobWatchAlertDelivery`, `IntegrationEvent`, `IdempotencyRecord`, `OutboxEvent`). `Role`/`Permission`/`UserRole`/`RolePermission` have no timestamps.
- `mapped_column` arg order: type/FK → `default=` → `index=True` → `nullable=`. FK style: `ForeignKey("<table>.<col>", ondelete="X")` positional first.
- `__table_args__` is always a tuple with trailing comma; order = UniqueConstraints, CheckConstraints, Indexes.
- Field widths: names 100, phone 32, license/registration 100, legal/address-ish 255, URLs 2048, status 32 (64 for `PortalRecord`/`WorkflowInstance`), category 64, event_type/purpose 100.
- **Everything except those 4 enum columns is a bare `String(N)`** — status/category/role/channel/severity/kind/source_type. Vocabularies enforced by `CheckConstraint("col IN ('a','b')", name=...)`, Pydantic `pattern=`/`Literal`, or Python allowlists — never a new DB enum.

**`ondelete` semantics (strict)**: `CASCADE` for owned children (profiles, `user_roles`, sessions, `owner_user_id`, memberships, consents, workflow tasks); `SET NULL` for nullable refs that must survive (`audit_events.actor_user_id`, `patient_user_id`, `assigned_user_id`, `application_definitions.supersedes_id`); `RESTRICT` for config/authorship (`system_settings.updated_by_user_id`, `application_definitions.created_by_user_id`, `workflow_instances.definition_id`); no `ondelete` on `auth_sessions.replaced_by_id` and `idempotency_records.actor_user_id`.

**Index/constraint naming**: single-column ⇒ `index=True`, auto-named `ix_<table>_<column>`. Composite ⇒ explicit hand-shortened name in `__table_args__`, pattern `ix_<short_domain>_<purpose>` with column order `tenant_id, <discriminator>, <time|status>` (`ix_portal_records_scope`, `ix_documents_scope`, `ix_consent_patient_status`, `ix_workflow_task_queue`, `ix_outbox_delivery`). `UniqueConstraint` usually **unnamed** (convention supplies `uq_<table>_<col0>`); `CheckConstraint` **always** named with the prefix omitted (`name="patient_id_length"`). FK names never hand-written.

**Tenancy**: there is **no `tenants` table**; every tenant-scoped table declares `tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)` with **no ForeignKey**, because `AuthContext.tenant_id` = primary active `OrganizationMembership.organization_id` **falling back to `user.id`** for solo/patient accounts. No RLS — filtering is application-level via `scoped_records(context)` (`portal/service.py:29-74`): admin ⇒ unfiltered, patient ⇒ `or_(owner_user_id==me, patient_user_id==me)`, else `tenant_id == context.tenant_id`. Global-then-tenant lookups: `or_(M.tenant_id.is_(None), M.tenant_id == ctx.tenant_id).order_by(M.tenant_id.desc().nullslast())`.

**Audit hash chain**: never set `AuditEvent.previous_hash`/`event_hash` in Python. Postgres trigger `seal_audit_event` → `healthos_seal_audit_event()` (sha256 chain under `pg_advisory_xact_lock('healthos-audit-chain')`) fills them; `reject_audit_mutation` blocks UPDATE/DELETE (migration `0004`).

Session factory (`db/session.py`): `create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)`, `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`.

---

## 2. Alembic migration skeleton + CURRENT HEAD

**Chain is strictly linear `0001→0002→…→0008`. CURRENT HEAD = `"0008"`** (`/Users/manastole/Projects/Healthcare/services/api/migrations/versions/0008_job_watch.py`). Next migration: file `0009_<slug>.py`, `revision = "0009"`, `down_revision = "0008"`. (Separate AI tree at `services/ai/alembic.ini`, head `"0003"` — `0003_action_proposals`.)

Skeleton (`/Users/manastole/Projects/Healthcare/services/api/migrations/versions/0009_<slug>.py`):

```python
"""Add clinical encounter tables.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
        sa.UniqueConstraint("tenant_id", "external_reference"),
        sa.CheckConstraint(
            "status IN ('scheduled','in_progress','completed','cancelled')",
            name="encounter_status",
        ),
    )
    op.create_index("ix_encounters_tenant_id", "encounters", ["tenant_id"])
    op.create_index("ix_encounters_scope", "encounters", ["tenant_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_encounters_scope", table_name="encounters")
    op.drop_index("ix_encounters_tenant_id", table_name="encounters")
    op.drop_table("encounters")
```

Rules: 4-digit zero-padded string revision matching the filename prefix; docstring has **no** `Create Date:` line (unlike `script.py.mako`); `timestamps()` is copy-pasted per file, never imported; migrations are **hand-written, never autogenerated**; constraints passed positionally inside `create_table`; UUID PKs have no server default (app supplies `uuid4`); index names always written literally (the declarative NAMING_CONVENTION is not used by `op.create_index`); `server_default` styles: timestamps `sa.func.now()`, bools `sa.true()/sa.false()`, ints/JSONB as string literals (`"0"`, `"{}"`, `"[]"`), strings bare (`"active"`). Widening a CHECK vocabulary = `op.drop_constraint` + `op.create_check_constraint`. Seeding = `op.bulk_insert(sa.table(...), [...])` or `op.get_bind().execute(sa.text("INSERT ..."), params)` with `CAST(:x AS jsonb)`. `downgrade()` is the exact inverse in reverse order. `migrations/env.py` overrides `sqlalchemy.url` from `get_settings().database_url.get_secret_value()`, uses `target_metadata = Base.metadata`, `compare_type=True`, `NullPool`, and imports `healthos_api.db.models  # noqa: F401` — so **every new model must be importable from `db/models.py`**.

---

## 3. FastAPI router + auth dependency skeleton

Auth layer (`/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/core/security.py`) — verbatim:

```python
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthContext:
    user: User
    session: AuthSession
    claims: AccessTokenClaims
    tenant_id: UUID


async def current_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    ...


def require_permissions(*required: str) -> Callable[..., Awaitable[AuthContext]]:
    async def dependency(
        context: Annotated[AuthContext, Depends(current_auth_context)],
    ) -> AuthContext:
        granted = set(permission_names(context.user))
        if not set(required).issubset(granted):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return context

    return dependency


def require_roles(*required: str) -> Callable[..., Awaitable[AuthContext]]:
    async def dependency(
        context: Annotated[AuthContext, Depends(current_auth_context)],
    ) -> AuthContext:
        granted = {role.name for role in context.user.roles}
        if not granted.intersection(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not authorized",
            )
        return context

    return dependency


async def enforce_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if request.headers.get("authorization") and settings.refresh_cookie_name not in request.cookies:
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
    header_token = request.headers.get("x-csrf-token", "")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
```

`require_permissions` = AND (subset); `require_roles` = OR (intersection). Token = bearer header **or** `settings.access_cookie_name` cookie; 401 if user missing / session missing / `status != ACTIVE` / `token_version != claims.ver` / revoked / expired. Tenant resolution:

```python
    primary_tenant = await db.scalar(
        select(OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .order_by(OrganizationMembership.is_primary.desc(), OrganizationMembership.created_at)
        .limit(1)
    )
    return AuthContext(user=user, session=session, claims=claims, tenant_id=primary_tenant or user.id)
```

DB dependency (`db/dependencies.py`) — **no auto-commit**:

```python
async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

Router skeleton (`api/routes/<domain>.py`):

```python
router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/resources/{category}", response_model=list[RecordResponse])
async def list_resources(
    category: str,
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
) -> list[RecordResponse]:
    try:
        records = await list_records(db, context, category, status_filter, limit)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return [record_response(item) for item in records]


@router.post(
    "/resources/{category}",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def create_resource(
    category: str,
    payload: RecordCreate,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    try:
        record = await create_record(db, context, category, payload)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return record_response(record)
```

Registration — `/Users/manastole/Projects/Healthcare/services/api/src/healthos_api/api/router.py` (complete file):

```python
from fastapi import APIRouter

from healthos_api.api.routes import auth, health, platform, portal, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(portal.router)
api_router.include_router(platform.router)
```

Mounted in `main.py:78` as `app.include_router(api_router, prefix="/api/v1")` ⇒ portal paths are `/api/v1/portal/...`. `api/__init__.py` and `api/routes/__init__.py` are docstring-only — no re-exports to update.

**Route rules**

- Handler param order: path params → body → `request: Request` → `context: Annotated[AuthContext, Depends(...)]` → `db` → `settings` → defaulted `Query`/`Form` params. Auth param is **always** named `context`, declared even when unused.
- Every mutating verb carries `dependencies=[Depends(enforce_csrf)]` (only exception: the HMAC-verified Stripe webhook `@router.post("/webhooks/payments", include_in_schema=False)`).
- POST-create ⇒ `status_code=status.HTTP_201_CREATED`; POST-action ⇒ default 200; DELETE ⇒ `HTTP_204_NO_CONTENT` + `-> None`. `status.*` constants, never bare ints. Note `HTTP_422_UNPROCESSABLE_CONTENT` and `HTTP_413_CONTENT_TOO_LARGE` spellings.
- `response_model=` only for Pydantic returns; `dict[str, Any]` returns rely on the annotation.
- Exception mapping: `PermissionError → 403`, `ValueError → 422`, `None → 404`, always `from exc`. Route modules raise `HTTPException(status.X, "Sentence")` positionally; `core/security.py` uses kwargs. Service layer raises **built-ins only** (no custom domain exceptions in portal).
- Global RFC 7807: `install_error_handlers(app)` from `healthos_platform.errors` — `application/problem+json` with `type/title/status/detail/instance/error_id/request_id/trace_id`; 422 adds `errors[]`.
- **No pagination and no envelope.** Bare JSON arrays with hard caps: service re-clamps `.limit(min(limit, 200))`; inline `.limit(200)` docs/notifications, `.limit(100)` availability, `.limit(500)` admin, `.limit(6)` dashboard recent. Sorting is fixed per endpoint (`created_at.desc()` default), never client-controlled. Row locking for booking/state transitions: `.with_for_update()`.
- Query idioms: `(await db.scalars(q)).all()`, `await db.scalar(q)`, `await db.get(Model, pk)`, `int(await db.scalar(select(func.count()).select_from(M)) or 0)`.

**Write-transaction template** (audit in the *same* commit):

```python
db.add(entity)
db.add(
    AuditEvent(
        actor_user_id=context.user.id,
        event_type="portal.appointment.booked",
        subject_user_id=context.user.id,
        event_data={"slot_id": str(slot.id), "appointment_id": str(appointment.id)},
    )
)
await db.commit()
await db.refresh(entity)
return entity_response(entity)
```

`event_type` is dotted-lowercase (`portal.<category>.<verb>`, `document.downloaded`, `admin.user_status_changed`, `consent.granted`, `configuration.published`, `workflow.transitioned`); `event_data` must be JSON-safe (`str(uuid)`). Auth flows instead use `record_audit_event(db, event_type=..., client=client_context(request), ...)` which also captures IP/UA. Outbound integrations write one `IntegrationEvent` in the same commit with `request_digest=request_digest(payload.model_dump())` (`hashlib.sha256(repr(value).encode()).hexdigest()`). `OutboxEvent` has exactly one producer (`platform.py:476`) and **no dispatcher**. `IdempotencyRecord` has **zero call sites** — only header pass-through in `POST /portal/payments/intents`.

**Permission catalog** (seeded, integer ids): `profile:read`(1), `profile:write`(2), `sessions:read`(3), `sessions:revoke`(4), `users:manage`(5), `rbac:manage`(6), `portal:read`(7), `portal:write`(8), `documents:manage`(9), `integrations:execute`(10), `system:admin`(11). Role ids 1-5 = patient/doctor/hospital/insurance/admin. 7/8/9 → all roles; 10 → roles 2-5; 11 → role 5. New permissions get a new migration following `0003_portal_domain.py:196-219`.

**Module authorization vocabulary** — `portal/access.py`: `PORTAL_MODULES: dict[AccountType, tuple[str, ...]]` + `authorize_module(account_type, category)` raising `PermissionError`. Allowed categories:
- patient: `medical_history, vitals, allergies, vaccinations, visits, medications, appointments, telemedicine, lab_reports, lab_bookings, insurance, buy_insurance, loyalty_points, claims, cost_estimates, payments, notifications, health_reminders, consents, documents, ai_assistant`
- doctor: `schedule, patients, prescriptions, documentation, medical_coding, referrals, care_coordination, telemedicine, lab_reports, appointments, ai_assistant, documents`
- hospital: `staff, departments, beds, resources, service_catalog, lab_slots, billing, revenue_cycle, eligibility, reports, appointments, documents`
- insurance: `policies, eligibility, claims, prior_authorization, cost_estimates, fraud_detection, documents`
- admin: `analytics, audit_logs, user_management, monitoring, system_settings, escalations, support, documents`

**Service vs route split**: `healthos_api/<domain>/{__init__.py, access.py, schemas.py, service.py}`. Service functions are `async def f(db: AsyncSession, context: AuthContext, ...)` positionally, own `authorize_module`, tenant scoping, consent checks, derived fields, and may own the commit. Routes own HTTP status/`HTTPException`/multipart/`Response`/`request.app.state.{http,redis}`/client instantiation. `platform.py` has no service module at all (module-private `_helpers`) — both patterns are native.

**New-router checklist**: create domain package → `api/routes/<domain>.py` with one module-level `router` → add to the `from healthos_api.api.routes import ...` line + one `include_router` in `api/router.py` → gate every endpoint with `require_permissions` + `enforce_csrf` on mutations → seed new permissions in `0009+` → scope reads by `context.tenant_id` with `account_type.value != "admin"` bypass → keep explicit `status_code=` (asserted by `services/api/tests/test_openapi_contract.py`).

---

## 4. Pydantic schema style

Schemas live in `healthos_api/<domain>/schemas.py`, never in the route module. **No `ConfigDict`/`model_config` anywhere in the API service**; no `from_attributes` on classes (one ad-hoc `Model.model_validate(item, from_attributes=True)` in `platform.py:58`). Naming `<Noun>Create` / `<Noun>Update` / `<Noun>Response`. Response models declare all fields **without defaults** so a missing mapper field is a hard error. PEP 604 unions only, never `Optional[...]`.

```python
class RecordCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", min_length=1, max_length=64)
    patient_user_id: UUID | None = None
    assigned_user_id: UUID | None = None
    external_reference: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def bound_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 50_000:
            raise ValueError("Structured payload is too large")
        return value


class ConsentCreate(BaseModel):
    @model_validator(mode="after")
    def exactly_one_grantee(self) -> "ConsentCreate":
        if (self.grantee_user_id is None) == (self.grantee_organization_id is None):
            raise ValueError("Provide exactly one user or organization grantee")
        return self
```

Enum-ish strings use `pattern=` or `Literal`, never Python `Enum`:

```python
channel: str = Field(default="in_app", pattern="^(in_app|email|webhook)$")
severity: str = Field(default="info", pattern="^(info|success|warning|critical)$")
status: str = Field(pattern="^(active|suspended|disabled)$")
amount_cents: int = Field(gt=49, le=100_000_000)
loyalty_points: int = Field(default=0, ge=0, le=10_000_000)

DefinitionKind = Literal["module", "form", "dashboard", "workflow", "content"]
DefinitionStatus = Literal["draft", "review", "published", "retired"]
key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
locale: str = Field(default="en-US", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")

# auth/schemas.py reusable aliases
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=7, max_length=32, pattern=r"^\+?[0-9() .-]+$")]
```

Aliases only dodge name clashes (`schema_ = Field(..., alias="schema")` on requests, `serialization_alias="schema"` on responses; SQLAlchemy `metadata_` → response field `metadata`). No camelCase, no alias generator, no `populate_by_name`. ORM→schema conversion is hand-written module-level mappers: `def record_response(record: PortalRecord) -> RecordResponse` with explicit kwargs.

---

## 5. Settings

`Settings(BaseServiceSettings)` in `services/api/src/healthos_api/config.py`; base in `packages/python/healthos_platform/.../config.py` with `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)` and **no `env_prefix`** ⇒ env var = UPPER_SNAKE of the field name. Credentials are `SecretStr` (`.get_secret_value()`); `DATABASE_URL` is one whole DSN (`postgresql+asyncpg://…`), never assembled from parts. Accessor `@lru_cache def get_settings()` (`get_settings.cache_clear()` in tests). Adding a setting = typed defaulted field + entry in `.env.example` + optional check inside `@model_validator(mode="after") reject_placeholder_production_secret`. List-valued env vars are JSON-encoded.

Platform middleware (mounted in `main.py`, outermost-last): `SessionMiddleware`, `CORSMiddleware(allow_credentials=True)`, `TrustedHostMiddleware`, `SecurityHeadersMiddleware`, `DistributedRateLimitMiddleware(default_limit=600)`, `RequestBodyLimitMiddleware`, `PrometheusMiddleware`, `RequestContextMiddleware`. `app.state`: `db_engine`, `session_factory`, `redis`, `http` (`httpx.AsyncClient(timeout=Timeout(60))`). Structlog auto-redacts any log key matching `(authorization|cookie|token|secret|password|otp|email|phone|patient|prompt|content|body|key)` — name log fields accordingly.

---

## 6. Web fetch wrapper (verbatim)

`/Users/manastole/Projects/Healthcare/apps/web/lib/auth.ts`:

```ts
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

let refreshInFlight: Promise<unknown> | null = null;

function getApiUrl(path: string): string { return `${env.NEXT_PUBLIC_API_URL}${path}`; }

function refreshSession(): Promise<unknown> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        return await apiFetch("/api/v1/auth/refresh", { method: "POST" });
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
        await new Promise((resolve) => setTimeout(resolve, 300));
        return apiFetch("/api/v1/auth/refresh", { method: "POST" });
      }
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const csrf = getCookie("healthos_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(getApiUrl(path), { ...init, headers, credentials: "include" });
  } catch {
    throw new Error(
      `Unable to reach the HealthOS API at ${getApiOriginLabel()}. Verify the gateway is running and NEXT_PUBLIC_API_URL is correct.`,
    );
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string" ? detail
      : Array.isArray(detail)
        ? detail.map((item) =>
            typeof item === "object" && item && "msg" in item ? String(item.msg) : "Invalid input",
          ).join(". ")
        : "Request failed";
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function authenticatedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    await refreshSession();
    return apiFetch<T>(path, init);
  }
}
```

Base URL from `lib/env.ts` (`z.union([z.literal(""), z.string().url()]).default("")`, `NEXT_PUBLIC_API_URL=http://localhost:8080` → the gateway). Cookie auth only (`credentials: "include"`, **no `Authorization` header anywhere**); double-submit CSRF on non-GET/HEAD; single-flight refresh on 401 with a 409 retry. No SWR/React Query, no Server Actions, no `next/headers`/`cookies()`/`"use server"` anywhere — server components are thin shells and every data fetch is a client `useEffect`. Cookies: `healthos_access` (HttpOnly, `/`, 15 min), `healthos_refresh` (HttpOnly, path `/api/v1/auth`, 30 d), `healthos_csrf` (**not** HttpOnly, `/`). `middleware.ts` only checks cookie *presence* for `/dashboard|/profile|/portal`. Error UI is per-component `useState<string|null>` + `<p className="mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">`; loading is ad-hoc `animate-pulse`. One raw `fetch` bypasses the wrapper for blob download at `components/portal/documents-workspace.tsx:67`. AI calls go to `/ai/v1/runs` on the same base URL.

Portal routing: `app/(protected)/portal/[module]/page.tsx` → `<ModuleWorkspace slug={module}/>` which looks the slug up in the server manifest and dispatches to `DocumentsWorkspace | NotificationsWorkspace | AIAssistant | PatientBookingWorkspace(kind="labs"|"appointments") | PatientInsuranceWorkspace(marketplace?) | AdminWorkspace | RecordWorkspace` (generic CRUD driven by manifest JSON-Schema `formDefinition.schema.properties`, falling back to `workflowFields[slug]` in `lib/portal.ts`). Sidebar nav comes from the **server manifest** (`manifestModules(manifest)`), not `roleModules`. Contracts in `packages/typescript/api-types/src/index.ts` are hand-written (no codegen from `docs/api/openapi-core.json`); `PolicyOffer`, `Slot`, `AIRun`, `AdminRow` are locally re-declared and will drift.

---

## 7. Tailwind / CSS token setup (verbatim)

Tailwind **v3.4.19** (classic: `postcss.config.mjs` = `{ plugins: { tailwindcss: {}, autoprefixer: {} } }`).

`/Users/manastole/Projects/Healthcare/apps/web/tailwind.config.ts` (complete):

```ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/typescript/ui/src/**/*.{ts,tsx}",
  ],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary:   { DEFAULT: "hsl(var(--primary))",   foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted:     { DEFAULT: "hsl(var(--muted))",     foreground: "hsl(var(--muted-foreground))" },
        accent:    { DEFAULT: "hsl(var(--accent))",    foreground: "hsl(var(--accent-foreground))" },
        card:      { DEFAULT: "hsl(var(--card))",      foreground: "hsl(var(--card-foreground))" },
      },
    },
  },
  plugins: [animate],
};
export default config;
```

`/Users/manastole/Projects/Healthcare/apps/web/app/globals.css` (58 lines, complete):

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 168 30% 98%;
    --foreground: 222 47% 11%;
    --card: 0 0% 100%;
    --card-foreground: 222 47% 11%;
    --primary: 171 77% 27%;
    --primary-foreground: 166 76% 97%;
    --secondary: 210 40% 96%;
    --secondary-foreground: 222 47% 11%;
    --muted: 210 40% 96%;
    --muted-foreground: 215 16% 47%;
    --accent: 166 76% 94%;
    --accent-foreground: 173 80% 20%;
    --border: 214 32% 91%;
    --input: 214 32% 91%;
    --ring: 173 80% 29%;
    --radius: 0.9rem;
  }

  * { @apply border-border; }
  body {
    @apply bg-background text-foreground antialiased;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  ::selection { @apply bg-primary/20 text-foreground; }
  button, a, input, select, textarea {
    @apply focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2;
  }
}

@layer utilities {
  .hero-glow {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(circle at 12% 18%, hsl(168 76% 91% / 0.75), transparent 32%),
      radial-gradient(circle at 88% 42%, hsl(201 92% 92% / 0.62), transparent 30%);
    pointer-events: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

Token facts: 17 bare-HSL-triplet tokens; brand = teal `--primary: 171 77% 27%` (`themeColor: "#10b981"`). `--radius` is **dead** (no `borderRadius` mapping). `darkMode: ["class"]` is **dead** (no `.dark {}` block, zero `dark:` usages). Missing shadcn tokens: `--popover*`, `--destructive*`, `--chart-1..5`, `--sidebar-*`. Most portal UI **bypasses tokens** and hardcodes `bg-slate-950`, `bg-emerald-500`, `text-slate-*`, `bg-red-50 text-red-700`, etc.

UI package `@healthos/ui` — **no barrel**, subpath exports only (`./badge ./button ./card ./input ./label ./table ./textarea`); each new component needs a manual `exports` entry. `cn` lives in `@healthos/utils` (`twMerge(clsx(inputs))`); `tailwind-merge` resolves to **3.6.0 against Tailwind 3.4.19** — a latent mismatch. cva is used in `button.tsx` and `badge.tsx` only:

```ts
const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  { variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
      size: { default: "h-10 px-4 py-2", sm: "h-9 rounded-md px-3", lg: "h-11 rounded-md px-8" },
    },
    defaultVariants: { variant: "default", size: "default" } },
);
```

No `secondary`/`destructive`/`link` button variants, no `icon` size, no destructive Badge, no `CardFooter`, Table has no forwardRef/wrapper. Missing primitives hand-rolled today: Select, Dialog/Sheet, Skeleton, Alert, Toast, Tabs, Avatar, DropdownMenu, Separator, Tooltip, Form. If migrating: do Tailwind v4 + shadcn as **one** change — v4 requires `@import "tailwindcss"`, `@tailwindcss/postcss`, `@config`, `@source "../../../packages/typescript/ui/src"` (else all `@healthos/ui` classes are purged), `@utility container` (v4 dropped `theme.container`), `tw-animate-css` instead of `tailwindcss-animate`, and `@custom-variant dark`. `components.json` aliases `@healthos/ui`/`@healthos/utils` are not tsconfig `paths` and will break the shadcn CLI; `@/hooks` doesn't exist.

---

## 8. AI team registration pattern (verbatim)

`/Users/manastole/Projects/Healthcare/services/ai/src/healthos_ai/teams/definitions.py` is the single source of truth:

```python
class TeamName(StrEnum):
    ...
    PAYER_OPERATIONS = "payer_operations"          # 1. enum member; value <= 64 chars (DB String(64))

TEAM_DEFINITIONS = {
    ...
    TeamName.PAYER_OPERATIONS: TeamDefinition(     # 2. dict entry, APPEND at the end
        TeamName.PAYER_OPERATIONS,
        "Payer-side claim adjudication support",
        frozenset({"insurance", "admin"}),         # 3. RBAC allowed account_types
        "payer_operations_model",                  # 4. MUST be an attribute name on Settings
        (
            _specialist("claim_adjudication", "Prepare adjudication evidence for human review"),
            _specialist("appeals", "Draft appeal packets for reviewer attestation"),
        ),
    ),
}
```

Then: add `payer_operations_model: str = "healthos-openai"` to `services/ai/src/healthos_ai/config.py` (`TeamAgentFactory.create` does `getattr(settings, definition.model_setting)` — a missing attr is an `AttributeError` at first run); add a `RoutingCase` in `evaluation/cases.py`; run `make openapi` (`TeamName` is in the public schemas → `docs/api/openapi-ai.json`); update `docs/architecture/ai-operating-system.md`. **Ordering matters** — `allowed_teams()` preserves insertion order and index 0 is the default team (`queue/runs.py:88`, `orchestration/graph.py:90`). Tests enforce: ≥2 specialists per team, non-empty `allowed_account_types`/instructions, every routing case's team RBAC-allowed, and `set(allowed_teams("admin")) == set(TeamName)` (**every new team must include `admin`**).

Graph construction (`teams/factory.py`, cached per `(TeamName, provider)`):

```python
graph = create_deep_agent(
    name=f"{team_name.value}_team",
    model=model,                       # ChatOpenAI via LiteLLM
    tools=self._tools,                 # global tool list (local + MCP)
    subagents=cast(Any, subagents),    # [{"name","description","system_prompt","tools","model"}]
    context_schema=RuntimeContext,
    system_prompt=f"{SAFETY_PROMPT}\nYou lead the {team_name.value} team. Mission: ...",
)
```

Tool pattern (`tools/catalog.py`, closure factory `build_tools(knowledge, memories, messages, audit)`):

```python
@tool
async def search_knowledge(query: str, runtime: ToolRuntime[RuntimeContext]) -> str:
    """Docstring is the tool description shown to the model."""
    async def operation() -> str: ...
    return str(await audited("search_knowledge", runtime, operation))
```

Return `str`; return a denial *string* for policy refusals (check `runtime.context.{team,account_type,memory_mode,allowed_teams}`); always wrap in `audited(...)` (metadata-only audit rows, never PHI/args); append to the returned list. **No per-team tool allowlist exists** — `TeamAgentFactory` flattens `[*tools, *mcp_tools]` to every lead and specialist. Tools are built once in `bootstrap.py`, so any HTTP client must be created there and injected.

Existing teams / RBAC: `patient, insurance, clinical, administrative, infrastructure, document_intelligence`. `patient`→(patient,insurance,document_intelligence); `doctor`→(patient,clinical,administrative,document_intelligence); `hospital`→(patient,insurance,clinical,administrative,document_intelligence); `insurance`→(insurance,administrative,document_intelligence); `admin`→all.

`POST /ai/v1/runs` (`api/routes.py:88`, prefix `/ai/v1`): `RunRequest{prompt(1..30_000), team?, execution_mode=sync|async, provider=auto|openai|anthropic|gemini, memory_mode=none|read|read_write, thread_id?}` → **201** always; 403 on disallowed team; 502 on graph failure in sync mode; async `XADD`s to Redis stream `healthos:ai:runs`. Writes are human-in-the-loop `ActionProposal` only — the allowed action regex (`api/schemas.py:96`) is `hold_slot|book|reschedule|verify_eligibility|estimate_cost|submit_claim|submit_prior_authorization|purchase_policy|draft_clinical_document|draft_medical_codes`, plus `HIGH_RISK_ACTIONS` in `api/routes.py:34` — new domain actions must be added to **both**. AI→core auth is bare relay of the end-user token to `/api/v1/auth/session`; `RuntimeContext` carries **no credential**, so tools cannot call core today.

---

## 9. Ops quick reference

`make bootstrap | demo | up | down | migrate | seed-demo | lint | typecheck | test | openapi | verify`. Containers self-migrate (`alembic upgrade head && uvicorn ...`). Two Alembic histories share one database. Host-side: `export DATABASE_URL='postgresql+asyncpg://healthos:change-me@localhost:55432/healthos'; uv run alembic -c services/api/alembic.ini upgrade head`. Ports: web 3000, gateway 8080, api 8000, ai 8001, litellm 4000, postgres 127.0.0.1:55432, redis 127.0.0.1:56379. Seed: `healthos-seed-demo` (idempotent, 5 users + 60 portal records + AI tables), password `Demo@HealthOS2026!`, patient id `PATDEMO00000001`. Dependencies: `uv add --package healthos-api <pkg>` then `uv sync --all-packages --dev` (CI is `--frozen`; images run `--no-dev`). Known infra gotchas: compose `environment:` replaces the YAML anchor map, so `OTEL_EXPORTER_OTLP_ENDPOINT` is absent from every service; `.env.example` `AI_SERVICE_URL=http://ai:8001` is wrong in-network (should be `:8000`); no source bind mounts ⇒ no hot reload.

---

# GAP LIST — PDF requirements not modeled in the database

**Headline finding:** the schema has **29 tables and zero clinical/financial domain tables**. Every requirement below is currently satisfied (where satisfied at all) by rows in the single generic `portal_records` table — `category: String(64)` + untyped `data: JSON` (guarded only by a Pydantic `len(str(value)) > 50_000` check) — plus `document_assets` for files. Consequences that apply to *every* gap: no foreign-key integrity between domain objects (an appointment references its slot via `data["slot_id"]` string), no typed columns or CHECK constraints on clinical values, no uniqueness guarantees (double-booking is prevented only by a `SELECT … FOR UPDATE` on a `portal_records` row, and there is no unique index to back it), no queryable history/state machine, no reporting-grade aggregation (trends require JSON extraction), no per-domain retention or field-level encryption, and no linkage table between `document_assets` and the records they evidence.

Legend: **P** = partially present as `portal_records.category` + JSON only; **✗** = nothing at all.

### Patient — lifelong health record

| Requirement | Today | Missing from the DB |
|---|---|---|
| Vitals | **P** `category="vitals"` JSON | `vital_signs` (patient_user_id, encounter_id, taken_at, LOINC code, `value_numeric`, unit, method, device, recorded_by) — needed for trend queries/charts |
| Growth tracking + percentiles | **✗** | `growth_measurements` (height/weight/head_circumference by age) and a `growth_reference_standards` table (WHO/CDC L-M-S percentile curves). No reference data exists anywhere |
| BMI | **P** computed in Python at `portal/service.py:125-130` and written back into `data["bmi"]` | derived column/table; no recomputation on update, no history, no BMI-for-age percentile |
| Allergies | **P** `category="allergies"` JSON | `allergy_intolerances` (substance code RxNorm/SNOMED, category, criticality, reaction/manifestation, onset, verification_status, recorded_by) |
| Immunizations + certificates | **P** `category="vaccinations"` JSON | `immunizations` (vaccine code CVX, dose_number, series, lot, site, administered_by, next_due_at) and `immunization_certificates` (issuer, certificate number, QR/verification hash, revocation). No certificate issuance or verification model at all |
| Visit timeline | **P** `category="visits"` JSON | `encounters` (class, start/end, location, provider, department, reason, disposition) — the timeline has no spine; nothing else can FK to a visit |
| Medications | **P** `category="medications"` JSON | `medication_statements` / `prescriptions` (RxNorm, dose, route, frequency, start/end, prescriber, refills, status) |
| Medication reminders | **P** `_add_medication_reminders()` writes `category="health_reminders"` records with `data["reminder_type"]="medication"`, `data["time"]` | `medication_schedules` (recurrence rule, timezone) + `reminder_deliveries`/`adherence_events` (taken/skipped/snoozed). No scheduler table, no delivery state, no user timezone column on `users` |
| Problem list / diagnoses / care team / family history | **✗** | `conditions`, `encounter_diagnoses`, `care_team_members`, `family_history` — none exist |
| Patient demographics beyond the basics | **P** `patient_profiles` | no `addresses`, `next_of_kin`, `insurance_cards`, MRN cross-reference (`patient_identifiers`), language/communication preferences |

### Patient — appointments & payments

| Requirement | Today | Missing |
|---|---|---|
| Real-time provider availability | **P** `portal_records.category="schedule"` scanned at `portal.py:565,610`, specialty filtered **in Python** over JSON | `provider_schedules` + `appointment_slots` (provider_user_id, organization_id, start_at, end_at, capacity, status) with `UniqueConstraint(provider, start_at)` and a partial index for open slots |
| Booking | **P** creates `category="appointments"` record + `with_for_update()` on the slot record | `appointments` (slot_id FK, patient_user_id, provider_user_id, encounter_id, reason, channel in-person/tele, status history, cancellation reason, no-show). No FK from appointment→slot, no state-transition table |
| Consultation payment | **P** Stripe intent via `PaymentGateway`; one `IntegrationEvent` + a `portal_records` row `category="payments"` (patient) / `"billing"` (others) | `payments` / `payment_intents` / `invoices` / `refunds` ledger with FK to the appointment, provider payout, reconciliation status. No money is modeled relationally; `amount_cents`/`currency` on `portal_records` is the only monetary field in the schema |
| Idempotent booking/payment | **✗ (schema exists, unused)** | `idempotency_records` has **zero call sites**; payment endpoint only passes an `Idempotency-Key` header through to Stripe |

### Patient — lab test booking

| Requirement | Today | Missing |
|---|---|---|
| Test catalog + availability | **P** `category="lab_slots"` records, `test_code` filtered in Python (`portal.py:657,672`) | `lab_tests` catalog (LOINC, specimen type, prep instructions, TAT, price), `lab_slots` (facility, start_at, capacity, offered test_ids), and a join table for slot×test availability |
| Booking | **P** `category="lab_bookings"` record | `lab_orders` (ordering provider, patient, tests, priority, status), `specimens`, `lab_results` (LOINC, value, unit, reference range, abnormal flag, verified_by). **Results are not modeled at all** — `lab_reports` is only a document category |

### Patient — insurance claims tab

| Requirement | Today | Missing |
|---|---|---|
| Plain-language coverage explanation | **✗** | `insurance_policies` / `coverages` (member id, group, effective dates, plan_id), `plan_benefits` (service category, copay, coinsurance, deductible, out-of-pocket max, limits, exclusions) and a `benefit_explanations` / plain-language content table. There is **no source of truth for coverage**, so the explanation can only be LLM-generated with no grounding rows |
| Initiate a claim | **✗** | `claims` (claim number, payer, subscriber, provider, encounter, service dates, total/allowed/paid, status), `claim_lines` (CPT/HCPCS, modifiers, units, charge, diagnosis pointers), `claim_status_history`, `claim_attachments`, `remittance_advice`/`EOB`, `denials`/`appeals`. `category="claims"` is a portal module string only |

### Patient — buy insurance marketplace

| Requirement | Today | Missing |
|---|---|---|
| Product catalog | **P** `category="policies"` records ordered by `amount_cents` (`portal.py:746,823`) | `insurance_products` / `plans` (payer org, product type, network, premium, deductible, term, eligibility rules, filing/approval id) |
| Ranking by medical history | **✗** | no risk/eligibility feature store, no `plan_recommendations` (score, reason codes, model version), and no structured medical history to rank on (it's all JSON) |
| Loyalty points | **P** `category="loyalty_points"` records (`portal.py:773`) | `loyalty_accounts` + `loyalty_ledger` (accrual/redemption/expiry, balance invariant). A balance derived from generic records cannot be transactionally enforced |
| Purchase | **P** `category="insurance"` record + audit `portal.policy.purchase_initiated` | `policy_applications` (underwriting status), `policy_enrollments`, `premium_schedules`, `beneficiaries` |

### Doctor

| Requirement | Today | Missing |
|---|---|---|
| Clinical documentation | **P** `category="documentation"` JSON | `clinical_notes` (encounter FK, note type SOAP/H&P/discharge, author, cosigner, version, signed_at, amendment chain, addenda). No signing/attestation/versioning model — a hard regulatory gap |
| Medical coding | **P** `category="medical_coding"` JSON | `code_systems` + `code_concepts` (ICD-10-CM, CPT, HCPCS, SNOMED, LOINC, RxNorm) and `encounter_codes` (code, rank, modifiers, coder, confidence, human-review status). **No terminology tables exist**, so nothing can be validated or billed from |
| Referrals | **P** `category="referrals"` JSON | `referrals` (referring/receiving provider+org, specialty, urgency, reason, status, expiry, linked prior-auth, feedback note) |
| Telemedicine | **P** `category="telemedicine"` JSON | `telehealth_sessions` (appointment FK, provider room id, join tokens, start/end, participants, recording consent + artifact ref, connection quality, cross-state licensure check) |
| Prescribing | **P** `category="prescriptions"` JSON | `prescriptions` + `prescription_fills`, drug-interaction/allergy check results, e-prescribe transmission log |
| Care coordination / patient panel | **P** `category="care_coordination"`, `"patients"` | `care_plans`, `care_team_members`, `provider_patient_panel` |

### Hospital

| Requirement | Today | Missing |
|---|---|---|
| Provider directory | **P** `doctor_profiles` + `organization_memberships.role: String(64)` | `practitioners`/`practitioner_roles` (org FK, department, privileges, credentialing status+expiry, licenses per jurisdiction, NPI, taxonomy). `doctor_profiles` has a single `affiliation: String(255)` free-text field and no org FK |
| Departments | **P** `category="departments"` | `departments` (org FK, code, cost center, parent) |
| Beds / resources | **P** `category="beds"`, `"resources"` | `locations`, `beds` (unit, room, class, status, occupancy), `equipment`/`resources` (type, maintenance, availability), `resource_reservations`, `staff_shifts`/rosters |
| Service catalog | **P** `category="service_catalog"` | `service_items` / chargemaster (code, description, department, base price, CPT mapping, effective dates), `price_lists`, `payer_contract_rates` |
| Billing | **P** `category="billing"` | `invoices`, `invoice_lines`, `charges`, `payments`, `adjustments`, `write_offs`, `patient_statements` |
| Revenue cycle | **P** `category="revenue_cycle"` | `claim_submissions`/`835-837` batches, `ar_aging` snapshots, `denials` + reason codes, `collections`, `remittances`. No ledger primitives at all |

### Insurer

| Requirement | Today | Missing |
|---|---|---|
| Eligibility | **P** `category="eligibility"`; live check goes to `InsuranceClient` and leaves only an `IntegrationEvent` | `eligibility_requests` / `eligibility_responses` (270/271 payload, member, coverage found, active dates, benefits returned, cached-until). Responses are **not persisted** as domain rows |
| Claims processing | **✗** | payer-side `claims`, `adjudication_results`, `edits/rules`, `pended_reasons`, `payment_runs` (see patient-claims row — one shared claims model is missing on both sides) |
| Prior authorization | **P** `category="prior_authorization"` | `prior_authorizations` (member, service codes, requesting provider, clinical criteria met, reviewer, decision, decision reason, valid from/to, appeal). The AI action `submit_prior_authorization` has no table to write to |
| Policy management | **✗** | `insurance_products`, `policies`, `members`/`enrollments`, `riders`, `endorsements`, `premium_invoices`, `policy_documents` |
| Cost estimation | **P** `category="cost_estimates"` | `cost_estimates` (service bundle, contracted rate, member liability breakdown, deductible remaining, confidence, expiry) + the contract-rate and accumulator tables it depends on (`benefit_accumulators` — deductible/OOP consumed to date — do not exist) |
| Fraud detection | **P** `category="fraud_detection"` | `fraud_signals`/`risk_scores` (subject, rule/model, score, features, disposition, reviewer) |
| Document intelligence | **P** `document_assets.ocr_text` + AI-service tables (`ai_knowledge_documents/_chunks`, `ai_agent_runs`) | `document_extractions` (document FK, extraction schema/version, structured fields, per-field confidence, validation status, human corrections) and any FK linking a `document_asset` to the claim/policy/lab record it evidences. Extraction results live in a different service's tables with no relational link back |

### Admin

| Requirement | Today | Missing |
|---|---|---|
| Audit | **✓ strongest area** — `audit_events` with sha256 hash chain (BEFORE-INSERT trigger) and append-only enforcement | no `audit_events.tenant_id` (cross-tenant queries/retention are impossible), no PHI **access** log (reads are not audited — only writes), no break-glass/emergency-access records, no audit export/attestation table |
| Oversight / monitoring | **P** `category="analytics"`, `"monitoring"`; live values computed ad hoc | `system_health_snapshots`, `sla_metrics`, `usage_counters` — nothing is persisted for trending |
| Escalation / support | **P** `category="escalations"`, `"support"` | `support_cases`/`tickets` (subject, severity, SLA due, assignee, queue, state machine), `case_comments`, `escalation_paths`, `on_call_rosters`. `workflow_instances`/`workflow_tasks` exist and are the closest generic substrate but have no case semantics |
| User management | **P** `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, admin status-change endpoint | no `role_assignments` scoped per organization (roles are global to a user), no delegation/impersonation record, no access-review/recertification table |
| Compliance | **P** `consent_grants` (purpose, scopes JSON, expiry, revocation) | no `data_subject_requests` (access/erasure), no `retention_policies`, no `disclosure_accounting` (HIPAA §164.528 requires it and there is no read-access log to build it from) |

### Cross-cutting structural gaps

1. **No `tenants`/`organizations` FK on `tenant_id`.** `tenant_id` is an unconstrained UUID that is *either* an `organizations.id` *or* a `users.id` (fallback in `current_auth_context`). Any real multi-tenant hospital/insurer feature needs a real tenant entity and a decision about the solo-user fallback; today referential integrity, cascade deletes, and per-tenant retention are all impossible.
2. **No row-level security.** Isolation is one `scoped_records()` helper; every new domain table must re-implement it correctly or leak across tenants.
3. **`outbox_events` has one producer and no dispatcher/relay** — eventing is not actually delivered.
4. **`idempotency_records` is dead schema** — no write endpoint is idempotent, including booking and payment.
5. **Document bytes live in Postgres** (`document_assets.content: LargeBinary`, 10 MB cap) — no object storage, no per-document encryption key, no virus scan status, no versioning, and no `document_links` table tying a document to a claim/lab/immunization record.
6. **No FHIR resource store.** `document_assets.fhir_resource_type/_id` are two loose strings; there is no interoperability mapping table, no `integration_identifiers` cross-reference for external EHR/payer ids beyond `external_reference: String(255)` on `portal_records`.
7. **No terminology/reference data of any kind** (ICD/CPT/LOINC/RxNorm/CVX/NPI, growth standards, payer directories) — every "coding", "coverage", or "percentile" requirement is ungrounded.
8. **No notification preferences or scheduled-delivery table** — `portal_notifications` is fire-and-forget with `channel`/`severity` strings; reminders cannot be scheduled, retried, or opted out of.
9. **No PHI field-level encryption in the core API** (the AI service has `DataCipher`; core stores everything in plaintext columns and JSON).
10. **Migration/permission debt for all of the above**: each new domain needs a `0009+` migration, new permission rows seeded with explicit integer ids, new `PORTAL_MODULES` categories, and `ApplicationDefinition` manifest rows (module/form JSON Schema) for the web `RecordWorkspace` to render — the manifest, not the code, drives the sidebar.