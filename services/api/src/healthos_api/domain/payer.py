"""Payer back-office domain: products, plans, benefits, eligibility, claims, estimates.

Everything in this module is *operational* payer data — every table carries a
``tenant_id`` and is therefore :func:`~healthos_api.domain.common.tenant_scoped`
rather than consent scoped. The rows still describe identified members, so every
function that hands patient data back to a caller appends a PHI access event with
the HL7 ``HPAYMT`` purpose of use in the same transaction as the read.

Two invariants the schema cannot enforce on its own:

* Claim adjudication must move money and the member's accumulators together. The
  accumulator upsert, the claim/line updates and the append-only ``claim_events``
  row are written inside one transaction and committed once.
* Benefit rows are effective-dated, not mutated in place. Replacing a grid closes
  the outgoing row with ``effective_to`` and inserts the new version.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccumulatorType,
    BenefitAccumulator,
    BenefitExplanation,
    BenefitLimitPeriod,
    Claim,
    ClaimEvent,
    ClaimLine,
    ClaimStatus,
    ClaimType,
    CostEstimate,
    DocumentLink,
    DocumentLinkType,
    EligibilityCheck,
    EligibilityStatus,
    InsurancePlan,
    InsuranceProduct,
    NetworkTier,
    PayerContractRate,
    PlanBenefit,
    Policy,
    PolicyMember,
    PolicyStatus,
    PremiumSchedule,
    PriorAuthorization,
    PriorAuthStatus,
    ServiceItem,
)
from healthos_api.domain.common import (
    DomainModel,
    Page,
    Pagination,
    assert_transition,
    conflict,
    not_found,
    paginate,
    record_phi_access,
    record_phi_access_many,
    tenant_scoped,
    unprocessable,
    write_audit,
)

#: Days a submitted claim may sit before the adjudication queue flags it.
SLA_TARGET_DAYS = 30

#: Default eligibility cache window; payers publish 12h freshness for 270/271.
DEFAULT_ELIGIBILITY_TTL_MINUTES = 720

CLAIM_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"accepted", "pended", "adjudicated", "denied"},
    "accepted": {"adjudicated", "pended", "denied"},
    "pended": {"accepted", "adjudicated", "denied"},
    "adjudicated": {"paid", "denied", "appealed"},
    "paid": {"appealed"},
    "denied": {"appealed"},
    "appealed": {"pended", "adjudicated", "denied"},
}

PRIOR_AUTH_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"pended", "approved", "partially_approved", "denied"},
    "pended": {"approved", "partially_approved", "denied"},
    "approved": {"appealed", "expired"},
    "partially_approved": {"appealed", "expired"},
    "denied": {"appealed"},
    "appealed": {"approved", "partially_approved", "denied"},
    "expired": set(),
}

OPEN_CLAIM_STATUSES = (ClaimStatus.SUBMITTED, ClaimStatus.ACCEPTED, ClaimStatus.PENDED)
APPROVED_CLAIM_STATUSES = (ClaimStatus.ADJUDICATED, ClaimStatus.PAID)

ProductType = Literal["hmo", "ppo", "epo", "pos", "indemnity"]


# --------------------------------------------------------------------------------------
# schemas
# --------------------------------------------------------------------------------------


class ProductCreate(DomainModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    product_type: ProductType
    payer_organization_id: UUID | None = None
    network_name: str | None = Field(default=None, max_length=255)
    filing_id: str | None = Field(default=None, max_length=64)
    regulator_approval_id: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class ProductUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    product_type: ProductType | None = None
    network_name: str | None = Field(default=None, max_length=255)
    filing_id: str | None = Field(default=None, max_length=64)
    regulator_approval_id: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class ProductResponse(DomainModel):
    id: UUID
    payer_organization_id: UUID
    code: str
    name: str
    product_type: str
    network_name: str | None
    filing_id: str | None
    regulator_approval_id: str | None
    is_active: bool
    plan_count: int
    created_at: datetime
    updated_at: datetime


class PlanCreate(DomainModel):
    product_id: UUID
    plan_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    premium_cents: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_from: date
    effective_to: date | None = None
    metal_tier: str | None = Field(default=None, max_length=16)
    individual_deductible_cents: int | None = Field(default=None, ge=0)
    family_deductible_cents: int | None = Field(default=None, ge=0)
    individual_oop_max_cents: int | None = Field(default=None, ge=0)
    family_oop_max_cents: int | None = Field(default=None, ge=0)
    term_months: int = Field(default=12, ge=1, le=120)
    eligibility_rules: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @model_validator(mode="after")
    def _check_period(self) -> PlanCreate:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class PlanUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    premium_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    metal_tier: str | None = Field(default=None, max_length=16)
    individual_deductible_cents: int | None = Field(default=None, ge=0)
    family_deductible_cents: int | None = Field(default=None, ge=0)
    individual_oop_max_cents: int | None = Field(default=None, ge=0)
    family_oop_max_cents: int | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, ge=1, le=120)
    eligibility_rules: dict[str, Any] | None = None
    effective_to: date | None = None
    is_active: bool | None = None


class PlanResponse(DomainModel):
    id: UUID
    product_id: UUID
    product_code: str
    product_name: str
    plan_code: str
    name: str
    metal_tier: str | None
    premium_cents: int
    currency: str
    individual_deductible_cents: int | None
    family_deductible_cents: int | None
    individual_oop_max_cents: int | None
    family_oop_max_cents: int | None
    term_months: int
    eligibility_rules: dict[str, Any]
    effective_from: date
    effective_to: date | None
    is_active: bool
    benefit_count: int
    created_at: datetime
    updated_at: datetime


class BenefitInput(DomainModel):
    service_category: str = Field(min_length=1, max_length=64)
    covered: bool
    effective_from: date
    service_code_system: str | None = Field(default=None, max_length=128)
    service_code: str | None = Field(default=None, max_length=64)
    service_display: str | None = Field(default=None, max_length=255)
    service_concept_id: UUID | None = None
    network_tier: NetworkTier = NetworkTier.IN_NETWORK
    copay_cents: int | None = Field(default=None, ge=0)
    coinsurance_percent: Decimal | None = Field(default=None, ge=0, le=100)
    deductible_applies: bool = True
    visit_limit_count: int | None = Field(default=None, ge=0)
    limit_period: BenefitLimitPeriod | None = None
    prior_auth_required: bool = False
    waiting_period_days: int = Field(default=0, ge=0)
    exclusion_text: str | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def _check_row(self) -> BenefitInput:
        if (self.visit_limit_count is None) != (self.limit_period is None):
            raise ValueError("visit_limit_count and limit_period must be set together")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class BenefitGridPut(DomainModel):
    """The full benefit grid for a plan. Rows omitted here are closed out."""

    benefits: list[BenefitInput] = Field(min_length=1)
    close_omitted_on: date | None = None


class BenefitResponse(DomainModel):
    id: UUID
    plan_id: UUID
    service_category: str
    service_code_system: str | None
    service_code: str | None
    service_display: str | None
    service_concept_id: UUID | None
    network_tier: NetworkTier
    covered: bool
    copay_cents: int | None
    coinsurance_percent: Decimal | None
    deductible_applies: bool
    visit_limit_count: int | None
    limit_period: BenefitLimitPeriod | None
    prior_auth_required: bool
    waiting_period_days: int
    exclusion_text: str | None
    effective_from: date
    effective_to: date | None
    explanation_count: int


class BenefitGridResult(DomainModel):
    plan_id: UUID
    created: int
    updated: int
    closed: int
    benefits: list[BenefitResponse]


class ExplanationInput(DomainModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", protected_namespaces=())

    plan_benefit_id: UUID
    summary_text: str = Field(min_length=1)
    generated_by: str = Field(min_length=1, max_length=64)
    locale: str = Field(default="en-US", max_length=16)
    reading_level: str = Field(default="grade6", max_length=16)
    example_scenario: dict[str, Any] = Field(default_factory=dict)
    source_document_asset_id: UUID | None = None
    model_version: str | None = Field(default=None, max_length=64)
    mark_reviewed: bool = False


class ExplanationPut(DomainModel):
    explanations: list[ExplanationInput] = Field(min_length=1)


class ExplanationResponse(DomainModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", protected_namespaces=())

    id: UUID
    plan_benefit_id: UUID
    locale: str
    reading_level: str
    summary_text: str
    example_scenario: dict[str, Any]
    source_document_asset_id: UUID | None
    generated_by: str
    model_version: str | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    updated_at: datetime


class ExplanationPutResult(DomainModel):
    plan_id: UUID
    created: int
    updated: int
    items: list[ExplanationResponse]


class EligibilityRequest(DomainModel):
    patient_user_id: UUID
    service_date: date | None = None
    service_codes: list[str] = Field(default_factory=list, max_length=50)
    policy_id: UUID | None = None
    member_id: str | None = Field(default=None, max_length=64)
    payer_organization_id: UUID | None = None
    cache_ttl_minutes: int = Field(default=DEFAULT_ELIGIBILITY_TTL_MINUTES, ge=0, le=10080)
    force_refresh: bool = False


class EligibilityResponse(DomainModel):
    id: UUID
    patient_user_id: UUID
    policy_id: UUID | None
    payer_organization_id: UUID
    member_id: str
    service_date: date
    service_codes: list[str]
    status: EligibilityStatus
    coverage_found: bool
    active_from: date | None
    active_to: date | None
    benefits_returned: dict[str, Any]
    transaction_id: str | None
    cached_until: datetime | None
    from_cache: bool
    created_at: datetime


class ClaimLineResponse(DomainModel):
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


class ClaimResponse(DomainModel):
    id: UUID
    claim_number: str
    policy_id: UUID
    patient_user_id: UUID
    subscriber_user_id: UUID
    payer_organization_id: UUID
    billing_provider_organization_id: UUID
    rendering_provider_user_id: UUID | None
    encounter_id: UUID | None
    prior_authorization_id: UUID | None
    claim_type: ClaimType
    service_from: date
    service_to: date
    total_charge_cents: int
    allowed_cents: int | None
    paid_cents: int | None
    patient_responsibility_cents: int | None
    currency: str
    status: ClaimStatus
    submitted_at: datetime | None
    adjudicated_at: datetime | None
    denial_reason_code: str | None
    line_count: int
    sla_age_days: float
    sla_breached: bool
    created_at: datetime


class AccumulatorResponse(DomainModel):
    id: UUID
    policy_id: UUID
    patient_user_id: UUID
    accumulator_type: AccumulatorType
    benefit_year: int
    limit_cents: int | None
    consumed_cents: int
    limit_count: int | None
    consumed_count: int
    remaining_cents: int | None
    as_of: datetime


class AdjudicationLine(DomainModel):
    line_number: int = Field(ge=1)
    allowed_cents: int = Field(ge=0)
    paid_cents: int = Field(ge=0)
    copay_cents: int = Field(default=0, ge=0)
    coinsurance_cents: int = Field(default=0, ge=0)
    deductible_cents: int = Field(default=0, ge=0)
    adjustment_reason_codes: list[str] = Field(default_factory=list, max_length=20)


class AdjudicateRequest(DomainModel):
    lines: list[AdjudicationLine] = Field(min_length=1)
    status: Literal["adjudicated", "paid"] = "adjudicated"
    benefit_year: int | None = Field(default=None, ge=1900, le=2999)
    note: str | None = Field(default=None, max_length=500)
    payment_reference: str | None = Field(default=None, max_length=64)


class AdjudicationResult(DomainModel):
    claim: ClaimResponse
    lines: list[ClaimLineResponse]
    accumulators: list[AccumulatorResponse]
    accumulators_applied: bool
    event_id: UUID


class DenyRequest(DomainModel):
    reason_code: str = Field(min_length=1, max_length=32)
    reason_description: str | None = Field(default=None, max_length=500)


class PriorAuthCreate(DomainModel):
    policy_id: UUID
    patient_user_id: UUID
    requesting_provider_user_id: UUID
    service_codes: list[str] = Field(min_length=1, max_length=50)
    diagnosis_codes: list[str] = Field(default_factory=list, max_length=50)
    units_requested: int | None = Field(default=None, ge=1)
    clinical_justification: str | None = None
    criteria_met: dict[str, Any] = Field(default_factory=dict)
    submit: bool = True
    document_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)


class PriorAuthDecision(DomainModel):
    decision: Literal["approved", "partially_approved", "denied", "pended"]
    reason: str | None = Field(default=None, max_length=500)
    units_approved: int | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_to: date | None = None
    authorization_number: str | None = Field(default=None, max_length=64)
    reviewer_user_id: UUID | None = None

    @model_validator(mode="after")
    def _check_period(self) -> PriorAuthDecision:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        if self.decision in {"denied", "partially_approved"} and not self.reason:
            raise ValueError("a decision reason is required for this decision")
        return self


class PriorAuthResponse(DomainModel):
    id: UUID
    policy_id: UUID
    patient_user_id: UUID
    requesting_provider_user_id: UUID
    service_codes: list[str]
    diagnosis_codes: list[str]
    units_requested: int | None
    units_approved: int | None
    clinical_justification: str | None
    criteria_met: dict[str, Any]
    status: PriorAuthStatus
    reviewer_user_id: UUID | None
    decision_at: datetime | None
    decision_reason: str | None
    authorization_number: str | None
    valid_from: date | None
    valid_to: date | None
    evidence_document_count: int
    created_at: datetime
    updated_at: datetime


class CostEstimateLineInput(DomainModel):
    service_code: str = Field(min_length=1, max_length=64)
    service_code_system: str | None = Field(default=None, max_length=128)
    service_display: str | None = Field(default=None, max_length=255)
    service_category: str | None = Field(default=None, max_length=64)
    units: int = Field(default=1, ge=1, le=999)
    network_tier: NetworkTier = NetworkTier.IN_NETWORK


class CostEstimateRequest(DomainModel):
    patient_user_id: UUID
    organization_id: UUID
    bundle: list[CostEstimateLineInput] = Field(min_length=1, max_length=50)
    policy_id: UUID | None = None
    service_item_id: UUID | None = None
    service_date: date | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    valid_days: int = Field(default=30, ge=1, le=365)


class CostEstimateLine(DomainModel):
    service_code: str
    service_display: str
    units: int
    network_tier: NetworkTier
    billed_cents: int
    contracted_rate_cents: int | None
    allowed_cents: int
    copay_cents: int
    deductible_applied_cents: int
    coinsurance_cents: int
    member_liability_cents: int
    plan_pays_cents: int
    covered: bool
    prior_auth_required: bool
    benefit_source: Literal["service_code", "service_category", "none", "self_pay"]


class CostEstimateResponse(DomainModel):
    id: UUID
    patient_user_id: UUID
    policy_id: UUID | None
    organization_id: UUID
    service_item_id: UUID | None
    billed_cents: int
    contracted_rate_cents: int | None
    deductible_applied_cents: int
    coinsurance_cents: int
    copay_cents: int
    member_liability_cents: int
    plan_pays_cents: int
    deductible_remaining_cents: int | None
    currency: str
    confidence: Decimal | None
    assumptions: dict[str, Any]
    expires_at: datetime
    is_expired: bool
    lines: list[CostEstimateLine]
    created_at: datetime


class StatusCount(DomainModel):
    status: str
    count: int


class CurrencyTotals(DomainModel):
    currency: str
    charged_cents: int
    allowed_cents: int
    paid_cents: int


class PriorAuthSummary(DomainModel):
    total: int
    approved: int
    partially_approved: int
    denied: int
    pending: int
    approval_rate: float
    avg_days_to_decision: float | None


class PremiumSummary(DomainModel):
    due_count: int
    due_cents: int
    paid_count: int
    paid_cents: int
    overdue_count: int
    overdue_cents: int


class AnalyticsSummary(DomainModel):
    window_from: date
    window_to: date
    window_days: int
    claims_total: int
    claims_by_status: list[StatusCount]
    decided_count: int
    approved_count: int
    denied_count: int
    approval_rate: float
    avg_days_to_decision: float | None
    throughput_per_day: float
    open_count: int
    open_sla_breached_count: int
    oldest_open_age_days: float | None
    totals_by_currency: list[CurrencyTotals]
    prior_authorizations: PriorAuthSummary
    premiums: PremiumSummary


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _age_days(moment: datetime | None, *, now: datetime) -> float:
    if moment is None:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return round((now - moment).total_seconds() / 86400.0, 3)


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _coinsurance_of(amount: int, percent: Decimal | None) -> int:
    if percent is None or amount <= 0:
        return 0
    value = (Decimal(amount) * percent / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(value)


def _effective_on(model: Any, moment: date) -> list[ColumnElement[bool]]:
    """Effective-dating predicate shared by benefits, rates and service items."""
    return [
        model.effective_from <= moment,
        or_(model.effective_to.is_(None), model.effective_to >= moment),
    ]


def _claim_ids(context: AuthContext) -> Select[tuple[UUID]]:
    return tenant_scoped(select(Claim.id), Claim, context)


def _line_count_subquery() -> Any:
    return (
        select(func.count(ClaimLine.id))
        .where(ClaimLine.claim_id == Claim.id)
        .correlate(Claim)
        .scalar_subquery()
    )


def _product_response(product: InsuranceProduct, plan_count: int) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        payer_organization_id=product.payer_organization_id,
        code=product.code,
        name=product.name,
        product_type=product.product_type,
        network_name=product.network_name,
        filing_id=product.filing_id,
        regulator_approval_id=product.regulator_approval_id,
        is_active=product.is_active,
        plan_count=plan_count,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _plan_response(
    plan: InsurancePlan, product: InsuranceProduct, benefit_count: int
) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        product_id=plan.product_id,
        product_code=product.code,
        product_name=product.name,
        plan_code=plan.plan_code,
        name=plan.name,
        metal_tier=plan.metal_tier,
        premium_cents=plan.premium_cents,
        currency=plan.currency,
        individual_deductible_cents=plan.individual_deductible_cents,
        family_deductible_cents=plan.family_deductible_cents,
        individual_oop_max_cents=plan.individual_oop_max_cents,
        family_oop_max_cents=plan.family_oop_max_cents,
        term_months=plan.term_months,
        eligibility_rules=plan.eligibility_rules,
        effective_from=plan.effective_from,
        effective_to=plan.effective_to,
        is_active=plan.is_active,
        benefit_count=benefit_count,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _benefit_response(benefit: PlanBenefit, explanation_count: int) -> BenefitResponse:
    return BenefitResponse(
        id=benefit.id,
        plan_id=benefit.plan_id,
        service_category=benefit.service_category,
        service_code_system=benefit.service_code_system,
        service_code=benefit.service_code,
        service_display=benefit.service_display,
        service_concept_id=benefit.service_concept_id,
        network_tier=benefit.network_tier,
        covered=benefit.covered,
        copay_cents=benefit.copay_cents,
        coinsurance_percent=benefit.coinsurance_percent,
        deductible_applies=benefit.deductible_applies,
        visit_limit_count=benefit.visit_limit_count,
        limit_period=benefit.limit_period,
        prior_auth_required=benefit.prior_auth_required,
        waiting_period_days=benefit.waiting_period_days,
        exclusion_text=benefit.exclusion_text,
        effective_from=benefit.effective_from,
        effective_to=benefit.effective_to,
        explanation_count=explanation_count,
    )


def _explanation_response(row: BenefitExplanation) -> ExplanationResponse:
    return ExplanationResponse(
        id=row.id,
        plan_benefit_id=row.plan_benefit_id,
        locale=row.locale,
        reading_level=row.reading_level,
        summary_text=row.summary_text,
        example_scenario=row.example_scenario,
        source_document_asset_id=row.source_document_asset_id,
        generated_by=row.generated_by,
        model_version=row.model_version,
        reviewed_by_user_id=row.reviewed_by_user_id,
        reviewed_at=row.reviewed_at,
        updated_at=row.updated_at,
    )


def _eligibility_response(row: EligibilityCheck, *, from_cache: bool) -> EligibilityResponse:
    return EligibilityResponse(
        id=row.id,
        patient_user_id=row.patient_user_id,
        policy_id=row.policy_id,
        payer_organization_id=row.payer_organization_id,
        member_id=row.member_id,
        service_date=row.service_date,
        service_codes=row.service_codes,
        status=row.status,
        coverage_found=row.coverage_found,
        active_from=row.active_from,
        active_to=row.active_to,
        benefits_returned=row.benefits_returned,
        transaction_id=row.transaction_id,
        cached_until=row.cached_until,
        from_cache=from_cache,
        created_at=row.created_at,
    )


def _claim_response(
    claim: Claim, payer_organization_id: UUID, line_count: int, *, now: datetime
) -> ClaimResponse:
    age = _age_days(claim.submitted_at or claim.created_at, now=now)
    open_claim = claim.status in OPEN_CLAIM_STATUSES
    return ClaimResponse(
        id=claim.id,
        claim_number=claim.claim_number,
        policy_id=claim.policy_id,
        patient_user_id=claim.patient_user_id,
        subscriber_user_id=claim.subscriber_user_id,
        payer_organization_id=payer_organization_id,
        billing_provider_organization_id=claim.billing_provider_organization_id,
        rendering_provider_user_id=claim.rendering_provider_user_id,
        encounter_id=claim.encounter_id,
        prior_authorization_id=claim.prior_authorization_id,
        claim_type=claim.claim_type,
        service_from=claim.service_from,
        service_to=claim.service_to,
        total_charge_cents=claim.total_charge_cents,
        allowed_cents=claim.allowed_cents,
        paid_cents=claim.paid_cents,
        patient_responsibility_cents=claim.patient_responsibility_cents,
        currency=claim.currency,
        status=claim.status,
        submitted_at=claim.submitted_at,
        adjudicated_at=claim.adjudicated_at,
        denial_reason_code=claim.denial_reason_code,
        line_count=line_count,
        sla_age_days=age,
        sla_breached=open_claim and age > SLA_TARGET_DAYS,
        created_at=claim.created_at,
    )


def _claim_line_response(line: ClaimLine) -> ClaimLineResponse:
    return ClaimLineResponse(
        id=line.id,
        line_number=line.line_number,
        service_date=line.service_date,
        service_code_system=line.service_code_system,
        service_code=line.service_code,
        service_display=line.service_display,
        modifiers=line.modifiers,
        units=line.units,
        charge_cents=line.charge_cents,
        allowed_cents=line.allowed_cents,
        paid_cents=line.paid_cents,
        copay_cents=line.copay_cents,
        coinsurance_cents=line.coinsurance_cents,
        deductible_cents=line.deductible_cents,
        diagnosis_pointers=line.diagnosis_pointers,
        adjustment_reason_codes=line.adjustment_reason_codes,
    )


def _accumulator_response(row: BenefitAccumulator) -> AccumulatorResponse:
    remaining = None if row.limit_cents is None else max(row.limit_cents - row.consumed_cents, 0)
    return AccumulatorResponse(
        id=row.id,
        policy_id=row.policy_id,
        patient_user_id=row.patient_user_id,
        accumulator_type=row.accumulator_type,
        benefit_year=row.benefit_year,
        limit_cents=row.limit_cents,
        consumed_cents=row.consumed_cents,
        limit_count=row.limit_count,
        consumed_count=row.consumed_count,
        remaining_cents=remaining,
        as_of=row.as_of,
    )


def _prior_auth_response(row: PriorAuthorization, evidence_count: int) -> PriorAuthResponse:
    return PriorAuthResponse(
        id=row.id,
        policy_id=row.policy_id,
        patient_user_id=row.patient_user_id,
        requesting_provider_user_id=row.requesting_provider_user_id,
        service_codes=row.service_codes,
        diagnosis_codes=row.diagnosis_codes,
        units_requested=row.units_requested,
        units_approved=row.units_approved,
        clinical_justification=row.clinical_justification,
        criteria_met=row.criteria_met,
        status=row.status,
        reviewer_user_id=row.reviewer_user_id,
        decision_at=row.decision_at,
        decision_reason=row.decision_reason,
        authorization_number=row.authorization_number,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        evidence_document_count=evidence_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _estimate_lines(bundle: list[dict[str, Any]]) -> list[CostEstimateLine]:
    """Decode a stored bundle, tolerating rows written by another estimator."""
    lines: list[CostEstimateLine] = []
    for item in bundle:
        try:
            lines.append(CostEstimateLine.model_validate(item))
        except ValidationError:
            continue
    return lines


def _cost_estimate_response(row: CostEstimate, *, now: datetime) -> CostEstimateResponse:
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    return CostEstimateResponse(
        id=row.id,
        patient_user_id=row.patient_user_id,
        policy_id=row.policy_id,
        organization_id=row.organization_id,
        service_item_id=row.service_item_id,
        billed_cents=row.billed_cents,
        contracted_rate_cents=row.contracted_rate_cents,
        deductible_applied_cents=row.deductible_applied_cents,
        coinsurance_cents=row.coinsurance_cents,
        copay_cents=row.copay_cents,
        member_liability_cents=row.member_liability_cents,
        plan_pays_cents=row.plan_pays_cents,
        deductible_remaining_cents=row.deductible_remaining_cents,
        currency=row.currency,
        confidence=row.confidence,
        assumptions=row.assumptions,
        expires_at=row.expires_at,
        is_expired=expires <= now,
        lines=_estimate_lines(row.service_bundle),
        created_at=row.created_at,
    )


async def _load_product(
    db: AsyncSession, context: AuthContext, product_id: UUID
) -> InsuranceProduct:
    product = await db.scalar(
        tenant_scoped(select(InsuranceProduct), InsuranceProduct, context).where(
            InsuranceProduct.id == product_id
        )
    )
    if product is None:
        raise not_found("Insurance product")
    return product


async def _load_plan(
    db: AsyncSession, context: AuthContext, plan_id: UUID
) -> tuple[InsurancePlan, InsuranceProduct]:
    row = (
        await db.execute(
            select(InsurancePlan, InsuranceProduct)
            .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
            .where(
                InsurancePlan.id == plan_id,
                InsurancePlan.id.in_(
                    tenant_scoped(select(InsurancePlan.id), InsurancePlan, context)
                ),
            )
        )
    ).first()
    if row is None:
        raise not_found("Insurance plan")
    plan, product = row
    return plan, product


async def _explanation_counts(db: AsyncSession, benefit_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not benefit_ids:
        return {}
    rows = await db.execute(
        select(BenefitExplanation.plan_benefit_id, func.count(BenefitExplanation.id))
        .where(BenefitExplanation.plan_benefit_id.in_(benefit_ids))
        .group_by(BenefitExplanation.plan_benefit_id)
    )
    return {benefit_id: count for benefit_id, count in rows.all()}


async def _resolve_policy(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    on_date: date,
    policy_id: UUID | None = None,
    member_id: str | None = None,
) -> Policy | None:
    """The member's coverage on ``on_date``, joined through policy_members."""
    stmt = (
        select(Policy)
        .join(PolicyMember, PolicyMember.policy_id == Policy.id)
        .where(
            Policy.id.in_(tenant_scoped(select(Policy.id), Policy, context)),
            PolicyMember.patient_user_id == patient_user_id,
            Policy.effective_from <= on_date,
            or_(Policy.effective_to.is_(None), Policy.effective_to >= on_date),
            PolicyMember.effective_from <= on_date,
            or_(PolicyMember.effective_to.is_(None), PolicyMember.effective_to >= on_date),
        )
        .order_by((Policy.status == PolicyStatus.ACTIVE).desc(), Policy.effective_from.desc())
        .limit(1)
    )
    if policy_id is not None:
        stmt = stmt.where(Policy.id == policy_id)
    if member_id is not None:
        stmt = stmt.where(Policy.member_id == member_id)
    policy: Policy | None = await db.scalar(stmt)
    return policy


