from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import urlencode
from uuid import UUID

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.auth.cookies import clear_auth_cookies, set_auth_cookies
from healthos_api.auth.delivery import OtpDeliveryError, deliver_mobile_otp, deliver_otp
from healthos_api.auth.rate_limit import enforce_rate_limit
from healthos_api.auth.schemas import (
    AuthResponse,
    DoctorSignup,
    LoginRequest,
    MessageResponse,
    OrganizationSignup,
    OtpResendRequest,
    OtpVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PatientSignup,
    SessionResponse,
    UserSummary,
)
from healthos_api.auth.service import (
    AccountUnavailableError,
    AuthenticationError,
    OAuthLinkError,
    OtpValidationError,
    RefreshRaceError,
    RefreshTokenReuseError,
    RegistrationConflict,
    VerificationRequiredError,
    authenticate_google,
    authenticate_password,
    issue_session,
    list_user_sessions,
    record_audit_event,
    register_user,
    request_otp,
    reset_password,
    revoke_user_session,
    rotate_refresh_token,
    to_auth_response,
    to_user_summary,
    user_query,
    verify_otp,
)
from healthos_api.auth.tokens import InvalidTokenError, decode_refresh_token
from healthos_api.config import Settings, get_settings
from healthos_api.core.security import (
    AuthContext,
    client_context,
    current_auth_context,
    enforce_csrf,
    require_permissions,
)
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import AccountType, AuthSession, OtpPurpose, User
from healthos_platform.config import Environment

router = APIRouter(prefix="/auth", tags=["authentication"])


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


