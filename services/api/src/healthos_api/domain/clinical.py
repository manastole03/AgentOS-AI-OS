"""Clinical domain: encounters, problems, allergies, observations, immunizations.

This module owns the longitudinal clinical record. Three invariants shape every
function below and are worth stating once:

* Reads are **consent** scoped, never tenant scoped. A vaccination given at one
  hospital has to stay visible at the next one, so
  :func:`~healthos_api.domain.common.consent_scoped_patients` decides visibility
  and ``tenant_id`` is only ever a *write* attribute.
* Every function that hands patient data back to a caller appends a
  ``phi_access_events`` row in the same transaction as the read. Disclosure
  accounting is not reconstructable after the fact, so it is done inline.
* Clinical facts are never corrected in place. A correction inserts a new row
  carrying ``supersedes_id`` and stamps ``superseded_at`` on the row it replaces,
  which keeps the "what did the chart say on the day we treated them" question
  answerable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Request
from pydantic import Field, model_validator
from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AllergyCategory,
    AllergyIntolerance,
    AllergyReaction,
    AllergyType,
    AllergyVerificationStatus,
    AsserterType,
    BiologicalSex,
    CareTeamMember,
    CertificateStatus,
    ClinicalNote,
    ClinicalStatus,
    Condition,
    ConditionCategory,
    Criticality,
    DoctorProfile,
    Encounter,
    EncounterClass,
    EncounterDiagnosis,
    EncounterStatus,
    FamilyHistory,
    GrowthMeasure,
    GrowthMeasurement,
    GrowthReferenceStandard,
    GrowthSource,
    Immunization,
    ImmunizationCertificate,
    ImmunizationStatus,
    LabResult,
    NoteStatus,
    ObservationStatus,
    Organization,
    PatientAllergyStatus,
    PatientIdentifier,
    PatientProfile,
    PhiAccessAction,
    Prescription,
    ProvenanceSource,
    ReactionSeverity,
    VerificationStatus,
    VitalSign,
    VitalSignComponent,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    StatusChange,
    assert_transition,
    conflict,
    consent_scoped_patients,
    forbidden,
    not_found,
    paginate,
    record_phi_access,
    unprocessable,
    write_audit,
)

# --------------------------------------------------------------------------- #
# Constant vocabularies                                                        #
# --------------------------------------------------------------------------- #

#: UCUM units accepted by the ``vital_unit_ucum`` check constraint.
VitalUnit = Literal["mm[Hg]", "kg", "cm", "Cel", "/min", "%", "kg/m2", "[degF]", "L/min"]

#: HL7 ObservationInterpretation codes accepted by the vitals check constraint.
InterpretationCode = Literal["N", "A", "AA", "H", "HH", "L", "LL", "R", "S", "I"]

Comparator = Literal["<", "<=", ">", ">="]
DatePrecision = Literal["day", "month", "year"]
IdentifierType = Literal["MR", "NI", "PPN", "DL", "MB"]

#: ``encounters.status`` state machine. Terminal states only fall through to
#: ``entered-in-error``, which is how a mistakenly opened visit is retracted.
ENCOUNTER_TRANSITIONS: dict[str, set[str]] = {
    EncounterStatus.PLANNED.value: {
        EncounterStatus.ARRIVED.value,
        EncounterStatus.IN_PROGRESS.value,
        EncounterStatus.CANCELLED.value,
        EncounterStatus.ENTERED_IN_ERROR.value,
    },
    EncounterStatus.ARRIVED.value: {
        EncounterStatus.IN_PROGRESS.value,
        EncounterStatus.CANCELLED.value,
        EncounterStatus.ENTERED_IN_ERROR.value,
    },
    EncounterStatus.IN_PROGRESS.value: {
        EncounterStatus.FINISHED.value,
        EncounterStatus.CANCELLED.value,
        EncounterStatus.ENTERED_IN_ERROR.value,
    },
    EncounterStatus.FINISHED.value: {EncounterStatus.ENTERED_IN_ERROR.value},
    EncounterStatus.CANCELLED.value: {EncounterStatus.ENTERED_IN_ERROR.value},
    EncounterStatus.ENTERED_IN_ERROR.value: set(),
}

#: ``clinical_status`` values that put a problem on the active problem list.
ACTIVE_CONDITION_STATUSES = (
    ClinicalStatus.ACTIVE,
    ClinicalStatus.RECURRENCE,
    ClinicalStatus.RELAPSE,
)

#: Growth measures and the ``growth_measurements`` column each one scores.
GROWTH_MEASURE_COLUMNS: dict[GrowthMeasure, str] = {
    GrowthMeasure.HEIGHT_FOR_AGE: "height_cm",
    GrowthMeasure.WEIGHT_FOR_AGE: "weight_kg",
    GrowthMeasure.BMI_FOR_AGE: "bmi",
    GrowthMeasure.HC_FOR_AGE: "head_circumference_cm",
}

#: Which curve's reference row gets stamped onto ``growth_measurements.standard_id``.
GROWTH_STANDARD_PRIORITY = (
    GrowthMeasure.BMI_FOR_AGE,
    GrowthMeasure.WEIGHT_FOR_AGE,
    GrowthMeasure.HEIGHT_FOR_AGE,
    GrowthMeasure.HC_FOR_AGE,
)

#: Mean days per month, used to map ``age_days`` onto month-indexed LMS curves.
DAYS_PER_MONTH = Decimal("30.4375")

DEFAULT_DUE_HORIZON_DAYS = 90

# --------------------------------------------------------------------------- #
# Write payloads                                                               #
# --------------------------------------------------------------------------- #


class ProvenanceIn(DomainModel):
    """Where a clinical assertion came from, and who stands behind it."""

    source: ProvenanceSource = ProvenanceSource.PRACTITIONER
    source_document_id: UUID | None = None
    extraction_confidence: Annotated[Decimal, Field(ge=0, le=1)] | None = None
    asserter_user_id: UUID | None = None
    human_verified: bool = False


class ClinicalRowIn(ProvenanceIn):
    """Provenance plus the amendment fields shared by versioned clinical rows."""

    encounter_id: UUID | None = None
    supersedes_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=500)


class EncounterCreate(ProvenanceIn):
    organization_id: UUID
    department_id: UUID | None = None
    appointment_id: UUID | None = None
    primary_practitioner_user_id: UUID | None = None
    class_code: EncounterClass
    status: EncounterStatus = EncounterStatus.PLANNED
    started_at: datetime
    ended_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    reason_text: str | None = None
    disposition: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def check_period(self) -> EncounterCreate:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        return self


class ConditionCreate(ClinicalRowIn):
    condition_code_system: str = Field(max_length=128)
    condition_code: str = Field(max_length=64)
    condition_display: str = Field(max_length=255)
    condition_concept_id: UUID | None = None
    category: ConditionCategory = ConditionCategory.PROBLEM_LIST_ITEM
    clinical_status: ClinicalStatus = ClinicalStatus.ACTIVE
    verification_status: VerificationStatus = VerificationStatus.CONFIRMED
    severity_code_system: str | None = Field(default=None, max_length=128)
    severity_code: str | None = Field(default=None, max_length=64)
    severity_display: str | None = Field(default=None, max_length=255)
    body_site_code_system: str | None = Field(default=None, max_length=128)
    body_site_code: str | None = Field(default=None, max_length=64)
    body_site_display: str | None = Field(default=None, max_length=255)
    onset_date: date | None = None
    onset_precision: DatePrecision | None = None
    abatement_date: date | None = None
    abatement_precision: DatePrecision | None = None
    note: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> ConditionCreate:
        if self.onset_date is not None and self.onset_precision is None:
            raise ValueError("onset_precision is required when onset_date is given")
        if self.abatement_date is not None and self.abatement_precision is None:
            raise ValueError("abatement_precision is required when abatement_date is given")
        if (
            self.abatement_date is not None
            and self.onset_date is not None
            and self.abatement_date < self.onset_date
        ):
            raise ValueError("abatement_date must not precede onset_date")
        return self


class AllergyReactionCreate(DomainModel):
    manifestation_code_system: str = Field(max_length=128)
    manifestation_code: str = Field(max_length=64)
    manifestation_display: str = Field(max_length=255)
    manifestation_concept_id: UUID | None = None
    severity: ReactionSeverity | None = None
    exposure_route_code_system: str | None = Field(default=None, max_length=128)
    exposure_route_code: str | None = Field(default=None, max_length=64)
    exposure_route_display: str | None = Field(default=None, max_length=255)
    onset_at: datetime | None = None
    note: str | None = None


class AllergyCreate(ClinicalRowIn):
    substance_code_system: str = Field(max_length=128)
    substance_code: str = Field(max_length=64)
    substance_display: str = Field(max_length=255)
    substance_concept_id: UUID | None = None
    substance_is_class: bool = False
    type: AllergyType = AllergyType.ALLERGY
    category: AllergyCategory
    criticality: Criticality = Criticality.UNABLE_TO_ASSESS
    clinical_status: ClinicalStatus = ClinicalStatus.ACTIVE
    verification_status: AllergyVerificationStatus = AllergyVerificationStatus.UNCONFIRMED
    asserter_type: AsserterType = AsserterType.PRACTITIONER
    onset_date: date | None = None
    onset_precision: DatePrecision | None = None
    last_occurrence_at: datetime | None = None
    note: str | None = None
    reactions: list[AllergyReactionCreate] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def check_onset(self) -> AllergyCreate:
        if self.onset_date is not None and self.onset_precision is None:
            raise ValueError("onset_precision is required when onset_date is given")
        return self


class AllergyReviewIn(DomainModel):
    """Attest that the allergy list was looked at, and by whom."""

    no_known_allergies: bool = False
    note: str | None = Field(default=None, max_length=500)


class VitalComponentCreate(DomainModel):
    observation_code_system: str = Field(max_length=128)
    observation_code: str = Field(max_length=64)
    observation_display: str = Field(max_length=255)
    observation_concept_id: UUID | None = None
    value_numeric: Decimal | None = None
    value_string: str | None = Field(default=None, max_length=255)
    unit: VitalUnit | None = None
    interpretation_code: InterpretationCode | None = None
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    sequence: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def check_value(self) -> VitalComponentCreate:
        if self.value_numeric is None and self.value_string is None:
            raise ValueError("a component needs value_numeric or value_string")
        if self.value_numeric is not None and self.unit is None:
            raise ValueError("value_numeric requires a UCUM unit")
        return self


class VitalCreate(ClinicalRowIn):
    """One observation. Panel members (systolic/diastolic) ride in ``components``."""

    observation_code_system: str = Field(max_length=128)
    observation_code: str = Field(max_length=64)
    observation_display: str = Field(max_length=255)
    observation_concept_id: UUID | None = None
    status: ObservationStatus = ObservationStatus.FINAL
    value_numeric: Decimal | None = None
    value_string: str | None = Field(default=None, max_length=255)
    value_code_system: str | None = Field(default=None, max_length=128)
    value_code: str | None = Field(default=None, max_length=64)
    value_display: str | None = Field(default=None, max_length=255)
    value_boolean: bool | None = None
    value_comparator: Comparator | None = None
    unit: VitalUnit | None = None
    data_absent_reason: str | None = Field(default=None, max_length=32)
    interpretation_code: InterpretationCode | None = None
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    reference_range_text: str | None = Field(default=None, max_length=255)
    body_site_code: str | None = Field(default=None, max_length=64)
    method_code: str | None = Field(default=None, max_length=64)
    device: str | None = Field(default=None, max_length=128)
    performer_user_id: UUID | None = None
    note: str | None = None
    effective_at: datetime
    issued_at: datetime | None = None
    components: list[VitalComponentCreate] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def check_single_value(self) -> VitalCreate:
        present = [
            self.value_numeric is not None,
            self.value_string is not None,
            self.value_code is not None,
            self.value_boolean is not None,
            self.data_absent_reason is not None,
        ]
        chosen = sum(present)
        if chosen == 0:
            if not self.components:
                raise ValueError("an observation needs a value or a data_absent_reason")
            # A panel head (e.g. blood pressure) carries no value of its own; the
            # DB requires exactly one value slot, so say so explicitly.
            self.data_absent_reason = "not-applicable"
        elif chosen > 1:
            raise ValueError("exactly one of value_* / data_absent_reason may be set")
        if self.value_numeric is not None and self.unit is None:
            raise ValueError("value_numeric requires a UCUM unit")
        if (
            self.reference_range_low is not None
            and self.reference_range_high is not None
            and self.reference_range_high < self.reference_range_low
        ):
            raise ValueError("reference_range_high must not be below reference_range_low")
        codes = [component.observation_code for component in self.components]
        if len(codes) != len(set(codes)):
            raise ValueError("component observation codes must be unique")
        return self


class GrowthCreate(ClinicalRowIn):
    measured_at: datetime
    age_days: int = Field(ge=0)
    height_cm: Decimal | None = Field(default=None, gt=0)
    weight_kg: Decimal | None = Field(default=None, gt=0)
    head_circumference_cm: Decimal | None = Field(default=None, gt=0)
    bmi: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_any_measure(self) -> GrowthCreate:
        if (
            self.height_cm is None
            and self.weight_kg is None
            and self.head_circumference_cm is None
            and self.bmi is None
        ):
            raise ValueError("at least one measurement is required")
        return self


class ImmunizationCreate(ClinicalRowIn):
    vaccine_code_system: str = Field(max_length=128)
    vaccine_code: str = Field(max_length=64)
    vaccine_display: str = Field(max_length=255)
    vaccine_concept_id: UUID | None = None
    manufacturer_code_system: str | None = Field(default=None, max_length=128)
    manufacturer_code: str | None = Field(default=None, max_length=64)
    manufacturer_display: str | None = Field(default=None, max_length=255)
    status: ImmunizationStatus = ImmunizationStatus.COMPLETED
    status_reason_code: str | None = Field(default=None, max_length=64)
    administered_date: date
    administered_precision: DatePrecision = "day"
    administered_at: datetime | None = None
    lot_number: str | None = Field(default=None, max_length=64)
    expiration_date: date | None = None
    site_code_system: str | None = Field(default=None, max_length=128)
    site_code: str | None = Field(default=None, max_length=64)
    site_display: str | None = Field(default=None, max_length=255)
    route_code_system: str | None = Field(default=None, max_length=128)
    route_code: str | None = Field(default=None, max_length=64)
    route_display: str | None = Field(default=None, max_length=255)
    dose_quantity: Decimal | None = Field(default=None, gt=0)
    dose_unit: str | None = Field(default=None, max_length=16)
    series_name: str | None = Field(default=None, max_length=100)
    series_dose_number: int | None = Field(default=None, ge=1)
    series_doses_expected: int | None = Field(default=None, ge=1)
    funding_source: str | None = Field(default=None, max_length=32)
    administered_by_user_id: UUID | None = None
    organization_id: UUID | None = None
    next_due_at: datetime | None = None
    booster_of_immunization_id: UUID | None = None

    @model_validator(mode="after")
    def check_status(self) -> ImmunizationCreate:
        if self.status is ImmunizationStatus.NOT_DONE and self.status_reason_code is None:
            raise ValueError("status_reason_code is required when status is not-done")
        if self.status is ImmunizationStatus.COMPLETED and (
            self.dose_quantity is None or self.dose_unit is None
        ):
            raise ValueError("dose_quantity and dose_unit are required for a completed dose")
        return self


class CertificateIssueIn(DomainModel):
    issuer_organization_id: UUID | None = None
    document_asset_id: UUID | None = None


# --------------------------------------------------------------------------- #
# Read payloads                                                                #
# --------------------------------------------------------------------------- #


class EncounterOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    primary_practitioner_user_id: UUID | None
    organization_id: UUID
    department_id: UUID | None
    appointment_id: UUID | None
    class_code: EncounterClass
    status: EncounterStatus
    started_at: datetime
    ended_at: datetime | None
    location: str | None
    reason_text: str | None
    disposition: str | None
    source: ProvenanceSource
    recorded_at: datetime


class DiagnosisOut(DomainModel):
    id: UUID
    encounter_id: UUID
    condition_id: UUID | None
    diagnosis_code_system: str
    diagnosis_code: str
    diagnosis_display: str
    rank: int
    is_principal: bool
    present_on_admission: str | None
    recorded_at: datetime


class TimelineEntry(DomainModel):
    """One visit, with everything a clinician scans for before opening it."""

    encounter: EncounterOut
    practitioner_name: str | None
    practitioner_specialty: str | None
    diagnoses: list[DiagnosisOut]
    note_count: int
    prescription_count: int
    result_count: int


class ConditionOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    condition_code_system: str
    condition_code: str
    condition_display: str
    category: ConditionCategory
    clinical_status: ClinicalStatus
    verification_status: VerificationStatus
    severity_code: str | None
    severity_display: str | None
    body_site_code: str | None
    body_site_display: str | None
    onset_date: date | None
    onset_precision: str | None
    abatement_date: date | None
    abatement_precision: str | None
    note: str | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None


class AllergyReactionOut(DomainModel):
    id: UUID
    manifestation_code_system: str
    manifestation_code: str
    manifestation_display: str
    severity: ReactionSeverity | None
    exposure_route_code: str | None
    exposure_route_display: str | None
    onset_at: datetime | None
    note: str | None


class AllergyOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    substance_code_system: str
    substance_code: str
    substance_display: str
    substance_is_class: bool
    type: AllergyType
    category: AllergyCategory
    criticality: Criticality
    clinical_status: ClinicalStatus
    verification_status: AllergyVerificationStatus
    asserter_type: AsserterType
    onset_date: date | None
    last_occurrence_at: datetime | None
    note: str | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None
    reactions: list[AllergyReactionOut]


class AllergyStatusOut(DomainModel):
    patient_user_id: UUID
    no_known_allergies: bool
    last_reviewed_at: datetime | None
    reviewed_by_user_id: UUID | None
    note: str | None
    active_allergy_count: int


class VitalComponentOut(DomainModel):
    id: UUID
    observation_code_system: str
    observation_code: str
    observation_display: str
    value_numeric: Decimal | None
    value_string: str | None
    unit: str | None
    interpretation_code: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    sequence: int


class VitalOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    observation_code_system: str
    observation_code: str
    observation_display: str
    status: ObservationStatus
    value_numeric: Decimal | None
    value_string: str | None
    value_code: str | None
    value_display: str | None
    value_boolean: bool | None
    value_comparator: str | None
    unit: str | None
    data_absent_reason: str | None
    interpretation_code: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    reference_range_text: str | None
    body_site_code: str | None
    method_code: str | None
    device: str | None
    note: str | None
    effective_at: datetime
    issued_at: datetime | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None
    components: list[VitalComponentOut]


class GrowthOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    measured_at: datetime
    age_days: int
    height_cm: Decimal | None
    weight_kg: Decimal | None
    head_circumference_cm: Decimal | None
    bmi: Decimal | None
    height_percentile: Decimal | None
    weight_percentile: Decimal | None
    bmi_percentile: Decimal | None
    height_zscore: Decimal | None
    weight_zscore: Decimal | None
    bmi_zscore: Decimal | None
    standard_id: UUID | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None


class GrowthScore(DomainModel):
    """LMS scoring for one measure at one point, or ``None`` where uncovered."""

    measure: GrowthMeasure
    value: Decimal
    standard_id: UUID
    l: Decimal  # noqa: E741 - the LMS parameter is named L in every growth reference
    m: Decimal
    s: Decimal
    zscore: float
    percentile: float


class GrowthPercentilePoint(DomainModel):
    measurement_id: UUID
    measured_at: datetime
    age_days: int
    scores: dict[GrowthMeasure, GrowthScore | None]


class GrowthPercentileSeries(DomainModel):
    patient_user_id: UUID
    sex: BiologicalSex | None
    source: GrowthSource
    points: list[GrowthPercentilePoint]


class ImmunizationOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    vaccine_code_system: str
    vaccine_code: str
    vaccine_display: str
    manufacturer_display: str | None
    status: ImmunizationStatus
    status_reason_code: str | None
    administered_date: date
    administered_precision: str
    administered_at: datetime | None
    lot_number: str | None
    expiration_date: date | None
    site_display: str | None
    route_display: str | None
    dose_quantity: Decimal | None
    dose_unit: str | None
    series_name: str | None
    series_dose_number: int | None
    series_doses_expected: int | None
    funding_source: str | None
    administered_by_user_id: UUID | None
    organization_id: UUID | None
    next_due_at: datetime | None
    booster_of_immunization_id: UUID | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None


class ImmunizationDueItem(DomainModel):
    immunization_id: UUID
    vaccine_code: str
    vaccine_display: str
    series_name: str | None
    series_dose_number: int | None
    series_doses_expected: int | None
    last_administered_date: date
    next_due_at: datetime
    days_until_due: int


class ImmunizationDueOut(DomainModel):
    as_of: datetime
    horizon_days: int
    overdue: list[ImmunizationDueItem]
    upcoming: list[ImmunizationDueItem]


class CertificateOut(DomainModel):
    id: UUID
    immunization_id: UUID
    patient_user_id: UUID
    certificate_number: str
    issuer_organization_id: UUID
    issued_at: datetime
    verification_hash: str
    qr_payload: str
    signature_algorithm: str
    status: CertificateStatus
    revoked_at: datetime | None
    revocation_reason: str | None
    document_asset_id: UUID | None


class PatientIdentifierOut(DomainModel):
    id: UUID
    system: str
    value: str
    type_code: str
    assigner_organization_id: UUID | None
    period_start: date | None
    period_end: date | None
    is_active: bool


class CareTeamMemberOut(DomainModel):
    id: UUID
    member_user_id: UUID
    member_name: str | None
    member_specialty: str | None
    organization_id: UUID | None
    role_code: str
    is_primary: bool
    period_start: date
    period_end: date | None


class FamilyHistoryOut(DomainModel):
    id: UUID
    relationship_code: str
    condition_code_system: str
    condition_code: str
    condition_display: str
    onset_age_years: int | None
    deceased: bool
    note: str | None
    recorded_at: datetime


class ImmunizationSummary(DomainModel):
    total: int
    completed: int
    not_done: int
    latest_administered_date: date | None
    overdue: int
    upcoming: int
    next_due_at: datetime | None


class PatientSummary(DomainModel):
    """The first screen a clinician opens: one request, no follow-ups."""

    patient_user_id: UUID
    patient_display_id: str
    full_name: str
    date_of_birth: date | None
    sex_at_birth: str | None
    blood_type: str | None
    identifiers: list[PatientIdentifierOut]
    active_conditions: list[ConditionOut]
    active_allergies: list[AllergyOut]
    allergy_status: AllergyStatusOut
    latest_vitals: list[VitalOut]
    immunizations: ImmunizationSummary
    care_team: list[CareTeamMemberOut]
    family_history: list[FamilyHistoryOut]
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Shared internals                                                             #
# --------------------------------------------------------------------------- #


async def _patient_scope(
    db: AsyncSession, context: AuthContext, patient_id: UUID
) -> set[UUID] | None:
    """Resolve the consent allow-set and assert it covers ``patient_id``.

    One round trip instead of ``assert_may_read_patient`` followed by a second
    ``consent_scoped_patients`` for the query filter.
    """
    allowed = await consent_scoped_patients(db, context)
    if allowed is not None and patient_id not in allowed:
        raise forbidden("No consent grant covers this patient")
    return allowed


def _scoped[M](
    query: Select[tuple[M]], model: type[M], allowed: set[UUID] | None
) -> Select[tuple[M]]:
    """Apply the consent allow-set to a single-entity clinical query."""
    if allowed is None:
        return query
    if not allowed:
        return query.where(model.patient_user_id.is_(None)).where(  # type: ignore[attr-defined]
            model.patient_user_id.is_not(None)  # type: ignore[attr-defined]
        )
    return query.where(model.patient_user_id.in_(allowed))  # type: ignore[attr-defined]


async def _load_patient(db: AsyncSession, patient_id: UUID) -> PatientProfile:
    profile = await db.get(PatientProfile, patient_id)
    if profile is None:
        raise not_found("Patient")
    return profile


def _full_name(first: str | None, last: str | None) -> str | None:
    parts = [part for part in (first, last) if part]
    return " ".join(parts) if parts else None


def _supersede(
    previous: Condition | AllergyIntolerance | VitalSign | GrowthMeasurement | Immunization,
    patient_id: UUID,
    now: datetime,
) -> int:
    """Retire the row being corrected and return the new row's version number."""
    if previous.patient_user_id != patient_id:
        raise not_found("Superseded record")
    if previous.superseded_at is not None:
        raise conflict("That record has already been superseded")
    previous.superseded_at = now
    return previous.version + 1