# --------------------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------------------


async def list_products(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    search: str | None = None,
    product_type: str | None = None,
    is_active: bool | None = None,
) -> Page[ProductResponse]:
    plan_count = (
        select(func.count(InsurancePlan.id))
        .where(InsurancePlan.product_id == InsuranceProduct.id)
        .correlate(InsuranceProduct)
        .scalar_subquery()
    )
    stmt = select(InsuranceProduct, plan_count.label("plan_count")).where(
        InsuranceProduct.id.in_(
            tenant_scoped(select(InsuranceProduct.id), InsuranceProduct, context)
        )
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(InsuranceProduct.name.ilike(pattern), InsuranceProduct.code.ilike(pattern))
        )
    if product_type:
        stmt = stmt.where(InsuranceProduct.product_type == product_type)
    if is_active is not None:
        stmt = stmt.where(InsuranceProduct.is_active.is_(is_active))

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = await db.execute(
        stmt.order_by(InsuranceProduct.code).offset(page.offset).limit(page.limit + 1)
    )
    items = [_product_response(product, int(count)) for product, count in rows.all()]
    return paginate(items, page, total=int(total or 0))


async def create_product(
    db: AsyncSession,
    context: AuthContext,
    payload: ProductCreate,
    *,
    request: Request | None = None,
) -> ProductResponse:
    payer_organization_id = payload.payer_organization_id or context.tenant_id
    duplicate = await db.scalar(
        select(InsuranceProduct.id).where(
            InsuranceProduct.payer_organization_id == payer_organization_id,
            InsuranceProduct.code == payload.code,
        )
    )
    if duplicate is not None:
        raise conflict(f"Product code '{payload.code}' already exists for this payer")

    product = InsuranceProduct(
        tenant_id=context.tenant_id,
        payer_organization_id=payer_organization_id,
        code=payload.code,
        name=payload.name,
        product_type=payload.product_type,
        network_name=payload.network_name,
        filing_id=payload.filing_id,
        regulator_approval_id=payload.regulator_approval_id,
        is_active=payload.is_active,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)
    await write_audit(
        db,
        context,
        event_type="insurance.product.created",
        resource_id=product.id,
        event_data={"code": product.code, "product_type": product.product_type},
        request=request,
    )
    response = _product_response(product, 0)
    await db.commit()
    return response


