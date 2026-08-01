"""One coherent patient journey across every table migration 0009 created.

``seed_reference`` loads ground truth (terminologies, WHO curves, a chargemaster)
and ``seed_demo`` creates the five demo accounts and their portal records. Both
leave the normalised clinical and insurance tables empty, so the endpoints built
on them return nothing: availability search finds no slots, the percentile chart
has no points, the adherence view has no doses, and the coverage explainer has no
benefit to explain.

This module fills that gap with a single, internally consistent story about the
existing demo patient (``PATDEMO00000001``, Maya Patel), rather than with
unrelated rows per table. Every foreign key points at a row this module or an
earlier seeder actually created, and the numbers reconcile: the claim's patient
responsibility is the invoice total, the cost estimate's deductible line is the
accumulator's remaining balance, and the loyalty ledger's ``balance_after``
column is a running sum of its own ``points`` column.

The story
---------
Maya is 35. Her childhood growth points and immunisation series were imported
from a previous provider. She has two active problems: essential hypertension
(ICD-10-CM I10), managed in Internal Medicine by Dr. Amara Okafor, and primary
osteoarthritis of the right knee (M17.11), managed in Orthopaedics by
Dr. Elena Rodriguez, the existing demo doctor. Three years of blood pressures
trend down as treatment is titrated. At her most recent visit lisinopril was
started; the follow-up metabolic panel came back with a potassium of
6.8 mmol/L — a critical result nobody has acknowledged yet, which is why a
severity-2 support case is open. On the insurance side her knee has generated a
denied MRI claim (no precertification), a pending prior authorisation for a
repeat scan, an approved authorisation for arthroscopy, and a cost estimate for
the surgery that prices off her partially met deductible.

Codes
-----
No clinical code here is invented. ICD-10-CM, CPT, LOINC and CVX codes are
resolved against the ``code_concepts`` rows ``seed_reference`` loaded, so a typo
raises instead of writing an unresolvable string. Three vocabularies are used
that ``seed_reference`` does not load, and are therefore written as code plus
display with a null ``*_concept_id``:

``RxNorm``
    ``314076`` — lisinopril 10 MG Oral Tablet (SCD), the clinical-drug form.
``SNOMED CT``
    Allergy substances (``373270004`` penicillins, ``762952008`` peanut),
    manifestations (``126485001`` urticaria, ``39579001`` anaphylaxis,
    ``422587007`` nausea), routes (``78421000`` intramuscular, ``34206005``
    subcutaneous, ``26643006`` oral) and sites (``368208006`` left upper arm,
    ``61396006`` left thigh).
``X12 CARC``
    ``197`` — "precertification/authorization/notification absent", the denial
    reason on the MRI claim.

Determinism and idempotency
---------------------------
Every row has a UUID derived from :func:`healthos_api.cli.seed_demo.demo_id`
under a ``journey:`` prefix, and every write is keyed on that primary key. Rows
on append-only tables (``claim_events``, ``appointment_status_events``,
``medication_adherence_events``, ``loyalty_ledger``, ``phi_access_events``,
``prescription_safety_checks``) and signed ``clinical_notes`` are inserted once
and never updated, because the database has triggers that reject the update.

All timestamps derive from *today's date* plus fixed offsets, never from the
current instant, so two runs on the same day write byte-identical values. The
rolling capacity window (appointment and lab slots for the next 30 days) does
move forward on a later day, which is the intended behaviour for a demo
environment.

Randomness
----------
There is none. Plausible variation in vitals comes from ``_wobble``, a SHA-256
digest of a row key folded into a small integer range, so the same row always
gets the same jitter.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.cli.seed_demo import demo_id
from healthos_api.cli.seed_reference import CPT, CVX, ICD10CM, LOINC
from healthos_api.config import get_settings
from healthos_api.db.base import Base
from healthos_api.db.models import (
    AccumulatorType,
    AdherenceStatus,
    AllergyCategory,
    AllergyIntolerance,
    AllergyReaction,
    AllergyType,
    AllergyVerificationStatus,
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    AppointmentStatusEvent,
    AsserterType,
    BenefitAccumulator,
    BenefitExplanation,
    BenefitLimitPeriod,
    BiologicalSex,
    CertificateStatus,
    Claim,
    ClaimEvent,
    ClaimLine,
    ClaimStatus,
    ClaimType,
    ClinicalNote,
    ClinicalStatus,
    CodeConcept,
    CodeSystem,
    CodeType,
    CommentVisibility,
    Condition,
    ConditionCategory,
    CostEstimate,
    Criticality,
    Department,
    DoctorProfile,
    EncounterChannel,
    EncounterClass,
    EncounterCode,
    EncounterDiagnosis,
    EncounterStatus,
    GrowthMeasure,
    GrowthMeasurement,
    GrowthReferenceStandard,
    GrowthSource,
    Immunization,
    ImmunizationCertificate,
    ImmunizationStatus,
    InsurancePlan,
    InsuranceProduct,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    LabFacility,
    LabOrder,
    LabOrderStatus,
    LabOrderTest,
    LabPriority,
    LabResult,
    LabSlot,
    LabSlotTest,
    LabTest,
    LoyaltyAccount,
    LoyaltyEntryType,
    LoyaltyLedgerEntry,
    MedicationAdherenceEvent,
    MedicationDosageInstruction,
    MedicationRequest,
    MedicationRequestIntent,
    MedicationRequestStatus,
    MedicationSchedule,
    MedicationScheduleStatus,
    MedicationReminderOccurrence,
    MemberRelationship,
    NetworkTier,
    NoteStatus,
    NotificationChannel,
    ObservationStatus,
    Organization,
    PatientAllergyStatus,
    PatientCommunicationPreference,
    PatientProfile,
    PayerContractRate,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PhiAccessAction,
    PhiAccessEvent,
    PlanBenefit,
    Policy,
    PolicyMember,
    PolicyStatus,
    PractitionerRole,
    PremiumFrequency,
    PremiumSchedule,
    Prescription,
    PrescriptionSafetyCheck,
    PrescriptionStatus,
    PriorAuthorization,
    PriorAuthStatus,
    ProvenanceSource,
    ProviderSchedule,
    Refund,
    RefundStatus,
    ReactionSeverity,
    ReminderStatus,
    ReviewStatus,
    SafetyCheckOutcome,
    SafetyCheckType,
    ServiceItem,
    SlotStatus,
    Specimen,
    SupportCase,
    SupportCaseComment,
    SupportCaseEvent,
    SupportSeverity,
    SupportStatus,
    User,
    UserStatus,
    VerificationStatus,
    VitalSign,
    VitalSignComponent,
)
from healthos_api.db.session import create_database_engine, create_session_factory
from healthos_api.domain.clinical import _lms_zscore, _zscore_to_percentile

# --------------------------------------------------------------------------------------
# Vocabularies this module uses that seed_reference does not load
# --------------------------------------------------------------------------------------

RXNORM: Final = "http://www.nlm.nih.gov/research/umls/rxnorm"
SNOMED: Final = "http://snomed.info/sct"
CARC: Final = "https://x12.org/codes/claim-adjustment-reason-codes"

ROUTE_IM: Final = ("78421000", "Intramuscular route")
ROUTE_SC: Final = ("34206005", "Subcutaneous route")
ROUTE_PO: Final = ("26643006", "Oral route")
SITE_ARM: Final = ("368208006", "Left upper arm structure")
SITE_THIGH: Final = ("61396006", "Left thigh structure")

CURRENCY: Final = "USD"
ZONE: Final = ZoneInfo("America/Phoenix")
TIMEZONE_NAME: Final = "America/Phoenix"

# Negotiated allowed amount as a share of the chargemaster price. One number for
# the whole contract keeps every derived figure (claims, estimates, invoices)
# reproducible by hand.
CONTRACT_SHARE: Final = Decimal("0.68")

PATIENT_MRN: Final = "PATDEMO00000001"
CONTRACT_FROM: Final = date(2026, 1, 1)
BENEFIT_YEAR: Final = 2026
PLAN_YEAR_FROM: Final = date(2026, 1, 1)
PLAN_YEAR_TO: Final = date(2026, 12, 31)


def journey_id(name: str) -> UUID:
    """Deterministic id, reusing the demo namespace under a ``journey:`` prefix."""
    return demo_id(f"journey:{name}")


def _wobble(key: str, span: int) -> int:
    """Reproducible pseudo-variation in ``[-span, span]`` derived from a row key."""
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2 * span + 1) - span


def _cents(value: Decimal | int) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _allowed(base_price_cents: int) -> int:
    return _cents(Decimal(base_price_cents) * CONTRACT_SHARE)


def _money(cents: int) -> str:
    """Render cents the way a member statement would: ``$1,234`` or ``$12.50``."""
    if cents % 100 == 0:
        return f"${cents // 100:,}"
    return f"${cents / 100:,.2f}"


def _add_months(anchor: date, months: int) -> date:
    """Calendar month arithmetic that clamps to the end of a short month."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    if month == 12:
        last_day = 31
    else:
        last_day = (date(year, month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(anchor.day, last_day))


def _local(day: date, at: time) -> datetime:
    """A wall-clock time in the clinic's timezone, expressed in UTC."""
    return datetime.combine(day, at, tzinfo=ZONE).astimezone(UTC)


async def _upsert[M: Base](session: AsyncSession, model: type[M], row_id: UUID, /, **fields: Any) -> M:
    """Insert the row if missing, otherwise refresh every supplied field."""
    row = await session.get(model, row_id)
    if row is None:
        row = model(id=row_id, **fields)
        session.add(row)
        return row
    for key, value in fields.items():
        setattr(row, key, value)
    return row


async def _insert_once[M: Base](
    session: AsyncSession, model: type[M], row_id: UUID, /, **fields: Any
) -> M:
    """Insert the row if missing and never touch it again.

    Used for the append-only log tables and for signed clinical notes: the
    database has BEFORE UPDATE triggers that raise on any attempt to change them.
    """
    row = await session.get(model, row_id)
    if row is not None:
        return row
    row = model(id=row_id, **fields)
    session.add(row)
    return row


# --------------------------------------------------------------------------------------
# Cast of characters
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StaffSpec:
    key: str
    first_name: str
    last_name: str
    email: str
    license_number: str
    jurisdiction: str
    specialty: str
    phone: str


# The existing demo doctor (Dr. Rodriguez) is reused as the orthopaedic surgeon.
# A clinic needs more than one clinician for a capacity story, so two additional
# practitioners are created here; they are staff records, not login personas.
STAFF: Final[tuple[StaffSpec, ...]] = (
    StaffSpec(
        key="okafor",
        first_name="Amara",
        last_name="Okafor",
        email="amara.okafor@desertvalley.example.com",
        license_number="AZ-MD-771043",
        jurisdiction="Arizona",
        specialty="Internal Medicine",
        phone="+14805550111",
    ),
    StaffSpec(
        key="whitfield",
        first_name="Daniel",
        last_name="Whitfield",
        email="daniel.whitfield@desertvalley.example.com",
        license_number="AZ-MD-663118",
        jurisdiction="Arizona",
        specialty="Internal Medicine",
        phone="+14805550112",
    ),
)


@dataclass(frozen=True)
class DepartmentSpec:
    code: str
    name: str
    cost_center: str


DEPARTMENTS: Final[tuple[DepartmentSpec, ...]] = (
    DepartmentSpec("IM", "Internal Medicine", "CC-4100"),
    DepartmentSpec("ORTHO", "Orthopaedics", "CC-4200"),
    DepartmentSpec("LAB", "Laboratory Medicine", "CC-4300"),
)

# CPT prefixes that belong to each department in the chargemaster.
LAB_CPT: Final = frozenset(
    {"80053", "85025", "80061", "83036", "82947", "82565", "84520", "84443", "85610", "81002", "36415"}
)
ORTHO_CPT: Final = frozenset({"27447", "29881", "01402", "20610", "97110", "73721"})


# --------------------------------------------------------------------------------------
# Capacity
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleSpec:
    key: str
    provider: str
    department: str
    day_of_week: int  # 0 = Monday, matching datetime.date.weekday()
    start: time
    end: time
    channel: EncounterChannel


SCHEDULES: Final[tuple[ScheduleSpec, ...]] = (
    ScheduleSpec("okafor-mon", "okafor", "IM", 0, time(8, 0), time(12, 0), EncounterChannel.IN_PERSON),
    ScheduleSpec("okafor-wed", "okafor", "IM", 2, time(13, 0), time(17, 0), EncounterChannel.IN_PERSON),
    ScheduleSpec(
        "rodriguez-tue", "rodriguez", "ORTHO", 1, time(9, 0), time(12, 0), EncounterChannel.IN_PERSON
    ),
    ScheduleSpec(
        "rodriguez-thu", "rodriguez", "ORTHO", 3, time(9, 0), time(12, 0), EncounterChannel.IN_PERSON
    ),
    ScheduleSpec(
        "whitfield-mon", "whitfield", "IM", 0, time(13, 0), time(17, 0), EncounterChannel.IN_PERSON
    ),
    ScheduleSpec(
        "whitfield-fri", "whitfield", "IM", 4, time(9, 0), time(12, 0), EncounterChannel.TELEHEALTH
    ),
)

SLOT_MINUTES: Final = 30
CAPACITY_DAYS: Final = 30
SLOT_PRICE_CENTS: Final = 16500

# Tests bookable in every lab slot, by LOINC code.
LAB_SLOT_TESTS: Final = ("58410-2", "24323-8", "51990-0", "57698-3", "4548-4", "3016-3")


# --------------------------------------------------------------------------------------
# Childhood growth
# --------------------------------------------------------------------------------------

DAYS_PER_MONTH: Final = Decimal("30.4375")

# Maya tracked a little above the median through infancy and settled onto it.
GROWTH_MONTHS: Final[tuple[tuple[int, str, str], ...]] = (
    # (age in months, weight-for-age z, height-for-age z)
    (0, "0.30", "0.15"),
    (2, "0.42", "0.22"),
    (4, "0.55", "0.30"),
    (6, "0.61", "0.34"),
    (9, "0.58", "0.36"),
    (12, "0.52", "0.35"),
    (15, "0.47", "0.33"),
    (18, "0.44", "0.31"),
    (24, "0.38", "0.28"),
    (30, "0.33", "0.26"),
    (36, "0.29", "0.24"),
    (48, "0.22", "0.20"),
    (60, "0.18", "0.17"),
)


# --------------------------------------------------------------------------------------
# Immunisations
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DoseSpec:
    cvx: str
    series: str
    dose: int
    expected: int
    months: int | None = None
    on: date | None = None
    ml: str = "0.5"
    route: tuple[str, str] = ROUTE_IM
    site: tuple[str, str] | None = SITE_THIGH
    imported: bool = True
    next_due: date | None = None
    booster_of: str | None = None


def _child(cvx: str, series: str, expected: int, schedule: Iterable[int], **kw: Any) -> tuple[DoseSpec, ...]:
    return tuple(
        DoseSpec(cvx=cvx, series=series, dose=index, expected=expected, months=months, **kw)
        for index, months in enumerate(schedule, start=1)
    )


DOSES: Final[tuple[DoseSpec, ...]] = (
    *_child("08", "Hepatitis B", 3, (0, 2, 6)),
    *_child("116", "Rotavirus", 3, (2, 4, 6), ml="2", route=ROUTE_PO, site=None),
    *_child("20", "DTaP", 5, (2, 4, 6, 15, 48)),
    *_child("49", "Hib", 3, (2, 4, 12)),
    *_child("133", "Pneumococcal conjugate", 4, (2, 4, 6, 12)),
    *_child("10", "IPV", 4, (2, 4, 6, 48)),
    *_child("03", "MMR", 2, (12, 48), route=ROUTE_SC),
    *_child("21", "Varicella", 2, (12, 48), route=ROUTE_SC),
    DoseSpec("62", "HPV", 1, 3, on=date(2007, 9, 11), site=SITE_ARM),
    DoseSpec("62", "HPV", 2, 3, on=date(2007, 11, 13), site=SITE_ARM),
    DoseSpec("62", "HPV", 3, 3, on=date(2008, 3, 18), site=SITE_ARM),
    DoseSpec("115", "Tdap", 1, 2, on=date(2003, 5, 12), site=SITE_ARM),
    DoseSpec(
        "115",
        "Tdap",
        2,
        2,
        on=date(2023, 3, 14),
        site=SITE_ARM,
        imported=False,
        next_due=date(2033, 3, 14),
        booster_of="115:Tdap:1",
    ),
    DoseSpec("213", "COVID-19", 1, 3, on=date(2021, 3, 6), site=SITE_ARM, imported=False),
    DoseSpec("213", "COVID-19", 2, 3, on=date(2021, 3, 27), site=SITE_ARM, imported=False),
    DoseSpec(
        "213",
        "COVID-19",
        3,
        3,
        on=date(2023, 10, 21),
        site=SITE_ARM,
        imported=False,
        booster_of="213:COVID-19:2",
    ),
    DoseSpec(
        "88",
        "Influenza 2025-2026",
        1,
        1,
        on=date(2025, 10, 8),
        site=SITE_ARM,
        imported=False,
        next_due=date(2026, 10, 1),
    ),
)

CERTIFIED_DOSES: Final = ("88:Influenza 2025-2026:1", "213:COVID-19:3")


# --------------------------------------------------------------------------------------
# Encounters
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EncounterSpec:
    key: str
    provider: str
    department: str
    on: date | None
    day_offset: int | None
    reason: str
    location: str
    note_type: str
    note_title: str
    note: str
    diagnoses: tuple[tuple[str, bool], ...]  # (icd-10 code, is_principal)
    procedures: tuple[str, ...]  # cpt codes


ENCOUNTERS: Final[tuple[EncounterSpec, ...]] = (
    EncounterSpec(
        key="2023-annual",
        provider="okafor",
        department="IM",
        on=date(2023, 9, 12),
        day_offset=None,
        reason="New patient annual examination",
        location="Desert Valley Medical Plaza, Internal Medicine, Suite 210",
        note_type="34117-2",
        note_title="History and physical — new patient annual examination",
        note=(
            "## Subjective\n"
            "32-year-old woman establishing primary care. No current medications. Reports "
            "occasional headaches over the past six months, usually late in the day. Family "
            "history of type 2 diabetes in her mother, diagnosed at 52.\n\n"
            "## Objective\n"
            "Blood pressure 152/96 in the right arm, seated, repeated after five minutes at "
            "150/94. Heart rate 78 and regular. Weight 71.5 kg, height 167 cm. Heart sounds "
            "normal, no murmur. Lungs clear. No peripheral oedema. Fundoscopy without "
            "hypertensive changes.\n\n"
            "## Assessment\n"
            "Stage 2 hypertension on two readings at a single visit, previously undiagnosed. "
            "No evidence of end-organ damage today. Otherwise well.\n\n"
            "## Plan\n"
            "Comprehensive metabolic panel, lipid panel and complete blood count ordered to "
            "establish a baseline before starting therapy. Home blood-pressure log discussed "
            "and the cuff technique demonstrated. Reduce sodium, aim for 150 minutes of "
            "activity a week. Return in five months, sooner if home readings stay above "
            "160 systolic."
        ),
        diagnoses=(("Z00.00", True), ("I10", False)),
        procedures=("99204",),
    ),
    EncounterSpec(
        key="2024-bp-followup",
        provider="okafor",
        department="IM",
        on=date(2024, 2, 6),
        day_offset=None,
        reason="Hypertension follow-up",
        location="Desert Valley Medical Plaza, Internal Medicine, Suite 210",
        note_type="11506-0",
        note_title="Progress note — hypertension follow-up",
        note=(
            "## Subjective\n"
            "Returns with a five-month home log. Morning readings mostly 143-149 systolic. "
            "Has cut back on takeaway meals and walks three evenings a week. Headaches less "
            "frequent. No chest pain, no shortness of breath.\n\n"
            "## Objective\n"
            "Blood pressure 146/92. Heart rate 76. Weight 70.8 kg, down 0.7 kg. Cardiovascular "
            "and respiratory examination unchanged.\n\n"
            "## Assessment\n"
            "Hypertension improving with lifestyle change but still above the 130/80 target.\n\n"
            "## Plan\n"
            "Continue lifestyle measures for one more interval given the clear downward trend "
            "and her preference to avoid medication for now. Explicitly agreed that if the "
            "average stays above 140/90 at the next review we will start an ACE inhibitor. "
            "Keep logging. Review in six months."
        ),
        diagnoses=(("I10", True),),
        procedures=("99213",),
    ),
    EncounterSpec(
        key="2024-knee",
        provider="rodriguez",
        department="ORTHO",
        on=date(2024, 8, 20),
        day_offset=None,
        reason="Right knee pain",
        location="Desert Valley Medical Plaza, Orthopaedics, Suite 310",
        note_type="11488-4",
        note_title="Consultation note — right knee pain",
        note=(
            "## Subjective\n"
            "Referred by Dr. Okafor. Eighteen months of right knee pain, medial, worse going "
            "downstairs and after long periods of sitting. Morning stiffness lasting about "
            "fifteen minutes. No locking, no giving way, no injury she can recall.\n\n"
            "## Objective\n"
            "Antalgic gait on the right. Small effusion. Medial joint line tenderness. Range "
            "of motion 5-130 degrees. Ligaments stable. McMurray equivocal. Weight-bearing "
            "radiographs show medial compartment joint space narrowing with osteophytes; "
            "Kellgren-Lawrence grade 2.\n\n"
            "## Assessment\n"
            "Primary osteoarthritis of the right knee, medial compartment.\n\n"
            "## Plan\n"
            "Intra-articular corticosteroid injection performed today with informed consent, "
            "aseptic technique, no immediate complication. Referred to physical therapy for a "
            "quadriceps and hip abductor programme. Discussed that surgery is not the first "
            "step and that most people improve with strengthening. Review in three months."
        ),
        diagnoses=(("M17.11", True),),
        procedures=("99203", "20610"),
    ),
    EncounterSpec(
        key="2025-uri",
        provider="okafor",
        department="IM",
        on=date(2025, 3, 11),
        day_offset=None,
        reason="Cough and sore throat",
        location="Desert Valley Medical Plaza, Internal Medicine, Suite 210",
        note_type="11506-0",
        note_title="Progress note — acute upper respiratory infection",
        note=(
            "## Subjective\n"
            "Four days of sore throat, nasal congestion and a dry cough. No fever measured at "
            "home. No shortness of breath. Two colleagues unwell with the same thing.\n\n"
            "## Objective\n"
            "Temperature 37.1 C. Oxygen saturation 98% on room air. Respiratory rate 16. "
            "Pharynx mildly erythematous without exudate. No cervical lymphadenopathy. Chest "
            "clear. Centor score 1.\n\n"
            "## Assessment\n"
            "Viral upper respiratory infection.\n\n"
            "## Plan\n"
            "No antibiotic indicated and the reasoning was explained; she agreed. Fluids, "
            "rest, paracetamol as needed. Safety-netting given: return for fever above 38.5 C "
            "for more than three days, breathlessness, or symptoms beyond ten days. Note her "
            "documented penicillin allergy, so any future indicated antibiotic must be "
            "non-beta-lactam."
        ),
        diagnoses=(("J06.9", True),),
        procedures=("99212",),
    ),
    EncounterSpec(
        key="2025-annual",
        provider="okafor",
        department="IM",
        on=date(2025, 10, 14),
        day_offset=None,
        reason="Annual examination",
        location="Desert Valley Medical Plaza, Internal Medicine, Suite 210",
        note_type="34117-2",
        note_title="History and physical — annual examination",
        note=(
            "## Subjective\n"
            "Annual review. Knee is better since physical therapy; she does the home programme "
            "most weeks. Home blood pressures average 138/86 over the last month. Influenza "
            "vaccine given at this visit.\n\n"
            "## Objective\n"
            "Blood pressure 138/86, repeated 136/84. Heart rate 74. Weight 69.1 kg, BMI 24.8. "
            "Electrocardiogram: sinus rhythm, no left ventricular hypertrophy, no ischaemic "
            "change. Right knee with mild crepitus, full extension, flexion to 135 degrees.\n\n"
            "## Assessment\n"
            "Hypertension, still above target after two years of lifestyle management. "
            "Osteoarthritis of the right knee, improved. Lipids borderline on the last panel.\n\n"
            "## Plan\n"
            "Repeat lipid panel and HbA1c today. Agreed to start an antihypertensive at the "
            "next visit once the labs are back. Continue the knee programme. Influenza "
            "vaccination administered, left deltoid."
        ),
        diagnoses=(("Z00.00", True), ("I10", False), ("M17.11", False)),
        procedures=("99214", "93000"),
    ),
    EncounterSpec(
        key="latest-bp",
        provider="okafor",
        department="IM",
        on=None,
        day_offset=-9,
        reason="Hypertension — initiate pharmacotherapy",
        location="Desert Valley Medical Plaza, Internal Medicine, Suite 210",
        note_type="11506-0",
        note_title="Progress note — starting lisinopril for hypertension",
        note=(
            "## Subjective\n"
            "Here to start treatment as agreed. Home average over the past fortnight is "
            "141/88 despite consistent lifestyle measures. No cough, no angio-oedema history, "
            "not pregnant and not planning pregnancy; contraception discussed. Documented "
            "penicillin and peanut allergies reviewed with her today and re-confirmed.\n\n"
            "## Objective\n"
            "Blood pressure 140/88, repeated 138/86. Heart rate 72. Weight 68.4 kg. No oedema. "
            "Chest clear.\n\n"
            "## Assessment\n"
            "Essential hypertension requiring pharmacological treatment. Knee osteoarthritis "
            "stable and not limiting activity.\n\n"
            "## Plan\n"
            "Start lisinopril 10 mg once daily in the morning. Counselled on dry cough, "
            "dizziness on standing for the first week, and to stop and call immediately if "
            "she notices lip or tongue swelling. Comprehensive metabolic panel in one week to "
            "check potassium and creatinine — this is not optional and the reason was "
            "explained. Daily reminder set for 08:00. Review in four weeks with her home log."
        ),
        diagnoses=(("I10", True), ("M17.11", False)),
        procedures=("99214", "36415", "80053"),
    ),
)


# --------------------------------------------------------------------------------------
# Vitals
# --------------------------------------------------------------------------------------

VITAL_INTERVAL_DAYS: Final = 45
VITAL_POINTS: Final = 24


# --------------------------------------------------------------------------------------
# Laboratory
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultSpec:
    loinc: str
    display: str
    value: str
    unit: str
    low: str | None
    high: str | None
    interpretation: str
    critical: bool = False


CMP_BASELINE: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("2951-2", "Sodium", "140", "mmol/L", "135", "145", "N"),
    ResultSpec("2823-3", "Potassium", "4.1", "mmol/L", "3.5", "5.1", "N"),
    ResultSpec("2075-0", "Chloride", "103", "mmol/L", "98", "107", "N"),
    ResultSpec("2028-9", "Carbon dioxide", "26", "mmol/L", "22", "29", "N"),
    ResultSpec("2345-7", "Glucose", "92", "mg/dL", "70", "99", "N"),
    ResultSpec("3094-0", "Urea nitrogen", "14", "mg/dL", "7", "20", "N"),
    ResultSpec("2160-0", "Creatinine", "0.86", "mg/dL", "0.59", "1.04", "N"),
    ResultSpec("17861-6", "Calcium", "9.4", "mg/dL", "8.6", "10.2", "N"),
)

