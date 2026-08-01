from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from healthos_api.auth.identifiers import generate_patient_id
from healthos_api.auth.otp import new_otp_challenge, otp_matches
from healthos_api.auth.passwords import hash_password, verify_dummy_password, verify_password
from healthos_api.auth.schemas import (
    AuthResponse,
    DoctorSignup,
    OrganizationSignup,
    PatientSignup,
    ProfileResponse,
    ProfileUpdate,
    SessionResponse,
    UserSummary,
)
from healthos_api.auth.tokens import create_access_token, create_refresh_token, token_digest
from healthos_api.config import Settings
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    AuthSession,
    DoctorProfile,
    OAuthIdentity,
    Organization,
    OrganizationMembership,
    OrganizationProfile,
    OtpChallenge,
    OtpPurpose,
    PatientProfile,
    Role,
    User,
    UserStatus,
)


class AuthenticationError(ValueError):
    pass


class RegistrationConflict(ValueError):
    pass


class VerificationRequiredError(AuthenticationError):
    pass


class AccountUnavailableError(AuthenticationError):
    pass


class OtpValidationError(ValueError):
    pass


class RefreshTokenReuseError(AuthenticationError):
    pass


class RefreshRaceError(AuthenticationError):
    pass


class OAuthLinkError(AuthenticationError):
    pass


@dataclass(slots=True)
class ClientContext:
    ip_address: str | None
    user_agent: str | None


@dataclass(slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    user: User
    session: AuthSession


USER_LOAD_OPTIONS = (
    selectinload(User.roles).selectinload(Role.permissions),
    selectinload(User.patient_profile),
    selectinload(User.doctor_profile),
    selectinload(User.organization_profile),
)


def user_query() -> Select[tuple[User]]:
    return select(User).options(*USER_LOAD_OPTIONS)


def role_names(user: User) -> list[str]:
    return sorted(role.name for role in user.roles)


def permission_names(user: User) -> list[str]:
    return sorted({permission.name for role in user.roles for permission in role.permissions})


def to_user_summary(user: User, tenant_id: UUID | None = None) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        account_type=user.account_type,
        status=user.status,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        roles=role_names(user),
        patient_id=(user.patient_profile.patient_id if user.patient_profile else None),
        tenant_id=tenant_id or user.id,
    )


def to_auth_response(tokens: IssuedTokens, settings: Settings) -> AuthResponse:
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=to_user_summary(tokens.user),
    )


def to_profile_response(user: User) -> ProfileResponse:
    data: dict[str, Any] = to_user_summary(user).model_dump()
    data.update(created_at=user.created_at, updated_at=user.updated_at)
    if user.patient_profile:
        data.update(
            first_name=user.patient_profile.first_name,
            last_name=user.patient_profile.last_name,
            phone=user.patient_profile.phone,
            date_of_birth=user.patient_profile.date_of_birth,
            sex_at_birth=user.patient_profile.sex_at_birth,
            blood_type=user.patient_profile.blood_type,
            emergency_contact=user.patient_profile.emergency_contact,
            avatar_url=user.patient_profile.avatar_url,
        )
    elif user.doctor_profile:
        data.update(
            first_name=user.doctor_profile.first_name,
            last_name=user.doctor_profile.last_name,
            license_number=user.doctor_profile.license_number,
            license_jurisdiction=user.doctor_profile.license_jurisdiction,
            specialty=user.doctor_profile.specialty,
            affiliation=user.doctor_profile.affiliation,
            credentials_verified=user.doctor_profile.credentials_verified,
            phone=user.doctor_profile.phone,
            avatar_url=user.doctor_profile.avatar_url,
        )
    elif user.organization_profile:
        data.update(
            legal_name=user.organization_profile.legal_name,
            registration_number=user.organization_profile.registration_number,
            license_number=user.organization_profile.license_number,
            organization_type=user.organization_profile.organization_type,
            product_types=user.organization_profile.product_types,
            credentials_verified=user.organization_profile.credentials_verified,
            phone=user.organization_profile.phone,
            avatar_url=user.organization_profile.avatar_url,
        )
    return ProfileResponse.model_validate(data)


