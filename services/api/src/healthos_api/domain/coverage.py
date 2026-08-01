"""Patient-facing insurance coverage: policies, benefits, claims, and the marketplace.

This module backs the Insurance tab. Two rules shape everything here:

* Anything that reads a patient's policies, accumulators, claims, or loyalty
  balance is *consent* scoped (:func:`consent_scoped_patients`) and writes a
  :class:`PhiAccessEvent` in the same transaction as the read.
* Coverage text is never invented. Plain-language strings come from
  ``benefit_explanations`` rows joined to the ``plan_benefits`` row they
  explain; when no explanation exists the structured benefit is returned with
  ``plain_language`` set to ``None``.

The marketplace deliberately does *not* tenant filter: a patient shopping for a
policy must see plans from every participating payer. Payer participation is
expressed by ``organizations.status`` plus the product/plan ``is_active`` flags
and the plan's effective window.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import Field
from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AllergyIntolerance,
    AllergyVerificationStatus,
    BenefitAccumulator,
    BenefitExplanation,
    Claim,
    ClaimEvent,
    ClaimLine,
    ClaimStatus,
    ClaimType,
    ClinicalStatus,
    Condition,
    ConditionCategory,
    DoctorProfile,
    DocumentAsset,
    DocumentLink,
    DocumentLinkType,
    Encounter,
    InsurancePlan,
    InsuranceProduct,
    LoyaltyAccount,
    LoyaltyEntryType,
    LoyaltyLedgerEntry,
    MemberRelationship,
    NetworkTier,
    Organization,
    PatientProfile,
    PlanBenefit,
    PlanRecommendation,
    Policy,
    PolicyApplication,
    PolicyApplicationStatus,
    PolicyMember,
    PolicyStatus,
    PremiumFrequency,
    PremiumSchedule,
    SystemSetting,
    VerificationStatus,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    PurposeOfUse,
    apply_patient_scope,
    assert_may_read_patient,
    assert_transition,
    conflict,
    consent_scoped_patients,
    is_patient,
    not_found,
    paginate,
    record_phi_access,
    record_phi_access_many,
    tenant_scoped,
    unprocessable,
    write_audit,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

HELPLINE_SETTING_KEY = "claims.helpline"
DEFAULT_HELPLINE_PHONE = "+1-800-555-0142"
DEFAULT_HELPLINE_HOURS = "Mon-Fri 08:00-20:00, Sat 09:00-13:00 (local time)"
DEFAULT_HELPLINE_LANGUAGES = ("en-US",)
DEFAULT_CLAIM_CHECKLIST = (
    "Your member ID and policy number",
    "The provider's name and the date of service",
    "The itemised bill or receipt for the visit",
    "Any referral or prior-authorisation number",
    "A photo or PDF of the discharge summary, if you were admitted",
)

#: Version stamped onto every persisted ``plan_recommendations`` row.
RECOMMENDER_VERSION = "coverage-recommender-v1"
#: Hard cap on how many plans a single marketplace call scores and persists.
MAX_MARKETPLACE_CANDIDATES = 200
RECOMMENDATION_TTL_DAYS = 7
#: ``insurance_plans.premium_cents`` is the amount for one billing period; the
#: marketplace annualises it at the monthly default used by ``policies``.
ANNUAL_PREMIUM_PERIODS = 12
#: One loyalty point is accrued per this many cents of first-term premium.
ACCRUAL_CENTS_PER_POINT = 1000
#: Loyalty redemption rate applied to the first premium instalment.
REDEMPTION_CENTS_PER_POINT = 1
CLAIM_LOOKBACK_DAYS = 365

_FREQUENCY_MONTHS: dict[PremiumFrequency, int] = {
    PremiumFrequency.MONTHLY: 1,
    PremiumFrequency.QUARTERLY: 3,
    PremiumFrequency.ANNUAL: 12,
}

OPEN_CLAIM_STATUSES = (
    ClaimStatus.DRAFT,
    ClaimStatus.SUBMITTED,
    ClaimStatus.ACCEPTED,
    ClaimStatus.PENDED,
    ClaimStatus.APPEALED,
)

ACTIVE_CONDITION_STATUSES = (
    ClinicalStatus.ACTIVE,
    ClinicalStatus.RECURRENCE,
    ClinicalStatus.RELAPSE,
)

#: An application may only be converted into a policy from these states.
APPLICATION_TRANSITIONS: dict[str, set[str]] = {
    PolicyApplicationStatus.DRAFT.value: {PolicyApplicationStatus.SUBMITTED.value},
    PolicyApplicationStatus.SUBMITTED.value: {PolicyApplicationStatus.ISSUED.value},
    PolicyApplicationStatus.UNDERWRITING.value: {PolicyApplicationStatus.ISSUED.value},
    PolicyApplicationStatus.APPROVED.value: {PolicyApplicationStatus.ISSUED.value},
}

MarketplaceSort = Literal["recommended", "premium_asc", "deductible_asc"]

REASON_TEXT: dict[str, str] = {
    "RICH_COVERAGE_FOR_ACTIVE_CONDITIONS": (
        "Your active conditions make richer cost sharing worth more than a low premium."
    ),
    "HIGH_RECENT_CLAIM_VOLUME": (
        "You filed several claims in the last year, so this plan's cost sharing was weighted up."
    ),
    "SENIOR_UTILISATION_WEIGHTING": (
        "Comprehensive coverage was weighted up because of your age band."
    ),
    "ALLERGY_BURDEN_WEIGHTED": (
        "Your recorded allergies raise the chance of specialist and pharmacy visits."
    ),
    "LOW_PREMIUM_IN_MARKET": "The monthly premium is in the cheapest quarter of the market today.",
    "LOW_DEDUCTIBLE": "The individual deductible is in the lowest quarter of the market today.",
    "LOW_OUT_OF_POCKET_MAX": "The out-of-pocket maximum caps your worst-case year early.",
    "BROAD_BENEFIT_COVERAGE": "Most published benefit categories on this plan are covered.",
    "MINIMAL_PRIOR_AUTH": "Few benefits on this plan need prior authorisation.",
    "LOYALTY_POINTS_OFFSET": "Your loyalty points can be redeemed against the first premium.",
    "BASELINE_MARKET_MATCH": "This plan matches your filters and is open for enrolment today.",
}


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class PayerSummary(DomainModel):
    organization_id: UUID
    slug: str
    legal_name: str
    organization_type: str


class PlanSummary(DomainModel):
    id: UUID
    plan_code: str
    name: str
    metal_tier: str | None
    product_id: UUID
    product_code: str
    product_name: str
    product_type: str
    network_name: str | None
    premium_cents: int
    currency: str
    individual_deductible_cents: int | None
    family_deductible_cents: int | None
    individual_oop_max_cents: int | None
    family_oop_max_cents: int | None
    term_months: int
    effective_from: date
    effective_to: date | None
    payer: PayerSummary


class PolicySummary(DomainModel):
    id: UUID
    policy_number: str
    member_id: str
    status: str
    effective_from: date
    effective_to: date | None
    premium_cents: int
    currency: str
    premium_frequency: str
    subscriber_user_id: UUID
    member_relationship: str | None
    purchased_via_application_id: UUID | None
    plan: PlanSummary


class BenefitPlainLanguage(DomainModel):
    explanation_id: UUID
    locale: str
    reading_level: str
    summary_text: str
    example_scenario: dict[str, Any]
    generated_by: str
    model_version: str | None
    reviewed_at: datetime | None


class BenefitRow(DomainModel):
    benefit_id: UUID
    service_category: str
    service_code_system: str | None
    service_code: str | None
    service_display: str | None
    network_tier: str
    covered: bool
    copay_cents: int | None
    coinsurance_percent: Decimal | None
    deductible_applies: bool
    visit_limit_count: int | None
    limit_period: str | None
    prior_auth_required: bool
    waiting_period_days: int
    exclusion_text: str | None
    effective_from: date
    effective_to: date | None
    plain_language: BenefitPlainLanguage | None


class AccumulatorRead(DomainModel):
    id: UUID
    accumulator_type: str
    benefit_year: int
    limit_cents: int | None
    consumed_cents: int
    remaining_cents: int | None
    limit_count: int | None
    consumed_count: int
    as_of: datetime


class CoverageExplanation(DomainModel):
    policy: PolicySummary
    patient_user_id: UUID
    locale: str
    reading_level: str
    benefit_year: int
    as_of: date
    benefits: list[BenefitRow]
    benefits_with_plain_language: int
    benefits_without_plain_language: int
    accumulators: list[AccumulatorRead]
    deductible_consumed_cents: int
    deductible_limit_cents: int | None
    oop_consumed_cents: int
    oop_limit_cents: int | None


class ClaimAssistancePolicy(DomainModel):
    policy_id: UUID
    policy_number: str
    member_id: str
    payer_name: str


class ClaimAssistance(DomainModel):
    phone: str
    hours: str
    languages: list[str]
    what_to_have_ready: list[str]
    source: Literal["system_setting", "default"]
    your_policies: list[ClaimAssistancePolicy]
    open_claim_count: int


class ClaimLineRead(DomainModel):
    id: UUID
    line_number: int
    service_date: date
    service_code_system: str
    service_code: str
    service_display: str
    modifiers: list[str]
    units: Decimal
    charge_cents: int
    allowed_cents: int | None
    paid_cents: int | None
    copay_cents: int | None
    coinsurance_cents: int | None
    deductible_cents: int | None
    diagnosis_pointers: list[str]
    adjustment_reason_codes: list[str]


class ClaimEventRead(DomainModel):
    id: UUID
    event_type: str
    from_status: str | None
    to_status: str
    actor_user_id: UUID | None
    payload: dict[str, Any]
    occurred_at: datetime


class ClaimSummary(DomainModel):
    id: UUID
    claim_number: str
    policy_id: UUID
    patient_user_id: UUID
    subscriber_user_id: UUID
    billing_provider_organization_id: UUID
    rendering_provider_user_id: UUID | None
    encounter_id: UUID | None
    claim_type: str
    status: str
    service_from: date
    service_to: date
    total_charge_cents: int
    allowed_cents: int | None
    paid_cents: int | None
    patient_responsibility_cents: int | None
    currency: str
    submitted_at: datetime | None
    adjudicated_at: datetime | None
    denial_reason_code: str | None
    line_count: int
    created_at: datetime


class ClaimDetail(ClaimSummary):
    lines: list[ClaimLineRead]
    events: list[ClaimEventRead]


class ClaimLineCreate(DomainModel):
    service_date: date
    service_code_system: str = Field(min_length=1, max_length=128)
    service_code: str = Field(min_length=1, max_length=64)
    service_display: str = Field(min_length=1, max_length=255)
    modifiers: list[str] = Field(default_factory=list, max_length=8)
    units: Decimal = Field(default=Decimal(1), gt=0, le=9999, max_digits=10, decimal_places=2)
    charge_cents: int = Field(ge=0, le=1_000_000_000)
    diagnosis_pointers: list[str] = Field(default_factory=list, max_length=8)


class ClaimCreate(DomainModel):
    policy_id: UUID
    patient_user_id: UUID | None = None
    claim_type: Literal["professional", "institutional", "dental", "pharmacy"] = "professional"
    billing_provider_organization_id: UUID
    rendering_provider_user_id: UUID | None = None
    encounter_id: UUID | None = None
    service_from: date
    service_to: date
    lines: list[ClaimLineCreate] = Field(min_length=1, max_length=50)
    submit: bool = True
    note: str | None = Field(default=None, max_length=500)


class ClaimDocumentAttach(DomainModel):
    document_asset_ids: list[UUID] = Field(min_length=1, max_length=20)
    link_type: Literal["evidence", "report", "certificate", "attachment", "receipt"] = "evidence"


class DocumentLinkRead(DomainModel):
    id: UUID
    document_asset_id: UUID
    subject_type: str
    subject_id: UUID
    link_type: str
    linked_by_user_id: UUID
    filename: str
    content_type: str
    byte_size: int
    created_at: datetime


class PatientRiskFeatures(DomainModel):
    """The medical-history parameters the ranking model consumes."""

    patient_user_id: UUID
    age_years: int | None
    active_condition_count: int
    chronic_condition_count: int
    active_allergy_count: int
    recent_claim_count: int
    recent_claim_charge_cents: int
    loyalty_balance_points: int


class RecommendationReason(DomainModel):
    code: str
    detail: str


class MarketplacePlan(DomainModel):
    plan: PlanSummary
    recommendation_id: UUID
    rank: int
    score: Decimal
    history_score: Decimal
    loyalty_score: Decimal
    loyalty_points_applied: int
    estimated_annual_cost_cents: int
    reason_codes: list[str]
    reasons: list[RecommendationReason]
    benefit_count: int
    covered_benefit_count: int


class MarketplaceResponse(DomainModel):
    patient_user_id: UUID
    model_version: str
    generated_at: datetime
    sort: MarketplaceSort
    features: PatientRiskFeatures
    candidates_scored: int
    plans: Page[MarketplacePlan]


class PlanDetail(DomainModel):
    plan: PlanSummary
    as_of: date
    locale: str
    reading_level: str
    benefits: list[BenefitRow]


class ApplicantDetails(DomainModel):
    full_name: str = Field(min_length=2, max_length=255)
    date_of_birth: date
    email: str = Field(min_length=3, max_length=255)
    phone: str = Field(min_length=5, max_length=32)
    address_line1: str = Field(min_length=2, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=2, max_length=20)
    country: str = Field(min_length=2, max_length=2)


class ApplicationCreate(DomainModel):
    plan_id: UUID
    applicant: ApplicantDetails
    loyalty_points_to_redeem: int = Field(default=0, ge=0, le=10_000_000)
    answers: dict[str, Any] = Field(default_factory=dict)


class ApplicationRead(DomainModel):
    id: UUID
    application_number: str
    applicant_user_id: UUID
    plan_id: UUID
    status: str
    submitted_at: datetime | None
    decision_at: datetime | None
    decline_reason: str | None
    quoted_premium_cents: int | None
    currency: str | None
    loyalty_points_redeemed: int
    answers: dict[str, Any]
    created_at: datetime


class PurchaseMember(DomainModel):
    patient_user_id: UUID
    relationship: Literal["spouse", "child", "other"]


class PurchaseRequest(DomainModel):
    effective_from: date | None = None
    premium_frequency: Literal["monthly", "quarterly", "annual"] = "monthly"
    members: list[PurchaseMember] = Field(default_factory=list, max_length=10)


class PremiumInstalment(DomainModel):
    id: UUID
    due_date: date
    amount_cents: int
    currency: str
    status: str


class PolicyMemberRead(DomainModel):
    id: UUID
    patient_user_id: UUID
    relationship: str
    member_suffix: str | None
    effective_from: date
    effective_to: date | None


class LoyaltyLedgerRead(DomainModel):
    id: UUID
    entry_type: str
    points: int
    balance_after: int
    reason: str
    reference_type: str
    reference_id: UUID
    expires_at: datetime | None
    occurred_at: datetime


class LoyaltyBalance(DomainModel):
    account_id: UUID | None
    program: str
    balance_points: int
    lifetime_points: int
    tier: str | None
    status: str
    history: Page[LoyaltyLedgerRead]


class PurchaseResult(DomainModel):
    policy: PolicySummary
    members: list[PolicyMemberRead]
    premium_schedule: list[PremiumInstalment]
    loyalty_entries: list[LoyaltyLedgerRead]
    loyalty_balance_points: int
    application: ApplicationRead
    already_issued: bool


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _today() -> date:
    return datetime.now(UTC).date()


def _purpose(context: AuthContext, patient_user_id: UUID) -> PurposeOfUse:
    """Patients reading their own file is PATRQT; everyone else is payment."""
    return "PATRQT" if context.user.id == patient_user_id else "HPAYMT"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score(value: float) -> Decimal:
    """Numeric(6, 4) with a non-negative check constraint."""
    return Decimal(f"{_clamp(value):.4f}")


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _reference(prefix: str) -> str:
    return f"{prefix}{datetime.now(UTC):%Y%m%d}{uuid4().hex[:10].upper()}"


def _payer_summary(payer: Organization) -> PayerSummary:
    return PayerSummary(
        organization_id=payer.id,
        slug=payer.slug,
        legal_name=payer.legal_name,
        organization_type=payer.organization_type,
    )


def _plan_summary(
    plan: InsurancePlan, product: InsuranceProduct, payer: Organization
) -> PlanSummary:
    return PlanSummary(
        id=plan.id,
        plan_code=plan.plan_code,
        name=plan.name,
        metal_tier=plan.metal_tier,
        product_id=product.id,
        product_code=product.code,
        product_name=product.name,
        product_type=product.product_type,
        network_name=product.network_name,
        premium_cents=plan.premium_cents,
        currency=plan.currency,
        individual_deductible_cents=plan.individual_deductible_cents,
        family_deductible_cents=plan.family_deductible_cents,
        individual_oop_max_cents=plan.individual_oop_max_cents,
        family_oop_max_cents=plan.family_oop_max_cents,
        term_months=plan.term_months,
        effective_from=plan.effective_from,
        effective_to=plan.effective_to,
        payer=_payer_summary(payer),
    )


def _policy_summary(
    policy: Policy,
    plan: InsurancePlan,
    product: InsuranceProduct,
    payer: Organization,
    member_relationship: MemberRelationship | None,
) -> PolicySummary:
    return PolicySummary(
        id=policy.id,
        policy_number=policy.policy_number,
        member_id=policy.member_id,
        status=policy.status.value,
        effective_from=policy.effective_from,
        effective_to=policy.effective_to,
        premium_cents=policy.premium_cents,
        currency=policy.currency,
        premium_frequency=policy.premium_frequency.value,
        subscriber_user_id=policy.subscriber_user_id,
        member_relationship=member_relationship.value if member_relationship else None,
        purchased_via_application_id=policy.application_id,
        plan=_plan_summary(plan, product, payer),
    )


def _claim_summary(claim: Claim, line_count: int) -> ClaimSummary:
    return ClaimSummary(
        id=claim.id,
        claim_number=claim.claim_number,
        policy_id=claim.policy_id,
        patient_user_id=claim.patient_user_id,
        subscriber_user_id=claim.subscriber_user_id,
        billing_provider_organization_id=claim.billing_provider_organization_id,
        rendering_provider_user_id=claim.rendering_provider_user_id,
        encounter_id=claim.encounter_id,
        claim_type=claim.claim_type.value,
        status=claim.status.value,
        service_from=claim.service_from,
        service_to=claim.service_to,
        total_charge_cents=claim.total_charge_cents,
        allowed_cents=claim.allowed_cents,
        paid_cents=claim.paid_cents,
        patient_responsibility_cents=claim.patient_responsibility_cents,
        currency=claim.currency,
        submitted_at=claim.submitted_at,
        adjudicated_at=claim.adjudicated_at,
        denial_reason_code=claim.denial_reason_code,
        line_count=line_count,
        created_at=claim.created_at,
    )


def _claim_line_read(line: ClaimLine) -> ClaimLineRead:
    return ClaimLineRead(
        id=line.id,
        line_number=line.line_number,
        service_date=line.service_date,
        service_code_system=line.service_code_system,
        service_code=line.service_code,
        service_display=line.service_display,
        modifiers=list(line.modifiers),
        units=line.units,
        charge_cents=line.charge_cents,
        allowed_cents=line.allowed_cents,
        paid_cents=line.paid_cents,
        copay_cents=line.copay_cents,
        coinsurance_cents=line.coinsurance_cents,
        deductible_cents=line.deductible_cents,
        diagnosis_pointers=list(line.diagnosis_pointers),
        adjustment_reason_codes=list(line.adjustment_reason_codes),
    )


def _claim_event_read(event: ClaimEvent) -> ClaimEventRead:
    return ClaimEventRead(
        id=event.id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        actor_user_id=event.actor_user_id,
        payload=dict(event.payload),
        occurred_at=event.occurred_at,
    )


def _application_read(application: PolicyApplication) -> ApplicationRead:
    return ApplicationRead(
        id=application.id,
        application_number=application.application_number,
        applicant_user_id=application.applicant_user_id,
        plan_id=application.plan_id,
        status=application.status.value,
        submitted_at=application.submitted_at,
        decision_at=application.decision_at,
        decline_reason=application.decline_reason,
        quoted_premium_cents=application.quoted_premium_cents,
        currency=application.currency,
        loyalty_points_redeemed=application.loyalty_points_redeemed,
        answers=dict(application.answers),
        created_at=application.created_at,
    )


def _ledger_read(entry: LoyaltyLedgerEntry) -> LoyaltyLedgerRead:
    return LoyaltyLedgerRead(
        id=entry.id,
        entry_type=entry.entry_type.value,
        points=entry.points,
        balance_after=entry.balance_after,
        reason=entry.reason,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        expires_at=entry.expires_at,
        occurred_at=entry.occurred_at,
    )


async def resolve_patient(db: AsyncSession, context: AuthContext, requested: UUID | None) -> UUID:
    """Resolve the patient a coverage read is about and authorise the caller."""
    target = requested or (context.user.id if is_patient(context) else None)
    if target is None:
        raise unprocessable("patient_user_id is required for non-patient callers")
    await assert_may_read_patient(db, context, target)
    profile = await db.scalar(
        select(PatientProfile.user_id).where(PatientProfile.user_id == target)
    )
    if profile is None:
        raise not_found("Patient")
    return target


# --------------------------------------------------------------------------- #
# Tab 1 — Insurance claim
# --------------------------------------------------------------------------- #


def _covers_patient(patient_user_id: UUID, as_of: date) -> ColumnElement[bool]:
    """Policy is the patient's: they subscribe to it or are an unexpired member."""
    member_exists = (
        select(PolicyMember.id)
        .where(
            PolicyMember.policy_id == Policy.id,
            PolicyMember.patient_user_id == patient_user_id,
            or_(PolicyMember.effective_to.is_(None), PolicyMember.effective_to >= as_of),
        )
        .exists()
    )
    return or_(member_exists, Policy.subscriber_user_id == patient_user_id)