LIPIDS_BASELINE: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("2093-3", "Cholesterol, total", "212", "mg/dL", None, "200", "H"),
    ResultSpec("2085-9", "HDL cholesterol", "54", "mg/dL", "50", None, "N"),
    ResultSpec("2089-1", "LDL cholesterol", "131", "mg/dL", None, "100", "H"),
    ResultSpec("2571-8", "Triglycerides", "136", "mg/dL", None, "150", "N"),
)

CBC_BASELINE: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("718-7", "Hemoglobin", "13.4", "g/dL", "12.0", "15.5", "N"),
    ResultSpec("6690-2", "White blood cell count", "6.2", "10*3/uL", "4.0", "11.0", "N"),
    ResultSpec("777-3", "Platelet count", "268", "10*3/uL", "150", "400", "N"),
)

LIPIDS_RECENT: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("2093-3", "Cholesterol, total", "204", "mg/dL", None, "200", "H"),
    ResultSpec("2085-9", "HDL cholesterol", "57", "mg/dL", "50", None, "N"),
    ResultSpec("2089-1", "LDL cholesterol", "124", "mg/dL", None, "100", "H"),
    ResultSpec("2571-8", "Triglycerides", "118", "mg/dL", None, "150", "N"),
)

A1C_RECENT: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("4548-4", "Hemoglobin A1c", "5.6", "%", None, "5.7", "N"),
)

