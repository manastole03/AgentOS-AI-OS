import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.config import Settings, get_settings
from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    DocumentAsset,
    IntegrationEvent,
    PortalNotification,
    PortalRecord,
    SystemSetting,
    User,
    UserStatus,
)
from healthos_api.integrations.clients import (
    FHIRClient,
    InsuranceClient,
    OCRService,
    PaymentGateway,
    request_digest,
)
from healthos_api.integrations.notifications import NotificationDispatcher
from healthos_api.portal.access import PORTAL_MODULES
from healthos_api.portal.schemas import (
    AppointmentBookingCreate,
    DashboardResponse,
    DocumentResponse,
    LabBookingCreate,
    NotificationCreate,
    NotificationResponse,
    PaymentIntentCreate,
    PolicyPurchaseCreate,
    RecordCreate,
    RecordResponse,
    RecordUpdate,
    SettingUpdate,
    SyncRequest,
    UserStatusUpdate,
)
from healthos_api.portal.service import (
    create_record,
    dashboard,
    find_record,
    list_records,
    record_response,
    tenant_id,
    update_record,
)

router = APIRouter(prefix="/portal", tags=["portal"])


def document_response(item: DocumentAsset) -> DocumentResponse:
    return DocumentResponse(
        id=item.id,
        category=item.category,
        filename=item.filename,
        content_type=item.content_type,
        byte_size=item.byte_size,
        status=item.status,
        ocr_text=item.ocr_text,
        fhir_resource_type=item.fhir_resource_type,
        fhir_resource_id=item.fhir_resource_id,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def notification_response(item: PortalNotification) -> NotificationResponse:
    return NotificationResponse(
        id=item.id,
        channel=item.channel,
        severity=item.severity,
        title=item.title,
        body=item.body,
        action_url=item.action_url,
        read_at=item.read_at,
        delivered_at=item.delivered_at,
        created_at=item.created_at,
    )


def integrations(settings: Settings) -> dict[str, bool]:
    return {
        "ocr": bool(settings.ocr_api_url),
        "fhir": bool(settings.fhir_base_url),
        "insurance": bool(settings.insurance_api_url),
        "payments": bool(settings.stripe_secret_key.get_secret_value()),
        "notifications": bool(settings.smtp_host or settings.notification_webhook_url),
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@router.get("/overview", response_model=DashboardResponse)
async def overview(
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DashboardResponse:
    return await dashboard(db, context, integrations(settings))


@router.get("/resources/{category}", response_model=list[RecordResponse])
async def resources(
    category: str,
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
) -> list[RecordResponse]:
    try:
        records = await list_records(db, context, category, status_filter, limit)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return [record_response(item) for item in records]


@router.post(
    "/resources/{category}",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def add_resource(
    category: str,
    payload: RecordCreate,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    try:
        record = await create_record(db, context, category, payload)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return record_response(record)


@router.patch(
    "/resources/{category}/{record_id}",
    response_model=RecordResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def patch_resource(
    category: str,
    record_id: UUID,
    payload: RecordUpdate,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    try:
        record = await find_record(db, context, category, record_id)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    return record_response(await update_record(db, context, record, payload))


@router.delete(
    "/resources/{category}/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
async def delete_resource(
    category: str,
    record_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        record = await find_record(db, context, category, record_id)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    await db.delete(record)
    await db.commit()


@router.get("/notifications", response_model=list[NotificationResponse])
async def notifications(
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[NotificationResponse]:
    items = (
        await db.scalars(
            select(PortalNotification)
            .where(PortalNotification.recipient_user_id == context.user.id)
            .order_by(PortalNotification.created_at.desc())
            .limit(200)
        )
    ).all()
    return [notification_response(item) for item in items]


@router.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def create_notification(
    payload: NotificationCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotificationResponse:
    recipient = payload.recipient_user_id or context.user.id
    if recipient != context.user.id and context.user.account_type.value not in {
        "doctor",
        "hospital",
        "insurance",
        "admin",
    }:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot notify another user")
    recipient_user = await db.get(User, recipient)
    if recipient_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")
    if recipient != context.user.id and context.user.account_type.value != "admin":
        authorized = await db.scalar(
            select(PortalRecord.id)
            .where(
                PortalRecord.tenant_id == tenant_id(context),
                PortalRecord.patient_user_id == recipient,
            )
            .limit(1)
        )
        if authorized is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Recipient is outside your care scope")
    delivered = await NotificationDispatcher(settings, request.app.state.http).dispatch(
        channel=payload.channel,
        email=recipient_user.email,
        title=payload.title,
        body=payload.body,
    )
    item = PortalNotification(
        tenant_id=tenant_id(context),
        recipient_user_id=recipient,
        channel=payload.channel,
        severity=payload.severity,
        title=payload.title,
        body=payload.body,
        action_url=payload.action_url,
        delivered_at=datetime.now(UTC) if delivered else None,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return notification_response(item)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def mark_notification_read(
    notification_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    item = await db.scalar(
        select(PortalNotification).where(
            PortalNotification.id == notification_id,
            PortalNotification.recipient_user_id == context.user.id,
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    item.read_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(item)
    return notification_response(item)


@router.get("/documents", response_model=list[DocumentResponse])
async def documents(
    context: Annotated[AuthContext, Depends(require_permissions("documents:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DocumentResponse]:
    query = select(DocumentAsset)
    if context.user.account_type.value != "admin":
        query = query.where(DocumentAsset.tenant_id == tenant_id(context))
    items = (await db.scalars(query.order_by(DocumentAsset.created_at.desc()).limit(200))).all()
    return [document_response(item) for item in items]


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def upload_document(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("documents:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    category: Annotated[str, Form()] = "general",
    patient_user_id: Annotated[UUID | None, Form()] = None,
) -> DocumentResponse:
    content = await file.read(settings.document_max_bytes + 1)
    if len(content) > settings.document_max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Document exceeds upload limit")
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Document is empty")
    filename = (file.filename or "document")[:255]
    content_type = file.content_type or "application/octet-stream"
    result = await OCRService(settings, request.app.state.http).extract(
        filename, content_type, content
    )
    item = DocumentAsset(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=patient_user_id,
        category=category[:64],
        filename=filename,
        content_type=content_type,
        byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        status=result.status,
        ocr_text=str(result.data.get("text", "")) or None,
        metadata_={"ocr_provider": result.provider},
    )
    db.add(item)
    db.add(
        IntegrationEvent(
            tenant_id=tenant_id(context),
            actor_user_id=context.user.id,
            provider=result.provider,
            operation="document_ocr",
            status=result.status,
            request_digest=item.sha256,
            response_metadata={"byte_size": len(content)},
        )
    )
    await db.commit()
    await db.refresh(item)
    return document_response(item)


async def authorized_document(
    db: AsyncSession, context: AuthContext, document_id: UUID
) -> DocumentAsset:
    query = select(DocumentAsset).where(DocumentAsset.id == document_id)
    if context.user.account_type.value != "admin":
        query = query.where(DocumentAsset.tenant_id == tenant_id(context))
    item = await db.scalar(query)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return item


@router.get("/documents/{document_id}/content")
async def download_document(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("documents:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    item = await authorized_document(db, context, document_id)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="document.downloaded",
            subject_user_id=item.patient_user_id,
            event_data={"document_id": str(item.id)},
        )
    )
    await db.commit()
    safe_name = (
        "".join(
            character for character in item.filename if character.isalnum() or character in "._- "
        )
        or "document"
    )
    return Response(
        item.content,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
async def delete_document(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("documents:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    item = await authorized_document(db, context, document_id)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="document.deleted",
            subject_user_id=item.patient_user_id,
            event_data={"document_id": str(item.id), "sha256": item.sha256},
        )
    )
    await db.delete(item)
    await db.commit()


@router.post("/integrations/fhir", dependencies=[Depends(enforce_csrf)])
async def sync_fhir(
    payload: SyncRequest,
    request: Request,
    context: Annotated[
        AuthContext, Depends(require_roles("patient", "doctor", "hospital", "admin"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if not payload.patient_reference:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "patient_reference is required")
    result = await FHIRClient(settings, request.app.state.http).sync_patient(
        payload.patient_reference
    )
    imported = 0
    mapping = {
        "Appointment": "appointments",
        "Immunization": "vaccinations",
        "DiagnosticReport": "lab_reports",
        "Observation": "lab_reports",
        "MedicationRequest": "prescriptions",
        "Condition": "medical_history",
    }
    for resource in result.data.get("resources", []):
        category = mapping.get(resource.get("resourceType"))
        if category and category not in PORTAL_MODULES[context.user.account_type]:
            category = "reports" if "reports" in PORTAL_MODULES[context.user.account_type] else None
        if category:
            db.add(
                PortalRecord(
                    tenant_id=tenant_id(context),
                    owner_user_id=context.user.id,
                    patient_user_id=context.user.id
                    if context.user.account_type.value == "patient"
                    else None,
                    category=category,
                    title=f"{resource.get('resourceType')} import",
                    status=str(resource.get("status", "active")),
                    external_reference=str(resource.get("id", "")) or None,
                    data=resource,
                )
            )
            imported += 1
    db.add(
        IntegrationEvent(
            tenant_id=tenant_id(context),
            actor_user_id=context.user.id,
            provider="fhir",
            operation="patient_everything",
            status=result.status,
            external_reference=result.external_reference,
            request_digest=request_digest(payload.model_dump()),
            response_metadata={"imported": imported},
        )
    )
    await db.commit()
    return {"status": result.status, "imported": imported}


@router.post("/integrations/insurance", dependencies=[Depends(enforce_csrf)])
async def sync_insurance(
    payload: SyncRequest,
    request: Request,
    context: Annotated[
        AuthContext, Depends(require_roles("patient", "hospital", "insurance", "admin"))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    result = await InsuranceClient(settings, request.app.state.http).execute(
        payload.operation, payload.parameters
    )
    category = (
        payload.operation
        if payload.operation in PORTAL_MODULES[context.user.account_type]
        else "claims"
    )
    imported = 0
    for record_data in result.data.get("records", []):
        db.add(
            PortalRecord(
                tenant_id=tenant_id(context),
                owner_user_id=context.user.id,
                patient_user_id=context.user.id
                if context.user.account_type.value == "patient"
                else None,
                category=category,
                title=str(record_data.get("title", "Insurance API record"))[:255],
                status=str(record_data.get("status", "active"))[:64],
                external_reference=str(record_data.get("id", ""))[:255] or None,
                data=record_data,
            )
        )
        imported += 1
    db.add(
        IntegrationEvent(
            tenant_id=tenant_id(context),
            actor_user_id=context.user.id,
            provider="insurance",
            operation=payload.operation,
            status=result.status,
            external_reference=result.external_reference,
            request_digest=request_digest(payload.model_dump()),
            response_metadata={"record_count": imported},
        )
    )
    await db.commit()
    return {"status": result.status, **result.data}


@router.get("/patient/providers/availability")
async def provider_availability(
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    specialty: str | None = Query(default=None, max_length=150),
) -> list[dict[str, Any]]:
    query = (
        select(PortalRecord)
        .join(User, User.id == PortalRecord.owner_user_id)
        .where(
            User.account_type == AccountType.DOCTOR,
            PortalRecord.category == "schedule",
            PortalRecord.status == "available",
            PortalRecord.occurred_at >= datetime.now(UTC),
        )
        .order_by(PortalRecord.occurred_at)
        .limit(100)
    )
    slots = list((await db.scalars(query)).all())
    if specialty:
        slots = [
            slot
            for slot in slots
            if specialty.casefold() in str(slot.data.get("specialty", "")).casefold()
        ]
    return [
        {
            "id": str(slot.id),
            "provider": slot.title,
            "specialty": slot.data.get("specialty"),
            "location": slot.data.get("location"),
            "visit_type": slot.data.get("visit_type", "consultation"),
            "starts_at": slot.occurred_at,
            "fee_cents": slot.amount_cents or 0,
            "currency": slot.currency or "USD",
        }
        for slot in slots
    ]


@router.post(
    "/patient/appointments/book",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def book_appointment(
    payload: AppointmentBookingCreate,
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    slot = await db.scalar(
        select(PortalRecord)
        .join(User, User.id == PortalRecord.owner_user_id)
        .where(
            PortalRecord.id == payload.slot_id,
            PortalRecord.category == "schedule",
            PortalRecord.status == "available",
            User.account_type == AccountType.DOCTOR,
        )
        .with_for_update()
    )
    if slot is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This appointment slot is unavailable")
    slot.status = "booked"
    slot.patient_user_id = context.user.id
    appointment = PortalRecord(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=context.user.id,
        assigned_user_id=slot.owner_user_id,
        category="appointments",
        title=slot.title,
        status="scheduled",
        occurred_at=slot.occurred_at,
        amount_cents=slot.amount_cents,
        currency=slot.currency or "USD",
        data={
            "reason": payload.reason,
            "location": slot.data.get("location"),
            "visit_type": slot.data.get("visit_type"),
            "provider_slot_id": str(slot.id),
            "payment_id": str(payload.payment_id) if payload.payment_id else None,
        },
    )
    db.add(appointment)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="portal.appointment.booked",
            subject_user_id=context.user.id,
            event_data={"slot_id": str(slot.id), "appointment_id": str(appointment.id)},
        )
    )
    await db.commit()
    await db.refresh(appointment)
    return record_response(appointment)


@router.get("/patient/labs/availability")
async def lab_availability(
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    test_code: str | None = Query(default=None, max_length=100),
) -> list[dict[str, Any]]:
    query = (
        select(PortalRecord)
        .join(User, User.id == PortalRecord.owner_user_id)
        .where(
            User.account_type == AccountType.HOSPITAL,
            PortalRecord.category == "lab_slots",
            PortalRecord.status == "available",
            PortalRecord.occurred_at >= datetime.now(UTC),
        )
        .order_by(PortalRecord.occurred_at)
        .limit(100)
    )
    slots = list((await db.scalars(query)).all())
    if test_code:
        slots = [slot for slot in slots if slot.data.get("test_code") == test_code]
    return [
        {
            "id": str(slot.id),
            "laboratory": slot.title,
            "test_code": slot.data.get("test_code"),
            "test_name": slot.data.get("test_name"),
            "location": slot.data.get("location"),
            "starts_at": slot.occurred_at,
            "price_cents": slot.amount_cents or 0,
            "currency": slot.currency or "USD",
        }
        for slot in slots
    ]


@router.post(
    "/patient/labs/book",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def book_lab(
    payload: LabBookingCreate,
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    slot = await db.scalar(
        select(PortalRecord)
        .join(User, User.id == PortalRecord.owner_user_id)
        .where(
            PortalRecord.id == payload.slot_id,
            PortalRecord.category == "lab_slots",
            PortalRecord.status == "available",
            User.account_type == AccountType.HOSPITAL,
        )
        .with_for_update()
    )
    if slot is None or slot.data.get("test_code") != payload.test_code:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lab slot is unavailable")
    slot.status = "booked"
    slot.patient_user_id = context.user.id
    booking = PortalRecord(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=context.user.id,
        assigned_user_id=slot.owner_user_id,
        category="lab_bookings",
        title=str(slot.data.get("test_name") or slot.title),
        status="scheduled",
        occurred_at=slot.occurred_at,
        amount_cents=slot.amount_cents,
        currency=slot.currency or "USD",
        data={**slot.data, "lab_slot_id": str(slot.id)},
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return record_response(booking)


@router.get("/patient/insurance/marketplace")
async def policy_marketplace(
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    policies = list(
        (
            await db.scalars(
                select(PortalRecord)
                .join(User, User.id == PortalRecord.owner_user_id)
                .where(
                    User.account_type == AccountType.INSURANCE,
                    PortalRecord.category == "policies",
                    PortalRecord.status == "active",
                )
                .order_by(PortalRecord.amount_cents, PortalRecord.created_at.desc())
                .limit(200)
            )
        ).all()
    )
    history_records = list(
        (
            await db.scalars(
                select(PortalRecord).where(
                    PortalRecord.patient_user_id == context.user.id,
                    PortalRecord.category.in_(["medical_history", "allergies"]),
                    PortalRecord.status.in_(["active", "completed"]),
                )
            )
        ).all()
    )
    history_text = " ".join(
        str(value) for item in history_records for value in (item.title, *item.data.values())
    ).casefold()
    point_records = list(
        (
            await db.scalars(
                select(PortalRecord).where(
                    PortalRecord.patient_user_id == context.user.id,
                    PortalRecord.category == "loyalty_points",
                    PortalRecord.status == "active",
                )
            )
        ).all()
    )
    loyalty = sum(int(item.data.get("points", 0) or 0) for item in point_records)
    ranked: list[tuple[int, PortalRecord, list[str]]] = []
    for index, policy in enumerate(policies):
        excluded = _string_list(policy.data.get("excluded_conditions"))
        if any(term.casefold() in history_text for term in excluded):
            continue
        recommended = _string_list(policy.data.get("recommended_for"))
        matches = [term for term in recommended if term.casefold() in history_text]
        ranked.append((max(0, 100 - index + len(matches) * 10), policy, matches))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": str(policy.id),
            "payer": policy.data.get("payer", policy.title),
            "plan_name": policy.data.get("plan_name", policy.title),
            "coverage_type": policy.data.get("coverage_type"),
            "plain_language_coverage": policy.data.get("plain_language_coverage"),
            "monthly_premium_cents": policy.amount_cents,
            "currency": policy.currency or "USD",
            "loyalty_points_available": loyalty,
            "ranking_score": score,
            "match_reasons": matches,
            "disclaimer": "Coverage and premium are confirmed by the insurer at enrollment.",
        }
        for score, policy, matches in ranked
    ]


@router.post(
    "/patient/insurance/purchase",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def purchase_policy(
    payload: PolicyPurchaseCreate,
    context: Annotated[AuthContext, Depends(require_roles("patient"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecordResponse:
    policy = await db.scalar(
        select(PortalRecord)
        .join(User, User.id == PortalRecord.owner_user_id)
        .where(
            PortalRecord.id == payload.policy_id,
            PortalRecord.category == "policies",
            PortalRecord.status == "active",
            User.account_type == AccountType.INSURANCE,
        )
    )
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy offering was not found")
    active_policy = PortalRecord(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=context.user.id,
        assigned_user_id=policy.owner_user_id,
        category="insurance",
        title=str(policy.data.get("plan_name") or policy.title),
        status="pending_enrollment",
        external_reference=str(policy.id),
        amount_cents=policy.amount_cents,
        currency=policy.currency or "USD",
        data={
            **policy.data,
            "applicant_details": payload.applicant_details,
            "loyalty_points_used": payload.loyalty_points,
            "source_policy_id": str(policy.id),
            "plain_language_notice": (
                "Enrollment is pending insurer confirmation. Benefits are governed by the "
                "issued policy documents."
            ),
        },
    )
    db.add(active_policy)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="portal.policy.purchase_initiated",
            subject_user_id=context.user.id,
            event_data={"policy_id": str(policy.id), "enrollment_id": str(active_policy.id)},
        )
    )
    await db.commit()
    await db.refresh(active_policy)
    return record_response(active_policy)


@router.post("/payments/intents", dependencies=[Depends(enforce_csrf)])
async def payment_intent(
    payload: PaymentIntentCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_roles("patient", "hospital", "admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    key = request.headers.get("idempotency-key") or request_digest(
        (context.user.id, payload.model_dump())
    )
    result = await PaymentGateway(settings, request.app.state.http).create_intent(
        payload.amount_cents, payload.currency, payload.description, key
    )
    record = PortalRecord(
        tenant_id=tenant_id(context),
        owner_user_id=context.user.id,
        patient_user_id=context.user.id if context.user.account_type.value == "patient" else None,
        category="payments" if context.user.account_type.value == "patient" else "billing",
        title=payload.description,
        status=result.status,
        external_reference=result.external_reference,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper(),
        data={"claim_id": str(payload.claim_id) if payload.claim_id else None},
    )
    db.add(record)
    db.add(
        IntegrationEvent(
            tenant_id=tenant_id(context),
            actor_user_id=context.user.id,
            provider=result.provider,
            operation="create_payment_intent",
            status=result.status,
            external_reference=result.external_reference,
            request_digest=key,
            response_metadata={"amount_cents": payload.amount_cents, "currency": payload.currency},
        )
    )
    await db.commit()
    return {
        "status": result.status,
        "payment_id": str(record.id),
        "external_reference": result.external_reference,
        **result.data,
    }


@router.post("/webhooks/payments", include_in_schema=False)
async def payment_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    secret = settings.stripe_webhook_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Payment webhook is not configured"
        )
    parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
    timestamp = parts.get("t", "")
    supplied = parts.get("v1", "")
    try:
        fresh = abs(int(time.time()) - int(timestamp)) <= 300
    except ValueError:
        fresh = False
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    if not fresh or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payment signature")
    event = json.loads(payload)
    intent = event.get("data", {}).get("object", {})
    reference = str(intent.get("id", ""))
    record = await db.scalar(
        select(PortalRecord).where(
            PortalRecord.external_reference == reference,
            PortalRecord.category.in_(["payments", "billing"]),
        )
    )
    if record:
        record.status = str(intent.get("status", event.get("type", "updated")))[:64]
        record.data = {**record.data, "payment_event": str(event.get("type", ""))}
        await db.commit()
    return {"received": True}


@router.get("/admin/users")
async def admin_users(
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    users = (await db.scalars(select(User).order_by(User.created_at.desc()).limit(500))).all()
    return [
        {
            "id": str(item.id),
            "email": item.email,
            "account_type": item.account_type.value,
            "status": item.status.value,
            "email_verified": item.email_verified,
            "phone_verified": item.phone_verified,
            "created_at": item.created_at.isoformat(),
        }
        for item in users
    ]


@router.patch("/admin/users/{user_id}", dependencies=[Depends(enforce_csrf)])
async def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdate,
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == context.user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot change your own status")
    user.status = UserStatus(payload.status)
    if user.status == UserStatus.ACTIVE:
        if user.doctor_profile:
            user.doctor_profile.credentials_verified = True
        if user.organization_profile:
            user.organization_profile.credentials_verified = True
    user.token_version += 1
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="admin.user_status_changed",
            subject_user_id=user.id,
            event_data={
                "status": payload.status,
                "credentials_verified": payload.status == UserStatus.ACTIVE.value,
            },
        )
    )
    await db.commit()
    return {"id": str(user.id), "status": user.status.value}


@router.get("/admin/audit")
async def admin_audit(
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    items = (
        await db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500))
    ).all()
    return [
        {
            "id": str(item.id),
            "event_type": item.event_type,
            "actor_user_id": str(item.actor_user_id) if item.actor_user_id else None,
            "subject_user_id": str(item.subject_user_id) if item.subject_user_id else None,
            "event_data": item.event_data,
            "previous_hash": item.previous_hash,
            "event_hash": item.event_hash,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.get("/admin/monitoring")
async def monitoring(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    counts = {
        "users": int(await db.scalar(select(func.count()).select_from(User)) or 0),
        "records": int(await db.scalar(select(func.count()).select_from(PortalRecord)) or 0),
        "documents": int(await db.scalar(select(func.count()).select_from(DocumentAsset)) or 0),
        "integration_events": int(
            await db.scalar(select(func.count()).select_from(IntegrationEvent)) or 0
        ),
    }
    return {
        "status": "operational",
        "database": "ok",
        "redis": "ok" if await request.app.state.redis.ping() else "unavailable",
        "counts": counts,
    }


@router.get("/admin/settings")
async def settings_list(
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    items = (await db.scalars(select(SystemSetting).order_by(SystemSetting.key))).all()
    return [
        {
            "key": item.key,
            "value": item.value,
            "description": item.description,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in items
    ]


@router.put("/admin/settings/{key}", dependencies=[Depends(enforce_csrf)])
async def setting_update(
    key: str,
    payload: SettingUpdate,
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    item = await db.get(SystemSetting, key)
    if item is None:
        item = SystemSetting(
            key=key[:100],
            value=payload.value,
            description=payload.description,
            updated_by_user_id=context.user.id,
        )
        db.add(item)
    else:
        item.value = payload.value
        item.description = payload.description
        item.updated_by_user_id = context.user.id
    await db.commit()
    return {"key": item.key, "value": item.value}
