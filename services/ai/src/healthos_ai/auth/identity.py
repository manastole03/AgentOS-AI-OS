import hashlib
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from healthos_ai.config import Settings


class Identity(BaseModel):
    id: UUID
    email: str = ""
    account_type: str
    roles: list[str] = Field(default_factory=list)
    patient_id: str | None = None

    @property
    def tenant_id(self) -> str:
        # Identity tenancy can later be replaced by an organization claim without
        # weakening current owner isolation.
        return str(self.id)

    @property
    def is_admin(self) -> bool:
        return self.account_type == "admin" or "admin" in self.roles


def _credential(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    token = request.cookies.get("healthos_access")
    if token:
        return token
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


async def get_identity(request: Request) -> Identity:
    token = _credential(request)
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    cache_key = f"healthos:ai:identity:{hashlib.sha256(token.encode()).hexdigest()}"
    cached = await redis.get(cache_key)
    if cached:
        return Identity.model_validate_json(cached)

    client: httpx.AsyncClient = request.app.state.http
    try:
        response = await client.get(
            f"{str(settings.api_service_url).rstrip('/')}/api/v1/auth/session",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service unavailable"
        ) from exc
    if response.status_code == 401:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service unavailable")
    body = response.json()
    user = body.get("user", body)
    identity = Identity(
        id=user["id"],
        email=user.get("email", ""),
        account_type=user["account_type"],
        roles=user.get("roles", []),
        patient_id=user.get("patient_id"),
    )
    await redis.set(cache_key, identity.model_dump_json(), ex=settings.identity_cache_ttl_seconds)
    return identity


CurrentIdentity = Annotated[Identity, Depends(get_identity)]
