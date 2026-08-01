from fastapi import APIRouter

from healthos_api.api.routes import (
    auth,
    clinical,
    coverage,
    health,
    labs,
    medications,
    operations,
    payer,
    platform,
    portal,
    scheduling,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(portal.router)
api_router.include_router(platform.router)
api_router.include_router(clinical.router)
api_router.include_router(medications.router)
api_router.include_router(scheduling.router)
api_router.include_router(labs.router)
api_router.include_router(coverage.router)
api_router.include_router(payer.router)
api_router.include_router(operations.router)
