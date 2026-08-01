"""Scheduling domain: availability search, booking, payment, telehealth, schedules.

The booking path is the only place in the product where two patients can collide
on the same resource, so it is defended three times over:

* ``SELECT ... FOR UPDATE`` on the slot row serialises concurrent bookers,
* ``booked_count < capacity`` is re-checked while holding that lock,
* ``ix_appointment_slot_booked`` (partial unique on ``slot_id`` for the live
  statuses) is the database's own last word, surfaced here as a clean 409.

Slots, invoices and the service catalogue are *operational* tables and are
tenant scoped. Appointments carry PHI, so every read of one is written to
``phi_access_events`` in the same transaction as the read.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from pydantic import Field, model_validator
from sqlalchemy import Date, Select, Table, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccountType,
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    AppointmentStatusEvent,
    DoctorProfile,
    Encounter,
    EncounterChannel,
    EncounterClass,
    EncounterStatus,
    IdempotencyRecord,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Organization,
    PatientProfile,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PractitionerRole,
    ProvenanceSource,
    ProviderSchedule,
    ServiceItem,
    SlotStatus,
    TelehealthSession,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    assert_transition,
    conflict,
    discovery_predicate,
    forbidden,
    is_admin,
    is_patient,
    not_found,
    paginate,
    record_phi_access,
    record_phi_access_many,
    tenant_scoped,
    unprocessable,
    write_audit,
)

#: Chargemaster code used to price a consultation when the slot carries no price.
CONSULTATION_SERVICE_CODE = "CONSULT"
#: Widest window a single generate-slots call may expand.
SLOT_GENERATION_MAX_DAYS = 92
#: How long a replayed Idempotency-Key keeps returning the stored response.
IDEMPOTENCY_TTL_HOURS = 24
BOOKING_OPERATION = "scheduling.book_appointment"

APPOINTMENT_TRANSITIONS: dict[str, set[str]] = {
    AppointmentStatus.REQUESTED.value: {"pending-payment", "confirmed", "cancelled"},
    AppointmentStatus.PENDING_PAYMENT.value: {"confirmed", "cancelled"},
    AppointmentStatus.CONFIRMED.value: {"checked-in", "cancelled", "no-show"},
    AppointmentStatus.CHECKED_IN.value: {"fulfilled", "cancelled"},
    AppointmentStatus.FULFILLED.value: set(),
    AppointmentStatus.CANCELLED.value: set(),
    AppointmentStatus.NO_SHOW.value: set(),
}

#: Statuses from which an appointment may still be moved to another slot.
RESCHEDULABLE_STATUSES = frozenset(
    {
        AppointmentStatus.REQUESTED,
        AppointmentStatus.PENDING_PAYMENT,
        AppointmentStatus.CONFIRMED,
    }
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AvailabilitySlot(DomainModel):
    """One bookable opening, priced and attributed to a named provider."""

    slot_id: UUID
    provider_user_id: UUID
    provider_name: str
    specialty: str | None
    specialty_code: str | None
    organization_id: UUID
    organization_name: str
    department_id: UUID | None
    start_at: datetime
    end_at: datetime
    channel: EncounterChannel
    capacity: int
    booked_count: int
    remaining: int
    fee_cents: int | None
    currency: str | None


class InvoiceSummary(DomainModel):
    id: UUID
    invoice_number: str
    status: InvoiceStatus
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    balance_cents: int
    currency: str
    issued_at: datetime | None
    due_at: datetime | None


class AppointmentResponse(DomainModel):
    id: UUID
    slot_id: UUID
    patient_user_id: UUID
    patient_name: str | None = None
    provider_user_id: UUID
    provider_name: str | None = None
    organization_id: UUID
    encounter_id: UUID | None
    referral_id: UUID | None
    reason: str | None
    channel: EncounterChannel
    status: AppointmentStatus
    payment_status: str
    invoice_id: UUID | None
    cancellation_reason: str | None
    start_at: datetime
    end_at: datetime
    booked_at: datetime
    created_at: datetime
    updated_at: datetime


class AppointmentCreate(DomainModel):
    slot_id: UUID
    patient_user_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)
    referral_id: UUID | None = None
    service_code: str | None = Field(default=None, max_length=64)
    channel: EncounterChannel | None = None


class BookingResponse(DomainModel):
    appointment: AppointmentResponse
    invoice: InvoiceSummary


class PaymentCreate(DomainModel):
    method: PaymentMethod = PaymentMethod.CARD
    amount_cents: int | None = Field(default=None, ge=1)
    processor: str = Field(default="internal", max_length=32)
    processor_intent_id: str | None = Field(default=None, max_length=255)
    processor_charge_id: str | None = Field(default=None, max_length=255)
    capture: bool = True
    idempotency_key: str | None = Field(default=None, max_length=255)


class PaymentResponse(DomainModel):
    id: UUID
    invoice_id: UUID
    appointment_id: UUID | None
    payer_user_id: UUID
    method: PaymentMethod
    amount_cents: int
    currency: str
    status: PaymentStatus
    processor: str
    processor_intent_id: str | None
    idempotency_key: str
    authorized_at: datetime | None
    captured_at: datetime | None
    appointment_payment_status: str
    invoice: InvoiceSummary


class CancelRequest(DomainModel):
    reason: str | None = Field(default=None, max_length=255)


class RescheduleRequest(DomainModel):
    slot_id: UUID
    reason: str | None = Field(default=None, max_length=255)


class TelehealthCreate(DomainModel):
    recording_consent: bool = False
    licensure_state: str | None = Field(default=None, max_length=8)


class TelehealthSessionResponse(DomainModel):
    """Join details. ``join_token`` is returned once; only its hash is stored."""

    id: UUID
    appointment_id: UUID
    encounter_id: UUID | None
    provider_room_id: str
    join_token: str
    join_url: str
    started_at: datetime | None
    ended_at: datetime | None
    participants: list[dict[str, Any]]
    recording_consent: bool
    licensure_state: str | None
    licensure_verified: bool


class ProviderScheduleCreate(DomainModel):
    provider_user_id: UUID
    organization_id: UUID | None = None
    department_id: UUID | None = None
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time
    slot_minutes: int = Field(default=30, ge=5, le=480)
    timezone: str = Field(min_length=1, max_length=64)
    channel: EncounterChannel = EncounterChannel.IN_PERSON
    valid_from: date
    valid_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _check_period(self) -> ProviderScheduleCreate:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        return self


class ProviderScheduleResponse(DomainModel):
    id: UUID
    provider_user_id: UUID
    provider_name: str | None = None
    organization_id: UUID
    department_id: UUID | None
    day_of_week: int
    start_time: time
    end_time: time
    slot_minutes: int
    timezone: str
    channel: EncounterChannel
    valid_from: date
    valid_to: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SlotGenerationRequest(DomainModel):
    from_date: date
    to_date: date
    capacity: int = Field(default=1, ge=1, le=100)
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def _check_window(self) -> SlotGenerationRequest:
        if self.to_date < self.from_date:
            raise ValueError("to_date must not precede from_date")
        if (self.to_date - self.from_date).days + 1 > SLOT_GENERATION_MAX_DAYS:
            raise ValueError(f"window may not exceed {SLOT_GENERATION_MAX_DAYS} days")
        if self.price_cents is not None and self.currency is None:
            raise ValueError("currency is required when price_cents is set")
        return self


class SlotGenerationResult(DomainModel):
    schedule_id: UUID
    from_date: date
    to_date: date
    created: int
    skipped: int
    slot_ids: list[UUID]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _provider_name(first_name: str | None, last_name: str | None) -> str:
    parts = [part for part in (first_name, last_name) if part]
    return f"Dr. {' '.join(parts)}" if parts else "Unknown provider"


def _person_name(first_name: str | None, last_name: str | None) -> str | None:
    parts = [part for part in (first_name, last_name) if part]
    return " ".join(parts) if parts else None


def _invoice_summary(invoice: Invoice) -> InvoiceSummary:
    return InvoiceSummary(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        total_cents=invoice.total_cents,
        balance_cents=invoice.balance_cents,
        currency=invoice.currency,
        issued_at=invoice.issued_at,
        due_at=invoice.due_at,
    )


def _appointment_response(
    appointment: Appointment,
    slot: AppointmentSlot,
    *,
    provider_name: str | None = None,
    patient_name: str | None = None,
) -> AppointmentResponse:
    return AppointmentResponse(
        id=appointment.id,
        slot_id=appointment.slot_id,
        patient_user_id=appointment.patient_user_id,
        patient_name=patient_name,
        provider_user_id=appointment.provider_user_id,
        provider_name=provider_name,
        organization_id=appointment.organization_id,
        encounter_id=appointment.encounter_id,
        referral_id=appointment.referral_id,
        reason=appointment.reason,
        channel=appointment.channel,
        status=appointment.status,
        payment_status=appointment.payment_status,
        invoice_id=appointment.invoice_id,
        cancellation_reason=appointment.cancellation_reason,
        start_at=slot.start_at,
        end_at=slot.end_at,
        booked_at=appointment.booked_at,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


def _schedule_response(
    schedule: ProviderSchedule, provider_name: str | None = None
) -> ProviderScheduleResponse:
    return ProviderScheduleResponse(
        id=schedule.id,
        provider_user_id=schedule.provider_user_id,
        provider_name=provider_name,
        organization_id=schedule.organization_id,
        department_id=schedule.department_id,
        day_of_week=schedule.day_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        slot_minutes=schedule.slot_minutes,
        timezone=schedule.timezone,
        channel=schedule.channel,
        valid_from=schedule.valid_from,
        valid_to=schedule.valid_to,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def _is_org_staff(context: AuthContext, organization_id: UUID) -> bool:
    return context.tenant_id == organization_id and context.user.account_type in {
        AccountType.HOSPITAL,
        AccountType.DOCTOR,
    }


def _authorize_appointment(context: AuthContext, appointment: Appointment) -> None:
    """Patient, treating provider, the treating organization, or an admin."""
    if is_admin(context):
        return
    if context.user.id in (appointment.patient_user_id, appointment.provider_user_id):
        return
    if _is_org_staff(context, appointment.organization_id):
        return
    raise forbidden("You may not access this appointment")


def _resolve_patient(context: AuthContext, requested: UUID | None) -> UUID:
    if is_patient(context):
        if requested is not None and requested != context.user.id:
            raise forbidden("Patients may only book for themselves")
        return context.user.id
    if requested is None:
        raise unprocessable("patient_user_id is required when booking on behalf of a patient")
    return requested


async def _load_slot_for_update(
    db: AsyncSession, context: AuthContext, slot_id: UUID
) -> AppointmentSlot:
    slot = await db.scalar(
        select(AppointmentSlot).where(AppointmentSlot.id == slot_id).with_for_update()
    )
    if slot is None:
        raise not_found("Appointment slot")
    if not is_admin(context) and slot.tenant_id != context.tenant_id and not is_patient(context):
        raise not_found("Appointment slot")
    return slot


def _assert_slot_bookable(slot: AppointmentSlot, now: datetime) -> None:
    if slot.status != SlotStatus.OPEN:
        raise conflict(f"Slot is '{slot.status.value}', not open for booking")
    if slot.booked_count >= slot.capacity:
        raise conflict("Slot is already at capacity")
    if slot.start_at <= now:
        raise conflict("Slot start time has already passed")


def _take_slot(slot: AppointmentSlot) -> None:
    """Consume one seat, closing the slot when the last seat goes."""
    slot.booked_count += 1
    if slot.booked_count >= slot.capacity:
        slot.status = SlotStatus.BOOKED


def _release_slot(slot: AppointmentSlot, now: datetime) -> None:
    """Give a seat back, reopening a future slot that was closed by a booking."""
    slot.booked_count = max(0, slot.booked_count - 1)
    if (
        slot.status in {SlotStatus.BOOKED, SlotStatus.HELD}
        and slot.booked_count < slot.capacity
        and slot.start_at > now
    ):
        slot.status = SlotStatus.OPEN


def _status_event(
    appointment: Appointment,
    context: AuthContext,
    *,
    from_status: str | None,
    to_status: str,
    reason: str | None = None,
) -> AppointmentStatusEvent:
    return AppointmentStatusEvent(
        tenant_id=appointment.tenant_id,
        appointment_id=appointment.id,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=context.user.id,
        reason=reason,
    )


async def _consultation_service_item(
    db: AsyncSession, *, organization_id: UUID, service_code: str, on_day: date
) -> ServiceItem | None:
    item: ServiceItem | None = await db.scalar(
        select(ServiceItem)
        .where(
            ServiceItem.organization_id == organization_id,
            ServiceItem.service_code == service_code,
            ServiceItem.is_active.is_(True),
            ServiceItem.effective_from <= on_day,
            or_(ServiceItem.effective_to.is_(None), ServiceItem.effective_to >= on_day),
        )
        .order_by(ServiceItem.effective_from.desc())
        .limit(1)
    )
    return item


def _next_invoice_number(now: datetime) -> str:
    return f"INV-{now:%Y%m%d}-{uuid4().hex[:12].upper()}"


async def _idempotent_lookup(
    db: AsyncSession, context: AuthContext, *, operation: str, key: str, digest: str
) -> dict[str, Any] | None:
    """Return the stored response for a replayed key, or claim the key."""
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == context.tenant_id,
            IdempotencyRecord.actor_user_id == context.user.id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise conflict("Idempotency-Key was already used with a different payload")
        if existing.response_body is None:
            raise conflict("A request with this Idempotency-Key is still in flight")
        return existing.response_body

    record = IdempotencyRecord(
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        operation=operation,
        key=key,
        request_digest=digest,
        expires_at=_now() + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
    )
    try:
        async with db.begin_nested():
            db.add(record)
            await db.flush()
    except IntegrityError as exc:
        raise conflict("A request with this Idempotency-Key is still in flight") from exc
    return None


async def _idempotent_store(
    db: AsyncSession,
    context: AuthContext,
    *,
    operation: str,
    key: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    record = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == context.tenant_id,
            IdempotencyRecord.actor_user_id == context.user.id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if record is not None:
        record.response_status = status_code
        record.response_body = body


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def search_availability(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    specialty: str | None = None,
    organization_id: UUID | None = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    mode: EncounterChannel | None = None,
) -> Page[AvailabilitySlot]:
    """Real-time openings, priced, in a single round trip.

    The predicate ``status = 'open'`` matches the ``ix_slot_open`` partial index;
    ``booked_count < capacity`` then filters oversubscribed multi-seat slots.
    Provider role and chargemaster price are pulled through LATERAL joins so a
    provider holding several roles cannot fan the slot list out.
    """
    now = _now()
    window_start = start_from if start_from is not None else now

    slot_day = AppointmentSlot.start_at.cast(Date)
    role_lateral = (
        select(
            PractitionerRole.specialty_code.label("specialty_code"),
            PractitionerRole.department_id.label("department_id"),
        )
        .where(
            PractitionerRole.practitioner_user_id == AppointmentSlot.provider_user_id,
            PractitionerRole.organization_id == AppointmentSlot.organization_id,
            PractitionerRole.is_active.is_(True),
            PractitionerRole.credentialing_status == "active",
        )
        .order_by(
            PractitionerRole.accepts_new_patients.desc(),
            PractitionerRole.created_at.asc(),
        )
        .limit(1)
        .lateral("provider_role")
    )
    fee_lateral = (
        select(
            ServiceItem.base_price_cents.label("base_price_cents"),
            ServiceItem.currency.label("fee_currency"),
        )
        .where(
            ServiceItem.organization_id == AppointmentSlot.organization_id,
            ServiceItem.service_code == CONSULTATION_SERVICE_CODE,
            ServiceItem.is_active.is_(True),
            ServiceItem.effective_from <= slot_day,
            or_(ServiceItem.effective_to.is_(None), ServiceItem.effective_to >= slot_day),
        )
        .order_by(ServiceItem.effective_from.desc())
        .limit(1)
        .lateral("consultation_fee")
    )

    stmt = (
        select(
            AppointmentSlot.id.label("slot_id"),
            AppointmentSlot.provider_user_id.label("provider_user_id"),
            AppointmentSlot.organization_id.label("organization_id"),
            AppointmentSlot.start_at.label("start_at"),
            AppointmentSlot.end_at.label("end_at"),
            AppointmentSlot.channel.label("channel"),
            AppointmentSlot.capacity.label("capacity"),
            AppointmentSlot.booked_count.label("booked_count"),
            DoctorProfile.first_name.label("first_name"),
            DoctorProfile.last_name.label("last_name"),
            DoctorProfile.specialty.label("specialty"),
            Organization.legal_name.label("organization_name"),
            role_lateral.c.specialty_code.label("specialty_code"),
            role_lateral.c.department_id.label("department_id"),
            func.coalesce(AppointmentSlot.price_cents, fee_lateral.c.base_price_cents).label(
                "fee_cents"
            ),
            func.coalesce(AppointmentSlot.currency, fee_lateral.c.fee_currency).label("currency"),
        )
        .select_from(AppointmentSlot)
        .join(DoctorProfile, DoctorProfile.user_id == AppointmentSlot.provider_user_id)
        .join(Organization, Organization.id == AppointmentSlot.organization_id)
        .outerjoin(role_lateral, true())
        .outerjoin(fee_lateral, true())
        .where(
            AppointmentSlot.status == SlotStatus.OPEN,
            AppointmentSlot.booked_count < AppointmentSlot.capacity,
            AppointmentSlot.start_at >= window_start,
        )
    )
    # Discovery, not management: a patient must be able to find open capacity at
    # ANY organization, so this is deliberately cross-tenant for patients and
    # admins. Providers and hospitals stay scoped to the capacity they own.
    slot_scope = discovery_predicate(AppointmentSlot, context)
    if slot_scope is not None:
        stmt = stmt.where(slot_scope)
    if start_to is not None:
        stmt = stmt.where(AppointmentSlot.start_at <= start_to)
    if organization_id is not None:
        stmt = stmt.where(AppointmentSlot.organization_id == organization_id)
    if mode is not None:
        stmt = stmt.where(AppointmentSlot.channel == mode)
    if specialty:
        needle = specialty.strip()
        role_match = (
            select(PractitionerRole.id)
            .where(
                PractitionerRole.practitioner_user_id == AppointmentSlot.provider_user_id,
                PractitionerRole.organization_id == AppointmentSlot.organization_id,
                PractitionerRole.is_active.is_(True),
                func.lower(PractitionerRole.specialty_code) == needle.lower(),
            )
            .exists()
        )
        stmt = stmt.where(or_(DoctorProfile.specialty.ilike(f"%{needle}%"), role_match))

    stmt = (
        stmt.order_by(AppointmentSlot.start_at.asc(), AppointmentSlot.id.asc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )

    rows = (await db.execute(stmt)).all()
    items = [
        AvailabilitySlot(
            slot_id=row.slot_id,
            provider_user_id=row.provider_user_id,
            provider_name=_provider_name(row.first_name, row.last_name),
            specialty=row.specialty,
            specialty_code=row.specialty_code,
            organization_id=row.organization_id,
            organization_name=row.organization_name,
            department_id=row.department_id,
            start_at=row.start_at,
            end_at=row.end_at,
            channel=row.channel,
            capacity=row.capacity,
            booked_count=row.booked_count,
            remaining=max(0, row.capacity - row.booked_count),
            fee_cents=row.fee_cents,
            currency=row.currency,
        )
        for row in rows
    ]
    return paginate(items, page)


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


async def book_appointment(
    db: AsyncSession,
    context: AuthContext,
    payload: AppointmentCreate,
    *,
    idempotency_key: str | None,
    request: Request | None = None,
) -> BookingResponse:
    """Race-safe booking plus the consultation invoice, in one transaction."""
    now = _now()
    patient_user_id = _resolve_patient(context, payload.patient_user_id)
    body = payload.model_dump(mode="json")
    body["patient_user_id"] = str(patient_user_id)
    digest = _digest(body)

    if idempotency_key:
        stored = await _idempotent_lookup(
            db, context, operation=BOOKING_OPERATION, key=idempotency_key, digest=digest
        )
        if stored is not None:
            return BookingResponse.model_validate(stored)

    slot = await _load_slot_for_update(db, context, payload.slot_id)
    _assert_slot_bookable(slot, now)
    if payload.channel is not None and payload.channel != slot.channel:
        raise unprocessable(f"Slot is a '{slot.channel.value}' slot")

    patient = await db.get(PatientProfile, patient_user_id)
    if patient is None:
        raise not_found("Patient")
    provider = await db.get(DoctorProfile, slot.provider_user_id)
    if provider is None:
        raise not_found("Provider")

    appointment = Appointment(
        tenant_id=slot.tenant_id,
        slot_id=slot.id,
        patient_user_id=patient_user_id,
        provider_user_id=slot.provider_user_id,
        organization_id=slot.organization_id,
        referral_id=payload.referral_id,
        reason=payload.reason,
        channel=slot.channel,
        status=AppointmentStatus.CONFIRMED,
        payment_status="unpaid",
        booked_at=now,
    )
    db.add(appointment)
    try:
        await db.flush()
    except IntegrityError as exc:
        # ix_appointment_slot_booked fired: someone else won the slot.
        await db.rollback()
        raise conflict("This slot has already been booked") from exc

    _take_slot(slot)
    db.add(
        _status_event(
            appointment,
            context,
            from_status=None,
            to_status=AppointmentStatus.CONFIRMED.value,
            reason=payload.reason[:255] if payload.reason else None,
        )
    )

    invoice = await _create_consultation_invoice(
        db,
        slot=slot,
        appointment=appointment,
        provider=provider,
        service_code=payload.service_code or CONSULTATION_SERVICE_CODE,
        now=now,
    )
    appointment.invoice_id = invoice.id

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="appointment",
        resource_id=appointment.id,
        purpose_of_use="TREAT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="scheduling.appointment.booked",
        subject_user_id=patient_user_id,
        resource_id=appointment.id,
        event_data={
            "slot_id": str(slot.id),
            "provider_user_id": str(slot.provider_user_id),
            "organization_id": str(slot.organization_id),
            "channel": slot.channel.value,
            "invoice_id": str(invoice.id),
        },
        request=request,
    )

    response = BookingResponse(
        appointment=_appointment_response(
            appointment,
            slot,
            provider_name=_provider_name(provider.first_name, provider.last_name),
            patient_name=_person_name(patient.first_name, patient.last_name),
        ),
        invoice=_invoice_summary(invoice),
    )
    if idempotency_key:
        await _idempotent_store(
            db,
            context,
            operation=BOOKING_OPERATION,
            key=idempotency_key,
            status_code=201,
            body=response.model_dump(mode="json"),
        )
    await db.commit()
    return response


async def _create_consultation_invoice(
    db: AsyncSession,
    *,
    slot: AppointmentSlot,
    appointment: Appointment,
    provider: DoctorProfile,
    service_code: str,
    now: datetime,
) -> Invoice:
    """Price the consultation from the slot, falling back to the chargemaster."""
    service_item: ServiceItem | None = None
    if slot.price_cents is not None and slot.currency is not None:
        fee_cents = slot.price_cents
        currency = slot.currency
    else:
        service_item = await _consultation_service_item(
            db,
            organization_id=slot.organization_id,
            service_code=service_code,
            on_day=slot.start_at.date(),
        )
        if service_item is None:
            raise unprocessable("No consultation price is configured for this slot or organization")
        fee_cents = service_item.base_price_cents
        currency = service_item.currency

    invoice = Invoice(
        tenant_id=slot.tenant_id,
        invoice_number=_next_invoice_number(now),
        payer_user_id=appointment.patient_user_id,
        patient_user_id=appointment.patient_user_id,
        organization_id=slot.organization_id,
        appointment_id=appointment.id,
        status=InvoiceStatus.ISSUED,
        subtotal_cents=fee_cents,
        tax_cents=0,
        total_cents=fee_cents,
        balance_cents=fee_cents,
        currency=currency,
        issued_at=now,
        due_at=min(slot.start_at, now + timedelta(days=7)),
    )
    db.add(invoice)
    await db.flush()

    description = f"Consultation with {_provider_name(provider.first_name, provider.last_name)}"
    db.add(
        InvoiceLine(
            invoice_id=invoice.id,
            service_item_id=service_item.id if service_item else None,
            service_code_system=service_item.service_code_system if service_item else None,
            service_code=service_item.service_code if service_item else service_code,
            service_display=service_item.service_display if service_item else description[:255],
            description=description[:500],
            quantity=1,
            unit_price_cents=fee_cents,
            amount_cents=fee_cents,
            line_number=1,
        )
    )
    await db.flush()
    return invoice


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


async def pay_appointment(
    db: AsyncSession,
    context: AuthContext,
    appointment_id: UUID,
    payload: PaymentCreate,
    *,
    idempotency_key: str | None,
    request: Request | None = None,
) -> PaymentResponse:
    """Authorize or capture the consultation fee. Idempotent on the payment key."""
    now = _now()
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise not_found("Appointment")
    _authorize_appointment(context, appointment)
    if appointment.invoice_id is None:
        raise unprocessable("This appointment has no invoice to pay")

    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == appointment.invoice_id).with_for_update()
    )
    if invoice is None:
        raise not_found("Invoice")

    key = payload.idempotency_key or idempotency_key or f"appointment-pay:{appointment.id}"
    existing = await db.scalar(
        select(Payment).where(
            Payment.tenant_id == appointment.tenant_id,
            Payment.idempotency_key == key,
        )
    )
    if existing is not None:
        await record_phi_access(
            db,
            context,
            patient_user_id=appointment.patient_user_id,
            resource_type="payment",
            resource_id=existing.id,
            purpose_of_use="HPAYMT",
            request=request,
            result_count=1,
        )
        await db.commit()
        return PaymentResponse(
            id=existing.id,
            invoice_id=existing.invoice_id,
            appointment_id=existing.appointment_id,
            payer_user_id=existing.payer_user_id,
            method=existing.method,
            amount_cents=existing.amount_cents,
            currency=existing.currency,
            status=existing.status,
            processor=existing.processor,
            processor_intent_id=existing.processor_intent_id,
            idempotency_key=existing.idempotency_key,
            authorized_at=existing.authorized_at,
            captured_at=existing.captured_at,
            appointment_payment_status=appointment.payment_status,
            invoice=_invoice_summary(invoice),
        )

    if invoice.status in {InvoiceStatus.VOID, InvoiceStatus.REFUNDED}:
        raise conflict(f"Invoice is '{invoice.status.value}' and cannot be paid")
    if invoice.balance_cents <= 0:
        raise conflict("Invoice is already settled")
    amount_cents = payload.amount_cents or invoice.balance_cents
    if amount_cents > invoice.balance_cents:
        raise unprocessable("Payment exceeds the outstanding invoice balance")

    payment = Payment(
        tenant_id=appointment.tenant_id,
        invoice_id=invoice.id,
        appointment_id=appointment.id,
        payer_user_id=invoice.payer_user_id,
        method=payload.method,
        amount_cents=amount_cents,
        currency=invoice.currency,
        status=PaymentStatus.CAPTURED if payload.capture else PaymentStatus.AUTHORIZED,
        processor=payload.processor,
        processor_intent_id=payload.processor_intent_id,
        processor_charge_id=payload.processor_charge_id if payload.capture else None,
        idempotency_key=key,
        authorized_at=now,
        captured_at=now if payload.capture else None,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("A payment with this idempotency key already exists") from exc

    if payload.capture:
        invoice.balance_cents = max(0, invoice.balance_cents - amount_cents)
        if invoice.balance_cents == 0:
            invoice.status = InvoiceStatus.PAID
            appointment.payment_status = "paid"
    else:
        appointment.payment_status = "authorized"

    await record_phi_access(
        db,
        context,
        patient_user_id=appointment.patient_user_id,
        resource_type="payment",
        resource_id=payment.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="scheduling.appointment.paid",
        subject_user_id=appointment.patient_user_id,
        resource_id=payment.id,
        event_data={
            "appointment_id": str(appointment.id),
            "invoice_id": str(invoice.id),
            "amount_cents": amount_cents,
            "currency": invoice.currency,
            "captured": payload.capture,
        },
        request=request,
    )
    await db.commit()
    return PaymentResponse(
        id=payment.id,
        invoice_id=payment.invoice_id,
        appointment_id=payment.appointment_id,
        payer_user_id=payment.payer_user_id,
        method=payment.method,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        status=payment.status,
        processor=payment.processor,
        processor_intent_id=payment.processor_intent_id,
        idempotency_key=payment.idempotency_key,
        authorized_at=payment.authorized_at,
        captured_at=payment.captured_at,
        appointment_payment_status=appointment.payment_status,
        invoice=_invoice_summary(invoice),
    )


# ---------------------------------------------------------------------------
# Cancel / reschedule
# ---------------------------------------------------------------------------


async def cancel_appointment(
    db: AsyncSession,
    context: AuthContext,
    appointment_id: UUID,
    payload: CancelRequest,
    *,
    request: Request | None = None,
) -> AppointmentResponse:
    now = _now()
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise not_found("Appointment")
    _authorize_appointment(context, appointment)

    previous = appointment.status
    assert_transition(previous.value, AppointmentStatus.CANCELLED.value, APPOINTMENT_TRANSITIONS)

    slot = await _load_slot_for_update(db, context, appointment.slot_id)
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = payload.reason
    appointment.cancelled_by_user_id = context.user.id
    _release_slot(slot, now)

    db.add(
        _status_event(
            appointment,
            context,
            from_status=previous.value,
            to_status=AppointmentStatus.CANCELLED.value,
            reason=payload.reason,
        )
    )

    if appointment.invoice_id is not None:
        invoice = await db.get(Invoice, appointment.invoice_id)
        if invoice is not None and invoice.status in {InvoiceStatus.DRAFT, InvoiceStatus.ISSUED}:
            invoice.status = InvoiceStatus.VOID
            invoice.balance_cents = 0

    await record_phi_access(
        db,
        context,
        patient_user_id=appointment.patient_user_id,
        resource_type="appointment",
        resource_id=appointment.id,
        purpose_of_use="TREAT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="scheduling.appointment.cancelled",
        subject_user_id=appointment.patient_user_id,
        resource_id=appointment.id,
        event_data={"from_status": previous.value, "reason": payload.reason},
        request=request,
    )
    await db.commit()
    return _appointment_response(appointment, slot)


async def reschedule_appointment(
    db: AsyncSession,
    context: AuthContext,
    appointment_id: UUID,
    payload: RescheduleRequest,
    *,
    request: Request | None = None,
) -> AppointmentResponse:
    """Move an appointment to another slot, freeing the old seat atomically."""
    now = _now()
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise not_found("Appointment")
    _authorize_appointment(context, appointment)
    if appointment.status not in RESCHEDULABLE_STATUSES:
        raise conflict(f"Cannot reschedule an appointment that is '{appointment.status.value}'")
    if payload.slot_id == appointment.slot_id:
        raise unprocessable("The appointment is already on that slot")

    # Lock both slots in a stable order so two mirrored reschedules cannot deadlock.
    locked = (
        await db.scalars(
            select(AppointmentSlot)
            .where(AppointmentSlot.id.in_([appointment.slot_id, payload.slot_id]))
            .order_by(AppointmentSlot.id.asc())
            .with_for_update()
        )
    ).all()
    slots = {slot.id: slot for slot in locked}
    old_slot = slots.get(appointment.slot_id)
    new_slot = slots.get(payload.slot_id)
    if old_slot is None or new_slot is None:
        raise not_found("Appointment slot")
    if (
        not is_admin(context)
        and not is_patient(context)
        and new_slot.tenant_id != context.tenant_id
    ):
        raise not_found("Appointment slot")
    _assert_slot_bookable(new_slot, now)

    appointment.slot_id = new_slot.id
    appointment.provider_user_id = new_slot.provider_user_id
    appointment.organization_id = new_slot.organization_id
    appointment.channel = new_slot.channel
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("The requested slot has already been booked") from exc

    _release_slot(old_slot, now)
    _take_slot(new_slot)

    reason = payload.reason or f"rescheduled to {new_slot.start_at.isoformat()}"
    db.add(
        _status_event(
            appointment,
            context,
            from_status=appointment.status.value,
            to_status=appointment.status.value,
            reason=reason[:255],
        )
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=appointment.patient_user_id,
        resource_type="appointment",
        resource_id=appointment.id,
        purpose_of_use="TREAT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="scheduling.appointment.rescheduled",
        subject_user_id=appointment.patient_user_id,
        resource_id=appointment.id,
        event_data={
            "from_slot_id": str(old_slot.id),
            "to_slot_id": str(new_slot.id),
            "start_at": new_slot.start_at.isoformat(),
        },
        request=request,
    )
    await db.commit()
    return _appointment_response(appointment, new_slot)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _role_scoped_appointments(
    stmt: Select[tuple[Any, ...]], context: AuthContext
) -> Select[tuple[Any, ...]]:
    """A patient sees their own, a doctor their panel, an organization its own."""
    if is_admin(context):
        return stmt
    if is_patient(context):
        return stmt.where(Appointment.patient_user_id == context.user.id)
    if context.user.account_type == AccountType.DOCTOR:
        return stmt.where(Appointment.provider_user_id == context.user.id)
    return stmt.where(Appointment.organization_id == context.tenant_id)


async def list_appointments(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status_filter: AppointmentStatus | None = None,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    request: Request | None = None,
) -> Page[AppointmentResponse]:
    stmt = (
        select(
            Appointment,
            AppointmentSlot.start_at.label("start_at"),
            AppointmentSlot.end_at.label("end_at"),
            DoctorProfile.first_name.label("provider_first_name"),
            DoctorProfile.last_name.label("provider_last_name"),
            PatientProfile.first_name.label("patient_first_name"),
            PatientProfile.last_name.label("patient_last_name"),
        )
        .select_from(Appointment)
        .join(AppointmentSlot, AppointmentSlot.id == Appointment.slot_id)
        .join(DoctorProfile, DoctorProfile.user_id == Appointment.provider_user_id)
        .join(PatientProfile, PatientProfile.user_id == Appointment.patient_user_id)
    )
    stmt = _role_scoped_appointments(stmt, context)
    if status_filter is not None:
        stmt = stmt.where(Appointment.status == status_filter)
    if start_from is not None:
        stmt = stmt.where(AppointmentSlot.start_at >= start_from)
    if start_to is not None:
        stmt = stmt.where(AppointmentSlot.start_at <= start_to)
    stmt = (
        stmt.order_by(AppointmentSlot.start_at.desc(), Appointment.id.asc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )

    rows = (await db.execute(stmt)).all()
    items: list[AppointmentResponse] = []
    for row in rows:
        appointment: Appointment = row[0]
        items.append(
            AppointmentResponse(
                id=appointment.id,
                slot_id=appointment.slot_id,
                patient_user_id=appointment.patient_user_id,
                patient_name=_person_name(row.patient_first_name, row.patient_last_name),
                provider_user_id=appointment.provider_user_id,
                provider_name=_provider_name(row.provider_first_name, row.provider_last_name),
                organization_id=appointment.organization_id,
                encounter_id=appointment.encounter_id,
                referral_id=appointment.referral_id,
                reason=appointment.reason,
                channel=appointment.channel,
                status=appointment.status,
                payment_status=appointment.payment_status,
                invoice_id=appointment.invoice_id,
                cancellation_reason=appointment.cancellation_reason,
                start_at=row.start_at,
                end_at=row.end_at,
                booked_at=appointment.booked_at,
                created_at=appointment.created_at,
                updated_at=appointment.updated_at,
            )
        )

    page_out = paginate(items, page)
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[item.patient_user_id for item in page_out.items],
        resource_type="appointment",
        purpose_of_use="TREAT",
        request=request,
    )
    await db.commit()
    return page_out


async def get_appointment(
    db: AsyncSession,
    context: AuthContext,
    appointment_id: UUID,
    *,
    request: Request | None = None,
) -> AppointmentResponse:
    row = (
        await db.execute(
            select(
                Appointment,
                AppointmentSlot.start_at.label("start_at"),
                AppointmentSlot.end_at.label("end_at"),
                DoctorProfile.first_name.label("provider_first_name"),
                DoctorProfile.last_name.label("provider_last_name"),
                PatientProfile.first_name.label("patient_first_name"),
                PatientProfile.last_name.label("patient_last_name"),
            )
            .select_from(Appointment)
            .join(AppointmentSlot, AppointmentSlot.id == Appointment.slot_id)
            .join(DoctorProfile, DoctorProfile.user_id == Appointment.provider_user_id)
            .join(PatientProfile, PatientProfile.user_id == Appointment.patient_user_id)
            .where(Appointment.id == appointment_id)
        )
    ).first()
    if row is None:
        raise not_found("Appointment")
    appointment: Appointment = row[0]
    _authorize_appointment(context, appointment)

    await record_phi_access(
        db,
        context,
        patient_user_id=appointment.patient_user_id,
        resource_type="appointment",
        resource_id=appointment.id,
        purpose_of_use="TREAT",
        request=request,
        result_count=1,
    )
    await db.commit()
    return AppointmentResponse(
        id=appointment.id,
        slot_id=appointment.slot_id,
        patient_user_id=appointment.patient_user_id,
        patient_name=_person_name(row.patient_first_name, row.patient_last_name),
        provider_user_id=appointment.provider_user_id,
        provider_name=_provider_name(row.provider_first_name, row.provider_last_name),
        organization_id=appointment.organization_id,
        encounter_id=appointment.encounter_id,
        referral_id=appointment.referral_id,
        reason=appointment.reason,
        channel=appointment.channel,
        status=appointment.status,
        payment_status=appointment.payment_status,
        invoice_id=appointment.invoice_id,
        cancellation_reason=appointment.cancellation_reason,
        start_at=row.start_at,
        end_at=row.end_at,
        booked_at=appointment.booked_at,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


# ---------------------------------------------------------------------------
# Telehealth
# ---------------------------------------------------------------------------


async def start_telehealth_session(
    db: AsyncSession,
    context: AuthContext,
    appointment_id: UUID,
    payload: TelehealthCreate,
    *,
    request: Request | None = None,
) -> TelehealthSessionResponse:
    """Create (or re-issue join details for) the telehealth room."""
    now = _now()
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise not_found("Appointment")
    _authorize_appointment(context, appointment)
    if appointment.channel != EncounterChannel.TELEHEALTH:
        raise unprocessable("This appointment is not a telehealth appointment")
    if appointment.status not in {AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN}:
        raise conflict(f"Cannot join an appointment that is '{appointment.status.value}'")

    slot = await db.get(AppointmentSlot, appointment.slot_id)
    if slot is None:
        raise not_found("Appointment slot")

    if appointment.encounter_id is None:
        encounter = Encounter(
            tenant_id=appointment.tenant_id,
            patient_user_id=appointment.patient_user_id,
            primary_practitioner_user_id=appointment.provider_user_id,
            organization_id=appointment.organization_id,
            appointment_id=appointment.id,
            class_code=EncounterClass.VR,
            status=EncounterStatus.PLANNED,
            started_at=slot.start_at,
            reason_text=appointment.reason,
            recorded_by_user_id=context.user.id,
            source=ProvenanceSource.PRACTITIONER,
        )
        db.add(encounter)
        await db.flush()
        appointment.encounter_id = encounter.id

    session = await db.scalar(
        select(TelehealthSession).where(TelehealthSession.appointment_id == appointment.id)
    )
    join_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(join_token.encode()).hexdigest()
    if session is None:
        session = TelehealthSession(
            tenant_id=appointment.tenant_id,
            appointment_id=appointment.id,
            encounter_id=appointment.encounter_id,
            provider_room_id=f"appt-{appointment.id}",
            join_token_hash=token_hash,
            participants=[],
            recording_consent=payload.recording_consent,
            connection_quality={},
            licensure_state=payload.licensure_state,
            licensure_verified=False,
        )
        db.add(session)
        await db.flush()
    else:
        session.join_token_hash = token_hash
        session.encounter_id = appointment.encounter_id
        if payload.recording_consent:
            session.recording_consent = True
        if payload.licensure_state is not None:
            session.licensure_state = payload.licensure_state

    participants = list(session.participants)
    participants.append(
        {
            "user_id": str(context.user.id),
            "role": context.user.account_type.value,
            "joined_at": now.isoformat(),
        }
    )
    session.participants = participants
    if session.started_at is None and context.user.id == appointment.provider_user_id:
        session.started_at = now

    await record_phi_access(
        db,
        context,
        patient_user_id=appointment.patient_user_id,
        resource_type="telehealth_session",
        resource_id=session.id,
        purpose_of_use="TREAT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="scheduling.telehealth.joined",
        subject_user_id=appointment.patient_user_id,
        resource_id=session.id,
        event_data={
            "appointment_id": str(appointment.id),
            "encounter_id": str(appointment.encounter_id),
            "room": session.provider_room_id,
        },
        request=request,
    )
    await db.commit()
    return TelehealthSessionResponse(
        id=session.id,
        appointment_id=session.appointment_id,
        encounter_id=session.encounter_id,
        provider_room_id=session.provider_room_id,
        join_token=join_token,
        join_url=f"/telehealth/rooms/{session.provider_room_id}?token={join_token}",
        started_at=session.started_at,
        ended_at=session.ended_at,
        participants=session.participants,
        recording_consent=session.recording_consent,
        licensure_state=session.licensure_state,
        licensure_verified=session.licensure_verified,
    )


# ---------------------------------------------------------------------------
# Provider schedules
# ---------------------------------------------------------------------------


async def list_provider_schedules(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    provider_user_id: UUID | None = None,
    organization_id: UUID | None = None,
    is_active: bool | None = None,
) -> Page[ProviderScheduleResponse]:
    stmt = tenant_scoped(select(ProviderSchedule), ProviderSchedule, context)
    if provider_user_id is not None:
        stmt = stmt.where(ProviderSchedule.provider_user_id == provider_user_id)
    if organization_id is not None:
        stmt = stmt.where(ProviderSchedule.organization_id == organization_id)
    if is_active is not None:
        stmt = stmt.where(ProviderSchedule.is_active.is_(is_active))
    stmt = (
        stmt.order_by(
            ProviderSchedule.provider_user_id.asc(),
            ProviderSchedule.day_of_week.asc(),
            ProviderSchedule.start_time.asc(),
        )
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    schedules = list((await db.scalars(stmt)).all())

    names: dict[UUID, str] = {}
    if schedules:
        rows = await db.execute(
            select(DoctorProfile.user_id, DoctorProfile.first_name, DoctorProfile.last_name).where(
                DoctorProfile.user_id.in_({item.provider_user_id for item in schedules})
            )
        )
        names = {
            user_id: _provider_name(first_name, last_name)
            for user_id, first_name, last_name in rows.all()
        }
    return paginate(
        [_schedule_response(item, names.get(item.provider_user_id)) for item in schedules], page
    )


async def create_provider_schedule(
    db: AsyncSession,
    context: AuthContext,
    payload: ProviderScheduleCreate,
    *,
    request: Request | None = None,
) -> ProviderScheduleResponse:
    organization_id = payload.organization_id or context.tenant_id
    if not is_admin(context) and organization_id != context.tenant_id:
        raise forbidden("Schedules may only be created inside your own organization")

    provider = await db.get(DoctorProfile, payload.provider_user_id)
    if provider is None:
        raise not_found("Provider")
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise not_found("Organization")
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise unprocessable(f"Unknown timezone '{payload.timezone}'") from exc

    schedule = ProviderSchedule(
        tenant_id=context.tenant_id,
        provider_user_id=payload.provider_user_id,
        organization_id=organization_id,
        department_id=payload.department_id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        slot_minutes=payload.slot_minutes,
        timezone=payload.timezone,
        channel=payload.channel,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        is_active=payload.is_active,
    )
    db.add(schedule)
    await db.flush()
    await write_audit(
        db,
        context,
        event_type="scheduling.provider_schedule.created",
        resource_id=schedule.id,
        event_data={
            "provider_user_id": str(payload.provider_user_id),
            "organization_id": str(organization_id),
            "day_of_week": payload.day_of_week,
            "channel": payload.channel.value,
        },
        request=request,
    )
    await db.commit()
    return _schedule_response(schedule, _provider_name(provider.first_name, provider.last_name))


def _expand_schedule(
    schedule: ProviderSchedule, payload: SlotGenerationRequest
) -> list[tuple[datetime, datetime]]:
    """Materialise (start, end) instants in UTC for one recurring template.

    ``day_of_week`` follows :meth:`datetime.date.weekday` — 0 is Monday.
    """
    try:
        zone = ZoneInfo(schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise unprocessable(f"Schedule has an unknown timezone '{schedule.timezone}'") from exc

    window_start = max(payload.from_date, schedule.valid_from)
    window_end = payload.to_date
    if schedule.valid_to is not None:
        window_end = min(window_end, schedule.valid_to)
    periods: list[tuple[datetime, datetime]] = []
    step = timedelta(minutes=schedule.slot_minutes)
    day = window_start
    while day <= window_end:
        if day.weekday() == schedule.day_of_week:
            cursor = datetime.combine(day, schedule.start_time, tzinfo=zone)
            day_end = datetime.combine(day, schedule.end_time, tzinfo=zone)
            while cursor + step <= day_end:
                periods.append((cursor.astimezone(UTC), (cursor + step).astimezone(UTC)))
                cursor += step
        day += timedelta(days=1)
    return periods


async def generate_slots(
    db: AsyncSession,
    context: AuthContext,
    schedule_id: UUID,
    payload: SlotGenerationRequest,
    *,
    request: Request | None = None,
) -> SlotGenerationResult:
    """Expand a recurring schedule into slots. Re-running is a no-op."""
    now = _now()
    schedule = await db.get(ProviderSchedule, schedule_id)
    if schedule is None:
        raise not_found("Provider schedule")
    if not is_admin(context) and schedule.tenant_id != context.tenant_id:
        raise not_found("Provider schedule")
    if not schedule.is_active:
        raise conflict("Schedule is inactive")

    periods = [period for period in _expand_schedule(schedule, payload) if period[0] > now]
    if not periods:
        return SlotGenerationResult(
            schedule_id=schedule.id,
            from_date=payload.from_date,
            to_date=payload.to_date,
            created=0,
            skipped=0,
            slot_ids=[],
        )

    rows = [
        {
            "id": uuid4(),
            "tenant_id": schedule.tenant_id,
            "provider_user_id": schedule.provider_user_id,
            "organization_id": schedule.organization_id,
            "schedule_id": schedule.id,
            "start_at": start_at,
            "end_at": end_at,
            "capacity": payload.capacity,
            "booked_count": 0,
            "status": SlotStatus.OPEN.value,
            "channel": schedule.channel.value,
            "price_cents": payload.price_cents,
            "currency": payload.currency,
        }
        for start_at, end_at in periods
    ]
    # ON CONFLICT DO NOTHING against uq_appointment_slot_provider_start is what
    # makes a repeated expansion idempotent instead of a duplicate-key failure.
    # Targets the Table rather than the mapped class: the ORM insert path cannot
    # tolerate RETURNING coming back with fewer rows than were sent.
    slots_table = cast(Table, AppointmentSlot.__table__)
    statement = (
        pg_insert(slots_table)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_appointment_slot_provider_start")
        .returning(slots_table.c.id)
    )
    created_ids: list[UUID] = list((await db.scalars(statement)).all())

    await write_audit(
        db,
        context,
        event_type="scheduling.slots.generated",
        resource_id=schedule.id,
        event_data={
            "from_date": payload.from_date.isoformat(),
            "to_date": payload.to_date.isoformat(),
            "created": len(created_ids),
            "skipped": len(rows) - len(created_ids),
        },
        request=request,
    )
    await db.commit()
    return SlotGenerationResult(
        schedule_id=schedule.id,
        from_date=payload.from_date,
        to_date=payload.to_date,
        created=len(created_ids),
        skipped=len(rows) - len(created_ids),
        slot_ids=created_ids,
    )