def _member_relationship_column(patient_user_id: UUID, as_of: date) -> ColumnElement[Any]:
    return (
        select(PolicyMember.relationship)
        .where(
            PolicyMember.policy_id == Policy.id,
            PolicyMember.patient_user_id == patient_user_id,
            or_(PolicyMember.effective_to.is_(None), PolicyMember.effective_to >= as_of),
        )
        .order_by(PolicyMember.effective_from.desc())
        .limit(1)
        .scalar_subquery()
        .label("member_relationship")
    )


async def list_active_policies(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    request: Request | None = None,
) -> list[PolicySummary]:
    """Active policies covering the patient, with plan, product, and payer detail.

    A policy bought through the marketplace lands here the moment
    :func:`purchase_application` commits: that flow issues the policy with
    ``status='active'`` and writes the subscriber's ``policy_members`` row.
    """
    as_of = _today()
    rows = (
        await db.execute(
            select(
                Policy,
                InsurancePlan,
                InsuranceProduct,
                Organization,
                _member_relationship_column(patient_user_id, as_of),
            )
            .join(InsurancePlan, InsurancePlan.id == Policy.plan_id)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == Policy.payer_organization_id)
            .where(
                _covers_patient(patient_user_id, as_of),
                Policy.status == PolicyStatus.ACTIVE,
                or_(Policy.effective_to.is_(None), Policy.effective_to >= as_of),
            )
            .order_by(Policy.effective_from.desc(), Policy.policy_number)
        )
    ).all()

    items = [
        _policy_summary(policy, plan, product, payer, relationship)
        for policy, plan, product, payer, relationship in rows
    ]
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="policy",
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=len(items),
        request=request,
    )
    await db.commit()
    return items


