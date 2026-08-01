"""Hospital operations, clinical documentation, and administrator oversight.

Three surfaces share this module because they share a spine:

* **Hospital operations** (departments, practitioner credentialing, the
  chargemaster, invoices, payments, refunds) are *operational* tables and are
  therefore ``tenant_scoped``.
* **Clinical documentation** (notes, addenda, encounter codes, referrals) is
  *longitudinal* and therefore consent scoped. Signed notes are immutable at the
  database level: a correction is a new version, an addition is an addendum.
* **Administrator oversight** (support cases, the PHI disclosure log, data
  subject requests, platform analytics) reads across tenants.

Every function that returns patient data appends ``phi_access_events`` rows in
the same transaction as the read, before the commit.
"""

import hashlib
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import Field
from sqlalchemy import Select, case, distinct, func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccountType,
    Appointment,
    AppointmentStatus,
    Claim,
    ClaimStatus,
    ClinicalNote,
    ClinicalNoteAddendum,
    CodeType,
    CommentVisibility,
    DataSubjectRequest,
    Department,
    DoctorProfile,
    DocumentAsset,
    DocumentExtraction,
    DocumentLink,
    DsrStatus,
    DsrType,
    Encounter,
    EncounterCode,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    NoteStatus,
    Organization,
    PatientProfile,
    PayerContractRate,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PhiAccessAction,
    PhiAccessEvent,
    PractitionerRole,
    ProvenanceSource,
    Referral,
    ReferralStatus,
    Refund,
    RefundStatus,
    ReviewStatus,
    ServiceItem,
    SupportCase,
    SupportCaseComment,
    SupportCaseEvent,
    SupportSeverity,
    SupportStatus,
    User,
    UserStatus,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    PurposeOfUse,
    apply_patient_scope,
    assert_may_read_patient,
    assert_transition,
    conflict,
    consent_scoped_patients,
    forbidden,
    is_admin,
    not_found,
    paginate,
    record_phi_access,
    record_phi_access_many,
    tenant_scoped,
    unprocessable,
    write_audit,
)

CURRENCY = r"^[A-Z]{3}$"

CredentialingStatus = Literal["pending", "active", "suspended", "expired", "revoked"]
ContentFormat = Literal["markdown", "plain", "fhir"]
Urgency = Literal["routine", "urgent", "emergent"]

#: Response-time commitment per severity, in hours.
SLA_HOURS: dict[SupportSeverity, int] = {
    SupportSeverity.SEV1: 4,
    SupportSeverity.SEV2: 8,
    SupportSeverity.SEV3: 24,
    SupportSeverity.SEV4: 72,
}

SUPPORT_TRANSITIONS: dict[str, set[str]] = {
    SupportStatus.NEW: {
        SupportStatus.TRIAGED,
        SupportStatus.IN_PROGRESS,
        SupportStatus.ESCALATED,
        SupportStatus.RESOLVED,
        SupportStatus.CLOSED,
    },
    SupportStatus.TRIAGED: {
        SupportStatus.IN_PROGRESS,
        SupportStatus.WAITING_CUSTOMER,
        SupportStatus.ESCALATED,
        SupportStatus.RESOLVED,
        SupportStatus.CLOSED,
    },
    SupportStatus.IN_PROGRESS: {
        SupportStatus.WAITING_CUSTOMER,
        SupportStatus.ESCALATED,
        SupportStatus.RESOLVED,
        SupportStatus.CLOSED,
    },
    SupportStatus.WAITING_CUSTOMER: {
        SupportStatus.IN_PROGRESS,
        SupportStatus.ESCALATED,
        SupportStatus.RESOLVED,
        SupportStatus.CLOSED,
    },
    SupportStatus.ESCALATED: {
        SupportStatus.IN_PROGRESS,
        SupportStatus.WAITING_CUSTOMER,
        SupportStatus.RESOLVED,
        SupportStatus.CLOSED,
    },
    SupportStatus.RESOLVED: {SupportStatus.CLOSED, SupportStatus.IN_PROGRESS},
    SupportStatus.CLOSED: set(),
}

REFERRAL_TRANSITIONS: dict[str, set[str]] = {
    ReferralStatus.DRAFT: {ReferralStatus.SENT, ReferralStatus.EXPIRED},
    ReferralStatus.SENT: {
        ReferralStatus.ACCEPTED,
        ReferralStatus.DECLINED,
        ReferralStatus.EXPIRED,
    },
    ReferralStatus.ACCEPTED: {
        ReferralStatus.SCHEDULED,
        ReferralStatus.COMPLETED,
        ReferralStatus.EXPIRED,
    },
    ReferralStatus.SCHEDULED: {ReferralStatus.COMPLETED, ReferralStatus.EXPIRED},
    ReferralStatus.DECLINED: set(),
    ReferralStatus.COMPLETED: set(),
    ReferralStatus.EXPIRED: set(),
}

DSR_TRANSITIONS: dict[str, set[str]] = {
    DsrStatus.RECEIVED: {
        DsrStatus.VERIFYING,
        DsrStatus.IN_PROGRESS,
        DsrStatus.FULFILLED,
        DsrStatus.REFUSED,
        DsrStatus.WITHDRAWN,
    },
    DsrStatus.VERIFYING: {
        DsrStatus.IN_PROGRESS,
        DsrStatus.FULFILLED,
        DsrStatus.REFUSED,
        DsrStatus.WITHDRAWN,
    },
    DsrStatus.IN_PROGRESS: {DsrStatus.FULFILLED, DsrStatus.REFUSED, DsrStatus.WITHDRAWN},
    DsrStatus.FULFILLED: set(),
    DsrStatus.REFUSED: set(),
    DsrStatus.WITHDRAWN: set(),
}

# ---------------------------------------------------------------------------
# Schemas: hospital directory and chargemaster
# ---------------------------------------------------------------------------


class DepartmentCreate(DomainModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    organization_id: UUID | None = None
    parent_department_id: UUID | None = None
    cost_center: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class DepartmentUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_department_id: UUID | None = None
    cost_center: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class DepartmentOut(DomainModel):
    id: UUID
    organization_id: UUID
    code: str
    name: str
    parent_department_id: UUID | None
    cost_center: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PractitionerRoleCreate(DomainModel):
    practitioner_user_id: UUID
    role_code: str = Field(min_length=1, max_length=64)
    organization_id: UUID | None = None
    department_id: UUID | None = None
    specialty_code: str | None = Field(default=None, max_length=64)
    taxonomy_code: str | None = Field(default=None, max_length=32)
    privileges: list[str] = Field(default_factory=list)
    credentialing_status: CredentialingStatus = "pending"
    credentialed_at: date | None = None
    credential_expires_at: date | None = None
    accepts_new_patients: bool = True
    is_active: bool = True


class PractitionerRoleUpdate(DomainModel):
    department_id: UUID | None = None
    specialty_code: str | None = Field(default=None, max_length=64)
    taxonomy_code: str | None = Field(default=None, max_length=32)
    privileges: list[str] | None = None
    credentialing_status: CredentialingStatus | None = None
    credentialed_at: date | None = None
    credential_expires_at: date | None = None
    accepts_new_patients: bool | None = None
    is_active: bool | None = None


class PractitionerRoleOut(DomainModel):
    id: UUID
    practitioner_user_id: UUID
    practitioner_name: str
    license_number: str
    organization_id: UUID
    department_id: UUID | None
    role_code: str
    specialty_code: str | None
    taxonomy_code: str | None
    privileges: list[str]
    credentialing_status: str
    credentialed_at: date | None
    credential_expires_at: date | None
    days_until_expiry: int | None
    accepts_new_patients: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ServiceItemCreate(DomainModel):
    service_code_system: str = Field(min_length=1, max_length=128)
    service_code: str = Field(min_length=1, max_length=64)
    service_display: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=500)
    base_price_cents: int = Field(ge=0)
    currency: str = Field(pattern=CURRENCY)
    effective_from: date
    organization_id: UUID | None = None
    department_id: UUID | None = None
    service_concept_id: UUID | None = None
    cpt_code: str | None = Field(default=None, max_length=16)
    revenue_code: str | None = Field(default=None, max_length=16)
    effective_to: date | None = None
    is_active: bool = True


class ServiceItemUpdate(DomainModel):
    service_display: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    base_price_cents: int | None = Field(default=None, ge=0)
    department_id: UUID | None = None
    cpt_code: str | None = Field(default=None, max_length=16)
    revenue_code: str | None = Field(default=None, max_length=16)
    effective_to: date | None = None
    is_active: bool | None = None


class ServiceItemOut(DomainModel):
    id: UUID
    organization_id: UUID
    department_id: UUID | None
    service_code_system: str
    service_code: str
    service_display: str
    description: str
    cpt_code: str | None
    revenue_code: str | None
    base_price_cents: int
    currency: str
    effective_from: date
    effective_to: date | None
    is_active: bool
    contracted_payer_count: int
    best_allowed_cents: int | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Schemas: revenue cycle
# ---------------------------------------------------------------------------


class InvoiceLineOut(DomainModel):
    id: UUID
    line_number: int
    service_item_id: UUID | None
    service_code: str | None
    service_display: str | None
    description: str
    quantity: float
    unit_price_cents: int
    amount_cents: int


class PaymentOut(DomainModel):
    id: UUID
    invoice_id: UUID
    payer_user_id: UUID
    method: PaymentMethod
    amount_cents: int
    currency: str
    status: PaymentStatus
    processor: str
    processor_intent_id: str | None
    processor_charge_id: str | None
    authorized_at: datetime | None
    captured_at: datetime | None
    failure_code: str | None
    created_at: datetime


class RefundOut(DomainModel):
    id: UUID
    payment_id: UUID
    amount_cents: int
    currency: str
    reason: str
    status: RefundStatus
    processor_refund_id: str | None
    refunded_at: datetime | None
    created_at: datetime


class DocumentLinkOut(DomainModel):
    id: UUID
    document_asset_id: UUID
    subject_type: str
    subject_id: UUID
    link_type: str
    filename: str
    content_type: str
    byte_size: int
    linked_by_user_id: UUID
    created_at: datetime


class InvoiceOut(DomainModel):
    id: UUID
    invoice_number: str
    organization_id: UUID
    payer_user_id: UUID
    patient_user_id: UUID | None
    appointment_id: UUID | None
    lab_order_id: UUID | None
    policy_id: UUID | None
    status: InvoiceStatus
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    balance_cents: int
    paid_cents: int
    refunded_cents: int
    currency: str
    issued_at: datetime | None
    due_at: datetime | None
    days_outstanding: int | None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailOut(DomainModel):
    invoice: InvoiceOut
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]
    refunds: list[RefundOut]
    documents: list[DocumentLinkOut]


class PaymentCreate(DomainModel):
    method: PaymentMethod
    amount_cents: int = Field(gt=0)
    currency: str = Field(pattern=CURRENCY)
    idempotency_key: str = Field(min_length=8, max_length=255)
    processor: str = Field(default="manual", min_length=1, max_length=32)
    processor_intent_id: str | None = Field(default=None, max_length=255)
    processor_charge_id: str | None = Field(default=None, max_length=255)


class PaymentResult(DomainModel):
    payment: PaymentOut
    invoice: InvoiceOut
    replayed: bool


class RefundCreate(DomainModel):
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=255)
    processor_refund_id: str | None = Field(default=None, max_length=255)


class RefundResult(DomainModel):
    refund: RefundOut
    payment: PaymentOut
    invoice: InvoiceOut


class AgingBucket(DomainModel):
    bucket: str
    invoice_count: int
    balance_cents: int


class StatusBucket(DomainModel):
    key: str
    count: int
    amount_cents: int


class ClaimDenialStats(DomainModel):
    submitted_count: int
    denied_count: int
    denial_rate: float
    denied_charge_cents: int
    paid_cents: int


class RevenueCycleSummary(DomainModel):
    window_from: datetime
    window_to: datetime
    currency: str | None
    billed_cents: int
    collected_cents: int
    refunded_cents: int
    outstanding_cents: int
    collection_rate: float
    invoice_count: int
    aging: list[AgingBucket]
    invoices_by_status: list[StatusBucket]
    claims: ClaimDenialStats