# The headline abnormal result: hyperkalaemia one week after starting an ACE
# inhibitor. Left unacknowledged on purpose so the critical-results queue and the
# severity-2 support case both have something real to point at.
CMP_CRITICAL: Final[tuple[ResultSpec, ...]] = (
    ResultSpec("2951-2", "Sodium", "137", "mmol/L", "135", "145", "N"),
    ResultSpec("2823-3", "Potassium", "6.8", "mmol/L", "3.5", "5.1", "HH", critical=True),
    ResultSpec("2075-0", "Chloride", "101", "mmol/L", "98", "107", "N"),
    ResultSpec("2028-9", "Carbon dioxide", "23", "mmol/L", "22", "29", "N"),
    ResultSpec("2345-7", "Glucose", "96", "mg/dL", "70", "99", "N"),
    ResultSpec("3094-0", "Urea nitrogen", "22", "mg/dL", "7", "20", "H"),
    ResultSpec("2160-0", "Creatinine", "1.12", "mg/dL", "0.59", "1.04", "H"),
    ResultSpec("17861-6", "Calcium", "9.2", "mg/dL", "8.6", "10.2", "N"),
    ResultSpec("1751-7", "Albumin", "4.2", "g/dL", "3.5", "5.0", "N"),
    ResultSpec("1742-6", "Alanine aminotransferase", "22", "U/L", "7", "35", "N"),
)