def _verified_by(
    payload: ProvenanceIn, context: AuthContext, now: datetime
) -> tuple[UUID, datetime] | tuple[None, None]:
    if payload.human_verified:
        return context.user.id, now
    return None, None


def _guard_ai_provenance(payload: ProvenanceIn, *, confirmed: bool) -> None:
    """Mirror the ``*_ai_human_verified`` check constraints with a 422, not a 500."""
    if payload.source is ProvenanceSource.AI_EXTRACTED and confirmed and not payload.human_verified:
        raise unprocessable(
            "An AI-extracted record cannot be recorded as confirmed without human verification"
        )


def _biological_sex(profile: PatientProfile) -> BiologicalSex | None:
    raw = (profile.sex_at_birth or "").strip().lower()
    if raw in {"male", "m"}:
        return BiologicalSex.MALE
    if raw in {"female", "f"}:
        return BiologicalSex.FEMALE
    return None


def _reaction_out(row: AllergyReaction) -> AllergyReactionOut:
    return AllergyReactionOut.model_validate(row)


async def _reactions_for(
    db: AsyncSession, allergy_ids: list[UUID]
) -> dict[UUID, list[AllergyReactionOut]]:
    grouped: dict[UUID, list[AllergyReactionOut]] = {key: [] for key in allergy_ids}
    if not allergy_ids:
        return grouped
    rows = await db.scalars(
        select(AllergyReaction)
        .where(AllergyReaction.allergy_intolerance_id.in_(allergy_ids))
        .order_by(AllergyReaction.onset_at.desc().nullslast(), AllergyReaction.id)
    )
    for row in rows:
        grouped.setdefault(row.allergy_intolerance_id, []).append(_reaction_out(row))
    return grouped


