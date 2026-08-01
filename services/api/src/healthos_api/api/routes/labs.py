"""Lab endpoints: catalogue, availability, booking, collection, results."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.labs import (
    CriticalResultOut,
    LabFacilityOut,
    LabOrderCreate,
    LabOrderDetail,
    LabOrderOut,
    LabResultOut,
    LabResultsCreate,
    LabTestOut,
    OrderCancel,
    PatientResultTrend,
    ResultAcknowledge,
    SlotAvailabilityOut,
    SpecimenCreate,
    SpecimenOut,
    acknowledge_result,
    cancel_order,
    create_order,
    critical_worklist,
    enter_results,
    find_availability,
    get_order,
    list_facilities,
    list_orders,
    list_tests,
    patient_result_series,
    register_specimen,
)
from healthos_api.integrations.clients import request_digest

router = APIRouter(prefix="/labs", tags=["labs"])

#: Roles that operate the lab itself: accessioning specimens and resulting.
#: These match the roles that migration 0009 grants ``lab:manage``.
LAB_ROLES = ("hospital", "admin")

#: Roles that may close a critical-value call-back loop.
CLINICIAN_ROLES = ("doctor", "hospital", "admin")


@router.get("/tests", response_model=Page[LabTestOut])
async def catalog(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    search: Annotated[str | None, Query(max_length=120)] = None,
    code: Annotated[str | None, Query(max_length=64)] = None,
    panel_code: Annotated[str | None, Query(max_length=64)] = None,
    specimen_type_code: Annotated[str | None, Query(max_length=64)] = None,
    fasting_required: bool | None = None,
    max_turnaround_hours: Annotated[int | None, Query(ge=0, le=8760)] = None,
    include_inactive: bool = False,
) -> Page[LabTestOut]:
    """Searchable test catalogue: code, specimen type, prep, TAT and price."""
    return await list_tests(
        db,
        context,
        page,
        search=search,
        code=code,
        panel_code=panel_code,
        specimen_type_code=specimen_type_code,
        fasting_required=fasting_required,
        max_turnaround_hours=max_turnaround_hours,
        include_inactive=include_inactive,
    )


@router.get("/facilities", response_model=Page[LabFacilityOut])
async def facilities(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    search: Annotated[str | None, Query(max_length=120)] = None,
    city: Annotated[str | None, Query(max_length=100)] = None,
    home_collection: bool | None = None,
    include_inactive: bool = False,
) -> Page[LabFacilityOut]:
    """Collection centres, with home-collection capability."""
    return await list_facilities(
        db,
        context,
        page,
        search=search,
        city=city,
        home_collection=home_collection,
        include_inactive=include_inactive,
    )


@router.get("/availability", response_model=Page[SlotAvailabilityOut])
async def availability(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    test_ids: Annotated[list[UUID] | None, Query()] = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
    facility_id: UUID | None = None,
) -> Page[SlotAvailabilityOut]:
    """Open slots that offer every requested test, with remaining capacity."""
    return await find_availability(
        db,
        context,
        page,
        test_ids=test_ids,
        from_at=from_at,
        to_at=to_at,
        facility_id=facility_id,
    )


@router.post(
    "/orders",
    response_model=LabOrderDetail,
    status_code=status.HTTP_201_CREATED,
)
async def book_order(
    payload: LabOrderCreate,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> LabOrderDetail:
    """Book a lab order against a slot, claiming capacity and raising the invoice."""
    detail, replayed = await create_order(
        db,
        context,
        payload,
        request=request,
        idempotency_key=idempotency_key,
        request_digest=request_digest(payload.model_dump(mode="json")),
    )
    if replayed:
        response.status_code = status.HTTP_200_OK
    return detail


@router.get("/orders", response_model=Page[LabOrderOut])
async def orders(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    patient_id: UUID | None = None,
    facility_id: UUID | None = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
) -> Page[LabOrderOut]:
    """Role-aware order list: own orders for patients, consented ones otherwise."""
    return await list_orders(
        db,
        context,
        page,
        status_filter=status_filter,
        patient_user_id=patient_id,
        facility_id=facility_id,
        from_at=from_at,
        to_at=to_at,
        request=request,
    )


@router.get("/orders/{order_id}", response_model=LabOrderDetail)
async def order_detail(
    order_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LabOrderDetail:
    """One order with its tests, specimens, results and invoice."""
    return await get_order(db, context, order_id, request=request)


@router.post("/orders/{order_id}/cancel", response_model=LabOrderDetail)
async def cancel(
    order_id: UUID,
    payload: OrderCancel,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LabOrderDetail:
    """Cancel an order, release the slot capacity and void the invoice."""
    return await cancel_order(db, context, order_id, payload, request=request)


@router.post(
    "/orders/{order_id}/specimens",
    response_model=SpecimenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*LAB_ROLES))],
)
async def collect_specimen(
    order_id: UUID,
    payload: SpecimenCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("lab:manage"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpecimenOut:
    """Register specimen collection and move the order to 'collected'."""
    return await register_specimen(db, context, order_id, payload, request=request)


@router.post(
    "/orders/{order_id}/results",
    response_model=list[LabResultOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*LAB_ROLES))],
)
async def post_results(
    order_id: UUID,
    payload: LabResultsCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("lab:manage"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LabResultOut]:
    """Enter results, flagging abnormal and panic values against the reference range."""
    return await enter_results(db, context, order_id, payload, request=request)


@router.get("/results/critical", response_model=Page[CriticalResultOut])
async def critical_results(
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    facility_id: UUID | None = None,
    ordering_provider_user_id: UUID | None = None,
    since: datetime | None = None,
) -> Page[CriticalResultOut]:
    """Unacknowledged critical-value worklist for the caller's organisation."""
    return await critical_worklist(
        db,
        context,
        page,
        facility_id=facility_id,
        ordering_provider_user_id=ordering_provider_user_id,
        since=since,
        request=request,
    )


@router.post(
    "/results/{result_id}/acknowledge",
    response_model=LabResultOut,
    dependencies=[Depends(require_roles(*CLINICIAN_ROLES))],
)
async def acknowledge(
    result_id: UUID,
    payload: ResultAcknowledge,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LabResultOut:
    """Clinician acknowledges a critical result, clearing it from the worklist."""
    return await acknowledge_result(db, context, result_id, payload, request=request)


@router.get("/patients/{patient_id}/results", response_model=PatientResultTrend)
async def patient_results(
    patient_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[list[str] | None, Query()] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> PatientResultTrend:
    """Trendable per-analyte result series for charting."""
    return await patient_result_series(
        db,
        context,
        patient_id,
        codes=code,
        since=since,
        until=until,
        limit=limit,
        request=request,
    )