# ---------------------------------------------------------------------------
# Schemas: clinical documentation
# ---------------------------------------------------------------------------


class ExtractionSummary(DomainModel):
    id: UUID
    document_asset_id: UUID
    extraction_schema: str
    schema_version: str
    overall_confidence: float | None
    validation_status: ReviewStatus
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None


class AddendumOut(DomainModel):
    id: UUID
    clinical_note_id: UUID
    author_user_id: UUID
    content: str
    sequence: int
    signed_at: datetime
    signature_hash: str
    created_at: datetime


class ClinicalNoteOut(DomainModel):
    id: UUID
    encounter_id: UUID
    patient_user_id: UUID
    author_user_id: UUID
    note_type_code: str
    title: str
    content: str
    content_format: str
    status: NoteStatus
    signed_at: datetime | None
    signed_by_user_id: UUID | None
    cosigner_user_id: UUID | None
    cosigned_at: datetime | None
    signature_hash: str | None
    source: ProvenanceSource
    source_document_id: UUID | None
    extraction_confidence: float | None
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None
    amendment_reason: str | None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    addenda: list[AddendumOut]
    extraction: ExtractionSummary | None


class ClinicalNoteCreate(DomainModel):
    note_type_code: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    content_format: ContentFormat = "markdown"
    source: ProvenanceSource = ProvenanceSource.PRACTITIONER
    source_document_id: UUID | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    supersedes_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=500)


class NoteSignRequest(DomainModel):
    cosigner_user_id: UUID | None = None


class AddendumCreate(DomainModel):
    content: str = Field(min_length=1)


class EncounterCodeCreate(DomainModel):
    billing_code_system: str = Field(min_length=1, max_length=128)
    billing_code: str = Field(min_length=1, max_length=64)
    billing_display: str = Field(min_length=1, max_length=255)
    code_type: CodeType
    billing_concept_id: UUID | None = None
    rank: int | None = Field(default=None, ge=1)
    modifiers: list[str] = Field(default_factory=list)
    units: int = Field(default=1, ge=1)
    source: ProvenanceSource = ProvenanceSource.PRACTITIONER
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: ReviewStatus = ReviewStatus.PENDING


class EncounterCodeOut(DomainModel):
    id: UUID
    encounter_id: UUID
    patient_user_id: UUID
    billing_code_system: str
    billing_code: str
    billing_display: str
    billing_concept_id: UUID | None
    code_type: CodeType
    rank: int
    modifiers: list[str]
    units: int
    coder_user_id: UUID | None
    source: ProvenanceSource
    confidence: float | None
    review_status: ReviewStatus
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReferralCreate(DomainModel):
    patient_user_id: UUID
    specialty_code: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1)
    urgency: Urgency = "routine"
    referring_provider_user_id: UUID | None = None
    referring_organization_id: UUID | None = None
    receiving_provider_user_id: UUID | None = None
    receiving_organization_id: UUID | None = None
    encounter_id: UUID | None = None
    expires_at: datetime | None = None
    send: bool = False


class ReferralStatusChange(DomainModel):
    status: ReferralStatus
    reason: str | None = Field(default=None, max_length=2000)
    receiving_provider_user_id: UUID | None = None
    receiving_organization_id: UUID | None = None
    appointment_id: UUID | None = None


class ReferralOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    referring_provider_user_id: UUID
    referring_organization_id: UUID
    receiving_provider_user_id: UUID | None
    receiving_organization_id: UUID | None
    encounter_id: UUID | None
    specialty_code: str
    urgency: str
    reason: str
    status: ReferralStatus
    prior_authorization_id: UUID | None
    appointment_id: UUID | None
    expires_at: datetime | None
    feedback_note: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Schemas: administrator oversight
# ---------------------------------------------------------------------------


class SupportCaseCreate(DomainModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=64)
    severity: SupportSeverity = SupportSeverity.SEV3
    queue: str = Field(default="general", min_length=1, max_length=64)
    requester_user_id: UUID | None = None
    assignee_user_id: UUID | None = None
    related_record_type: str | None = Field(default=None, max_length=64)
    related_record_id: UUID | None = None


class SupportCaseOut(DomainModel):
    id: UUID
    case_number: str
    subject: str
    description: str
    category: str
    severity: SupportSeverity
    status: SupportStatus
    queue: str
    requester_user_id: UUID
    assignee_user_id: UUID | None
    sla_due_at: datetime
    sla_breached: bool
    first_response_at: datetime | None
    resolved_at: datetime | None
    escalated_at: datetime | None
    escalation_level: int
    related_record_type: str | None
    related_record_id: UUID | None
    comment_count: int
    created_at: datetime
    updated_at: datetime


class SupportCommentCreate(DomainModel):
    body: str = Field(min_length=1)
    visibility: CommentVisibility = CommentVisibility.INTERNAL


class SupportCommentOut(DomainModel):
    id: UUID
    case_id: UUID
    author_user_id: UUID
    body: str
    visibility: CommentVisibility
    created_at: datetime


class SupportTransitionRequest(DomainModel):
    status: SupportStatus
    reason: str | None = Field(default=None, max_length=255)
    assignee_user_id: UUID | None = None


class SupportEscalateRequest(DomainModel):
    reason: str = Field(min_length=1, max_length=255)
    severity: SupportSeverity | None = None
    assignee_user_id: UUID | None = None


class SupportEventOut(DomainModel):
    id: UUID
    case_id: UUID
    from_status: str | None
    to_status: str
    actor_user_id: UUID
    reason: str | None
    occurred_at: datetime


class SupportCaseResult(DomainModel):
    case: SupportCaseOut
    event: SupportEventOut


class PhiAccessOut(DomainModel):
    id: UUID
    tenant_id: UUID
    actor_user_id: UUID
    actor_email: str
    actor_account_type: AccountType
    patient_user_id: UUID
    resource_type: str
    resource_id: UUID | None
    action: PhiAccessAction
    purpose_of_use: str
    consent_grant_id: UUID | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    result_count: int | None
    created_at: datetime


class BreakGlassEntry(DomainModel):
    actor_user_id: UUID
    actor_email: str
    patient_user_id: UUID
    event_count: int
    resource_types: list[str]
    first_access_at: datetime
    last_access_at: datetime


class DataSubjectRequestCreate(DomainModel):
    subject_user_id: UUID
    request_type: DsrType
    due_at: datetime | None = None
    notes: str | None = None


class DataSubjectRequestFulfil(DomainModel):
    export_document_asset_id: UUID | None = None
    notes: str | None = None


class DataSubjectRequestOut(DomainModel):
    id: UUID
    subject_user_id: UUID
    request_type: DsrType
    status: DsrStatus
    received_at: datetime
    due_at: datetime
    verified_at: datetime | None
    fulfilled_at: datetime | None
    refusal_reason: str | None
    handled_by_user_id: UUID | None
    export_document_asset_id: UUID | None
    notes: str | None
    overdue: bool
    created_at: datetime
    updated_at: datetime


class RoleActivity(DomainModel):
    account_type: AccountType
    total_users: int
    active_users: int
    signed_in_users: int


class CountBucket(DomainModel):
    key: str
    count: int


class ClaimActivity(DomainModel):
    claim_count: int
    denied_count: int
    denial_rate: float
    charged_cents: int
    paid_cents: int
    by_status: list[CountBucket]


class PlatformAnalytics(DomainModel):
    window_from: datetime
    window_to: datetime
    roles: list[RoleActivity]
    encounter_count: int
    encounters_by_status: list[CountBucket]
    appointment_count: int
    appointments_by_status: list[CountBucket]
    no_show_rate: float
    claims: ClaimActivity
    open_support_cases: int
    breached_support_cases: int
    phi_access_events: int
    break_glass_events: int


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _count(db: AsyncSession, query: Select[Any]) -> int:
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return int(total or 0)


async def _organization_for(db: AsyncSession, context: AuthContext, requested: UUID | None) -> UUID:
    """Resolve the organization a hospital write targets, tenant-checked."""
    organization_id = requested or context.tenant_id
    if not is_admin(context) and organization_id != context.tenant_id:
        raise forbidden("Cannot manage another organization")
    known = await db.scalar(select(Organization.id).where(Organization.id == organization_id))
    if known is None:
        raise unprocessable("Unknown organization")
    return organization_id


async def _patient_subjects(db: AsyncSession, ids: Iterable[UUID | None]) -> list[UUID]:
    """Narrow a mixed list of user ids to the ones that are patients.

    ``phi_access_events.patient_user_id`` is a foreign key onto
    ``patient_profiles``, so a disclosure row may only be written for a real
    patient.
    """
    candidates = {value for value in ids if value is not None}
    if not candidates:
        return []
    rows = await db.scalars(
        select(PatientProfile.user_id).where(PatientProfile.user_id.in_(candidates))
    )
    return list(rows.all())


async def _log_patient_reads(
    db: AsyncSession,
    context: AuthContext,
    *,
    ids: Iterable[UUID | None],
    resource_type: str,
    purpose_of_use: PurposeOfUse,
    request: Request | None,
) -> None:
    patients = await _patient_subjects(db, ids)
    if patients:
        await record_phi_access_many(
            db,
            context,
            patient_user_ids=patients,
            resource_type=resource_type,
            purpose_of_use=purpose_of_use,
            request=request,
        )


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------


async def list_departments(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    is_active: bool | None = None,
    search: str | None = None,
) -> Page[DepartmentOut]:
    query = tenant_scoped(select(Department), Department, context)
    if is_active is not None:
        query = query.where(Department.is_active.is_(is_active))
    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(func.lower(Department.name).like(term), func.lower(Department.code).like(term))
        )
    total = await _count(db, query)
    rows = await db.scalars(
        query.order_by(Department.name).limit(page.limit + 1).offset(page.offset)
    )
    return paginate([DepartmentOut.model_validate(row) for row in rows.all()], page, total)


async def _get_department(
    db: AsyncSession, context: AuthContext, department_id: UUID
) -> Department:
    query = tenant_scoped(select(Department), Department, context).where(
        Department.id == department_id
    )
    department = await db.scalar(query)
    if department is None:
        raise not_found("Department")
    return department


async def create_department(
    db: AsyncSession,
    context: AuthContext,
    payload: DepartmentCreate,
    request: Request | None = None,
) -> DepartmentOut:
    organization_id = await _organization_for(db, context, payload.organization_id)
    duplicate = await db.scalar(
        select(Department.id).where(
            Department.organization_id == organization_id, Department.code == payload.code
        )
    )
    if duplicate is not None:
        raise conflict(f"Department code '{payload.code}' already exists")
    if payload.parent_department_id is not None:
        parent = await db.scalar(
            select(Department.id).where(
                Department.id == payload.parent_department_id,
                Department.organization_id == organization_id,
            )
        )
        if parent is None:
            raise unprocessable("Parent department belongs to another organization")

    department = Department(
        tenant_id=organization_id,
        organization_id=organization_id,
        code=payload.code,
        name=payload.name,
        parent_department_id=payload.parent_department_id,
        cost_center=payload.cost_center,
        is_active=payload.is_active,
    )
    db.add(department)
    await db.flush()
    await write_audit(
        db,
        context,
        event_type="operations.department.created",
        resource_id=department.id,
        event_data={"code": payload.code, "organization_id": str(organization_id)},
        request=request,
    )
    await db.commit()
    await db.refresh(department)
    return DepartmentOut.model_validate(department)