async def _load_policy(
    db: AsyncSession, policy_id: UUID
) -> tuple[Policy, InsurancePlan, InsuranceProduct, Organization]:
    row = (
        await db.execute(
            select(Policy, InsurancePlan, InsuranceProduct, Organization)
            .join(InsurancePlan, InsurancePlan.id == Policy.plan_id)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == Policy.payer_organization_id)
            .where(Policy.id == policy_id)
        )
    ).first()
    if row is None:
        raise not_found("Policy")
    policy, plan, product, payer = row
    return policy, plan, product, payer


async def _policy_relationship(
    db: AsyncSession, policy: Policy, patient_user_id: UUID
) -> MemberRelationship | None:
    relationship = await db.scalar(
        select(PolicyMember.relationship)
        .where(
            PolicyMember.policy_id == policy.id,
            PolicyMember.patient_user_id == patient_user_id,
        )
        .order_by(PolicyMember.effective_from.desc())
        .limit(1)
    )
    if relationship is None and policy.subscriber_user_id != patient_user_id:
        raise not_found("Policy")
    return relationship


async def _benefit_rows(
    db: AsyncSession,
    plan_id: UUID,
    *,
    as_of: date,
    locale: str,
    reading_level: str,
) -> list[BenefitRow]:
    """Benefit grid for a plan joined to its plain-language explanations.

    One explanation per benefit is picked in SQL (a ``row_number`` window),
    preferring the requested reading level and then the most recently
    clinically reviewed row. Benefits with no explanation come back with
    ``plain_language = None`` rather than invented text.
    """
    preferred = (
        select(
            BenefitExplanation.id.label("explanation_id"),
            BenefitExplanation.plan_benefit_id.label("plan_benefit_id"),
            BenefitExplanation.locale.label("locale"),
            BenefitExplanation.reading_level.label("reading_level"),
            BenefitExplanation.summary_text.label("summary_text"),
            BenefitExplanation.example_scenario.label("example_scenario"),
            BenefitExplanation.generated_by.label("generated_by"),
            BenefitExplanation.model_version.label("model_version"),
            BenefitExplanation.reviewed_at.label("reviewed_at"),
            func.row_number()
            .over(
                partition_by=BenefitExplanation.plan_benefit_id,
                order_by=(
                    case((BenefitExplanation.reading_level == reading_level, 0), else_=1),
                    BenefitExplanation.reviewed_at.desc().nulls_last(),
                    BenefitExplanation.created_at.desc(),
                ),
            )
            .label("rank"),
        )
        .where(BenefitExplanation.locale == locale)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                PlanBenefit,
                preferred.c.explanation_id,
                preferred.c.locale,
                preferred.c.reading_level,
                preferred.c.summary_text,
                preferred.c.example_scenario,
                preferred.c.generated_by,
                preferred.c.model_version,
                preferred.c.reviewed_at,
            )
            .outerjoin(
                preferred,
                and_(
                    preferred.c.plan_benefit_id == PlanBenefit.id,
                    preferred.c.rank == 1,
                ),
            )
            .where(
                PlanBenefit.plan_id == plan_id,
                PlanBenefit.effective_from <= as_of,
                or_(PlanBenefit.effective_to.is_(None), PlanBenefit.effective_to >= as_of),
            )
            .order_by(PlanBenefit.service_category, PlanBenefit.network_tier, PlanBenefit.id)
        )
    ).all()

    benefits: list[BenefitRow] = []
    for row in rows:
        benefit = row[0]
        plain: BenefitPlainLanguage | None = None
        if row[1] is not None:
            plain = BenefitPlainLanguage(
                explanation_id=row[1],
                locale=row[2],
                reading_level=row[3],
                summary_text=row[4],
                example_scenario=dict(row[5] or {}),
                generated_by=row[6],
                model_version=row[7],
                reviewed_at=row[8],
            )
        benefits.append(
            BenefitRow(
                benefit_id=benefit.id,
                service_category=benefit.service_category,
                service_code_system=benefit.service_code_system,
                service_code=benefit.service_code,
                service_display=benefit.service_display,
                network_tier=benefit.network_tier.value,
                covered=benefit.covered,
                copay_cents=benefit.copay_cents,
                coinsurance_percent=benefit.coinsurance_percent,
                deductible_applies=benefit.deductible_applies,
                visit_limit_count=benefit.visit_limit_count,
                limit_period=benefit.limit_period.value if benefit.limit_period else None,
                prior_auth_required=benefit.prior_auth_required,
                waiting_period_days=benefit.waiting_period_days,
                exclusion_text=benefit.exclusion_text,
                effective_from=benefit.effective_from,
                effective_to=benefit.effective_to,
                plain_language=plain,
            )
        )
    return benefits


