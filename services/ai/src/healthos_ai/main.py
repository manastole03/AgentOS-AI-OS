from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from healthos_ai import __version__
from healthos_ai.api.health import router as health_router
from healthos_ai.api.routes import router as agent_router
from healthos_ai.bootstrap import build_runtime
from healthos_ai.config import get_settings
from healthos_ai.mcp.server import mcp, mcp_app
from healthos_platform.config import Environment
from healthos_platform.errors import install_error_handlers
from healthos_platform.logging import configure_logging
from healthos_platform.middleware import RequestContextMiddleware
from healthos_platform.observability import (
    PrometheusMiddleware,
    configure_tracing,
    metrics_response,
)
from healthos_platform.rate_limit import DistributedRateLimitMiddleware, RequestBodyLimitMiddleware
from healthos_platform.security import SecurityHeadersMiddleware

settings = get_settings()
configure_logging(level=settings.log_level, log_format=settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run(), build_runtime(settings) as runtime:
        app.state.settings = settings
        app.state.engine, app.state.sessions = runtime.engine, runtime.sessions
        app.state.redis, app.state.llm = runtime.redis, runtime.llm
        app.state.knowledge, app.state.memories = runtime.knowledge, runtime.memories
        app.state.audit, app.state.orchestrator = runtime.audit, runtime.orchestrator
        app.state.runs = runtime.runs
        app.state.cipher = runtime.cipher
        app.state.checkpointer_ready = runtime.checkpointer_ready
        app.state.http = httpx.AsyncClient()
        yield
        await app.state.http.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HealthOS AI Operating System",
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(PrometheusMiddleware, service_name=settings.service_name)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        DistributedRateLimitMiddleware, service_name=settings.service_name, default_limit=300
    )
    app.add_middleware(
        SecurityHeadersMiddleware, production=settings.environment == Environment.PRODUCTION
    )
    app.include_router(health_router, prefix="/ai/v1")
    app.include_router(agent_router, prefix="/ai/v1")
    app.mount("/mcp", mcp_app)

    app.add_api_route("/metrics", metrics_response, include_in_schema=False)
    install_error_handlers(app)
    configure_tracing(
        app,
        service_name=settings.service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
        sample_ratio=settings.otel_trace_sample_ratio,
    )
    return app


app = create_app()
