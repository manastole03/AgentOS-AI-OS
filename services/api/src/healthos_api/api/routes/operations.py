"""Hospital operations, clinical documentation, and admin oversight endpoints.

The router stays thin: it validates and shapes, ``healthos_api.domain.operations``
owns scoping, PHI disclosure accounting, and the state machines.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import (
    CodeType,
    DsrStatus,
    DsrType,
    InvoiceStatus,
    ReferralStatus,
    ReviewStatus,
    SupportSeverity,
    SupportStatus,
)
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.operations import (
    AddendumCreate,
    AddendumOut,
    BreakGlassEntry,
    ClinicalNoteCreate,
    ClinicalNoteOut,
    CredentialingStatus,
    DataSubjectRequestCreate,
    DataSubjectRequestFulfil,
    DataSubjectRequestOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    EncounterCodeCreate,
    EncounterCodeOut,
    InvoiceDetailOut,
    InvoiceOut,
    NoteSignRequest,
    PaymentCreate,
    PaymentResult,
    PhiAccessOut,
    PlatformAnalytics,
    PractitionerRoleCreate,
    PractitionerRoleOut,
    PractitionerRoleUpdate,
    ReferralCreate,
    ReferralOut,
    ReferralStatusChange,
    RefundCreate,
    RefundResult,
    RevenueCycleSummary,
    ServiceItemCreate,
    ServiceItemOut,
    ServiceItemUpdate,
    SupportCaseCreate,
    SupportCaseOut,
    SupportCaseResult,
    SupportCommentCreate,
    SupportCommentOut,
    SupportEscalateRequest,
    SupportTransitionRequest,
    add_note_addendum,
    add_support_comment,
    break_glass_register,
    change_referral_status,
    create_data_subject_request,
    create_department,
    create_encounter_code,
    create_encounter_note,
    create_practitioner_role,
    create_referral,
    create_service_item,
    create_support_case,
    escalate_support_case,
    fulfil_data_subject_request,
    get_invoice_detail,
    list_data_subject_requests,
    list_departments,
    list_encounter_codes,
    list_encounter_notes,
    list_invoices,
    list_phi_access,
    list_practitioners,
    list_referrals,
    list_service_items,
    list_support_cases,
    platform_analytics,
    record_invoice_payment,
    refund_payment,
    revenue_cycle_summary,
    sign_note,
    transition_support_case,
    update_department,
    update_practitioner_role,
    update_service_item,
)

router = APIRouter(prefix="/operations", tags=["operations"])

hospital_only = Depends(require_roles("hospital", "admin"))
clinician_only = Depends(require_roles("doctor", "hospital", "admin"))
admin_only = Depends(require_roles("admin"))

DbSession = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Hospital directory
# ---------------------------------------------------------------------------


@router.get("/departments", response_model=Page[DepartmentOut], dependencies=[hospital_only])
async def get_departments(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: DbSession,
    page: PaginationDep,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[DepartmentOut]:
    """List the organization's departments."""
    return await list_departments(db, context, page=page, is_active=is_active, search=search)


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[hospital_only],
)
async def post_department(
    payload: DepartmentCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> DepartmentOut:
    """Open a new department in the caller's organization."""
    return await create_department(db, context, payload, request)


@router.patch(
    "/departments/{department_id}", response_model=DepartmentOut, dependencies=[hospital_only]
)
async def patch_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> DepartmentOut:
    """Rename, re-parent, or deactivate a department."""
    return await update_department(db, context, department_id, payload, request)


@router.get(
    "/practitioners", response_model=Page[PractitionerRoleOut], dependencies=[hospital_only]
)
async def get_practitioners(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: DbSession,
    page: PaginationDep,
    credentialing_status: Annotated[CredentialingStatus | None, Query()] = None,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    department_id: Annotated[UUID | None, Query()] = None,
    specialty_code: Annotated[str | None, Query(max_length=64)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[PractitionerRoleOut]:
    """Credentialing register: privileges, status, and licence expiry."""
    return await list_practitioners(
        db,
        context,
        page=page,
        credentialing_status=credentialing_status,
        expiring_within_days=expiring_within_days,
        department_id=department_id,
        specialty_code=specialty_code,
        is_active=is_active,
    )


@router.post(
    "/practitioners",
    response_model=PractitionerRoleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[hospital_only],
)
async def post_practitioner(
    payload: PractitionerRoleCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> PractitionerRoleOut:
    """Affiliate a practitioner and record their initial credentialing state."""
    return await create_practitioner_role(db, context, payload, request)


@router.patch(
    "/practitioners/{role_id}",
    response_model=PractitionerRoleOut,
    dependencies=[hospital_only],
)
async def patch_practitioner(
    role_id: UUID,
    payload: PractitionerRoleUpdate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> PractitionerRoleOut:
    """Update privileges, credentialing status, or licence expiry."""
    return await update_practitioner_role(db, context, role_id, payload, request)


# ---------------------------------------------------------------------------
# Chargemaster
# ---------------------------------------------------------------------------


@router.get("/service-catalog", response_model=Page[ServiceItemOut], dependencies=[hospital_only])
async def get_service_catalog(
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    page: PaginationDep,
    service_code: Annotated[str | None, Query(max_length=64)] = None,
    department_id: Annotated[UUID | None, Query()] = None,
    effective_on: Annotated[date | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[ServiceItemOut]:
    """Chargemaster listing with negotiated-rate coverage per code."""
    return await list_service_items(
        db,
        context,
        page=page,
        service_code=service_code,
        department_id=department_id,
        effective_on=effective_on,
        is_active=is_active,
        search=search,
    )


@router.post(
    "/service-catalog",
    response_model=ServiceItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[hospital_only],
)
async def post_service_item(
    payload: ServiceItemCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ServiceItemOut:
    """Add a chargemaster entry effective from a given date."""
    return await create_service_item(db, context, payload, request)


@router.patch(
    "/service-catalog/{service_item_id}",
    response_model=ServiceItemOut,
    dependencies=[hospital_only],
)
async def patch_service_item(
    service_item_id: UUID,
    payload: ServiceItemUpdate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ServiceItemOut:
    """Reprice, retire, or re-describe a chargemaster entry."""
    return await update_service_item(db, context, service_item_id, payload, request)


# ---------------------------------------------------------------------------
# Revenue cycle
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=Page[InvoiceOut], dependencies=[hospital_only])
async def get_invoices(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    page: PaginationDep,
    invoice_status: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    issued_from: Annotated[datetime | None, Query(alias="from")] = None,
    issued_to: Annotated[datetime | None, Query(alias="to")] = None,
    patient_id: Annotated[UUID | None, Query()] = None,
) -> Page[InvoiceOut]:
    """List invoices with captured and refunded totals."""
    return await list_invoices(
        db,
        context,
        page=page,
        status=invoice_status,
        issued_from=issued_from,
        issued_to=issued_to,
        patient_user_id=patient_id,
        request=request,
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut, dependencies=[hospital_only])
async def get_invoice(
    invoice_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
) -> InvoiceDetailOut:
    """One invoice with its lines, payments, refunds, and linked documents."""
    return await get_invoice_detail(db, context, invoice_id, request)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[hospital_only],
)
async def post_invoice_payment(
    invoice_id: UUID,
    payload: PaymentCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> PaymentResult:
    """Capture a payment against an invoice, idempotent on idempotency_key."""
    return await record_invoice_payment(db, context, invoice_id, payload, request)


@router.post(
    "/payments/{payment_id}/refund",
    response_model=RefundResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[hospital_only],
)
async def post_payment_refund(
    payment_id: UUID,
    payload: RefundCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> RefundResult:
    """Refund part or all of a captured payment and restate the invoice."""
    return await refund_payment(db, context, payment_id, payload, request)


@router.get(
    "/revenue-cycle/summary", response_model=RevenueCycleSummary, dependencies=[hospital_only]
)
async def get_revenue_cycle_summary(
    context: Annotated[AuthContext, Depends(require_permissions("billing:manage"))],
    db: DbSession,
    window_from: Annotated[datetime | None, Query(alias="from")] = None,
    window_to: Annotated[datetime | None, Query(alias="to")] = None,
    currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
) -> RevenueCycleSummary:
    """AR aging, collected vs billed, and claim denial rate for the dashboard."""
    return await revenue_cycle_summary(
        db, context, window_from=window_from, window_to=window_to, currency=currency
    )


# ---------------------------------------------------------------------------
# Clinical documentation
# ---------------------------------------------------------------------------


@router.get(
    "/encounters/{encounter_id}/notes",
    response_model=Page[ClinicalNoteOut],
    dependencies=[clinician_only],
)
async def get_encounter_notes(
    encounter_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: DbSession,
    page: PaginationDep,
    include_superseded: Annotated[bool, Query()] = False,
) -> Page[ClinicalNoteOut]:
    """Notes for an encounter, each with its signed addenda."""
    return await list_encounter_notes(
        db,
        context,
        encounter_id,
        page=page,
        include_superseded=include_superseded,
        request=request,
    )


@router.post(
    "/encounters/{encounter_id}/notes",
    response_model=ClinicalNoteOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[clinician_only],
)
async def post_encounter_note(
    encounter_id: UUID,
    payload: ClinicalNoteCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ClinicalNoteOut:
    """Draft a clinical note, optionally superseding an unsigned earlier version."""
    return await create_encounter_note(db, context, encounter_id, payload, request)


@router.post("/notes/{note_id}/sign", response_model=ClinicalNoteOut, dependencies=[clinician_only])
async def post_note_signature(
    note_id: UUID,
    payload: NoteSignRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ClinicalNoteOut:
    """Sign a draft note; the row becomes immutable in the database."""
    return await sign_note(db, context, note_id, payload, request)


@router.post(
    "/notes/{note_id}/addenda",
    response_model=AddendumOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[clinician_only],
)
async def post_note_addendum(
    note_id: UUID,
    payload: AddendumCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> AddendumOut:
    """Append a signed addendum: the only way to amend a signed note."""
    return await add_note_addendum(db, context, note_id, payload, request)


@router.get(
    "/encounters/{encounter_id}/codes",
    response_model=Page[EncounterCodeOut],
    dependencies=[clinician_only],
)
async def get_encounter_codes(
    encounter_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: DbSession,
    page: PaginationDep,
    code_type: Annotated[CodeType | None, Query()] = None,
    review_status: Annotated[ReviewStatus | None, Query()] = None,
) -> Page[EncounterCodeOut]:
    """ICD-10/CPT codes on an encounter with coder, confidence, and review state."""
    return await list_encounter_codes(
        db,
        context,
        encounter_id,
        page=page,
        code_type=code_type,
        review_status=review_status,
        request=request,
    )


@router.post(
    "/encounters/{encounter_id}/codes",
    response_model=EncounterCodeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[clinician_only],
)
async def post_encounter_code(
    encounter_id: UUID,
    payload: EncounterCodeCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> EncounterCodeOut:
    """Code an encounter; accepting an AI suggestion records the human reviewer."""
    return await create_encounter_code(db, context, encounter_id, payload, request)


@router.get("/referrals", response_model=Page[ReferralOut], dependencies=[clinician_only])
async def get_referrals(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: DbSession,
    page: PaginationDep,
    referral_status: Annotated[ReferralStatus | None, Query(alias="status")] = None,
    patient_id: Annotated[UUID | None, Query()] = None,
    specialty_code: Annotated[str | None, Query(max_length=64)] = None,
    direction: Annotated[Literal["incoming", "outgoing"] | None, Query()] = None,
) -> Page[ReferralOut]:
    """Consent-scoped referral worklist, inbound or outbound."""
    return await list_referrals(
        db,
        context,
        page=page,
        status=referral_status,
        patient_user_id=patient_id,
        specialty_code=specialty_code,
        direction=direction,
        request=request,
    )


@router.post(
    "/referrals",
    response_model=ReferralOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[clinician_only],
)
async def post_referral(
    payload: ReferralCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ReferralOut:
    """Raise a referral as a draft, or send it immediately."""
    return await create_referral(db, context, payload, request)


@router.post(
    "/referrals/{referral_id}/status", response_model=ReferralOut, dependencies=[clinician_only]
)
async def post_referral_status(
    referral_id: UUID,
    payload: ReferralStatusChange,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> ReferralOut:
    """Advance a referral through its state machine."""
    return await change_referral_status(db, context, referral_id, payload, request)


# ---------------------------------------------------------------------------
# Support desk
# ---------------------------------------------------------------------------


@router.get("/support-cases", response_model=Page[SupportCaseOut], dependencies=[admin_only])
async def get_support_cases(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("support:manage"))],
    db: DbSession,
    page: PaginationDep,
    case_status: Annotated[SupportStatus | None, Query(alias="status")] = None,
    severity: Annotated[SupportSeverity | None, Query()] = None,
    queue: Annotated[str | None, Query(max_length=64)] = None,
    assignee_user_id: Annotated[UUID | None, Query()] = None,
    breached_only: Annotated[bool, Query()] = False,
) -> Page[SupportCaseOut]:
    """Support queue ordered by severity then SLA deadline."""
    return await list_support_cases(
        db,
        context,
        page=page,
        status=case_status,
        severity=severity,
        queue=queue,
        assignee_user_id=assignee_user_id,
        breached_only=breached_only,
        request=request,
    )


@router.post(
    "/support-cases",
    response_model=SupportCaseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[admin_only],
)
async def post_support_case(
    payload: SupportCaseCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("support:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> SupportCaseOut:
    """Open a case; the SLA deadline follows the severity."""
    return await create_support_case(db, context, payload, request)


@router.post(
    "/support-cases/{case_id}/comments",
    response_model=SupportCommentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[admin_only],
)
async def post_support_comment(
    case_id: UUID,
    payload: SupportCommentCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("support:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> SupportCommentOut:
    """Comment on a case, stamping first response when an agent replies."""
    return await add_support_comment(db, context, case_id, payload, request)


@router.post(
    "/support-cases/{case_id}/transition",
    response_model=SupportCaseResult,
    dependencies=[admin_only],
)
async def post_support_transition(
    case_id: UUID,
    payload: SupportTransitionRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("support:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> SupportCaseResult:
    """Move a case through the state machine, appending an immutable event."""
    return await transition_support_case(db, context, case_id, payload, request)


@router.post(
    "/support-cases/{case_id}/escalate",
    response_model=SupportCaseResult,
    dependencies=[admin_only],
)
async def post_support_escalation(
    case_id: UUID,
    payload: SupportEscalateRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("support:manage"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> SupportCaseResult:
    """Escalate a case, optionally raising severity and resetting the SLA clock."""
    return await escalate_support_case(db, context, case_id, payload, request)


# ---------------------------------------------------------------------------
# Disclosure accounting and privacy
# ---------------------------------------------------------------------------


@router.get("/phi-access", response_model=Page[PhiAccessOut], dependencies=[admin_only])
async def get_phi_access(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("phi:audit:read"))],
    db: DbSession,
    page: PaginationDep,
    patient_id: Annotated[UUID | None, Query()] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    accessed_from: Annotated[datetime | None, Query(alias="from")] = None,
    accessed_to: Annotated[datetime | None, Query(alias="to")] = None,
    purpose_of_use: Annotated[str | None, Query(max_length=64)] = None,
    resource_type: Annotated[str | None, Query(max_length=64)] = None,
) -> Page[PhiAccessOut]:
    """The HIPAA disclosure-accounting log."""
    return await list_phi_access(
        db,
        context,
        page=page,
        patient_user_id=patient_id,
        actor_user_id=actor_id,
        accessed_from=accessed_from,
        accessed_to=accessed_to,
        purpose_of_use=purpose_of_use,
        resource_type=resource_type,
        request=request,
    )


@router.get(
    "/phi-access/break-glass", response_model=Page[BreakGlassEntry], dependencies=[admin_only]
)
async def get_break_glass(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("phi:audit:read"))],
    db: DbSession,
    page: PaginationDep,
    accessed_from: Annotated[datetime | None, Query(alias="from")] = None,
    accessed_to: Annotated[datetime | None, Query(alias="to")] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
) -> Page[BreakGlassEntry]:
    """Emergency-access (ETREAT) register, aggregated per actor and patient."""
    return await break_glass_register(
        db,
        context,
        page=page,
        accessed_from=accessed_from,
        accessed_to=accessed_to,
        actor_user_id=actor_id,
        request=request,
    )


@router.get(
    "/data-subject-requests",
    response_model=Page[DataSubjectRequestOut],
    dependencies=[admin_only],
)
async def get_data_subject_requests(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("phi:audit:read"))],
    db: DbSession,
    page: PaginationDep,
    dsr_status: Annotated[DsrStatus | None, Query(alias="status")] = None,
    request_type: Annotated[DsrType | None, Query()] = None,
    subject_id: Annotated[UUID | None, Query()] = None,
    overdue_only: Annotated[bool, Query()] = False,
) -> Page[DataSubjectRequestOut]:
    """Privacy request queue, ordered by statutory due date."""
    return await list_data_subject_requests(
        db,
        context,
        page=page,
        status=dsr_status,
        request_type=request_type,
        subject_user_id=subject_id,
        overdue_only=overdue_only,
        request=request,
    )


@router.post(
    "/data-subject-requests",
    response_model=DataSubjectRequestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[admin_only],
)
async def post_data_subject_request(
    payload: DataSubjectRequestCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("phi:audit:read"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> DataSubjectRequestOut:
    """Register a data subject request with a 30-day default deadline."""
    return await create_data_subject_request(db, context, payload, request)


@router.post(
    "/data-subject-requests/{dsr_id}/fulfil",
    response_model=DataSubjectRequestOut,
    dependencies=[admin_only],
)
async def post_data_subject_request_fulfilment(
    dsr_id: UUID,
    payload: DataSubjectRequestFulfil,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("phi:audit:read"))],
    db: DbSession,
    _csrf: Annotated[None, Depends(enforce_csrf)],
) -> DataSubjectRequestOut:
    """Close out a privacy request, attaching the export that satisfied it."""
    return await fulfil_data_subject_request(db, context, dsr_id, payload, request)


@router.get("/analytics/platform", response_model=PlatformAnalytics, dependencies=[admin_only])
async def get_platform_analytics(
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: DbSession,
    window_from: Annotated[datetime | None, Query(alias="from")] = None,
    window_to: Annotated[datetime | None, Query(alias="to")] = None,
) -> PlatformAnalytics:
    """Platform dashboard: users by role, encounters, appointments, claims."""
    return await platform_analytics(db, context, window_from=window_from, window_to=window_to)
