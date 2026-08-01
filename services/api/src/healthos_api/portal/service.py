from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    ConsentGrant,
    OrganizationMembership,
    PatientProfile,
    PortalNotification,
    PortalRecord,
    User,
)
from healthos_api.portal.access import authorize_module
from healthos_api.portal.schemas import (
    DashboardMetric,
    DashboardResponse,
    RecordCreate,
    RecordResponse,
    RecordUpdate,
)


def tenant_id(context: AuthContext) -> UUID:
    return context.tenant_id


def display_name(context: AuthContext) -> str:
    user = context.user
    if user.patient_profile:
        return f"{user.patient_profile.first_name} {user.patient_profile.last_name}"
    if user.doctor_profile:
        return f"Dr. {user.doctor_profile.first_name} {user.doctor_profile.last_name}"
    if user.organization_profile:
        return user.organization_profile.legal_name
    return user.email


def record_response(record: PortalRecord) -> RecordResponse:
    return RecordResponse(
        id=record.id,
        category=record.category,
        title=record.title,
        status=record.status,
        patient_user_id=record.patient_user_id,
        assigned_user_id=record.assigned_user_id,
        external_reference=record.external_reference,
        occurred_at=record.occurred_at,
        due_at=record.due_at,
        amount_cents=record.amount_cents,
        currency=record.currency,
        data=record.data,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def scoped_records(context: AuthContext) -> Any:
    query = select(PortalRecord)
    if context.user.account_type == AccountType.ADMIN:
        return query
    if context.user.account_type == AccountType.PATIENT:
        return query.where(
            or_(
                PortalRecord.owner_user_id == context.user.id,
                PortalRecord.patient_user_id == context.user.id,
            )
        )
    return query.where(PortalRecord.tenant_id == tenant_id(context))


async def list_records(
    db: AsyncSession, context: AuthContext, category: str, status: str | None, limit: int
) -> list[PortalRecord]:
    authorize_module(context.user.account_type, category)
    query = scoped_records(context).where(PortalRecord.category == category)
    if status:
        query = query.where(PortalRecord.status == status)
    return list(
        (
            await db.scalars(query.order_by(PortalRecord.created_at.desc()).limit(min(limit, 200)))
        ).all()
    )


async def create_record(
    db: AsyncSession, context: AuthContext, category: str, payload: RecordCreate
) -> PortalRecord:
    authorize_module(context.user.account_type, category)
    patient_user_id = payload.patient_user_id
    if context.user.account_type == AccountType.PATIENT:
        patient_user_id = context.user.id
    healthos_patient_id = str(payload.data.get("patient_id", "")).upper()
    if patient_user_id is None and healthos_patient_id:
        patient_user_id = await db.scalar(
            select(PatientProfile.user_id).where(PatientProfile.patient_id == healthos_patient_id)
        )
        if patient_user_id is None:
            raise ValueError("HealthOS Patient ID was not found")
    assigned_user_id = payload.assigned_user_id
    if category == "consents":
        raw_grantee = payload.data.get("grantee_user_id")
        if raw_grantee:
            try:
                assigned_user_id = UUID(str(raw_grantee))
            except ValueError as exc:
                raise ValueError("The consent grantee must be a valid user ID") from exc
            if await db.scalar(select(User.id).where(User.id == assigned_user_id)) is None:
                raise ValueError("The consent grantee was not found")
    if (
        patient_user_id
        and patient_user_id != context.user.id
        and context.user.account_type != AccountType.ADMIN
        and not await has_patient_consent(
            db, patient_user_id=patient_user_id, grantee_user_id=context.user.id, category=category
        )
    ):
        raise PermissionError("The patient has not granted access for this record type")
    data = dict(payload.data)
    if category == "vitals" and not data.get("bmi"):
        try:
            weight = float(data.get("weight_kg", 0))
            height_m = float(data.get("height_cm", 0)) / 100
            if weight > 0 and height_m > 0:
                data["bmi"] = round(weight / (height_m * height_m), 1)
        except (TypeError, ValueError):
            pass
    record = PortalRecord(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=patient_user_id
        or (context.user.id if context.user.account_type == AccountType.PATIENT else None),
        assigned_user_id=assigned_user_id,
        category=category,
        title=payload.title,
        status=payload.status,
        external_reference=payload.external_reference,
        occurred_at=payload.occurred_at,
        due_at=payload.due_at,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper() if payload.currency else None,
        data=data,
    )
    db.add(record)
    if category == "medications" and patient_user_id:
        _add_medication_reminders(db, record, context, data)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type=f"portal.{category}.created",
            subject_user_id=patient_user_id,
            event_data={"record_id": str(record.id)},
        )
    )
    await db.commit()
    await db.refresh(record)
    return record


async def find_record(
    db: AsyncSession, context: AuthContext, category: str, record_id: UUID
) -> PortalRecord | None:
    authorize_module(context.user.account_type, category)
    return cast(
        PortalRecord | None,
        await db.scalar(
            scoped_records(context).where(
                PortalRecord.id == record_id, PortalRecord.category == category
            )
        ),
    )