@router.post("/signup/patient", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def signup_patient(
    payload: PatientSignup,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    return await _signup(AccountType.PATIENT, payload, request, db, settings)


@router.post("/signup/doctor", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def signup_doctor(
    payload: DoctorSignup,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    return await _signup(AccountType.DOCTOR, payload, request, db, settings)


@router.post(
    "/signup/hospital", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def signup_hospital(
    payload: OrganizationSignup,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    return await _signup(AccountType.HOSPITAL, payload, request, db, settings)


@router.post(
    "/signup/insurance", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def signup_insurance(
    payload: OrganizationSignup,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    return await _signup(AccountType.INSURANCE, payload, request, db, settings)


async def _signup(
    account_type: AccountType,
    payload: PatientSignup | DoctorSignup | OrganizationSignup,
    request: Request,
    db: AsyncSession,
    settings: Settings,
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="signup",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=5,
        window_seconds=3600,
    )
    try:
        user, code, mobile_code = await register_user(
            db,
            account_type=account_type,
            payload=payload,
            settings=settings,
            client=client_context(request),
        )
        await deliver_otp(
            email=user.email,
            code=code,
            purpose=OtpPurpose.EMAIL_VERIFICATION,
            settings=settings,
        )
        phone = (
            user.patient_profile.phone
            if user.patient_profile
            else user.doctor_profile.phone
            if user.doctor_profile
            else user.organization_profile.phone
            if user.organization_profile
            else None
        )
        if not phone:
            raise OtpDeliveryError("A mobile number is required for registration")
        await deliver_mobile_otp(phone=phone, code=mobile_code, settings=settings)
    except RegistrationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OtpDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return MessageResponse(
        message="Account created. Verify the email address and mobile number to continue.",
        debug_code=_debug_code(code, settings),
        debug_mobile_code=_debug_code(mobile_code, settings),
    )


@router.post("/login/{account_type}", response_model=AuthResponse)
async def login(
    account_type: AccountType,
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    await enforce_rate_limit(
        request,
        scope="login",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=10,
        window_seconds=900,
    )
    try:
        user = await authenticate_password(
            db,
            email=str(payload.email),
            password=payload.password,
            account_type=account_type,
        )
        tokens = await issue_session(
            db, user=user, settings=settings, client=client_context(request)
        )
    except VerificationRequiredError as exc:
        await record_audit_event(
            db,
            event_type="auth.login_rejected.verification_required",
            client=client_context(request),
            event_data={"account_type": account_type.value},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AccountUnavailableError as exc:
        await record_audit_event(
            db,
            event_type="auth.login_rejected.account_unavailable",
            client=client_context(request),
            event_data={"account_type": account_type.value},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AuthenticationError as exc:
        await record_audit_event(
            db,
            event_type="auth.login_rejected.invalid_credentials",
            client=client_context(request),
            event_data={"account_type": account_type.value},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        settings=settings,
    )
    return to_auth_response(tokens, settings)


@router.post("/otp/verify", response_model=MessageResponse)
async def verify_otp_code(
    payload: OtpVerificationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="otp-verify",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=10,
        window_seconds=600,
    )
    try:
        await verify_otp(
            db,
            email=str(payload.email),
            code=payload.code,
            purpose=payload.purpose,
            settings=settings,
            client=client_context(request),
        )
    except OtpValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Verification completed successfully.")


@router.post("/otp/resend", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def resend_otp(
    payload: OtpResendRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="otp-resend",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=3,
        window_seconds=900,
    )
    code = await request_otp(
        db,
        email=str(payload.email),
        purpose=payload.purpose,
        settings=settings,
        client=client_context(request),
    )
    if code:
        try:
            if payload.purpose == OtpPurpose.MOBILE_VERIFICATION:
                user = await db.scalar(user_query().where(User.email == str(payload.email)))
                phone = (
                    user.patient_profile.phone
                    if user and user.patient_profile
                    else user.doctor_profile.phone
                    if user and user.doctor_profile
                    else user.organization_profile.phone
                    if user and user.organization_profile
                    else None
                )
                if phone:
                    await deliver_mobile_otp(phone=phone, code=code, settings=settings)
            else:
                await deliver_otp(
                    email=str(payload.email),
                    code=code,
                    purpose=payload.purpose,
                    settings=settings,
                )
        except OtpDeliveryError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
    return MessageResponse(
        message="If the account is eligible, a verification code has been sent.",
        debug_code=_debug_code(code, settings),
    )


@router.post(
    "/password/forgot", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
async def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="password-forgot",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=3,
        window_seconds=900,
    )
    code = await request_otp(
        db,
        email=str(payload.email),
        purpose=OtpPurpose.PASSWORD_RESET,
        settings=settings,
        client=client_context(request),
    )
    if code:
        try:
            await deliver_otp(
                email=str(payload.email),
                code=code,
                purpose=OtpPurpose.PASSWORD_RESET,
                settings=settings,
            )
        except OtpDeliveryError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
    return MessageResponse(
        message="If an account exists, password reset instructions have been sent.",
        debug_code=_debug_code(code, settings),
    )


@router.post("/password/reset", response_model=MessageResponse)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await enforce_rate_limit(
        request,
        scope="password-reset",
        identifier=f"{request.client.host if request.client else 'unknown'}:{payload.email}",
        limit=10,
        window_seconds=900,
    )
    try:
        await reset_password(
            db,
            email=str(payload.email),
            code=payload.code,
            new_password=payload.password,
            settings=settings,
            client=client_context(request),
        )
    except OtpValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Password reset successfully. Sign in with the new password.")


@router.post(
    "/refresh",
    response_model=AuthResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def refresh_session(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required"
        )
    try:
        claims = decode_refresh_token(raw_token, settings)
        tokens = await rotate_refresh_token(
            db,
            raw_token=raw_token,
            session_id=claims.sid,
            family_id=claims.family,
            settings=settings,
            client=client_context(request),
        )
    except RefreshRaceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidTokenError, AuthenticationError, RefreshTokenReuseError) as exc:
        clear_auth_cookies(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        settings=settings,
    )
    return to_auth_response(tokens, settings)


@router.post(
    "/logout",
    response_model=MessageResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def logout(
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await revoke_user_session(
        db,
        user_id=context.user.id,
        session_id=context.session.id,
        client=client_context(request),
    )
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Signed out successfully.")


@router.get("/session", response_model=UserSummary)
async def get_current_session(
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> UserSummary:
    return to_user_summary(context.user, context.tenant_id)


@router.get("/sessions", response_model=list[SessionResponse])
async def get_sessions(
    context: Annotated[AuthContext, Depends(require_permissions("sessions:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionResponse]:
    return await list_user_sessions(
        db, user_id=context.user.id, current_session_id=context.session.id
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def delete_session(
    session_id: UUID,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(require_permissions("sessions:revoke"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    found = await revoke_user_session(
        db,
        user_id=context.user.id,
        session_id=session_id,
        client=client_context(request),
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session_id == context.session.id:
        clear_auth_cookies(response, settings)
    return MessageResponse(message="Session revoked.")


@router.delete(
    "/sessions",
    response_model=MessageResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def delete_all_sessions(
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(require_permissions("sessions:revoke"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == context.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason="user_revoked_all")
    )
    await db.commit()
    await record_audit_event(
        db,
        event_type="auth.all_sessions_revoked",
        actor_user_id=context.user.id,
        subject_user_id=context.user.id,
        client=client_context(request),
    )
    clear_auth_cookies(response, settings)
    return MessageResponse(message="All sessions revoked.")


@router.get("/google/{account_type}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def google_login(
    account_type: AccountType,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    if account_type == AccountType.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin OAuth is disabled")
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OAuth is not configured"
        )
    await enforce_rate_limit(
        request,
        scope="google-oauth",
        identifier=request.client.host if request.client else "unknown",
        limit=20,
        window_seconds=600,
    )
    request.session["oauth_account_type"] = account_type.value
    response = await build_oauth(settings).google.authorize_redirect(
        request, str(settings.google_redirect_uri)
    )
    return cast(RedirectResponse, response)


@router.get("/google/callback", response_model=None)
async def google_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    try:
        account_type = AccountType(request.session.pop("oauth_account_type"))
        token: dict[str, Any] = await build_oauth(settings).google.authorize_access_token(request)
        user_info = token.get("userinfo", {})
        tokens = await authenticate_google(
            db,
            account_type=account_type,
            subject=str(user_info["sub"]),
            email=str(user_info["email"]),
            email_verified=(
                user_info.get("email_verified") is True or user_info.get("email_verified") == "true"
            ),
            given_name=str(user_info.get("given_name", "")),
            family_name=str(user_info.get("family_name", "")),
            settings=settings,
            client=client_context(request),
        )
    except (KeyError, ValueError, OAuthError, OAuthLinkError, AuthenticationError):
        query = urlencode({"error": "google_authentication_failed"})
        return RedirectResponse(f"{settings.frontend_auth_callback_url}?{query}")
    response = RedirectResponse(str(settings.frontend_auth_callback_url))
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        settings=settings,
    )
    return response


def _debug_code(code: str | None, settings: Settings) -> str | None:
    if settings.environment in {Environment.LOCAL, Environment.TEST}:
        return code
    return None