async def register_user(
    db: AsyncSession,
    *,
    account_type: AccountType,
    payload: PatientSignup | DoctorSignup | OrganizationSignup,
    settings: Settings,
    client: ClientContext,
) -> tuple[User, str, str]:
    email = str(payload.email).strip().lower()
    existing = await db.scalar(select(User.id).where(User.email == email))
    if existing:
        raise RegistrationConflict("An account with this email already exists")

    role = await db.scalar(select(Role).where(Role.name == account_type.value))
    if role is None:
        raise RuntimeError(f"RBAC role {account_type.value!r} has not been seeded")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        account_type=account_type,
        status=UserStatus.PENDING_VERIFICATION,
        roles=[role],
    )
    if account_type == AccountType.PATIENT and isinstance(payload, PatientSignup):
        user.patient_profile = PatientProfile(
            patient_id=generate_patient_id(),
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            date_of_birth=payload.date_of_birth,
            sex_at_birth=payload.sex_at_birth,
            blood_type=payload.blood_type,
            emergency_contact=payload.emergency_contact,
        )
    elif account_type == AccountType.DOCTOR and isinstance(payload, DoctorSignup):
        user.doctor_profile = DoctorProfile(
            first_name=payload.first_name,
            last_name=payload.last_name,
            license_number=payload.license_number.upper(),
            license_jurisdiction=payload.license_jurisdiction,
            specialty=payload.specialty,
            affiliation=payload.affiliation,
            phone=payload.phone,
        )
    elif account_type in {AccountType.HOSPITAL, AccountType.INSURANCE} and isinstance(
        payload, OrganizationSignup
    ):
        user.organization_profile = OrganizationProfile(
            account_type=account_type,
            legal_name=payload.legal_name,
            registration_number=payload.registration_number.upper(),
            license_number=(payload.license_number.upper() if payload.license_number else None),
            organization_type=payload.organization_type,
            product_types=list(payload.product_types),
            phone=payload.phone,
        )
    else:
        raise ValueError("Signup payload does not match account type")

    db.add(user)
    try:
        await db.flush()
        if user.organization_profile:
            organization = Organization(
                id=user.id,
                slug=f"{account_type.value}-{str(user.id)[:8]}",
                legal_name=user.organization_profile.legal_name,
                organization_type=account_type.value,
            )
            db.add(organization)
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="owner",
                    is_primary=True,
                    permissions=["*"],
                )
            )
        email_code = await create_otp(
            db, user=user, purpose=OtpPurpose.EMAIL_VERIFICATION, settings=settings
        )
        mobile_code = await create_otp(
            db, user=user, purpose=OtpPurpose.MOBILE_VERIFICATION, settings=settings
        )
        _audit(db, "auth.signup", user.id, user.id, client)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise RegistrationConflict(
            "The email, license, registration number, or patient identifier is already in use"
        ) from exc

    refreshed = await db.scalar(user_query().where(User.id == user.id))
    if refreshed is None:
        raise RuntimeError("Created user could not be reloaded")
    return refreshed, email_code, mobile_code


async def create_otp(
    db: AsyncSession,
    *,
    user: User,
    purpose: OtpPurpose,
    settings: Settings,
) -> str:
    await db.execute(
        update(OtpChallenge)
        .where(
            OtpChallenge.email == user.email,
            OtpChallenge.purpose == purpose,
            OtpChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
    )
    challenge, code = new_otp_challenge(
        email=user.email,
        purpose=purpose,
        settings=settings,
        user_id=user.id,
    )
    db.add(challenge)
    return code


async def request_otp(
    db: AsyncSession,
    *,
    email: str,
    purpose: OtpPurpose,
    settings: Settings,
    client: ClientContext,
) -> str | None:
    verify_dummy_password("otp-request-timing-equalizer")
    user = await db.scalar(user_query().where(User.email == email.strip().lower()))
    if user is None:
        return None
    if purpose == OtpPurpose.EMAIL_VERIFICATION and user.email_verified:
        return None
    if purpose == OtpPurpose.MOBILE_VERIFICATION and user.phone_verified:
        return None
    code = await create_otp(db, user=user, purpose=purpose, settings=settings)
    _audit(db, f"auth.otp_requested.{purpose.value}", user.id, user.id, client)
    await db.commit()
    return code


async def verify_otp(
    db: AsyncSession,
    *,
    email: str,
    code: str,
    purpose: OtpPurpose,
    settings: Settings,
    client: ClientContext,
    commit: bool = True,
) -> User:
    challenge = await db.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.email == email.strip().lower(),
            OtpChallenge.purpose == purpose,
            OtpChallenge.consumed_at.is_(None),
        )
        .order_by(OtpChallenge.created_at.desc())
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.expires_at <= now
        or challenge.attempts >= challenge.max_attempts
    ):
        raise OtpValidationError("The verification code is invalid or expired")

    challenge.attempts += 1
    if not otp_matches(challenge, code, settings):
        await db.commit()
        raise OtpValidationError("The verification code is invalid or expired")

    challenge.consumed_at = now
    user = await db.scalar(user_query().where(User.id == challenge.user_id).with_for_update())
    if user is None:
        raise OtpValidationError("The verification code is invalid or expired")

    if purpose == OtpPurpose.EMAIL_VERIFICATION:
        user.email_verified = True
    elif purpose == OtpPurpose.MOBILE_VERIFICATION:
        user.phone_verified = True
    if user.email_verified and user.phone_verified:
        user.status = (
            UserStatus.ACTIVE
            if user.account_type == AccountType.PATIENT
            else UserStatus.PENDING_REVIEW
        )
    _audit(db, f"auth.otp_verified.{purpose.value}", user.id, user.id, client)
    if commit:
        await db.commit()
    return user