async def update_product(
    db: AsyncSession,
    context: AuthContext,
    product_id: UUID,
    payload: ProductUpdate,
    *,
    request: Request | None = None,
) -> ProductResponse:
    product = await _load_product(db, context, product_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise unprocessable("No fields to update")
    for field, value in changes.items():
        setattr(product, field, value)
    await db.flush()
    await db.refresh(product)
    plan_count = await db.scalar(
        select(func.count(InsurancePlan.id)).where(InsurancePlan.product_id == product.id)
    )
    await write_audit(
        db,
        context,
        event_type="insurance.product.updated",
        resource_id=product.id,
        event_data={"fields": sorted(changes)},
        request=request,
    )
    response = _product_response(product, int(plan_count or 0))
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# plans
# --------------------------------------------------------------------------------------


async def list_plans(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    product_id: UUID | None = None,
    metal_tier: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> Page[PlanResponse]:
    benefit_count = (
        select(func.count(PlanBenefit.id))
        .where(PlanBenefit.plan_id == InsurancePlan.id, PlanBenefit.effective_to.is_(None))
        .correlate(InsurancePlan)
        .scalar_subquery()
    )
    stmt = (
        select(InsurancePlan, InsuranceProduct, benefit_count.label("benefit_count"))
        .join(InsuranceProduct, InsuranceProduct.id == InsurancePlan.product_id)
        .where(
            InsurancePlan.id.in_(tenant_scoped(select(InsurancePlan.id), InsurancePlan, context))
        )
    )
    if product_id is not None:
        stmt = stmt.where(InsurancePlan.product_id == product_id)
    if metal_tier:
        stmt = stmt.where(InsurancePlan.metal_tier == metal_tier)
    if is_active is not None:
        stmt = stmt.where(InsurancePlan.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(InsurancePlan.name.ilike(pattern), InsurancePlan.plan_code.ilike(pattern))
        )

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = await db.execute(
        stmt.order_by(InsurancePlan.premium_cents, InsurancePlan.plan_code)
        .offset(page.offset)
        .limit(page.limit + 1)
    )
    items = [_plan_response(plan, product, int(count)) for plan, product, count in rows.all()]
    return paginate(items, page, total=int(total or 0))


async def create_plan(
    db: AsyncSession,
    context: AuthContext,
    payload: PlanCreate,
    *,
    request: Request | None = None,
) -> PlanResponse:
    product = await _load_product(db, context, payload.product_id)
    duplicate = await db.scalar(
        select(InsurancePlan.id).where(
            InsurancePlan.product_id == product.id,
            InsurancePlan.plan_code == payload.plan_code,
            InsurancePlan.effective_from == payload.effective_from,
        )
    )
    if duplicate is not None:
        raise conflict(f"Plan '{payload.plan_code}' already exists for that effective date")

    plan = InsurancePlan(
        tenant_id=context.tenant_id,
        product_id=product.id,
        plan_code=payload.plan_code,
        name=payload.name,
        metal_tier=payload.metal_tier,
        premium_cents=payload.premium_cents,
        currency=payload.currency,
        individual_deductible_cents=payload.individual_deductible_cents,
        family_deductible_cents=payload.family_deductible_cents,
        individual_oop_max_cents=payload.individual_oop_max_cents,
        family_oop_max_cents=payload.family_oop_max_cents,
        term_months=payload.term_months,
        eligibility_rules=payload.eligibility_rules,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_active=payload.is_active,
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    await write_audit(
        db,
        context,
        event_type="insurance.plan.created",
        resource_id=plan.id,
        event_data={
            "plan_code": plan.plan_code,
            "product_id": str(product.id),
            "premium_cents": plan.premium_cents,
            "currency": plan.currency,
        },
        request=request,
    )
    response = _plan_response(plan, product, 0)
    await db.commit()
    return response


async def update_plan(
    db: AsyncSession,
    context: AuthContext,
    plan_id: UUID,
    payload: PlanUpdate,
    *,
    request: Request | None = None,
) -> PlanResponse:
    plan, product = await _load_plan(db, context, plan_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise unprocessable("No fields to update")
    effective_to = changes.get("effective_to")
    if effective_to is not None and effective_to < plan.effective_from:
        raise unprocessable("effective_to must not precede the plan effective_from")
    for field, value in changes.items():
        setattr(plan, field, value)
    await db.flush()
    await db.refresh(plan)
    benefit_count = await db.scalar(
        select(func.count(PlanBenefit.id)).where(
            PlanBenefit.plan_id == plan.id, PlanBenefit.effective_to.is_(None)
        )
    )
    await write_audit(
        db,
        context,
        event_type="insurance.plan.updated",
        resource_id=plan.id,
        event_data={"fields": sorted(changes)},
        request=request,
    )
    response = _plan_response(plan, product, int(benefit_count or 0))
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# benefit grid
# --------------------------------------------------------------------------------------


def _benefit_key(
    category: str, code: str | None, tier: NetworkTier
) -> tuple[str, str, NetworkTier]:
    return (category, code or "", tier)


async def list_plan_benefits(
    db: AsyncSession,
    context: AuthContext,
    plan_id: UUID,
    *,
    as_of: date | None = None,
    include_closed: bool = False,
) -> list[BenefitResponse]:
    plan, _ = await _load_plan(db, context, plan_id)
    stmt = select(PlanBenefit).where(PlanBenefit.plan_id == plan.id)
    if not include_closed:
        if as_of is not None:
            stmt = stmt.where(*_effective_on(PlanBenefit, as_of))
        else:
            stmt = stmt.where(PlanBenefit.effective_to.is_(None))
    benefits = list(
        (
            await db.scalars(
                stmt.order_by(
                    PlanBenefit.service_category,
                    PlanBenefit.network_tier,
                    PlanBenefit.effective_from.desc(),
                )
            )
        ).all()
    )
    counts = await _explanation_counts(db, [benefit.id for benefit in benefits])
    return [_benefit_response(benefit, counts.get(benefit.id, 0)) for benefit in benefits]


async def replace_plan_benefits(
    db: AsyncSession,
    context: AuthContext,
    plan_id: UUID,
    payload: BenefitGridPut,
    *,
    request: Request | None = None,
) -> BenefitGridResult:
    """Effective-date the grid forward: close outgoing rows, insert new versions."""
    plan, _ = await _load_plan(db, context, plan_id)
    current = list(
        (
            await db.scalars(
                select(PlanBenefit).where(
                    PlanBenefit.plan_id == plan.id, PlanBenefit.effective_to.is_(None)
                )
            )
        ).all()
    )
    by_key = {
        _benefit_key(row.service_category, row.service_code, row.network_tier): row
        for row in current
    }

    seen: set[tuple[str, str, NetworkTier]] = set()
    created = 0
    updated = 0
    closed = 0
    for item in payload.benefits:
        key = _benefit_key(item.service_category, item.service_code, item.network_tier)
        if key in seen:
            raise unprocessable(
                f"Duplicate benefit for {item.service_category}/{item.service_code or '*'} "
                f"({item.network_tier.value})"
            )
        seen.add(key)
        existing = by_key.get(key)
        if existing is not None and existing.effective_from == item.effective_from:
            for field, value in item.model_dump().items():
                setattr(existing, field, value)
            updated += 1
            continue
        if existing is not None:
            if item.effective_from <= existing.effective_from:
                raise unprocessable(
                    f"New benefit version for {item.service_category} must start after "
                    f"{existing.effective_from.isoformat()}"
                )
            existing.effective_to = item.effective_from - timedelta(days=1)
            closed += 1
        db.add(
            PlanBenefit(
                tenant_id=context.tenant_id,
                plan_id=plan.id,
                **item.model_dump(),
            )
        )
        created += 1

    close_on = payload.close_omitted_on or _now().date()
    for key, row in by_key.items():
        if key in seen:
            continue
        row.effective_to = max(close_on, row.effective_from)
        closed += 1

    await db.flush()
    await write_audit(
        db,
        context,
        event_type="insurance.plan.benefits.replaced",
        resource_id=plan.id,
        event_data={"created": created, "updated": updated, "closed": closed},
        request=request,
    )
    await db.commit()
    benefits = await list_plan_benefits(db, context, plan.id)
    return BenefitGridResult(
        plan_id=plan.id, created=created, updated=updated, closed=closed, benefits=benefits
    )


async def upsert_benefit_explanations(
    db: AsyncSession,
    context: AuthContext,
    plan_id: UUID,
    payload: ExplanationPut,
    *,
    request: Request | None = None,
) -> ExplanationPutResult:
    """Upsert the plain-language layer the patient coverage explainer reads."""
    plan, _ = await _load_plan(db, context, plan_id)
    benefit_ids = {item.plan_benefit_id for item in payload.explanations}
    owned = set(
        (
            await db.scalars(
                select(PlanBenefit.id).where(
                    PlanBenefit.plan_id == plan.id, PlanBenefit.id.in_(benefit_ids)
                )
            )
        ).all()
    )
    missing = benefit_ids - owned
    if missing:
        raise unprocessable(
            "These benefit rows do not belong to this plan: "
            + ", ".join(sorted(str(item) for item in missing))
        )

    existing = list(
        (
            await db.scalars(
                select(BenefitExplanation).where(
                    BenefitExplanation.plan_benefit_id.in_(benefit_ids)
                )
            )
        ).all()
    )
    by_key = {(row.plan_benefit_id, row.locale, row.reading_level): row for row in existing}

    now = _now()
    created = 0
    updated = 0
    touched: list[BenefitExplanation] = []
    for item in payload.explanations:
        key = (item.plan_benefit_id, item.locale, item.reading_level)
        row = by_key.get(key)
        if row is None:
            row = BenefitExplanation(
                tenant_id=context.tenant_id,
                plan_benefit_id=item.plan_benefit_id,
                locale=item.locale,
                reading_level=item.reading_level,
                summary_text=item.summary_text,
                example_scenario=item.example_scenario,
                source_document_asset_id=item.source_document_asset_id,
                generated_by=item.generated_by,
                model_version=item.model_version,
            )
            db.add(row)
            by_key[key] = row
            created += 1
        else:
            row.summary_text = item.summary_text
            row.example_scenario = item.example_scenario
            row.source_document_asset_id = item.source_document_asset_id
            row.generated_by = item.generated_by
            row.model_version = item.model_version
            updated += 1
        # The check constraint keeps reviewed_at and reviewer set or cleared together.
        if item.mark_reviewed:
            row.reviewed_by_user_id = context.user.id
            row.reviewed_at = now
        else:
            row.reviewed_by_user_id = None
            row.reviewed_at = None
        touched.append(row)

    await db.flush()
    for row in touched:
        await db.refresh(row)
    await write_audit(
        db,
        context,
        event_type="insurance.plan.explanations.upserted",
        resource_id=plan.id,
        event_data={"created": created, "updated": updated},
        request=request,
    )
    items = [_explanation_response(row) for row in touched]
    await db.commit()
    return ExplanationPutResult(plan_id=plan.id, created=created, updated=updated, items=items)


# --------------------------------------------------------------------------------------
# eligibility
# --------------------------------------------------------------------------------------


async def _benefit_snapshot(
    db: AsyncSession, plan_id: UUID, service_codes: Sequence[str], on_date: date
) -> list[dict[str, Any]]:
    stmt = select(PlanBenefit).where(
        PlanBenefit.plan_id == plan_id, *_effective_on(PlanBenefit, on_date)
    )
    if service_codes:
        stmt = stmt.where(
            or_(
                PlanBenefit.service_code.in_(list(service_codes)),
                PlanBenefit.service_category.in_(list(service_codes)),
            )
        )
    rows = (
        await db.scalars(
            stmt.order_by(PlanBenefit.service_category, PlanBenefit.network_tier).limit(200)
        )
    ).all()
    return [
        {
            "service_category": row.service_category,
            "service_code": row.service_code,
            "network_tier": row.network_tier.value,
            "covered": row.covered,
            "copay_cents": row.copay_cents,
            "coinsurance_percent": (
                str(row.coinsurance_percent) if row.coinsurance_percent is not None else None
            ),
            "deductible_applies": row.deductible_applies,
            "prior_auth_required": row.prior_auth_required,
            "visit_limit_count": row.visit_limit_count,
            "limit_period": row.limit_period.value if row.limit_period else None,
        }
        for row in rows
    ]


async def _accumulator_snapshot(
    db: AsyncSession, policy_id: UUID, patient_user_id: UUID, benefit_year: int
) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(BenefitAccumulator).where(
                BenefitAccumulator.policy_id == policy_id,
                BenefitAccumulator.patient_user_id == patient_user_id,
                BenefitAccumulator.benefit_year == benefit_year,
            )
        )
    ).all()
    return [
        {
            "accumulator_type": row.accumulator_type.value,
            "limit_cents": row.limit_cents,
            "consumed_cents": row.consumed_cents,
            "remaining_cents": (
                None if row.limit_cents is None else max(row.limit_cents - row.consumed_cents, 0)
            ),
            "consumed_count": row.consumed_count,
        }
        for row in rows
    ]


async def run_eligibility_check(
    db: AsyncSession,
    context: AuthContext,
    payload: EligibilityRequest,
    *,
    request: Request | None = None,
) -> EligibilityResponse:
    now = _now()
    service_date = payload.service_date or now.date()
    codes = [code.strip() for code in payload.service_codes if code.strip()]

    if not payload.force_refresh:
        cached_stmt = (
            select(EligibilityCheck)
            .where(
                EligibilityCheck.id.in_(
                    tenant_scoped(select(EligibilityCheck.id), EligibilityCheck, context)
                ),
                EligibilityCheck.patient_user_id == payload.patient_user_id,
                EligibilityCheck.service_date == service_date,
                EligibilityCheck.status != EligibilityStatus.ERROR,
                EligibilityCheck.cached_until.is_not(None),
                EligibilityCheck.cached_until > now,
            )
            .order_by(EligibilityCheck.created_at.desc())
            .limit(5)
        )
        if payload.member_id:
            cached_stmt = cached_stmt.where(EligibilityCheck.member_id == payload.member_id)
        if payload.policy_id:
            cached_stmt = cached_stmt.where(EligibilityCheck.policy_id == payload.policy_id)
        for candidate in (await db.scalars(cached_stmt)).all():
            if set(codes).issubset(set(candidate.service_codes)):
                await record_phi_access(
                    db,
                    context,
                    patient_user_id=candidate.patient_user_id,
                    resource_type="eligibility_check",
                    resource_id=candidate.id,
                    purpose_of_use="HPAYMT",
                    request=request,
                    result_count=1,
                )
                response = _eligibility_response(candidate, from_cache=True)
                await db.commit()
                return response

    policy = await _resolve_policy(
        db,
        context,
        patient_user_id=payload.patient_user_id,
        on_date=service_date,
        policy_id=payload.policy_id,
        member_id=payload.member_id,
    )

    benefits: dict[str, Any] = {"lines": [], "accumulators": []}
    coverage_found = policy is not None
    status = EligibilityStatus.INACTIVE
    active_from: date | None = None
    active_to: date | None = None
    member_id = payload.member_id or "UNKNOWN"
    payer_organization_id = payload.payer_organization_id or context.tenant_id

    if policy is not None:
        member_id = policy.member_id
        payer_organization_id = policy.payer_organization_id
        active_from = policy.effective_from
        active_to = policy.effective_to
        if policy.status == PolicyStatus.ACTIVE:
            status = EligibilityStatus.ACTIVE
        benefits = {
            "policy_number": policy.policy_number,
            "plan_id": str(policy.plan_id),
            "policy_status": policy.status.value,
            "lines": await _benefit_snapshot(db, policy.plan_id, codes, service_date),
            "accumulators": await _accumulator_snapshot(
                db, policy.id, payload.patient_user_id, service_date.year
            ),
        }

    check = EligibilityCheck(
        tenant_id=context.tenant_id,
        requested_by_user_id=context.user.id,
        patient_user_id=payload.patient_user_id,
        policy_id=policy.id if policy else None,
        payer_organization_id=payer_organization_id,
        member_id=member_id,
        service_date=service_date,
        service_codes=codes,
        status=status,
        coverage_found=coverage_found,
        active_from=active_from,
        active_to=active_to,
        benefits_returned=benefits,
        raw_request={
            "patient_user_id": str(payload.patient_user_id),
            "policy_id": str(payload.policy_id) if payload.policy_id else None,
            "member_id": payload.member_id,
            "service_date": service_date.isoformat(),
            "service_codes": codes,
        },
        raw_response={
            "source": "internal_coverage_ledger",
            "coverage_found": coverage_found,
            "status": status.value,
            "benefit_lines": len(benefits.get("lines", [])),
        },
        transaction_id=uuid4().hex[:32],
        cached_until=(
            now + timedelta(minutes=payload.cache_ttl_minutes)
            if payload.cache_ttl_minutes > 0
            else None
        ),
    )
    db.add(check)
    await db.flush()
    await db.refresh(check)
    await record_phi_access(
        db,
        context,
        patient_user_id=check.patient_user_id,
        resource_type="eligibility_check",
        resource_id=check.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.eligibility.checked",
        subject_user_id=check.patient_user_id,
        resource_id=check.id,
        event_data={"status": status.value, "coverage_found": coverage_found},
        request=request,
    )
    response = _eligibility_response(check, from_cache=False)
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# claims
# --------------------------------------------------------------------------------------


async def list_claims(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: ClaimStatus | None = None,
    payer_organization_id: UUID | None = None,
    submitted_from: date | None = None,
    submitted_to: date | None = None,
    patient_user_id: UUID | None = None,
    breached_only: bool = False,
    request: Request | None = None,
) -> Page[ClaimResponse]:
    """Adjudication queue ordered oldest-first, with SLA age computed in SQL."""
    now = _now()
    age_days = (
        func.extract("epoch", func.now() - func.coalesce(Claim.submitted_at, Claim.created_at))
        / 86400.0
    )
    stmt = (
        select(Claim, Policy.payer_organization_id, _line_count_subquery().label("line_count"))
        .join(Policy, Policy.id == Claim.policy_id)
        .where(Claim.id.in_(_claim_ids(context)))
    )
    if status is not None:
        stmt = stmt.where(Claim.status == status)
    if payer_organization_id is not None:
        stmt = stmt.where(Policy.payer_organization_id == payer_organization_id)
    if submitted_from is not None:
        stmt = stmt.where(
            func.coalesce(Claim.submitted_at, Claim.created_at)
            >= datetime.combine(submitted_from, datetime.min.time(), tzinfo=UTC)
        )
    if submitted_to is not None:
        stmt = stmt.where(
            func.coalesce(Claim.submitted_at, Claim.created_at)
            < datetime.combine(submitted_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        )
    if patient_user_id is not None:
        stmt = stmt.where(Claim.patient_user_id == patient_user_id)
    if breached_only:
        stmt = stmt.where(Claim.status.in_(OPEN_CLAIM_STATUSES), age_days > SLA_TARGET_DAYS)

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = await db.execute(
        stmt.order_by(age_days.desc()).offset(page.offset).limit(page.limit + 1)
    )
    records = rows.all()
    items = [
        _claim_response(claim, payer_id, int(line_count), now=now)
        for claim, payer_id, line_count in records
    ]
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[claim.patient_user_id for claim, _, _ in records[: page.limit]],
        resource_type="claim",
        purpose_of_use="HPAYMT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total=int(total or 0))


async def _load_claim(
    db: AsyncSession, context: AuthContext, claim_id: UUID
) -> tuple[Claim, Policy, InsurancePlan]:
    row = (
        await db.execute(
            select(Claim, Policy, InsurancePlan)
            .join(Policy, Policy.id == Claim.policy_id)
            .join(InsurancePlan, InsurancePlan.id == Policy.plan_id)
            .where(Claim.id == claim_id, Claim.id.in_(_claim_ids(context)))
        )
    ).first()
    if row is None:
        raise not_found("Claim")
    claim, policy, plan = row
    return claim, policy, plan


async def _apply_accumulator(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    policy_id: UUID,
    patient_user_id: UUID,
    accumulator_type: AccumulatorType,
    benefit_year: int,
    limit_cents: int | None,
    delta_cents: int,
    delta_count: int,
    now: datetime,
) -> None:
    """Insert-or-increment an accumulator, clamped to its limit by the database."""
    seeded = delta_cents if limit_cents is None else min(delta_cents, limit_cents)
    stmt = pg_insert(BenefitAccumulator).values(
        id=uuid4(),
        tenant_id=tenant_id,
        policy_id=policy_id,
        patient_user_id=patient_user_id,
        accumulator_type=accumulator_type,
        benefit_year=benefit_year,
        limit_cents=limit_cents,
        consumed_cents=max(seeded, 0),
        consumed_count=max(delta_count, 0),
        as_of=now,
    )
    running = BenefitAccumulator.consumed_cents + delta_cents
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                BenefitAccumulator.policy_id,
                BenefitAccumulator.patient_user_id,
                BenefitAccumulator.accumulator_type,
                BenefitAccumulator.benefit_year,
            ],
            set_={
                "consumed_cents": func.greatest(
                    func.least(func.coalesce(BenefitAccumulator.limit_cents, running), running), 0
                ),
                "consumed_count": BenefitAccumulator.consumed_count + delta_count,
                "as_of": now,
                "updated_at": now,
            },
        )
    )