async def update_department(
    db: AsyncSession,
    context: AuthContext,
    department_id: UUID,
    payload: DepartmentUpdate,
    request: Request | None = None,
) -> DepartmentOut:
    department = await _get_department(db, context, department_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise unprocessable("No fields to update")
    if changes.get("parent_department_id") == department.id:
        raise unprocessable("A department cannot be its own parent")
    for field, value in changes.items():
        setattr(department, field, value)
    await write_audit(
        db,
        context,
        event_type="operations.department.updated",
        resource_id=department.id,
        event_data={"fields": sorted(changes)},
        request=request,
    )
    await db.commit()
    await db.refresh(department)
    return DepartmentOut.model_validate(department)


# ---------------------------------------------------------------------------
# Practitioner roles / credentialing
# ---------------------------------------------------------------------------


def _practitioner_out(
    role: PractitionerRole, first_name: str, last_name: str, license_number: str
) -> PractitionerRoleOut:
    expires = role.credential_expires_at
    return PractitionerRoleOut(
        id=role.id,
        practitioner_user_id=role.practitioner_user_id,
        practitioner_name=f"Dr. {first_name} {last_name}",
        license_number=license_number,
        organization_id=role.organization_id,
        department_id=role.department_id,
        role_code=role.role_code,
        specialty_code=role.specialty_code,
        taxonomy_code=role.taxonomy_code,
        privileges=list(role.privileges),
        credentialing_status=role.credentialing_status,
        credentialed_at=role.credentialed_at,
        credential_expires_at=expires,
        days_until_expiry=(expires - _now().date()).days if expires is not None else None,
        accepts_new_patients=role.accepts_new_patients,
        is_active=role.is_active,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


async def list_practitioners(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    credentialing_status: CredentialingStatus | None = None,
    expiring_within_days: int | None = None,
    department_id: UUID | None = None,
    specialty_code: str | None = None,
    is_active: bool | None = None,
) -> Page[PractitionerRoleOut]:
    query = tenant_scoped(select(PractitionerRole), PractitionerRole, context)
    if credentialing_status is not None:
        query = query.where(PractitionerRole.credentialing_status == credentialing_status)
    if expiring_within_days is not None:
        cutoff = _now().date() + timedelta(days=expiring_within_days)
        query = query.where(
            PractitionerRole.credential_expires_at.is_not(None),
            PractitionerRole.credential_expires_at <= cutoff,
        )
    if department_id is not None:
        query = query.where(PractitionerRole.department_id == department_id)
    if specialty_code is not None:
        query = query.where(PractitionerRole.specialty_code == specialty_code)
    if is_active is not None:
        query = query.where(PractitionerRole.is_active.is_(is_active))

    total = await _count(db, query)
    listing: Select[Any] = (
        query.join(DoctorProfile, DoctorProfile.user_id == PractitionerRole.practitioner_user_id)
        .add_columns(
            DoctorProfile.first_name, DoctorProfile.last_name, DoctorProfile.license_number
        )
        .order_by(nulls_last(PractitionerRole.credential_expires_at.asc()), DoctorProfile.last_name)
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = (await db.execute(listing)).all()
    items = [
        _practitioner_out(role, first_name, last_name, license_number)
        for role, first_name, last_name, license_number in rows
    ]
    return paginate(items, page, total)


async def _practitioner_view(db: AsyncSession, role: PractitionerRole) -> PractitionerRoleOut:
    profile = await db.scalar(
        select(DoctorProfile).where(DoctorProfile.user_id == role.practitioner_user_id)
    )
    if profile is None:
        raise unprocessable("Practitioner has no doctor profile")
    return _practitioner_out(role, profile.first_name, profile.last_name, profile.license_number)


async def create_practitioner_role(
    db: AsyncSession,
    context: AuthContext,
    payload: PractitionerRoleCreate,
    request: Request | None = None,
) -> PractitionerRoleOut:
    organization_id = await _organization_for(db, context, payload.organization_id)
    profile = await db.scalar(
        select(DoctorProfile).where(DoctorProfile.user_id == payload.practitioner_user_id)
    )
    if profile is None:
        raise unprocessable("Unknown practitioner")
    if payload.department_id is not None:
        department = await db.scalar(
            select(Department.id).where(
                Department.id == payload.department_id,
                Department.organization_id == organization_id,
            )
        )
        if department is None:
            raise unprocessable("Department belongs to another organization")
    duplicate = await db.scalar(
        select(PractitionerRole.id).where(
            PractitionerRole.practitioner_user_id == payload.practitioner_user_id,
            PractitionerRole.organization_id == organization_id,
            PractitionerRole.role_code == payload.role_code,
        )
    )
    if duplicate is not None:
        raise conflict("This practitioner already holds that role here")

    role = PractitionerRole(
        tenant_id=organization_id,
        practitioner_user_id=payload.practitioner_user_id,
        organization_id=organization_id,
        department_id=payload.department_id,
        role_code=payload.role_code,
        specialty_code=payload.specialty_code,
        taxonomy_code=payload.taxonomy_code,
        privileges=payload.privileges,
        credentialing_status=payload.credentialing_status,
        credentialed_at=payload.credentialed_at,
        credential_expires_at=payload.credential_expires_at,
        accepts_new_patients=payload.accepts_new_patients,
        is_active=payload.is_active,
    )
    db.add(role)
    await db.flush()
    await write_audit(
        db,
        context,
        event_type="operations.practitioner_role.created",
        subject_user_id=payload.practitioner_user_id,
        resource_id=role.id,
        event_data={
            "role_code": payload.role_code,
            "credentialing_status": payload.credentialing_status,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(role)
    return _practitioner_out(role, profile.first_name, profile.last_name, profile.license_number)


async def update_practitioner_role(
    db: AsyncSession,
    context: AuthContext,
    role_id: UUID,
    payload: PractitionerRoleUpdate,
    request: Request | None = None,
) -> PractitionerRoleOut:
    query = tenant_scoped(select(PractitionerRole), PractitionerRole, context).where(
        PractitionerRole.id == role_id
    )
    role = await db.scalar(query)
    if role is None:
        raise not_found("Practitioner role")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise unprocessable("No fields to update")
    if "department_id" in changes and changes["department_id"] is not None:
        department = await db.scalar(
            select(Department.id).where(
                Department.id == changes["department_id"],
                Department.organization_id == role.organization_id,
            )
        )
        if department is None:
            raise unprocessable("Department belongs to another organization")
    previous_status = role.credentialing_status
    for field, value in changes.items():
        setattr(role, field, value)
    await write_audit(
        db,
        context,
        event_type="operations.practitioner_role.updated",
        subject_user_id=role.practitioner_user_id,
        resource_id=role.id,
        event_data={
            "fields": sorted(changes),
            "credentialing_status_from": previous_status,
            "credentialing_status_to": role.credentialing_status,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(role)
    return await _practitioner_view(db, role)


# ---------------------------------------------------------------------------
# Service catalogue (chargemaster)
# ---------------------------------------------------------------------------


async def _contract_rate_stats(
    db: AsyncSession, items: Sequence[ServiceItem]
) -> dict[str, tuple[int, int | None]]:
    """Payer coverage per service code: (payer count, best allowed amount)."""
    codes = {item.service_code for item in items}
    organizations = {item.organization_id for item in items}
    if not codes:
        return {}
    rows = (
        await db.execute(
            select(
                PayerContractRate.service_code,
                func.count(distinct(PayerContractRate.payer_organization_id)),
                func.max(PayerContractRate.allowed_cents),
            )
            .where(
                PayerContractRate.service_code.in_(codes),
                PayerContractRate.provider_organization_id.in_(organizations),
            )
            .group_by(PayerContractRate.service_code)
        )
    ).all()
    return {str(row[0]): (int(row[1]), None if row[2] is None else int(row[2])) for row in rows}


def _service_item_out(item: ServiceItem, stats: tuple[int, int | None] | None) -> ServiceItemOut:
    payer_count, best_allowed = stats or (0, None)
    return ServiceItemOut(
        id=item.id,
        organization_id=item.organization_id,
        department_id=item.department_id,
        service_code_system=item.service_code_system,
        service_code=item.service_code,
        service_display=item.service_display,
        description=item.description,
        cpt_code=item.cpt_code,
        revenue_code=item.revenue_code,
        base_price_cents=item.base_price_cents,
        currency=item.currency,
        effective_from=item.effective_from,
        effective_to=item.effective_to,
        is_active=item.is_active,
        contracted_payer_count=payer_count,
        best_allowed_cents=best_allowed,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def list_service_items(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    service_code: str | None = None,
    department_id: UUID | None = None,
    effective_on: date | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> Page[ServiceItemOut]:
    query = tenant_scoped(select(ServiceItem), ServiceItem, context)
    if service_code is not None:
        query = query.where(ServiceItem.service_code == service_code)
    if department_id is not None:
        query = query.where(ServiceItem.department_id == department_id)
    if is_active is not None:
        query = query.where(ServiceItem.is_active.is_(is_active))
    if effective_on is not None:
        query = query.where(
            ServiceItem.effective_from <= effective_on,
            or_(
                ServiceItem.effective_to.is_(None),
                ServiceItem.effective_to >= effective_on,
            ),
        )
    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(ServiceItem.service_display).like(term),
                func.lower(ServiceItem.service_code).like(term),
            )
        )
    total = await _count(db, query)
    items = list(
        (
            await db.scalars(
                query.order_by(ServiceItem.service_code, ServiceItem.effective_from.desc())
                .limit(page.limit + 1)
                .offset(page.offset)
            )
        ).all()
    )
    stats = await _contract_rate_stats(db, items)
    return paginate(
        [_service_item_out(item, stats.get(item.service_code)) for item in items], page, total
    )


async def create_service_item(
    db: AsyncSession,
    context: AuthContext,
    payload: ServiceItemCreate,
    request: Request | None = None,
) -> ServiceItemOut:
    organization_id = await _organization_for(db, context, payload.organization_id)
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise unprocessable("effective_to must not precede effective_from")
    duplicate = await db.scalar(
        select(ServiceItem.id).where(
            ServiceItem.organization_id == organization_id,
            ServiceItem.service_code == payload.service_code,
            ServiceItem.effective_from == payload.effective_from,
        )
    )
    if duplicate is not None:
        raise conflict("A chargemaster entry with that code and effective date already exists")

    item = ServiceItem(
        tenant_id=organization_id,
        organization_id=organization_id,
        department_id=payload.department_id,
        service_code_system=payload.service_code_system,
        service_code=payload.service_code,
        service_display=payload.service_display,
        service_concept_id=payload.service_concept_id,
        description=payload.description,
        cpt_code=payload.cpt_code,
        revenue_code=payload.revenue_code,
        base_price_cents=payload.base_price_cents,
        currency=payload.currency,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_active=payload.is_active,
    )
    db.add(item)
    await db.flush()
    await write_audit(
        db,
        context,
        event_type="operations.service_item.created",
        resource_id=item.id,
        event_data={
            "service_code": payload.service_code,
            "base_price_cents": payload.base_price_cents,
            "currency": payload.currency,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    stats = await _contract_rate_stats(db, [item])
    return _service_item_out(item, stats.get(item.service_code))


async def update_service_item(
    db: AsyncSession,
    context: AuthContext,
    service_item_id: UUID,
    payload: ServiceItemUpdate,
    request: Request | None = None,
) -> ServiceItemOut:
    query = tenant_scoped(select(ServiceItem), ServiceItem, context).where(
        ServiceItem.id == service_item_id
    )
    item = await db.scalar(query)
    if item is None:
        raise not_found("Service item")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise unprocessable("No fields to update")
    effective_to = changes.get("effective_to", item.effective_to)
    if effective_to is not None and effective_to < item.effective_from:
        raise unprocessable("effective_to must not precede effective_from")
    previous_price = item.base_price_cents
    for field, value in changes.items():
        setattr(item, field, value)
    await write_audit(
        db,
        context,
        event_type="operations.service_item.updated",
        resource_id=item.id,
        event_data={
            "fields": sorted(changes),
            "base_price_cents_from": previous_price,
            "base_price_cents_to": item.base_price_cents,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    stats = await _contract_rate_stats(db, [item])
    return _service_item_out(item, stats.get(item.service_code))


# ---------------------------------------------------------------------------
# Invoices, payments, refunds
# ---------------------------------------------------------------------------


async def _payment_totals(
    db: AsyncSession, invoice_ids: Sequence[UUID]
) -> dict[UUID, tuple[int, int]]:
    """(captured cents, refunded cents) per invoice, aggregated in SQL."""
    if not invoice_ids:
        return {}
    totals: dict[UUID, tuple[int, int]] = {}
    captured = (
        await db.execute(
            select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount_cents), 0))
            .where(
                Payment.invoice_id.in_(invoice_ids),
                Payment.status.in_([PaymentStatus.CAPTURED, PaymentStatus.REFUNDED]),
            )
            .group_by(Payment.invoice_id)
        )
    ).all()
    for row in captured:
        totals[row[0]] = (int(row[1]), 0)
    refunded = (
        await db.execute(
            select(Payment.invoice_id, func.coalesce(func.sum(Refund.amount_cents), 0))
            .join(Refund, Refund.payment_id == Payment.id)
            .where(
                Payment.invoice_id.in_(invoice_ids),
                Refund.status == RefundStatus.SUCCEEDED,
            )
            .group_by(Payment.invoice_id)
        )
    ).all()
    for row in refunded:
        paid, _ = totals.get(row[0], (0, 0))
        totals[row[0]] = (paid, int(row[1]))
    return totals


def _invoice_out(invoice: Invoice, paid_cents: int, refunded_cents: int) -> InvoiceOut:
    days_outstanding: int | None = None
    if invoice.issued_at is not None and invoice.balance_cents > 0:
        days_outstanding = max((_now() - invoice.issued_at).days, 0)
    return InvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        organization_id=invoice.organization_id,
        payer_user_id=invoice.payer_user_id,
        patient_user_id=invoice.patient_user_id,
        appointment_id=invoice.appointment_id,
        lab_order_id=invoice.lab_order_id,
        policy_id=invoice.policy_id,
        status=invoice.status,
        subtotal_cents=invoice.subtotal_cents,
        tax_cents=invoice.tax_cents,
        total_cents=invoice.total_cents,
        balance_cents=invoice.balance_cents,
        paid_cents=paid_cents,
        refunded_cents=refunded_cents,
        currency=invoice.currency,
        issued_at=invoice.issued_at,
        due_at=invoice.due_at,
        days_outstanding=days_outstanding,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


async def _invoice_view(db: AsyncSession, invoice: Invoice) -> InvoiceOut:
    totals = await _payment_totals(db, [invoice.id])
    paid, refunded = totals.get(invoice.id, (0, 0))
    return _invoice_out(invoice, paid, refunded)


async def list_invoices(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: InvoiceStatus | None = None,
    issued_from: datetime | None = None,
    issued_to: datetime | None = None,
    patient_user_id: UUID | None = None,
    request: Request | None = None,
) -> Page[InvoiceOut]:
    query = tenant_scoped(select(Invoice), Invoice, context)
    if status is not None:
        query = query.where(Invoice.status == status)
    if issued_from is not None:
        query = query.where(Invoice.issued_at >= issued_from)
    if issued_to is not None:
        query = query.where(Invoice.issued_at < issued_to)
    if patient_user_id is not None:
        query = query.where(Invoice.patient_user_id == patient_user_id)

    total = await _count(db, query)
    invoices = list(
        (
            await db.scalars(
                query.order_by(func.coalesce(Invoice.issued_at, Invoice.created_at).desc())
                .limit(page.limit + 1)
                .offset(page.offset)
            )
        ).all()
    )
    totals = await _payment_totals(db, [invoice.id for invoice in invoices])
    items = [_invoice_out(invoice, *totals.get(invoice.id, (0, 0))) for invoice in invoices]
    await _log_patient_reads(
        db,
        context,
        ids=[invoice.patient_user_id for invoice in invoices],
        resource_type="invoice",
        purpose_of_use="HPAYMT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def _get_invoice(db: AsyncSession, context: AuthContext, invoice_id: UUID) -> Invoice:
    query = tenant_scoped(select(Invoice), Invoice, context).where(Invoice.id == invoice_id)
    invoice = await db.scalar(query)
    if invoice is None:
        raise not_found("Invoice")
    return invoice


async def get_invoice_detail(
    db: AsyncSession,
    context: AuthContext,
    invoice_id: UUID,
    request: Request | None = None,
) -> InvoiceDetailOut:
    invoice = await _get_invoice(db, context, invoice_id)
    lines = (
        await db.scalars(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.line_number)
        )
    ).all()
    payments = (
        await db.scalars(
            select(Payment)
            .where(Payment.invoice_id == invoice.id)
            .order_by(Payment.created_at.desc())
        )
    ).all()
    refunds = (
        await db.scalars(
            select(Refund)
            .join(Payment, Payment.id == Refund.payment_id)
            .where(Payment.invoice_id == invoice.id)
            .order_by(Refund.created_at.desc())
        )
    ).all()
    document_rows = (
        await db.execute(
            select(
                DocumentLink,
                DocumentAsset.filename,
                DocumentAsset.content_type,
                DocumentAsset.byte_size,
            )
            .join(DocumentAsset, DocumentAsset.id == DocumentLink.document_asset_id)
            .where(DocumentLink.subject_type == "invoice", DocumentLink.subject_id == invoice.id)
            .order_by(DocumentLink.created_at.desc())
        )
    ).all()

    if invoice.patient_user_id is not None:
        await _log_patient_reads(
            db,
            context,
            ids=[invoice.patient_user_id],
            resource_type="invoice",
            purpose_of_use="HPAYMT",
            request=request,
        )
    await db.commit()

    return InvoiceDetailOut(
        invoice=await _invoice_view(db, invoice),
        lines=[
            InvoiceLineOut(
                id=line.id,
                line_number=line.line_number,
                service_item_id=line.service_item_id,
                service_code=line.service_code,
                service_display=line.service_display,
                description=line.description,
                quantity=float(line.quantity),
                unit_price_cents=line.unit_price_cents,
                amount_cents=line.amount_cents,
            )
            for line in lines
        ],
        payments=[PaymentOut.model_validate(payment) for payment in payments],
        refunds=[RefundOut.model_validate(refund) for refund in refunds],
        documents=[
            DocumentLinkOut(
                id=link.id,
                document_asset_id=link.document_asset_id,
                subject_type=link.subject_type,
                subject_id=link.subject_id,
                link_type=link.link_type.value,
                filename=filename,
                content_type=content_type,
                byte_size=byte_size,
                linked_by_user_id=link.linked_by_user_id,
                created_at=link.created_at,
            )
            for link, filename, content_type, byte_size in document_rows
        ],
    )


async def record_invoice_payment(
    db: AsyncSession,
    context: AuthContext,
    invoice_id: UUID,
    payload: PaymentCreate,
    request: Request | None = None,
) -> PaymentResult:
    invoice = await _get_invoice(db, context, invoice_id)

    existing = await db.scalar(
        select(Payment).where(
            Payment.tenant_id == invoice.tenant_id,
            Payment.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.invoice_id != invoice.id:
            raise conflict("Idempotency key already used for another invoice")
        return PaymentResult(
            payment=PaymentOut.model_validate(existing),
            invoice=await _invoice_view(db, invoice),
            replayed=True,
        )

    if invoice.status in {InvoiceStatus.VOID, InvoiceStatus.REFUNDED}:
        raise conflict(f"Invoice is {invoice.status.value}")
    if invoice.status == InvoiceStatus.PAID or invoice.balance_cents <= 0:
        raise conflict("Invoice is already settled")
    if payload.currency != invoice.currency:
        raise unprocessable(f"Invoice is denominated in {invoice.currency}")
    if payload.amount_cents > invoice.balance_cents:
        raise unprocessable("Payment exceeds the outstanding balance")

    now = _now()
    payment = Payment(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        appointment_id=invoice.appointment_id,
        payer_user_id=invoice.payer_user_id,
        method=payload.method,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        status=PaymentStatus.CAPTURED,
        processor=payload.processor,
        processor_intent_id=payload.processor_intent_id,
        processor_charge_id=payload.processor_charge_id,
        idempotency_key=payload.idempotency_key,
        authorized_at=now,
        captured_at=now,
    )
    db.add(payment)
    invoice.balance_cents -= payload.amount_cents
    if invoice.balance_cents == 0:
        invoice.status = InvoiceStatus.PAID
    await db.flush()

    if invoice.patient_user_id is not None:
        await record_phi_access(
            db,
            context,
            patient_user_id=invoice.patient_user_id,
            resource_type="invoice",
            resource_id=invoice.id,
            purpose_of_use="HPAYMT",
            request=request,
        )
    await write_audit(
        db,
        context,
        event_type="operations.payment.captured",
        subject_user_id=invoice.patient_user_id,
        resource_id=payment.id,
        event_data={
            "invoice_id": str(invoice.id),
            "amount_cents": payload.amount_cents,
            "currency": payload.currency,
            "method": payload.method.value,
            "balance_cents": invoice.balance_cents,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(payment)
    await db.refresh(invoice)
    return PaymentResult(
        payment=PaymentOut.model_validate(payment),
        invoice=await _invoice_view(db, invoice),
        replayed=False,
    )


async def refund_payment(
    db: AsyncSession,
    context: AuthContext,
    payment_id: UUID,
    payload: RefundCreate,
    request: Request | None = None,
) -> RefundResult:
    query = tenant_scoped(select(Payment), Payment, context).where(Payment.id == payment_id)
    payment = await db.scalar(query)
    if payment is None:
        raise not_found("Payment")
    if payment.status not in {PaymentStatus.CAPTURED, PaymentStatus.REFUNDED}:
        raise conflict(f"Cannot refund a payment that is {payment.status.value}")

    already_refunded = int(
        await db.scalar(
            select(func.coalesce(func.sum(Refund.amount_cents), 0)).where(
                Refund.payment_id == payment.id, Refund.status == RefundStatus.SUCCEEDED
            )
        )
        or 0
    )
    remaining = payment.amount_cents - already_refunded
    if remaining <= 0:
        raise conflict("Payment is already fully refunded")
    if payload.amount_cents > remaining:
        raise unprocessable(f"Only {remaining} cents remain refundable")

    invoice = await _get_invoice(db, context, payment.invoice_id)
    now = _now()
    refund = Refund(
        tenant_id=payment.tenant_id,
        payment_id=payment.id,
        amount_cents=payload.amount_cents,
        currency=payment.currency,
        reason=payload.reason,
        status=RefundStatus.SUCCEEDED,
        processor_refund_id=payload.processor_refund_id,
        refunded_at=now,
    )
    db.add(refund)
    if already_refunded + payload.amount_cents == payment.amount_cents:
        payment.status = PaymentStatus.REFUNDED
    invoice.balance_cents += payload.amount_cents
    if invoice.balance_cents >= invoice.total_cents and invoice.total_cents > 0:
        invoice.status = InvoiceStatus.REFUNDED
    elif invoice.status == InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.ISSUED
    await db.flush()

    if invoice.patient_user_id is not None:
        await record_phi_access(
            db,
            context,
            patient_user_id=invoice.patient_user_id,
            resource_type="invoice",
            resource_id=invoice.id,
            purpose_of_use="HPAYMT",
            request=request,
        )
    await write_audit(
        db,
        context,
        event_type="operations.payment.refunded",
        subject_user_id=invoice.patient_user_id,
        resource_id=refund.id,
        event_data={
            "payment_id": str(payment.id),
            "invoice_id": str(invoice.id),
            "amount_cents": payload.amount_cents,
            "currency": payment.currency,
            "reason": payload.reason,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(refund)
    await db.refresh(payment)
    await db.refresh(invoice)
    return RefundResult(
        refund=RefundOut.model_validate(refund),
        payment=PaymentOut.model_validate(payment),
        invoice=await _invoice_view(db, invoice),
    )


async def revenue_cycle_summary(
    db: AsyncSession,
    context: AuthContext,
    *,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
    currency: str | None = None,
) -> RevenueCycleSummary:
    now = _now()
    end = window_to or now
    start = window_from or (end - timedelta(days=90))
    if start >= end:
        raise unprocessable("window_from must precede window_to")

    invoices = tenant_scoped(select(Invoice), Invoice, context).subquery("scoped_invoices")
    payments = tenant_scoped(select(Payment), Payment, context).subquery("scoped_payments")
    refunds = tenant_scoped(select(Refund), Refund, context).subquery("scoped_refunds")
    claims = tenant_scoped(select(Claim), Claim, context).subquery("scoped_claims")

    currency_filter = [invoices.c.currency == currency] if currency else []

    billed_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(invoices.c.total_cents), 0),
                func.count(invoices.c.id),
            ).where(
                invoices.c.issued_at >= start,
                invoices.c.issued_at < end,
                invoices.c.status != InvoiceStatus.VOID,
                *currency_filter,
            )
        )
    ).one()
    billed_cents = int(billed_row[0])
    invoice_count = int(billed_row[1])

    collected_cents = int(
        await db.scalar(
            select(func.coalesce(func.sum(payments.c.amount_cents), 0)).where(
                payments.c.status.in_([PaymentStatus.CAPTURED, PaymentStatus.REFUNDED]),
                payments.c.captured_at >= start,
                payments.c.captured_at < end,
                *([payments.c.currency == currency] if currency else []),
            )
        )
        or 0
    )
    refunded_cents = int(
        await db.scalar(
            select(func.coalesce(func.sum(refunds.c.amount_cents), 0)).where(
                refunds.c.status == RefundStatus.SUCCEEDED,
                refunds.c.refunded_at >= start,
                refunds.c.refunded_at < end,
                *([refunds.c.currency == currency] if currency else []),
            )
        )
        or 0
    )

    bucket = case(
        (invoices.c.issued_at >= now - timedelta(days=30), "0-30"),
        (invoices.c.issued_at >= now - timedelta(days=60), "31-60"),
        (invoices.c.issued_at >= now - timedelta(days=90), "61-90"),
        else_="90+",
    ).label("bucket")
    aging_rows = (
        await db.execute(
            select(
                bucket,
                func.count(invoices.c.id),
                func.coalesce(func.sum(invoices.c.balance_cents), 0),
            )
            .where(
                invoices.c.balance_cents > 0,
                invoices.c.status == InvoiceStatus.ISSUED,
                invoices.c.issued_at.is_not(None),
                *currency_filter,
            )
            .group_by(bucket)
        )
    ).all()
    found = {
        str(row[0]): AgingBucket(
            bucket=str(row[0]), invoice_count=int(row[1]), balance_cents=int(row[2])
        )
        for row in aging_rows
    }
    aging = [
        found.get(name, AgingBucket(bucket=name, invoice_count=0, balance_cents=0))
        for name in ("0-30", "31-60", "61-90", "90+")
    ]
    outstanding_cents = sum(item.balance_cents for item in aging)

    status_rows = (
        await db.execute(
            select(
                invoices.c.status,
                func.count(invoices.c.id),
                func.coalesce(func.sum(invoices.c.total_cents), 0),
            )
            .where(
                func.coalesce(invoices.c.issued_at, invoices.c.created_at) >= start,
                func.coalesce(invoices.c.issued_at, invoices.c.created_at) < end,
                *currency_filter,
            )
            .group_by(invoices.c.status)
            .order_by(invoices.c.status)
        )
    ).all()

    claim_row = (
        await db.execute(
            select(
                func.count(claims.c.id),
                func.count().filter(claims.c.status == ClaimStatus.DENIED),
                func.coalesce(
                    func.sum(claims.c.total_charge_cents).filter(
                        claims.c.status == ClaimStatus.DENIED
                    ),
                    0,
                ),
                func.coalesce(func.sum(claims.c.paid_cents), 0),
            ).where(
                func.coalesce(claims.c.submitted_at, claims.c.created_at) >= start,
                func.coalesce(claims.c.submitted_at, claims.c.created_at) < end,
            )
        )
    ).one()
    submitted_count = int(claim_row[0])
    denied_count = int(claim_row[1])

    currencies = (
        await db.scalars(
            select(invoices.c.currency)
            .where(
                func.coalesce(invoices.c.issued_at, invoices.c.created_at) >= start,
                func.coalesce(invoices.c.issued_at, invoices.c.created_at) < end,
            )
            .distinct()
        )
    ).all()
    resolved_currency = currency or (str(currencies[0]) if len(currencies) == 1 else None)

    return RevenueCycleSummary(
        window_from=start,
        window_to=end,
        currency=resolved_currency,
        billed_cents=billed_cents,
        collected_cents=collected_cents,
        refunded_cents=refunded_cents,
        outstanding_cents=outstanding_cents,
        collection_rate=_rate(collected_cents - refunded_cents, billed_cents),
        invoice_count=invoice_count,
        aging=aging,
        invoices_by_status=[
            StatusBucket(key=str(row[0]), count=int(row[1]), amount_cents=int(row[2]))
            for row in status_rows
        ],
        claims=ClaimDenialStats(
            submitted_count=submitted_count,
            denied_count=denied_count,
            denial_rate=_rate(denied_count, submitted_count),
            denied_charge_cents=int(claim_row[2]),
            paid_cents=int(claim_row[3]),
        ),
    )


# ---------------------------------------------------------------------------
# Clinical documentation
# ---------------------------------------------------------------------------


async def _load_encounter(db: AsyncSession, context: AuthContext, encounter_id: UUID) -> Encounter:
    allowed = await consent_scoped_patients(db, context)
    query = apply_patient_scope(
        select(Encounter).where(Encounter.id == encounter_id), Encounter, allowed
    )
    encounter = await db.scalar(query)
    if encounter is None:
        raise not_found("Encounter")
    return encounter


async def _load_note(db: AsyncSession, context: AuthContext, note_id: UUID) -> ClinicalNote:
    allowed = await consent_scoped_patients(db, context)
    query = apply_patient_scope(
        select(ClinicalNote).where(ClinicalNote.id == note_id), ClinicalNote, allowed
    )
    note = await db.scalar(query)
    if note is None:
        raise not_found("Clinical note")
    return note


async def _note_addenda(
    db: AsyncSession, note_ids: Sequence[UUID]
) -> dict[UUID, list[AddendumOut]]:
    if not note_ids:
        return {}
    rows = (
        await db.scalars(
            select(ClinicalNoteAddendum)
            .where(ClinicalNoteAddendum.clinical_note_id.in_(note_ids))
            .order_by(ClinicalNoteAddendum.clinical_note_id, ClinicalNoteAddendum.sequence)
        )
    ).all()
    grouped: dict[UUID, list[AddendumOut]] = {}
    for row in rows:
        grouped.setdefault(row.clinical_note_id, []).append(AddendumOut.model_validate(row))
    return grouped


async def _note_extractions(
    db: AsyncSession, document_ids: Sequence[UUID]
) -> dict[UUID, ExtractionSummary]:
    if not document_ids:
        return {}
    rows = (
        await db.scalars(
            select(DocumentExtraction)
            .where(DocumentExtraction.document_asset_id.in_(document_ids))
            .order_by(DocumentExtraction.document_asset_id, DocumentExtraction.created_at.desc())
        )
    ).all()
    latest: dict[UUID, ExtractionSummary] = {}
    for row in rows:
        latest.setdefault(
            row.document_asset_id,
            ExtractionSummary(
                id=row.id,
                document_asset_id=row.document_asset_id,
                extraction_schema=row.extraction_schema,
                schema_version=row.schema_version,
                overall_confidence=(
                    None if row.overall_confidence is None else float(row.overall_confidence)
                ),
                validation_status=row.validation_status,
                reviewed_by_user_id=row.reviewed_by_user_id,
                reviewed_at=row.reviewed_at,
            ),
        )
    return latest


def _note_out(
    note: ClinicalNote,
    addenda: list[AddendumOut],
    extraction: ExtractionSummary | None,
) -> ClinicalNoteOut:
    return ClinicalNoteOut(
        id=note.id,
        encounter_id=note.encounter_id,
        patient_user_id=note.patient_user_id,
        author_user_id=note.author_user_id,
        note_type_code=note.note_type_code,
        title=note.title,
        content=note.content,
        content_format=note.content_format,
        status=note.status,
        signed_at=note.signed_at,
        signed_by_user_id=note.signed_by_user_id,
        cosigner_user_id=note.cosigner_user_id,
        cosigned_at=note.cosigned_at,
        signature_hash=note.signature_hash,
        source=note.source,
        source_document_id=note.source_document_id,
        extraction_confidence=(
            None if note.extraction_confidence is None else float(note.extraction_confidence)
        ),
        version=note.version,
        supersedes_id=note.supersedes_id,
        superseded_at=note.superseded_at,
        amendment_reason=note.amendment_reason,
        recorded_at=note.recorded_at,
        created_at=note.created_at,
        updated_at=note.updated_at,
        addenda=addenda,
        extraction=extraction,
    )


async def _note_view(db: AsyncSession, note: ClinicalNote) -> ClinicalNoteOut:
    addenda = await _note_addenda(db, [note.id])
    extractions = await _note_extractions(
        db, [note.source_document_id] if note.source_document_id else []
    )
    return _note_out(
        note,
        addenda.get(note.id, []),
        extractions.get(note.source_document_id) if note.source_document_id else None,
    )


async def list_encounter_notes(
    db: AsyncSession,
    context: AuthContext,
    encounter_id: UUID,
    *,
    page: Pagination,
    include_superseded: bool = False,
    request: Request | None = None,
) -> Page[ClinicalNoteOut]:
    encounter = await _load_encounter(db, context, encounter_id)
    query = select(ClinicalNote).where(ClinicalNote.encounter_id == encounter.id)
    if not include_superseded:
        query = query.where(ClinicalNote.superseded_at.is_(None))
    total = await _count(db, query)
    notes = list(
        (
            await db.scalars(
                query.order_by(ClinicalNote.note_type_code, ClinicalNote.version.desc())
                .limit(page.limit + 1)
                .offset(page.offset)
            )
        ).all()
    )
    addenda = await _note_addenda(db, [note.id for note in notes])
    extractions = await _note_extractions(
        db, [note.source_document_id for note in notes if note.source_document_id is not None]
    )
    items = [
        _note_out(
            note,
            addenda.get(note.id, []),
            extractions.get(note.source_document_id) if note.source_document_id else None,
        )
        for note in notes
    ]
    await record_phi_access(
        db,
        context,
        patient_user_id=encounter.patient_user_id,
        resource_type="clinical_note",
        resource_id=encounter.id,
        result_count=len(items),
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def create_encounter_note(
    db: AsyncSession,
    context: AuthContext,
    encounter_id: UUID,
    payload: ClinicalNoteCreate,
    request: Request | None = None,
) -> ClinicalNoteOut:
    encounter = await _load_encounter(db, context, encounter_id)
    await assert_may_read_patient(db, context, encounter.patient_user_id)

    superseded: ClinicalNote | None = None
    if payload.supersedes_id is not None:
        superseded = await db.scalar(
            select(ClinicalNote).where(
                ClinicalNote.id == payload.supersedes_id,
                ClinicalNote.encounter_id == encounter.id,
            )
        )
        if superseded is None:
            raise unprocessable("The superseded note belongs to another encounter")
        if superseded.signed_at is not None:
            raise conflict("Signed notes are immutable; add an addendum instead")
        if payload.amendment_reason is None:
            raise unprocessable("amendment_reason is required when superseding a note")

    highest = await db.scalar(
        select(func.coalesce(func.max(ClinicalNote.version), 0)).where(
            ClinicalNote.encounter_id == encounter.id,
            ClinicalNote.note_type_code == payload.note_type_code,
        )
    )
    note = ClinicalNote(
        tenant_id=context.tenant_id,
        encounter_id=encounter.id,
        patient_user_id=encounter.patient_user_id,
        author_user_id=context.user.id,
        note_type_code=payload.note_type_code,
        title=payload.title,
        content=payload.content,
        content_format=payload.content_format,
        status=NoteStatus.DRAFT,
        recorded_by_user_id=context.user.id,
        recorded_at=_now(),
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=_decimal(payload.extraction_confidence),
        version=int(highest or 0) + 1,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(note)
    if superseded is not None:
        superseded.superseded_at = _now()
    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=encounter.patient_user_id,
        resource_type="clinical_note",
        resource_id=note.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.note.drafted",
        subject_user_id=encounter.patient_user_id,
        resource_id=note.id,
        event_data={
            "encounter_id": str(encounter.id),
            "note_type_code": payload.note_type_code,
            "version": note.version,
            "supersedes_id": str(payload.supersedes_id) if payload.supersedes_id else None,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(note)
    return await _note_view(db, note)


async def sign_note(
    db: AsyncSession,
    context: AuthContext,
    note_id: UUID,
    payload: NoteSignRequest,
    request: Request | None = None,
) -> ClinicalNoteOut:
    note = await _load_note(db, context, note_id)
    if note.signed_at is not None:
        raise conflict("Note is already signed")
    if note.status not in {NoteStatus.DRAFT, NoteStatus.PRELIMINARY}:
        raise conflict(f"Cannot sign a note that is '{note.status.value}'")
    if note.author_user_id != context.user.id and not is_admin(context):
        raise forbidden("Only the authoring clinician may sign this note")
    if payload.cosigner_user_id is not None:
        cosigner = await db.scalar(
            select(DoctorProfile.user_id).where(DoctorProfile.user_id == payload.cosigner_user_id)
        )
        if cosigner is None:
            raise unprocessable("Cosigner must be a clinician")

    signed_at = _now()
    note.signed_at = signed_at
    note.signed_by_user_id = context.user.id
    note.signature_hash = _digest(
        str(note.id), str(note.version), note.content, str(context.user.id), signed_at.isoformat()
    )
    note.status = NoteStatus.FINAL
    if payload.cosigner_user_id is not None:
        note.cosigner_user_id = payload.cosigner_user_id
        note.cosigned_at = signed_at

    await record_phi_access(
        db,
        context,
        patient_user_id=note.patient_user_id,
        resource_type="clinical_note",
        resource_id=note.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.note.signed",
        subject_user_id=note.patient_user_id,
        resource_id=note.id,
        event_data={
            "encounter_id": str(note.encounter_id),
            "version": note.version,
            "signature_hash": note.signature_hash,
            "cosigner_user_id": (
                str(payload.cosigner_user_id) if payload.cosigner_user_id else None
            ),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(note)
    return await _note_view(db, note)


async def add_note_addendum(
    db: AsyncSession,
    context: AuthContext,
    note_id: UUID,
    payload: AddendumCreate,
    request: Request | None = None,
) -> AddendumOut:
    note = await _load_note(db, context, note_id)
    if note.signed_at is None:
        raise conflict("Edit the draft directly; addenda only apply to signed notes")

    next_sequence = (
        int(
            await db.scalar(
                select(func.coalesce(func.max(ClinicalNoteAddendum.sequence), 0)).where(
                    ClinicalNoteAddendum.clinical_note_id == note.id
                )
            )
            or 0
        )
        + 1
    )
    signed_at = _now()
    addendum = ClinicalNoteAddendum(
        clinical_note_id=note.id,
        author_user_id=context.user.id,
        content=payload.content,
        sequence=next_sequence,
        signed_at=signed_at,
        signature_hash=_digest(
            str(note.id),
            str(next_sequence),
            payload.content,
            str(context.user.id),
            signed_at.isoformat(),
        ),
    )
    db.add(addendum)
    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=note.patient_user_id,
        resource_type="clinical_note_addendum",
        resource_id=addendum.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.note.amended",
        subject_user_id=note.patient_user_id,
        resource_id=addendum.id,
        event_data={"clinical_note_id": str(note.id), "sequence": next_sequence},
        request=request,
    )
    await db.commit()
    await db.refresh(addendum)
    return AddendumOut.model_validate(addendum)


def _encounter_code_out(code: EncounterCode, patient_user_id: UUID) -> EncounterCodeOut:
    return EncounterCodeOut(
        id=code.id,
        encounter_id=code.encounter_id,
        patient_user_id=patient_user_id,
        billing_code_system=code.billing_code_system,
        billing_code=code.billing_code,
        billing_display=code.billing_display,
        billing_concept_id=code.billing_concept_id,
        code_type=code.code_type,
        rank=code.rank,
        modifiers=list(code.modifiers),
        units=code.units,
        coder_user_id=code.coder_user_id,
        source=code.source,
        confidence=None if code.confidence is None else float(code.confidence),
        review_status=code.review_status,
        reviewed_by_user_id=code.reviewed_by_user_id,
        reviewed_at=code.reviewed_at,
        created_at=code.created_at,
        updated_at=code.updated_at,
    )


async def list_encounter_codes(
    db: AsyncSession,
    context: AuthContext,
    encounter_id: UUID,
    *,
    page: Pagination,
    code_type: CodeType | None = None,
    review_status: ReviewStatus | None = None,
    request: Request | None = None,
) -> Page[EncounterCodeOut]:
    encounter = await _load_encounter(db, context, encounter_id)
    query = select(EncounterCode).where(EncounterCode.encounter_id == encounter.id)
    if code_type is not None:
        query = query.where(EncounterCode.code_type == code_type)
    if review_status is not None:
        query = query.where(EncounterCode.review_status == review_status)
    total = await _count(db, query)
    codes = (
        await db.scalars(
            query.order_by(EncounterCode.code_type, EncounterCode.rank)
            .limit(page.limit + 1)
            .offset(page.offset)
        )
    ).all()
    items = [_encounter_code_out(code, encounter.patient_user_id) for code in codes]
    await record_phi_access(
        db,
        context,
        patient_user_id=encounter.patient_user_id,
        resource_type="encounter_code",
        resource_id=encounter.id,
        result_count=len(items),
        purpose_of_use="HPAYMT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def create_encounter_code(
    db: AsyncSession,
    context: AuthContext,
    encounter_id: UUID,
    payload: EncounterCodeCreate,
    request: Request | None = None,
) -> EncounterCodeOut:
    encounter = await _load_encounter(db, context, encounter_id)
    await assert_may_read_patient(db, context, encounter.patient_user_id)

    rank = payload.rank
    if rank is None:
        highest = await db.scalar(
            select(func.coalesce(func.max(EncounterCode.rank), 0)).where(
                EncounterCode.encounter_id == encounter.id,
                EncounterCode.code_type == payload.code_type,
            )
        )
        rank = int(highest or 0) + 1
    duplicate = await db.scalar(
        select(EncounterCode.id).where(
            EncounterCode.encounter_id == encounter.id,
            EncounterCode.billing_code == payload.billing_code,
            EncounterCode.code_type == payload.code_type,
            EncounterCode.rank == rank,
        )
    )
    if duplicate is not None:
        raise conflict("That code is already recorded at this rank")

    reviewed_by = context.user.id if payload.review_status != ReviewStatus.PENDING else None
    code = EncounterCode(
        tenant_id=context.tenant_id,
        encounter_id=encounter.id,
        billing_code_system=payload.billing_code_system,
        billing_code=payload.billing_code,
        billing_display=payload.billing_display,
        billing_concept_id=payload.billing_concept_id,
        code_type=payload.code_type,
        rank=rank,
        modifiers=payload.modifiers,
        units=payload.units,
        coder_user_id=context.user.id,
        source=payload.source,
        confidence=_decimal(payload.confidence),
        review_status=payload.review_status,
        reviewed_by_user_id=reviewed_by,
        reviewed_at=_now() if reviewed_by is not None else None,
    )
    db.add(code)
    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=encounter.patient_user_id,
        resource_type="encounter_code",
        resource_id=code.id,
        purpose_of_use="HPAYMT",
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.encounter_code.recorded",
        subject_user_id=encounter.patient_user_id,
        resource_id=code.id,
        event_data={
            "encounter_id": str(encounter.id),
            "billing_code": payload.billing_code,
            "code_type": payload.code_type.value,
            "review_status": payload.review_status.value,
            "source": payload.source.value,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(code)
    return _encounter_code_out(code, encounter.patient_user_id)


async def list_referrals(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: ReferralStatus | None = None,
    patient_user_id: UUID | None = None,
    specialty_code: str | None = None,
    direction: Literal["incoming", "outgoing"] | None = None,
    request: Request | None = None,
) -> Page[ReferralOut]:
    allowed = await consent_scoped_patients(db, context)
    query = apply_patient_scope(select(Referral), Referral, allowed)
    if status is not None:
        query = query.where(Referral.status == status)
    if patient_user_id is not None:
        query = query.where(Referral.patient_user_id == patient_user_id)
    if specialty_code is not None:
        query = query.where(Referral.specialty_code == specialty_code)
    if direction == "incoming":
        query = query.where(Referral.receiving_organization_id == context.tenant_id)
    elif direction == "outgoing":
        query = query.where(Referral.referring_organization_id == context.tenant_id)

    total = await _count(db, query)
    referrals = (
        await db.scalars(
            query.order_by(Referral.created_at.desc()).limit(page.limit + 1).offset(page.offset)
        )
    ).all()
    items = [ReferralOut.model_validate(referral) for referral in referrals]
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[referral.patient_user_id for referral in referrals],
        resource_type="referral",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def create_referral(
    db: AsyncSession,
    context: AuthContext,
    payload: ReferralCreate,
    request: Request | None = None,
) -> ReferralOut:
    await assert_may_read_patient(db, context, payload.patient_user_id)
    patient = await db.scalar(
        select(PatientProfile.user_id).where(PatientProfile.user_id == payload.patient_user_id)
    )
    if patient is None:
        raise unprocessable("Unknown patient")

    referring_provider = payload.referring_provider_user_id or context.user.id
    provider = await db.scalar(
        select(DoctorProfile.user_id).where(DoctorProfile.user_id == referring_provider)
    )
    if provider is None:
        raise unprocessable("referring_provider_user_id must be a clinician")
    referring_organization = await _organization_for(db, context, payload.referring_organization_id)
    if payload.encounter_id is not None:
        encounter = await _load_encounter(db, context, payload.encounter_id)
        if encounter.patient_user_id != payload.patient_user_id:
            raise unprocessable("Encounter belongs to another patient")

    referral = Referral(
        tenant_id=context.tenant_id,
        patient_user_id=payload.patient_user_id,
        referring_provider_user_id=referring_provider,
        referring_organization_id=referring_organization,
        receiving_provider_user_id=payload.receiving_provider_user_id,
        receiving_organization_id=payload.receiving_organization_id,
        encounter_id=payload.encounter_id,
        specialty_code=payload.specialty_code,
        urgency=payload.urgency,
        reason=payload.reason,
        status=ReferralStatus.SENT if payload.send else ReferralStatus.DRAFT,
        expires_at=payload.expires_at,
    )
    db.add(referral)
    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=payload.patient_user_id,
        resource_type="referral",
        resource_id=referral.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.referral.created",
        subject_user_id=payload.patient_user_id,
        resource_id=referral.id,
        event_data={
            "specialty_code": payload.specialty_code,
            "urgency": payload.urgency,
            "status": referral.status.value,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(referral)
    return ReferralOut.model_validate(referral)


async def change_referral_status(
    db: AsyncSession,
    context: AuthContext,
    referral_id: UUID,
    payload: ReferralStatusChange,
    request: Request | None = None,
) -> ReferralOut:
    allowed = await consent_scoped_patients(db, context)
    query = apply_patient_scope(
        select(Referral).where(Referral.id == referral_id), Referral, allowed
    )
    referral = await db.scalar(query)
    if referral is None:
        raise not_found("Referral")

    assert_transition(referral.status.value, payload.status.value, REFERRAL_TRANSITIONS)
    previous = referral.status
    referral.status = payload.status
    if payload.reason is not None:
        referral.feedback_note = payload.reason
    if payload.receiving_provider_user_id is not None:
        referral.receiving_provider_user_id = payload.receiving_provider_user_id
    if payload.receiving_organization_id is not None:
        referral.receiving_organization_id = payload.receiving_organization_id
    if payload.appointment_id is not None:
        referral.appointment_id = payload.appointment_id

    await record_phi_access(
        db,
        context,
        patient_user_id=referral.patient_user_id,
        resource_type="referral",
        resource_id=referral.id,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="clinical.referral.status_changed",
        subject_user_id=referral.patient_user_id,
        resource_id=referral.id,
        event_data={
            "from": previous.value,
            "to": payload.status.value,
            "reason": payload.reason,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(referral)
    return ReferralOut.model_validate(referral)


# ---------------------------------------------------------------------------
# Support cases
# ---------------------------------------------------------------------------


def _support_out(case_row: SupportCase, comment_count: int) -> SupportCaseOut:
    breached = case_row.resolved_at is None and case_row.sla_due_at < _now()
    return SupportCaseOut(
        id=case_row.id,
        case_number=case_row.case_number,
        subject=case_row.subject,
        description=case_row.description,
        category=case_row.category,
        severity=case_row.severity,
        status=case_row.status,
        queue=case_row.queue,
        requester_user_id=case_row.requester_user_id,
        assignee_user_id=case_row.assignee_user_id,
        sla_due_at=case_row.sla_due_at,
        sla_breached=breached,
        first_response_at=case_row.first_response_at,
        resolved_at=case_row.resolved_at,
        escalated_at=case_row.escalated_at,
        escalation_level=case_row.escalation_level,
        related_record_type=case_row.related_record_type,
        related_record_id=case_row.related_record_id,
        comment_count=comment_count,
        created_at=case_row.created_at,
        updated_at=case_row.updated_at,
    )


async def _comment_counts(db: AsyncSession, case_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not case_ids:
        return {}
    rows = (
        await db.execute(
            select(SupportCaseComment.case_id, func.count())
            .where(SupportCaseComment.case_id.in_(case_ids))
            .group_by(SupportCaseComment.case_id)
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows}


async def _support_view(db: AsyncSession, case_row: SupportCase) -> SupportCaseOut:
    counts = await _comment_counts(db, [case_row.id])
    return _support_out(case_row, counts.get(case_row.id, 0))


async def _get_support_case(db: AsyncSession, context: AuthContext, case_id: UUID) -> SupportCase:
    query = tenant_scoped(select(SupportCase), SupportCase, context).where(
        SupportCase.id == case_id
    )
    case_row = await db.scalar(query)
    if case_row is None:
        raise not_found("Support case")
    return case_row


async def list_support_cases(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: SupportStatus | None = None,
    severity: SupportSeverity | None = None,
    queue: str | None = None,
    assignee_user_id: UUID | None = None,
    breached_only: bool = False,
    request: Request | None = None,
) -> Page[SupportCaseOut]:
    query = tenant_scoped(select(SupportCase), SupportCase, context)
    if status is not None:
        query = query.where(SupportCase.status == status)
    if severity is not None:
        query = query.where(SupportCase.severity == severity)
    if queue is not None:
        query = query.where(SupportCase.queue == queue)
    if assignee_user_id is not None:
        query = query.where(SupportCase.assignee_user_id == assignee_user_id)
    if breached_only:
        query = query.where(SupportCase.resolved_at.is_(None), SupportCase.sla_due_at < _now())

    total = await _count(db, query)
    cases = (
        await db.scalars(
            query.order_by(SupportCase.severity, SupportCase.sla_due_at)
            .limit(page.limit + 1)
            .offset(page.offset)
        )
    ).all()
    counts = await _comment_counts(db, [case_row.id for case_row in cases])
    items = [_support_out(case_row, counts.get(case_row.id, 0)) for case_row in cases]
    await _log_patient_reads(
        db,
        context,
        ids=[case_row.requester_user_id for case_row in cases],
        resource_type="support_case",
        purpose_of_use="HOPERAT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def create_support_case(
    db: AsyncSession,
    context: AuthContext,
    payload: SupportCaseCreate,
    request: Request | None = None,
) -> SupportCaseOut:
    requester = payload.requester_user_id or context.user.id
    known = await db.scalar(select(User.id).where(User.id == requester))
    if known is None:
        raise unprocessable("Unknown requester")
    if payload.assignee_user_id is not None:
        assignee = await db.scalar(select(User.id).where(User.id == payload.assignee_user_id))
        if assignee is None:
            raise unprocessable("Unknown assignee")

    now = _now()
    case_row = SupportCase(
        tenant_id=context.tenant_id,
        case_number=f"SUP-{now:%Y%m%d}-{uuid4().hex[:8].upper()}",
        subject=payload.subject,
        description=payload.description,
        category=payload.category,
        severity=payload.severity,
        status=SupportStatus.NEW,
        queue=payload.queue,
        requester_user_id=requester,
        assignee_user_id=payload.assignee_user_id,
        sla_due_at=now + timedelta(hours=SLA_HOURS[payload.severity]),
        related_record_type=payload.related_record_type,
        related_record_id=payload.related_record_id,
    )
    db.add(case_row)
    await db.flush()
    db.add(
        SupportCaseEvent(
            case_id=case_row.id,
            from_status=None,
            to_status=SupportStatus.NEW.value,
            actor_user_id=context.user.id,
            reason="case opened",
            occurred_at=now,
        )
    )
    await _log_patient_reads(
        db,
        context,
        ids=[requester],
        resource_type="support_case",
        purpose_of_use="HOPERAT",
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="support.case.created",
        subject_user_id=requester,
        resource_id=case_row.id,
        event_data={
            "case_number": case_row.case_number,
            "severity": payload.severity.value,
            "queue": payload.queue,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(case_row)
    return await _support_view(db, case_row)


async def add_support_comment(
    db: AsyncSession,
    context: AuthContext,
    case_id: UUID,
    payload: SupportCommentCreate,
    request: Request | None = None,
) -> SupportCommentOut:
    case_row = await _get_support_case(db, context, case_id)
    if case_row.status == SupportStatus.CLOSED:
        raise conflict("Closed cases cannot take new comments")

    comment = SupportCaseComment(
        case_id=case_row.id,
        author_user_id=context.user.id,
        body=payload.body,
        visibility=payload.visibility,
    )
    db.add(comment)
    if case_row.first_response_at is None and context.user.id != case_row.requester_user_id:
        case_row.first_response_at = _now()
    await db.flush()
    await write_audit(
        db,
        context,
        event_type="support.case.commented",
        subject_user_id=case_row.requester_user_id,
        resource_id=comment.id,
        event_data={
            "case_id": str(case_row.id),
            "visibility": payload.visibility.value,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(comment)
    return SupportCommentOut.model_validate(comment)


async def _apply_support_transition(
    db: AsyncSession,
    context: AuthContext,
    case_row: SupportCase,
    *,
    target: SupportStatus,
    reason: str | None,
    request: Request | None,
) -> SupportCaseEvent:
    assert_transition(case_row.status.value, target.value, SUPPORT_TRANSITIONS)
    previous = case_row.status
    now = _now()
    case_row.status = target
    if target == SupportStatus.RESOLVED:
        case_row.resolved_at = now
    elif previous == SupportStatus.RESOLVED:
        case_row.resolved_at = None
    if case_row.first_response_at is None and target != SupportStatus.NEW:
        case_row.first_response_at = now

    event = SupportCaseEvent(
        case_id=case_row.id,
        from_status=previous.value,
        to_status=target.value,
        actor_user_id=context.user.id,
        reason=reason,
        occurred_at=now,
    )
    db.add(event)
    await write_audit(
        db,
        context,
        event_type="support.case.transitioned",
        subject_user_id=case_row.requester_user_id,
        resource_id=case_row.id,
        event_data={"from": previous.value, "to": target.value, "reason": reason},
        request=request,
    )
    return event


async def transition_support_case(
    db: AsyncSession,
    context: AuthContext,
    case_id: UUID,
    payload: SupportTransitionRequest,
    request: Request | None = None,
) -> SupportCaseResult:
    case_row = await _get_support_case(db, context, case_id)
    if payload.assignee_user_id is not None:
        assignee = await db.scalar(select(User.id).where(User.id == payload.assignee_user_id))
        if assignee is None:
            raise unprocessable("Unknown assignee")
        case_row.assignee_user_id = payload.assignee_user_id
    event = await _apply_support_transition(
        db,
        context,
        case_row,
        target=payload.status,
        reason=payload.reason,
        request=request,
    )
    await db.commit()
    await db.refresh(case_row)
    await db.refresh(event)
    return SupportCaseResult(
        case=await _support_view(db, case_row),
        event=SupportEventOut.model_validate(event),
    )


async def escalate_support_case(
    db: AsyncSession,
    context: AuthContext,
    case_id: UUID,
    payload: SupportEscalateRequest,
    request: Request | None = None,
) -> SupportCaseResult:
    case_row = await _get_support_case(db, context, case_id)
    if payload.assignee_user_id is not None:
        assignee = await db.scalar(select(User.id).where(User.id == payload.assignee_user_id))
        if assignee is None:
            raise unprocessable("Unknown assignee")
        case_row.assignee_user_id = payload.assignee_user_id

    now = _now()
    if payload.severity is not None:
        case_row.severity = payload.severity
    case_row.escalation_level += 1
    case_row.escalated_at = now
    # Escalation restarts the response clock against the (possibly raised) severity.
    case_row.sla_due_at = now + timedelta(hours=SLA_HOURS[case_row.severity])

    event = await _apply_support_transition(
        db,
        context,
        case_row,
        target=SupportStatus.ESCALATED,
        reason=payload.reason,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="support.case.escalated",
        subject_user_id=case_row.requester_user_id,
        resource_id=case_row.id,
        event_data={
            "escalation_level": case_row.escalation_level,
            "severity": case_row.severity.value,
            "sla_due_at": case_row.sla_due_at.isoformat(),
            "reason": payload.reason,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(case_row)
    await db.refresh(event)
    return SupportCaseResult(
        case=await _support_view(db, case_row),
        event=SupportEventOut.model_validate(event),
    )


# ---------------------------------------------------------------------------
# PHI disclosure accounting
# ---------------------------------------------------------------------------


async def list_phi_access(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    patient_user_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    accessed_from: datetime | None = None,
    accessed_to: datetime | None = None,
    purpose_of_use: str | None = None,
    resource_type: str | None = None,
    request: Request | None = None,
) -> Page[PhiAccessOut]:
    query = tenant_scoped(select(PhiAccessEvent), PhiAccessEvent, context)
    if patient_user_id is not None:
        query = query.where(PhiAccessEvent.patient_user_id == patient_user_id)
    if actor_user_id is not None:
        query = query.where(PhiAccessEvent.actor_user_id == actor_user_id)
    if accessed_from is not None:
        query = query.where(PhiAccessEvent.created_at >= accessed_from)
    if accessed_to is not None:
        query = query.where(PhiAccessEvent.created_at < accessed_to)
    if purpose_of_use is not None:
        query = query.where(PhiAccessEvent.purpose_of_use == purpose_of_use)
    if resource_type is not None:
        query = query.where(PhiAccessEvent.resource_type == resource_type)

    total = await _count(db, query)
    listing: Select[Any] = (
        query.join(User, User.id == PhiAccessEvent.actor_user_id)
        .add_columns(User.email, User.account_type)
        .order_by(PhiAccessEvent.created_at.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = (await db.execute(listing)).all()
    items = [
        PhiAccessOut(
            id=event.id,
            tenant_id=event.tenant_id,
            actor_user_id=event.actor_user_id,
            actor_email=email,
            actor_account_type=account_type,
            patient_user_id=event.patient_user_id,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            action=event.action,
            purpose_of_use=event.purpose_of_use,
            consent_grant_id=event.consent_grant_id,
            request_id=event.request_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            result_count=event.result_count,
            created_at=event.created_at,
        )
        for event, email, account_type in rows
    ]
    # Reading the accounting log is itself a disclosure and is logged as one.
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[item.patient_user_id for item in items],
        resource_type="phi_access_event",
        purpose_of_use="HOPERAT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def break_glass_register(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    accessed_from: datetime | None = None,
    accessed_to: datetime | None = None,
    actor_user_id: UUID | None = None,
    request: Request | None = None,
) -> Page[BreakGlassEntry]:
    """Emergency-access register: one row per (actor, patient) ETREAT pairing."""
    scoped = tenant_scoped(select(PhiAccessEvent), PhiAccessEvent, context).where(
        PhiAccessEvent.purpose_of_use == "ETREAT"
    )
    if accessed_from is not None:
        scoped = scoped.where(PhiAccessEvent.created_at >= accessed_from)
    if accessed_to is not None:
        scoped = scoped.where(PhiAccessEvent.created_at < accessed_to)
    if actor_user_id is not None:
        scoped = scoped.where(PhiAccessEvent.actor_user_id == actor_user_id)

    events = scoped.subquery("break_glass_events")
    grouped = (
        select(
            events.c.actor_user_id,
            User.email,
            events.c.patient_user_id,
            func.count().label("event_count"),
            func.array_agg(distinct(events.c.resource_type)).label("resource_types"),
            func.min(events.c.created_at).label("first_access_at"),
            func.max(events.c.created_at).label("last_access_at"),
        )
        .join(User, User.id == events.c.actor_user_id)
        .group_by(events.c.actor_user_id, User.email, events.c.patient_user_id)
    )
    total = await _count(db, grouped)
    rows = (
        await db.execute(
            grouped.order_by(func.max(events.c.created_at).desc())
            .limit(page.limit + 1)
            .offset(page.offset)
        )
    ).all()
    items = [
        BreakGlassEntry(
            actor_user_id=row[0],
            actor_email=row[1],
            patient_user_id=row[2],
            event_count=int(row[3]),
            resource_types=sorted(str(value) for value in row[4]),
            first_access_at=row[5],
            last_access_at=row[6],
        )
        for row in rows
    ]
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[item.patient_user_id for item in items],
        resource_type="phi_access_event",
        purpose_of_use="HOPERAT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


# ---------------------------------------------------------------------------
# Data subject requests
# ---------------------------------------------------------------------------


def _dsr_out(dsr: DataSubjectRequest) -> DataSubjectRequestOut:
    overdue = (
        dsr.fulfilled_at is None
        and dsr.due_at < _now()
        and dsr.status
        not in {
            DsrStatus.FULFILLED,
            DsrStatus.REFUSED,
            DsrStatus.WITHDRAWN,
        }
    )
    return DataSubjectRequestOut(
        id=dsr.id,
        subject_user_id=dsr.subject_user_id,
        request_type=dsr.request_type,
        status=dsr.status,
        received_at=dsr.received_at,
        due_at=dsr.due_at,
        verified_at=dsr.verified_at,
        fulfilled_at=dsr.fulfilled_at,
        refusal_reason=dsr.refusal_reason,
        handled_by_user_id=dsr.handled_by_user_id,
        export_document_asset_id=dsr.export_document_asset_id,
        notes=dsr.notes,
        overdue=overdue,
        created_at=dsr.created_at,
        updated_at=dsr.updated_at,
    )


async def list_data_subject_requests(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: DsrStatus | None = None,
    request_type: DsrType | None = None,
    subject_user_id: UUID | None = None,
    overdue_only: bool = False,
    request: Request | None = None,
) -> Page[DataSubjectRequestOut]:
    query = tenant_scoped(select(DataSubjectRequest), DataSubjectRequest, context)
    if status is not None:
        query = query.where(DataSubjectRequest.status == status)
    if request_type is not None:
        query = query.where(DataSubjectRequest.request_type == request_type)
    if subject_user_id is not None:
        query = query.where(DataSubjectRequest.subject_user_id == subject_user_id)
    if overdue_only:
        query = query.where(
            DataSubjectRequest.due_at < _now(),
            DataSubjectRequest.status.in_(
                [DsrStatus.RECEIVED, DsrStatus.VERIFYING, DsrStatus.IN_PROGRESS]
            ),
        )

    total = await _count(db, query)
    requests = (
        await db.scalars(
            query.order_by(DataSubjectRequest.due_at).limit(page.limit + 1).offset(page.offset)
        )
    ).all()
    items = [_dsr_out(dsr) for dsr in requests]
    await _log_patient_reads(
        db,
        context,
        ids=[dsr.subject_user_id for dsr in requests],
        resource_type="data_subject_request",
        purpose_of_use="PATRQT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total)


async def create_data_subject_request(
    db: AsyncSession,
    context: AuthContext,
    payload: DataSubjectRequestCreate,
    request: Request | None = None,
) -> DataSubjectRequestOut:
    subject = await db.scalar(select(User.id).where(User.id == payload.subject_user_id))
    if subject is None:
        raise unprocessable("Unknown data subject")
    now = _now()
    due_at = payload.due_at or (now + timedelta(days=30))
    if due_at <= now:
        raise unprocessable("due_at must be in the future")

    dsr = DataSubjectRequest(
        tenant_id=context.tenant_id,
        subject_user_id=payload.subject_user_id,
        request_type=payload.request_type,
        status=DsrStatus.RECEIVED,
        received_at=now,
        due_at=due_at,
        notes=payload.notes,
    )
    db.add(dsr)
    await db.flush()
    await _log_patient_reads(
        db,
        context,
        ids=[payload.subject_user_id],
        resource_type="data_subject_request",
        purpose_of_use="PATRQT",
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="privacy.dsr.received",
        subject_user_id=payload.subject_user_id,
        resource_id=dsr.id,
        event_data={"request_type": payload.request_type.value, "due_at": due_at.isoformat()},
        request=request,
    )
    await db.commit()
    await db.refresh(dsr)
    return _dsr_out(dsr)


async def fulfil_data_subject_request(
    db: AsyncSession,
    context: AuthContext,
    dsr_id: UUID,
    payload: DataSubjectRequestFulfil,
    request: Request | None = None,
) -> DataSubjectRequestOut:
    query = tenant_scoped(select(DataSubjectRequest), DataSubjectRequest, context).where(
        DataSubjectRequest.id == dsr_id
    )
    dsr = await db.scalar(query)
    if dsr is None:
        raise not_found("Data subject request")
    assert_transition(dsr.status.value, DsrStatus.FULFILLED.value, DSR_TRANSITIONS)
    if payload.export_document_asset_id is not None:
        asset = await db.scalar(
            select(DocumentAsset.id).where(DocumentAsset.id == payload.export_document_asset_id)
        )
        if asset is None:
            raise unprocessable("Unknown export document")
        dsr.export_document_asset_id = payload.export_document_asset_id

    now = _now()
    dsr.status = DsrStatus.FULFILLED
    dsr.fulfilled_at = now
    dsr.handled_by_user_id = context.user.id
    if dsr.verified_at is None:
        dsr.verified_at = now
    if payload.notes is not None:
        dsr.notes = payload.notes

    await _log_patient_reads(
        db,
        context,
        ids=[dsr.subject_user_id],
        resource_type="data_subject_request",
        purpose_of_use="PATRQT",
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="privacy.dsr.fulfilled",
        subject_user_id=dsr.subject_user_id,
        resource_id=dsr.id,
        event_data={
            "request_type": dsr.request_type.value,
            "export_document_asset_id": (
                str(dsr.export_document_asset_id) if dsr.export_document_asset_id else None
            ),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(dsr)
    return _dsr_out(dsr)


# ---------------------------------------------------------------------------
# Platform analytics
# ---------------------------------------------------------------------------


async def platform_analytics(
    db: AsyncSession,
    context: AuthContext,
    *,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
) -> PlatformAnalytics:
    now = _now()
    end = window_to or now
    start = window_from or (end - timedelta(days=30))
    if start >= end:
        raise unprocessable("window_from must precede window_to")

    role_rows = (
        await db.execute(
            select(
                User.account_type,
                func.count(),
                func.count().filter(User.status == UserStatus.ACTIVE),
                func.count().filter(User.last_login_at >= start, User.last_login_at < end),
            )
            .group_by(User.account_type)
            .order_by(User.account_type)
        )
    ).all()

    encounters = tenant_scoped(select(Encounter), Encounter, context).subquery("scoped_encounters")
    encounter_rows = (
        await db.execute(
            select(encounters.c.status, func.count())
            .where(encounters.c.started_at >= start, encounters.c.started_at < end)
            .group_by(encounters.c.status)
            .order_by(encounters.c.status)
        )
    ).all()

    appointments = tenant_scoped(select(Appointment), Appointment, context).subquery(
        "scoped_appointments"
    )
    appointment_rows = (
        await db.execute(
            select(appointments.c.status, func.count())
            .where(appointments.c.booked_at >= start, appointments.c.booked_at < end)
            .group_by(appointments.c.status)
            .order_by(appointments.c.status)
        )
    ).all()

    claims = tenant_scoped(select(Claim), Claim, context).subquery("scoped_claims")
    claim_row = (
        await db.execute(
            select(
                func.count(claims.c.id),
                func.count().filter(claims.c.status == ClaimStatus.DENIED),
                func.coalesce(func.sum(claims.c.total_charge_cents), 0),
                func.coalesce(func.sum(claims.c.paid_cents), 0),
            ).where(
                func.coalesce(claims.c.submitted_at, claims.c.created_at) >= start,
                func.coalesce(claims.c.submitted_at, claims.c.created_at) < end,
            )
        )
    ).one()
    claim_status_rows = (
        await db.execute(
            select(claims.c.status, func.count())
            .where(
                func.coalesce(claims.c.submitted_at, claims.c.created_at) >= start,
                func.coalesce(claims.c.submitted_at, claims.c.created_at) < end,
            )
            .group_by(claims.c.status)
            .order_by(claims.c.status)
        )
    ).all()

    cases = tenant_scoped(select(SupportCase), SupportCase, context).subquery("scoped_cases")
    support_row = (
        await db.execute(
            select(
                func.count().filter(
                    cases.c.status.notin_([SupportStatus.RESOLVED, SupportStatus.CLOSED])
                ),
                func.count().filter(
                    cases.c.resolved_at.is_(None),
                    cases.c.sla_due_at < now,
                ),
            )
        )
    ).one()

    phi = tenant_scoped(select(PhiAccessEvent), PhiAccessEvent, context).subquery("scoped_phi")
    phi_row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(phi.c.purpose_of_use == "ETREAT"),
            ).where(phi.c.created_at >= start, phi.c.created_at < end)
        )
    ).one()

    encounter_buckets = [CountBucket(key=str(row[0]), count=int(row[1])) for row in encounter_rows]
    appointment_buckets = [
        CountBucket(key=str(row[0]), count=int(row[1])) for row in appointment_rows
    ]
    appointment_count = sum(bucket.count for bucket in appointment_buckets)
    no_shows = sum(
        bucket.count
        for bucket in appointment_buckets
        if bucket.key == AppointmentStatus.NO_SHOW.value
    )
    claim_count = int(claim_row[0])
    denied_count = int(claim_row[1])

    return PlatformAnalytics(
        window_from=start,
        window_to=end,
        roles=[
            RoleActivity(
                account_type=row[0],
                total_users=int(row[1]),
                active_users=int(row[2]),
                signed_in_users=int(row[3]),
            )
            for row in role_rows
        ],
        encounter_count=sum(bucket.count for bucket in encounter_buckets),
        encounters_by_status=encounter_buckets,
        appointment_count=appointment_count,
        appointments_by_status=appointment_buckets,
        no_show_rate=_rate(no_shows, appointment_count),
        claims=ClaimActivity(
            claim_count=claim_count,
            denied_count=denied_count,
            denial_rate=_rate(denied_count, claim_count),
            charged_cents=int(claim_row[2]),
            paid_cents=int(claim_row[3]),
            by_status=[
                CountBucket(key=str(row[0]), count=int(row[1])) for row in claim_status_rows
            ],
        ),
        open_support_cases=int(support_row[0]),
        breached_support_cases=int(support_row[1]),
        phi_access_events=int(phi_row[0]),
        break_glass_events=int(phi_row[1]),
    )