async def authenticate_password(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    account_type: AccountType,
) -> User:
    user = await db.scalar(user_query().where(User.email == email.strip().lower()))
    if user is None or user.password_hash is None:
        verify_dummy_password(password)
        raise AuthenticationError("Invalid email or password")
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password")
    if user.account_type != account_type:
        raise AuthenticationError("Invalid email or password")
    if user.status == UserStatus.PENDING_VERIFICATION:
        raise VerificationRequiredError("Email and mobile verification are required")
    if user.status == UserStatus.PENDING_REVIEW:
        raise AccountUnavailableError("Professional credentials are awaiting verification")
    if user.status != UserStatus.ACTIVE:
        raise AccountUnavailableError("This account is unavailable")
    return user


async def issue_session(
    db: AsyncSession,
    *,
    user: User,
    settings: Settings,
    client: ClientContext,
    family_id: UUID | None = None,
) -> IssuedTokens:
    session_id = uuid4()
    family = family_id or uuid4()
    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=session_id,
        family_id=family,
        settings=settings,
    )
    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        family_id=family,
        refresh_token_hash=token_digest(refresh_token),
        user_agent=client.user_agent,
        ip_address=client.ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(auth_session)
    user.last_login_at = datetime.now(UTC)
    access_token = create_access_token(
        user_id=user.id,
        session_id=session_id,
        token_version=user.token_version,
        roles=role_names(user),
        permissions=permission_names(user),
        settings=settings,
    )
    _audit(db, "auth.session_created", user.id, user.id, client, {"session_id": str(session_id)})
    await db.commit()
    return IssuedTokens(access_token, refresh_token, user, auth_session)


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    raw_token: str,
    session_id: UUID,
    family_id: UUID,
    settings: Settings,
    client: ClientContext,
) -> IssuedTokens:
    session = await db.scalar(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    now = datetime.now(UTC)
    if session is None or session.family_id != family_id:
        raise AuthenticationError("Invalid refresh token")
    if session.revoked_at is not None:
        if (
            session.revoke_reason == "rotated"
            and (now - session.revoked_at).total_seconds()
            <= settings.refresh_rotation_grace_seconds
        ):
            raise RefreshRaceError("Refresh already in progress")
        await revoke_session_family(db, family_id, "refresh_token_reuse")
        await db.commit()
        raise RefreshTokenReuseError("Refresh token reuse detected")
    if session.refresh_token_hash != token_digest(raw_token):
        await revoke_session_family(db, family_id, "refresh_token_reuse")
        await db.commit()
        raise RefreshTokenReuseError("Refresh token reuse detected")
    if session.expires_at <= now:
        session.revoked_at = now
        session.revoke_reason = "expired"
        await db.commit()
        raise AuthenticationError("Refresh token expired")

    user = await db.scalar(user_query().where(User.id == session.user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        raise AccountUnavailableError("This account is unavailable")

    replacement_id = uuid4()
    refresh_token = create_refresh_token(
        user_id=user.id,
        session_id=replacement_id,
        family_id=family_id,
        settings=settings,
    )
    replacement = AuthSession(
        id=replacement_id,
        user_id=user.id,
        family_id=family_id,
        refresh_token_hash=token_digest(refresh_token),
        user_agent=client.user_agent,
        ip_address=client.ip_address,
        expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    # The self-referential FK requires the replacement row to exist before the
    # previous session can point at it; explicit flush avoids ORM ordering ambiguity.
    db.add(replacement)
    await db.flush()
    session.revoked_at = now
    session.revoke_reason = "rotated"
    session.replaced_by_id = replacement_id
    session.last_used_at = now
    access_token = create_access_token(
        user_id=user.id,
        session_id=replacement_id,
        token_version=user.token_version,
        roles=role_names(user),
        permissions=permission_names(user),
        settings=settings,
    )
    _audit(
        db,
        "auth.session_refreshed",
        user.id,
        user.id,
        client,
        {"session_id": str(replacement_id)},
    )
    await db.commit()
    return IssuedTokens(access_token, refresh_token, user, replacement)


async def revoke_session_family(db: AsyncSession, family_id: UUID, reason: str) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
    )


async def revoke_user_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    session_id: UUID,
    client: ClientContext,
) -> bool:
    session = await db.scalar(
        select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user_id)
    )
    if session is None:
        return False
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        session.revoke_reason = "user_revoked"
        _audit(
            db, "auth.session_revoked", user_id, user_id, client, {"session_id": str(session_id)}
        )
        await db.commit()
    return True


async def list_user_sessions(
    db: AsyncSession, *, user_id: UUID, current_session_id: UUID
) -> list[SessionResponse]:
    sessions = (
        await db.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
            )
            .order_by(AuthSession.created_at.desc())
        )
    ).all()
    return [
        SessionResponse(
            id=session.id,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            created_at=session.created_at,
            last_used_at=session.last_used_at,
            expires_at=session.expires_at,
            current=session.id == current_session_id,
        )
        for session in sessions
    ]