def _allergy_out(row: AllergyIntolerance, reactions: list[AllergyReactionOut]) -> AllergyOut:
    return AllergyOut(
        id=row.id,
        patient_user_id=row.patient_user_id,
        encounter_id=row.encounter_id,
        substance_code_system=row.substance_code_system,
        substance_code=row.substance_code,
        substance_display=row.substance_display,
        substance_is_class=row.substance_is_class,
        type=row.type,
        category=row.category,
        criticality=row.criticality,
        clinical_status=row.clinical_status,
        verification_status=row.verification_status,
        asserter_type=row.asserter_type,
        onset_date=row.onset_date,
        last_occurrence_at=row.last_occurrence_at,
        note=row.note,
        source=row.source,
        recorded_at=row.recorded_at,
        version=row.version,
        supersedes_id=row.supersedes_id,
        superseded_at=row.superseded_at,
        reactions=reactions,
    )


async def _components_for(
    db: AsyncSession, vital_ids: list[UUID]
) -> dict[UUID, list[VitalComponentOut]]:
    grouped: dict[UUID, list[VitalComponentOut]] = {key: [] for key in vital_ids}
    if not vital_ids:
        return grouped
    rows = await db.scalars(
        select(VitalSignComponent)
        .where(VitalSignComponent.vital_sign_id.in_(vital_ids))
        .order_by(VitalSignComponent.vital_sign_id, VitalSignComponent.sequence)
    )
    for row in rows:
        grouped.setdefault(row.vital_sign_id, []).append(VitalComponentOut.model_validate(row))
    return grouped


