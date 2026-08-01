"""Clinical REST surface.

Thin by design: every handler validates, delegates to
:mod:`healthos_api.domain.clinical`, and returns a Pydantic model. Consent
scoping, PHI disclosure accounting, and audit writes live in the service layer
so they cannot be forgotten by a new endpoint.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.config import Settings, get_settings
from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import (
    ClinicalStatus,
    EncounterClass,
    EncounterStatus,
    GrowthSource,
)
from healthos_api.domain.clinical import (
    AllergyCreate,
    AllergyOut,
    AllergyReviewIn,
    AllergyStatusOut,
    CertificateIssueIn,
    CertificateOut,
    ConditionCreate,
    ConditionOut,
    EncounterCreate,
    EncounterOut,
    GrowthCreate,
    GrowthOut,
    GrowthPercentileSeries,
    ImmunizationCreate,
    ImmunizationDueOut,
    ImmunizationOut,
    PatientSummary,
    TimelineEntry,
    VitalCreate,
    VitalOut,
    create_allergy,
    create_condition,
    create_encounter,
    create_growth,
    create_immunization,
    create_vital,
    get_certificate,
    growth_percentiles,
    immunizations_due,
    issue_certificate,
    list_allergies,
    list_conditions,
    list_encounters,
    list_growth,
    list_immunizations,
    list_vitals,
    patient_summary,
    patient_timeline,
    review_allergies,
    update_encounter_status,
)
from healthos_api.domain.common import Page, PaginationDep, StatusChange

router = APIRouter(prefix="/clinical", tags=["clinical"])

ReadContext = Annotated[AuthContext, Depends(require_permissions("clinical:read"))]
WriteContext = Annotated[AuthContext, Depends(require_permissions("clinical:write"))]
Csrf = Annotated[None, Depends(enforce_csrf)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/patients/{patient_id}/timeline", response_model=Page[TimelineEntry])
async def get_timeline(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
) -> Page[TimelineEntry]:
    """Visit timeline: encounters newest-first with diagnoses, clinician, counts."""
    return await patient_timeline(db, context, patient_id=patient_id, page=page, request=request)


@router.get("/patients/{patient_id}/encounters", response_model=Page[EncounterOut])
async def get_encounters(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    encounter_status: Annotated[EncounterStatus | None, Query(alias="status")] = None,
    class_code: Annotated[EncounterClass | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> Page[EncounterOut]:
    """List a patient's encounters, newest first."""
    return await list_encounters(
        db,
        context,
        patient_id=patient_id,
        page=page,
        status_filter=encounter_status,
        class_code=class_code,
        since=since,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/encounters",
    response_model=EncounterOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_encounter(
    patient_id: UUID,
    payload: EncounterCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> EncounterOut:
    """Open a new encounter for a patient."""
    return await create_encounter(
        db, context, patient_id=patient_id, payload=payload, request=request
    )


@router.patch("/encounters/{encounter_id}", response_model=EncounterOut)
async def patch_encounter_status(
    encounter_id: UUID,
    payload: StatusChange,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> EncounterOut:
    """Move an encounter along its status state machine."""
    return await update_encounter_status(
        db, context, encounter_id=encounter_id, payload=payload, request=request
    )


@router.get("/patients/{patient_id}/conditions", response_model=Page[ConditionOut])
async def get_conditions(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    clinical_status: Annotated[ClinicalStatus | None, Query()] = None,
    include_superseded: Annotated[bool, Query()] = False,
) -> Page[ConditionOut]:
    """List a patient's problem list."""
    return await list_conditions(
        db,
        context,
        patient_id=patient_id,
        page=page,
        clinical_status=clinical_status,
        include_superseded=include_superseded,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/conditions",
    response_model=ConditionOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_condition(
    patient_id: UUID,
    payload: ConditionCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> ConditionOut:
    """Record a condition, or supersede an earlier version of one."""
    return await create_condition(
        db, context, patient_id=patient_id, payload=payload, request=request
    )


@router.get("/patients/{patient_id}/allergies", response_model=Page[AllergyOut])
async def get_allergies(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    active_only: Annotated[bool, Query()] = True,
) -> Page[AllergyOut]:
    """List allergies and intolerances, most critical first."""
    return await list_allergies(
        db,
        context,
        patient_id=patient_id,
        page=page,
        active_only=active_only,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/allergies",
    response_model=AllergyOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_allergy(
    patient_id: UUID,
    payload: AllergyCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> AllergyOut:
    """Record an allergy together with its past reactions."""
    return await create_allergy(
        db, context, patient_id=patient_id, payload=payload, request=request
    )


@router.post("/patients/{patient_id}/allergies/review", response_model=AllergyStatusOut)
async def post_allergy_review(
    patient_id: UUID,
    payload: AllergyReviewIn,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> AllergyStatusOut:
    """Attest that the allergy list was reviewed, optionally asserting NKA."""
    return await review_allergies(
        db, context, patient_id=patient_id, payload=payload, request=request
    )


@router.get("/patients/{patient_id}/vitals", response_model=Page[VitalOut])
async def get_vitals(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    code: Annotated[str | None, Query(max_length=64)] = None,
    since: Annotated[datetime | None, Query()] = None,
) -> Page[VitalOut]:
    """Vital-sign trend, ascending by effective time and ready to chart."""
    return await list_vitals(
        db,
        context,
        patient_id=patient_id,
        page=page,
        code=code,
        since=since,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/vitals",
    response_model=VitalOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_vital(
    patient_id: UUID,
    payload: VitalCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> VitalOut:
    """Record an observation, including multi-component panels such as BP."""
    return await create_vital(db, context, patient_id=patient_id, payload=payload, request=request)


@router.get("/patients/{patient_id}/growth", response_model=Page[GrowthOut])
async def get_growth(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    since: Annotated[datetime | None, Query()] = None,
) -> Page[GrowthOut]:
    """Paediatric growth points, oldest first."""
    return await list_growth(
        db, context, patient_id=patient_id, page=page, since=since, request=request
    )


@router.post(
    "/patients/{patient_id}/growth",
    response_model=GrowthOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_growth(
    patient_id: UUID,
    payload: GrowthCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
    standard: Annotated[GrowthSource, Query()] = GrowthSource.WHO,
) -> GrowthOut:
    """Record a growth measurement and score it against the reference curves."""
    return await create_growth(
        db,
        context,
        patient_id=patient_id,
        payload=payload,
        source_standard=standard,
        request=request,
    )


@router.get("/patients/{patient_id}/growth/percentiles", response_model=GrowthPercentileSeries)
async def get_growth_percentiles(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    standard: Annotated[GrowthSource, Query()] = GrowthSource.WHO,
    since: Annotated[datetime | None, Query()] = None,
) -> GrowthPercentileSeries:
    """LMS percentile and z-score per growth point; null where no curve covers it."""
    return await growth_percentiles(
        db,
        context,
        patient_id=patient_id,
        page=page,
        source_standard=standard,
        since=since,
        request=request,
    )


@router.get("/patients/{patient_id}/immunizations", response_model=Page[ImmunizationOut])
async def get_immunizations(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    page: PaginationDep,
    request: Request,
    vaccine_code: Annotated[str | None, Query(max_length=64)] = None,
) -> Page[ImmunizationOut]:
    """List administered, refused, and contraindicated doses."""
    return await list_immunizations(
        db,
        context,
        patient_id=patient_id,
        page=page,
        vaccine_code=vaccine_code,
        request=request,
    )


@router.post(
    "/patients/{patient_id}/immunizations",
    response_model=ImmunizationOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_immunization(
    patient_id: UUID,
    payload: ImmunizationCreate,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
) -> ImmunizationOut:
    """Record an immunization event."""
    return await create_immunization(
        db, context, patient_id=patient_id, payload=payload, request=request
    )


@router.get("/patients/{patient_id}/immunizations/due", response_model=ImmunizationDueOut)
async def get_immunizations_due(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    request: Request,
    horizon_days: Annotated[int, Query(ge=1, le=730)] = 90,
) -> ImmunizationDueOut:
    """Overdue boosters plus those falling due inside the horizon."""
    return await immunizations_due(
        db, context, patient_id=patient_id, horizon_days=horizon_days, request=request
    )


@router.post(
    "/immunizations/{immunization_id}/certificate",
    response_model=CertificateOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_certificate(
    immunization_id: UUID,
    payload: CertificateIssueIn,
    context: WriteContext,
    _csrf: Csrf,
    db: Db,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CertificateOut:
    """Issue a signed, verifiable certificate for an administered dose."""
    return await issue_certificate(
        db,
        context,
        immunization_id=immunization_id,
        payload=payload,
        signing_secret=settings.jwt_secret_key.get_secret_value(),
        request=request,
    )


@router.get("/immunizations/{immunization_id}/certificate", response_model=CertificateOut)
async def fetch_certificate(
    immunization_id: UUID,
    context: ReadContext,
    db: Db,
    request: Request,
) -> CertificateOut:
    """Fetch a dose's certificate, including its verification hash."""
    return await get_certificate(db, context, immunization_id=immunization_id, request=request)


@router.get("/patients/{patient_id}/summary", response_model=PatientSummary)
async def get_patient_summary(
    patient_id: UUID,
    context: ReadContext,
    db: Db,
    request: Request,
) -> PatientSummary:
    """Chart-open payload: problems, allergies, latest vitals, immunization status."""
    return await patient_summary(db, context, patient_id=patient_id, request=request)
