import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import jwt
from pydantic import BaseModel, Field, ValidationError

from healthos_api.config import Settings


class AccessTokenClaims(BaseModel):
    sub: UUID
    sid: UUID
    jti: UUID
    type: Literal["access"]
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    ver: int
    iss: str
    aud: str | list[str]
    iat: datetime
    exp: datetime


class RefreshTokenClaims(BaseModel):
    sub: UUID
    sid: UUID
    family: UUID
    jti: UUID
    type: Literal["refresh"]
    iss: str
    aud: str | list[str]
    iat: datetime
    exp: datetime


class InvalidTokenError(ValueError):
    pass


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    token_version: int,
    roles: list[str],
    permissions: list[str],
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(session_id),
        "type": "access",
        "roles": sorted(set(roles)),
        "permissions": sorted(set(permissions)),
        "ver": token_version,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    *, user_id: UUID, session_id: UUID, family_id: UUID, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(session_id),
        "family": str(family_id),
        "type": "refresh",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return jwt.encode(
        payload,
        settings.jwt_refresh_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    return _decode(token, settings.jwt_secret_key.get_secret_value(), settings, AccessTokenClaims)


def decode_refresh_token(token: str, settings: Settings) -> RefreshTokenClaims:
    return _decode(
        token,
        settings.jwt_refresh_secret_key.get_secret_value(),
        settings,
        RefreshTokenClaims,
    )


def _decode[ClaimsT: BaseModel](
    token: str,
    secret: str,
    settings: Settings,
    claims_type: type[ClaimsT],
) -> ClaimsT:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "sid", "jti", "type", "iat", "exp"]},
        )
        return claims_type.model_validate(payload)
    except (jwt.PyJWTError, ValidationError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