async def explain_policy(
    db: AsyncSession,
    context: AuthContext,
    *,
    policy_id: UUID,
    patient_user_id: UUID,
    locale: str,
    reading_level: str,
    benefit_year: int,
    request: Request | None = None,
) -> CoverageExplanation:
    """Structured benefit grid + grounded plain language + the patient's accumulators."""
    policy, plan, product, payer = await _load_policy(db, policy_id)
    relationship = await _policy_relationship(db, policy, patient_user_id)
    as_of = _today()
    benefits = await _benefit_rows(
        db, plan.id, as_of=as_of, locale=locale, reading_level=reading_level
    )

    accumulator_rows = (
        await db.scalars(
            select(BenefitAccumulator)
            .where(
                BenefitAccumulator.policy_id == policy.id,
                BenefitAccumulator.patient_user_id == patient_user_id,
                BenefitAccumulator.benefit_year == benefit_year,
            )
            .order_by(BenefitAccumulator.accumulator_type)
        )
    ).all()
    accumulators = [
        AccumulatorRead(
            id=row.id,
            accumulator_type=row.accumulator_type.value,
            benefit_year=row.benefit_year,
            limit_cents=row.limit_cents,
            consumed_cents=row.consumed_cents,
            remaining_cents=(
                None if row.limit_cents is None else max(0, row.limit_cents - row.consumed_cents)
            ),
            limit_count=row.limit_count,
            consumed_count=row.consumed_count,
            as_of=row.as_of,
        )
        for row in accumulator_rows
    ]
    by_type = {row.accumulator_type.value: row for row in accumulator_rows}
    deductible = by_type.get("individual_deductible")
    oop = by_type.get("individual_oop")

    explained = sum(1 for benefit in benefits if benefit.plain_language is not None)
    result = CoverageExplanation(
        policy=_policy_summary(policy, plan, product, payer, relationship),
        patient_user_id=patient_user_id,
        locale=locale,
        reading_level=reading_level,
        benefit_year=benefit_year,
        as_of=as_of,
        benefits=benefits,
        benefits_with_plain_language=explained,
        benefits_without_plain_language=len(benefits) - explained,
        accumulators=accumulators,
        deductible_consumed_cents=deductible.consumed_cents if deductible else 0,
        deductible_limit_cents=(
            deductible.limit_cents if deductible else plan.individual_deductible_cents
        ),
        oop_consumed_cents=oop.consumed_cents if oop else 0,
        oop_limit_cents=oop.limit_cents if oop else plan.individual_oop_max_cents,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="benefit_accumulator",
        resource_id=policy.id,
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=len(accumulators),
        request=request,
    )
    await db.commit()
    return result


async def claim_assistance(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    request: Request | None = None,
) -> ClaimAssistance:
    """Helpline card: number and hours from ``system_settings`` plus what to have ready."""
    setting = await db.get(SystemSetting, HELPLINE_SETTING_KEY)
    raw: dict[str, Any] = dict(setting.value) if setting is not None else {}
    phone = str(raw.get("phone") or DEFAULT_HELPLINE_PHONE)
    hours = str(raw.get("hours") or DEFAULT_HELPLINE_HOURS)
    languages = [str(item) for item in raw.get("languages") or DEFAULT_HELPLINE_LANGUAGES]
    checklist = [str(item) for item in raw.get("what_to_have_ready") or DEFAULT_CLAIM_CHECKLIST]

    as_of = _today()
    policy_rows = (
        await db.execute(
            select(Policy.id, Policy.policy_number, Policy.member_id, Organization.legal_name)
            .join(Organization, Organization.id == Policy.payer_organization_id)
            .where(
                _covers_patient(patient_user_id, as_of),
                Policy.status == PolicyStatus.ACTIVE,
                or_(Policy.effective_to.is_(None), Policy.effective_to >= as_of),
            )
            .order_by(Policy.effective_from.desc())
        )
    ).all()
    open_claims = await db.scalar(
        select(func.count())
        .select_from(Claim)
        .where(
            Claim.patient_user_id == patient_user_id,
            Claim.status.in_(OPEN_CLAIM_STATUSES),
        )
    )

    card = ClaimAssistance(
        phone=phone,
        hours=hours,
        languages=languages,
        what_to_have_ready=checklist,
        source="system_setting" if setting is not None else "default",
        your_policies=[
            ClaimAssistancePolicy(
                policy_id=policy_id,
                policy_number=policy_number,
                member_id=member_id,
                payer_name=payer_name,
            )
            for policy_id, policy_number, member_id, payer_name in policy_rows
        ],
        open_claim_count=int(open_claims or 0),
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="claim_assistance",
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=len(card.your_policies),
        request=request,
    )
    await db.commit()
    return card


async def list_claims(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    patient_user_id: UUID | None = None,
    policy_id: UUID | None = None,
    status: str | None = None,
    service_from: date | None = None,
    service_to: date | None = None,
    request: Request | None = None,
) -> Page[ClaimSummary]:
    """Claims the caller may read, newest service date first."""
    if patient_user_id is not None:
        await assert_may_read_patient(db, context, patient_user_id)
        allowed: set[UUID] | None = {patient_user_id}
    else:
        allowed = await consent_scoped_patients(db, context)

    query = apply_patient_scope(select(Claim), Claim, allowed)
    if policy_id is not None:
        query = query.where(Claim.policy_id == policy_id)
    if status is not None:
        try:
            query = query.where(Claim.status == ClaimStatus(status))
        except ValueError as exc:
            raise unprocessable(f"Unknown claim status '{status}'") from exc
    if service_from is not None:
        query = query.where(Claim.service_to >= service_from)
    if service_to is not None:
        query = query.where(Claim.service_from <= service_to)

    line_count = (
        select(func.count(ClaimLine.id))
        .where(ClaimLine.claim_id == Claim.id)
        .correlate(Claim)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            query.add_columns(line_count)
            .order_by(Claim.service_from.desc(), Claim.claim_number)
            .limit(page.limit + 1)
            .offset(page.offset)
        )
    ).all()

    items = [_claim_summary(claim, int(count or 0)) for claim, count in rows]
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[item.patient_user_id for item in items],
        resource_type="claim",
        purpose_of_use="HPAYMT",
        request=request,
    )
    await db.commit()
    return paginate(items, page)


async def get_claim(
    db: AsyncSession,
    context: AuthContext,
    *,
    claim_id: UUID,
    request: Request | None = None,
) -> ClaimDetail:
    """A claim with its lines and its full append-only event timeline."""
    claim = await _load_claim(db, context, claim_id)
    lines = (
        await db.scalars(
            select(ClaimLine).where(ClaimLine.claim_id == claim.id).order_by(ClaimLine.line_number)
        )
    ).all()
    events = (
        await db.scalars(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.occurred_at, ClaimEvent.created_at)
        )
    ).all()

    detail = ClaimDetail(
        **_claim_summary(claim, len(lines)).model_dump(),
        lines=[_claim_line_read(line) for line in lines],
        events=[_claim_event_read(event) for event in events],
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=claim.patient_user_id,
        resource_type="claim",
        resource_id=claim.id,
        purpose_of_use=_purpose(context, claim.patient_user_id),
        result_count=1,
        request=request,
    )
    await db.commit()
    return detail


async def _load_claim(db: AsyncSession, context: AuthContext, claim_id: UUID) -> Claim:
    allowed = await consent_scoped_patients(db, context)
    claim = await db.scalar(
        apply_patient_scope(select(Claim), Claim, allowed).where(Claim.id == claim_id)
    )
    if claim is None:
        raise not_found("Claim")
    return claim


