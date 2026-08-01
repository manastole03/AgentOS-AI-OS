import secrets

from fastapi import Response

from healthos_api.config import Settings


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    settings: Settings,
) -> str:
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        httponly=True,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/v1/auth",
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )
    return csrf_token


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name, path in (
        (settings.access_cookie_name, "/"),
        (settings.refresh_cookie_name, "/api/v1/auth"),
        (settings.csrf_cookie_name, "/"),
    ):
        response.delete_cookie(
            name,
            path=path,
            domain=settings.auth_cookie_domain,
            secure=settings.auth_cookie_secure,
            httponly=name != settings.csrf_cookie_name,
            samesite="lax",
        )
