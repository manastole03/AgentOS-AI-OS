from fastapi import APIRouter, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from healthos_ai import __version__
from healthos_platform.models import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(service="healthos-ai", status="ok", version=__version__)


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    redis: Redis = request.app.state.redis
    checks: dict[str, str] = {}
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    try:
        async with request.app.state.sessions() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"
    checks["langgraph_checkpointer"] = (
        "ok" if request.app.state.checkpointer_ready else "unavailable"
    )
    checks["model_gateway"] = "ok" if await request.app.state.llm.healthy() else "unavailable"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service="healthos-ai",
        status="ok" if healthy else "degraded",
        version=__version__,
        checks=checks,
    )