async def create_claim(
    db: AsyncSession,
    context: AuthContext,
    payload: ClaimCreate,
    *,
    request: Request | None = None,
) -> ClaimDetail:
    """Initiate a claim: header, lines, and the first append-only claim event."""
    patient_user_id = await resolve_patient(db, context, payload.patient_user_id)
    policy, _plan, _product, _payer = await _load_policy(db, payload.policy_id)
    await _policy_relationship(db, policy, patient_user_id)

    if payload.service_to < payload.service_from:
        raise unprocessable("service_to must not precede service_from")
    if payload.service_from < policy.effective_from:
        raise unprocessable(
            f"Service dates start before the policy took effect on {policy.effective_from}"
        )
    if policy.effective_to is not None and payload.service_to > policy.effective_to:
        raise unprocessable(f"Service dates run past the policy end date {policy.effective_to}")
    for line in payload.lines:
        if not payload.service_from <= line.service_date <= payload.service_to:
            raise unprocessable(
                f"Line service date {line.service_date} falls outside the claim service period"
            )

    organization = await db.scalar(
        select(Organization.id).where(Organization.id == payload.billing_provider_organization_id)
    )
    if organization is None:
        raise not_found("Billing provider organization")
    if payload.rendering_provider_user_id is not None:
        provider = await db.scalar(
            select(DoctorProfile.user_id).where(
                DoctorProfile.user_id == payload.rendering_provider_user_id
            )
        )
        if provider is None:
            raise not_found("Rendering provider")
    if payload.encounter_id is not None:
        encounter = await db.scalar(
            select(Encounter.id).where(
                Encounter.id == payload.encounter_id,
                Encounter.patient_user_id == patient_user_id,
            )
        )
        if encounter is None:
            raise not_found("Encounter")

    now = datetime.now(UTC)
    submitted = payload.submit
    claim = Claim(
        tenant_id=context.tenant_id,
        claim_number=_reference("CLM"),
        policy_id=policy.id,
        patient_user_id=patient_user_id,
        subscriber_user_id=policy.subscriber_user_id,
        billing_provider_organization_id=payload.billing_provider_organization_id,
        rendering_provider_user_id=payload.rendering_provider_user_id,
        encounter_id=payload.encounter_id,
        claim_type=ClaimType(payload.claim_type),
        service_from=payload.service_from,
        service_to=payload.service_to,
        total_charge_cents=sum(line.charge_cents for line in payload.lines),
        currency=policy.currency,
        status=ClaimStatus.SUBMITTED if submitted else ClaimStatus.DRAFT,
        submitted_at=now if submitted else None,
    )
    db.add(claim)
    await db.flush()

    lines = [
        ClaimLine(
            claim_id=claim.id,
            line_number=index,
            service_date=line.service_date,
            service_code_system=line.service_code_system,
            service_code=line.service_code,
            service_display=line.service_display,
            modifiers=list(line.modifiers),
            units=line.units,
            charge_cents=line.charge_cents,
            diagnosis_pointers=list(line.diagnosis_pointers),
        )
        for index, line in enumerate(payload.lines, start=1)
    ]
    db.add_all(lines)

    event = ClaimEvent(
        tenant_id=context.tenant_id,
        claim_id=claim.id,
        event_type="claim.submitted" if submitted else "claim.created",
        from_status=None,
        to_status=claim.status.value,
        actor_user_id=context.user.id,
        payload={
            "line_count": len(lines),
            "total_charge_cents": claim.total_charge_cents,
            "currency": claim.currency,
            "note": payload.note,
        },
        occurred_at=now,
    )
    db.add(event)
    await db.flush()
    await db.refresh(claim)
    for created_line in lines:
        await db.refresh(created_line)
    await db.refresh(event)

    detail = ClaimDetail(
        **_claim_summary(claim, len(lines)).model_dump(),
        lines=[_claim_line_read(created_line) for created_line in lines],
        events=[_claim_event_read(event)],
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="claim",
        resource_id=claim.id,
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=1,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="coverage.claim.created",
        subject_user_id=patient_user_id,
        resource_id=claim.id,
        event_data={
            "claim_number": claim.claim_number,
            "policy_id": str(policy.id),
            "status": claim.status.value,
            "line_count": len(lines),
        },
        request=request,
    )
    await db.commit()
    return detail


async def attach_claim_documents(
    db: AsyncSession,
    context: AuthContext,
    *,
    claim_id: UUID,
    payload: ClaimDocumentAttach,
    request: Request | None = None,
) -> list[DocumentLinkRead]:
    """Link stored documents to a claim; re-attaching an existing link is a no-op."""
    claim = await _load_claim(db, context, claim_id)
    assets = (
        await db.scalars(
            tenant_scoped(select(DocumentAsset), DocumentAsset, context).where(
                DocumentAsset.id.in_(payload.document_asset_ids)
            )
        )
    ).all()
    found = {asset.id: asset for asset in assets}
    missing = [str(item) for item in payload.document_asset_ids if item not in found]
    if missing:
        raise not_found(f"Document asset(s) {', '.join(missing)}")

    existing = set(
        (
            await db.scalars(
                select(DocumentLink.document_asset_id).where(
                    DocumentLink.subject_type == "claim",
                    DocumentLink.subject_id == claim.id,
                    DocumentLink.document_asset_id.in_(payload.document_asset_ids),
                )
            )
        ).all()
    )
    created: list[DocumentLink] = []
    for asset_id in payload.document_asset_ids:
        if asset_id in existing:
            continue
        link = DocumentLink(
            tenant_id=context.tenant_id,
            document_asset_id=asset_id,
            subject_type="claim",
            subject_id=claim.id,
            link_type=DocumentLinkType(payload.link_type),
            linked_by_user_id=context.user.id,
        )
        db.add(link)
        created.append(link)
    if created:
        await db.flush()
        for link in created:
            await db.refresh(link)

    links = (
        await db.scalars(
            select(DocumentLink)
            .where(DocumentLink.subject_type == "claim", DocumentLink.subject_id == claim.id)
            .order_by(DocumentLink.created_at)
        )
    ).all()
    asset_rows = (
        await db.execute(
            select(
                DocumentAsset.id,
                DocumentAsset.filename,
                DocumentAsset.content_type,
                DocumentAsset.byte_size,
            ).where(DocumentAsset.id.in_([link.document_asset_id for link in links]))
        )
    ).all()
    metadata = {row[0]: (row[1], row[2], row[3]) for row in asset_rows}

    items = [
        DocumentLinkRead(
            id=link.id,
            document_asset_id=link.document_asset_id,
            subject_type=link.subject_type,
            subject_id=link.subject_id,
            link_type=link.link_type.value,
            linked_by_user_id=link.linked_by_user_id,
            filename=metadata[link.document_asset_id][0],
            content_type=metadata[link.document_asset_id][1],
            byte_size=metadata[link.document_asset_id][2],
            created_at=link.created_at,
        )
        for link in links
        if link.document_asset_id in metadata
    ]
    await record_phi_access(
        db,
        context,
        patient_user_id=claim.patient_user_id,
        resource_type="claim_document",
        resource_id=claim.id,
        purpose_of_use=_purpose(context, claim.patient_user_id),
        result_count=len(items),
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="coverage.claim.documents_attached",
        subject_user_id=claim.patient_user_id,
        resource_id=claim.id,
        event_data={
            "attached": [str(link.document_asset_id) for link in created],
            "link_type": payload.link_type,
        },
        request=request,
    )
    await db.commit()
    return items


# --------------------------------------------------------------------------- #
# Tab 2 — Buy insurance
# --------------------------------------------------------------------------- #


async def patient_features(db: AsyncSession, patient_user_id: UUID) -> PatientRiskFeatures:
    """One round trip for every ranking input the model uses."""
    since = _today() - timedelta(days=CLAIM_LOOKBACK_DAYS)
    active_conditions = (
        select(func.count())
        .select_from(Condition)
        .where(
            Condition.patient_user_id == patient_user_id,
            Condition.superseded_at.is_(None),
            Condition.clinical_status.in_(ACTIVE_CONDITION_STATUSES),
            Condition.verification_status != VerificationStatus.ENTERED_IN_ERROR,
        )
        .scalar_subquery()
    )
    chronic_conditions = (
        select(func.count())
        .select_from(Condition)
        .where(
            Condition.patient_user_id == patient_user_id,
            Condition.superseded_at.is_(None),
            Condition.category == ConditionCategory.PROBLEM_LIST_ITEM,
            Condition.clinical_status.in_(ACTIVE_CONDITION_STATUSES),
            Condition.verification_status != VerificationStatus.ENTERED_IN_ERROR,
        )
        .scalar_subquery()
    )
    allergies = (
        select(func.count())
        .select_from(AllergyIntolerance)
        .where(
            AllergyIntolerance.patient_user_id == patient_user_id,
            AllergyIntolerance.superseded_at.is_(None),
            AllergyIntolerance.clinical_status == ClinicalStatus.ACTIVE,
            AllergyIntolerance.verification_status != AllergyVerificationStatus.ENTERED_IN_ERROR,
        )
        .scalar_subquery()
    )
    recent_claims = (
        select(func.count())
        .select_from(Claim)
        .where(Claim.patient_user_id == patient_user_id, Claim.service_from >= since)
        .scalar_subquery()
    )
    recent_charges = (
        select(func.coalesce(func.sum(Claim.total_charge_cents), 0))
        .select_from(Claim)
        .where(Claim.patient_user_id == patient_user_id, Claim.service_from >= since)
        .scalar_subquery()
    )
    loyalty_balance = (
        select(LoyaltyAccount.balance_points)
        .where(LoyaltyAccount.user_id == patient_user_id)
        .limit(1)
        .scalar_subquery()
    )

    row = (
        await db.execute(
            select(
                PatientProfile.date_of_birth,
                active_conditions,
                chronic_conditions,
                allergies,
                recent_claims,
                recent_charges,
                func.coalesce(loyalty_balance, 0),
            ).where(PatientProfile.user_id == patient_user_id)
        )
    ).first()
    if row is None:
        raise not_found("Patient")

    born, condition_count, chronic_count, allergy_count, claim_count, charges, points = row
    age: int | None = None
    if born is not None:
        today = _today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return PatientRiskFeatures(
        patient_user_id=patient_user_id,
        age_years=age,
        active_condition_count=int(condition_count or 0),
        chronic_condition_count=int(chronic_count or 0),
        active_allergy_count=int(allergy_count or 0),
        recent_claim_count=int(claim_count or 0),
        recent_claim_charge_cents=int(charges or 0),
        loyalty_balance_points=int(points or 0),
    )


