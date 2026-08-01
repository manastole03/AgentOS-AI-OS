import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.auth.service import USER_LOAD_OPTIONS, ClientContext, permission_names
from healthos_api.auth.tokens import AccessTokenClaims, InvalidTokenError, decode_access_token
from healthos_api.config import Settings, get_settings
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import AuthSession, OrganizationMembership, User, UserStatus

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
    token = (
        credentials.credentials if credentials else request.cookies.get(settings.access_cookie_name)
    )
    if not token:
        raise _unauthorized()
    try:
        claims = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise _unauthorized() from exc

    user = await db.scalar(select(User).options(*USER_LOAD_OPTIONS).where(User.id == claims.sub))
    session = await db.scalar(
        select(AuthSession).where(
            AuthSession.id == claims.sid,
            AuthSession.user_id == claims.sub,
        )
    )
    now = datetime.now(UTC)
    if (
        user is None
        or session is None
        or user.status != UserStatus.ACTIVE
        or user.token_version != claims.ver
        or session.revoked_at is not None
        or session.expires_at <= now
    ):
        raise _unauthorized()
    primary_tenant = await db.scalar(
        select(OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .order_by(OrganizationMembership.is_primary.desc(), OrganizationMembership.created_at)
        .limit(1)
    )
    return AuthContext(
        user=user,
        session=session,
        claims=claims,
        tenant_id=primary_tenant or user.id,
    )


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


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
