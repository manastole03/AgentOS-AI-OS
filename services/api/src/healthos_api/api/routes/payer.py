"""Insurer / aggregator back-office endpoints.

Thin transport layer: validate, delegate to :mod:`healthos_api.domain.payer`,
return a Pydantic model. Every route is gated on both the ``insurance``/``admin``
role and the permission that matches the operation.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import ClaimStatus, PriorAuthStatus
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.payer import (
    AdjudicateRequest,
    AdjudicationResult,
    AnalyticsSummary,
    BenefitGridPut,
    BenefitGridResult,
    BenefitResponse,
    ClaimResponse,
    CostEstimateRequest,
    CostEstimateResponse,
    DenyRequest,
    EligibilityRequest,
    EligibilityResponse,
    ExplanationPut,
    ExplanationPutResult,
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    PriorAuthCreate,
    PriorAuthDecision,
    PriorAuthResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    adjudicate_claim,
    analytics_summary,
    create_cost_estimate,
    create_plan,
    create_prior_authorization,
    create_product,
    decide_prior_authorization,
    deny_claim,
    get_cost_estimate,
    list_claims,
    list_plan_benefits,
    list_plans,
    list_prior_authorizations,
    list_products,
    replace_plan_benefits,
    run_eligibility_check,
    update_plan,
    update_product,
    upsert_benefit_explanations,
)

router = APIRouter(prefix="/payer", tags=["payer"])

PayerRole = Depends(require_roles("insurance", "admin"))
DbDep = Annotated[AsyncSession, Depends(get_db)]
#: Product, plan, benefit and explanation surfaces are the policy catalogue.
PolicyContext = Annotated[AuthContext, Depends(require_permissions("policy:manage"))]
#: Eligibility, claims, prior auth, estimates and the dashboard are claims operations.
ClaimsContext = Annotated[AuthContext, Depends(require_permissions("claims:manage"))]
CsrfDep = Annotated[None, Depends(enforce_csrf)]


# --------------------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------------------


@router.get("/products", response_model=Page[ProductResponse], dependencies=[PayerRole])
async def get_products(
    context: PolicyContext,
    db: DbDep,
    page: PaginationDep,
    search: Annotated[str | None, Query(max_length=120)] = None,
    product_type: Annotated[str | None, Query(max_length=16)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[ProductResponse]:
    return await list_products(
        db,
        context,
        page=page,
        search=search,
        product_type=product_type,
        is_active=is_active,
    )


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[PayerRole],
)
async def post_product(
    payload: ProductCreate,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> ProductResponse:
    return await create_product(db, context, payload, request=request)


@router.patch("/products/{product_id}", response_model=ProductResponse, dependencies=[PayerRole])
async def patch_product(
    product_id: UUID,
    payload: ProductUpdate,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> ProductResponse:
    return await update_product(db, context, product_id, payload, request=request)


# --------------------------------------------------------------------------------------
# plans
# --------------------------------------------------------------------------------------


@router.get("/plans", response_model=Page[PlanResponse], dependencies=[PayerRole])
async def get_plans(
    context: PolicyContext,
    db: DbDep,
    page: PaginationDep,
    product_id: Annotated[UUID | None, Query()] = None,
    metal_tier: Annotated[str | None, Query(max_length=16)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
) -> Page[PlanResponse]:
    return await list_plans(
        db,
        context,
        page=page,
        product_id=product_id,
        metal_tier=metal_tier,
        is_active=is_active,
        search=search,
    )


@router.post(
    "/plans",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[PayerRole],
)
async def post_plan(
    payload: PlanCreate,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> PlanResponse:
    return await create_plan(db, context, payload, request=request)


@router.patch("/plans/{plan_id}", response_model=PlanResponse, dependencies=[PayerRole])
async def patch_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> PlanResponse:
    return await update_plan(db, context, plan_id, payload, request=request)


# --------------------------------------------------------------------------------------
# benefit grid and explanations
# --------------------------------------------------------------------------------------


@router.get(
    "/plans/{plan_id}/benefits", response_model=list[BenefitResponse], dependencies=[PayerRole]
)
async def get_plan_benefits(
    plan_id: UUID,
    context: PolicyContext,
    db: DbDep,
    as_of: Annotated[date | None, Query()] = None,
    include_closed: Annotated[bool, Query()] = False,
) -> list[BenefitResponse]:
    return await list_plan_benefits(
        db, context, plan_id, as_of=as_of, include_closed=include_closed
    )


@router.put("/plans/{plan_id}/benefits", response_model=BenefitGridResult, dependencies=[PayerRole])
async def put_plan_benefits(
    plan_id: UUID,
    payload: BenefitGridPut,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> BenefitGridResult:
    return await replace_plan_benefits(db, context, plan_id, payload, request=request)


@router.put(
    "/plans/{plan_id}/explanations",
    response_model=ExplanationPutResult,
    dependencies=[PayerRole],
)
async def put_plan_explanations(
    plan_id: UUID,
    payload: ExplanationPut,
    context: PolicyContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> ExplanationPutResult:
    return await upsert_benefit_explanations(db, context, plan_id, payload, request=request)


# --------------------------------------------------------------------------------------
# eligibility
# --------------------------------------------------------------------------------------


@router.post(
    "/eligibility/check",
    response_model=EligibilityResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[PayerRole],
)
async def post_eligibility_check(
    payload: EligibilityRequest,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> EligibilityResponse:
    return await run_eligibility_check(db, context, payload, request=request)


# --------------------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------------------


@router.get("/claims", response_model=Page[ClaimResponse], dependencies=[PayerRole])
async def get_claims(
    context: ClaimsContext,
    db: DbDep,
    page: PaginationDep,
    request: Request,
    claim_status: Annotated[ClaimStatus | None, Query(alias="status")] = None,
    payer: Annotated[UUID | None, Query()] = None,
    submitted_from: Annotated[date | None, Query(alias="from")] = None,
    submitted_to: Annotated[date | None, Query(alias="to")] = None,
    patient_user_id: Annotated[UUID | None, Query()] = None,
    breached_only: Annotated[bool, Query()] = False,
) -> Page[ClaimResponse]:
    return await list_claims(
        db,
        context,
        page=page,
        status=claim_status,
        payer_organization_id=payer,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        patient_user_id=patient_user_id,
        breached_only=breached_only,
        request=request,
    )


@router.post(
    "/claims/{claim_id}/adjudicate", response_model=AdjudicationResult, dependencies=[PayerRole]
)
async def post_claim_adjudication(
    claim_id: UUID,
    payload: AdjudicateRequest,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> AdjudicationResult:
    return await adjudicate_claim(db, context, claim_id, payload, request=request)


@router.post("/claims/{claim_id}/deny", response_model=ClaimResponse, dependencies=[PayerRole])
async def post_claim_denial(
    claim_id: UUID,
    payload: DenyRequest,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> ClaimResponse:
    return await deny_claim(db, context, claim_id, payload, request=request)


# --------------------------------------------------------------------------------------
# prior authorizations
# --------------------------------------------------------------------------------------


@router.get(
    "/prior-authorizations", response_model=Page[PriorAuthResponse], dependencies=[PayerRole]
)
async def get_prior_authorizations(
    context: ClaimsContext,
    db: DbDep,
    page: PaginationDep,
    request: Request,
    auth_status: Annotated[PriorAuthStatus | None, Query(alias="status")] = None,
    patient_user_id: Annotated[UUID | None, Query()] = None,
    policy_id: Annotated[UUID | None, Query()] = None,
    created_from: Annotated[date | None, Query(alias="from")] = None,
    created_to: Annotated[date | None, Query(alias="to")] = None,
) -> Page[PriorAuthResponse]:
    return await list_prior_authorizations(
        db,
        context,
        page=page,
        status=auth_status,
        patient_user_id=patient_user_id,
        policy_id=policy_id,
        created_from=created_from,
        created_to=created_to,
        request=request,
    )


@router.post(
    "/prior-authorizations",
    response_model=PriorAuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[PayerRole],
)
async def post_prior_authorization(
    payload: PriorAuthCreate,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> PriorAuthResponse:
    return await create_prior_authorization(db, context, payload, request=request)


@router.post(
    "/prior-authorizations/{auth_id}/decide",
    response_model=PriorAuthResponse,
    dependencies=[PayerRole],
)
async def post_prior_authorization_decision(
    auth_id: UUID,
    payload: PriorAuthDecision,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> PriorAuthResponse:
    return await decide_prior_authorization(db, context, auth_id, payload, request=request)


# --------------------------------------------------------------------------------------
# cost estimates
# --------------------------------------------------------------------------------------


@router.post(
    "/cost-estimates",
    response_model=CostEstimateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[PayerRole],
)
async def post_cost_estimate(
    payload: CostEstimateRequest,
    context: ClaimsContext,
    db: DbDep,
    request: Request,
    _csrf: CsrfDep,
) -> CostEstimateResponse:
    return await create_cost_estimate(db, context, payload, request=request)


@router.get(
    "/cost-estimates/{estimate_id}", response_model=CostEstimateResponse, dependencies=[PayerRole]
)
async def get_cost_estimate_by_id(
    estimate_id: UUID,
    context: PolicyContext,
    db: DbDep,
    request: Request,
) -> CostEstimateResponse:
    return await get_cost_estimate(db, context, estimate_id, request=request)


# --------------------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------------------


@router.get("/analytics/summary", response_model=AnalyticsSummary, dependencies=[PayerRole])
async def get_analytics_summary(
    context: ClaimsContext,
    db: DbDep,
    window_from: Annotated[date | None, Query(alias="from")] = None,
    window_to: Annotated[date | None, Query(alias="to")] = None,
) -> AnalyticsSummary:
    return await analytics_summary(db, context, window_from=window_from, window_to=window_to)