def _marketplace_filters(
    as_of: date,
    *,
    product_type: str | None,
    metal_tier: str | None,
    payer_organization_id: UUID | None,
    currency: str | None,
    max_premium_cents: int | None,
    max_deductible_cents: int | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        InsurancePlan.is_active.is_(True),
        InsuranceProduct.is_active.is_(True),
        Organization.status == "active",
        InsurancePlan.effective_from <= as_of,
        or_(InsurancePlan.effective_to.is_(None), InsurancePlan.effective_to >= as_of),
    ]
    if product_type is not None:
        filters.append(InsuranceProduct.product_type == product_type)
    if metal_tier is not None:
        filters.append(InsurancePlan.metal_tier == metal_tier)
    if payer_organization_id is not None:
        filters.append(InsuranceProduct.payer_organization_id == payer_organization_id)
    if currency is not None:
        filters.append(InsurancePlan.currency == currency.upper())
    if max_premium_cents is not None:
        filters.append(InsurancePlan.premium_cents <= max_premium_cents)
    if max_deductible_cents is not None:
        filters.append(
            func.coalesce(InsurancePlan.individual_deductible_cents, 0) <= max_deductible_cents
        )
    return filters


def _normalise(value: int, low: int | None, high: int | None) -> float:
    if low is None or high is None or high <= low:
        return 0.0
    return _clamp((value - low) / (high - low))


def _rank_plan(
    plan: InsurancePlan,
    features: PatientRiskFeatures,
    bounds: tuple[int | None, int | None, int | None, int | None, int | None, int | None],
    benefit_stats: tuple[int, int, Decimal | None, int],
) -> tuple[Decimal, Decimal, Decimal, int, int, list[str]]:
    """Score one plan; returns (score, history, loyalty, points_applied, annual_cost, codes)."""
    min_premium, max_premium, min_deduct, max_deduct, min_oop, max_oop = bounds
    benefit_count, covered_count, avg_coinsurance, prior_auth_count = benefit_stats

    premium_norm = _normalise(plan.premium_cents, min_premium, max_premium)
    deductible = plan.individual_deductible_cents or 0
    deductible_norm = _normalise(deductible, min_deduct, max_deduct)
    oop = plan.individual_oop_max_cents or 0
    oop_norm = _normalise(oop, min_oop, max_oop)
    covered_ratio = covered_count / benefit_count if benefit_count else 0.5
    coinsurance_norm = float(avg_coinsurance) / 100.0 if avg_coinsurance is not None else 0.0
    prior_auth_ratio = prior_auth_count / benefit_count if benefit_count else 0.0

    richness = (
        0.35 * (1.0 - deductible_norm)
        + 0.25 * (1.0 - oop_norm)
        + 0.25 * covered_ratio
        + 0.10 * (1.0 - _clamp(coinsurance_norm))
        + 0.05 * (1.0 - prior_auth_ratio)
    )
    affordability = 1.0 - premium_norm
    need = _clamp(
        0.15 * features.active_condition_count
        + 0.10 * features.recent_claim_count
        + (0.20 if (features.age_years or 0) >= 60 else 0.0)
        + 0.03 * features.active_allergy_count
    )
    history = _clamp(need * richness + (1.0 - need) * affordability)

    points_applied = min(features.loyalty_balance_points, plan.premium_cents)
    loyalty = _clamp(points_applied / plan.premium_cents) if plan.premium_cents else 0.0

    expected_spend = features.recent_claim_charge_cents
    if oop:
        expected_spend = min(expected_spend, oop)
    annual_cost = plan.premium_cents * ANNUAL_PREMIUM_PERIODS + min(deductible, expected_spend)

    codes: list[str] = []
    if need >= 0.5 and richness >= 0.6:
        codes.append("RICH_COVERAGE_FOR_ACTIVE_CONDITIONS")
    if features.recent_claim_count >= 3:
        codes.append("HIGH_RECENT_CLAIM_VOLUME")
    if (features.age_years or 0) >= 60:
        codes.append("SENIOR_UTILISATION_WEIGHTING")
    if features.active_allergy_count >= 3:
        codes.append("ALLERGY_BURDEN_WEIGHTED")
    if premium_norm <= 0.25:
        codes.append("LOW_PREMIUM_IN_MARKET")
    if deductible_norm <= 0.25 and plan.individual_deductible_cents is not None:
        codes.append("LOW_DEDUCTIBLE")
    if oop_norm <= 0.25 and plan.individual_oop_max_cents is not None:
        codes.append("LOW_OUT_OF_POCKET_MAX")
    if benefit_count and covered_ratio >= 0.8:
        codes.append("BROAD_BENEFIT_COVERAGE")
    if benefit_count and prior_auth_ratio <= 0.2:
        codes.append("MINIMAL_PRIOR_AUTH")
    if points_applied > 0:
        codes.append("LOYALTY_POINTS_OFFSET")
    if not codes:
        codes.append("BASELINE_MARKET_MATCH")

    score = 0.75 * history + 0.25 * loyalty
    return _score(score), _score(history), _score(loyalty), points_applied, annual_cost, codes


async def marketplace(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    page: Pagination,
    sort: MarketplaceSort = "recommended",
    product_type: str | None = None,
    metal_tier: str | None = None,
    payer_organization_id: UUID | None = None,
    currency: str | None = None,
    max_premium_cents: int | None = None,
    max_deductible_cents: int | None = None,
    request: Request | None = None,
) -> MarketplaceResponse:
    """Rank every participating payer's open plans for one patient and persist the result."""
    as_of = _today()
    filters = _marketplace_filters(
        as_of,
        product_type=product_type,
        metal_tier=metal_tier,
        payer_organization_id=payer_organization_id,
        currency=currency,
        max_premium_cents=max_premium_cents,
        max_deductible_cents=max_deductible_cents,
    )
    features = await patient_features(db, patient_user_id)

    candidate_rows = (
        await db.execute(
            select(InsurancePlan, InsuranceProduct, Organization)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == InsuranceProduct.payer_organization_id)
            .where(*filters)
            .order_by(InsurancePlan.premium_cents, InsurancePlan.id)
            .limit(MAX_MARKETPLACE_CANDIDATES)
        )
    ).all()

    generated_at = datetime.now(UTC)
    if not candidate_rows:
        await record_phi_access(
            db,
            context,
            patient_user_id=patient_user_id,
            resource_type="plan_recommendation",
            purpose_of_use=_purpose(context, patient_user_id),
            result_count=0,
            request=request,
        )
        await db.commit()
        return MarketplaceResponse(
            patient_user_id=patient_user_id,
            model_version=RECOMMENDER_VERSION,
            generated_at=generated_at,
            sort=sort,
            features=features,
            candidates_scored=0,
            plans=paginate([], page),
        )

    bounds_row = (
        await db.execute(
            select(
                func.min(InsurancePlan.premium_cents),
                func.max(InsurancePlan.premium_cents),
                func.min(InsurancePlan.individual_deductible_cents),
                func.max(InsurancePlan.individual_deductible_cents),
                func.min(InsurancePlan.individual_oop_max_cents),
                func.max(InsurancePlan.individual_oop_max_cents),
            )
            .select_from(InsurancePlan)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == InsuranceProduct.payer_organization_id)
            .where(*filters)
        )
    ).one()
    bounds = (
        bounds_row[0],
        bounds_row[1],
        bounds_row[2],
        bounds_row[3],
        bounds_row[4],
        bounds_row[5],
    )

    plan_ids = [plan.id for plan, _product, _payer in candidate_rows]
    stats_rows = (
        await db.execute(
            select(
                PlanBenefit.plan_id,
                func.count().label("benefit_count"),
                func.count().filter(PlanBenefit.covered.is_(True)).label("covered_count"),
                func.avg(PlanBenefit.coinsurance_percent).label("avg_coinsurance"),
                func.count()
                .filter(PlanBenefit.prior_auth_required.is_(True))
                .label("prior_auth_count"),
            )
            .where(
                PlanBenefit.plan_id.in_(plan_ids),
                PlanBenefit.network_tier == NetworkTier.IN_NETWORK,
                PlanBenefit.effective_from <= as_of,
                or_(PlanBenefit.effective_to.is_(None), PlanBenefit.effective_to >= as_of),
            )
            .group_by(PlanBenefit.plan_id)
        )
    ).all()
    stats: dict[UUID, tuple[int, int, Decimal | None, int]] = {
        row[0]: (int(row[1] or 0), int(row[2] or 0), row[3], int(row[4] or 0)) for row in stats_rows
    }

    scored: list[tuple[Decimal, int, str, InsurancePlan, InsuranceProduct, Organization, Any]] = []
    for plan, product, payer in candidate_rows:
        benefit_stats = stats.get(plan.id, (0, 0, None, 0))
        score, history, loyalty, points, annual_cost, codes = _rank_plan(
            plan, features, bounds, benefit_stats
        )
        scored.append(
            (
                score,
                plan.premium_cents,
                plan.name,
                plan,
                product,
                payer,
                (history, loyalty, points, annual_cost, codes, benefit_stats),
            )
        )
    scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))

    feature_snapshot = features.model_dump(mode="json")
    plans: list[MarketplacePlan] = []
    for rank, entry in enumerate(scored, start=1):
        score, _premium, _name, plan, product, payer, extra = entry
        history, loyalty, points, annual_cost, codes, benefit_stats = extra
        # The primary key is a Python-side default, so it is assigned here to
        # keep the persisted row and the response body pointing at each other.
        recommendation_id = uuid4()
        recommendation = PlanRecommendation(
            id=recommendation_id,
            tenant_id=context.tenant_id,
            patient_user_id=patient_user_id,
            plan_id=plan.id,
            rank=rank,
            score=score,
            history_score=history,
            loyalty_score=loyalty,
            loyalty_points_applied=points,
            estimated_premium_cents=plan.premium_cents,
            estimated_annual_cost_cents=annual_cost,
            currency=plan.currency,
            reason_codes=list(codes),
            feature_snapshot=feature_snapshot,
            model_version=RECOMMENDER_VERSION,
            generated_at=generated_at,
            expires_at=generated_at + timedelta(days=RECOMMENDATION_TTL_DAYS),
        )
        db.add(recommendation)
        plans.append(
            MarketplacePlan(
                plan=_plan_summary(plan, product, payer),
                recommendation_id=recommendation_id,
                rank=rank,
                score=score,
                history_score=history,
                loyalty_score=loyalty,
                loyalty_points_applied=points,
                estimated_annual_cost_cents=annual_cost,
                reason_codes=list(codes),
                reasons=[
                    RecommendationReason(code=code, detail=REASON_TEXT[code]) for code in codes
                ],
                benefit_count=benefit_stats[0],
                covered_benefit_count=benefit_stats[1],
            )
        )

    if sort == "premium_asc":
        plans.sort(key=lambda item: (item.plan.premium_cents, item.rank))
    elif sort == "deductible_asc":
        plans.sort(
            key=lambda item: (
                item.plan.individual_deductible_cents
                if item.plan.individual_deductible_cents is not None
                else 2**31 - 1,
                item.rank,
            )
        )

    window = plans[page.offset : page.offset + page.limit + 1]
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="plan_recommendation",
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=len(plans),
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="coverage.marketplace.ranked",
        subject_user_id=patient_user_id,
        event_data={
            "model_version": RECOMMENDER_VERSION,
            "candidates_scored": len(plans),
            "sort": sort,
        },
        request=request,
    )
    await db.commit()
    return MarketplaceResponse(
        patient_user_id=patient_user_id,
        model_version=RECOMMENDER_VERSION,
        generated_at=generated_at,
        sort=sort,
        features=features,
        candidates_scored=len(plans),
        plans=paginate(window, page, total=len(plans)),
    )


