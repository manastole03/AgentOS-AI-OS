from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient, Timeout
from redis.asyncio import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from healthos_gateway import __version__
from healthos_gateway.api.health import router as health_router
from healthos_gateway.api.proxy import router as proxy_router
from healthos_gateway.config import get_settings
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
    app.state.http_client = AsyncClient(
        timeout=Timeout(settings.upstream_timeout_seconds),
        follow_redirects=False,
    )
    app.state.redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    yield
    await app.state.redis.aclose()
    await app.state.http_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HealthOS API Gateway",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(PrometheusMiddleware, service_name=settings.service_name)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        DistributedRateLimitMiddleware,
        service_name=settings.service_name,
        default_limit=settings.rate_limit_per_minute,
    )
    app.add_middleware(
        SecurityHeadersMiddleware, production=settings.environment == Environment.PRODUCTION
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(proxy_router)
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