# --------------------------------------------------------------------------------------
# Insurance
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanSpec:
    key: str
    product: str
    plan_code: str
    name: str
    metal: str
    premium_cents: int
    deductible_cents: int
    family_deductible_cents: int
    oop_cents: int
    family_oop_cents: int


PRODUCTS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    # (key, code, name, product_type, network name)
    ("choice", "SUN-CHOICE", "Sunrise Choice", "ppo", "Sunrise Choice Statewide Network"),
    ("essential", "SUN-ESSENTIAL", "Sunrise Essential", "hmo", "Sunrise Essential Metro Network"),
)

PLANS: Final[tuple[PlanSpec, ...]] = (
    PlanSpec("bronze", "essential", "ESS-BRZ-26", "Sunrise Essential Bronze HMO", "bronze",
             24800, 700000, 1400000, 900000, 1800000),
    PlanSpec("silver", "choice", "CHO-SLV-26", "Sunrise Choice Silver PPO", "silver",
             41800, 250000, 500000, 700000, 1400000),
    PlanSpec("gold", "choice", "CHO-GLD-26", "Sunrise Choice Gold PPO", "gold",
             58900, 100000, 200000, 450000, 900000),
    PlanSpec("platinum", "choice", "CHO-PLT-26", "Sunrise Choice Platinum PPO", "platinum",
             76500, 0, 0, 300000, 600000),
)

MEMBER_PLAN: Final = "silver"


@dataclass(frozen=True)
class CategorySpec:
    key: str
    service_code: str | None
    example_billed_cents: int
    deductible_applies: bool
    prior_auth: bool
    visit_limit: int | None
    limit_period: BenefitLimitPeriod | None
    out_of_network_covered: bool
    out_of_network_coinsurance: dict[str, int] | None
    exclusion_text: str | None


# copay (or coinsurance) per plan key; a category uses exactly one of the two.
COPAYS: Final[dict[str, dict[str, int]]] = {
    "primary_care": {"bronze": 4500, "silver": 3000, "gold": 2000, "platinum": 1500},
    "specialist": {"bronze": 8500, "silver": 5500, "gold": 4000, "platinum": 3000},
    "urgent_care": {"bronze": 7500, "silver": 5000, "gold": 3500, "platinum": 2500},
    "emergency_room": {"bronze": 100000, "silver": 75000, "gold": 50000, "platinum": 35000},
    "generic_drugs": {"bronze": 2500, "silver": 1500, "gold": 1000, "platinum": 500},
    "mental_health": {"bronze": 4500, "silver": 3000, "gold": 2000, "platinum": 1500},
    "physical_therapy": {"bronze": 6500, "silver": 4000, "gold": 3000, "platinum": 2000},
}