async def get_plan(
    db: AsyncSession,
    *,
    plan_id: UUID,
    locale: str,
    reading_level: str,
) -> PlanDetail:
    """Plan detail plus the full benefit grid for both network tiers."""
    row = (
        await db.execute(
            select(InsurancePlan, InsuranceProduct, Organization)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == InsuranceProduct.payer_organization_id)
            .where(InsurancePlan.id == plan_id)
        )
    ).first()
    if row is None:
        raise not_found("Insurance plan")
    plan, product, payer = row
    as_of = _today()
    return PlanDetail(
        plan=_plan_summary(plan, product, payer),
        as_of=as_of,
        locale=locale,
        reading_level=reading_level,
        benefits=await _benefit_rows(
            db, plan.id, as_of=as_of, locale=locale, reading_level=reading_level
        ),
    )


async def create_application(
    db: AsyncSession,
    context: AuthContext,
    payload: ApplicationCreate,
    *,
    request: Request | None = None,
) -> ApplicationRead:
    """Collect the applicant's details and open a submitted policy application."""
    applicant_id = context.user.id
    profile = await db.scalar(
        select(PatientProfile.user_id).where(PatientProfile.user_id == applicant_id)
    )
    if profile is None:
        raise unprocessable("Only patient accounts can apply for a policy")

    as_of = _today()
    row = (
        await db.execute(
            select(InsurancePlan, InsuranceProduct, Organization)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == InsuranceProduct.payer_organization_id)
            .where(
                InsurancePlan.id == payload.plan_id,
                InsurancePlan.is_active.is_(True),
                InsuranceProduct.is_active.is_(True),
                Organization.status == "active",
                InsurancePlan.effective_from <= as_of,
                or_(InsurancePlan.effective_to.is_(None), InsurancePlan.effective_to >= as_of),
            )
        )
    ).first()
    if row is None:
        raise not_found("Insurance plan")
    plan, _product, _payer = row

    if payload.loyalty_points_to_redeem:
        balance = await db.scalar(
            select(LoyaltyAccount.balance_points).where(LoyaltyAccount.user_id == applicant_id)
        )
        if payload.loyalty_points_to_redeem > int(balance or 0):
            raise unprocessable("Loyalty points to redeem exceed the available balance")

    now = datetime.now(UTC)
    application = PolicyApplication(
        tenant_id=context.tenant_id,
        applicant_user_id=applicant_id,
        plan_id=plan.id,
        application_number=_reference("APP"),
        status=PolicyApplicationStatus.SUBMITTED,
        submitted_at=now,
        quoted_premium_cents=plan.premium_cents,
        currency=plan.currency,
        loyalty_points_redeemed=payload.loyalty_points_to_redeem,
        answers={
            "applicant": payload.applicant.model_dump(mode="json"),
            "answers": payload.answers,
        },
    )
    db.add(application)
    await db.flush()
    await db.refresh(application)

    result = _application_read(application)
    await record_phi_access(
        db,
        context,
        patient_user_id=applicant_id,
        resource_type="policy_application",
        resource_id=application.id,
        purpose_of_use=_purpose(context, applicant_id),
        result_count=1,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="coverage.application.created",
        subject_user_id=applicant_id,
        resource_id=application.id,
        event_data={
            "application_number": application.application_number,
            "plan_id": str(plan.id),
            "quoted_premium_cents": plan.premium_cents,
            "currency": plan.currency,
        },
        request=request,
    )
    await db.commit()
    return result


async def _loyalty_account(
    db: AsyncSession, context: AuthContext, user_id: UUID, *, for_update: bool
) -> LoyaltyAccount:
    query = select(LoyaltyAccount).where(LoyaltyAccount.user_id == user_id)
    if for_update:
        query = query.with_for_update()
    account = await db.scalar(query)
    if account is None:
        account = LoyaltyAccount(
            tenant_id=context.tenant_id,
            user_id=user_id,
            program="default",
            balance_points=0,
            lifetime_points=0,
            status="active",
        )
        db.add(account)
        await db.flush()
    return account


