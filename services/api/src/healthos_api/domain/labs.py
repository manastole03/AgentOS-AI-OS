"""Laboratory domain: catalogue, slot availability, ordering, specimens, results.

Booking honours the two-dimensional availability the schema models: a
``lab_slots`` row carries the facility capacity for a window, and
``lab_slot_tests`` carries the per-test capacity *and* decides which tests are
bookable in that window at all. A slot is only offered for a basket of tests
when it links every requested test and both counters still have room, and the
claim itself is taken under ``SELECT ... FOR UPDATE`` so two concurrent
bookings can never oversell the same slot.

Results are append-only in spirit: a correction inserts a new ``lab_results``
row carrying ``supersedes_id`` and stamps ``superseded_at`` on the row it
replaces, rather than mutating the original observation.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import Field, model_validator
from sqlalchemy import Select, distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccountType,
    IdempotencyRecord,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    LabFacility,
    LabOrder,
    LabOrderStatus,
    LabOrderTest,
    LabPriority,
    LabResult,
    LabSlot,
    LabSlotTest,
    LabTest,
    ObservationStatus,
    PatientProfile,
    PhiAccessAction,
    ProvenanceSource,
    SlotStatus,
    Specimen,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    apply_patient_scope,
    assert_may_read_patient,
    assert_transition,
    conflict,
    consent_scoped_patients,
    discovery_scoped,
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

#: Fraction of the reference interval width beyond which a value is a panic
#: value when the submitting lab does not supply explicit critical bounds.
PANIC_MARGIN = Decimal("0.5")

#: How long a stored ``Idempotency-Key`` result stays replayable.
IDEMPOTENCY_TTL = timedelta(hours=24)

ORDER_TRANSITIONS: dict[str, set[str]] = {
    LabOrderStatus.DRAFT.value: {
        LabOrderStatus.PLACED.value,
        LabOrderStatus.CANCELLED.value,
        LabOrderStatus.ENTERED_IN_ERROR.value,
    },
    LabOrderStatus.PLACED.value: {
        LabOrderStatus.COLLECTED.value,
        LabOrderStatus.IN_PROCESS.value,
        LabOrderStatus.CANCELLED.value,
        LabOrderStatus.ENTERED_IN_ERROR.value,
    },
    LabOrderStatus.COLLECTED.value: {
        LabOrderStatus.IN_PROCESS.value,
        LabOrderStatus.RESULTED.value,
        LabOrderStatus.CANCELLED.value,
        LabOrderStatus.ENTERED_IN_ERROR.value,
    },
    LabOrderStatus.IN_PROCESS.value: {
        LabOrderStatus.RESULTED.value,
        LabOrderStatus.CANCELLED.value,
        LabOrderStatus.ENTERED_IN_ERROR.value,
    },
    LabOrderStatus.RESULTED.value: {LabOrderStatus.ENTERED_IN_ERROR.value},
    LabOrderStatus.CANCELLED.value: set(),
    LabOrderStatus.ENTERED_IN_ERROR.value: set(),
}

RESULT_ENTRY_STATUSES = frozenset(
    {
        ObservationStatus.REGISTERED.value,
        ObservationStatus.PRELIMINARY.value,
        ObservationStatus.FINAL.value,
        ObservationStatus.AMENDED.value,
        ObservationStatus.CORRECTED.value,
    }
)

VERIFIED_STATUSES = frozenset(
    {
        ObservationStatus.FINAL.value,
        ObservationStatus.AMENDED.value,
        ObservationStatus.CORRECTED.value,
    }
)

CLOSING_RESULT_STATUSES = VERIFIED_STATUSES

ResultStatusLiteral = Literal[
    "registered", "preliminary", "final", "amended", "corrected", "cancelled"
]
PriorityLiteral = Literal["routine", "urgent", "stat"]
ComparatorLiteral = Literal["<", "<=", ">", ">="]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class LabTestOut(DomainModel):
    """A single orderable entry in the test catalogue."""

    id: UUID
    test_code_system: str
    test_code: str
    test_display: str
    name: str
    panel_code_system: str | None = None
    panel_code: str | None = None
    panel_display: str | None = None
    specimen_type_code_system: str | None = None
    specimen_type_code: str | None = None
    specimen_type_display: str | None = None
    container: str | None = None
    prep_instructions: str | None = None
    fasting_required: bool
    turnaround_hours: int | None = None
    price_cents: int | None = None
    currency: str | None = None
    department_id: UUID | None = None
    is_active: bool


class LabFacilityOut(DomainModel):
    id: UUID
    organization_id: UUID
    name: str
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    timezone: str
    home_collection_available: bool
    is_active: bool


class SlotAvailabilityOut(DomainModel):
    """An open slot that offers every requested test, with the tighter of the
    facility-level and per-test remaining capacities."""

    slot_id: UUID
    facility_id: UUID
    facility_name: str
    start_at: datetime
    end_at: datetime
    capacity: int
    booked_count: int
    slot_remaining: int
    test_remaining: int
    remaining: int
    offered_test_ids: list[UUID]
    matched_test_count: int
    total_price_cents: int
    currency: str | None = None


class LabOrderCreate(DomainModel):
    patient_user_id: UUID | None = None
    facility_id: UUID
    slot_id: UUID | None = None
    test_ids: list[UUID] = Field(min_length=1, max_length=50)
    priority: PriorityLiteral = "routine"
    ordering_provider_user_id: UUID | None = None
    encounter_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _unique_tests(self) -> "LabOrderCreate":
        if len(set(self.test_ids)) != len(self.test_ids):
            raise ValueError("test_ids must be unique")
        return self


class LabOrderTestOut(DomainModel):
    id: UUID
    lab_test_id: UUID
    test_code_system: str
    test_code: str
    test_display: str
    name: str
    status: str
    price_cents: int | None = None
    currency: str | None = None


class InvoiceLineOut(DomainModel):
    id: UUID
    line_number: int
    description: str
    service_code_system: str | None = None
    service_code: str | None = None
    quantity: Decimal
    unit_price_cents: int
    amount_cents: int


class InvoiceOut(DomainModel):
    id: UUID
    invoice_number: str
    status: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    balance_cents: int
    currency: str
    issued_at: datetime | None = None
    due_at: datetime | None = None
    lines: list[InvoiceLineOut] = Field(default_factory=list)


class SpecimenOut(DomainModel):
    id: UUID
    lab_order_id: UUID
    patient_user_id: UUID
    accession_number: str
    specimen_type_code_system: str
    specimen_type_code: str
    specimen_type_display: str
    collected_at: datetime
    collected_by_user_id: UUID | None = None
    condition: str | None = None
    received_at: datetime | None = None
    rejected_reason: str | None = None


class LabResultOut(DomainModel):
    id: UUID
    lab_order_id: UUID | None = None
    lab_test_id: UUID | None = None
    specimen_id: UUID | None = None
    patient_user_id: UUID
    test_code_system: str
    test_code: str
    test_display: str
    status: str
    value_numeric: Decimal | None = None
    value_string: str | None = None
    value_code_system: str | None = None
    value_code: str | None = None
    value_display: str | None = None
    value_boolean: bool | None = None
    value_comparator: str | None = None
    unit: str | None = None
    data_absent_reason: str | None = None
    interpretation_code: str | None = None
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    reference_range_text: str | None = None
    is_critical: bool
    critical_notified_at: datetime | None = None
    acknowledged_by_user_id: UUID | None = None
    acknowledged_at: datetime | None = None
    acknowledgement_note: str | None = None
    effective_at: datetime
    issued_at: datetime | None = None
    version: int
    supersedes_id: UUID | None = None
    superseded_at: datetime | None = None
    amendment_reason: str | None = None


class LabOrderOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    ordering_provider_user_id: UUID | None = None
    encounter_id: UUID | None = None
    facility_id: UUID
    slot_id: UUID | None = None
    order_number: str
    priority: str
    status: str
    invoice_id: UUID | None = None
    requested_at: datetime
    collected_at: datetime | None = None
    note: str | None = None
    test_count: int


class LabOrderDetail(LabOrderOut):
    tests: list[LabOrderTestOut] = Field(default_factory=list)
    specimens: list[SpecimenOut] = Field(default_factory=list)
    results: list[LabResultOut] = Field(default_factory=list)
    invoice: InvoiceOut | None = None


class OrderCancel(DomainModel):
    reason: str | None = Field(default=None, max_length=255)


class SpecimenCreate(DomainModel):
    accession_number: str | None = Field(default=None, max_length=64)
    specimen_type_code_system: str | None = Field(default=None, max_length=128)
    specimen_type_code: str | None = Field(default=None, max_length=64)
    specimen_type_display: str | None = Field(default=None, max_length=255)
    collected_at: datetime | None = None
    collected_by_user_id: UUID | None = None
    condition: str | None = Field(default=None, max_length=64)
    received_at: datetime | None = None
    rejected_reason: str | None = Field(default=None, max_length=255)


class LabResultEntry(DomainModel):
    """One observation. Mirrors the ``lab_result_single_value`` DB constraint."""

    lab_test_id: UUID | None = None
    specimen_id: UUID | None = None
    test_code_system: str | None = Field(default=None, max_length=128)
    test_code: str | None = Field(default=None, max_length=64)
    test_display: str | None = Field(default=None, max_length=255)
    status: ResultStatusLiteral = "final"
    value_numeric: Decimal | None = None
    value_string: str | None = Field(default=None, max_length=255)
    value_code_system: str | None = Field(default=None, max_length=128)
    value_code: str | None = Field(default=None, max_length=64)
    value_display: str | None = Field(default=None, max_length=255)
    value_boolean: bool | None = None
    value_comparator: ComparatorLiteral | None = None
    unit: str | None = Field(default=None, max_length=32)
    data_absent_reason: str | None = Field(default=None, max_length=32)
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    reference_range_text: str | None = Field(default=None, max_length=255)
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    effective_at: datetime | None = None
    issued_at: datetime | None = None
    supersedes_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _single_value(self) -> "LabResultEntry":
        present = [
            self.value_numeric is not None,
            self.value_string is not None,
            self.value_code is not None,
            self.value_boolean is not None,
            self.data_absent_reason is not None,
        ]
        if sum(present) != 1:
            raise ValueError(
                "exactly one of value_numeric, value_string, value_code, value_boolean or "
                "data_absent_reason must be supplied"
            )
        if self.value_numeric is not None and not self.unit:
            raise ValueError("unit is required when value_numeric is supplied")
        if self.value_code is not None and not self.value_code_system:
            raise ValueError("value_code_system is required when value_code is supplied")
        if self.lab_test_id is None and not (self.test_code_system and self.test_code):
            raise ValueError("lab_test_id or test_code_system + test_code is required")
        low, high = self.reference_range_low, self.reference_range_high
        if low is not None and high is not None and high < low:
            raise ValueError("reference_range_high must be >= reference_range_low")
        return self


class LabResultsCreate(DomainModel):
    results: list[LabResultEntry] = Field(min_length=1, max_length=200)


class ResultAcknowledge(DomainModel):
    note: str | None = Field(default=None, max_length=500)


class TrendPoint(DomainModel):
    result_id: UUID
    effective_at: datetime
    value_numeric: Decimal | None = None
    value_string: str | None = None
    value_comparator: str | None = None
    unit: str | None = None
    interpretation_code: str | None = None
    is_critical: bool
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    status: str


class ResultSeries(DomainModel):
    test_code_system: str
    test_code: str
    test_display: str
    unit: str | None = None
    point_count: int
    points: list[TrendPoint] = Field(default_factory=list)


class PatientResultTrend(DomainModel):
    patient_user_id: UUID
    series: list[ResultSeries] = Field(default_factory=list)


class CriticalResultOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    lab_order_id: UUID | None = None
    order_number: str | None = None
    ordering_provider_user_id: UUID | None = None
    facility_id: UUID | None = None
    test_code_system: str
    test_code: str
    test_display: str
    value_numeric: Decimal | None = None
    value_string: str | None = None
    unit: str | None = None
    interpretation_code: str | None = None
    status: str
    effective_at: datetime
    critical_notified_at: datetime | None = None
    notified_user_id: UUID | None = None
    outstanding_hours: Decimal


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(UTC)


def _reference(prefix: str) -> str:
    return f"{prefix}-{_now():%Y%m%d}-{uuid4().hex[:10].upper()}"


def _order_out(order: LabOrder, test_count: int) -> LabOrderOut:
    return LabOrderOut(
        id=order.id,
        patient_user_id=order.patient_user_id,
        ordering_provider_user_id=order.ordering_provider_user_id,
        encounter_id=order.encounter_id,
        facility_id=order.facility_id,
        slot_id=order.slot_id,
        order_number=order.order_number,
        priority=order.priority.value,
        status=order.status.value,
        invoice_id=order.invoice_id,
        requested_at=order.requested_at,
        collected_at=order.collected_at,
        note=order.note,
        test_count=test_count,
    )


def _result_out(result: LabResult) -> LabResultOut:
    return LabResultOut(
        id=result.id,
        lab_order_id=result.lab_order_id,
        lab_test_id=result.lab_test_id,
        specimen_id=result.specimen_id,
        patient_user_id=result.patient_user_id,
        test_code_system=result.test_code_system,
        test_code=result.test_code,
        test_display=result.test_display,
        status=result.status.value,
        value_numeric=result.value_numeric,
        value_string=result.value_string,
        value_code_system=result.value_code_system,
        value_code=result.value_code,
        value_display=result.value_display,
        value_boolean=result.value_boolean,
        value_comparator=result.value_comparator,
        unit=result.unit,
        data_absent_reason=result.data_absent_reason,
        interpretation_code=result.interpretation_code,
        reference_range_low=result.reference_range_low,
        reference_range_high=result.reference_range_high,
        reference_range_text=result.reference_range_text,
        is_critical=result.is_critical,
        critical_notified_at=result.critical_notified_at,
        acknowledged_by_user_id=result.acknowledged_by_user_id,
        acknowledged_at=result.acknowledged_at,
        acknowledgement_note=result.acknowledgement_note,
        effective_at=result.effective_at,
        issued_at=result.issued_at,
        version=result.version,
        supersedes_id=result.supersedes_id,
        superseded_at=result.superseded_at,
        amendment_reason=result.amendment_reason,
    )


def _specimen_out(specimen: Specimen) -> SpecimenOut:
    return SpecimenOut(
        id=specimen.id,
        lab_order_id=specimen.lab_order_id,
        patient_user_id=specimen.patient_user_id,
        accession_number=specimen.accession_number,
        specimen_type_code_system=specimen.specimen_type_code_system,
        specimen_type_code=specimen.specimen_type_code,
        specimen_type_display=specimen.specimen_type_display,
        collected_at=specimen.collected_at,
        collected_by_user_id=specimen.collected_by_user_id,
        condition=specimen.condition,
        received_at=specimen.received_at,
        rejected_reason=specimen.rejected_reason,
    )


def interpret(
    value: Decimal | None,
    low: Decimal | None,
    high: Decimal | None,
    critical_low: Decimal | None = None,
    critical_high: Decimal | None = None,
) -> tuple[str | None, bool]:
    """Return ``(interpretation_code, is_critical)`` for a numeric result.

    Explicit panic bounds win. Otherwise a value that falls outside the
    reference interval by more than :data:`PANIC_MARGIN` of the interval width
    is treated as a panic value, which is what the ``ix_lab_result_unacked``
    worklist is built to surface.
    """
    if value is None:
        return None, False
    if low is not None and high is not None and high > low:
        width = high - low
        if critical_low is None:
            critical_low = low - width * PANIC_MARGIN
        if critical_high is None:
            critical_high = high + width * PANIC_MARGIN
    if critical_low is not None and value < critical_low:
        return "LL", True
    if critical_high is not None and value > critical_high:
        return "HH", True
    if low is not None and value < low:
        return "L", False
    if high is not None and value > high:
        return "H", False
    if low is None and high is None:
        return None, False
    return "N", False


async def _fallback_range(
    db: AsyncSession, tenant_id: UUID, test_code: str
) -> tuple[Decimal | None, Decimal | None, str | None]:
    """Reuse the most recent published interval for this analyte when the
    submitting lab omits one."""
    row = (
        await db.execute(
            select(
                LabResult.reference_range_low,
                LabResult.reference_range_high,
                LabResult.reference_range_text,
            )
            .where(
                LabResult.tenant_id == tenant_id,
                LabResult.test_code == test_code,
                or_(
                    LabResult.reference_range_low.is_not(None),
                    LabResult.reference_range_high.is_not(None),
                ),
            )
            .order_by(LabResult.effective_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None, None
    return row[0], row[1], row[2]


async def _order_query(db: AsyncSession, context: AuthContext) -> Select[tuple[LabOrder]]:
    allowed = await consent_scoped_patients(db, context)
    return apply_patient_scope(select(LabOrder), LabOrder, allowed)


async def _load_order_for_read(db: AsyncSession, context: AuthContext, order_id: UUID) -> LabOrder:
    query = await _order_query(db, context)
    order = await db.scalar(query.where(LabOrder.id == order_id))
    if order is None:
        raise not_found("Lab order")
    return order


async def _load_order_for_write(db: AsyncSession, context: AuthContext, order_id: UUID) -> LabOrder:
    """A write is allowed by the owning organisation or by a consent holder."""
    order = await db.scalar(select(LabOrder).where(LabOrder.id == order_id))
    if order is None:
        raise not_found("Lab order")
    if is_admin(context) or order.tenant_id == context.tenant_id:
        return order
    allowed = await consent_scoped_patients(db, context)
    if allowed is None or order.patient_user_id in allowed:
        return order
    raise forbidden("This lab order belongs to another organization")


async def _order_test_rows(
    db: AsyncSession, order_ids: list[UUID]
) -> dict[UUID, list[LabOrderTestOut]]:
    if not order_ids:
        return {}
    rows = (
        await db.execute(
            select(
                LabOrderTest.id,
                LabOrderTest.lab_order_id,
                LabOrderTest.lab_test_id,
                LabOrderTest.status,
                LabOrderTest.price_cents,
                LabOrderTest.currency,
                LabTest.test_code_system,
                LabTest.test_code,
                LabTest.test_display,
                LabTest.name,
            )
            .join(LabTest, LabTest.id == LabOrderTest.lab_test_id)
            .where(LabOrderTest.lab_order_id.in_(order_ids))
            .order_by(LabTest.test_code)
        )
    ).mappings()
    grouped: dict[UUID, list[LabOrderTestOut]] = {}
    for row in rows:
        grouped.setdefault(row["lab_order_id"], []).append(
            LabOrderTestOut(
                id=row["id"],
                lab_test_id=row["lab_test_id"],
                test_code_system=row["test_code_system"],
                test_code=row["test_code"],
                test_display=row["test_display"],
                name=row["name"],
                status=row["status"].value,
                price_cents=row["price_cents"],
                currency=row["currency"],
            )
        )
    return grouped


async def _test_counts(db: AsyncSession, order_ids: list[UUID]) -> dict[UUID, int]:
    if not order_ids:
        return {}
    rows = (
        await db.execute(
            select(LabOrderTest.lab_order_id, func.count())
            .where(LabOrderTest.lab_order_id.in_(order_ids))
            .group_by(LabOrderTest.lab_order_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _invoice_out(db: AsyncSession, invoice_id: UUID | None) -> InvoiceOut | None:
    if invoice_id is None:
        return None
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if invoice is None:
        return None
    lines = (
        await db.scalars(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.line_number)
        )
    ).all()
    return InvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        status=invoice.status.value,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        total_cents=invoice.total_cents,
        balance_cents=invoice.balance_cents,
        currency=invoice.currency,
        issued_at=invoice.issued_at,
        due_at=invoice.due_at,
        lines=[
            InvoiceLineOut(
                id=line.id,
                line_number=line.line_number,
                description=line.description,
                service_code_system=line.service_code_system,
                service_code=line.service_code,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                amount_cents=line.amount_cents,
            )
            for line in lines
        ],
    )


async def _replay_idempotent(
    db: AsyncSession,
    context: AuthContext,
    *,
    operation: str,
    key: str,
    digest: str,
) -> tuple[dict[str, Any] | None, IdempotencyRecord | None]:
    """Return the stored response for a replayed key, or reserve the key.

    The reservation goes through a SAVEPOINT so that a concurrent request
    losing the unique-constraint race degrades into a 409 instead of poisoning
    the outer transaction.
    """
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
            raise conflict("Idempotency-Key was reused with a different payload")
        if existing.response_body is None:
            raise conflict("A request with this Idempotency-Key is still in flight")
        return existing.response_body, None

    record = IdempotencyRecord(
        tenant_id=context.tenant_id,
        actor_user_id=context.user.id,
        operation=operation,
        key=key,
        request_digest=digest,
        expires_at=_now() + IDEMPOTENCY_TTL,
    )
    try:
        async with db.begin_nested():
            db.add(record)
            await db.flush()
    except IntegrityError as exc:
        raise conflict("A request with this Idempotency-Key is still in flight") from exc
    return None, record


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #


async def list_tests(
    db: AsyncSession,
    context: AuthContext,
    page: Pagination,
    *,
    search: str | None = None,
    code: str | None = None,
    panel_code: str | None = None,
    specimen_type_code: str | None = None,
    fasting_required: bool | None = None,
    max_turnaround_hours: int | None = None,
    include_inactive: bool = False,
) -> Page[LabTestOut]:
    query = discovery_scoped(select(LabTest), LabTest, context)
    if not include_inactive:
        query = query.where(LabTest.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                LabTest.name.ilike(pattern),
                LabTest.test_display.ilike(pattern),
                LabTest.test_code.ilike(pattern),
                LabTest.panel_display.ilike(pattern),
            )
        )
    if code:
        query = query.where(LabTest.test_code == code)
    if panel_code:
        query = query.where(LabTest.panel_code == panel_code)
    if specimen_type_code:
        query = query.where(LabTest.specimen_type_code == specimen_type_code)
    if fasting_required is not None:
        query = query.where(LabTest.fasting_required.is_(fasting_required))
    if max_turnaround_hours is not None:
        query = query.where(LabTest.turnaround_hours <= max_turnaround_hours)

    rows = (
        await db.scalars(query.order_by(LabTest.name).limit(page.limit + 1).offset(page.offset))
    ).all()
    return paginate([LabTestOut.model_validate(row) for row in rows], page)


async def list_facilities(
    db: AsyncSession,
    context: AuthContext,
    page: Pagination,
    *,
    search: str | None = None,
    city: str | None = None,
    home_collection: bool | None = None,
    include_inactive: bool = False,
) -> Page[LabFacilityOut]:
    query = discovery_scoped(select(LabFacility), LabFacility, context)
    if not include_inactive:
        query = query.where(LabFacility.is_active.is_(True))
    if search:
        query = query.where(LabFacility.name.ilike(f"%{search.strip()}%"))
    if city:
        query = query.where(LabFacility.city.ilike(city))
    if home_collection is not None:
        query = query.where(LabFacility.home_collection_available.is_(home_collection))
    rows = (
        await db.scalars(query.order_by(LabFacility.name).limit(page.limit + 1).offset(page.offset))
    ).all()
    return paginate([LabFacilityOut.model_validate(row) for row in rows], page)


async def find_availability(
    db: AsyncSession,
    context: AuthContext,
    page: Pagination,
    *,
    test_ids: list[UUID] | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    facility_id: UUID | None = None,
) -> Page[SlotAvailabilityOut]:
    """Open slots that offer *all* requested tests, in a single aggregate query.

    ``HAVING count(distinct lab_slot_tests.lab_test_id) = :n`` is what enforces
    "every requested test is bookable in this slot"; the per-test capacity
    predicate is what enforces "and there is still room for each of them".
    """
    window_start = from_at or _now()
    window_end = to_at or (window_start + timedelta(days=14))
    if window_end <= window_start:
        raise unprocessable("'to' must be after 'from'")
    wanted = list(dict.fromkeys(test_ids or []))

    slot_remaining = (LabSlot.capacity - LabSlot.booked_count).label("slot_remaining")
    test_remaining = func.min(LabSlotTest.capacity - LabSlotTest.booked_count).label(
        "test_remaining"
    )
    matched = func.count(distinct(LabSlotTest.lab_test_id)).label("matched_test_count")
    total_price = func.coalesce(
        func.sum(func.coalesce(LabSlotTest.price_cents_override, LabTest.price_cents, 0)), 0
    ).label("total_price_cents")

    query = (
        select(
            LabSlot.id.label("slot_id"),
            LabSlot.facility_id,
            LabFacility.name.label("facility_name"),
            LabSlot.start_at,
            LabSlot.end_at,
            LabSlot.capacity,
            LabSlot.booked_count,
            slot_remaining,
            test_remaining,
            matched,
            total_price,
            func.max(LabTest.currency).label("currency"),
            func.array_agg(distinct(LabSlotTest.lab_test_id)).label("offered_test_ids"),
        )
        .select_from(LabSlot)
        .join(LabFacility, LabFacility.id == LabSlot.facility_id)
        .join(LabSlotTest, LabSlotTest.slot_id == LabSlot.id)
        .join(LabTest, LabTest.id == LabSlotTest.lab_test_id)
        .where(
            LabSlot.status == SlotStatus.OPEN,
            LabSlot.start_at >= window_start,
            LabSlot.start_at < window_end,
            LabSlot.booked_count < LabSlot.capacity,
            LabSlotTest.booked_count < LabSlotTest.capacity,
            LabFacility.is_active.is_(True),
            LabTest.is_active.is_(True),
        )
        .group_by(
            LabSlot.id,
            LabSlot.facility_id,
            LabFacility.name,
            LabSlot.start_at,
            LabSlot.end_at,
            LabSlot.capacity,
            LabSlot.booked_count,
        )
        .order_by(LabSlot.start_at, LabFacility.name)
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    query = discovery_scoped(query, LabSlot, context)
    if facility_id is not None:
        query = query.where(LabSlot.facility_id == facility_id)
    if wanted:
        query = query.where(LabSlotTest.lab_test_id.in_(wanted)).having(
            func.count(distinct(LabSlotTest.lab_test_id)) == len(wanted)
        )

    items = [
        SlotAvailabilityOut(
            slot_id=row["slot_id"],
            facility_id=row["facility_id"],
            facility_name=row["facility_name"],
            start_at=row["start_at"],
            end_at=row["end_at"],
            capacity=row["capacity"],
            booked_count=row["booked_count"],
            slot_remaining=int(row["slot_remaining"]),
            test_remaining=int(row["test_remaining"]),
            remaining=min(int(row["slot_remaining"]), int(row["test_remaining"])),
            offered_test_ids=list(row["offered_test_ids"]),
            matched_test_count=int(row["matched_test_count"]),
            total_price_cents=int(row["total_price_cents"]),
            currency=row["currency"],
        )
        for row in (await db.execute(query)).mappings()
    ]
    return paginate(items, page)


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


async def _claim_slot(
    db: AsyncSession, slot_id: UUID, facility_id: UUID, test_ids: list[UUID]
) -> dict[UUID, int | None]:
    """Take the capacity for one booking under row locks.

    Returns the per-test price override map. Locks are taken slot-first and
    then in ``lab_test_id`` order so concurrent bookings queue rather than
    deadlock.
    """
    slot = await db.scalar(select(LabSlot).where(LabSlot.id == slot_id).with_for_update())
    if slot is None:
        raise not_found("Lab slot")
    if slot.facility_id != facility_id:
        raise unprocessable("The slot belongs to a different facility")
    if slot.status != SlotStatus.OPEN:
        raise conflict("This slot is no longer open")
    if slot.booked_count >= slot.capacity:
        raise conflict("This slot is fully booked")

    slot_tests = (
        await db.scalars(
            select(LabSlotTest)
            .where(LabSlotTest.slot_id == slot_id, LabSlotTest.lab_test_id.in_(test_ids))
            .order_by(LabSlotTest.lab_test_id)
            .with_for_update()
        )
    ).all()
    by_test = {row.lab_test_id: row for row in slot_tests}
    missing = [test_id for test_id in test_ids if test_id not in by_test]
    if missing:
        raise conflict(f"{len(missing)} of the requested tests are not offered in this slot")

    overrides: dict[UUID, int | None] = {}
    for test_id in test_ids:
        slot_test = by_test[test_id]
        if slot_test.booked_count >= slot_test.capacity:
            raise conflict("One of the requested tests is fully booked in this slot")
        slot_test.booked_count += 1
        overrides[test_id] = slot_test.price_cents_override

    slot.booked_count += 1
    if slot.booked_count >= slot.capacity:
        slot.status = SlotStatus.BOOKED
    return overrides


async def _release_slot(db: AsyncSession, order: LabOrder, test_ids: list[UUID]) -> None:
    if order.slot_id is None:
        return
    slot = await db.scalar(select(LabSlot).where(LabSlot.id == order.slot_id).with_for_update())
    if slot is None:
        return
    slot_tests = (
        await db.scalars(
            select(LabSlotTest)
            .where(LabSlotTest.slot_id == slot.id, LabSlotTest.lab_test_id.in_(test_ids))
            .order_by(LabSlotTest.lab_test_id)
            .with_for_update()
        )
    ).all()
    for slot_test in slot_tests:
        slot_test.booked_count = max(0, slot_test.booked_count - 1)
    slot.booked_count = max(0, slot.booked_count - 1)
    if slot.status == SlotStatus.BOOKED and slot.booked_count < slot.capacity:
        slot.status = SlotStatus.OPEN


def _provenance(context: AuthContext) -> ProvenanceSource:
    if context.user.account_type == AccountType.PATIENT:
        return ProvenanceSource.PATIENT_REPORTED
    return ProvenanceSource.PRACTITIONER


async def create_order(
    db: AsyncSession,
    context: AuthContext,
    payload: LabOrderCreate,
    *,
    request: Request | None = None,
    idempotency_key: str | None = None,
    request_digest: str | None = None,
) -> tuple[LabOrderDetail, bool]:
    """Book a lab order. Returns ``(order, replayed)``."""
    patient_user_id = payload.patient_user_id or (context.user.id if is_patient(context) else None)
    if patient_user_id is None:
        raise unprocessable("patient_user_id is required")
    if is_patient(context) and patient_user_id != context.user.id:
        raise forbidden("Patients may only book for themselves")
    await assert_may_read_patient(db, context, patient_user_id)

    record: IdempotencyRecord | None = None
    if idempotency_key and request_digest:
        stored, record = await _replay_idempotent(
            db,
            context,
            operation="labs.create_order",
            key=idempotency_key,
            digest=request_digest,
        )
        if stored is not None:
            return LabOrderDetail.model_validate(stored), True

    patient_exists = await db.scalar(
        select(PatientProfile.user_id).where(PatientProfile.user_id == patient_user_id)
    )
    if patient_exists is None:
        raise not_found("Patient")

    facility = await db.scalar(
        discovery_scoped(select(LabFacility), LabFacility, context).where(
            LabFacility.id == payload.facility_id, LabFacility.is_active.is_(True)
        )
    )
    if facility is None:
        raise not_found("Lab facility")

    tests = (
        await db.scalars(
            discovery_scoped(select(LabTest), LabTest, context).where(
                LabTest.id.in_(payload.test_ids), LabTest.is_active.is_(True)
            )
        )
    ).all()
    by_id = {test.id: test for test in tests}
    unknown = [test_id for test_id in payload.test_ids if test_id not in by_id]
    if unknown:
        raise unprocessable(f"{len(unknown)} requested test(s) are unknown or inactive")
    ordered_tests = [by_id[test_id] for test_id in payload.test_ids]

    overrides: dict[UUID, int | None] = {}
    if payload.slot_id is not None:
        overrides = await _claim_slot(
            db, payload.slot_id, facility.id, sorted(payload.test_ids, key=str)
        )

    now = _now()
    order = LabOrder(
        tenant_id=facility.tenant_id,
        patient_user_id=patient_user_id,
        ordering_provider_user_id=payload.ordering_provider_user_id,
        encounter_id=payload.encounter_id,
        facility_id=facility.id,
        slot_id=payload.slot_id,
        order_number=_reference("LAB"),
        priority=LabPriority(payload.priority),
        status=LabOrderStatus.PLACED,
        requested_at=now,
        note=payload.note,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.ordering_provider_user_id,
        recorded_at=now,
        source=_provenance(context),
    )
    db.add(order)
    await db.flush()

    currencies: set[str] = set()
    priced: list[tuple[LabTest, int]] = []
    for test in ordered_tests:
        price = overrides.get(test.id)
        if price is None:
            price = test.price_cents
        # The catalogue guarantees a currency whenever a price exists; a slot
        # override on an unpriced test therefore cannot be billed.
        line_price = price if test.currency else None
        if line_price is not None:
            currencies.add(str(test.currency))
        db.add(
            LabOrderTest(
                lab_order_id=order.id,
                lab_test_id=test.id,
                status=LabOrderStatus.PLACED,
                price_cents=line_price,
                currency=test.currency if line_price is not None else None,
            )
        )
        priced.append((test, line_price or 0))

    if len(currencies) > 1:
        raise unprocessable("All tests on one order must share a single currency")

    invoice: Invoice | None = None
    if currencies:
        currency = currencies.pop()
        subtotal = sum(amount for _, amount in priced)
        invoice = Invoice(
            tenant_id=facility.tenant_id,
            invoice_number=_reference("INV"),
            payer_user_id=patient_user_id,
            patient_user_id=patient_user_id,
            organization_id=facility.organization_id,
            lab_order_id=order.id,
            status=InvoiceStatus.ISSUED,
            subtotal_cents=subtotal,
            tax_cents=0,
            total_cents=subtotal,
            balance_cents=subtotal,
            currency=currency,
            issued_at=now,
            due_at=now + timedelta(days=14),
        )
        db.add(invoice)
        await db.flush()
        for index, (test, amount) in enumerate(priced, start=1):
            db.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    service_code_system=test.test_code_system,
                    service_code=test.test_code,
                    service_display=test.test_display,
                    description=test.name,
                    quantity=Decimal(1),
                    unit_price_cents=amount,
                    amount_cents=amount,
                    line_number=index,
                )
            )
        order.invoice_id = invoice.id

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="lab_order",
        resource_id=order.id,
        action=PhiAccessAction.READ,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="lab.order.created",
        subject_user_id=patient_user_id,
        resource_id=order.id,
        event_data={
            "order_number": order.order_number,
            "facility_id": str(facility.id),
            "slot_id": str(payload.slot_id) if payload.slot_id else None,
            "test_count": len(ordered_tests),
            "invoice_id": str(invoice.id) if invoice else None,
        },
        request=request,
    )
    await db.flush()

    detail = await _build_detail(db, order)
    if record is not None:
        record.response_status = 201
        record.response_body = detail.model_dump(mode="json")
    await db.commit()
    return detail, False


async def _build_detail(db: AsyncSession, order: LabOrder) -> LabOrderDetail:
    tests = (await _order_test_rows(db, [order.id])).get(order.id, [])
    specimens = (
        await db.scalars(
            select(Specimen)
            .where(Specimen.lab_order_id == order.id)
            .order_by(Specimen.collected_at)
        )
    ).all()
    results = (
        await db.scalars(
            select(LabResult)
            .where(LabResult.lab_order_id == order.id)
            .order_by(LabResult.effective_at, LabResult.test_code)
        )
    ).all()
    base = _order_out(order, len(tests))
    return LabOrderDetail(
        **base.model_dump(),
        tests=tests,
        specimens=[_specimen_out(item) for item in specimens],
        results=[_result_out(item) for item in results],
        invoice=await _invoice_out(db, order.invoice_id),
    )


async def list_orders(
    db: AsyncSession,
    context: AuthContext,
    page: Pagination,
    *,
    status_filter: str | None = None,
    patient_user_id: UUID | None = None,
    facility_id: UUID | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    request: Request | None = None,
) -> Page[LabOrderOut]:
    query = await _order_query(db, context)
    if is_patient(context):
        query = query.where(LabOrder.patient_user_id == context.user.id)
    if patient_user_id is not None:
        query = query.where(LabOrder.patient_user_id == patient_user_id)
    if status_filter:
        if status_filter not in ORDER_TRANSITIONS:
            raise unprocessable(f"Unknown lab order status '{status_filter}'")
        query = query.where(LabOrder.status == LabOrderStatus(status_filter))
    if facility_id is not None:
        query = query.where(LabOrder.facility_id == facility_id)
    if from_at is not None:
        query = query.where(LabOrder.requested_at >= from_at)
    if to_at is not None:
        query = query.where(LabOrder.requested_at < to_at)

    orders = (
        await db.scalars(
            query.order_by(LabOrder.requested_at.desc()).limit(page.limit + 1).offset(page.offset)
        )
    ).all()
    window = list(orders)[: page.limit]
    counts = await _test_counts(db, [order.id for order in window])
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[order.patient_user_id for order in window],
        resource_type="lab_order",
        request=request,
    )
    await db.commit()
    items = [_order_out(order, counts.get(order.id, 0)) for order in orders]
    return paginate(items, page)


async def get_order(
    db: AsyncSession,
    context: AuthContext,
    order_id: UUID,
    *,
    request: Request | None = None,
) -> LabOrderDetail:
    order = await _load_order_for_read(db, context, order_id)
    detail = await _build_detail(db, order)
    await record_phi_access(
        db,
        context,
        patient_user_id=order.patient_user_id,
        resource_type="lab_order",
        resource_id=order.id,
        request=request,
        result_count=len(detail.results),
    )
    await db.commit()
    return detail


async def cancel_order(
    db: AsyncSession,
    context: AuthContext,
    order_id: UUID,
    payload: OrderCancel,
    *,
    request: Request | None = None,
) -> LabOrderDetail:
    order = await _load_order_for_write(db, context, order_id)
    if is_patient(context) and order.patient_user_id != context.user.id:
        raise forbidden("Patients may only cancel their own orders")
    assert_transition(order.status.value, LabOrderStatus.CANCELLED.value, ORDER_TRANSITIONS)

    order_tests = (
        await db.scalars(select(LabOrderTest).where(LabOrderTest.lab_order_id == order.id))
    ).all()
    await _release_slot(db, order, sorted((row.lab_test_id for row in order_tests), key=str))
    for order_test in order_tests:
        order_test.status = LabOrderStatus.CANCELLED
    order.status = LabOrderStatus.CANCELLED

    if order.invoice_id is not None:
        invoice = await db.scalar(select(Invoice).where(Invoice.id == order.invoice_id))
        if invoice is not None and invoice.status in {InvoiceStatus.DRAFT, InvoiceStatus.ISSUED}:
            invoice.status = InvoiceStatus.VOID
            invoice.balance_cents = 0

    await record_phi_access(
        db,
        context,
        patient_user_id=order.patient_user_id,
        resource_type="lab_order",
        resource_id=order.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="lab.order.cancelled",
        subject_user_id=order.patient_user_id,
        resource_id=order.id,
        event_data={"order_number": order.order_number, "reason": payload.reason},
        request=request,
    )
    await db.flush()
    detail = await _build_detail(db, order)
    await db.commit()
    return detail


async def register_specimen(
    db: AsyncSession,
    context: AuthContext,
    order_id: UUID,
    payload: SpecimenCreate,
    *,
    request: Request | None = None,
) -> SpecimenOut:
    order = await _load_order_for_write(db, context, order_id)
    if order.status in {LabOrderStatus.CANCELLED, LabOrderStatus.ENTERED_IN_ERROR}:
        raise conflict(f"Cannot collect against a '{order.status.value}' order")

    code_system = payload.specimen_type_code_system
    code = payload.specimen_type_code
    display = payload.specimen_type_display
    if not (code_system and code and display):
        row = (
            await db.execute(
                select(
                    LabTest.specimen_type_code_system,
                    LabTest.specimen_type_code,
                    LabTest.specimen_type_display,
                )
                .join(LabOrderTest, LabOrderTest.lab_test_id == LabTest.id)
                .where(
                    LabOrderTest.lab_order_id == order.id,
                    LabTest.specimen_type_code.is_not(None),
                )
                .limit(1)
            )
        ).first()
        if row is not None:
            code_system = code_system or row[0]
            code = code or row[1]
            display = display or row[2]
    if not (code_system and code and display):
        raise unprocessable(
            "specimen_type_code_system, specimen_type_code and specimen_type_display are "
            "required because the ordered tests do not declare a specimen type"
        )

    collected_at = payload.collected_at or _now()
    specimen = Specimen(
        tenant_id=order.tenant_id,
        lab_order_id=order.id,
        patient_user_id=order.patient_user_id,
        accession_number=payload.accession_number or _reference("SPC"),
        specimen_type_code_system=code_system,
        specimen_type_code=code,
        specimen_type_display=display,
        collected_at=collected_at,
        collected_by_user_id=payload.collected_by_user_id or context.user.id,
        condition=payload.condition,
        received_at=payload.received_at,
        rejected_reason=payload.rejected_reason,
    )
    db.add(specimen)

    if order.status == LabOrderStatus.PLACED:
        assert_transition(order.status.value, LabOrderStatus.COLLECTED.value, ORDER_TRANSITIONS)
        order.status = LabOrderStatus.COLLECTED
        for order_test in (
            await db.scalars(select(LabOrderTest).where(LabOrderTest.lab_order_id == order.id))
        ).all():
            if order_test.status == LabOrderStatus.PLACED:
                order_test.status = LabOrderStatus.COLLECTED
    if order.collected_at is None:
        order.collected_at = collected_at

    await record_phi_access(
        db,
        context,
        patient_user_id=order.patient_user_id,
        resource_type="specimen",
        resource_id=order.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="lab.specimen.collected",
        subject_user_id=order.patient_user_id,
        resource_id=order.id,
        event_data={
            "order_number": order.order_number,
            "accession_number": specimen.accession_number,
        },
        request=request,
    )
    await db.flush()
    await db.commit()
    return _specimen_out(specimen)


async def enter_results(
    db: AsyncSession,
    context: AuthContext,
    order_id: UUID,
    payload: LabResultsCreate,
    *,
    request: Request | None = None,
) -> list[LabResultOut]:
    order = await _load_order_for_write(db, context, order_id)
    if order.status in {LabOrderStatus.CANCELLED, LabOrderStatus.ENTERED_IN_ERROR}:
        raise conflict(f"Cannot result a '{order.status.value}' order")

    order_tests = (
        await db.scalars(select(LabOrderTest).where(LabOrderTest.lab_order_id == order.id))
    ).all()
    order_test_by_test = {row.lab_test_id: row for row in order_tests}
    catalogue = {
        test.id: test
        for test in (
            await db.scalars(select(LabTest).where(LabTest.id.in_(order_test_by_test.keys())))
        ).all()
    }

    now = _now()
    created: list[LabResult] = []
    critical_count = 0
    for entry in payload.results:
        test = catalogue.get(entry.lab_test_id) if entry.lab_test_id else None
        if entry.lab_test_id is not None and test is None:
            raise unprocessable("A result references a test that is not on this order")
        code_system = entry.test_code_system or (test.test_code_system if test else None)
        code = entry.test_code or (test.test_code if test else None)
        display = entry.test_display or (test.test_display if test else None) or code
        if not (code_system and code and display):
            raise unprocessable("test_code_system, test_code and test_display are required")

        superseded: LabResult | None = None
        if entry.supersedes_id is not None:
            if entry.status not in {
                ObservationStatus.AMENDED.value,
                ObservationStatus.CORRECTED.value,
            }:
                raise unprocessable(
                    "A superseding result must have status 'amended' or 'corrected'"
                )
            superseded = await db.scalar(
                select(LabResult).where(LabResult.id == entry.supersedes_id).with_for_update()
            )
            if superseded is None:
                raise not_found("Superseded lab result")
            if superseded.patient_user_id != order.patient_user_id:
                raise unprocessable("The superseded result belongs to a different patient")
            if superseded.superseded_at is not None:
                raise conflict("That result has already been superseded")

        low = entry.reference_range_low
        high = entry.reference_range_high
        range_text = entry.reference_range_text
        if low is None and high is None and entry.value_numeric is not None:
            low, high, fallback_text = await _fallback_range(db, order.tenant_id, code)
            range_text = range_text or fallback_text
        interpretation, is_critical = interpret(
            entry.value_numeric, low, high, entry.critical_low, entry.critical_high
        )

        verified_by = context.user.id if entry.status in VERIFIED_STATUSES else None
        result = LabResult(
            tenant_id=order.tenant_id,
            lab_order_id=order.id,
            lab_test_id=entry.lab_test_id,
            specimen_id=entry.specimen_id,
            patient_user_id=order.patient_user_id,
            encounter_id=order.encounter_id,
            test_code_system=code_system,
            test_code=code,
            test_display=display,
            test_concept_id=test.test_concept_id if test else None,
            panel_code_system=test.panel_code_system if test else None,
            panel_code=test.panel_code if test else None,
            panel_display=test.panel_display if test else None,
            status=ObservationStatus(entry.status),
            value_numeric=entry.value_numeric,
            value_string=entry.value_string,
            value_code_system=entry.value_code_system,
            value_code=entry.value_code,
            value_display=entry.value_display,
            value_boolean=entry.value_boolean,
            value_comparator=entry.value_comparator,
            unit=entry.unit,
            data_absent_reason=entry.data_absent_reason,
            interpretation_code=interpretation,
            reference_range_low=low,
            reference_range_high=high,
            reference_range_text=range_text,
            is_critical=is_critical,
            critical_notified_at=now if is_critical else None,
            notified_user_id=order.ordering_provider_user_id if is_critical else None,
            performer_user_id=context.user.id,
            verified_by_user_id=verified_by,
            effective_at=entry.effective_at or now,
            issued_at=entry.issued_at or now,
            recorded_by_user_id=context.user.id,
            recorded_at=now,
            source=_provenance(context),
            version=(superseded.version + 1) if superseded else 1,
            supersedes_id=entry.supersedes_id,
            amendment_reason=entry.amendment_reason,
        )
        db.add(result)
        created.append(result)
        if is_critical:
            critical_count += 1
        if superseded is not None:
            superseded.superseded_at = now

        if entry.lab_test_id is not None and entry.status in CLOSING_RESULT_STATUSES:
            order_test = order_test_by_test.get(entry.lab_test_id)
            if order_test is not None:
                order_test.status = LabOrderStatus.RESULTED

    all_resulted = bool(order_tests) and all(
        row.status == LabOrderStatus.RESULTED for row in order_tests
    )
    target = LabOrderStatus.RESULTED if all_resulted else LabOrderStatus.IN_PROCESS
    if order.status != target:
        assert_transition(order.status.value, target.value, ORDER_TRANSITIONS)
        order.status = target

    await record_phi_access(
        db,
        context,
        patient_user_id=order.patient_user_id,
        resource_type="lab_result",
        resource_id=order.id,
        request=request,
        result_count=len(created),
    )
    await write_audit(
        db,
        context,
        event_type="lab.result.entered",
        subject_user_id=order.patient_user_id,
        resource_id=order.id,
        event_data={
            "order_number": order.order_number,
            "result_count": len(created),
            "critical_count": critical_count,
            "order_status": order.status.value,
        },
        request=request,
    )
    await db.flush()
    await db.commit()
    return [_result_out(result) for result in created]


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


async def patient_result_series(
    db: AsyncSession,
    context: AuthContext,
    patient_user_id: UUID,
    *,
    codes: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
    request: Request | None = None,
) -> PatientResultTrend:
    if is_patient(context) and patient_user_id != context.user.id:
        raise forbidden("Patients may only read their own results")
    await assert_may_read_patient(db, context, patient_user_id)

    query = (
        select(LabResult)
        .where(
            LabResult.patient_user_id == patient_user_id,
            LabResult.superseded_at.is_(None),
            LabResult.status.not_in(
                [ObservationStatus.ENTERED_IN_ERROR, ObservationStatus.CANCELLED]
            ),
        )
        .order_by(LabResult.test_code, LabResult.effective_at)
        .limit(limit)
    )
    if codes:
        query = query.where(LabResult.test_code.in_(codes))
    if since is not None:
        query = query.where(LabResult.effective_at >= since)
    if until is not None:
        query = query.where(LabResult.effective_at < until)

    rows = (await db.scalars(query)).all()
    series: dict[str, ResultSeries] = {}
    for row in rows:
        entry = series.get(row.test_code)
        if entry is None:
            entry = ResultSeries(
                test_code_system=row.test_code_system,
                test_code=row.test_code,
                test_display=row.test_display,
                unit=row.unit,
                point_count=0,
                points=[],
            )
            series[row.test_code] = entry
        entry.points.append(
            TrendPoint(
                result_id=row.id,
                effective_at=row.effective_at,
                value_numeric=row.value_numeric,
                value_string=row.value_string,
                value_comparator=row.value_comparator,
                unit=row.unit,
                interpretation_code=row.interpretation_code,
                is_critical=row.is_critical,
                reference_range_low=row.reference_range_low,
                reference_range_high=row.reference_range_high,
                status=row.status.value,
            )
        )
        entry.point_count += 1
        if entry.unit is None:
            entry.unit = row.unit

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="lab_result",
        request=request,
        result_count=len(rows),
    )
    await db.commit()
    return PatientResultTrend(patient_user_id=patient_user_id, series=list(series.values()))


async def acknowledge_result(
    db: AsyncSession,
    context: AuthContext,
    result_id: UUID,
    payload: ResultAcknowledge,
    *,
    request: Request | None = None,
) -> LabResultOut:
    result = await db.scalar(select(LabResult).where(LabResult.id == result_id).with_for_update())
    if result is None:
        raise not_found("Lab result")
    if not (is_admin(context) or result.tenant_id == context.tenant_id):
        allowed = await consent_scoped_patients(db, context)
        if allowed is not None and result.patient_user_id not in allowed:
            raise forbidden("No consent grant covers this patient")
    if not result.is_critical:
        raise unprocessable("Only critical results require acknowledgement")
    if result.acknowledged_at is not None:
        raise conflict("This result has already been acknowledged")

    result.acknowledged_by_user_id = context.user.id
    result.acknowledged_at = _now()
    result.acknowledgement_note = payload.note

    await record_phi_access(
        db,
        context,
        patient_user_id=result.patient_user_id,
        resource_type="lab_result",
        resource_id=result.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="lab.result.acknowledged",
        subject_user_id=result.patient_user_id,
        resource_id=result.id,
        event_data={"test_code": result.test_code, "note": payload.note},
        request=request,
    )
    await db.flush()
    await db.commit()
    return _result_out(result)


async def critical_worklist(
    db: AsyncSession,
    context: AuthContext,
    page: Pagination,
    *,
    facility_id: UUID | None = None,
    ordering_provider_user_id: UUID | None = None,
    since: datetime | None = None,
    request: Request | None = None,
) -> Page[CriticalResultOut]:
    """Unacknowledged panic values for the caller's organisation.

    Matches the ``ix_lab_result_unacked`` partial index: tenant, critical, no
    acknowledgement, ordered oldest first so the longest-outstanding call-back
    is at the top.
    """
    allowed = await consent_scoped_patients(db, context)
    query = (
        select(
            LabResult.id,
            LabResult.patient_user_id,
            LabResult.lab_order_id,
            LabResult.test_code_system,
            LabResult.test_code,
            LabResult.test_display,
            LabResult.value_numeric,
            LabResult.value_string,
            LabResult.unit,
            LabResult.interpretation_code,
            LabResult.status,
            LabResult.effective_at,
            LabResult.critical_notified_at,
            LabResult.notified_user_id,
            LabOrder.order_number,
            LabOrder.ordering_provider_user_id,
            LabOrder.facility_id,
        )
        .select_from(LabResult)
        .outerjoin(LabOrder, LabOrder.id == LabResult.lab_order_id)
        .where(
            LabResult.is_critical.is_(True),
            LabResult.acknowledged_at.is_(None),
            LabResult.superseded_at.is_(None),
            LabResult.status.not_in(
                [ObservationStatus.ENTERED_IN_ERROR, ObservationStatus.CANCELLED]
            ),
        )
        .order_by(LabResult.effective_at)
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    query = tenant_scoped(query, LabResult, context)
    query = apply_patient_scope(query, LabResult, allowed)
    if facility_id is not None:
        query = query.where(LabOrder.facility_id == facility_id)
    if ordering_provider_user_id is not None:
        query = query.where(LabOrder.ordering_provider_user_id == ordering_provider_user_id)
    if since is not None:
        query = query.where(LabResult.effective_at >= since)

    now = _now()
    items: list[CriticalResultOut] = []
    for row in (await db.execute(query)).mappings():
        outstanding = (now - row["effective_at"]).total_seconds() / 3600
        items.append(
            CriticalResultOut(
                id=row["id"],
                patient_user_id=row["patient_user_id"],
                lab_order_id=row["lab_order_id"],
                order_number=row["order_number"],
                ordering_provider_user_id=row["ordering_provider_user_id"],
                facility_id=row["facility_id"],
                test_code_system=row["test_code_system"],
                test_code=row["test_code"],
                test_display=row["test_display"],
                value_numeric=row["value_numeric"],
                value_string=row["value_string"],
                unit=row["unit"],
                interpretation_code=row["interpretation_code"],
                status=row["status"].value,
                effective_at=row["effective_at"],
                critical_notified_at=row["critical_notified_at"],
                notified_user_id=row["notified_user_id"],
                outstanding_hours=Decimal(f"{outstanding:.2f}"),
            )
        )
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[item.patient_user_id for item in items[: page.limit]],
        resource_type="lab_result",
        request=request,
    )
    await db.commit()
    return paginate(items, page)
