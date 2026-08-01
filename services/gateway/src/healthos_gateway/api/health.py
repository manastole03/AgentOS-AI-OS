from fastapi import APIRouter, Request, Response, status
from httpx import AsyncClient

from healthos_gateway import __version__
from healthos_gateway.config import get_settings
from healthos_platform.models import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(service="healthos-gateway", status="ok", version=__version__)


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    settings = get_settings()
    client: AsyncClient = request.app.state.http_client
    targets = {
        "api": f"{str(settings.api_service_url).rstrip('/')}/api/v1/health/live",
        "ai": f"{str(settings.ai_service_url).rstrip('/')}/ai/v1/health/live",
    }
    checks: dict[str, str] = {}
    for name, url in targets.items():
        try:
            upstream = await client.get(url)
            checks[name] = "ok" if upstream.is_success else "unavailable"
        except Exception:
            checks[name] = "unavailable"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service="healthos-gateway",
        status="ok" if healthy else "degraded",
        version=__version__,
        checks=checks,
    )
