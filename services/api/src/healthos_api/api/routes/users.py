from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.auth.schemas import ProfileResponse, ProfileUpdate
from healthos_api.auth.service import to_profile_response, update_profile
from healthos_api.core.security import (
    AuthContext,
    client_context,
    enforce_csrf,
    require_permissions,
)
from healthos_api.db.dependencies import get_db
from healthos_api.job_watch.schemas import JobWatchResponse, JobWatchUpdate
from healthos_api.job_watch.service import (
    build_job_watch_response,
    get_job_watch_profile,
    update_job_watch_profile,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ProfileResponse)
async def get_profile(
    context: Annotated[AuthContext, Depends(require_permissions("profile:read"))],
) -> ProfileResponse:
    return to_profile_response(context.user)


@router.patch(
    "/me",
    response_model=ProfileResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def patch_profile(
    payload: ProfileUpdate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("profile:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileResponse:
    user = await update_profile(db, context.user, payload, client_context(request))
    return to_profile_response(user)


@router.get("/me/job-watch", response_model=JobWatchResponse)
async def get_my_job_watch(
    context: Annotated[AuthContext, Depends(require_permissions("profile:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobWatchResponse:
    profile = await get_job_watch_profile(db, context.user.id)
    return build_job_watch_response(context.user, profile)


@router.patch(
    "/me/job-watch",
    response_model=JobWatchResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def patch_my_job_watch(
    payload: JobWatchUpdate,
    context: Annotated[AuthContext, Depends(require_permissions("profile:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobWatchResponse:
    profile = await update_job_watch_profile(
        db,
        user=context.user,
        tenant_id=context.tenant_id,
        payload=payload,
    )
    return build_job_watch_response(context.user, profile)