async def update_record(
    db: AsyncSession, context: AuthContext, record: PortalRecord, payload: RecordUpdate
) -> PortalRecord:
    requested_patient_id = payload.patient_user_id
    if (
        requested_patient_id
        and requested_patient_id != record.patient_user_id
        and requested_patient_id != context.user.id
        and context.user.account_type != AccountType.ADMIN
        and not await has_patient_consent(
            db,
            patient_user_id=requested_patient_id,
            grantee_user_id=context.user.id,
            category=record.category,
        )
    ):
        raise PermissionError("The patient has not granted access for this record type")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "currency" and value:
            value = value.upper()
        setattr(record, field, value)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type=f"portal.{record.category}.updated",
            subject_user_id=record.patient_user_id,
            event_data={"record_id": str(record.id)},
        )
    )
    await db.commit()
    await db.refresh(record)
    return record


async def has_patient_consent(
    db: AsyncSession, *, patient_user_id: UUID, grantee_user_id: UUID, category: str
) -> bool:
    now = datetime.now(UTC)
    grantee_organizations = select(OrganizationMembership.organization_id).where(
        OrganizationMembership.user_id == grantee_user_id,
        OrganizationMembership.status == "active",
    )
    typed_grants = list(
        (
            await db.scalars(
                select(ConsentGrant).where(
                    ConsentGrant.patient_user_id == patient_user_id,
                    ConsentGrant.status == "active",
                    ConsentGrant.revoked_at.is_(None),
                    or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > now),
                    or_(
                        ConsentGrant.grantee_user_id == grantee_user_id,
                        ConsentGrant.grantee_organization_id.in_(grantee_organizations),
                    ),
                )
            )
        ).all()
    )
    if any(category in grant.scopes or "*" in grant.scopes for grant in typed_grants):
        return True
    # Compatibility read for grants created before migration 0006.
    grants = list(
        (
            await db.scalars(
                select(PortalRecord).where(
                    PortalRecord.category == "consents",
                    PortalRecord.patient_user_id == patient_user_id,
                    PortalRecord.assigned_user_id == grantee_user_id,
                    PortalRecord.status == "active",
                    or_(PortalRecord.due_at.is_(None), PortalRecord.due_at > datetime.now(UTC)),
                )
            )
        ).all()
    )
    return any(
        category in _consent_scopes(grant.data) or "*" in _consent_scopes(grant.data)
        for grant in grants
    )


def _consent_scopes(data: dict[str, Any]) -> set[str]:
    raw = data.get("scopes", [])
    if isinstance(raw, str):
        raw = raw.split(",")
    return {str(value).strip() for value in raw if str(value).strip()}


def _add_medication_reminders(
    db: AsyncSession,
    medication: PortalRecord,
    context: AuthContext,
    data: dict[str, Any],
) -> None:
    raw_times = data.get("times", [])
    if isinstance(raw_times, str):
        raw_times = raw_times.split(",")
    for reminder_time in (str(value).strip() for value in raw_times):
        if not reminder_time:
            continue
        db.add(
            PortalRecord(
                tenant_id=tenant_id(context),
                owner_user_id=context.user.id,
                patient_user_id=medication.patient_user_id,
                category="health_reminders",
                title=f"Take {data.get('medicine') or medication.title}",
                status="active",
                due_at=medication.due_at,
                data={
                    "medication_record_id": str(medication.id),
                    "reminder_type": "medication",
                    "frequency": "daily",
                    "time": reminder_time,
                    "active_until": data.get("course_end"),
                    "dosage": data.get("dosage"),
                },
            )
        )


async def dashboard(
    db: AsyncSession, context: AuthContext, integrations: dict[str, bool]
) -> DashboardResponse:
    categories = {
        AccountType.PATIENT: ("appointments", "lab_reports", "claims", "health_reminders"),
        AccountType.DOCTOR: ("schedule", "patients", "prescriptions", "documentation"),
        AccountType.HOSPITAL: ("staff", "departments", "beds", "billing"),
        AccountType.INSURANCE: ("policies", "eligibility", "claims", "prior_authorization"),
        AccountType.ADMIN: ("analytics", "audit_logs", "user_management", "monitoring"),
    }[context.user.account_type]
    metrics: list[DashboardMetric] = []
    for category in categories:
        if category == "user_management":
            value = int(await db.scalar(select(func.count()).select_from(User)) or 0)
        elif category == "audit_logs":
            value = int(await db.scalar(select(func.count()).select_from(AuditEvent)) or 0)
        else:
            count_query = (
                scoped_records(context)
                .with_only_columns(func.count())
                .where(PortalRecord.category == category)
            )
            value = int(await db.scalar(count_query) or 0)
        metrics.append(
            DashboardMetric(
                label=category.replace("_", " ").title(),
                value=value,
                trend="Live",
                tone="positive" if value else "neutral",
            )
        )
    recent = list(
        (
            await db.scalars(
                scoped_records(context).order_by(PortalRecord.created_at.desc()).limit(6)
            )
        ).all()
    )
    unread = int(
        await db.scalar(
            select(func.count())
            .select_from(PortalNotification)
            .where(
                PortalNotification.recipient_user_id == context.user.id,
                PortalNotification.read_at.is_(None),
            )
        )
        or 0
    )
    return DashboardResponse(
        account_type=context.user.account_type.value,
        display_name=display_name(context),
        metrics=metrics,
        recent=[record_response(item) for item in recent],
        unread_notifications=unread,
        integrations=integrations,
    )
