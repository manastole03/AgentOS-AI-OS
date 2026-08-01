"""Medication ordering, reminder, and adherence endpoints.

Thin transport layer: validate, delegate to :mod:`healthos_api.domain.medications`,
return the response model. Consent scoping, PHI disclosure logging, and audit
writes all live in the service so they cannot be skipped by a new route.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions, require_roles
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import MedicationStatementStatus, PrescriptionStatus
from healthos_api.domain.common import Page, PaginationDep
from healthos_api.domain.medications import (
    AckResult,
    AdherenceReport,
    GenerateOccurrencesRequest,
    GenerationResult,
    MedicationStatementOut,
    PrescriptionCreate,
    PrescriptionOut,
    ReminderAck,
    ReminderOut,
    ReminderWindow,
    SafetyCheckBatch,
    SafetyCheckOut,
    ScheduleCreate,
    ScheduleOut,
    acknowledge_reminder,
    adherence_report,
    create_prescription,
    create_schedule,
    generate_occurrences,
    list_current_medications,
    list_prescriptions,
    list_reminders,
    record_safety_checks,
)

router = APIRouter(prefix="/medications", tags=["medications"])


@router.get("/patients/{patient_id}/prescriptions", response_model=Page[PrescriptionOut])
async def get_patient_prescriptions(
    patient_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    page: PaginationDep,
    status_filter: Annotated[PrescriptionStatus | None, Query(alias="status")] = None,
    include_superseded: bool = False,
) -> Page[PrescriptionOut]:
    """List a patient's prescriptions with their drugs, dosing, and safety checks."""
    return await list_prescriptions(
        db,
        context,
        patient_user_id=patient_id,
        page=page,
        status_filter=status_filter,
        include_superseded=include_superseded,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/prescriptions",
    response_model=PrescriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_patient_prescription(
    patient_id: UUID,
    payload: PrescriptionCreate,
    context: Annotated[
        AuthContext, Depends(require_permissions("clinical:write", "prescribe:write"))
    ],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> PrescriptionOut:
    """Issue a prescription with its medication requests, dosing, and safety checks."""
    return await create_prescription(
        db,
        context,
        patient_user_id=patient_id,
        payload=payload,
        request=request,
    )


@router.post(
    "/prescriptions/{prescription_id}/safety-checks",
    response_model=list[SafetyCheckOut],
    status_code=status.HTTP_201_CREATED,
)
async def post_safety_checks(
    prescription_id: UUID,
    payload: SafetyCheckBatch,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> list[SafetyCheckOut]:
    """Record allergy, interaction, and duplicate-therapy results for a prescription."""
    return await record_safety_checks(
        db,
        context,
        prescription_id=prescription_id,
        payload=payload,
        request=request,
    )


@router.get("/patients/{patient_id}/medications", response_model=Page[MedicationStatementOut])
async def get_patient_medications(
    patient_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    page: PaginationDep,
    status_filter: Annotated[MedicationStatementStatus | None, Query(alias="status")] = None,
) -> Page[MedicationStatementOut]:
    """Return the patient's current medication list."""
    return await list_current_medications(
        db,
        context,
        patient_user_id=patient_id,
        page=page,
        status_filter=status_filter,
        request=request,
    )


@router.post(
    "/medication-requests/{medication_request_id}/schedule",
    response_model=list[ScheduleOut],
    status_code=status.HTTP_201_CREATED,
)
async def post_medication_schedule(
    medication_request_id: UUID,
    payload: ScheduleCreate,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> list[ScheduleOut]:
    """Create the daily reminder schedule (times of day, timezone, start/end) for a drug."""
    return await create_schedule(
        db,
        context,
        medication_request_id=medication_request_id,
        payload=payload,
        request=request,
    )


@router.post("/schedules/{schedule_id}/generate-occurrences", response_model=GenerationResult)
async def post_generate_occurrences(
    schedule_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:write"))],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    payload: GenerateOccurrencesRequest | None = None,
) -> GenerationResult:
    """Materialize reminder occurrences up to the horizon and end the course when it is over."""
    return await generate_occurrences(
        db,
        context,
        schedule_id=schedule_id,
        payload=payload or GenerateOccurrencesRequest(),
        request=request,
    )


@router.get("/patients/{patient_id}/reminders", response_model=Page[ReminderOut])
async def get_patient_reminders(
    patient_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    page: PaginationDep,
    window: ReminderWindow = "today",
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> Page[ReminderOut]:
    """List pending medication reminders for today or the upcoming window."""
    return await list_reminders(
        db,
        context,
        patient_user_id=patient_id,
        window=window,
        days=days,
        page=page,
        request=request,
    )


@router.post(
    "/reminders/{occurrence_id}/ack",
    response_model=AckResult,
    status_code=status.HTTP_201_CREATED,
)
async def post_reminder_ack(
    occurrence_id: UUID,
    payload: ReminderAck,
    # Patients hold clinical:read but not clinical:write, and self-reported
    # adherence is the whole point of the reminder loop, so this one write is
    # role-gated instead of permission-gated. Consent scoping in the service
    # still limits a patient to their own occurrences.
    context: Annotated[
        AuthContext, Depends(require_roles("patient", "doctor", "hospital", "admin"))
    ],
    _csrf: Annotated[None, Depends(enforce_csrf)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> AckResult:
    """Record a dose as taken, skipped, or snoozed against a reminder occurrence."""
    return await acknowledge_reminder(
        db,
        context,
        occurrence_id=occurrence_id,
        payload=payload,
        request=request,
    )


@router.get("/patients/{patient_id}/adherence", response_model=AdherenceReport)
async def get_patient_adherence(
    patient_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("clinical:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> AdherenceReport:
    """Per-medication adherence rate (taken/expected) over a window, computed in SQL."""
    return await adherence_report(
        db,
        context,
        patient_user_id=patient_id,
        days=days,
        request=request,
    )
