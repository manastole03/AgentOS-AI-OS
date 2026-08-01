"""Medication ordering, timed reminders, and adherence.

This module owns the product requirement that a prescription produces
*automatic daily timed reminders that continue until the medication course is
complete*. The mechanism is deliberately materialized rather than computed on
the fly:

``medication_schedules`` holds the recurrence rule (one row per dosage
instruction and time of day), and :func:`generate_occurrences` walks that rule
forward into ``medication_reminder_occurrences`` up to a bounded horizon. Two
columns make the loop terminate rather than run forever: ``ends_on`` and
``total_doses``. When either boundary is crossed the schedule flips to
``completed`` and every pending occurrence past the boundary is cancelled, so
the reminder stream stops exactly when the course does. Chronic schedules carry
neither boundary and are the only ones that keep extending.

Generation is idempotent: the unique constraint
``uq_reminder_occurrence (schedule_id, scheduled_at)`` is the source of truth
and conflicting rows are skipped by the database, not by a pre-read in Python.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import Date, Numeric, Select, cast, distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AdherenceStatus,
    MedicationAdherenceEvent,
    MedicationDispense,
    MedicationDosageInstruction,
    MedicationReminderOccurrence,
    MedicationRequest,
    MedicationRequestIntent,
    MedicationRequestStatus,
    MedicationSchedule,
    MedicationScheduleStatus,
    MedicationStatement,
    MedicationStatementStatus,
    NotificationChannel,
    PatientAllergyStatus,
    PatientProfile,
    Prescription,
    PrescriptionSafetyCheck,
    PrescriptionStatus,
    ProvenanceSource,
    ReminderStatus,
    SafetyCheckOutcome,
    SafetyCheckType,
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
    forbidden,
    not_found,
    paginate,
    record_phi_access,
    unprocessable,
    write_audit,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

#: Checks a prescriber must have run before a script may be issued. The row in
#: ``prescription_safety_checks`` is the durable proof that each one happened.
REQUIRED_SAFETY_CHECKS: frozenset[SafetyCheckType] = frozenset(
    {
        SafetyCheckType.DRUG_ALLERGY,
        SafetyCheckType.DRUG_DRUG,
        SafetyCheckType.DUPLICATE_THERAPY,
    }
)

#: Severities that cannot simply be acknowledged; they need a recorded override.
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"high", "contraindicated"})

#: Upper bound on how far ahead a single generation run may materialize.
MAX_HORIZON_HOURS = 2160
DEFAULT_HORIZON_HOURS = 72

#: Safety valve so back-filling a long-running schedule cannot emit an
#: unbounded INSERT. The caller simply runs the endpoint again.
MAX_OCCURRENCES_PER_RUN = 500

#: FHIR ``days-of-week`` codes, indexed by :meth:`datetime.date.weekday`.
DAY_CODES: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DayCode = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Severity = Literal["none", "low", "moderate", "high", "contraindicated"]
TermType = Literal["SCD", "SBD", "GPCK", "BPCK"]
PeriodUnit = Literal["h", "d", "wk", "mo"]
DeaSchedule = Literal["CI", "CII", "CIII", "CIV", "CV"]
ReminderWindow = Literal["today", "upcoming"]
AckAction = Literal["taken", "skipped", "snoozed"]

#: An acknowledgement resolves the delivery row. ``sent`` means "this reminder
#: is finished with"; ``pending`` is the snooze target (it fires again later).
ACK_TRANSITIONS: dict[str, set[str]] = {
    ReminderStatus.PENDING.value: {ReminderStatus.SENT.value, ReminderStatus.PENDING.value},
    ReminderStatus.SENT.value: {ReminderStatus.SENT.value, ReminderStatus.PENDING.value},
    ReminderStatus.FAILED.value: {ReminderStatus.SENT.value, ReminderStatus.PENDING.value},
    ReminderStatus.CANCELLED.value: set(),
    ReminderStatus.SUPPRESSED.value: set(),
}

ACK_TO_ADHERENCE: dict[str, AdherenceStatus] = {
    "taken": AdherenceStatus.TAKEN,
    "skipped": AdherenceStatus.SKIPPED,
    "snoozed": AdherenceStatus.SNOOZED,
}

#: Occurrence states that never counted as an expected dose: cancelled ones sit
#: past the end of the course, suppressed ones were deliberately not delivered.
NON_EXPECTED_STATUSES: tuple[ReminderStatus, ...] = (
    ReminderStatus.CANCELLED,
    ReminderStatus.SUPPRESSED,
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class DosageInstructionIn(DomainModel):
    """One dose line. A taper is two lines, never one line of free text."""

    sequence: int = Field(default=1, ge=1)
    dose_quantity: Decimal = Field(gt=0)
    dose_unit: str = Field(min_length=1, max_length=32)
    route_code: str = Field(min_length=1, max_length=64)
    frequency: int = Field(default=1, ge=1)
    period: Decimal = Field(default=Decimal(1), gt=0)
    period_unit: PeriodUnit = "d"
    as_needed: bool = False
    as_needed_reason: str | None = Field(default=None, max_length=255)
    max_dose_per_period: Decimal | None = Field(default=None, gt=0)
    is_chronic: bool = False
    effective_start_at: datetime
    effective_end_at: datetime | None = None
    sig_text: str = Field(min_length=1, max_length=500)

    @field_validator("effective_start_at", "effective_end_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if not self.is_chronic and self.effective_end_at is None:
            raise ValueError("effective_end_at is required unless the course is chronic")
        if self.effective_end_at is not None and self.effective_end_at < self.effective_start_at:
            raise ValueError("effective_end_at must not precede effective_start_at")
        if self.as_needed and not self.as_needed_reason:
            raise ValueError("as_needed_reason is required for as-needed dosing")
        return self


class DosageInstructionOut(DomainModel):
    id: UUID
    medication_request_id: UUID
    sequence: int
    dose_quantity: Decimal
    dose_unit: str
    route_code: str
    frequency: int
    period: Decimal
    period_unit: str
    as_needed: bool
    as_needed_reason: str | None
    max_dose_per_period: Decimal | None
    is_chronic: bool
    effective_start_at: datetime
    effective_end_at: datetime | None
    sig_text: str


class MedicationRequestIn(DomainModel):
    """One drug on a script. RxNorm dispensable terms only, never an ingredient."""

    medication_code_system: str = Field(min_length=1, max_length=128)
    medication_code: str = Field(min_length=1, max_length=64)
    medication_display: str = Field(min_length=1, max_length=255)
    medication_concept_id: UUID | None = None
    medication_term_type: TermType
    ndc_code: str | None = Field(default=None, max_length=16)
    intent: MedicationRequestIntent = MedicationRequestIntent.ORDER
    indication_condition_id: UUID | None = None
    substitution_allowed: bool = True
    quantity: Decimal | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=32)
    days_supply: int | None = Field(default=None, ge=1)
    refills_allowed: int = Field(default=0, ge=0)
    controlled_substance_schedule: DeaSchedule | None = None
    supersedes_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=500)
    dosage_instructions: list[DosageInstructionIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.controlled_substance_schedule == "CII" and self.refills_allowed:
            raise ValueError("Schedule CII medications cannot carry refills")
        if (self.quantity is None) != (self.quantity_unit is None):
            raise ValueError("quantity and quantity_unit must be supplied together")
        sequences = [line.sequence for line in self.dosage_instructions]
        if len(set(sequences)) != len(sequences):
            raise ValueError("dosage instruction sequences must be unique")
        return self


class MedicationRequestOut(DomainModel):
    id: UUID
    prescription_id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    medication_code_system: str
    medication_code: str
    medication_display: str
    medication_term_type: str
    ndc_code: str | None
    status: MedicationRequestStatus
    intent: MedicationRequestIntent
    substitution_allowed: bool
    quantity: Decimal | None
    quantity_unit: str | None
    days_supply: int | None
    refills_allowed: int
    refills_remaining: int
    controlled_substance_schedule: str | None
    stopped_at: datetime | None
    stop_reason: str | None
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None
    recorded_at: datetime
    dispensed_fills: int = 0
    last_dispensed_at: datetime | None = None
    dosage_instructions: list[DosageInstructionOut] = Field(default_factory=list)


class SafetyCheckBase(DomainModel):
    check_type: SafetyCheckType
    severity: Severity
    outcome: SafetyCheckOutcome
    message: str = Field(min_length=1, max_length=500)
    triggered_by_code_system: str | None = Field(default=None, max_length=128)
    triggered_by_code: str | None = Field(default=None, max_length=64)
    override_reason: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _override_pair(self) -> Self:
        overridden = self.outcome == SafetyCheckOutcome.OVERRIDDEN
        if overridden and not self.override_reason:
            raise ValueError("override_reason is required when the outcome is 'overridden'")
        if not overridden and self.override_reason:
            raise ValueError("override_reason is only meaningful for an overridden outcome")
        if self.outcome == SafetyCheckOutcome.NO_ALERT and self.severity != "none":
            raise ValueError("a 'no_alert' outcome must carry severity 'none'")
        return self


class InlineSafetyCheckIn(SafetyCheckBase):
    """A check submitted alongside the prescription it belongs to.

    ``medication_request_id`` cannot be supplied yet, so the drug is named by
    its position in :attr:`PrescriptionCreate.requests`.
    """

    medication_index: int | None = Field(default=None, ge=0)


class SafetyCheckIn(SafetyCheckBase):
    medication_request_id: UUID | None = None


class SafetyCheckBatch(DomainModel):
    checks: list[SafetyCheckIn] = Field(min_length=1, max_length=50)


class SafetyCheckOut(DomainModel):
    id: UUID
    prescription_id: UUID
    medication_request_id: UUID | None
    patient_user_id: UUID
    check_type: SafetyCheckType
    severity: str
    triggered_by_code_system: str | None
    triggered_by_code: str | None
    message: str
    outcome: SafetyCheckOutcome
    overridden_by_user_id: UUID | None
    override_reason: str | None
    payload: dict[str, Any]
    created_at: datetime


class PrescriptionCreate(DomainModel):
    prescriber_user_id: UUID
    encounter_id: UUID | None = None
    prescription_number: str | None = Field(default=None, min_length=1, max_length=64)
    written_at: datetime | None = None
    dosing_weight_kg: Decimal | None = Field(default=None, gt=0)
    dosing_weight_observed_at: datetime | None = None
    note: str | None = None
    source: ProvenanceSource = ProvenanceSource.PRACTITIONER
    source_document_id: UUID | None = None
    supersedes_id: UUID | None = None
    amendment_reason: str | None = Field(default=None, max_length=500)
    requests: list[MedicationRequestIn] = Field(min_length=1, max_length=50)
    safety_checks: list[InlineSafetyCheckIn] = Field(default_factory=list)

    @field_validator("written_at", "dosing_weight_observed_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if (self.dosing_weight_kg is None) != (self.dosing_weight_observed_at is None):
            raise ValueError("dosing_weight_kg and dosing_weight_observed_at travel together")
        for check in self.safety_checks:
            if check.medication_index is not None and check.medication_index >= len(self.requests):
                raise ValueError("medication_index does not address a request in this payload")
        return self


class PrescriptionOut(DomainModel):
    id: UUID
    tenant_id: UUID
    patient_user_id: UUID
    prescriber_user_id: UUID
    encounter_id: UUID | None
    prescription_number: str
    status: PrescriptionStatus
    written_at: datetime
    dosing_weight_kg: Decimal | None
    dosing_weight_observed_at: datetime | None
    note: str | None
    source: ProvenanceSource
    recorded_by_user_id: UUID
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None
    superseded_at: datetime | None
    amendment_reason: str | None
    requests: list[MedicationRequestOut] = Field(default_factory=list)
    safety_checks: list[SafetyCheckOut] = Field(default_factory=list)


class MedicationStatementOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    encounter_id: UUID | None
    medication_code_system: str
    medication_code: str
    medication_display: str
    medication_term_type: str | None
    status: MedicationStatementStatus
    sig_text: str | None
    effective_start_at: datetime | None
    effective_end_at: datetime | None
    note: str | None
    source: ProvenanceSource
    recorded_at: datetime
    version: int
    supersedes_id: UUID | None


class ScheduleCreate(DomainModel):
    """The recurrence rule the reminder generator walks forward."""

    dosage_instruction_id: UUID | None = None
    times_local: list[time] = Field(min_length=1, max_length=12)
    timezone: str = Field(min_length=1, max_length=64)
    days_of_week: list[DayCode] = Field(default_factory=list)
    starts_on: date | None = None
    ends_on: date | None = None
    is_chronic: bool = False
    total_doses: int | None = Field(default=None, gt=0)
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.IN_APP],
        min_length=1,
    )

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        if len(set(self.times_local)) != len(self.times_local):
            raise ValueError("times_local must not repeat a time of day")
        if len(set(self.days_of_week)) != len(self.days_of_week):
            raise ValueError("days_of_week must not repeat a day")
        if not self.is_chronic and self.ends_on is None:
            raise ValueError("ends_on is required unless the schedule is chronic")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on must not precede starts_on")
        return self


class ScheduleOut(DomainModel):
    id: UUID
    tenant_id: UUID
    patient_user_id: UUID
    prescription_id: UUID
    medication_request_id: UUID
    dosage_instruction_id: UUID
    time_local: time
    timezone: str
    days_of_week: list[str]
    starts_on: date
    ends_on: date | None
    is_chronic: bool
    total_doses: int | None
    doses_generated: int
    generated_through: date | None
    status: MedicationScheduleStatus
    channels: list[str]


class GenerateOccurrencesRequest(DomainModel):
    horizon_hours: int = Field(default=DEFAULT_HORIZON_HOURS, ge=1, le=MAX_HORIZON_HOURS)


class GenerationResult(DomainModel):
    schedule_id: UUID
    status: MedicationScheduleStatus
    created: int
    skipped: int
    cancelled: int
    generated_through: date | None
    doses_generated: int
    total_doses: int | None
    window_end: datetime
    course_complete: bool


class ReminderOut(DomainModel):
    id: UUID
    schedule_id: UUID
    patient_user_id: UUID
    medication_request_id: UUID
    scheduled_at: datetime
    time_local: time
    timezone: str
    status: ReminderStatus
    channel: NotificationChannel
    sent_at: datetime | None
    attempts: int
    medication_code: str
    medication_display: str
    dose_quantity: Decimal
    dose_unit: str
    route_code: str
    sig_text: str


class ReminderAck(DomainModel):
    action: AckAction
    taken_at: datetime | None = None
    dose_taken_quantity: Decimal | None = Field(default=None, gt=0)
    dose_unit: str | None = Field(default=None, max_length=32)
    reason_code: str | None = Field(default=None, max_length=64)
    note: str | None = None
    snooze_minutes: int = Field(default=15, ge=1, le=1440)

    @field_validator("taken_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.action != "taken" and self.taken_at is not None:
            raise ValueError("taken_at is only valid when the dose was taken")
        if (self.dose_taken_quantity is None) != (self.dose_unit is None):
            raise ValueError("dose_taken_quantity and dose_unit travel together")
        return self


class AdherenceEventOut(DomainModel):
    id: UUID
    patient_user_id: UUID
    schedule_id: UUID
    occurrence_id: UUID | None
    medication_request_id: UUID
    status: AdherenceStatus
    scheduled_at: datetime
    recorded_at: datetime
    taken_at: datetime | None
    dose_taken_quantity: Decimal | None
    dose_unit: str | None
    reported_by_user_id: UUID
    reason_code: str | None
    note: str | None


class AckResult(DomainModel):
    occurrence_id: UUID
    occurrence_status: ReminderStatus
    scheduled_at: datetime
    event: AdherenceEventOut


class AdherenceRow(DomainModel):
    medication_request_id: UUID
    medication_code: str
    medication_display: str
    expected_doses: int
    taken_doses: int
    skipped_doses: int
    missed_doses: int
    adherence_rate: Decimal


class AdherenceReport(DomainModel):
    patient_user_id: UUID
    window_start: datetime
    window_end: datetime
    days: int
    expected_doses: int
    taken_doses: int
    adherence_rate: Decimal
    items: list[AdherenceRow]


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a naive payload timestamp to UTC before it reaches asyncpg."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise unprocessable(f"Unknown IANA timezone '{name}'") from exc


def _scoped(query: Select[Any], model: Any, allowed: set[UUID] | None) -> Select[Any]:
    """:func:`apply_patient_scope` for column-oriented selects."""
    return apply_patient_scope(query, model, allowed)


async def _patient_scope(
    db: AsyncSession, context: AuthContext, patient_user_id: UUID
) -> set[UUID] | None:
    """Consent allow-set, rejecting the request outright if this patient is out of it."""
    allowed = await consent_scoped_patients(db, context)
    if allowed is not None and patient_user_id not in allowed:
        raise forbidden("No consent grant covers this patient")
    return allowed


async def _require_patient(db: AsyncSession, patient_user_id: UUID) -> None:
    exists = await db.scalar(
        select(PatientProfile.user_id).where(PatientProfile.user_id == patient_user_id)
    )
    if exists is None:
        raise not_found("Patient")


def _dosage_out(row: MedicationDosageInstruction) -> DosageInstructionOut:
    return DosageInstructionOut(
        id=row.id,
        medication_request_id=row.medication_request_id,
        sequence=row.sequence,
        dose_quantity=row.dose_quantity,
        dose_unit=row.dose_unit,
        route_code=row.route_code,
        frequency=row.frequency,
        period=row.period,
        period_unit=row.period_unit,
        as_needed=row.as_needed,
        as_needed_reason=row.as_needed_reason,
        max_dose_per_period=row.max_dose_per_period,
        is_chronic=row.is_chronic,
        effective_start_at=row.effective_start_at,
        effective_end_at=row.effective_end_at,
        sig_text=row.sig_text,
    )


def _request_out(
    row: MedicationRequest,
    dosages: list[DosageInstructionOut],
    fills: tuple[int, datetime | None] = (0, None),
) -> MedicationRequestOut:
    return MedicationRequestOut(
        id=row.id,
        prescription_id=row.prescription_id,
        patient_user_id=row.patient_user_id,
        encounter_id=row.encounter_id,
        medication_code_system=row.medication_code_system,
        medication_code=row.medication_code,
        medication_display=row.medication_display,
        medication_term_type=row.medication_term_type,
        ndc_code=row.ndc_code,
        status=row.status,
        intent=row.intent,
        substitution_allowed=row.substitution_allowed,
        quantity=row.quantity,
        quantity_unit=row.quantity_unit,
        days_supply=row.days_supply,
        refills_allowed=row.refills_allowed,
        refills_remaining=row.refills_remaining,
        controlled_substance_schedule=row.controlled_substance_schedule,
        stopped_at=row.stopped_at,
        stop_reason=row.stop_reason,
        version=row.version,
        supersedes_id=row.supersedes_id,
        superseded_at=row.superseded_at,
        recorded_at=row.recorded_at,
        dispensed_fills=fills[0],
        last_dispensed_at=fills[1],
        dosage_instructions=dosages,
    )


def _safety_out(row: PrescriptionSafetyCheck) -> SafetyCheckOut:
    return SafetyCheckOut(
        id=row.id,
        prescription_id=row.prescription_id,
        medication_request_id=row.medication_request_id,
        patient_user_id=row.patient_user_id,
        check_type=row.check_type,
        severity=row.severity,
        triggered_by_code_system=row.triggered_by_code_system,
        triggered_by_code=row.triggered_by_code,
        message=row.message,
        outcome=row.outcome,
        overridden_by_user_id=row.overridden_by_user_id,
        override_reason=row.override_reason,
        payload=row.payload,
        created_at=row.created_at,
    )


def _prescription_out(
    row: Prescription,
    requests: list[MedicationRequestOut],
    checks: list[SafetyCheckOut],
) -> PrescriptionOut:
    return PrescriptionOut(
        id=row.id,
        tenant_id=row.tenant_id,
        patient_user_id=row.patient_user_id,
        prescriber_user_id=row.prescriber_user_id,
        encounter_id=row.encounter_id,
        prescription_number=row.prescription_number,
        status=row.status,
        written_at=row.written_at,
        dosing_weight_kg=row.dosing_weight_kg,
        dosing_weight_observed_at=row.dosing_weight_observed_at,
        note=row.note,
        source=row.source,
        recorded_by_user_id=row.recorded_by_user_id,
        recorded_at=row.recorded_at,
        version=row.version,
        supersedes_id=row.supersedes_id,
        superseded_at=row.superseded_at,
        amendment_reason=row.amendment_reason,
        requests=requests,
        safety_checks=checks,
    )


def _schedule_out(row: MedicationSchedule) -> ScheduleOut:
    return ScheduleOut(
        id=row.id,
        tenant_id=row.tenant_id,
        patient_user_id=row.patient_user_id,
        prescription_id=row.prescription_id,
        medication_request_id=row.medication_request_id,
        dosage_instruction_id=row.dosage_instruction_id,
        time_local=row.time_local,
        timezone=row.timezone,
        days_of_week=list(row.days_of_week),
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        is_chronic=row.is_chronic,
        total_doses=row.total_doses,
        doses_generated=row.doses_generated,
        generated_through=row.generated_through,
        status=row.status,
        channels=list(row.channels),
    )


def _statement_out(row: MedicationStatement) -> MedicationStatementOut:
    return MedicationStatementOut(
        id=row.id,
        patient_user_id=row.patient_user_id,
        encounter_id=row.encounter_id,
        medication_code_system=row.medication_code_system,
        medication_code=row.medication_code,
        medication_display=row.medication_display,
        medication_term_type=row.medication_term_type,
        status=row.status,
        sig_text=row.sig_text,
        effective_start_at=row.effective_start_at,
        effective_end_at=row.effective_end_at,
        note=row.note,
        source=row.source,
        recorded_at=row.recorded_at,
        version=row.version,
        supersedes_id=row.supersedes_id,
    )


def _adherence_event_out(row: MedicationAdherenceEvent) -> AdherenceEventOut:
    return AdherenceEventOut(
        id=row.id,
        patient_user_id=row.patient_user_id,
        schedule_id=row.schedule_id,
        occurrence_id=row.occurrence_id,
        medication_request_id=row.medication_request_id,
        status=row.status,
        scheduled_at=row.scheduled_at,
        recorded_at=row.recorded_at,
        taken_at=row.taken_at,
        dose_taken_quantity=row.dose_taken_quantity,
        dose_unit=row.dose_unit,
        reported_by_user_id=row.reported_by_user_id,
        reason_code=row.reason_code,
        note=row.note,
    )


async def _dispense_totals(
    db: AsyncSession, request_ids: list[UUID]
) -> dict[UUID, tuple[int, datetime | None]]:
    """Fill counts per medication request, aggregated in SQL."""
    if not request_ids:
        return {}
    rows = await db.execute(
        select(
            MedicationDispense.medication_request_id,
            func.count(MedicationDispense.id),
            func.max(MedicationDispense.dispensed_at),
        )
        .where(MedicationDispense.medication_request_id.in_(request_ids))
        .group_by(MedicationDispense.medication_request_id)
    )
    return {row[0]: (row[1], row[2]) for row in rows.all()}


async def _hydrate_prescriptions(
    db: AsyncSession, prescriptions: list[Prescription]
) -> list[PrescriptionOut]:
    """Attach requests, dosage lines, fills, and safety checks in four queries."""
    if not prescriptions:
        return []
    prescription_ids = [row.id for row in prescriptions]

    requests = list(
        await db.scalars(
            select(MedicationRequest)
            .where(MedicationRequest.prescription_id.in_(prescription_ids))
            .order_by(MedicationRequest.medication_display, MedicationRequest.recorded_at)
        )
    )
    request_ids = [row.id for row in requests]

    dosages = list(
        await db.scalars(
            select(MedicationDosageInstruction)
            .where(MedicationDosageInstruction.medication_request_id.in_(request_ids))
            .order_by(
                MedicationDosageInstruction.medication_request_id,
                MedicationDosageInstruction.sequence,
            )
        )
        if request_ids
        else []
    )
    checks = list(
        await db.scalars(
            select(PrescriptionSafetyCheck)
            .where(PrescriptionSafetyCheck.prescription_id.in_(prescription_ids))
            .order_by(PrescriptionSafetyCheck.created_at)
        )
    )
    fills = await _dispense_totals(db, request_ids)

    dosages_by_request: dict[UUID, list[DosageInstructionOut]] = {}
    for dosage in dosages:
        dosages_by_request.setdefault(dosage.medication_request_id, []).append(_dosage_out(dosage))

    requests_by_prescription: dict[UUID, list[MedicationRequestOut]] = {}
    for item in requests:
        requests_by_prescription.setdefault(item.prescription_id, []).append(
            _request_out(
                item,
                dosages_by_request.get(item.id, []),
                fills.get(item.id, (0, None)),
            )
        )

    checks_by_prescription: dict[UUID, list[SafetyCheckOut]] = {}
    for check in checks:
        checks_by_prescription.setdefault(check.prescription_id, []).append(_safety_out(check))

    return [
        _prescription_out(
            row,
            requests_by_prescription.get(row.id, []),
            checks_by_prescription.get(row.id, []),
        )
        for row in prescriptions
    ]


def _generate_number(written_at: datetime) -> str:
    return f"RX-{written_at:%Y%m%d}-{uuid4().hex[:10].upper()}"


def _dose_days(starts_on: date, ends_on: date, days_of_week: list[str]) -> int:
    """Count dosing days in a closed date range, honouring day-of-week masks."""
    total = 0
    cursor = starts_on
    while cursor <= ends_on:
        if not days_of_week or DAY_CODES[cursor.weekday()] in days_of_week:
            total += 1
        cursor += timedelta(days=1)
    return total


def _local_instant(day: date, at: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


# --------------------------------------------------------------------------
# Prescriptions
# --------------------------------------------------------------------------


async def list_prescriptions(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    page: Pagination,
    status_filter: PrescriptionStatus | None,
    include_superseded: bool,
    request: Request,
) -> Page[PrescriptionOut]:
    allowed = await _patient_scope(db, context, patient_user_id)

    query = select(Prescription).where(Prescription.patient_user_id == patient_user_id)
    query = apply_patient_scope(query, Prescription, allowed)
    if status_filter is not None:
        query = query.where(Prescription.status == status_filter)
    if not include_superseded:
        query = query.where(Prescription.superseded_at.is_(None))
    query = (
        query.order_by(Prescription.written_at.desc(), Prescription.id)
        .offset(page.offset)
        .limit(page.limit + 1)
    )

    rows = list(await db.scalars(query))
    items = await _hydrate_prescriptions(db, rows)

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="prescription",
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def create_prescription(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    payload: PrescriptionCreate,
    request: Request,
) -> PrescriptionOut:
    """Issue a script, its drugs, its dosing, and its safety evidence atomically.

    The 409s here are the prescribing guard rails: an unreviewed allergy list
    and a missing interaction/allergy/duplicate-therapy check both block the
    write, and a high-severity alert must be explicitly overridden with a
    reason before the script exists at all.
    """
    await assert_may_read_patient(db, context, patient_user_id)
    await _require_patient(db, patient_user_id)

    now = _now()
    written_at = payload.written_at or now

    # (a) the allergy list must have been reviewed for this patient.
    reviewed_at = await db.scalar(
        select(PatientAllergyStatus.last_reviewed_at).where(
            PatientAllergyStatus.user_id == patient_user_id
        )
    )
    if reviewed_at is None:
        raise conflict(
            "Allergy list has not been reviewed for this patient; "
            "record patient_allergy_status.last_reviewed_at first"
        )

    # (b) every required safety check must end up on the row. Checks already
    # recorded against the prescription being superseded still count.
    supplied = {check.check_type for check in payload.safety_checks}
    carried: set[SafetyCheckType] = set()
    superseded: Prescription | None = None
    if payload.supersedes_id is not None:
        superseded = await db.scalar(
            select(Prescription).where(Prescription.id == payload.supersedes_id)
        )
        if superseded is None or superseded.patient_user_id != patient_user_id:
            raise not_found("Superseded prescription")
        carried = set(
            await db.scalars(
                select(PrescriptionSafetyCheck.check_type).where(
                    PrescriptionSafetyCheck.prescription_id == payload.supersedes_id
                )
            )
        )
    missing = sorted(check.value for check in REQUIRED_SAFETY_CHECKS - (supplied | carried))
    if missing:
        raise conflict(f"Missing required safety checks: {', '.join(missing)}")

    unresolved = [
        check.check_type.value
        for check in payload.safety_checks
        if check.severity in BLOCKING_SEVERITIES and check.outcome != SafetyCheckOutcome.OVERRIDDEN
    ]
    if unresolved:
        raise conflict(
            "High-severity safety alerts must be overridden with a reason: "
            f"{', '.join(sorted(set(unresolved)))}"
        )

    # The partial unique index forbids two active requests for one drug, so the
    # prescriber must say which existing order each line replaces.
    codes = [line.medication_code for line in payload.requests]
    replaced_ids = {line.supersedes_id for line in payload.requests if line.supersedes_id}
    clashes = list(
        await db.execute(
            select(MedicationRequest.id, MedicationRequest.medication_display).where(
                MedicationRequest.patient_user_id == patient_user_id,
                MedicationRequest.medication_code.in_(codes),
                MedicationRequest.status == MedicationRequestStatus.ACTIVE,
            )
        )
    )
    blocking = [row[1] for row in clashes if row[0] not in replaced_ids]
    if blocking:
        raise conflict(
            "An active medication request already exists for: "
            f"{', '.join(sorted(set(blocking)))}. Supply supersedes_id to replace it."
        )

    prescription = Prescription(
        tenant_id=context.tenant_id,
        patient_user_id=patient_user_id,
        prescriber_user_id=payload.prescriber_user_id,
        encounter_id=payload.encounter_id,
        prescription_number=payload.prescription_number or _generate_number(written_at),
        status=PrescriptionStatus.ACTIVE,
        written_at=written_at,
        dosing_weight_kg=payload.dosing_weight_kg,
        dosing_weight_observed_at=payload.dosing_weight_observed_at,
        note=payload.note,
        recorded_by_user_id=context.user.id,
        asserter_user_id=payload.prescriber_user_id,
        recorded_at=now,
        source=payload.source,
        source_document_id=payload.source_document_id,
        version=(superseded.version + 1) if superseded is not None else 1,
        supersedes_id=payload.supersedes_id,
        amendment_reason=payload.amendment_reason,
    )
    db.add(prescription)
    await db.flush()

    if superseded is not None:
        # Corrections never overwrite: the old row is closed, not edited.
        superseded.superseded_at = now

    created_requests: list[MedicationRequest] = []
    created_dosages: dict[UUID, list[MedicationDosageInstruction]] = {}
    for line in payload.requests:
        replaced: MedicationRequest | None = None
        if line.supersedes_id is not None:
            replaced = await db.scalar(
                select(MedicationRequest).where(MedicationRequest.id == line.supersedes_id)
            )
            if replaced is None or replaced.patient_user_id != patient_user_id:
                raise not_found("Superseded medication request")

        med_request = MedicationRequest(
            tenant_id=context.tenant_id,
            prescription_id=prescription.id,
            patient_user_id=patient_user_id,
            encounter_id=payload.encounter_id,
            medication_code_system=line.medication_code_system,
            medication_code=line.medication_code,
            medication_display=line.medication_display,
            medication_concept_id=line.medication_concept_id,
            medication_term_type=line.medication_term_type,
            ndc_code=line.ndc_code,
            status=MedicationRequestStatus.ACTIVE,
            intent=line.intent,
            indication_condition_id=line.indication_condition_id,
            substitution_allowed=line.substitution_allowed,
            quantity=line.quantity,
            quantity_unit=line.quantity_unit,
            days_supply=line.days_supply,
            refills_allowed=line.refills_allowed,
            refills_remaining=line.refills_allowed,
            controlled_substance_schedule=line.controlled_substance_schedule,
            recorded_by_user_id=context.user.id,
            asserter_user_id=payload.prescriber_user_id,
            recorded_at=now,
            source=payload.source,
            source_document_id=payload.source_document_id,
            version=(replaced.version + 1) if replaced is not None else 1,
            supersedes_id=line.supersedes_id,
            amendment_reason=line.amendment_reason,
        )
        db.add(med_request)
        await db.flush()
        created_requests.append(med_request)

        if replaced is not None:
            replaced.status = MedicationRequestStatus.STOPPED
            replaced.stopped_at = now
            replaced.stop_reason = line.amendment_reason or "Replaced by a newer order"
            replaced.stopped_by_user_id = context.user.id
            replaced.superseded_at = now

        dosage_rows: list[MedicationDosageInstruction] = []
        for dosage in sorted(line.dosage_instructions, key=lambda item: item.sequence):
            row = MedicationDosageInstruction(
                medication_request_id=med_request.id,
                sequence=dosage.sequence,
                dose_quantity=dosage.dose_quantity,
                dose_unit=dosage.dose_unit,
                route_code=dosage.route_code,
                frequency=dosage.frequency,
                period=dosage.period,
                period_unit=dosage.period_unit,
                as_needed=dosage.as_needed,
                as_needed_reason=dosage.as_needed_reason,
                max_dose_per_period=dosage.max_dose_per_period,
                is_chronic=dosage.is_chronic,
                effective_start_at=dosage.effective_start_at,
                effective_end_at=dosage.effective_end_at,
                sig_text=dosage.sig_text,
            )
            db.add(row)
            dosage_rows.append(row)
        created_dosages[med_request.id] = dosage_rows

        # Keep the "current medications" list truthful the moment the script
        # is written, rather than waiting for a reconciliation pass.
        first = dosage_rows[0]
        ends = [item.effective_end_at for item in dosage_rows]
        course_end = None if any(end is None for end in ends) else max(end for end in ends if end)
        db.add(
            MedicationStatement(
                tenant_id=context.tenant_id,
                patient_user_id=patient_user_id,
                encounter_id=payload.encounter_id,
                medication_code_system=line.medication_code_system,
                medication_code=line.medication_code,
                medication_display=line.medication_display,
                medication_concept_id=line.medication_concept_id,
                medication_term_type=line.medication_term_type,
                status=MedicationStatementStatus.ACTIVE,
                sig_text=first.sig_text,
                effective_start_at=first.effective_start_at,
                effective_end_at=course_end,
                note=payload.note,
                recorded_by_user_id=context.user.id,
                asserter_user_id=payload.prescriber_user_id,
                recorded_at=now,
                source=payload.source,
                source_document_id=payload.source_document_id,
                version=1,
            )
        )

    check_rows: list[PrescriptionSafetyCheck] = []
    for check in payload.safety_checks:
        target = (
            created_requests[check.medication_index].id
            if check.medication_index is not None
            else None
        )
        check_row = PrescriptionSafetyCheck(
            tenant_id=context.tenant_id,
            prescription_id=prescription.id,
            medication_request_id=target,
            patient_user_id=patient_user_id,
            check_type=check.check_type,
            severity=check.severity,
            triggered_by_code_system=check.triggered_by_code_system,
            triggered_by_code=check.triggered_by_code,
            message=check.message,
            outcome=check.outcome,
            overridden_by_user_id=(
                context.user.id if check.outcome == SafetyCheckOutcome.OVERRIDDEN else None
            ),
            override_reason=check.override_reason,
            payload=check.payload,
            created_at=now,
        )
        db.add(check_row)
        check_rows.append(check_row)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("Prescription violates a uniqueness or clinical constraint") from exc

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="prescription",
        resource_id=prescription.id,
        result_count=len(created_requests),
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="prescription.issued",
        subject_user_id=patient_user_id,
        resource_id=prescription.id,
        event_data={
            "prescription_number": prescription.prescription_number,
            "medication_count": len(created_requests),
            "safety_checks": sorted({check.check_type.value for check in payload.safety_checks}),
            "supersedes_id": str(payload.supersedes_id) if payload.supersedes_id else None,
        },
        request=request,
    )

    response = _prescription_out(
        prescription,
        [
            _request_out(item, [_dosage_out(d) for d in created_dosages[item.id]])
            for item in created_requests
        ],
        [_safety_out(row) for row in check_rows],
    )
    await db.commit()
    return response


async def record_safety_checks(
    db: AsyncSession,
    context: AuthContext,
    *,
    prescription_id: UUID,
    payload: SafetyCheckBatch,
    request: Request,
) -> list[SafetyCheckOut]:
    """Append allergy / interaction / duplicate-therapy results to a script."""
    prescription = await db.scalar(select(Prescription).where(Prescription.id == prescription_id))
    if prescription is None:
        raise not_found("Prescription")
    await assert_may_read_patient(db, context, prescription.patient_user_id)
    if prescription.status in (PrescriptionStatus.CANCELLED, PrescriptionStatus.ENTERED_IN_ERROR):
        raise conflict(f"Cannot add safety checks to a '{prescription.status.value}' prescription")

    targeted = {
        check.medication_request_id for check in payload.checks if check.medication_request_id
    }
    if targeted:
        known = set(
            await db.scalars(
                select(MedicationRequest.id).where(
                    MedicationRequest.id.in_(targeted),
                    MedicationRequest.prescription_id == prescription_id,
                )
            )
        )
        unknown = targeted - known
        if unknown:
            raise unprocessable("medication_request_id does not belong to this prescription")

    now = _now()
    rows = [
        PrescriptionSafetyCheck(
            tenant_id=context.tenant_id,
            prescription_id=prescription_id,
            medication_request_id=check.medication_request_id,
            patient_user_id=prescription.patient_user_id,
            check_type=check.check_type,
            severity=check.severity,
            triggered_by_code_system=check.triggered_by_code_system,
            triggered_by_code=check.triggered_by_code,
            message=check.message,
            outcome=check.outcome,
            overridden_by_user_id=(
                context.user.id if check.outcome == SafetyCheckOutcome.OVERRIDDEN else None
            ),
            override_reason=check.override_reason,
            payload=check.payload,
            created_at=now,
        )
        for check in payload.checks
    ]
    db.add_all(rows)
    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=prescription.patient_user_id,
        resource_type="prescription_safety_check",
        resource_id=prescription_id,
        result_count=len(rows),
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="prescription.safety_checked",
        subject_user_id=prescription.patient_user_id,
        resource_id=prescription_id,
        event_data={
            "checks": [
                {
                    "check_type": check.check_type.value,
                    "severity": check.severity,
                    "outcome": check.outcome.value,
                }
                for check in payload.checks
            ]
        },
        request=request,
    )

    response = [_safety_out(row) for row in rows]
    await db.commit()
    return response


async def list_current_medications(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    page: Pagination,
    status_filter: MedicationStatementStatus | None,
    request: Request,
) -> Page[MedicationStatementOut]:
    """The patient's current medication list (``medication_statements``)."""
    allowed = await _patient_scope(db, context, patient_user_id)

    query = select(MedicationStatement).where(
        MedicationStatement.patient_user_id == patient_user_id,
        MedicationStatement.superseded_at.is_(None),
        MedicationStatement.status == (status_filter or MedicationStatementStatus.ACTIVE),
    )
    query = apply_patient_scope(query, MedicationStatement, allowed)
    query = (
        query.order_by(
            MedicationStatement.medication_display,
            MedicationStatement.recorded_at.desc(),
        )
        .offset(page.offset)
        .limit(page.limit + 1)
    )

    rows = list(await db.scalars(query))
    items = [_statement_out(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="medication_statement",
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


# --------------------------------------------------------------------------
# Schedules and reminder generation
# --------------------------------------------------------------------------


async def create_schedule(
    db: AsyncSession,
    context: AuthContext,
    *,
    medication_request_id: UUID,
    payload: ScheduleCreate,
    request: Request,
) -> list[ScheduleOut]:
    """Create one schedule row per time of day for a medication request."""
    med_request = await db.scalar(
        select(MedicationRequest).where(MedicationRequest.id == medication_request_id)
    )
    if med_request is None:
        raise not_found("Medication request")
    await assert_may_read_patient(db, context, med_request.patient_user_id)
    if med_request.status not in (
        MedicationRequestStatus.ACTIVE,
        MedicationRequestStatus.DRAFT,
        MedicationRequestStatus.ON_HOLD,
    ):
        raise conflict(f"Cannot schedule a '{med_request.status.value}' medication request")

    zone = _zone(payload.timezone)

    dosage_query = select(MedicationDosageInstruction).where(
        MedicationDosageInstruction.medication_request_id == medication_request_id
    )
    if payload.dosage_instruction_id is not None:
        dosage_query = dosage_query.where(
            MedicationDosageInstruction.id == payload.dosage_instruction_id
        )
    dosage = await db.scalar(dosage_query.order_by(MedicationDosageInstruction.sequence).limit(1))
    if dosage is None:
        raise not_found("Dosage instruction")
    if dosage.as_needed:
        raise conflict("As-needed dosing has no fixed times and cannot be scheduled")

    starts_on = payload.starts_on or datetime.now(zone).date()
    ends_on = payload.ends_on
    if ends_on is None and not payload.is_chronic:
        # Mirrors the schedule_course_bounded constraint; reached only when the
        # caller omitted starts_on-derived defaults.
        raise unprocessable("ends_on is required unless the schedule is chronic")
    if ends_on is not None and ends_on < starts_on:
        raise unprocessable("ends_on must not precede starts_on")

    days = [str(day) for day in payload.days_of_week]
    total_doses = payload.total_doses
    if total_doses is None and ends_on is not None:
        total_doses = _dose_days(starts_on, ends_on, days) or None

    existing = set(
        await db.scalars(
            select(MedicationSchedule.time_local).where(
                MedicationSchedule.dosage_instruction_id == dosage.id,
                MedicationSchedule.time_local.in_(payload.times_local),
            )
        )
    )
    if existing:
        clashing = ", ".join(sorted(item.isoformat() for item in existing))
        raise conflict(f"A schedule already exists for this dosage line at: {clashing}")

    rows = [
        MedicationSchedule(
            tenant_id=context.tenant_id,
            patient_user_id=med_request.patient_user_id,
            prescription_id=med_request.prescription_id,
            medication_request_id=med_request.id,
            dosage_instruction_id=dosage.id,
            time_local=at,
            timezone=payload.timezone,
            days_of_week=days,
            starts_on=starts_on,
            ends_on=ends_on,
            is_chronic=payload.is_chronic,
            total_doses=total_doses,
            doses_generated=0,
            generated_through=None,
            status=MedicationScheduleStatus.ACTIVE,
            channels=[channel.value for channel in payload.channels],
        )
        for at in sorted(payload.times_local)
    ]
    db.add_all(rows)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("A schedule already exists for this dosage line and time") from exc

    await record_phi_access(
        db,
        context,
        patient_user_id=med_request.patient_user_id,
        resource_type="medication_schedule",
        resource_id=med_request.id,
        result_count=len(rows),
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="medication_schedule.created",
        subject_user_id=med_request.patient_user_id,
        resource_id=med_request.id,
        event_data={
            "times_local": [at.isoformat() for at in sorted(payload.times_local)],
            "timezone": payload.timezone,
            "starts_on": starts_on.isoformat(),
            "ends_on": ends_on.isoformat() if ends_on else None,
            "is_chronic": payload.is_chronic,
            "total_doses": total_doses,
        },
        request=request,
    )

    response = [_schedule_out(row) for row in rows]
    await db.commit()
    return response


async def generate_occurrences(
    db: AsyncSession,
    context: AuthContext,
    *,
    schedule_id: UUID,
    payload: GenerateOccurrencesRequest,
    request: Request,
) -> GenerationResult:
    """Materialize reminders forward, then stop the course when it is over.

    Idempotency comes from ``uq_reminder_occurrence``: every candidate instant
    is offered to Postgres with ``ON CONFLICT DO NOTHING`` and only the rows the
    database actually accepted advance ``doses_generated``. The row is locked
    ``FOR UPDATE`` so two concurrent runs cannot both advance the watermark.
    """
    schedule = await db.scalar(
        select(MedicationSchedule).where(MedicationSchedule.id == schedule_id).with_for_update()
    )
    if schedule is None:
        raise not_found("Medication schedule")
    await assert_may_read_patient(db, context, schedule.patient_user_id)
    if schedule.status == MedicationScheduleStatus.CANCELLED:
        raise conflict("Cannot generate reminders for a cancelled schedule")

    now = _now()
    zone = _zone(schedule.timezone)
    window_end = now + timedelta(hours=payload.horizon_hours)

    created = 0
    skipped = 0
    cancelled = 0

    if schedule.status == MedicationScheduleStatus.ACTIVE:
        horizon_day = window_end.astimezone(zone).date()
        start_day = (
            schedule.generated_through + timedelta(days=1)
            if schedule.generated_through is not None
            else schedule.starts_on
        )
        start_day = max(start_day, schedule.starts_on)
        end_day = min(schedule.ends_on, horizon_day) if schedule.ends_on else horizon_day

        remaining: int | None = None
        if schedule.total_doses is not None:
            remaining = max(schedule.total_doses - schedule.doses_generated, 0)

        days_mask = [str(day) for day in schedule.days_of_week]
        try:
            channel = NotificationChannel(str(schedule.channels[0]))
        except (IndexError, ValueError):
            channel = NotificationChannel.IN_APP

        candidates: list[dict[str, Any]] = []
        processed_through: date | None = None
        cursor = start_day
        while cursor <= end_day:
            if remaining is not None and len(candidates) >= remaining:
                break
            if len(candidates) >= MAX_OCCURRENCES_PER_RUN:
                break
            if not days_mask or DAY_CODES[cursor.weekday()] in days_mask:
                candidates.append(
                    {
                        "id": uuid4(),
                        "tenant_id": schedule.tenant_id,
                        "schedule_id": schedule.id,
                        "patient_user_id": schedule.patient_user_id,
                        "scheduled_at": _local_instant(cursor, schedule.time_local, zone),
                        "time_local": schedule.time_local,
                        "timezone": schedule.timezone,
                        "channel": channel,
                        "status": ReminderStatus.PENDING,
                        "attempts": 0,
                        "created_at": now,
                    }
                )
            processed_through = cursor
            cursor += timedelta(days=1)

        if candidates:
            insert_stmt = (
                pg_insert(MedicationReminderOccurrence)
                .values(candidates)
                .on_conflict_do_nothing(constraint="uq_reminder_occurrence")
                .returning(MedicationReminderOccurrence.id)
            )
            inserted = list((await db.execute(insert_stmt)).scalars().all())
            created = len(inserted)
            skipped = len(candidates) - created

        if processed_through is not None:
            schedule.generated_through = processed_through
        schedule.doses_generated += created

    # --- termination ------------------------------------------------------
    # The course boundary is the earlier of "the day after ends_on" and "just
    # after the final dose", whichever the schedule actually declares. Anything
    # still pending beyond it is cancelled so reminders cannot outlive the
    # course, and once the boundary is in the past the schedule is completed.
    boundaries: list[datetime] = []
    if schedule.ends_on is not None:
        boundaries.append(_local_instant(schedule.ends_on + timedelta(days=1), time(0, 0), zone))
    if schedule.total_doses is not None and schedule.doses_generated >= schedule.total_doses:
        last_dose = await db.scalar(
            select(func.max(MedicationReminderOccurrence.scheduled_at)).where(
                MedicationReminderOccurrence.schedule_id == schedule.id,
                MedicationReminderOccurrence.status != ReminderStatus.CANCELLED,
            )
        )
        if last_dose is not None:
            boundaries.append(last_dose + timedelta(microseconds=1))

    boundary = min(boundaries) if boundaries else None
    if boundary is not None:
        cancel_stmt = (
            update(MedicationReminderOccurrence)
            .where(
                MedicationReminderOccurrence.schedule_id == schedule.id,
                MedicationReminderOccurrence.status == ReminderStatus.PENDING,
                MedicationReminderOccurrence.scheduled_at >= boundary,
            )
            .values(status=ReminderStatus.CANCELLED)
            .returning(MedicationReminderOccurrence.id)
            .execution_options(synchronize_session=False)
        )
        cancelled = len(list((await db.execute(cancel_stmt)).scalars().all()))

    course_complete = boundary is not None and boundary <= now
    if course_complete and schedule.status == MedicationScheduleStatus.ACTIVE:
        schedule.status = MedicationScheduleStatus.COMPLETED

    await db.flush()

    await record_phi_access(
        db,
        context,
        patient_user_id=schedule.patient_user_id,
        resource_type="medication_reminder_occurrence",
        resource_id=schedule.id,
        result_count=created,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="medication_reminders.generated",
        subject_user_id=schedule.patient_user_id,
        resource_id=schedule.id,
        event_data={
            "created": created,
            "skipped": skipped,
            "cancelled": cancelled,
            "horizon_hours": payload.horizon_hours,
            "generated_through": (
                schedule.generated_through.isoformat() if schedule.generated_through else None
            ),
            "status": schedule.status.value,
        },
        request=request,
    )

    result = GenerationResult(
        schedule_id=schedule.id,
        status=schedule.status,
        created=created,
        skipped=skipped,
        cancelled=cancelled,
        generated_through=schedule.generated_through,
        doses_generated=schedule.doses_generated,
        total_doses=schedule.total_doses,
        window_end=window_end,
        course_complete=schedule.status == MedicationScheduleStatus.COMPLETED,
    )
    await db.commit()
    return result


# --------------------------------------------------------------------------
# Reminders and adherence
# --------------------------------------------------------------------------


def _reminder_row_out(row: Any) -> ReminderOut:
    return ReminderOut(
        id=row.id,
        schedule_id=row.schedule_id,
        patient_user_id=row.patient_user_id,
        medication_request_id=row.medication_request_id,
        scheduled_at=row.scheduled_at,
        time_local=row.time_local,
        timezone=row.timezone,
        status=row.status,
        channel=row.channel,
        sent_at=row.sent_at,
        attempts=row.attempts,
        medication_code=row.medication_code,
        medication_display=row.medication_display,
        dose_quantity=row.dose_quantity,
        dose_unit=row.dose_unit,
        route_code=row.route_code,
        sig_text=row.sig_text,
    )


async def list_reminders(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    window: ReminderWindow,
    days: int,
    page: Pagination,
    request: Request,
) -> Page[ReminderOut]:
    """Pending reminders for today (in each row's own zone) or the near future."""
    allowed = await _patient_scope(db, context, patient_user_id)
    occurrence = MedicationReminderOccurrence

    query = (
        select(
            occurrence.id,
            occurrence.schedule_id,
            occurrence.patient_user_id,
            occurrence.scheduled_at,
            occurrence.time_local,
            occurrence.timezone,
            occurrence.status,
            occurrence.channel,
            occurrence.sent_at,
            occurrence.attempts,
            MedicationSchedule.medication_request_id.label("medication_request_id"),
            MedicationRequest.medication_code,
            MedicationRequest.medication_display,
            MedicationDosageInstruction.dose_quantity,
            MedicationDosageInstruction.dose_unit,
            MedicationDosageInstruction.route_code,
            MedicationDosageInstruction.sig_text,
        )
        .join(MedicationSchedule, MedicationSchedule.id == occurrence.schedule_id)
        .join(MedicationRequest, MedicationRequest.id == MedicationSchedule.medication_request_id)
        .join(
            MedicationDosageInstruction,
            MedicationDosageInstruction.id == MedicationSchedule.dosage_instruction_id,
        )
        .where(
            occurrence.patient_user_id == patient_user_id,
            occurrence.status == ReminderStatus.PENDING,
        )
    )
    query = _scoped(query, occurrence, allowed)

    if window == "today":
        local_day = cast(func.timezone(occurrence.timezone, occurrence.scheduled_at), Date)
        today_local = cast(func.timezone(occurrence.timezone, func.now()), Date)
        query = query.where(local_day == today_local)
    else:
        now = _now()
        query = query.where(
            occurrence.scheduled_at > now,
            occurrence.scheduled_at <= now + timedelta(days=days),
        )

    query = (
        query.order_by(occurrence.scheduled_at, occurrence.id)
        .offset(page.offset)
        .limit(page.limit + 1)
    )

    rows = (await db.execute(query)).all()
    items = [_reminder_row_out(row) for row in rows]

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="medication_reminder_occurrence",
        result_count=min(len(items), page.limit),
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def acknowledge_reminder(
    db: AsyncSession,
    context: AuthContext,
    *,
    occurrence_id: UUID,
    payload: ReminderAck,
    request: Request,
) -> AckResult:
    """Record taken / skipped / snoozed against a reminder.

    The clinical assertion lands in the append-only
    ``medication_adherence_events`` table; the occurrence row only carries
    delivery state, so a snooze moves the fire time while taken and skipped
    close the reminder out.
    """
    occurrence = await db.scalar(
        select(MedicationReminderOccurrence)
        .where(MedicationReminderOccurrence.id == occurrence_id)
        .with_for_update()
    )
    if occurrence is None:
        raise not_found("Reminder")
    await assert_may_read_patient(db, context, occurrence.patient_user_id)

    target = (
        ReminderStatus.PENDING.value if payload.action == "snoozed" else ReminderStatus.SENT.value
    )
    assert_transition(occurrence.status.value, target, ACK_TRANSITIONS)

    if payload.action in ("taken", "skipped"):
        already = await db.scalar(
            select(MedicationAdherenceEvent.id).where(
                MedicationAdherenceEvent.occurrence_id == occurrence_id,
                MedicationAdherenceEvent.status.in_(
                    (AdherenceStatus.TAKEN, AdherenceStatus.SKIPPED)
                ),
            )
        )
        if already is not None:
            raise conflict("This dose has already been acknowledged")

    schedule = await db.scalar(
        select(MedicationSchedule).where(MedicationSchedule.id == occurrence.schedule_id)
    )
    if schedule is None:
        raise not_found("Medication schedule")

    now = _now()
    status = ACK_TO_ADHERENCE[payload.action]
    dose_quantity = payload.dose_taken_quantity
    dose_unit = payload.dose_unit
    if status == AdherenceStatus.TAKEN and dose_quantity is None:
        dosage = await db.scalar(
            select(MedicationDosageInstruction).where(
                MedicationDosageInstruction.id == schedule.dosage_instruction_id
            )
        )
        if dosage is not None:
            dose_quantity = dosage.dose_quantity
            dose_unit = dosage.dose_unit

    event = MedicationAdherenceEvent(
        tenant_id=occurrence.tenant_id,
        patient_user_id=occurrence.patient_user_id,
        schedule_id=occurrence.schedule_id,
        occurrence_id=occurrence.id,
        medication_request_id=schedule.medication_request_id,
        status=status,
        scheduled_at=occurrence.scheduled_at,
        recorded_at=now,
        taken_at=(payload.taken_at or now) if status == AdherenceStatus.TAKEN else None,
        dose_taken_quantity=dose_quantity if status == AdherenceStatus.TAKEN else None,
        dose_unit=dose_unit if status == AdherenceStatus.TAKEN else None,
        reported_by_user_id=context.user.id,
        reason_code=payload.reason_code,
        note=payload.note,
        created_at=now,
    )
    db.add(event)

    if payload.action == "snoozed":
        occurrence.scheduled_at = now + timedelta(minutes=payload.snooze_minutes)
        occurrence.attempts += 1
    else:
        occurrence.status = ReminderStatus.SENT
        if occurrence.sent_at is None:
            occurrence.sent_at = now

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("This acknowledgement conflicts with one already recorded") from exc

    await record_phi_access(
        db,
        context,
        patient_user_id=occurrence.patient_user_id,
        resource_type="medication_adherence_event",
        resource_id=occurrence.id,
        result_count=1,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="medication_reminder.acknowledged",
        subject_user_id=occurrence.patient_user_id,
        resource_id=occurrence.id,
        event_data={"action": payload.action, "schedule_id": str(occurrence.schedule_id)},
        request=request,
    )

    result = AckResult(
        occurrence_id=occurrence.id,
        occurrence_status=occurrence.status,
        scheduled_at=occurrence.scheduled_at,
        event=_adherence_event_out(event),
    )
    await db.commit()
    return result


async def adherence_report(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    days: int,
    request: Request,
) -> AdherenceReport:
    """Per-medication taken/expected over a window, aggregated by Postgres.

    Expected doses are the occurrences already due in the window that were
    neither cancelled (past the end of the course) nor suppressed, so a course
    that finished early does not drag the rate down.
    """
    allowed = await _patient_scope(db, context, patient_user_id)

    now = _now()
    window_start = now - timedelta(days=days)
    occurrence = MedicationReminderOccurrence
    event = MedicationAdherenceEvent

    expected = func.count(distinct(occurrence.id))
    taken = func.count(distinct(occurrence.id)).filter(event.status == AdherenceStatus.TAKEN)
    skipped = func.count(distinct(occurrence.id)).filter(
        event.status.in_((AdherenceStatus.SKIPPED, AdherenceStatus.NOT_TAKEN))
    )
    rate = func.coalesce(
        func.round(cast(taken, Numeric(12, 6)) / func.nullif(expected, 0), 4),
        0,
    )

    query = (
        select(
            MedicationRequest.id,
            MedicationRequest.medication_code,
            MedicationRequest.medication_display,
            expected.label("expected_doses"),
            taken.label("taken_doses"),
            skipped.label("skipped_doses"),
            rate.label("adherence_rate"),
        )
        .join(MedicationSchedule, MedicationSchedule.id == occurrence.schedule_id)
        .join(MedicationRequest, MedicationRequest.id == MedicationSchedule.medication_request_id)
        .outerjoin(event, event.occurrence_id == occurrence.id)
        .where(
            occurrence.patient_user_id == patient_user_id,
            occurrence.scheduled_at >= window_start,
            occurrence.scheduled_at <= now,
            occurrence.status.notin_(NON_EXPECTED_STATUSES),
        )
        .group_by(
            MedicationRequest.id,
            MedicationRequest.medication_code,
            MedicationRequest.medication_display,
        )
        .order_by(MedicationRequest.medication_display)
    )
    query = _scoped(query, occurrence, allowed)

    rows = (await db.execute(query)).all()
    items = [
        AdherenceRow(
            medication_request_id=row[0],
            medication_code=row[1],
            medication_display=row[2],
            expected_doses=row[3],
            taken_doses=row[4],
            skipped_doses=row[5],
            missed_doses=max(row[3] - row[4] - row[5], 0),
            adherence_rate=Decimal(row[6]),
        )
        for row in rows
    ]

    total_expected = sum(item.expected_doses for item in items)
    total_taken = sum(item.taken_doses for item in items)
    overall = (
        (Decimal(total_taken) / Decimal(total_expected)).quantize(Decimal("0.0001"))
        if total_expected
        else Decimal("0.0000")
    )

    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="medication_adherence_event",
        result_count=len(items),
        request=request,
    )
    await db.commit()

    return AdherenceReport(
        patient_user_id=patient_user_id,
        window_start=window_start,
        window_end=now,
        days=days,
        expected_doses=total_expected,
        taken_doses=total_taken,
        adherence_rate=overall,
        items=items,
    )


__all__ = [
    "AckResult",
    "AdherenceReport",
    "AdherenceRow",
    "GenerateOccurrencesRequest",
    "GenerationResult",
    "MedicationStatementOut",
    "PrescriptionCreate",
    "PrescriptionOut",
    "ReminderAck",
    "ReminderOut",
    "SafetyCheckBatch",
    "SafetyCheckOut",
    "ScheduleCreate",
    "ScheduleOut",
    "acknowledge_reminder",
    "adherence_report",
    "create_prescription",
    "create_schedule",
    "generate_occurrences",
    "list_current_medications",
    "list_prescriptions",
    "list_reminders",
    "record_safety_checks",
]
