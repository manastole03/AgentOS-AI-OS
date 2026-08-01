from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient, Timeout
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from healthos_api import __version__
from healthos_api.api.router import api_router
from healthos_api.config import get_settings
from healthos_api.db.session import create_database_engine, create_session_factory
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
    app.state.db_engine = create_database_engine(settings.database_url.get_secret_value())
    app.state.session_factory = create_session_factory(app.state.db_engine)
    app.state.redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    app.state.http = AsyncClient(timeout=Timeout(60))
    yield
    await app.state.http.aclose()
    await app.state.redis.aclose()
    await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HealthOS Core API",
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(PrometheusMiddleware, service_name=settings.service_name)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        DistributedRateLimitMiddleware,
        service_name=settings.service_name,
        default_limit=600,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=settings.environment == Environment.PRODUCTION,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.jwt_secret_key.get_secret_value(),
        https_only=settings.environment == Environment.PRODUCTION,
        same_site="lax",
        max_age=600,
    )
    app.include_router(api_router, prefix="/api/v1")
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