COINSURANCE: Final[dict[str, dict[str, int]]] = {
    "inpatient_hospital": {"bronze": 40, "silver": 20, "gold": 15, "platinum": 10},
    "outpatient_surgery": {"bronze": 40, "silver": 20, "gold": 15, "platinum": 10},
    "diagnostic_lab": {"bronze": 40, "silver": 20, "gold": 10, "platinum": 0},
    "advanced_imaging": {"bronze": 40, "silver": 20, "gold": 15, "platinum": 10},
}

OON_COINSURANCE: Final[dict[str, int]] = {"bronze": 60, "silver": 50, "gold": 40, "platinum": 30}

CATEGORIES: Final[tuple[CategorySpec, ...]] = (
    CategorySpec("preventive_care", "99214", 24000, False, False, None, None, False, None,
                 "Routine preventive care is only free inside the network."),
    CategorySpec("primary_care", "99213", 16500, False, False, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("specialist", "99204", 31500, False, False, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("urgent_care", "99214", 24000, False, False, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("emergency_room", None, 250000, True, False, None, None, True, None, None),
    CategorySpec("inpatient_hospital", "27447", 2850000, True, True, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("outpatient_surgery", "29881", 685000, True, True, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("diagnostic_lab", "80053", 4900, True, False, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("advanced_imaging", "73721", 95000, True, True, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("generic_drugs", None, 4200, False, False, None, None, False, None,
                 "Prescriptions filled outside the pharmacy network are not covered."),
    CategorySpec("mental_health", "99213", 16500, False, False, None, None, True,
                 OON_COINSURANCE, None),
    CategorySpec("physical_therapy", "97110", 6500, False, False, 20,
                 BenefitLimitPeriod.PER_YEAR, True, OON_COINSURANCE, None),
)

CATEGORY_DISPLAY: Final[dict[str, str]] = {
    "preventive_care": "Preventive care and screenings",
    "primary_care": "Primary care office visit",
    "specialist": "Specialist office visit",
    "urgent_care": "Urgent care visit",
    "emergency_room": "Emergency room visit",
    "inpatient_hospital": "Inpatient hospital stay",
    "outpatient_surgery": "Outpatient (same-day) surgery",
    "diagnostic_lab": "Laboratory tests and basic X-rays",
    "advanced_imaging": "MRI, CT and PET scans",
    "generic_drugs": "Generic prescription medicines",
    "mental_health": "Mental health therapy and psychiatry",
    "physical_therapy": "Physical therapy",
}


def _explain(category: str, plan: PlanSpec, copay: int | None, coinsurance: int | None) -> str:
    """Plain-language coverage text for one in-network benefit.

    Written to be read by a worried person, not by a broker: short sentences,
    the number they will actually be asked for, and the one thing that most
    often goes wrong with that benefit.
    """
    deductible = _money(plan.deductible_cents)
    oop = _money(plan.oop_cents)
    pays = 100 - (coinsurance or 0)
    if category == "preventive_care":
        return (
            "Your yearly check-up, the standard screenings for your age, and routine "
            "vaccinations cost you nothing when you use a doctor in the network. There is no "
            "copay and you do not have to meet your deductible first. One thing to watch: if "
            "your doctor finds a problem during the check-up and treats it on the spot, that "
            "treatment is a separate charge and the usual costs apply to it."
        )
    if category == "primary_care":
        return (
            f"This is your own doctor — the person you see for a sore throat, a blood-pressure "
            f"check, or to talk through your medicines. You pay {_money(copay or 0)} at the "
            "visit and nothing more for the doctor's time. You do not need to meet your "
            "deductible first. Blood tests or an injection given during the visit are billed "
            "separately, so a bill arriving later does not mean you were charged twice."
        )
    if category == "specialist":
        return (
            f"A specialist is a doctor who focuses on one part of your health, such as a "
            f"cardiologist or an orthopaedic surgeon. Each visit costs you "
            f"{_money(copay or 0)}, and your deductible does not apply to that fee. You do not "
            "need a referral from your regular doctor on this plan, but do check that the "
            "specialist is in the network before you book — that is the single most common "
            "reason people get a surprise bill."
        )
    if category == "urgent_care":
        return (
            f"Urgent care is for things that cannot wait for an appointment but are not "
            f"emergencies: a deep cut, a suspected sprain, a fever that will not settle. A "
            f"visit costs you {_money(copay or 0)}. Going here instead of the emergency room "
            f"for the same problem typically saves you several hundred dollars."
        )
    if category == "emergency_room":
        return (
            f"If you think you are having an emergency, go to the nearest emergency room and "
            f"do not stop to check whether it is in the network — this plan pays emergency "
            f"care at the in-network rate wherever you are. You pay {_money(copay or 0)} for "
            f"the visit, and that amount counts toward your {deductible} deductible. If you "
            "are admitted to hospital from the emergency room, the stay itself is billed under "
            "inpatient care instead, not on top of this."
        )
    if category == "inpatient_hospital":
        return (
            f"This covers being admitted and staying overnight. You first pay whatever is left "
            f"of your {deductible} deductible for the year, then {coinsurance}% of the price "
            f"the plan has agreed with the hospital; the plan pays the other {pays}%. A "
            f"planned admission has to be approved before you go in — the hospital usually "
            f"arranges this, but it is worth confirming. Once you have paid {oop} in total "
            "this year, the plan pays 100% of everything else."
        )
    if category == "outpatient_surgery":
        return (
            f"Surgery where you go home the same day, such as a knee arthroscopy or a cataract "
            f"operation. After your {deductible} deductible you pay {coinsurance}% of the "
            f"agreed price and the plan pays {pays}%. This needs approval in advance. If it "
            "goes ahead without approval the claim can be refused outright, and that is the "
            "situation where members end up owing the whole amount, so ask your surgeon's "
            "office to confirm the authorisation number before the date."
        )
    if category == "diagnostic_lab":
        share = "nothing" if coinsurance == 0 else f"{coinsurance}%"
        return (
            f"Blood tests, urine tests and standard X-rays. Once your {deductible} deductible "
            f"is met you pay {share} of the agreed price. The same test can cost several times "
            "more at a lab outside the network, and hospital-based labs are usually the most "
            "expensive option, so it is worth asking where the sample is being sent."
        )
    if category == "advanced_imaging":
        return (
            f"MRI, CT and PET scans. After your {deductible} deductible you pay {coinsurance}% "
            f"and the plan pays {pays}%. These scans need approval before they are done. A "
            "scan is often the largest single line on a hospital bill, so it is reasonable to "
            "ask for the price and for a free-standing imaging centre rather than a hospital "
            "one."
        )
    if category == "generic_drugs":
        return (
            f"A generic medicine has the same active ingredient as the brand-name version and "
            f"has to work the same way. You pay {_money(copay or 0)} for a 30-day supply at a "
            "pharmacy in the network, and your deductible does not apply. If your doctor "
            "writes for a brand when a generic exists, you may be asked to pay the difference, "
            "so it is worth asking whether a generic will do."
        )
    if category == "mental_health":
        return (
            f"Therapy and psychiatry are covered exactly like any other doctor's visit: "
            f"{_money(copay or 0)} per session, no deductible first, and no cap on the number "
            "of sessions in a year. You do not need anyone's permission to start, and the "
            "plan is not told what you discuss."
        )
    if category == "physical_therapy":
        return (
            f"Physical therapy costs you {_money(copay or 0)} per session and the plan covers "
            "up to 20 sessions a year, counted from January. If your therapist expects to need "
            "more than that, ask them to request extra visits before you run out rather than "
            "after — approval after the fact is much harder."
        )
    raise ValueError(f"No plain-language explanation written for category {category!r}")


def _example(
    category: str, spec: CategorySpec, copay: int | None, coinsurance: int | None
) -> dict[str, Any]:
    """A worked example whose three numbers add up."""
    billed = spec.example_billed_cents
    allowed = _allowed(billed)
    if copay is not None:
        you_pay = min(copay, allowed)
        return {
            "situation": f"A typical {CATEGORY_DISPLAY[category].lower()} in the network.",
            "billed_cents": billed,
            "plan_negotiated_cents": allowed,
            "you_pay_cents": you_pay,
            "plan_pays_cents": allowed - you_pay,
            "assumes_deductible_met": False,
        }
    share = coinsurance or 0
    you_pay = _cents(Decimal(allowed) * Decimal(share) / Decimal(100))
    return {
        "situation": f"A typical {CATEGORY_DISPLAY[category].lower()} in the network.",
        "billed_cents": billed,
        "plan_negotiated_cents": allowed,
        "you_pay_cents": you_pay,
        "plan_pays_cents": allowed - you_pay,
        "assumes_deductible_met": True,
    }


# Deductible and out-of-pocket progress for the member's silver plan.
DEDUCTIBLE_CONSUMED: Final = 96400
OOP_CONSUMED: Final = 143200
PT_VISITS_USED: Final = 6


@dataclass(frozen=True)
class LedgerSpec:
    key: str
    entry_type: LoyaltyEntryType
    points: int
    reason: str
    reference_type: str
    day_offset: int


LEDGER: Final[tuple[LedgerSpec, ...]] = (
    LedgerSpec("welcome", LoyaltyEntryType.ACCRUAL, 500,
               "Welcome bonus for completing your health profile", "enrollment", -640),
    LedgerSpec("wellness-2024", LoyaltyEntryType.ACCRUAL, 250,
               "Annual wellness visit completed", "encounter", -420),
    LedgerSpec("lab-booking", LoyaltyEntryType.ACCRUAL, 150,
               "Booked and attended a laboratory appointment", "lab_order", -395),
    LedgerSpec("premium-discount", LoyaltyEntryType.REDEMPTION, -300,
               "Redeemed against the January premium", "premium_schedule", -212),
    LedgerSpec("adherence-streak", LoyaltyEntryType.ACCRUAL, 400,
               "Ninety-day medication adherence streak", "medication_schedule", -180),
    LedgerSpec("screening", LoyaltyEntryType.ACCRUAL, 200,
               "Completed a recommended preventive screening", "encounter", -120),
    LedgerSpec("expiry-2025", LoyaltyEntryType.EXPIRY, -100,
               "Points earned in 2024 expired", "expiry_run", -60),
    LedgerSpec("renewal", LoyaltyEntryType.ACCRUAL, 325,
               "Policy renewal loyalty bonus", "policy", -30),
    LedgerSpec("correction", LoyaltyEntryType.ADJUSTMENT, -125,
               "Correction: duplicate wellness award reversed", "service_desk", -12),
)


# --------------------------------------------------------------------------------------
# Loading helpers
# --------------------------------------------------------------------------------------


class ConceptIndex:
    """``(system uri, code) -> code_concepts`` row, preferring the active version."""

    def __init__(self, rows: Iterable[tuple[CodeConcept, str]]) -> None:
        self._index: dict[tuple[str, str], CodeConcept] = {}
        for concept, uri in rows:
            key = (uri, concept.code)
            current = self._index.get(key)
            if current is None or (concept.is_active and not current.is_active):
                self._index[key] = concept

    def get(self, uri: str, code: str) -> CodeConcept:
        try:
            return self._index[(uri, code)]
        except KeyError as exc:
            raise RuntimeError(
                f"Reference concept {code!r} in {uri} is missing; run healthos-seed-reference first"
            ) from exc


async def _load_concepts(session: AsyncSession) -> ConceptIndex:
    stmt = select(CodeConcept, CodeSystem.uri).join(
        CodeSystem, CodeSystem.id == CodeConcept.code_system_id
    )
    rows = (await session.execute(stmt)).tuples().all()
    return ConceptIndex(rows)


@dataclass
class Cast:
    """Every actor and container the journey hangs off, resolved once."""

    provider_org: Organization
    payer_org: Organization
    patient: PatientProfile
    patient_user_id: UUID
    doctors: dict[str, UUID]
    hospital_user_id: UUID
    payer_user_id: UUID
    admin_user_id: UUID
    departments: dict[str, Department]
    service_items: dict[str, ServiceItem]
    lab_tests: dict[str, LabTest]
    facility: LabFacility
    concepts: ConceptIndex


async def _require_user(session: AsyncSession, key: str) -> UUID:
    user_id = demo_id(f"user:{key}")
    user = await session.get(User, user_id)
    if user is None:
        raise RuntimeError(f"Demo {key} account is missing; run healthos-seed-demo first")
    return user.id


async def _resolve_cast(session: AsyncSession) -> Cast:
    patient_user_id = await _require_user(session, "patient")
    doctor_user_id = await _require_user(session, "doctor")
    hospital_user_id = await _require_user(session, "hospital")
    payer_user_id = await _require_user(session, "insurance")
    admin_user_id = await _require_user(session, "admin")

    patient = await session.get(PatientProfile, patient_user_id)
    if patient is None or patient.patient_id != PATIENT_MRN:
        raise RuntimeError(f"Demo patient {PATIENT_MRN} is missing; run healthos-seed-demo first")

    provider_org = await session.scalar(
        select(Organization).where(Organization.organization_type == "hospital").order_by(
            Organization.created_at, Organization.slug
        )
    )
    payer_org = await session.scalar(
        select(Organization).where(Organization.organization_type == "insurance").order_by(
            Organization.created_at, Organization.slug
        )
    )
    if provider_org is None or payer_org is None:
        raise RuntimeError("A hospital and an insurance organisation must exist before seeding")

    service_items = {
        row.service_code: row
        for row in (
            await session.scalars(
                select(ServiceItem).where(ServiceItem.organization_id == provider_org.id)
            )
        ).all()
    }
    if not service_items:
        raise RuntimeError("The chargemaster is empty; run healthos-seed-reference first")

    lab_tests = {
        row.test_code: row
        for row in (
            await session.scalars(select(LabTest).where(LabTest.tenant_id == provider_org.id))
        ).all()
    }
    if not lab_tests:
        raise RuntimeError("The lab catalogue is empty; run healthos-seed-reference first")

    return Cast(
        provider_org=provider_org,
        payer_org=payer_org,
        patient=patient,
        patient_user_id=patient_user_id,
        doctors={"rodriguez": doctor_user_id},
        hospital_user_id=hospital_user_id,
        payer_user_id=payer_user_id,
        admin_user_id=admin_user_id,
        departments={},
        service_items=service_items,
        lab_tests=lab_tests,
        facility=LabFacility(),  # replaced in _seed_organisation
        concepts=await _load_concepts(session),
    )


# --------------------------------------------------------------------------------------
# A. Organisation
# --------------------------------------------------------------------------------------


async def _seed_staff(session: AsyncSession, cast: Cast) -> int:
    for spec in STAFF:
        user_id = journey_id(f"user:{spec.key}")
        await _upsert(
            session,
            User,
            user_id,
            email=spec.email,
            account_type="doctor",
            status=UserStatus.ACTIVE,
            email_verified=True,
            phone_verified=True,
        )
        profile = await session.get(DoctorProfile, user_id)
        if profile is None:
            profile = DoctorProfile(
                user_id=user_id,
                first_name=spec.first_name,
                last_name=spec.last_name,
                license_number=spec.license_number,
            )
            session.add(profile)
        profile.first_name = spec.first_name
        profile.last_name = spec.last_name
        profile.license_number = spec.license_number
        profile.license_jurisdiction = spec.jurisdiction
        profile.specialty = spec.specialty
        profile.affiliation = cast.provider_org.legal_name
        profile.credentials_verified = True
        profile.phone = spec.phone
        cast.doctors[spec.key] = user_id
    await session.flush()
    return len(STAFF)


async def _seed_organisation(session: AsyncSession, cast: Cast, today: date) -> dict[str, int]:
    tenant = cast.provider_org.id

    for spec in DEPARTMENTS:
        department = await _upsert(
            session,
            Department,
            journey_id(f"department:{spec.code}"),
            tenant_id=tenant,
            organization_id=tenant,
            code=spec.code,
            name=spec.name,
            cost_center=spec.cost_center,
            is_active=True,
        )
        cast.departments[spec.code] = department
    await session.flush()

    # One credential deliberately expires inside the 60-day renewal window so the
    # credentialing dashboard has something to escalate.
    roles = (
        ("okafor", "attending", "internal-medicine", "IM", "207R00000X", date(2028, 6, 30)),
        ("okafor", "medical-director", "internal-medicine", "IM", "207R00000X", date(2028, 6, 30)),
        ("rodriguez", "attending", "orthopedic-surgery", "ORTHO", "207X00000X", today + timedelta(days=40)),
        ("whitfield", "attending", "internal-medicine", "IM", "207R00000X", date(2027, 11, 30)),
    )
    for provider, role_code, specialty, department_code, taxonomy, expires in roles:
        await _upsert(
            session,
            PractitionerRole,
            journey_id(f"practitioner-role:{provider}:{role_code}"),
            tenant_id=tenant,
            practitioner_user_id=cast.doctors[provider],
            organization_id=tenant,
            department_id=cast.departments[department_code].id,
            role_code=role_code,
            specialty_code=specialty,
            taxonomy_code=taxonomy,
            privileges=["outpatient_clinic", "order_entry", "prescribe"],
            credentialing_status="active",
            credentialed_at=date(2023, 7, 1),
            credential_expires_at=expires,
            accepts_new_patients=role_code == "attending",
            is_active=True,
        )

    facility = await _upsert(
        session,
        LabFacility,
        journey_id("lab-facility:main"),
        tenant_id=tenant,
        organization_id=tenant,
        name="Desert Valley Laboratory — Main Campus",
        address_line1="4820 East Camelback Road",
        city="Phoenix",
        region="AZ",
        postal_code="85018",
        country="US",
        latitude=Decimal("33.509400"),
        longitude=Decimal("-111.978300"),
        timezone=TIMEZONE_NAME,
        home_collection_available=True,
        is_active=True,
    )
    cast.facility = facility

    # The chargemaster already exists; give it a home in the department structure
    # so the service catalogue is navigable and so lab pricing rolls up correctly.
    for code, item in cast.service_items.items():
        if code in LAB_CPT:
            item.department_id = cast.departments["LAB"].id
        elif code in ORTHO_CPT:
            item.department_id = cast.departments["ORTHO"].id
        else:
            item.department_id = cast.departments["IM"].id
    for test in cast.lab_tests.values():
        test.department_id = cast.departments["LAB"].id

    rates = 0
    for code, item in sorted(cast.service_items.items()):
        await _upsert(
            session,
            PayerContractRate,
            journey_id(f"contract-rate:{code}"),
            tenant_id=cast.payer_org.id,
            payer_organization_id=cast.payer_org.id,
            provider_organization_id=tenant,
            service_code_system=CPT,
            service_code=code,
            service_display=item.service_display,
            service_concept_id=item.service_concept_id,
            allowed_cents=_allowed(item.base_price_cents),
            currency=CURRENCY,
            effective_from=CONTRACT_FROM,
            effective_to=None,
        )
        rates += 1
    await session.flush()

    return {
        "departments": len(DEPARTMENTS),
        "practitioner_roles": len(roles),
        "lab_facilities": 1,
        "payer_contract_rates": rates,
        "service_items_assigned": len(cast.service_items),
    }


# --------------------------------------------------------------------------------------
# B. Capacity
# --------------------------------------------------------------------------------------


def _expand(spec: ScheduleSpec, window_from: date, window_to: date) -> list[tuple[datetime, datetime]]:
    """Mirror of ``scheduling._expand_schedule`` so seeded slots match generated ones."""
    step = timedelta(minutes=SLOT_MINUTES)
    periods: list[tuple[datetime, datetime]] = []
    day = window_from
    while day <= window_to:
        if day.weekday() == spec.day_of_week:
            cursor = datetime.combine(day, spec.start, tzinfo=ZONE)
            day_end = datetime.combine(day, spec.end, tzinfo=ZONE)
            while cursor + step <= day_end:
                periods.append((cursor.astimezone(UTC), (cursor + step).astimezone(UTC)))
                cursor += step
        day += timedelta(days=1)
    return periods


async def _seed_capacity(session: AsyncSession, cast: Cast, today: date) -> dict[str, int]:
    tenant = cast.provider_org.id
    window_from = today + timedelta(days=1)
    window_to = today + timedelta(days=CAPACITY_DAYS)

    created: list[AppointmentSlot] = []
    for spec in SCHEDULES:
        schedule = await _upsert(
            session,
            ProviderSchedule,
            journey_id(f"schedule:{spec.key}"),
            tenant_id=tenant,
            provider_user_id=cast.doctors[spec.provider],
            organization_id=tenant,
            department_id=cast.departments[spec.department].id,
            day_of_week=spec.day_of_week,
            start_time=spec.start,
            end_time=spec.end,
            slot_minutes=SLOT_MINUTES,
            timezone=TIMEZONE_NAME,
            channel=spec.channel,
            valid_from=date(2026, 1, 1),
            valid_to=None,
            is_active=True,
        )
        await session.flush()
        for start_at, end_at in _expand(spec, window_from, window_to):
            slot = await _upsert(
                session,
                AppointmentSlot,
                journey_id(f"slot:{spec.provider}:{start_at.isoformat()}"),
                tenant_id=tenant,
                provider_user_id=cast.doctors[spec.provider],
                organization_id=tenant,
                schedule_id=schedule.id,
                start_at=start_at,
                end_at=end_at,
                capacity=1,
                booked_count=0,
                status=SlotStatus.OPEN,
                channel=spec.channel,
                price_cents=SLOT_PRICE_CENTS,
                currency=CURRENCY,
            )
            created.append(slot)
    await session.flush()

    created.sort(key=lambda row: (row.start_at, str(row.provider_user_id)))

    # Every eleventh slot is protected admin time; five become real bookings. The
    # rest stay open so availability search returns genuine capacity.
    blocked = 0
    for index, slot in enumerate(created):
        if index % 11 == 10:
            slot.status = SlotStatus.BLOCKED
            blocked += 1

    booking_reasons = (
        "Four-week blood pressure review with the home log",
        "Repeat metabolic panel results review",
        "Right knee — three month orthopaedic review",
        "Physical therapy progress review",
        "Medication check-in",
    )
    bookable = [slot for slot in created if slot.status == SlotStatus.OPEN]
    chosen = [bookable[i] for i in (2, 9, 17, 26, 40) if i < len(bookable)]
    appointments = 0
    events = 0
    for reason, slot in zip(booking_reasons, chosen, strict=False):
        slot.status = SlotStatus.BOOKED
        slot.booked_count = 1
        appointment = await _upsert(
            session,
            Appointment,
            journey_id(f"appointment:{slot.id}"),
            tenant_id=tenant,
            slot_id=slot.id,
            patient_user_id=cast.patient_user_id,
            provider_user_id=slot.provider_user_id,
            organization_id=tenant,
            reason=reason,
            channel=slot.channel,
            status=AppointmentStatus.CONFIRMED,
            payment_status="unpaid",
            booked_at=_local(today - timedelta(days=2), time(9, 15)),
        )
        appointments += 1
        await session.flush()
        for index, (from_status, to_status) in enumerate(
            ((None, "requested"), ("requested", "confirmed"))
        ):
            await _insert_once(
                session,
                AppointmentStatusEvent,
                journey_id(f"appointment-event:{appointment.id}:{index}"),
                tenant_id=tenant,
                appointment_id=appointment.id,
                from_status=from_status,
                to_status=to_status,
                changed_by_user_id=cast.patient_user_id,
                reason=None if from_status is None else "Slot held and confirmed online",
                occurred_at=_local(today - timedelta(days=2), time(9, 15 + index)),
            )
            events += 1

    # One cancelled telehealth visit in the recent past, so the refunded invoice
    # further down has something real to refund.
    cancelled_start = _local(today - timedelta(days=3), time(10, 0))
    cancelled_slot = await _upsert(
        session,
        AppointmentSlot,
        journey_id(f"slot:rodriguez:{cancelled_start.isoformat()}"),
        tenant_id=tenant,
        provider_user_id=cast.doctors["rodriguez"],
        organization_id=tenant,
        schedule_id=None,
        start_at=cancelled_start,
        end_at=cancelled_start + timedelta(minutes=SLOT_MINUTES),
        capacity=1,
        booked_count=0,
        status=SlotStatus.CANCELLED,
        channel=EncounterChannel.TELEHEALTH,
        price_cents=11000,
        currency=CURRENCY,
    )
    await session.flush()
    cancelled_appointment = await _upsert(
        session,
        Appointment,
        journey_id("appointment:cancelled-telehealth"),
        tenant_id=tenant,
        slot_id=cancelled_slot.id,
        patient_user_id=cast.patient_user_id,
        provider_user_id=cast.doctors["rodriguez"],
        organization_id=tenant,
        reason="Telehealth knee review",
        channel=EncounterChannel.TELEHEALTH,
        status=AppointmentStatus.CANCELLED,
        payment_status="refunded",
        cancellation_reason="Clinician unavailable — rescheduled at the clinic's request",
        cancelled_by_user_id=cast.doctors["rodriguez"],
        booked_at=_local(today - timedelta(days=10), time(11, 0)),
    )
    appointments += 1
    await session.flush()
    for index, (from_status, to_status, reason) in enumerate(
        (
            (None, "requested", None),
            ("requested", "confirmed", "Confirmed online"),
            ("confirmed", "cancelled", "Clinician unavailable — rescheduled"),
        )
    ):
        await _insert_once(
            session,
            AppointmentStatusEvent,
            journey_id(f"appointment-event:{cancelled_appointment.id}:{index}"),
            tenant_id=tenant,
            appointment_id=cancelled_appointment.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=cast.doctors["rodriguez"]
            if to_status == "cancelled"
            else cast.patient_user_id,
            reason=reason,
            occurred_at=_local(today - timedelta(days=10 - index * 3), time(11, 0)),
        )
        events += 1

    # Laboratory capacity: ten working days of morning draw slots.
    lab_slots = 0
    lab_slot_tests = 0
    day = today + timedelta(days=1)
    working_days = 0
    while working_days < 10:
        if day.weekday() < 5:
            working_days += 1
            for index in range(5):
                start = _local(day, time(7, 0)) + timedelta(minutes=30 * index)
                slot = await _upsert(
                    session,
                    LabSlot,
                    journey_id(f"lab-slot:{start.isoformat()}"),
                    tenant_id=tenant,
                    facility_id=cast.facility.id,
                    start_at=start,
                    end_at=start + timedelta(minutes=30),
                    capacity=4,
                    booked_count=1 if index == 0 else 0,
                    status=SlotStatus.OPEN,
                )
                lab_slots += 1
                await session.flush()
                for code in LAB_SLOT_TESTS:
                    test = cast.lab_tests[code]
                    key = {"slot_id": slot.id, "lab_test_id": test.id}
                    row = await session.get(LabSlotTest, key)
                    if row is None:
                        row = LabSlotTest(slot_id=slot.id, lab_test_id=test.id)
                        session.add(row)
                    row.capacity = 2
                    row.booked_count = 1 if index == 0 and code == "24323-8" else 0
                    row.price_cents_override = None
                    lab_slot_tests += 1
        day += timedelta(days=1)
    await session.flush()

    return {
        "provider_schedules": len(SCHEDULES),
        "appointment_slots": len(created) + 1,
        "appointment_slots_blocked": blocked,
        "appointments": appointments,
        "appointment_status_events": events,
        "lab_slots": lab_slots,
        "lab_slot_tests": lab_slot_tests,
    }


# --------------------------------------------------------------------------------------
# C. Lifelong patient record
# --------------------------------------------------------------------------------------


async def _seed_growth(session: AsyncSession, cast: Cast) -> int:
    dob = cast.patient.date_of_birth
    if dob is None:
        raise RuntimeError("The demo patient has no date of birth; run healthos-seed-demo first")
    sex = BiologicalSex.FEMALE

    curves: dict[tuple[GrowthMeasure, int], GrowthReferenceStandard] = {
        (row.measure, row.age_value): row
        for row in (
            await session.scalars(
                select(GrowthReferenceStandard).where(
                    GrowthReferenceStandard.source == GrowthSource.WHO,
                    GrowthReferenceStandard.sex == sex,
                    GrowthReferenceStandard.age_unit == "month",
                )
            )
        ).all()
    }
    if not curves:
        raise RuntimeError("WHO growth curves are missing; run healthos-seed-reference first")

    count = 0
    for months, weight_z, height_z in GROWTH_MONTHS:
        weight_row = curves[(GrowthMeasure.WEIGHT_FOR_AGE, months)]
        height_row = curves[(GrowthMeasure.HEIGHT_FOR_AGE, months)]
        age_days = int((Decimal(months) * DAYS_PER_MONTH).to_integral_value(ROUND_HALF_UP))
        measured_at = _local(dob + timedelta(days=age_days), time(10, 30))

        weight = _lms_value(weight_row, Decimal(weight_z)).quantize(Decimal("0.001"))
        height = _lms_value(height_row, Decimal(height_z)).quantize(Decimal("0.01"))
        # Recompute from the rounded, stored values so the row agrees with what
        # the percentile endpoint will calculate from the same columns.
        weight_score = _lms_zscore(weight, weight_row.l, weight_row.m, weight_row.s)
        height_score = _lms_zscore(height, height_row.l, height_row.m, height_row.s)
        if weight_score is None or height_score is None:
            raise RuntimeError(f"Growth curve for month {months} produced no z-score")
        bmi = (weight / (height / Decimal(100)) ** 2).quantize(Decimal("0.01"))

        await _upsert(
            session,
            GrowthMeasurement,
            journey_id(f"growth:{months}"),
            tenant_id=cast.provider_org.id,
            patient_user_id=cast.patient_user_id,
            encounter_id=None,
            measured_at=measured_at,
            age_days=age_days,
            height_cm=height,
            weight_kg=weight,
            head_circumference_cm=None,
            bmi=bmi,
            height_percentile=Decimal(str(_zscore_to_percentile(height_score))).quantize(
                Decimal("0.01")
            ),
            weight_percentile=Decimal(str(_zscore_to_percentile(weight_score))).quantize(
                Decimal("0.01")
            ),
            bmi_percentile=None,
            height_zscore=Decimal(str(round(height_score, 3))),
            weight_zscore=Decimal(str(round(weight_score, 3))),
            bmi_zscore=None,
            standard_id=weight_row.id,
            recorded_by_user_id=cast.doctors["okafor"],
            asserter_user_id=None,
            recorded_at=_local(date(2023, 9, 12), time(14, 0)),
            source=ProvenanceSource.IMPORTED,
            note_free=None,
        ) if False else await _upsert(
            session,
            GrowthMeasurement,
            journey_id(f"growth:{months}"),
            tenant_id=cast.provider_org.id,
            patient_user_id=cast.patient_user_id,
            encounter_id=None,
            measured_at=measured_at,
            age_days=age_days,
            height_cm=height,
            weight_kg=weight,
            head_circumference_cm=None,
            bmi=bmi,
            height_percentile=Decimal(str(_zscore_to_percentile(height_score))).quantize(
                Decimal("0.01")
            ),
            weight_percentile=Decimal(str(_zscore_to_percentile(weight_score))).quantize(
                Decimal("0.01")
            ),
            bmi_percentile=None,
            height_zscore=Decimal(str(round(height_score, 3))),
            weight_zscore=Decimal(str(round(weight_score, 3))),
            bmi_zscore=None,
            standard_id=weight_row.id,
            recorded_by_user_id=cast.doctors["okafor"],
            asserter_user_id=None,
            recorded_at=_local(date(2023, 9, 12), time(14, 0)),
            source=ProvenanceSource.IMPORTED,
            version=1,
        )
        count += 1
    await session.flush()
    return count


def _lms_value(row: GrowthReferenceStandard, z: Decimal) -> Decimal:
    """Inverse LMS: the measurement that sits exactly ``z`` standard deviations out."""
    lam = float(row.l)
    median = float(row.m)
    sigma = float(row.s)
    target = float(z)
    if lam == 0.0:
        value = median * pow(2.718281828459045, sigma * target)
    else:
        value = median * pow(1.0 + lam * sigma * target, 1.0 / lam)
    return Decimal(f"{value:.6f}")