def _vital_out(row: VitalSign, components: list[VitalComponentOut]) -> VitalOut:
    return VitalOut(
        id=row.id,
        patient_user_id=row.patient_user_id,
        encounter_id=row.encounter_id,
        observation_code_system=row.observation_code_system,
        observation_code=row.observation_code,
        observation_display=row.observation_display,
        status=row.status,
        value_numeric=row.value_numeric,
        value_string=row.value_string,
        value_code=row.value_code,
        value_display=row.value_display,
        value_boolean=row.value_boolean,
        value_comparator=row.value_comparator,
        unit=row.unit,
        data_absent_reason=row.data_absent_reason,
        interpretation_code=row.interpretation_code,
        reference_range_low=row.reference_range_low,
        reference_range_high=row.reference_range_high,
        reference_range_text=row.reference_range_text,
        body_site_code=row.body_site_code,
        method_code=row.method_code,
        device=row.device,
        note=row.note,
        effective_at=row.effective_at,
        issued_at=row.issued_at,
        source=row.source,
        recorded_at=row.recorded_at,
        version=row.version,
        supersedes_id=row.supersedes_id,
        superseded_at=row.superseded_at,
        components=components,
    )


# --------------------------------------------------------------------------- #
# Timeline                                                                     #
# --------------------------------------------------------------------------- #