async def purchase_application(
    db: AsyncSession,
    context: AuthContext,
    *,
    application_id: UUID,
    payload: PurchaseRequest,
    request: Request | None = None,
) -> PurchaseResult:
    """Issue the policy, members, premium schedule, and loyalty accrual atomically."""
    application = await db.scalar(
        select(PolicyApplication).where(PolicyApplication.id == application_id).with_for_update()
    )
    if application is None:
        raise not_found("Policy application")
    if application.applicant_user_id != context.user.id:
        if is_patient(context):
            # A patient may only complete their own application.
            raise not_found("Policy application")
        await assert_may_read_patient(db, context, application.applicant_user_id)

    subscriber_id = application.applicant_user_id
    existing_policy = await db.scalar(select(Policy).where(Policy.application_id == application.id))
    if existing_policy is not None:
        # Idempotent replay: the purchase already completed.
        return await _purchase_result(
            db, context, application, existing_policy, already_issued=True, request=request
        )

    assert_transition(
        application.status.value, PolicyApplicationStatus.ISSUED.value, APPLICATION_TRANSITIONS
    )

    row = (
        await db.execute(
            select(InsurancePlan, InsuranceProduct, Organization)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .join(Organization, Organization.id == InsuranceProduct.payer_organization_id)
            .where(InsurancePlan.id == application.plan_id)
        )
    ).first()
    if row is None:
        raise not_found("Insurance plan")
    plan, product, payer = row

    today = _today()
    effective_from = payload.effective_from or today
    if effective_from < today:
        raise unprocessable("effective_from cannot be in the past")
    effective_to = _add_months(effective_from, plan.term_months) - timedelta(days=1)
    frequency = PremiumFrequency(payload.premium_frequency)
    step_months = _FREQUENCY_MONTHS[frequency]
    if plan.term_months < step_months:
        raise unprocessable(
            f"{payload.premium_frequency} billing does not fit a {plan.term_months}-month term"
        )

    policy = Policy(
        tenant_id=context.tenant_id,
        policy_number=_reference("POL"),
        plan_id=plan.id,
        application_id=application.id,
        subscriber_user_id=subscriber_id,
        member_id=_reference("MBR"),
        payer_organization_id=product.payer_organization_id,
        status=PolicyStatus.ACTIVE,
        effective_from=effective_from,
        effective_to=effective_to,
        premium_cents=plan.premium_cents,
        currency=plan.currency,
        premium_frequency=frequency,
    )
    db.add(policy)
    await db.flush()

    members = [
        PolicyMember(
            tenant_id=context.tenant_id,
            policy_id=policy.id,
            patient_user_id=subscriber_id,
            relationship=MemberRelationship.SELF,
            member_suffix="00",
            effective_from=effective_from,
            effective_to=effective_to,
        )
    ]
    for index, dependent in enumerate(payload.members, start=1):
        if dependent.patient_user_id == subscriber_id:
            raise unprocessable("The subscriber is already enrolled as the primary member")
        await assert_may_read_patient(db, context, dependent.patient_user_id)
        dependent_profile = await db.scalar(
            select(PatientProfile.user_id).where(
                PatientProfile.user_id == dependent.patient_user_id
            )
        )
        if dependent_profile is None:
            raise not_found("Dependent patient")
        members.append(
            PolicyMember(
                tenant_id=context.tenant_id,
                policy_id=policy.id,
                patient_user_id=dependent.patient_user_id,
                relationship=MemberRelationship(dependent.relationship),
                member_suffix=f"{index:02d}",
                effective_from=effective_from,
                effective_to=effective_to,
            )
        )
    db.add_all(members)

    account = await _loyalty_account(db, context, subscriber_id, for_update=True)
    redeemed = application.loyalty_points_redeemed
    if redeemed > account.balance_points:
        raise conflict("Loyalty balance no longer covers the redemption on this application")

    instalment_count = max(1, plan.term_months // step_months)
    discount_cents = min(redeemed * REDEMPTION_CENTS_PER_POINT, plan.premium_cents)
    schedule: list[PremiumSchedule] = []
    for index in range(instalment_count):
        amount = plan.premium_cents - (discount_cents if index == 0 else 0)
        schedule.append(
            PremiumSchedule(
                tenant_id=context.tenant_id,
                policy_id=policy.id,
                due_date=_add_months(effective_from, index * step_months),
                amount_cents=max(0, amount),
                currency=plan.currency,
                status="due",
            )
        )
    db.add_all(schedule)

    now = datetime.now(UTC)
    ledger: list[LoyaltyLedgerEntry] = []
    balance = account.balance_points
    if redeemed > 0 and not await _ledger_exists(
        db, account.id, "policy_application", application.id, LoyaltyEntryType.REDEMPTION
    ):
        balance -= redeemed
        entry = LoyaltyLedgerEntry(
            tenant_id=context.tenant_id,
            account_id=account.id,
            entry_type=LoyaltyEntryType.REDEMPTION,
            points=-redeemed,
            balance_after=balance,
            reason=f"Redeemed against policy {policy.policy_number}",
            reference_type="policy_application",
            reference_id=application.id,
            occurred_at=now,
        )
        db.add(entry)
        ledger.append(entry)

    total_term_premium = sum(item.amount_cents for item in schedule)
    accrual_points = total_term_premium // ACCRUAL_CENTS_PER_POINT
    if accrual_points > 0 and not await _ledger_exists(
        db, account.id, "policy_application", application.id, LoyaltyEntryType.ACCRUAL
    ):
        balance += accrual_points
        entry = LoyaltyLedgerEntry(
            tenant_id=context.tenant_id,
            account_id=account.id,
            entry_type=LoyaltyEntryType.ACCRUAL,
            points=accrual_points,
            balance_after=balance,
            reason=f"Policy {policy.policy_number} purchase",
            reference_type="policy_application",
            reference_id=application.id,
            occurred_at=now,
        )
        db.add(entry)
        ledger.append(entry)
        account.lifetime_points += accrual_points
    account.balance_points = balance

    application.status = PolicyApplicationStatus.ISSUED
    application.decision_at = now

    await db.flush()
    await db.refresh(policy)
    for member in members:
        await db.refresh(member)
    for instalment in schedule:
        await db.refresh(instalment)
    for entry in ledger:
        await db.refresh(entry)
    await db.refresh(application)

    result = PurchaseResult(
        policy=_policy_summary(policy, plan, product, payer, MemberRelationship.SELF),
        members=[
            PolicyMemberRead(
                id=member.id,
                patient_user_id=member.patient_user_id,
                relationship=member.relationship.value,
                member_suffix=member.member_suffix,
                effective_from=member.effective_from,
                effective_to=member.effective_to,
            )
            for member in members
        ],
        premium_schedule=[
            PremiumInstalment(
                id=instalment.id,
                due_date=instalment.due_date,
                amount_cents=instalment.amount_cents,
                currency=instalment.currency,
                status=instalment.status,
            )
            for instalment in schedule
        ],
        loyalty_entries=[_ledger_read(entry) for entry in ledger],
        loyalty_balance_points=account.balance_points,
        application=_application_read(application),
        already_issued=False,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=subscriber_id,
        resource_type="policy",
        resource_id=policy.id,
        purpose_of_use=_purpose(context, subscriber_id),
        result_count=1,
        request=request,
    )
    await write_audit(
        db,
        context,
        event_type="coverage.policy.issued",
        subject_user_id=subscriber_id,
        resource_id=policy.id,
        event_data={
            "policy_number": policy.policy_number,
            "application_id": str(application.id),
            "plan_id": str(plan.id),
            "premium_cents": policy.premium_cents,
            "currency": policy.currency,
            "instalments": len(schedule),
            "loyalty_points_accrued": accrual_points,
            "loyalty_points_redeemed": redeemed,
        },
        request=request,
    )
    await db.commit()
    return result


async def _ledger_exists(
    db: AsyncSession,
    account_id: UUID,
    reference_type: str,
    reference_id: UUID,
    entry_type: LoyaltyEntryType,
) -> bool:
    """The ledger's uniqueness guard doubles as the accrual idempotency key."""
    found = await db.scalar(
        select(LoyaltyLedgerEntry.id).where(
            LoyaltyLedgerEntry.account_id == account_id,
            LoyaltyLedgerEntry.reference_type == reference_type,
            LoyaltyLedgerEntry.reference_id == reference_id,
            LoyaltyLedgerEntry.entry_type == entry_type,
        )
    )
    return found is not None


async def _purchase_result(
    db: AsyncSession,
    context: AuthContext,
    application: PolicyApplication,
    policy: Policy,
    *,
    already_issued: bool,
    request: Request | None,
) -> PurchaseResult:
    """Rebuild the purchase payload for an application that was already issued."""
    _policy, plan, product, payer = await _load_policy(db, policy.id)
    members = (
        await db.scalars(
            select(PolicyMember)
            .where(PolicyMember.policy_id == policy.id)
            .order_by(PolicyMember.member_suffix)
        )
    ).all()
    schedule = (
        await db.scalars(
            select(PremiumSchedule)
            .where(PremiumSchedule.policy_id == policy.id)
            .order_by(PremiumSchedule.due_date)
        )
    ).all()
    account = await _loyalty_account(db, context, policy.subscriber_user_id, for_update=False)
    ledger = (
        await db.scalars(
            select(LoyaltyLedgerEntry)
            .where(
                LoyaltyLedgerEntry.account_id == account.id,
                LoyaltyLedgerEntry.reference_type == "policy_application",
                LoyaltyLedgerEntry.reference_id == application.id,
            )
            .order_by(LoyaltyLedgerEntry.occurred_at)
        )
    ).all()

    result = PurchaseResult(
        policy=_policy_summary(policy, plan, product, payer, MemberRelationship.SELF),
        members=[
            PolicyMemberRead(
                id=member.id,
                patient_user_id=member.patient_user_id,
                relationship=member.relationship.value,
                member_suffix=member.member_suffix,
                effective_from=member.effective_from,
                effective_to=member.effective_to,
            )
            for member in members
        ],
        premium_schedule=[
            PremiumInstalment(
                id=instalment.id,
                due_date=instalment.due_date,
                amount_cents=instalment.amount_cents,
                currency=instalment.currency,
                status=instalment.status,
            )
            for instalment in schedule
        ],
        loyalty_entries=[_ledger_read(entry) for entry in ledger],
        loyalty_balance_points=account.balance_points,
        application=_application_read(application),
        already_issued=already_issued,
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=policy.subscriber_user_id,
        resource_type="policy",
        resource_id=policy.id,
        purpose_of_use=_purpose(context, policy.subscriber_user_id),
        result_count=1,
        request=request,
    )
    await db.commit()
    return result


async def loyalty_summary(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    page: Pagination,
    request: Request | None = None,
) -> LoyaltyBalance:
    """Loyalty balance plus a page of the append-only ledger, newest first."""
    account = await db.scalar(
        select(LoyaltyAccount).where(LoyaltyAccount.user_id == patient_user_id)
    )
    entries: list[LoyaltyLedgerRead] = []
    if account is not None:
        rows = (
            await db.scalars(
                select(LoyaltyLedgerEntry)
                .where(LoyaltyLedgerEntry.account_id == account.id)
                .order_by(LoyaltyLedgerEntry.occurred_at.desc(), LoyaltyLedgerEntry.id)
                .limit(page.limit + 1)
                .offset(page.offset)
            )
        ).all()
        entries = [_ledger_read(entry) for entry in rows]

    summary = LoyaltyBalance(
        account_id=account.id if account else None,
        program=account.program if account else "default",
        balance_points=account.balance_points if account else 0,
        lifetime_points=account.lifetime_points if account else 0,
        tier=account.tier if account else None,
        status=account.status if account else "active",
        history=paginate(entries, page),
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=patient_user_id,
        resource_type="loyalty_account",
        resource_id=account.id if account else None,
        purpose_of_use=_purpose(context, patient_user_id),
        result_count=len(summary.history.items),
        request=request,
    )
    await db.commit()
    return summary
