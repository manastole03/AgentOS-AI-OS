import time

from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "healthos_http_requests_total", "HTTP requests", ["service", "method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "healthos_http_request_duration_seconds",
    "HTTP request duration",
    ["service", "method", "route"],
)
HTTP_IN_FLIGHT = Gauge("healthos_http_requests_in_flight", "In-flight HTTP requests", ["service"])


class PrometheusMiddleware:
    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        self.app, self.service_name = app, service_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_code = 500
        HTTP_IN_FLIGHT.labels(self.service_name).inc()

        async def tracked_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            route = scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            method = scope.get("method", "UNKNOWN")
            HTTP_REQUESTS.labels(self.service_name, method, route_path, str(status_code)).inc()
            HTTP_DURATION.labels(self.service_name, method, route_path).observe(
                time.perf_counter() - started
            )
            HTTP_IN_FLIGHT.labels(self.service_name).dec()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def configure_tracing(
    app: FastAPI, *, service_name: str, endpoint: str, sample_ratio: float
) -> None:
    if not endpoint:
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
        sampler=ParentBased(TraceIdRatioBased(sample_ratio)),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health/live,/health/ready,/metrics")
    HTTPXClientInstrumentor().instrument()
