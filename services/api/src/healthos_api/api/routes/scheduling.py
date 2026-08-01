"""Scheduling API: availability search, booking, payment, telehealth, schedules.

The router stays thin on purpose — validation and shaping live here, every rule
that touches the database (locking, PHI logging, state machine) lives in
:mod:`healthos_api.domain.scheduling`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import AppointmentStatus, EncounterChannel
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.scheduling import (
    AppointmentCreate,
    AppointmentResponse,
    AvailabilitySlot,
    BookingResponse,
    CancelRequest,
    PaymentCreate,
    PaymentResponse,
    ProviderScheduleCreate,
    ProviderScheduleResponse,
    RescheduleRequest,
    SlotGenerationRequest,
    SlotGenerationResult,
    TelehealthCreate,
    TelehealthSessionResponse,
    book_appointment,
    cancel_appointment,
    create_provider_schedule,
    generate_slots,
    get_appointment,
    list_appointments,
    list_provider_schedules,
    pay_appointment,
    reschedule_appointment,
    search_availability,
    start_telehealth_session,
)

router = APIRouter(prefix="/scheduling", tags=["scheduling"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=255)]


@router.get("/providers/availability", response_model=Page[AvailabilitySlot])
async def providers_availability(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    specialty: Annotated[str | None, Query(max_length=150)] = None,
    organization_id: Annotated[UUID | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    mode: Annotated[EncounterChannel | None, Query()] = None,
) -> Page[AvailabilitySlot]:
    """Open, priced provider slots matching the search filters."""
    return await search_availability(
        db,
        context,
        page=page,
        specialty=specialty,
        organization_id=organization_id,
        start_from=from_,
        start_to=to,
        mode=mode,
    )


@router.post(
    "/appointments",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: AppointmentCreate,
    request: Request,
    idempotency_key: IdempotencyKey = None,
) -> BookingResponse:
    """Book a slot race-safely and raise the consultation invoice."""
    return await book_appointment(
        db, context, payload, idempotency_key=idempotency_key, request=request
    )


@router.get("/appointments", response_model=Page[AppointmentResponse])
async def get_appointments(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    request: Request,
    status_filter: Annotated[AppointmentStatus | None, Query(alias="status")] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> Page[AppointmentResponse]:
    """Role-aware appointment list: own, panel, or organization."""
    return await list_appointments(
        db,
        context,
        page=page,
        status_filter=status_filter,
        start_from=from_,
        start_to=to,
        request=request,
    )


@router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def read_appointment(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    appointment_id: UUID,
    request: Request,
) -> AppointmentResponse:
    """A single appointment, with provider and patient display names."""
    return await get_appointment(db, context, appointment_id, request=request)


@router.post("/appointments/{appointment_id}/pay", response_model=PaymentResponse)
async def pay(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    appointment_id: UUID,
    payload: PaymentCreate,
    request: Request,
    idempotency_key: IdempotencyKey = None,
) -> PaymentResponse:
    """Authorize or capture the consultation fee and settle the invoice."""
    return await pay_appointment(
        db,
        context,
        appointment_id,
        payload,
        idempotency_key=idempotency_key,
        request=request,
    )


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    appointment_id: UUID,
    payload: CancelRequest,
    request: Request,
) -> AppointmentResponse:
    """Cancel an appointment, free its seat, and void an unpaid invoice."""
    return await cancel_appointment(db, context, appointment_id, payload, request=request)


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    appointment_id: UUID,
    payload: RescheduleRequest,
    request: Request,
) -> AppointmentResponse:
    """Move an appointment to another slot, freeing the old one atomically."""
    return await reschedule_appointment(db, context, appointment_id, payload, request=request)


@router.post(
    "/appointments/{appointment_id}/telehealth",
    response_model=TelehealthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def telehealth(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    appointment_id: UUID,
    payload: TelehealthCreate,
    request: Request,
) -> TelehealthSessionResponse:
    """Create the telehealth session and return one-time join details."""
    return await start_telehealth_session(db, context, appointment_id, payload, request=request)


@router.get("/provider-schedules", response_model=Page[ProviderScheduleResponse])
async def get_provider_schedules(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: PaginationDep,
    provider_user_id: Annotated[UUID | None, Query()] = None,
    organization_id: Annotated[UUID | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[ProviderScheduleResponse]:
    """Recurring availability templates for the caller's tenant."""
    return await list_provider_schedules(
        db,
        context,
        page=page,
        provider_user_id=provider_user_id,
        organization_id=organization_id,
        is_active=is_active,
    )


@router.post(
    "/provider-schedules",
    response_model=ProviderScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_provider_schedule(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: ProviderScheduleCreate,
    request: Request,
) -> ProviderScheduleResponse:
    """Define a recurring weekly availability template for a provider."""
    return await create_provider_schedule(db, context, payload, request=request)


@router.post(
    "/provider-schedules/{schedule_id}/generate-slots",
    response_model=SlotGenerationResult,
    status_code=status.HTTP_201_CREATED,
)
async def post_generate_slots(
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    schedule_id: UUID,
    payload: SlotGenerationRequest,
    request: Request,
) -> SlotGenerationResult:
    """Expand a schedule into appointment slots over a date range, idempotently."""
    return await generate_slots(db, context, schedule_id, payload, request=request)
