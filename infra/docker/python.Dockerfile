FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

ARG SERVICE_PACKAGE
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
COPY packages/python/healthos_platform/pyproject.toml packages/python/healthos_platform/pyproject.toml
COPY packages/python/healthos_platform/src packages/python/healthos_platform/src
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/api/src services/api/src
COPY services/ai/pyproject.toml services/ai/pyproject.toml
COPY services/ai/src services/ai/src
COPY services/gateway/pyproject.toml services/gateway/pyproject.toml
COPY services/gateway/src services/gateway/src

RUN uv sync --frozen --no-dev --no-editable --package "${SERVICE_PACKAGE}"

FROM python:3.12-slim-bookworm AS runtime

ARG SERVICE_PATH
ARG APP_MODULE

RUN groupadd --system --gid 10001 healthos \
    && useradd --system --uid 10001 --gid healthos --home-dir /app healthos

WORKDIR /app
COPY --from=builder --chown=healthos:healthos /app/.venv /app/.venv
COPY --chown=healthos:healthos services/${SERVICE_PATH} /app/services/${SERVICE_PATH}

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODULE="${APP_MODULE}"

USER healthos
EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port 8000 --no-access-log"]