async def adjudicate_claim(
    db: AsyncSession,
    context: AuthContext,
    claim_id: UUID,
    payload: AdjudicateRequest,
    *,
    request: Request | None = None,
) -> AdjudicationResult:
    """Decide a claim: price every line, move accumulators, append the claim event."""
    now = _now()
    claim, policy, plan = await _load_claim(db, context, claim_id)
    assert_transition(claim.status.value, payload.status, CLAIM_TRANSITIONS)

    lines = list(
        (
            await db.scalars(
                select(ClaimLine)
                .where(ClaimLine.claim_id == claim.id)
                .order_by(ClaimLine.line_number)
            )
        ).all()
    )
    if not lines:
        raise unprocessable("Claim has no lines to adjudicate")

    by_number = {line.line_number: line for line in lines}
    decided = {item.line_number for item in payload.lines}
    if len(decided) != len(payload.lines):
        raise unprocessable("Duplicate line_number in the adjudication payload")
    if decided != set(by_number):
        raise unprocessable(
            "Every claim line must be decided; expected lines "
            + ", ".join(str(number) for number in sorted(by_number))
        )

    total_allowed = 0
    total_paid = 0
    total_member = 0
    total_deductible = 0
    for item in payload.lines:
        line = by_number[item.line_number]
        member_share = item.copay_cents + item.coinsurance_cents + item.deductible_cents
        if item.allowed_cents > line.charge_cents:
            raise unprocessable(f"Line {item.line_number}: allowed_cents exceeds the billed charge")
        if item.paid_cents + member_share > item.allowed_cents:
            raise unprocessable(
                f"Line {item.line_number}: paid plus member responsibility exceeds allowed_cents"
            )
        line.allowed_cents = item.allowed_cents
        line.paid_cents = item.paid_cents
        line.copay_cents = item.copay_cents
        line.coinsurance_cents = item.coinsurance_cents
        line.deductible_cents = item.deductible_cents
        line.adjustment_reason_codes = item.adjustment_reason_codes
        total_allowed += item.allowed_cents
        total_paid += item.paid_cents
        total_member += member_share
        total_deductible += item.deductible_cents

    first_decision = claim.adjudicated_at is None
    from_status = claim.status.value
    claim.allowed_cents = total_allowed
    claim.paid_cents = total_paid
    claim.patient_responsibility_cents = total_member
    claim.status = ClaimStatus(payload.status)
    claim.adjudicated_at = now

    benefit_year = payload.benefit_year or claim.service_from.year
    if first_decision:
        # Accumulators move exactly once, on the first decision for this claim.
        await _apply_accumulator(
            db,
            tenant_id=claim.tenant_id,
            policy_id=policy.id,
            patient_user_id=claim.patient_user_id,
            accumulator_type=AccumulatorType.INDIVIDUAL_DEDUCTIBLE,
            benefit_year=benefit_year,
            limit_cents=plan.individual_deductible_cents,
            delta_cents=total_deductible,
            delta_count=0,
            now=now,
        )
        await _apply_accumulator(
            db,
            tenant_id=claim.tenant_id,
            policy_id=policy.id,
            patient_user_id=claim.patient_user_id,
            accumulator_type=AccumulatorType.INDIVIDUAL_OOP,
            benefit_year=benefit_year,
            limit_cents=plan.individual_oop_max_cents,
            delta_cents=total_member,
            delta_count=len(lines),
            now=now,
        )

    event = ClaimEvent(
        tenant_id=claim.tenant_id,
        claim_id=claim.id,
        event_type="adjudicated",
        from_status=from_status,
        to_status=claim.status.value,
        actor_user_id=context.user.id,
        payload={
            "allowed_cents": total_allowed,
            "paid_cents": total_paid,
            "patient_responsibility_cents": total_member,
            "deductible_applied_cents": total_deductible,
            "currency": claim.currency,
            "benefit_year": benefit_year,
            "accumulators_applied": first_decision,
            "payment_reference": payload.payment_reference,
            "note": payload.note,
        },
        occurred_at=now,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    accumulators = list(
        (
            await db.scalars(
                select(BenefitAccumulator).where(
                    BenefitAccumulator.policy_id == policy.id,
                    BenefitAccumulator.patient_user_id == claim.patient_user_id,
                    BenefitAccumulator.benefit_year == benefit_year,
                )
            )
        ).all()
    )
    await record_phi_access(
        db,
        context,
        patient_user_id=claim.patient_user_id,
        resource_type="claim",
        resource_id=claim.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.claim.adjudicated",
        subject_user_id=claim.patient_user_id,
        resource_id=claim.id,
        event_data={
            "from_status": from_status,
            "to_status": claim.status.value,
            "allowed_cents": total_allowed,
            "paid_cents": total_paid,
            "currency": claim.currency,
        },
        request=request,
    )
    result = AdjudicationResult(
        claim=_claim_response(claim, policy.payer_organization_id, len(lines), now=now),
        lines=[_claim_line_response(line) for line in lines],
        accumulators=[_accumulator_response(row) for row in accumulators],
        accumulators_applied=first_decision,
        event_id=event.id,
    )
    await db.commit()
    return result


async def deny_claim(
    db: AsyncSession,
    context: AuthContext,
    claim_id: UUID,
    payload: DenyRequest,
    *,
    request: Request | None = None,
) -> ClaimResponse:
    now = _now()
    claim, policy, _ = await _load_claim(db, context, claim_id)
    assert_transition(claim.status.value, ClaimStatus.DENIED.value, CLAIM_TRANSITIONS)

    from_status = claim.status.value
    claim.status = ClaimStatus.DENIED
    claim.denial_reason_code = payload.reason_code
    claim.paid_cents = 0
    claim.adjudicated_at = now

    line_count = await db.scalar(
        select(func.count(ClaimLine.id)).where(ClaimLine.claim_id == claim.id)
    )
    db.add(
        ClaimEvent(
            tenant_id=claim.tenant_id,
            claim_id=claim.id,
            event_type="denied",
            from_status=from_status,
            to_status=ClaimStatus.DENIED.value,
            actor_user_id=context.user.id,
            payload={
                "reason_code": payload.reason_code,
                "reason_description": payload.reason_description,
            },
            occurred_at=now,
        )
    )
    await db.flush()
    await record_phi_access(
        db,
        context,
        patient_user_id=claim.patient_user_id,
        resource_type="claim",
        resource_id=claim.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.claim.denied",
        subject_user_id=claim.patient_user_id,
        resource_id=claim.id,
        event_data={"from_status": from_status, "reason_code": payload.reason_code},
        request=request,
    )
    response = _claim_response(claim, policy.payer_organization_id, int(line_count or 0), now=now)
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# prior authorizations
# --------------------------------------------------------------------------------------


async def _evidence_counts(db: AsyncSession, auth_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not auth_ids:
        return {}
    rows = await db.execute(
        select(DocumentLink.subject_id, func.count(DocumentLink.id))
        .where(
            DocumentLink.subject_type == "prior_authorization",
            DocumentLink.subject_id.in_(auth_ids),
        )
        .group_by(DocumentLink.subject_id)
    )
    return {subject_id: count for subject_id, count in rows.all()}


async def list_prior_authorizations(
    db: AsyncSession,
    context: AuthContext,
    *,
    page: Pagination,
    status: PriorAuthStatus | None = None,
    patient_user_id: UUID | None = None,
    policy_id: UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    request: Request | None = None,
) -> Page[PriorAuthResponse]:
    stmt = select(PriorAuthorization).where(
        PriorAuthorization.id.in_(
            tenant_scoped(select(PriorAuthorization.id), PriorAuthorization, context)
        )
    )
    if status is not None:
        stmt = stmt.where(PriorAuthorization.status == status)
    if patient_user_id is not None:
        stmt = stmt.where(PriorAuthorization.patient_user_id == patient_user_id)
    if policy_id is not None:
        stmt = stmt.where(PriorAuthorization.policy_id == policy_id)
    if created_from is not None:
        stmt = stmt.where(
            PriorAuthorization.created_at
            >= datetime.combine(created_from, datetime.min.time(), tzinfo=UTC)
        )
    if created_to is not None:
        stmt = stmt.where(
            PriorAuthorization.created_at
            < datetime.combine(created_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        )

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = list(
        (
            await db.scalars(
                stmt.order_by(PriorAuthorization.created_at.desc())
                .offset(page.offset)
                .limit(page.limit + 1)
            )
        ).all()
    )
    counts = await _evidence_counts(db, [row.id for row in rows])
    items = [_prior_auth_response(row, counts.get(row.id, 0)) for row in rows]
    await record_phi_access_many(
        db,
        context,
        patient_user_ids=[row.patient_user_id for row in rows[: page.limit]],
        resource_type="prior_authorization",
        purpose_of_use="HPAYMT",
        request=request,
    )
    await db.commit()
    return paginate(items, page, total=int(total or 0))


async def create_prior_authorization(
    db: AsyncSession,
    context: AuthContext,
    payload: PriorAuthCreate,
    *,
    request: Request | None = None,
) -> PriorAuthResponse:
    policy = await db.scalar(
        select(Policy).where(
            Policy.id == payload.policy_id,
            Policy.id.in_(tenant_scoped(select(Policy.id), Policy, context)),
        )
    )
    if policy is None:
        raise not_found("Policy")
    member = await db.scalar(
        select(PolicyMember.id).where(
            PolicyMember.policy_id == policy.id,
            PolicyMember.patient_user_id == payload.patient_user_id,
        )
    )
    if member is None:
        raise unprocessable("That patient is not a member of the policy")

    auth = PriorAuthorization(
        tenant_id=context.tenant_id,
        policy_id=policy.id,
        patient_user_id=payload.patient_user_id,
        requesting_provider_user_id=payload.requesting_provider_user_id,
        service_codes=payload.service_codes,
        diagnosis_codes=payload.diagnosis_codes,
        units_requested=payload.units_requested,
        clinical_justification=payload.clinical_justification,
        criteria_met=payload.criteria_met,
        status=PriorAuthStatus.SUBMITTED if payload.submit else PriorAuthStatus.DRAFT,
    )
    db.add(auth)
    await db.flush()
    for asset_id in dict.fromkeys(payload.document_asset_ids):
        db.add(
            DocumentLink(
                tenant_id=context.tenant_id,
                document_asset_id=asset_id,
                subject_type="prior_authorization",
                subject_id=auth.id,
                link_type=DocumentLinkType.EVIDENCE,
                linked_by_user_id=context.user.id,
            )
        )
    await db.flush()
    await db.refresh(auth)
    await record_phi_access(
        db,
        context,
        patient_user_id=auth.patient_user_id,
        resource_type="prior_authorization",
        resource_id=auth.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.prior_authorization.created",
        subject_user_id=auth.patient_user_id,
        resource_id=auth.id,
        event_data={"status": auth.status.value, "service_codes": auth.service_codes},
        request=request,
    )
    response = _prior_auth_response(auth, len(set(payload.document_asset_ids)))
    await db.commit()
    return response


async def decide_prior_authorization(
    db: AsyncSession,
    context: AuthContext,
    auth_id: UUID,
    payload: PriorAuthDecision,
    *,
    request: Request | None = None,
) -> PriorAuthResponse:
    now = _now()
    auth = await db.scalar(
        select(PriorAuthorization).where(
            PriorAuthorization.id == auth_id,
            PriorAuthorization.id.in_(
                tenant_scoped(select(PriorAuthorization.id), PriorAuthorization, context)
            ),
        )
    )
    if auth is None:
        raise not_found("Prior authorization")
    assert_transition(auth.status.value, payload.decision, PRIOR_AUTH_TRANSITIONS)

    decision = PriorAuthStatus(payload.decision)
    if (
        payload.units_approved is not None
        and auth.units_requested is not None
        and payload.units_approved > auth.units_requested
    ):
        raise unprocessable("units_approved cannot exceed units_requested")
    if decision == PriorAuthStatus.PARTIALLY_APPROVED and payload.units_approved is None:
        raise unprocessable("units_approved is required for a partial approval")

    from_status = auth.status.value
    auth.status = decision
    auth.decision_reason = payload.reason
    auth.reviewer_user_id = payload.reviewer_user_id or context.user.id
    auth.decision_at = now
    if decision in {PriorAuthStatus.APPROVED, PriorAuthStatus.PARTIALLY_APPROVED}:
        auth.units_approved = payload.units_approved or auth.units_requested
        auth.valid_from = payload.valid_from or now.date()
        auth.valid_to = payload.valid_to
        auth.authorization_number = payload.authorization_number or f"PA-{uuid4().hex[:12].upper()}"
    elif decision == PriorAuthStatus.DENIED:
        auth.units_approved = 0

    await db.flush()
    await db.refresh(auth)
    counts = await _evidence_counts(db, [auth.id])
    await record_phi_access(
        db,
        context,
        patient_user_id=auth.patient_user_id,
        resource_type="prior_authorization",
        resource_id=auth.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.prior_authorization.decided",
        subject_user_id=auth.patient_user_id,
        resource_id=auth.id,
        event_data={
            "from_status": from_status,
            "to_status": decision.value,
            "reviewer_user_id": str(auth.reviewer_user_id),
            "authorization_number": auth.authorization_number,
        },
        request=request,
    )
    response = _prior_auth_response(auth, counts.get(auth.id, 0))
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# cost estimates
# --------------------------------------------------------------------------------------


async def create_cost_estimate(
    db: AsyncSession,
    context: AuthContext,
    payload: CostEstimateRequest,
    *,
    request: Request | None = None,
) -> CostEstimateResponse:
    """Price a service bundle against contracted rates, plan benefits and accumulators."""
    now = _now()
    service_date = payload.service_date or now.date()
    codes = [line.service_code for line in payload.bundle]
    categories = [line.service_category for line in payload.bundle if line.service_category]

    policy = await _resolve_policy(
        db,
        context,
        patient_user_id=payload.patient_user_id,
        on_date=service_date,
        policy_id=payload.policy_id,
    )
    if payload.policy_id is not None and policy is None:
        raise not_found("Policy for that member and service date")

    plan: InsurancePlan | None = None
    if policy is not None:
        plan = await db.scalar(select(InsurancePlan).where(InsurancePlan.id == policy.plan_id))
    payer_organization_id = policy.payer_organization_id if policy else context.tenant_id

    # DISTINCT ON keeps the newest effective row per service code in one round trip.
    rate_rows = (
        await db.scalars(
            select(PayerContractRate)
            .where(
                PayerContractRate.payer_organization_id == payer_organization_id,
                PayerContractRate.provider_organization_id == payload.organization_id,
                PayerContractRate.service_code.in_(codes),
                *_effective_on(PayerContractRate, service_date),
            )
            .order_by(PayerContractRate.service_code, PayerContractRate.effective_from.desc())
            .distinct(PayerContractRate.service_code)
        )
    ).all()
    rates = {row.service_code: row for row in rate_rows}

    # Service items belong to the *provider* tenant, so they are filtered by
    # organization_id rather than the payer's tenant scope.
    item_rows = (
        await db.scalars(
            select(ServiceItem)
            .where(
                ServiceItem.organization_id == payload.organization_id,
                ServiceItem.service_code.in_(codes),
                ServiceItem.is_active.is_(True),
                *_effective_on(ServiceItem, service_date),
            )
            .order_by(ServiceItem.service_code, ServiceItem.effective_from.desc())
            .distinct(ServiceItem.service_code)
        )
    ).all()
    items = {row.service_code: row for row in item_rows}

    benefits_by_code: dict[tuple[str, NetworkTier], PlanBenefit] = {}
    benefits_by_category: dict[tuple[str, NetworkTier], PlanBenefit] = {}
    if plan is not None:
        benefit_rows = (
            await db.scalars(
                select(PlanBenefit)
                .where(
                    PlanBenefit.plan_id == plan.id,
                    or_(
                        PlanBenefit.service_code.in_(codes),
                        PlanBenefit.service_category.in_(categories or [""]),
                    ),
                    *_effective_on(PlanBenefit, service_date),
                )
                .order_by(PlanBenefit.effective_from.desc())
            )
        ).all()
        for row in benefit_rows:
            if row.service_code:
                benefits_by_code.setdefault((row.service_code, row.network_tier), row)
            else:
                benefits_by_category.setdefault((row.service_category, row.network_tier), row)

    benefit_year = service_date.year
    deductible_remaining: int | None = None
    oop_remaining: int | None = None
    if policy is not None and plan is not None:
        accumulators = {
            row.accumulator_type: row
            for row in (
                await db.scalars(
                    select(BenefitAccumulator).where(
                        BenefitAccumulator.policy_id == policy.id,
                        BenefitAccumulator.patient_user_id == payload.patient_user_id,
                        BenefitAccumulator.benefit_year == benefit_year,
                        BenefitAccumulator.accumulator_type.in_(
                            [AccumulatorType.INDIVIDUAL_DEDUCTIBLE, AccumulatorType.INDIVIDUAL_OOP]
                        ),
                    )
                )
            ).all()
        }
        deductible_acc = accumulators.get(AccumulatorType.INDIVIDUAL_DEDUCTIBLE)
        deductible_limit = (
            deductible_acc.limit_cents
            if deductible_acc and deductible_acc.limit_cents is not None
            else plan.individual_deductible_cents
        )
        if deductible_limit is not None:
            consumed = deductible_acc.consumed_cents if deductible_acc else 0
            deductible_remaining = max(deductible_limit - consumed, 0)
        oop_acc = accumulators.get(AccumulatorType.INDIVIDUAL_OOP)
        oop_limit = (
            oop_acc.limit_cents
            if oop_acc and oop_acc.limit_cents is not None
            else plan.individual_oop_max_cents
        )
        if oop_limit is not None:
            oop_remaining = max(oop_limit - (oop_acc.consumed_cents if oop_acc else 0), 0)

    currency = payload.currency or (policy.currency if policy else None)
    for rate_row in rate_rows:
        currency = currency or rate_row.currency
    for item_row in item_rows:
        currency = currency or item_row.currency
    if currency is None:
        raise unprocessable("Cannot determine a currency for this estimate")

    deductible_left = deductible_remaining
    oop_left = oop_remaining
    breakdown: list[CostEstimateLine] = []
    missing_rate = 0
    missing_benefit = 0
    missing_price = 0
    for line in payload.bundle:
        rate = rates.get(line.service_code)
        item = items.get(line.service_code)
        if rate is None:
            missing_rate += 1
        if item is None:
            missing_price += 1
        unit_billed = (
            item.base_price_cents
            if item is not None
            else (rate.allowed_cents if rate is not None else 0)
        )
        billed = unit_billed * line.units
        allowed = rate.allowed_cents * line.units if rate is not None else billed

        benefit = benefits_by_code.get((line.service_code, line.network_tier))
        source: Literal["service_code", "service_category", "none", "self_pay"] = "service_code"
        if benefit is None and line.service_category:
            benefit = benefits_by_category.get((line.service_category, line.network_tier))
            source = "service_category"
        if plan is None:
            source = "self_pay"
        elif benefit is None:
            source = "none"
            missing_benefit += 1

        copay = 0
        deductible_applied = 0
        coinsurance = 0
        if benefit is None or not benefit.covered:
            member = allowed
            plan_pays = 0
            covered = benefit.covered if benefit is not None else False
        else:
            covered = True
            copay = min(benefit.copay_cents or 0, allowed)
            remainder = allowed - copay
            if benefit.deductible_applies and deductible_left:
                deductible_applied = min(remainder, deductible_left)
                deductible_left -= deductible_applied
                remainder -= deductible_applied
            coinsurance = _coinsurance_of(remainder, benefit.coinsurance_percent)
            plan_pays = remainder - coinsurance
            member = copay + deductible_applied + coinsurance
            if oop_left is not None:
                capped = min(member, oop_left)
                plan_pays += member - capped
                oop_left -= capped
                member = capped

        breakdown.append(
            CostEstimateLine(
                service_code=line.service_code,
                service_display=(
                    line.service_display
                    or (item.service_display if item else None)
                    or (rate.service_display if rate else None)
                    or line.service_code
                ),
                units=line.units,
                network_tier=line.network_tier,
                billed_cents=billed,
                contracted_rate_cents=rate.allowed_cents if rate is not None else None,
                allowed_cents=allowed,
                copay_cents=copay,
                deductible_applied_cents=deductible_applied,
                coinsurance_cents=coinsurance,
                member_liability_cents=member,
                plan_pays_cents=plan_pays,
                covered=covered,
                prior_auth_required=bool(benefit and benefit.prior_auth_required),
                benefit_source=source,
            )
        )

    confidence = Decimal("0.95") if policy is not None else Decimal("0.50")
    if missing_rate:
        confidence -= Decimal("0.15")
    if missing_benefit:
        confidence -= Decimal("0.20")
    if missing_price:
        confidence -= Decimal("0.05")
    confidence = min(max(confidence, Decimal("0.10")), Decimal("0.99")).quantize(Decimal("0.0001"))

    contracted_total = sum(
        line.contracted_rate_cents * line.units
        for line in breakdown
        if line.contracted_rate_cents is not None
    )
    estimate = CostEstimate(
        tenant_id=context.tenant_id,
        patient_user_id=payload.patient_user_id,
        policy_id=policy.id if policy else None,
        organization_id=payload.organization_id,
        service_item_id=payload.service_item_id,
        service_bundle=[line.model_dump(mode="json") for line in breakdown],
        billed_cents=sum(line.billed_cents for line in breakdown),
        contracted_rate_cents=contracted_total or None,
        deductible_applied_cents=sum(line.deductible_applied_cents for line in breakdown),
        coinsurance_cents=sum(line.coinsurance_cents for line in breakdown),
        copay_cents=sum(line.copay_cents for line in breakdown),
        member_liability_cents=sum(line.member_liability_cents for line in breakdown),
        plan_pays_cents=sum(line.plan_pays_cents for line in breakdown),
        deductible_remaining_cents=deductible_left,
        currency=currency,
        confidence=confidence,
        assumptions={
            "service_date": service_date.isoformat(),
            "benefit_year": benefit_year,
            "payer_organization_id": str(payer_organization_id),
            "plan_id": str(plan.id) if plan else None,
            "policy_status": policy.status.value if policy else None,
            "deductible_remaining_before_cents": deductible_remaining,
            "oop_remaining_before_cents": oop_remaining,
            "lines_without_contract_rate": missing_rate,
            "lines_without_plan_benefit": missing_benefit,
            "lines_without_provider_price": missing_price,
        },
        expires_at=now + timedelta(days=payload.valid_days),
    )
    db.add(estimate)
    await db.flush()
    await db.refresh(estimate)
    await record_phi_access(
        db,
        context,
        patient_user_id=estimate.patient_user_id,
        resource_type="cost_estimate",
        resource_id=estimate.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    await write_audit(
        db,
        context,
        event_type="insurance.cost_estimate.created",
        subject_user_id=estimate.patient_user_id,
        resource_id=estimate.id,
        event_data={
            "member_liability_cents": estimate.member_liability_cents,
            "plan_pays_cents": estimate.plan_pays_cents,
            "currency": estimate.currency,
            "confidence": str(confidence),
        },
        request=request,
    )
    response = _cost_estimate_response(estimate, now=now)
    await db.commit()
    return response


async def get_cost_estimate(
    db: AsyncSession,
    context: AuthContext,
    estimate_id: UUID,
    *,
    request: Request | None = None,
) -> CostEstimateResponse:
    estimate = await db.scalar(
        select(CostEstimate).where(
            CostEstimate.id == estimate_id,
            CostEstimate.id.in_(tenant_scoped(select(CostEstimate.id), CostEstimate, context)),
        )
    )
    if estimate is None:
        raise not_found("Cost estimate")
    await record_phi_access(
        db,
        context,
        patient_user_id=estimate.patient_user_id,
        resource_type="cost_estimate",
        resource_id=estimate.id,
        purpose_of_use="HPAYMT",
        request=request,
        result_count=1,
    )
    response = _cost_estimate_response(estimate, now=_now())
    await db.commit()
    return response


# --------------------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------------------


async def analytics_summary(
    db: AsyncSession,
    context: AuthContext,
    *,
    window_from: date | None = None,
    window_to: date | None = None,
) -> AnalyticsSummary:
    """Adjudication throughput and approval rates, aggregated entirely in SQL."""
    now = _now()
    end = window_to or now.date()
    start = window_from or (end - timedelta(days=29))
    if start > end:
        raise unprocessable("window_from must not be after window_to")
    window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    window_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    window_days = (end - start).days + 1

    claim_ids = _claim_ids(context)
    received = func.coalesce(Claim.submitted_at, Claim.created_at)
    in_window = (
        Claim.id.in_(claim_ids),
        received >= window_start,
        received < window_end,
    )

    status_rows = (
        await db.execute(
            select(Claim.status, func.count(Claim.id)).where(*in_window).group_by(Claim.status)
        )
    ).all()
    by_status = {row_status: int(count) for row_status, count in status_rows}
    claims_total = sum(by_status.values())
    approved_count = sum(by_status.get(item, 0) for item in APPROVED_CLAIM_STATUSES)
    denied_count = by_status.get(ClaimStatus.DENIED, 0)
    decided_count = approved_count + denied_count

    avg_days = await db.scalar(
        select(
            func.avg(func.extract("epoch", Claim.adjudicated_at - Claim.submitted_at) / 86400.0)
        ).where(
            *in_window,
            Claim.adjudicated_at.is_not(None),
            Claim.submitted_at.is_not(None),
        )
    )

    currency_rows = (
        await db.execute(
            select(
                Claim.currency,
                func.coalesce(func.sum(Claim.total_charge_cents), 0),
                func.coalesce(func.sum(Claim.allowed_cents), 0),
                func.coalesce(func.sum(Claim.paid_cents), 0),
            )
            .where(*in_window)
            .group_by(Claim.currency)
            .order_by(Claim.currency)
        )
    ).all()

    open_age = func.extract("epoch", func.now() - received) / 86400.0
    open_row = (
        await db.execute(
            select(
                func.count(Claim.id),
                func.max(open_age),
                func.count(Claim.id).filter(open_age > SLA_TARGET_DAYS),
            ).where(Claim.id.in_(claim_ids), Claim.status.in_(OPEN_CLAIM_STATUSES))
        )
    ).one()

    auth_ids = tenant_scoped(select(PriorAuthorization.id), PriorAuthorization, context)
    auth_window = (
        PriorAuthorization.id.in_(auth_ids),
        PriorAuthorization.created_at >= window_start,
        PriorAuthorization.created_at < window_end,
    )
    auth_rows = (
        await db.execute(
            select(PriorAuthorization.status, func.count(PriorAuthorization.id))
            .where(*auth_window)
            .group_by(PriorAuthorization.status)
        )
    ).all()
    auth_by_status = {row_status: int(count) for row_status, count in auth_rows}
    auth_avg_days = await db.scalar(
        select(
            func.avg(
                func.extract(
                    "epoch", PriorAuthorization.decision_at - PriorAuthorization.created_at
                )
                / 86400.0
            )
        ).where(*auth_window, PriorAuthorization.decision_at.is_not(None))
    )
    auth_approved = auth_by_status.get(PriorAuthStatus.APPROVED, 0)
    auth_partial = auth_by_status.get(PriorAuthStatus.PARTIALLY_APPROVED, 0)
    auth_denied = auth_by_status.get(PriorAuthStatus.DENIED, 0)
    auth_pending = sum(
        auth_by_status.get(item, 0)
        for item in (PriorAuthStatus.DRAFT, PriorAuthStatus.SUBMITTED, PriorAuthStatus.PENDED)
    )
    auth_decided = auth_approved + auth_partial + auth_denied

    premium_rows = (
        await db.execute(
            select(
                PremiumSchedule.status,
                func.count(PremiumSchedule.id),
                func.coalesce(func.sum(PremiumSchedule.amount_cents), 0),
            )
            .where(
                PremiumSchedule.id.in_(
                    tenant_scoped(select(PremiumSchedule.id), PremiumSchedule, context)
                ),
                PremiumSchedule.due_date >= start,
                PremiumSchedule.due_date <= end,
            )
            .group_by(PremiumSchedule.status)
        )
    ).all()
    premiums = {row_status: (int(count), int(amount)) for row_status, count, amount in premium_rows}

    return AnalyticsSummary(
        window_from=start,
        window_to=end,
        window_days=window_days,
        claims_total=claims_total,
        claims_by_status=[
            StatusCount(status=str(key.value), count=value)
            for key, value in sorted(by_status.items(), key=lambda pair: str(pair[0].value))
        ],
        decided_count=decided_count,
        approved_count=approved_count,
        denied_count=denied_count,
        approval_rate=_pct(approved_count, decided_count),
        avg_days_to_decision=round(float(avg_days), 3) if avg_days is not None else None,
        throughput_per_day=round(decided_count / window_days, 3),
        open_count=int(open_row[0] or 0),
        open_sla_breached_count=int(open_row[2] or 0),
        oldest_open_age_days=(round(float(open_row[1]), 3) if open_row[1] is not None else None),
        totals_by_currency=[
            CurrencyTotals(
                currency=currency,
                charged_cents=int(charged),
                allowed_cents=int(allowed),
                paid_cents=int(paid),
            )
            for currency, charged, allowed, paid in currency_rows
        ],
        prior_authorizations=PriorAuthSummary(
            total=sum(auth_by_status.values()),
            approved=auth_approved,
            partially_approved=auth_partial,
            denied=auth_denied,
            pending=auth_pending,
            approval_rate=_pct(auth_approved + auth_partial, auth_decided),
            avg_days_to_decision=(
                round(float(auth_avg_days), 3) if auth_avg_days is not None else None
            ),
        ),
        premiums=PremiumSummary(
            due_count=premiums.get("due", (0, 0))[0],
            due_cents=premiums.get("due", (0, 0))[1],
            paid_count=premiums.get("paid", (0, 0))[0],
            paid_cents=premiums.get("paid", (0, 0))[1],
            overdue_count=premiums.get("overdue", (0, 0))[0],
            overdue_cents=premiums.get("overdue", (0, 0))[1],
        ),
    )