async def patient_timeline(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    request: Request | None = None,
) -> Page[TimelineEntry]:
    """Encounters newest-first with diagnoses, clinician, and child-record counts."""
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    practitioner = aliased(DoctorProfile)
    note_count = (
        select(func.count())
        .select_from(ClinicalNote)
        .where(
            ClinicalNote.encounter_id == Encounter.id,
            ClinicalNote.superseded_at.is_(None),
            ClinicalNote.status != NoteStatus.ENTERED_IN_ERROR,
        )
        .scalar_subquery()
    )
    prescription_count = (
        select(func.count())
        .select_from(Prescription)
        .where(
            Prescription.encounter_id == Encounter.id,
            Prescription.superseded_at.is_(None),
        )
        .scalar_subquery()
    )
    result_count = (
        select(func.count())
        .select_from(LabResult)
        .where(
            LabResult.encounter_id == Encounter.id,
            LabResult.superseded_at.is_(None),
        )
        .scalar_subquery()
    )

    stmt = (
        select(
            Encounter,
            practitioner.first_name,
            practitioner.last_name,
            practitioner.specialty,
            note_count,
            prescription_count,
            result_count,
        )
        .outerjoin(practitioner, practitioner.user_id == Encounter.primary_practitioner_user_id)
        .where(
            Encounter.patient_user_id == patient_id,
            Encounter.status != EncounterStatus.ENTERED_IN_ERROR,
        )
        .order_by(Encounter.started_at.desc(), Encounter.id.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = (await db.execute(stmt)).tuples().all()

    encounter_ids = [row[0].id for row in rows[: page.limit]]
    diagnoses: dict[UUID, list[DiagnosisOut]] = {key: [] for key in encounter_ids}
    if encounter_ids:
        diagnosis_rows = await db.scalars(
            select(EncounterDiagnosis)
            .where(EncounterDiagnosis.encounter_id.in_(encounter_ids))
            .order_by(
                EncounterDiagnosis.encounter_id,
                EncounterDiagnosis.is_principal.desc(),
                EncounterDiagnosis.rank,
            )
        )
        for diagnosis in diagnosis_rows:
            diagnoses.setdefault(diagnosis.encounter_id, []).append(
                DiagnosisOut.model_validate(diagnosis)
            )

    entries = [
        TimelineEntry(
            encounter=EncounterOut.model_validate(encounter),
            practitioner_name=_full_name(first_name, last_name),
            practitioner_specialty=specialty,
            diagnoses=diagnoses.get(encounter.id, []),
            note_count=notes,
            prescription_count=prescriptions,
            result_count=results,
        )
        for encounter, first_name, last_name, specialty, notes, prescriptions, results in rows
    ]

    total = await db.scalar(
        select(func.count())
        .select_from(Encounter)
        .where(
            Encounter.patient_user_id == patient_id,
            Encounter.status != EncounterStatus.ENTERED_IN_ERROR,
        )
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="encounter_timeline",
        action=PhiAccessAction.SEARCH,
        result_count=len(encounter_ids),
        request=request,
    )
    await db.commit()
    return paginate(entries, page, total=total)


# --------------------------------------------------------------------------- #
# Encounters                                                                   #
# --------------------------------------------------------------------------- #


async def list_encounters(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    status_filter: EncounterStatus | None = None,
    class_code: EncounterClass | None = None,
    since: datetime | None = None,
    request: Request | None = None,
) -> Page[EncounterOut]:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(Encounter).where(Encounter.patient_user_id == patient_id)
    stmt = _scoped(stmt, Encounter, allowed)
    if status_filter is not None:
        stmt = stmt.where(Encounter.status == status_filter)
    if class_code is not None:
        stmt = stmt.where(Encounter.class_code == class_code)
    if since is not None:
        stmt = stmt.where(Encounter.started_at >= since)
    stmt = (
        stmt.order_by(Encounter.started_at.desc(), Encounter.id.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    items = [EncounterOut.model_validate(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="encounter",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_encounter(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: EncounterCreate,
    request: Request | None = None,
) -> EncounterOut:
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    now = datetime.now(UTC)
    if await db.get(Organization, payload.organization_id) is None:
        raise unprocessable("organization_id does not reference a known organization")
    if payload.status not in {EncounterStatus.PLANNED, EncounterStatus.ARRIVED}:
        raise unprocessable("A new encounter opens as 'planned' or 'arrived'")

    verified_by, verified_at = _verified_by(payload, context, now)
    encounter = Encounter(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        primary_practitioner_user_id=payload.primary_practitioner_user_id,
        organization_id=payload.organization_id,
        department_id=payload.department_id,
        appointment_id=payload.appointment_id,
        class_code=payload.class_code,
        status=payload.status,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        location=payload.location,
        reason_text=payload.reason_text,
        disposition=payload.disposition,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
    )
    db.add(encounter)
    await db.flush()

    await write_audit(
        db,
        context,
        event_type="clinical.encounter.created",
        subject_user_id=patient_id,
        resource_id=encounter.id,
        event_data={"class_code": encounter.class_code.value, "status": encounter.status.value},
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="encounter",
        resource_id=encounter.id,
        request=request,
    )
    await db.commit()
    await db.refresh(encounter)
    return EncounterOut.model_validate(encounter)


async def update_encounter_status(
    db: AsyncSession,
    context: AuthContext,
    *,
    encounter_id: UUID,
    payload: StatusChange,
    request: Request | None = None,
) -> EncounterOut:
    encounter = await db.get(Encounter, encounter_id)
    if encounter is None:
        raise not_found("Encounter")
    await _patient_scope(db, context, encounter.patient_user_id)

    try:
        target = EncounterStatus(payload.status)
    except ValueError as exc:
        raise unprocessable(f"'{payload.status}' is not an encounter status") from exc

    assert_transition(encounter.status.value, target.value, ENCOUNTER_TRANSITIONS)
    previous = encounter.status
    now = datetime.now(UTC)
    encounter.status = target
    if target is EncounterStatus.FINISHED and encounter.ended_at is None:
        encounter.ended_at = now
    if target is EncounterStatus.CANCELLED and payload.reason:
        encounter.disposition = payload.reason[:64]

    await write_audit(
        db,
        context,
        event_type="clinical.encounter.status_changed",
        subject_user_id=encounter.patient_user_id,
        resource_id=encounter.id,
        event_data={"from": previous.value, "to": target.value, "reason": payload.reason},
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=encounter.patient_user_id,
        resource_type="encounter",
        resource_id=encounter.id,
        request=request,
    )
    await db.commit()
    await db.refresh(encounter)
    return EncounterOut.model_validate(encounter)


# --------------------------------------------------------------------------- #
# Conditions                                                                   #
# --------------------------------------------------------------------------- #


async def list_conditions(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    clinical_status: ClinicalStatus | None = None,
    include_superseded: bool = False,
    request: Request | None = None,
) -> Page[ConditionOut]:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(Condition).where(
        Condition.patient_user_id == patient_id,
        Condition.verification_status != VerificationStatus.ENTERED_IN_ERROR,
    )
    stmt = _scoped(stmt, Condition, allowed)
    if not include_superseded:
        stmt = stmt.where(Condition.superseded_at.is_(None))
    if clinical_status is not None:
        stmt = stmt.where(Condition.clinical_status == clinical_status)
    stmt = (
        stmt.order_by(Condition.recorded_at.desc(), Condition.id.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    items = [ConditionOut.model_validate(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="condition",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_condition(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: ConditionCreate,
    request: Request | None = None,
) -> ConditionOut:
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)
    _guard_ai_provenance(
        payload, confirmed=payload.verification_status is VerificationStatus.CONFIRMED
    )

    now = datetime.now(UTC)
    version = 1
    if payload.supersedes_id is not None:
        previous = await db.get(Condition, payload.supersedes_id)
        if previous is None:
            raise not_found("Superseded condition")
        version = _supersede(previous, patient_id, now)

    verified_by, verified_at = _verified_by(payload, context, now)
    condition = Condition(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        encounter_id=payload.encounter_id,
        condition_code_system=payload.condition_code_system,
        condition_code=payload.condition_code,
        condition_display=payload.condition_display,
        condition_concept_id=payload.condition_concept_id,
        category=payload.category,
        clinical_status=payload.clinical_status,
        verification_status=payload.verification_status,
        severity_code_system=payload.severity_code_system,
        severity_code=payload.severity_code,
        severity_display=payload.severity_display,
        body_site_code_system=payload.body_site_code_system,
        body_site_code=payload.body_site_code,
        body_site_display=payload.body_site_display,
        onset_date=payload.onset_date,
        onset_precision=payload.onset_precision,
        abatement_date=payload.abatement_date,
        abatement_precision=payload.abatement_precision,
        note=payload.note,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
        version=version,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(condition)
    await db.flush()

    await write_audit(
        db,
        context,
        event_type="clinical.condition.recorded",
        subject_user_id=patient_id,
        resource_id=condition.id,
        event_data={
            "code": condition.condition_code,
            "clinical_status": condition.clinical_status.value,
            "version": version,
            "supersedes_id": str(payload.supersedes_id) if payload.supersedes_id else None,
        },
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="condition",
        resource_id=condition.id,
        request=request,
    )
    await db.commit()
    await db.refresh(condition)
    return ConditionOut.model_validate(condition)


# --------------------------------------------------------------------------- #
# Allergies                                                                    #
# --------------------------------------------------------------------------- #


def _criticality_rank() -> ColumnElement[int]:
    return case(
        (AllergyIntolerance.criticality == Criticality.HIGH, 0),
        (AllergyIntolerance.criticality == Criticality.LOW, 1),
        else_=2,
    )


async def list_allergies(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    active_only: bool = True,
    request: Request | None = None,
) -> Page[AllergyOut]:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(AllergyIntolerance).where(
        AllergyIntolerance.patient_user_id == patient_id,
        AllergyIntolerance.verification_status != AllergyVerificationStatus.ENTERED_IN_ERROR,
        AllergyIntolerance.superseded_at.is_(None),
    )
    stmt = _scoped(stmt, AllergyIntolerance, allowed)
    if active_only:
        stmt = stmt.where(AllergyIntolerance.clinical_status == ClinicalStatus.ACTIVE)
    stmt = (
        stmt.order_by(_criticality_rank(), AllergyIntolerance.recorded_at.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    reactions = await _reactions_for(db, [row.id for row in rows])
    items = [_allergy_out(row, reactions.get(row.id, [])) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="allergy_intolerance",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_allergy(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: AllergyCreate,
    request: Request | None = None,
) -> AllergyOut:
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)
    _guard_ai_provenance(
        payload, confirmed=payload.verification_status is AllergyVerificationStatus.CONFIRMED
    )

    now = datetime.now(UTC)
    version = 1
    if payload.supersedes_id is not None:
        previous = await db.get(AllergyIntolerance, payload.supersedes_id)
        if previous is None:
            raise not_found("Superseded allergy")
        version = _supersede(previous, patient_id, now)

    verified_by, verified_at = _verified_by(payload, context, now)
    allergy = AllergyIntolerance(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        encounter_id=payload.encounter_id,
        substance_code_system=payload.substance_code_system,
        substance_code=payload.substance_code,
        substance_display=payload.substance_display,
        substance_concept_id=payload.substance_concept_id,
        substance_is_class=payload.substance_is_class,
        type=payload.type,
        category=payload.category,
        criticality=payload.criticality,
        clinical_status=payload.clinical_status,
        verification_status=payload.verification_status,
        asserter_type=payload.asserter_type,
        onset_date=payload.onset_date,
        onset_precision=payload.onset_precision,
        last_occurrence_at=payload.last_occurrence_at,
        note=payload.note,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
        version=version,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(allergy)
    await db.flush()

    reactions = [
        AllergyReaction(
            allergy_intolerance_id=allergy.id,
            manifestation_code_system=item.manifestation_code_system,
            manifestation_code=item.manifestation_code,
            manifestation_display=item.manifestation_display,
            manifestation_concept_id=item.manifestation_concept_id,
            severity=item.severity,
            exposure_route_code_system=item.exposure_route_code_system,
            exposure_route_code=item.exposure_route_code,
            exposure_route_display=item.exposure_route_display,
            onset_at=item.onset_at,
            note=item.note,
        )
        for item in payload.reactions
    ]
    for reaction in reactions:
        db.add(reaction)

    # Recording a real allergy contradicts a standing "no known allergies" flag.
    status_row = await db.get(PatientAllergyStatus, patient_id)
    if (
        status_row is not None
        and status_row.no_known_allergies
        and payload.clinical_status is ClinicalStatus.ACTIVE
    ):
        status_row.no_known_allergies = False
        status_row.last_reviewed_at = now
        status_row.reviewed_by_user_id = context.user.id

    await db.flush()
    await write_audit(
        db,
        context,
        event_type="clinical.allergy.recorded",
        subject_user_id=patient_id,
        resource_id=allergy.id,
        event_data={
            "substance_code": allergy.substance_code,
            "criticality": allergy.criticality.value,
            "reaction_count": len(reactions),
            "version": version,
        },
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="allergy_intolerance",
        resource_id=allergy.id,
        request=request,
    )
    await db.commit()
    await db.refresh(allergy)
    stored = await _reactions_for(db, [allergy.id])
    return _allergy_out(allergy, stored.get(allergy.id, []))


async def _active_allergy_count(db: AsyncSession, patient_id: UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(AllergyIntolerance)
        .where(
            AllergyIntolerance.patient_user_id == patient_id,
            AllergyIntolerance.clinical_status == ClinicalStatus.ACTIVE,
            AllergyIntolerance.superseded_at.is_(None),
            AllergyIntolerance.verification_status != AllergyVerificationStatus.ENTERED_IN_ERROR,
        )
    )
    return count or 0


async def review_allergies(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: AllergyReviewIn,
    request: Request | None = None,
) -> AllergyStatusOut:
    """Stamp ``patient_allergy_status`` as reviewed by the current clinician."""
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    active = await _active_allergy_count(db, patient_id)
    if payload.no_known_allergies and active:
        raise conflict("Cannot assert 'no known allergies' while active allergies are recorded")

    now = datetime.now(UTC)
    status_row = await db.get(PatientAllergyStatus, patient_id)
    if status_row is None:
        status_row = PatientAllergyStatus(
            user_id=patient_id,
            tenant_id=context.tenant_id,
            no_known_allergies=payload.no_known_allergies,
            last_reviewed_at=now,
            reviewed_by_user_id=context.user.id,
            note=payload.note,
        )
        db.add(status_row)
    else:
        status_row.no_known_allergies = payload.no_known_allergies
        status_row.last_reviewed_at = now
        status_row.reviewed_by_user_id = context.user.id
        status_row.note = payload.note

    await write_audit(
        db,
        context,
        event_type="clinical.allergy.reviewed",
        subject_user_id=patient_id,
        resource_id=patient_id,
        event_data={"no_known_allergies": payload.no_known_allergies, "active_count": active},
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="patient_allergy_status",
        resource_id=patient_id,
        request=request,
    )
    await db.commit()
    return AllergyStatusOut(
        patient_user_id=patient_id,
        no_known_allergies=status_row.no_known_allergies,
        last_reviewed_at=status_row.last_reviewed_at,
        reviewed_by_user_id=status_row.reviewed_by_user_id,
        note=status_row.note,
        active_allergy_count=active,
    )


# --------------------------------------------------------------------------- #
# Vital signs                                                                  #
# --------------------------------------------------------------------------- #


async def list_vitals(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    code: str | None = None,
    since: datetime | None = None,
    request: Request | None = None,
) -> Page[VitalOut]:
    """Trend query: ascending by ``effective_at`` so a chart can plot it directly."""
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(VitalSign).where(
        VitalSign.patient_user_id == patient_id,
        VitalSign.superseded_at.is_(None),
        VitalSign.status != ObservationStatus.ENTERED_IN_ERROR,
    )
    stmt = _scoped(stmt, VitalSign, allowed)
    if code is not None:
        stmt = stmt.where(VitalSign.observation_code == code)
    if since is not None:
        stmt = stmt.where(VitalSign.effective_at >= since)
    stmt = (
        stmt.order_by(VitalSign.effective_at.asc(), VitalSign.id.asc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    components = await _components_for(db, [row.id for row in rows])
    items = [_vital_out(row, components.get(row.id, [])) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="vital_sign",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_vital(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: VitalCreate,
    request: Request | None = None,
) -> VitalOut:
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    now = datetime.now(UTC)
    version = 1
    if payload.supersedes_id is not None:
        previous = await db.get(VitalSign, payload.supersedes_id)
        if previous is None:
            raise not_found("Superseded observation")
        version = _supersede(previous, patient_id, now)

    verified_by, verified_at = _verified_by(payload, context, now)
    vital = VitalSign(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        encounter_id=payload.encounter_id,
        observation_code_system=payload.observation_code_system,
        observation_code=payload.observation_code,
        observation_display=payload.observation_display,
        observation_concept_id=payload.observation_concept_id,
        status=payload.status,
        value_numeric=payload.value_numeric,
        value_string=payload.value_string,
        value_code_system=payload.value_code_system,
        value_code=payload.value_code,
        value_display=payload.value_display,
        value_boolean=payload.value_boolean,
        value_comparator=payload.value_comparator,
        unit=payload.unit,
        data_absent_reason=payload.data_absent_reason,
        interpretation_code=payload.interpretation_code,
        reference_range_low=payload.reference_range_low,
        reference_range_high=payload.reference_range_high,
        reference_range_text=payload.reference_range_text,
        body_site_code=payload.body_site_code,
        method_code=payload.method_code,
        device=payload.device,
        performer_user_id=payload.performer_user_id,
        note=payload.note,
        effective_at=payload.effective_at,
        issued_at=payload.issued_at,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
        version=version,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(vital)
    await db.flush()

    for item in payload.components:
        db.add(
            VitalSignComponent(
                vital_sign_id=vital.id,
                observation_code_system=item.observation_code_system,
                observation_code=item.observation_code,
                observation_display=item.observation_display,
                observation_concept_id=item.observation_concept_id,
                value_numeric=item.value_numeric,
                value_string=item.value_string,
                unit=item.unit,
                interpretation_code=item.interpretation_code,
                reference_range_low=item.reference_range_low,
                reference_range_high=item.reference_range_high,
                sequence=item.sequence,
            )
        )

    await db.flush()
    await write_audit(
        db,
        context,
        event_type="clinical.vital.recorded",
        subject_user_id=patient_id,
        resource_id=vital.id,
        event_data={
            "observation_code": vital.observation_code,
            "component_count": len(payload.components),
            "version": version,
        },
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="vital_sign",
        resource_id=vital.id,
        request=request,
    )
    await db.commit()
    await db.refresh(vital)
    components = await _components_for(db, [vital.id])
    return _vital_out(vital, components.get(vital.id, []))


# --------------------------------------------------------------------------- #
# Growth                                                                       #
# --------------------------------------------------------------------------- #


def _lms_zscore(
    value: Decimal, l_value: Decimal, m_value: Decimal, s_value: Decimal
) -> float | None:
    """z = ((X/M)^L - 1) / (L*S), or ln(X/M)/S when L is zero."""
    x = float(value)
    lam = float(l_value)
    median = float(m_value)
    sigma = float(s_value)
    if x <= 0 or median <= 0 or sigma == 0:
        return None
    ratio = x / median
    if lam == 0:
        return math.log(ratio) / sigma
    try:
        return float(ratio**lam - 1.0) / (lam * sigma)
    except (OverflowError, ValueError):
        return None


def _zscore_to_percentile(z: float) -> float:
    """Standard-normal CDF, expressed as a percentile."""
    return round(100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))), 4)


async def _lms_by_measurement(
    db: AsyncSession,
    *,
    measurement_ids: list[UUID],
    sex: BiologicalSex,
    source: GrowthSource,
) -> dict[UUID, dict[GrowthMeasure, tuple[UUID, Decimal, Decimal, Decimal]]]:
    """Join each measurement onto the LMS row covering its age and sex.

    Reference curves are published either day-indexed or month-indexed; both are
    matched and the day-indexed row wins when the two overlap. Measurements with
    no covering row simply do not appear in the result, which is how the caller
    knows to emit ``null``.
    """
    if not measurement_ids:
        return {}

    measurement = GrowthMeasurement
    standard = GrowthReferenceStandard
    age_months = func.floor(measurement.age_days / DAYS_PER_MONTH)
    stmt = (
        select(
            measurement.id,
            standard.measure,
            standard.id,
            standard.l,
            standard.m,
            standard.s,
        )
        .join(
            standard,
            and_(
                standard.sex == sex,
                standard.source == source,
                standard.measure.in_(list(GROWTH_MEASURE_COLUMNS)),
                or_(
                    and_(
                        standard.age_unit == "day",
                        standard.age_value == measurement.age_days,
                    ),
                    and_(standard.age_unit == "month", standard.age_value == age_months),
                ),
            ),
        )
        .where(measurement.id.in_(measurement_ids))
        .distinct(measurement.id, standard.measure)
        .order_by(
            measurement.id,
            standard.measure,
            case((standard.age_unit == "day", 0), else_=1),
        )
    )
    rows = (await db.execute(stmt)).tuples().all()

    curves: dict[UUID, dict[GrowthMeasure, tuple[UUID, Decimal, Decimal, Decimal]]] = {}
    for measurement_id, measure, standard_id, l_value, m_value, s_value in rows:
        curves.setdefault(measurement_id, {})[measure] = (standard_id, l_value, m_value, s_value)
    return curves


def _measure_value(row: GrowthMeasurement, measure: GrowthMeasure) -> Decimal | None:
    value = getattr(row, GROWTH_MEASURE_COLUMNS[measure])
    return value if isinstance(value, Decimal) else None


async def list_growth(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    since: datetime | None = None,
    request: Request | None = None,
) -> Page[GrowthOut]:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(GrowthMeasurement).where(
        GrowthMeasurement.patient_user_id == patient_id,
        GrowthMeasurement.superseded_at.is_(None),
    )
    stmt = _scoped(stmt, GrowthMeasurement, allowed)
    if since is not None:
        stmt = stmt.where(GrowthMeasurement.measured_at >= since)
    stmt = (
        stmt.order_by(GrowthMeasurement.measured_at.asc(), GrowthMeasurement.id.asc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    items = [GrowthOut.model_validate(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="growth_measurement",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_growth(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: GrowthCreate,
    source_standard: GrowthSource = GrowthSource.WHO,
    request: Request | None = None,
) -> GrowthOut:
    """Store a growth point and score it against the reference curves at once."""
    await _patient_scope(db, context, patient_id)
    profile = await _load_patient(db, patient_id)

    now = datetime.now(UTC)
    version = 1
    if payload.supersedes_id is not None:
        previous = await db.get(GrowthMeasurement, payload.supersedes_id)
        if previous is None:
            raise not_found("Superseded growth measurement")
        version = _supersede(previous, patient_id, now)

    bmi = payload.bmi
    if bmi is None and payload.height_cm is not None and payload.weight_kg is not None:
        metres = payload.height_cm / Decimal(100)
        bmi = (payload.weight_kg / (metres * metres)).quantize(Decimal("0.01"))

    verified_by, verified_at = _verified_by(payload, context, now)
    measurement = GrowthMeasurement(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        encounter_id=payload.encounter_id,
        measured_at=payload.measured_at,
        age_days=payload.age_days,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        head_circumference_cm=payload.head_circumference_cm,
        bmi=bmi,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
        version=version,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(measurement)
    await db.flush()

    sex = _biological_sex(profile)
    if sex is not None:
        curves = await _lms_by_measurement(
            db, measurement_ids=[measurement.id], sex=sex, source=source_standard
        )
        _apply_scores(measurement, curves.get(measurement.id, {}))

    await write_audit(
        db,
        context,
        event_type="clinical.growth.recorded",
        subject_user_id=patient_id,
        resource_id=measurement.id,
        event_data={"age_days": measurement.age_days, "version": version},
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="growth_measurement",
        resource_id=measurement.id,
        request=request,
    )
    await db.commit()
    await db.refresh(measurement)
    return GrowthOut.model_validate(measurement)


def _apply_scores(
    measurement: GrowthMeasurement,
    curves: dict[GrowthMeasure, tuple[UUID, Decimal, Decimal, Decimal]],
) -> None:
    """Write the derived percentile/z-score columns of a freshly inserted point."""
    targets: dict[GrowthMeasure, tuple[str, str]] = {
        GrowthMeasure.HEIGHT_FOR_AGE: ("height_percentile", "height_zscore"),
        GrowthMeasure.WEIGHT_FOR_AGE: ("weight_percentile", "weight_zscore"),
        GrowthMeasure.BMI_FOR_AGE: ("bmi_percentile", "bmi_zscore"),
    }
    for measure, (percentile_field, zscore_field) in targets.items():
        curve = curves.get(measure)
        value = _measure_value(measurement, measure)
        if curve is None or value is None:
            continue
        _standard_id, l_value, m_value, s_value = curve
        z = _lms_zscore(value, l_value, m_value, s_value)
        if z is None:
            continue
        setattr(measurement, zscore_field, Decimal(str(round(z, 3))))
        percentile = _zscore_to_percentile(z)
        setattr(measurement, percentile_field, Decimal(str(round(percentile, 2))))

    for measure in GROWTH_STANDARD_PRIORITY:
        curve = curves.get(measure)
        if curve is not None:
            measurement.standard_id = curve[0]
            break


async def growth_percentiles(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    source_standard: GrowthSource = GrowthSource.WHO,
    since: datetime | None = None,
    request: Request | None = None,
) -> GrowthPercentileSeries:
    """LMS percentile and z-score per measurement, ascending for charting."""
    allowed = await _patient_scope(db, context, patient_id)
    profile = await _load_patient(db, patient_id)

    stmt = select(GrowthMeasurement).where(
        GrowthMeasurement.patient_user_id == patient_id,
        GrowthMeasurement.superseded_at.is_(None),
    )
    stmt = _scoped(stmt, GrowthMeasurement, allowed)
    if since is not None:
        stmt = stmt.where(GrowthMeasurement.measured_at >= since)
    stmt = (
        stmt.order_by(GrowthMeasurement.measured_at.asc(), GrowthMeasurement.id.asc())
        .limit(page.limit)
        .offset(page.offset)
    )
    measurements = list((await db.scalars(stmt)).all())

    sex = _biological_sex(profile)
    curves: dict[UUID, dict[GrowthMeasure, tuple[UUID, Decimal, Decimal, Decimal]]] = {}
    if sex is not None:
        curves = await _lms_by_measurement(
            db,
            measurement_ids=[row.id for row in measurements],
            sex=sex,
            source=source_standard,
        )

    points: list[GrowthPercentilePoint] = []
    for row in measurements:
        scores: dict[GrowthMeasure, GrowthScore | None] = {}
        row_curves = curves.get(row.id, {})
        for measure in GROWTH_MEASURE_COLUMNS:
            value = _measure_value(row, measure)
            curve = row_curves.get(measure)
            if value is None or curve is None:
                scores[measure] = None
                continue
            standard_id, l_value, m_value, s_value = curve
            z = _lms_zscore(value, l_value, m_value, s_value)
            if z is None:
                scores[measure] = None
                continue
            scores[measure] = GrowthScore(
                measure=measure,
                value=value,
                standard_id=standard_id,
                l=l_value,
                m=m_value,
                s=s_value,
                zscore=round(z, 4),
                percentile=_zscore_to_percentile(z),
            )
        points.append(
            GrowthPercentilePoint(
                measurement_id=row.id,
                measured_at=row.measured_at,
                age_days=row.age_days,
                scores=scores,
            )
        )

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="growth_percentile",
        action=PhiAccessAction.SEARCH,
        result_count=len(points),
        request=request,
    )
    await db.commit()
    return GrowthPercentileSeries(
        patient_user_id=patient_id,
        sex=sex,
        source=source_standard,
        points=points,
    )


# --------------------------------------------------------------------------- #
# Immunizations                                                                #
# --------------------------------------------------------------------------- #


async def list_immunizations(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    page: Pagination,
    vaccine_code: str | None = None,
    request: Request | None = None,
) -> Page[ImmunizationOut]:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    stmt = select(Immunization).where(
        Immunization.patient_user_id == patient_id,
        Immunization.superseded_at.is_(None),
        Immunization.status != ImmunizationStatus.ENTERED_IN_ERROR,
    )
    stmt = _scoped(stmt, Immunization, allowed)
    if vaccine_code is not None:
        stmt = stmt.where(Immunization.vaccine_code == vaccine_code)
    stmt = (
        stmt.order_by(Immunization.administered_date.desc(), Immunization.id.desc())
        .limit(page.limit + 1)
        .offset(page.offset)
    )
    rows = list((await db.scalars(stmt)).all())
    items = [ImmunizationOut.model_validate(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="immunization",
        action=PhiAccessAction.SEARCH,
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_immunization(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    payload: ImmunizationCreate,
    request: Request | None = None,
) -> ImmunizationOut:
    await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    now = datetime.now(UTC)
    version = 1
    if payload.supersedes_id is not None:
        previous = await db.get(Immunization, payload.supersedes_id)
        if previous is None:
            raise not_found("Superseded immunization")
        version = _supersede(previous, patient_id, now)

    if payload.booster_of_immunization_id is not None:
        parent = await db.get(Immunization, payload.booster_of_immunization_id)
        if parent is None or parent.patient_user_id != patient_id:
            raise unprocessable("booster_of_immunization_id must reference a dose for this patient")

    verified_by, verified_at = _verified_by(payload, context, now)
    immunization = Immunization(
        tenant_id=context.tenant_id,
        patient_user_id=patient_id,
        encounter_id=payload.encounter_id,
        vaccine_code_system=payload.vaccine_code_system,
        vaccine_code=payload.vaccine_code,
        vaccine_display=payload.vaccine_display,
        vaccine_concept_id=payload.vaccine_concept_id,
        manufacturer_code_system=payload.manufacturer_code_system,
        manufacturer_code=payload.manufacturer_code,
        manufacturer_display=payload.manufacturer_display,
        status=payload.status,
        status_reason_code=payload.status_reason_code,
        administered_date=payload.administered_date,
        administered_precision=payload.administered_precision,
        administered_at=payload.administered_at,
        lot_number=payload.lot_number,
        expiration_date=payload.expiration_date,
        site_code_system=payload.site_code_system,
        site_code=payload.site_code,
        site_display=payload.site_display,
        route_code_system=payload.route_code_system,
        route_code=payload.route_code,
        route_display=payload.route_display,
        dose_quantity=payload.dose_quantity,
        dose_unit=payload.dose_unit,
        series_name=payload.series_name,
        series_dose_number=payload.series_dose_number,
        series_doses_expected=payload.series_doses_expected,
        funding_source=payload.funding_source,
        administered_by_user_id=payload.administered_by_user_id,
        organization_id=payload.organization_id,
        next_due_at=payload.next_due_at,
        booster_of_immunization_id=payload.booster_of_immunization_id,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.asserter_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        extraction_confidence=payload.extraction_confidence,
        human_verified_by_user_id=verified_by,
        human_verified_at=verified_at,
        version=version,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(immunization)
    await db.flush()

    await write_audit(
        db,
        context,
        event_type="clinical.immunization.recorded",
        subject_user_id=patient_id,
        resource_id=immunization.id,
        event_data={
            "vaccine_code": immunization.vaccine_code,
            "status": immunization.status.value,
            "version": version,
        },
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="immunization",
        resource_id=immunization.id,
        request=request,
    )
    await db.commit()
    await db.refresh(immunization)
    return ImmunizationOut.model_validate(immunization)


def _due_query(patient_id: UUID, horizon: datetime) -> Select[tuple[Immunization]]:
    """Doses whose booster is scheduled inside the horizon and not yet given."""
    booster = aliased(Immunization)
    already_boosted = (
        select(booster.id)
        .where(
            booster.booster_of_immunization_id == Immunization.id,
            booster.superseded_at.is_(None),
            booster.status == ImmunizationStatus.COMPLETED,
        )
        .exists()
    )
    return (
        select(Immunization)
        .where(
            Immunization.patient_user_id == patient_id,
            Immunization.superseded_at.is_(None),
            Immunization.status == ImmunizationStatus.COMPLETED,
            Immunization.next_due_at.is_not(None),
            Immunization.next_due_at <= horizon,
            ~already_boosted,
        )
        .order_by(Immunization.next_due_at.asc())
    )


def _due_item(row: Immunization, now: datetime) -> ImmunizationDueItem:
    due_at = row.next_due_at
    assert due_at is not None  # guaranteed by _due_query
    return ImmunizationDueItem(
        immunization_id=row.id,
        vaccine_code=row.vaccine_code,
        vaccine_display=row.vaccine_display,
        series_name=row.series_name,
        series_dose_number=row.series_dose_number,
        series_doses_expected=row.series_doses_expected,
        last_administered_date=row.administered_date,
        next_due_at=due_at,
        days_until_due=(due_at - now).days,
    )


async def immunizations_due(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    horizon_days: int = DEFAULT_DUE_HORIZON_DAYS,
    request: Request | None = None,
) -> ImmunizationDueOut:
    allowed = await _patient_scope(db, context, patient_id)
    await _load_patient(db, patient_id)

    now = datetime.now(UTC)
    horizon = now + timedelta(days=horizon_days)
    stmt = _scoped(_due_query(patient_id, horizon), Immunization, allowed)
    rows = list((await db.scalars(stmt)).all())

    overdue = [_due_item(row, now) for row in rows if row.next_due_at and row.next_due_at < now]
    upcoming = [_due_item(row, now) for row in rows if row.next_due_at and row.next_due_at >= now]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="immunization_due",
        action=PhiAccessAction.SEARCH,
        result_count=len(rows),
        request=request,
    )
    await db.commit()
    return ImmunizationDueOut(
        as_of=now,
        horizon_days=horizon_days,
        overdue=overdue,
        upcoming=upcoming,
    )


# --------------------------------------------------------------------------- #
# Immunization certificates                                                    #
# --------------------------------------------------------------------------- #


def _certificate_out(row: ImmunizationCertificate, patient_id: UUID) -> CertificateOut:
    return CertificateOut(
        id=row.id,
        immunization_id=row.immunization_id,
        patient_user_id=patient_id,
        certificate_number=row.certificate_number,
        issuer_organization_id=row.issuer_organization_id,
        issued_at=row.issued_at,
        verification_hash=row.verification_hash,
        qr_payload=row.qr_payload,
        signature_algorithm=row.signature_algorithm,
        status=row.status,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
        document_asset_id=row.document_asset_id,
    )


def _certificate_payload(
    immunization: Immunization,
    profile: PatientProfile,
    certificate_number: str,
    issuer_organization_id: UUID,
    issued_at: datetime,
) -> str:
    """Canonical JSON that the verification hash is computed over."""
    return json.dumps(
        {
            "certificate_number": certificate_number,
            "patient_id": profile.patient_id,
            "immunization_id": str(immunization.id),
            "vaccine_code_system": immunization.vaccine_code_system,
            "vaccine_code": immunization.vaccine_code,
            "vaccine_display": immunization.vaccine_display,
            "lot_number": immunization.lot_number,
            "administered_date": immunization.administered_date.isoformat(),
            "series_name": immunization.series_name,
            "series_dose_number": immunization.series_dose_number,
            "issuer_organization_id": str(issuer_organization_id),
            "issued_at": issued_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def issue_certificate(
    db: AsyncSession,
    context: AuthContext,
    *,
    immunization_id: UUID,
    payload: CertificateIssueIn,
    signing_secret: str,
    request: Request | None = None,
) -> CertificateOut:
    immunization = await db.get(Immunization, immunization_id)
    if immunization is None:
        raise not_found("Immunization")
    await _patient_scope(db, context, immunization.patient_user_id)

    if immunization.status is not ImmunizationStatus.COMPLETED:
        raise unprocessable("Only a completed dose can be certified")
    if immunization.superseded_at is not None:
        raise conflict("That immunization record has been superseded")

    existing = await db.scalar(
        select(ImmunizationCertificate).where(
            ImmunizationCertificate.immunization_id == immunization_id
        )
    )
    if existing is not None:
        raise conflict("A certificate has already been issued for this dose")

    issuer_id = payload.issuer_organization_id or immunization.organization_id
    if issuer_id is None:
        raise unprocessable("issuer_organization_id is required for this dose")
    if await db.get(Organization, issuer_id) is None:
        raise unprocessable("issuer_organization_id does not reference a known organization")

    profile = await _load_patient(db, immunization.patient_user_id)
    now = datetime.now(UTC)
    certificate_number = f"IMM-{now:%Y%m%d}-{secrets.token_hex(6).upper()}"
    body = _certificate_payload(immunization, profile, certificate_number, issuer_id, now)
    verification_hash = hmac.new(
        signing_secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    qr_payload = json.dumps(
        {"v": 1, "body": body, "hash": verification_hash},
        separators=(",", ":"),
    )

    certificate = ImmunizationCertificate(
        tenant_id=context.tenant_id,
        immunization_id=immunization_id,
        certificate_number=certificate_number,
        issuer_organization_id=issuer_id,
        issued_at=now,
        verification_hash=verification_hash,
        qr_payload=qr_payload,
        signature_algorithm="HMAC-SHA256",
        status=CertificateStatus.ACTIVE,
        document_asset_id=payload.document_asset_id,
    )
    db.add(certificate)
    await db.flush()

    await write_audit(
        db,
        context,
        event_type="clinical.immunization_certificate.issued",
        subject_user_id=immunization.patient_user_id,
        resource_id=certificate.id,
        event_data={
            "certificate_number": certificate_number,
            "immunization_id": str(immunization_id),
        },
        request=request,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=immunization.patient_user_id,
        resource_type="immunization_certificate",
        resource_id=certificate.id,
        action=PhiAccessAction.EXPORT,
        request=request,
    )
    await db.commit()
    await db.refresh(certificate)
    return _certificate_out(certificate, immunization.patient_user_id)


async def get_certificate(
    db: AsyncSession,
    context: AuthContext,
    *,
    immunization_id: UUID,
    request: Request | None = None,
) -> CertificateOut:
    immunization = await db.get(Immunization, immunization_id)
    if immunization is None:
        raise not_found("Immunization")
    await _patient_scope(db, context, immunization.patient_user_id)

    certificate = await db.scalar(
        select(ImmunizationCertificate).where(
            ImmunizationCertificate.immunization_id == immunization_id
        )
    )
    if certificate is None:
        raise not_found("Immunization certificate")

    await record_phi_access(
        db,
        context,
        patient_user_id=immunization.patient_user_id,
        resource_type="immunization_certificate",
        resource_id=certificate.id,
        request=request,
    )
    await db.commit()
    return _certificate_out(certificate, immunization.patient_user_id)


# --------------------------------------------------------------------------- #
# Chart summary                                                                #
# --------------------------------------------------------------------------- #


async def _latest_vitals(
    db: AsyncSession, patient_id: UUID, allowed: set[UUID] | None
) -> list[VitalOut]:
    """Most recent observation per code, via DISTINCT ON rather than N queries."""
    stmt = (
        select(VitalSign)
        .where(
            VitalSign.patient_user_id == patient_id,
            VitalSign.superseded_at.is_(None),
            VitalSign.status != ObservationStatus.ENTERED_IN_ERROR,
        )
        .distinct(VitalSign.observation_code)
        .order_by(VitalSign.observation_code, VitalSign.effective_at.desc())
    )
    stmt = _scoped(stmt, VitalSign, allowed)
    rows = list((await db.scalars(stmt)).all())
    components = await _components_for(db, [row.id for row in rows])
    rows.sort(key=lambda row: row.effective_at, reverse=True)
    return [_vital_out(row, components.get(row.id, [])) for row in rows]


async def _immunization_summary(
    db: AsyncSession, patient_id: UUID, allowed: set[UUID] | None, now: datetime
) -> ImmunizationSummary:
    counts = (
        await db.execute(
            select(
                func.count(),
                func.count(case((Immunization.status == ImmunizationStatus.COMPLETED, 1))),
                func.count(case((Immunization.status == ImmunizationStatus.NOT_DONE, 1))),
                func.max(Immunization.administered_date),
            ).where(
                Immunization.patient_user_id == patient_id,
                Immunization.superseded_at.is_(None),
                Immunization.status != ImmunizationStatus.ENTERED_IN_ERROR,
            )
        )
    ).one()
    total, completed, not_done, latest = counts

    horizon = now + timedelta(days=DEFAULT_DUE_HORIZON_DAYS)
    due_rows = list(
        (await db.scalars(_scoped(_due_query(patient_id, horizon), Immunization, allowed))).all()
    )
    overdue = sum(1 for row in due_rows if row.next_due_at and row.next_due_at < now)
    next_due = due_rows[0].next_due_at if due_rows else None
    return ImmunizationSummary(
        total=total,
        completed=completed,
        not_done=not_done,
        latest_administered_date=latest,
        overdue=overdue,
        upcoming=len(due_rows) - overdue,
        next_due_at=next_due,
    )


async def patient_summary(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_id: UUID,
    request: Request | None = None,
) -> PatientSummary:
    """Everything a clinician needs on open: problems, allergies, vitals, shots."""
    allowed = await _patient_scope(db, context, patient_id)
    profile = await _load_patient(db, patient_id)
    now = datetime.now(UTC)
    today = now.date()

    identifiers = list(
        (
            await db.scalars(
                select(PatientIdentifier)
                .where(
                    PatientIdentifier.patient_user_id == patient_id,
                    PatientIdentifier.is_active.is_(True),
                )
                .order_by(PatientIdentifier.type_code, PatientIdentifier.system)
            )
        ).all()
    )

    condition_stmt = _scoped(
        select(Condition).where(
            Condition.patient_user_id == patient_id,
            Condition.superseded_at.is_(None),
            Condition.verification_status != VerificationStatus.ENTERED_IN_ERROR,
            Condition.clinical_status.in_(ACTIVE_CONDITION_STATUSES),
        ),
        Condition,
        allowed,
    ).order_by(Condition.recorded_at.desc())
    conditions = list((await db.scalars(condition_stmt)).all())

    allergy_stmt = _scoped(
        select(AllergyIntolerance).where(
            AllergyIntolerance.patient_user_id == patient_id,
            AllergyIntolerance.superseded_at.is_(None),
            AllergyIntolerance.clinical_status == ClinicalStatus.ACTIVE,
            AllergyIntolerance.verification_status != AllergyVerificationStatus.ENTERED_IN_ERROR,
        ),
        AllergyIntolerance,
        allowed,
    ).order_by(_criticality_rank(), AllergyIntolerance.recorded_at.desc())
    allergies = list((await db.scalars(allergy_stmt)).all())
    reactions = await _reactions_for(db, [row.id for row in allergies])

    status_row = await db.get(PatientAllergyStatus, patient_id)
    allergy_status = AllergyStatusOut(
        patient_user_id=patient_id,
        no_known_allergies=status_row.no_known_allergies if status_row else False,
        last_reviewed_at=status_row.last_reviewed_at if status_row else None,
        reviewed_by_user_id=status_row.reviewed_by_user_id if status_row else None,
        note=status_row.note if status_row else None,
        active_allergy_count=len(allergies),
    )

    latest_vitals = await _latest_vitals(db, patient_id, allowed)
    immunizations = await _immunization_summary(db, patient_id, allowed, now)

    member = aliased(DoctorProfile)
    care_rows = (
        (
            await db.execute(
                select(CareTeamMember, member.first_name, member.last_name, member.specialty)
                .outerjoin(member, member.user_id == CareTeamMember.member_user_id)
                .where(
                    CareTeamMember.patient_user_id == patient_id,
                    or_(
                        CareTeamMember.period_end.is_(None),
                        CareTeamMember.period_end >= today,
                    ),
                )
                .order_by(CareTeamMember.is_primary.desc(), CareTeamMember.period_start.desc())
            )
        )
        .tuples()
        .all()
    )
    care_team = [
        CareTeamMemberOut(
            id=row.id,
            member_user_id=row.member_user_id,
            member_name=_full_name(first_name, last_name),
            member_specialty=specialty,
            organization_id=row.organization_id,
            role_code=row.role_code,
            is_primary=row.is_primary,
            period_start=row.period_start,
            period_end=row.period_end,
        )
        for row, first_name, last_name, specialty in care_rows
    ]

    family_stmt = _scoped(
        select(FamilyHistory).where(
            FamilyHistory.patient_user_id == patient_id,
            FamilyHistory.superseded_at.is_(None),
        ),
        FamilyHistory,
        allowed,
    ).order_by(FamilyHistory.relationship_code, FamilyHistory.condition_display)
    family = list((await db.scalars(family_stmt)).all())

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_id,
        resource_type="patient_summary",
        resource_id=patient_id,
        result_count=len(conditions) + len(allergies) + len(latest_vitals),
        request=request,
    )
    await db.commit()

    return PatientSummary(
        patient_user_id=patient_id,
        patient_display_id=profile.patient_id,
        full_name=f"{profile.first_name} {profile.last_name}",
        date_of_birth=profile.date_of_birth,
        sex_at_birth=profile.sex_at_birth,
        blood_type=profile.blood_type,
        identifiers=[PatientIdentifierOut.model_validate(row) for row in identifiers],
        active_conditions=[ConditionOut.model_validate(row) for row in conditions],
        active_allergies=[_allergy_out(row, reactions.get(row.id, [])) for row in allergies],
        allergy_status=allergy_status,
        latest_vitals=latest_vitals,
        immunizations=immunizations,
        care_team=care_team,
        family_history=[FamilyHistoryOut.model_validate(row) for row in family],
        generated_at=now,
    )