async def reset_password(
    db: AsyncSession,
    *,
    email: str,
    code: str,
    new_password: str,
    settings: Settings,
    client: ClientContext,
) -> None:
    user = await verify_otp(
        db,
        email=email,
        code=code,
        purpose=OtpPurpose.PASSWORD_RESET,
        settings=settings,
        client=client,
        commit=False,
    )
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason="password_reset")
    )
    _audit(db, "auth.password_reset", user.id, user.id, client)
    await db.commit()


async def update_profile(
    db: AsyncSession,
    user: User,
    payload: ProfileUpdate,
    client: ClientContext,
) -> User:
    values = payload.model_dump(exclude_unset=True)
    if "avatar_url" in values and values["avatar_url"] is not None:
        values["avatar_url"] = str(values["avatar_url"])
    profile: PatientProfile | DoctorProfile | OrganizationProfile | None
    profile = user.patient_profile or user.doctor_profile or user.organization_profile
    if profile is None:
        raise ValueError("This account does not have an editable profile")
    allowed = {"phone", "avatar_url"}
    if isinstance(profile, (PatientProfile, DoctorProfile)):
        allowed.update({"first_name", "last_name"})
    if isinstance(profile, OrganizationProfile):
        allowed.add("legal_name")
    for field, value in values.items():
        if field in allowed:
            setattr(profile, field, value)
    _audit(
        db,
        "profile.updated",
        user.id,
        user.id,
        client,
        {"fields": sorted(set(values).intersection(allowed))},
    )
    await db.commit()
    refreshed = await db.scalar(user_query().where(User.id == user.id))
    if refreshed is None:
        raise RuntimeError("Updated user could not be reloaded")
    return refreshed


async def record_audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    client: ClientContext,
    actor_user_id: UUID | None = None,
    subject_user_id: UUID | None = None,
    event_data: dict[str, Any] | None = None,
) -> None:
    _audit(
        db,
        event_type,
        actor_user_id,
        subject_user_id,
        client,
        event_data,
    )
    await db.commit()


async def authenticate_google(
    db: AsyncSession,
    *,
    account_type: AccountType,
    subject: str,
    email: str,
    email_verified: bool,
    given_name: str,
    family_name: str,
    settings: Settings,
    client: ClientContext,
) -> IssuedTokens:
    if not email_verified:
        raise OAuthLinkError("Google did not verify this email address")
    identity = await db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == "google",
            OAuthIdentity.provider_subject == subject,
        )
    )
    user: User | None = None
    if identity:
        user = await db.scalar(user_query().where(User.id == identity.user_id))
    if user is None:
        user = await db.scalar(user_query().where(User.email == email.strip().lower()))
        if user and user.account_type != account_type:
            raise OAuthLinkError("This email belongs to a different account type")
        if user is None:
            if account_type != AccountType.PATIENT:
                raise OAuthLinkError(
                    "Register the professional or organization account before linking Google"
                )
            role = await db.scalar(select(Role).where(Role.name == AccountType.PATIENT.value))
            if role is None:
                raise RuntimeError("Patient role has not been seeded")
            user = User(
                email=email.strip().lower(),
                account_type=AccountType.PATIENT,
                status=UserStatus.ACTIVE,
                email_verified=True,
                roles=[role],
                patient_profile=PatientProfile(
                    patient_id=generate_patient_id(),
                    first_name=given_name or "Google",
                    last_name=family_name or "User",
                ),
            )
            db.add(user)
            await db.flush()
        else:
            user.email_verified = True
            if user.status == UserStatus.PENDING_VERIFICATION and user.phone_verified:
                user.status = (
                    UserStatus.ACTIVE
                    if user.account_type == AccountType.PATIENT
                    else UserStatus.PENDING_REVIEW
                )
        db.add(
            OAuthIdentity(
                user_id=user.id,
                provider="google",
                provider_subject=subject,
                provider_email=email,
            )
        )
        await db.flush()
    if user.account_type != account_type or user.status != UserStatus.ACTIVE:
        raise OAuthLinkError("This Google identity cannot access the selected account type")
    return await issue_session(db, user=user, settings=settings, client=client)


def _audit(
    db: AsyncSession,
    event_type: str,
    actor_user_id: UUID | None,
    subject_user_id: UUID | None,
    client: ClientContext,
    event_data: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            ip_address=client.ip_address,
            user_agent=client.user_agent,
            event_data=event_data or {},
        )
    )
