"""Insurance tab endpoints: claims assistance, coverage explanations, and the marketplace.

The router stays thin on purpose — validation of path/query shapes here, every
scoping, PHI-logging, and persistence decision in :mod:`healthos_api.domain.coverage`.
"""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions
from healthos_api.db.dependencies import get_db
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.coverage import (
    ApplicationCreate,
    ApplicationRead,
    ClaimAssistance,
    ClaimCreate,
    ClaimDetail,
    ClaimDocumentAttach,
    ClaimSummary,
    CoverageExplanation,
    DocumentLinkRead,
    LoyaltyBalance,
    MarketplaceResponse,
    MarketplaceSort,
    PlanDetail,
    PolicySummary,
    PurchaseRequest,
    PurchaseResult,
    attach_claim_documents,
    claim_assistance,
    create_application,
    create_claim,
    explain_policy,
    get_claim,
    get_plan,
    list_active_policies,
    list_claims,
    loyalty_summary,
    marketplace,
    purchase_application,
    resolve_patient,
)

router = APIRouter(prefix="/coverage", tags=["coverage"])

PatientQuery = Annotated[
    UUID | None,
    Query(description="Patient to read; defaults to the caller when they are a patient."),
]
LocaleQuery = Annotated[str, Query(min_length=2, max_length=16)]
ReadingLevelQuery = Annotated[str, Query(min_length=2, max_length=16)]


# --------------------------------------------------------------------------- #
# Tab 1 — Insurance claim
# --------------------------------------------------------------------------- #


@router.get("/me/policies", response_model=list[PolicySummary])
async def my_policies(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    patient_user_id: PatientQuery = None,
) -> list[PolicySummary]:
    """Active policies covering the patient, including anything bought in the marketplace."""
    target = await resolve_patient(db, context, patient_user_id)
    return await list_active_policies(db, context, patient_user_id=target, request=request)


@router.get("/policies/{policy_id}/explain", response_model=CoverageExplanation)
async def explain_coverage(
    policy_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    patient_user_id: PatientQuery = None,
    locale: LocaleQuery = "en-US",
    reading_level: ReadingLevelQuery = "grade6",
    benefit_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
) -> CoverageExplanation:
    """Structured benefits, grounded plain language, and the patient's accumulators."""
    target = await resolve_patient(db, context, patient_user_id)
    return await explain_policy(
        db,
        context,
        policy_id=policy_id,
        patient_user_id=target,
        locale=locale,
        reading_level=reading_level,
        benefit_year=benefit_year or datetime.now(UTC).year,
        request=request,
    )


@router.get("/me/claim-assistance", response_model=ClaimAssistance)
async def my_claim_assistance(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    patient_user_id: PatientQuery = None,
) -> ClaimAssistance:
    """Helpline number, hours, and the checklist of what to have ready."""
    target = await resolve_patient(db, context, patient_user_id)
    return await claim_assistance(db, context, patient_user_id=target, request=request)


@router.get("/claims", response_model=Page[ClaimSummary])
async def claims_index(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    patient_user_id: PatientQuery = None,
    policy_id: Annotated[UUID | None, Query()] = None,
    claim_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    service_from: Annotated[date | None, Query()] = None,
    service_to: Annotated[date | None, Query()] = None,
) -> Page[ClaimSummary]:
    """Claims the caller may read, newest service date first."""
    return await list_claims(
        db,
        context,
        page=page,
        patient_user_id=patient_user_id,
        policy_id=policy_id,
        status=claim_status,
        service_from=service_from,
        service_to=service_to,
        request=request,
    )


@router.post("/claims", response_model=ClaimDetail, status_code=status.HTTP_201_CREATED)
async def initiate_claim(
    payload: ClaimCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClaimDetail:
    """Open a claim with its lines and the first append-only claim event."""
    return await create_claim(db, context, payload, request=request)


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
async def claim_detail(
    claim_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClaimDetail:
    """A claim with its lines and its full status timeline."""
    return await get_claim(db, context, claim_id=claim_id, request=request)


@router.post(
    "/claims/{claim_id}/documents",
    response_model=list[DocumentLinkRead],
    status_code=status.HTTP_201_CREATED,
)
async def attach_documents(
    claim_id: UUID,
    payload: ClaimDocumentAttach,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DocumentLinkRead]:
    """Attach supporting documents to a claim through ``document_links``."""
    return await attach_claim_documents(
        db, context, claim_id=claim_id, payload=payload, request=request
    )


# --------------------------------------------------------------------------- #
# Tab 2 — Buy insurance
# --------------------------------------------------------------------------- #


@router.get("/marketplace", response_model=MarketplaceResponse)
async def browse_marketplace(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    patient_user_id: PatientQuery = None,
    sort: Annotated[MarketplaceSort, Query()] = "recommended",
    product_type: Annotated[str | None, Query(pattern="^(hmo|ppo|epo|pos|indemnity)$")] = None,
    metal_tier: Annotated[str | None, Query(max_length=16)] = None,
    payer_organization_id: Annotated[UUID | None, Query()] = None,
    currency: Annotated[str | None, Query(pattern="^[A-Za-z]{3}$")] = None,
    max_premium_cents: Annotated[int | None, Query(ge=0)] = None,
    max_deductible_cents: Annotated[int | None, Query(ge=0)] = None,
) -> MarketplaceResponse:
    """Ranked plans from every participating payer, with explainable reason codes."""
    target = await resolve_patient(db, context, patient_user_id)
    return await marketplace(
        db,
        context,
        patient_user_id=target,
        page=page,
        sort=sort,
        product_type=product_type,
        metal_tier=metal_tier,
        payer_organization_id=payer_organization_id,
        currency=currency,
        max_premium_cents=max_premium_cents,
        max_deductible_cents=max_deductible_cents,
        request=request,
    )


@router.get("/marketplace/plans/{plan_id}", response_model=PlanDetail)
async def marketplace_plan(
    plan_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: LocaleQuery = "en-US",
    reading_level: ReadingLevelQuery = "grade6",
) -> PlanDetail:
    """Full plan detail with its benefit grid."""
    return await get_plan(db, plan_id=plan_id, locale=locale, reading_level=reading_level)


@router.post("/applications", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def submit_application(
    payload: ApplicationCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationRead:
    """Collect the applicant's details and open a policy application."""
    return await create_application(db, context, payload, request=request)


@router.post(
    "/applications/{application_id}/purchase",
    response_model=PurchaseResult,
    status_code=status.HTTP_201_CREATED,
)
async def purchase_policy(
    application_id: UUID,
    payload: PurchaseRequest,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseResult:
    """Issue the policy, members, premium schedule, and loyalty accrual in one transaction."""
    return await purchase_application(
        db, context, application_id=application_id, payload=payload, request=request
    )


@router.get("/me/loyalty", response_model=LoyaltyBalance)
async def my_loyalty(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    patient_user_id: PatientQuery = None,
) -> LoyaltyBalance:
    """Loyalty balance plus a page of the append-only ledger."""
    target = await resolve_patient(db, context, patient_user_id)
    return await loyalty_summary(db, context, patient_user_id=target, page=page, request=request)
