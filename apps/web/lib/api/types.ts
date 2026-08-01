/**
 * Domain payload types for the HealthOS API.
 *
 * Generated from the live OpenAPI contract exposed by `healthos_api.main.create_app()`
 * (`components.schemas`), narrowed to the schemas reachable from the clinical,
 * medications, scheduling, labs, coverage, payer and operations routers.
 *
 * Conventions carried over from the backend contract:
 * - `string` in `format: uuid` / `date` / `date-time` positions — ISO-8601 strings.
 * - Decimal quantities (doses, percentiles, rates) are serialised as strings to
 *   preserve precision; parse with `Number(...)` only at the render edge.
 * - Money is always an integer count of minor units, in fields suffixed `_cents`.
 */

/** Envelope returned by every list endpoint. */
export interface Page<T> {
  items: T[];
  /** Absent when the backend skips the count query. */
  total?: number | null;
  limit: number;
  offset: number;
  has_more: boolean;
}

export type AccountType = "patient" | "doctor" | "hospital" | "insurance" | "admin";

export interface AccumulatorRead {
  id: string;
  accumulator_type: string;
  benefit_year: number;
  limit_cents: number | null;
  consumed_cents: number;
  remaining_cents: number | null;
  limit_count: number | null;
  consumed_count: number;
  as_of: string;
}

export interface AccumulatorResponse {
  id: string;
  policy_id: string;
  patient_user_id: string;
  accumulator_type: AccumulatorType;
  benefit_year: number;
  limit_cents: number | null;
  consumed_cents: number;
  limit_count: number | null;
  consumed_count: number;
  remaining_cents: number | null;
  as_of: string;
}

export type AccumulatorType = "individual_deductible" | "family_deductible" | "individual_oop" | "family_oop" | "visit_limit";

export interface AckResult {
  occurrence_id: string;
  occurrence_status: ReminderStatus;
  scheduled_at: string;
  event: AdherenceEventOut;
}

export interface AddendumCreate {
  content: string;
}

export interface AddendumOut {
  id: string;
  clinical_note_id: string;
  author_user_id: string;
  content: string;
  sequence: number;
  signed_at: string;
  signature_hash: string;
  created_at: string;
}

export interface AdherenceEventOut {
  id: string;
  patient_user_id: string;
  schedule_id: string;
  occurrence_id: string | null;
  medication_request_id: string;
  status: AdherenceStatus;
  scheduled_at: string;
  recorded_at: string;
  taken_at: string | null;
  dose_taken_quantity: string | null;
  dose_unit: string | null;
  reported_by_user_id: string;
  reason_code: string | null;
  note: string | null;
}

export interface AdherenceReport {
  patient_user_id: string;
  window_start: string;
  window_end: string;
  days: number;
  expected_doses: number;
  taken_doses: number;
  adherence_rate: string;
  items: AdherenceRow[];
}

export interface AdherenceRow {
  medication_request_id: string;
  medication_code: string;
  medication_display: string;
  expected_doses: number;
  taken_doses: number;
  skipped_doses: number;
  missed_doses: number;
  adherence_rate: string;
}

export type AdherenceStatus = "taken" | "not-taken" | "skipped" | "snoozed" | "entered-in-error";

export interface AdjudicateRequest {
  lines: AdjudicationLine[];
  status?: "adjudicated" | "paid";
  benefit_year?: number | null;
  note?: string | null;
  payment_reference?: string | null;
}

export interface AdjudicationLine {
  line_number: number;
  allowed_cents: number;
  paid_cents: number;
  copay_cents?: number;
  coinsurance_cents?: number;
  deductible_cents?: number;
  adjustment_reason_codes?: string[];
}

export interface AdjudicationResult {
  claim: ClaimResponse;
  lines: ClaimLineResponse[];
  accumulators: AccumulatorResponse[];
  accumulators_applied: boolean;
  event_id: string;
}

export interface AgingBucket {
  bucket: string;
  invoice_count: number;
  balance_cents: number;
}

export type AllergyCategory = "food" | "medication" | "environment" | "biologic";

export interface AllergyCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  encounter_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  substance_code_system: string;
  substance_code: string;
  substance_display: string;
  substance_concept_id?: string | null;
  substance_is_class?: boolean;
  type?: AllergyType;
  category: AllergyCategory;
  criticality?: Criticality;
  clinical_status?: ClinicalStatus;
  verification_status?: AllergyVerificationStatus;
  asserter_type?: AsserterType;
  onset_date?: string | null;
  onset_precision?: "day" | "month" | "year" | null;
  last_occurrence_at?: string | null;
  note?: string | null;
  reactions?: AllergyReactionCreate[];
}

export interface AllergyOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  substance_code_system: string;
  substance_code: string;
  substance_display: string;
  substance_is_class: boolean;
  type: AllergyType;
  category: AllergyCategory;
  criticality: Criticality;
  clinical_status: ClinicalStatus;
  verification_status: AllergyVerificationStatus;
  asserter_type: AsserterType;
  onset_date: string | null;
  last_occurrence_at: string | null;
  note: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
  reactions: AllergyReactionOut[];
}

export interface AllergyReactionCreate {
  manifestation_code_system: string;
  manifestation_code: string;
  manifestation_display: string;
  manifestation_concept_id?: string | null;
  severity?: ReactionSeverity | null;
  exposure_route_code_system?: string | null;
  exposure_route_code?: string | null;
  exposure_route_display?: string | null;
  onset_at?: string | null;
  note?: string | null;
}

export interface AllergyReactionOut {
  id: string;
  manifestation_code_system: string;
  manifestation_code: string;
  manifestation_display: string;
  severity: ReactionSeverity | null;
  exposure_route_code: string | null;
  exposure_route_display: string | null;
  onset_at: string | null;
  note: string | null;
}

/** Attest that the allergy list was looked at, and by whom. */
export interface AllergyReviewIn {
  no_known_allergies?: boolean;
  note?: string | null;
}

export interface AllergyStatusOut {
  patient_user_id: string;
  no_known_allergies: boolean;
  last_reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  note: string | null;
  active_allergy_count: number;
}

export type AllergyType = "allergy" | "intolerance";

export type AllergyVerificationStatus = "unconfirmed" | "presumed" | "confirmed" | "refuted" | "entered-in-error";

export interface AnalyticsSummary {
  window_from: string;
  window_to: string;
  window_days: number;
  claims_total: number;
  claims_by_status: StatusCount[];
  decided_count: number;
  approved_count: number;
  denied_count: number;
  approval_rate: number;
  avg_days_to_decision: number | null;
  throughput_per_day: number;
  open_count: number;
  open_sla_breached_count: number;
  oldest_open_age_days: number | null;
  totals_by_currency: CurrencyTotals[];
  prior_authorizations: PriorAuthSummary;
  premiums: PremiumSummary;
}

export interface ApplicantDetails {
  full_name: string;
  date_of_birth: string;
  email: string;
  phone: string;
  address_line1: string;
  address_line2?: string | null;
  city: string;
  region: string;
  postal_code: string;
  country: string;
}

export interface ApplicationCreate {
  plan_id: string;
  applicant: ApplicantDetails;
  loyalty_points_to_redeem?: number;
  answers?: Record<string, unknown>;
}

export interface ApplicationRead {
  id: string;
  application_number: string;
  applicant_user_id: string;
  plan_id: string;
  status: string;
  submitted_at: string | null;
  decision_at: string | null;
  decline_reason: string | null;
  quoted_premium_cents: number | null;
  currency: string | null;
  loyalty_points_redeemed: number;
  answers: Record<string, unknown>;
  created_at: string;
}

export interface AppointmentCreate {
  slot_id: string;
  patient_user_id?: string | null;
  reason?: string | null;
  referral_id?: string | null;
  service_code?: string | null;
  channel?: EncounterChannel | null;
}

export interface AppointmentResponse {
  id: string;
  slot_id: string;
  patient_user_id: string;
  patient_name?: string | null;
  provider_user_id: string;
  provider_name?: string | null;
  organization_id: string;
  encounter_id: string | null;
  referral_id: string | null;
  reason: string | null;
  channel: EncounterChannel;
  status: AppointmentStatus;
  payment_status: string;
  invoice_id: string | null;
  cancellation_reason: string | null;
  start_at: string;
  end_at: string;
  booked_at: string;
  created_at: string;
  updated_at: string;
}

export type AppointmentStatus = "requested" | "pending-payment" | "confirmed" | "checked-in" | "fulfilled" | "cancelled" | "no-show";

export type AsserterType = "patient" | "practitioner" | "related-person";

/** One bookable opening, priced and attributed to a named provider. */
export interface AvailabilitySlot {
  slot_id: string;
  provider_user_id: string;
  provider_name: string;
  specialty: string | null;
  specialty_code: string | null;
  organization_id: string;
  organization_name: string;
  department_id: string | null;
  start_at: string;
  end_at: string;
  channel: EncounterChannel;
  capacity: number;
  booked_count: number;
  remaining: number;
  fee_cents: number | null;
  currency: string | null;
}

/** The full benefit grid for a plan. Rows omitted here are closed out. */
export interface BenefitGridPut {
  benefits: BenefitInput[];
  close_omitted_on?: string | null;
}

export interface BenefitGridResult {
  plan_id: string;
  created: number;
  updated: number;
  closed: number;
  benefits: BenefitResponse[];
}

export interface BenefitInput {
  service_category: string;
  covered: boolean;
  effective_from: string;
  service_code_system?: string | null;
  service_code?: string | null;
  service_display?: string | null;
  service_concept_id?: string | null;
  network_tier?: NetworkTier;
  copay_cents?: number | null;
  coinsurance_percent?: number | string | null;
  deductible_applies?: boolean;
  visit_limit_count?: number | null;
  limit_period?: BenefitLimitPeriod | null;
  prior_auth_required?: boolean;
  waiting_period_days?: number;
  exclusion_text?: string | null;
  effective_to?: string | null;
}

export type BenefitLimitPeriod = "per_year" | "per_visit" | "lifetime";

export interface BenefitPlainLanguage {
  explanation_id: string;
  locale: string;
  reading_level: string;
  summary_text: string;
  example_scenario: Record<string, unknown>;
  generated_by: string;
  model_version: string | null;
  reviewed_at: string | null;
}

export interface BenefitResponse {
  id: string;
  plan_id: string;
  service_category: string;
  service_code_system: string | null;
  service_code: string | null;
  service_display: string | null;
  service_concept_id: string | null;
  network_tier: NetworkTier;
  covered: boolean;
  copay_cents: number | null;
  coinsurance_percent: string | null;
  deductible_applies: boolean;
  visit_limit_count: number | null;
  limit_period: BenefitLimitPeriod | null;
  prior_auth_required: boolean;
  waiting_period_days: number;
  exclusion_text: string | null;
  effective_from: string;
  effective_to: string | null;
  explanation_count: number;
}

export interface BenefitRow {
  benefit_id: string;
  service_category: string;
  service_code_system: string | null;
  service_code: string | null;
  service_display: string | null;
  network_tier: string;
  covered: boolean;
  copay_cents: number | null;
  coinsurance_percent: string | null;
  deductible_applies: boolean;
  visit_limit_count: number | null;
  limit_period: string | null;
  prior_auth_required: boolean;
  waiting_period_days: number;
  exclusion_text: string | null;
  effective_from: string;
  effective_to: string | null;
  plain_language: BenefitPlainLanguage | null;
}

export type BiologicalSex = "male" | "female";

export interface BookingResponse {
  appointment: AppointmentResponse;
  invoice: InvoiceSummary;
}

export interface BreakGlassEntry {
  actor_user_id: string;
  actor_email: string;
  patient_user_id: string;
  event_count: number;
  resource_types: string[];
  first_access_at: string;
  last_access_at: string;
}

export interface CancelRequest {
  reason?: string | null;
}

export interface CareTeamMemberOut {
  id: string;
  member_user_id: string;
  member_name: string | null;
  member_specialty: string | null;
  organization_id: string | null;
  role_code: string;
  is_primary: boolean;
  period_start: string;
  period_end: string | null;
}

export interface CertificateIssueIn {
  issuer_organization_id?: string | null;
  document_asset_id?: string | null;
}

export interface CertificateOut {
  id: string;
  immunization_id: string;
  patient_user_id: string;
  certificate_number: string;
  issuer_organization_id: string;
  issued_at: string;
  verification_hash: string;
  qr_payload: string;
  signature_algorithm: string;
  status: CertificateStatus;
  revoked_at: string | null;
  revocation_reason: string | null;
  document_asset_id: string | null;
}

export type CertificateStatus = "active" | "revoked" | "superseded";

export interface ClaimActivity {
  claim_count: number;
  denied_count: number;
  denial_rate: number;
  charged_cents: number;
  paid_cents: number;
  by_status: CountBucket[];
}

export interface ClaimAssistance {
  phone: string;
  hours: string;
  languages: string[];
  what_to_have_ready: string[];
  source: "system_setting" | "default";
  your_policies: ClaimAssistancePolicy[];
  open_claim_count: number;
}

export interface ClaimAssistancePolicy {
  policy_id: string;
  policy_number: string;
  member_id: string;
  payer_name: string;
}

export interface ClaimCreate {
  policy_id: string;
  patient_user_id?: string | null;
  claim_type?: "professional" | "institutional" | "dental" | "pharmacy";
  billing_provider_organization_id: string;
  rendering_provider_user_id?: string | null;
  encounter_id?: string | null;
  service_from: string;
  service_to: string;
  lines: ClaimLineCreate[];
  submit?: boolean;
  note?: string | null;
}

export interface ClaimDenialStats {
  submitted_count: number;
  denied_count: number;
  denial_rate: number;
  denied_charge_cents: number;
  paid_cents: number;
}

export interface ClaimDetail {
  id: string;
  claim_number: string;
  policy_id: string;
  patient_user_id: string;
  subscriber_user_id: string;
  billing_provider_organization_id: string;
  rendering_provider_user_id: string | null;
  encounter_id: string | null;
  claim_type: string;
  status: string;
  service_from: string;
  service_to: string;
  total_charge_cents: number;
  allowed_cents: number | null;
  paid_cents: number | null;
  patient_responsibility_cents: number | null;
  currency: string;
  submitted_at: string | null;
  adjudicated_at: string | null;
  denial_reason_code: string | null;
  line_count: number;
  created_at: string;
  lines: ClaimLineRead[];
  events: ClaimEventRead[];
}

export interface ClaimDocumentAttach {
  document_asset_ids: string[];
  link_type?: "evidence" | "report" | "certificate" | "attachment" | "receipt";
}

export interface ClaimEventRead {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface ClaimLineCreate {
  service_date: string;
  service_code_system: string;
  service_code: string;
  service_display: string;
  modifiers?: string[];
  units?: number | string;
  charge_cents: number;
  diagnosis_pointers?: string[];
}

export interface ClaimLineRead {
  id: string;
  line_number: number;
  service_date: string;
  service_code_system: string;
  service_code: string;
  service_display: string;
  modifiers: string[];
  units: string;
  charge_cents: number;
  allowed_cents: number | null;
  paid_cents: number | null;
  copay_cents: number | null;
  coinsurance_cents: number | null;
  deductible_cents: number | null;
  diagnosis_pointers: string[];
  adjustment_reason_codes: string[];
}

export interface ClaimLineResponse {
  id: string;
  line_number: number;
  service_date: string;
  service_code_system: string;
  service_code: string;
  service_display: string;
  modifiers: string[];
  units: string;
  charge_cents: number;
  allowed_cents: number | null;
  paid_cents: number | null;
  copay_cents: number | null;
  coinsurance_cents: number | null;
  deductible_cents: number | null;
  diagnosis_pointers: string[];
  adjustment_reason_codes: string[];
}

export interface ClaimResponse {
  id: string;
  claim_number: string;
  policy_id: string;
  patient_user_id: string;
  subscriber_user_id: string;
  payer_organization_id: string;
  billing_provider_organization_id: string;
  rendering_provider_user_id: string | null;
  encounter_id: string | null;
  prior_authorization_id: string | null;
  claim_type: ClaimType;
  service_from: string;
  service_to: string;
  total_charge_cents: number;
  allowed_cents: number | null;
  paid_cents: number | null;
  patient_responsibility_cents: number | null;
  currency: string;
  status: ClaimStatus;
  submitted_at: string | null;
  adjudicated_at: string | null;
  denial_reason_code: string | null;
  line_count: number;
  sla_age_days: number;
  sla_breached: boolean;
  created_at: string;
}

export type ClaimStatus = "draft" | "submitted" | "accepted" | "pended" | "adjudicated" | "paid" | "denied" | "appealed";

export interface ClaimSummary {
  id: string;
  claim_number: string;
  policy_id: string;
  patient_user_id: string;
  subscriber_user_id: string;
  billing_provider_organization_id: string;
  rendering_provider_user_id: string | null;
  encounter_id: string | null;
  claim_type: string;
  status: string;
  service_from: string;
  service_to: string;
  total_charge_cents: number;
  allowed_cents: number | null;
  paid_cents: number | null;
  patient_responsibility_cents: number | null;
  currency: string;
  submitted_at: string | null;
  adjudicated_at: string | null;
  denial_reason_code: string | null;
  line_count: number;
  created_at: string;
}

export type ClaimType = "professional" | "institutional" | "dental" | "pharmacy";

export interface ClinicalNoteCreate {
  note_type_code: string;
  title: string;
  content: string;
  content_format?: "markdown" | "plain" | "fhir";
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
}

export interface ClinicalNoteOut {
  id: string;
  encounter_id: string;
  patient_user_id: string;
  author_user_id: string;
  note_type_code: string;
  title: string;
  content: string;
  content_format: string;
  status: NoteStatus;
  signed_at: string | null;
  signed_by_user_id: string | null;
  cosigner_user_id: string | null;
  cosigned_at: string | null;
  signature_hash: string | null;
  source: ProvenanceSource;
  source_document_id: string | null;
  extraction_confidence: number | null;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
  amendment_reason: string | null;
  recorded_at: string;
  created_at: string;
  updated_at: string;
  addenda: AddendumOut[];
  extraction: ExtractionSummary | null;
}

export type ClinicalStatus = "active" | "recurrence" | "relapse" | "inactive" | "remission" | "resolved";

export type CodeType = "diagnosis" | "procedure" | "hcpcs";

export type CommentVisibility = "internal" | "external";

export type ConditionCategory = "problem-list-item" | "encounter-diagnosis";

export interface ConditionCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  encounter_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  condition_code_system: string;
  condition_code: string;
  condition_display: string;
  condition_concept_id?: string | null;
  category?: ConditionCategory;
  clinical_status?: ClinicalStatus;
  verification_status?: VerificationStatus;
  severity_code_system?: string | null;
  severity_code?: string | null;
  severity_display?: string | null;
  body_site_code_system?: string | null;
  body_site_code?: string | null;
  body_site_display?: string | null;
  onset_date?: string | null;
  onset_precision?: "day" | "month" | "year" | null;
  abatement_date?: string | null;
  abatement_precision?: "day" | "month" | "year" | null;
  note?: string | null;
}

export interface ConditionOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  condition_code_system: string;
  condition_code: string;
  condition_display: string;
  category: ConditionCategory;
  clinical_status: ClinicalStatus;
  verification_status: VerificationStatus;
  severity_code: string | null;
  severity_display: string | null;
  body_site_code: string | null;
  body_site_display: string | null;
  onset_date: string | null;
  onset_precision: string | null;
  abatement_date: string | null;
  abatement_precision: string | null;
  note: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
}

export interface CostEstimateLine {
  service_code: string;
  service_display: string;
  units: number;
  network_tier: NetworkTier;
  billed_cents: number;
  contracted_rate_cents: number | null;
  allowed_cents: number;
  copay_cents: number;
  deductible_applied_cents: number;
  coinsurance_cents: number;
  member_liability_cents: number;
  plan_pays_cents: number;
  covered: boolean;
  prior_auth_required: boolean;
  benefit_source: "service_code" | "service_category" | "none" | "self_pay";
}

export interface CostEstimateLineInput {
  service_code: string;
  service_code_system?: string | null;
  service_display?: string | null;
  service_category?: string | null;
  units?: number;
  network_tier?: NetworkTier;
}

export interface CostEstimateRequest {
  patient_user_id: string;
  organization_id: string;
  bundle: CostEstimateLineInput[];
  policy_id?: string | null;
  service_item_id?: string | null;
  service_date?: string | null;
  currency?: string | null;
  valid_days?: number;
}

export interface CostEstimateResponse {
  id: string;
  patient_user_id: string;
  policy_id: string | null;
  organization_id: string;
  service_item_id: string | null;
  billed_cents: number;
  contracted_rate_cents: number | null;
  deductible_applied_cents: number;
  coinsurance_cents: number;
  copay_cents: number;
  member_liability_cents: number;
  plan_pays_cents: number;
  deductible_remaining_cents: number | null;
  currency: string;
  confidence: string | null;
  assumptions: Record<string, unknown>;
  expires_at: string;
  is_expired: boolean;
  lines: CostEstimateLine[];
  created_at: string;
}

export interface CountBucket {
  key: string;
  count: number;
}

export interface CoverageExplanation {
  policy: PolicySummary;
  patient_user_id: string;
  locale: string;
  reading_level: string;
  benefit_year: number;
  as_of: string;
  benefits: BenefitRow[];
  benefits_with_plain_language: number;
  benefits_without_plain_language: number;
  accumulators: AccumulatorRead[];
  deductible_consumed_cents: number;
  deductible_limit_cents: number | null;
  oop_consumed_cents: number;
  oop_limit_cents: number | null;
}

export interface CriticalResultOut {
  id: string;
  patient_user_id: string;
  lab_order_id?: string | null;
  order_number?: string | null;
  ordering_provider_user_id?: string | null;
  facility_id?: string | null;
  test_code_system: string;
  test_code: string;
  test_display: string;
  value_numeric?: string | null;
  value_string?: string | null;
  unit?: string | null;
  interpretation_code?: string | null;
  status: string;
  effective_at: string;
  critical_notified_at?: string | null;
  notified_user_id?: string | null;
  outstanding_hours: string;
}

export type Criticality = "low" | "high" | "unable-to-assess";

export interface CurrencyTotals {
  currency: string;
  charged_cents: number;
  allowed_cents: number;
  paid_cents: number;
}

export interface DataSubjectRequestCreate {
  subject_user_id: string;
  request_type: DsrType;
  due_at?: string | null;
  notes?: string | null;
}

export interface DataSubjectRequestFulfil {
  export_document_asset_id?: string | null;
  notes?: string | null;
}

export interface DataSubjectRequestOut {
  id: string;
  subject_user_id: string;
  request_type: DsrType;
  status: DsrStatus;
  received_at: string;
  due_at: string;
  verified_at: string | null;
  fulfilled_at: string | null;
  refusal_reason: string | null;
  handled_by_user_id: string | null;
  export_document_asset_id: string | null;
  notes: string | null;
  overdue: boolean;
  created_at: string;
  updated_at: string;
}

export interface DenyRequest {
  reason_code: string;
  reason_description?: string | null;
}

export interface DepartmentCreate {
  code: string;
  name: string;
  organization_id?: string | null;
  parent_department_id?: string | null;
  cost_center?: string | null;
  is_active?: boolean;
}

export interface DepartmentOut {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  parent_department_id: string | null;
  cost_center: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DepartmentUpdate {
  name?: string | null;
  parent_department_id?: string | null;
  cost_center?: string | null;
  is_active?: boolean | null;
}

export interface DiagnosisOut {
  id: string;
  encounter_id: string;
  condition_id: string | null;
  diagnosis_code_system: string;
  diagnosis_code: string;
  diagnosis_display: string;
  rank: number;
  is_principal: boolean;
  present_on_admission: string | null;
  recorded_at: string;
}

export interface DocumentLinkOut {
  id: string;
  document_asset_id: string;
  subject_type: string;
  subject_id: string;
  link_type: string;
  filename: string;
  content_type: string;
  byte_size: number;
  linked_by_user_id: string;
  created_at: string;
}

export interface DocumentLinkRead {
  id: string;
  document_asset_id: string;
  subject_type: string;
  subject_id: string;
  link_type: string;
  linked_by_user_id: string;
  filename: string;
  content_type: string;
  byte_size: number;
  created_at: string;
}

/** One dose line. A taper is two lines, never one line of free text. */
export interface DosageInstructionIn {
  sequence?: number;
  dose_quantity: number | string;
  dose_unit: string;
  route_code: string;
  frequency?: number;
  period?: number | string;
  period_unit?: "h" | "d" | "wk" | "mo";
  as_needed?: boolean;
  as_needed_reason?: string | null;
  max_dose_per_period?: number | string | null;
  is_chronic?: boolean;
  effective_start_at: string;
  effective_end_at?: string | null;
  sig_text: string;
}

export interface DosageInstructionOut {
  id: string;
  medication_request_id: string;
  sequence: number;
  dose_quantity: string;
  dose_unit: string;
  route_code: string;
  frequency: number;
  period: string;
  period_unit: string;
  as_needed: boolean;
  as_needed_reason: string | null;
  max_dose_per_period: string | null;
  is_chronic: boolean;
  effective_start_at: string;
  effective_end_at: string | null;
  sig_text: string;
}

export type DsrStatus = "received" | "verifying" | "in_progress" | "fulfilled" | "refused" | "withdrawn";

export type DsrType = "access" | "rectification" | "erasure" | "portability" | "restriction";

export interface EligibilityRequest {
  patient_user_id: string;
  service_date?: string | null;
  service_codes?: string[];
  policy_id?: string | null;
  member_id?: string | null;
  payer_organization_id?: string | null;
  cache_ttl_minutes?: number;
  force_refresh?: boolean;
}

export interface EligibilityResponse {
  id: string;
  patient_user_id: string;
  policy_id: string | null;
  payer_organization_id: string;
  member_id: string;
  service_date: string;
  service_codes: string[];
  status: EligibilityStatus;
  coverage_found: boolean;
  active_from: string | null;
  active_to: string | null;
  benefits_returned: Record<string, unknown>;
  transaction_id: string | null;
  cached_until: string | null;
  from_cache: boolean;
  created_at: string;
}

export type EligibilityStatus = "pending" | "active" | "inactive" | "error";

export type EncounterChannel = "in_person" | "telehealth";

export type EncounterClass = "AMB" | "IMP" | "EMER" | "VR" | "HH";

export interface EncounterCodeCreate {
  billing_code_system: string;
  billing_code: string;
  billing_display: string;
  code_type: CodeType;
  billing_concept_id?: string | null;
  rank?: number | null;
  modifiers?: string[];
  units?: number;
  source?: ProvenanceSource;
  confidence?: number | null;
  review_status?: ReviewStatus;
}

export interface EncounterCodeOut {
  id: string;
  encounter_id: string;
  patient_user_id: string;
  billing_code_system: string;
  billing_code: string;
  billing_display: string;
  billing_concept_id: string | null;
  code_type: CodeType;
  rank: number;
  modifiers: string[];
  units: number;
  coder_user_id: string | null;
  source: ProvenanceSource;
  confidence: number | null;
  review_status: ReviewStatus;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EncounterCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  organization_id: string;
  department_id?: string | null;
  appointment_id?: string | null;
  primary_practitioner_user_id?: string | null;
  class_code: EncounterClass;
  status?: EncounterStatus;
  started_at: string;
  ended_at?: string | null;
  location?: string | null;
  reason_text?: string | null;
  disposition?: string | null;
}

export interface EncounterOut {
  id: string;
  patient_user_id: string;
  primary_practitioner_user_id: string | null;
  organization_id: string;
  department_id: string | null;
  appointment_id: string | null;
  class_code: EncounterClass;
  status: EncounterStatus;
  started_at: string;
  ended_at: string | null;
  location: string | null;
  reason_text: string | null;
  disposition: string | null;
  source: ProvenanceSource;
  recorded_at: string;
}

export type EncounterStatus = "planned" | "arrived" | "in-progress" | "finished" | "cancelled" | "entered-in-error";

export interface ExplanationInput {
  plan_benefit_id: string;
  summary_text: string;
  generated_by: string;
  locale?: string;
  reading_level?: string;
  example_scenario?: Record<string, unknown>;
  source_document_asset_id?: string | null;
  model_version?: string | null;
  mark_reviewed?: boolean;
}

export interface ExplanationPut {
  explanations: ExplanationInput[];
}

export interface ExplanationPutResult {
  plan_id: string;
  created: number;
  updated: number;
  items: ExplanationResponse[];
}

export interface ExplanationResponse {
  id: string;
  plan_benefit_id: string;
  locale: string;
  reading_level: string;
  summary_text: string;
  example_scenario: Record<string, unknown>;
  source_document_asset_id: string | null;
  generated_by: string;
  model_version: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  updated_at: string;
}

export interface ExtractionSummary {
  id: string;
  document_asset_id: string;
  extraction_schema: string;
  schema_version: string;
  overall_confidence: number | null;
  validation_status: ReviewStatus;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
}

export interface FamilyHistoryOut {
  id: string;
  relationship_code: string;
  condition_code_system: string;
  condition_code: string;
  condition_display: string;
  onset_age_years: number | null;
  deceased: boolean;
  note: string | null;
  recorded_at: string;
}

export interface GenerateOccurrencesRequest {
  horizon_hours?: number;
}

export interface GenerationResult {
  schedule_id: string;
  status: MedicationScheduleStatus;
  created: number;
  skipped: number;
  cancelled: number;
  generated_through: string | null;
  doses_generated: number;
  total_doses: number | null;
  window_end: string;
  course_complete: boolean;
}

export interface GrowthCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  encounter_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  measured_at: string;
  age_days: number;
  height_cm?: number | string | null;
  weight_kg?: number | string | null;
  head_circumference_cm?: number | string | null;
  bmi?: number | string | null;
}

export type GrowthMeasure = "height_for_age" | "weight_for_age" | "bmi_for_age" | "hc_for_age" | "weight_for_height";

export interface GrowthOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  measured_at: string;
  age_days: number;
  height_cm: string | null;
  weight_kg: string | null;
  head_circumference_cm: string | null;
  bmi: string | null;
  height_percentile: string | null;
  weight_percentile: string | null;
  bmi_percentile: string | null;
  height_zscore: string | null;
  weight_zscore: string | null;
  bmi_zscore: string | null;
  standard_id: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
}

export interface GrowthPercentilePoint {
  measurement_id: string;
  measured_at: string;
  age_days: number;
  scores: Record<string, GrowthScore | null>;
}

export interface GrowthPercentileSeries {
  patient_user_id: string;
  sex: BiologicalSex | null;
  source: GrowthSource;
  points: GrowthPercentilePoint[];
}

/** LMS scoring for one measure at one point, or ``None`` where uncovered. */
export interface GrowthScore {
  measure: GrowthMeasure;
  value: string;
  standard_id: string;
  l: string;
  m: string;
  s: string;
  zscore: number;
  percentile: number;
}

export type GrowthSource = "WHO" | "CDC";

export interface ImmunizationCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  encounter_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  vaccine_code_system: string;
  vaccine_code: string;
  vaccine_display: string;
  vaccine_concept_id?: string | null;
  manufacturer_code_system?: string | null;
  manufacturer_code?: string | null;
  manufacturer_display?: string | null;
  status?: ImmunizationStatus;
  status_reason_code?: string | null;
  administered_date: string;
  administered_precision?: "day" | "month" | "year";
  administered_at?: string | null;
  lot_number?: string | null;
  expiration_date?: string | null;
  site_code_system?: string | null;
  site_code?: string | null;
  site_display?: string | null;
  route_code_system?: string | null;
  route_code?: string | null;
  route_display?: string | null;
  dose_quantity?: number | string | null;
  dose_unit?: string | null;
  series_name?: string | null;
  series_dose_number?: number | null;
  series_doses_expected?: number | null;
  funding_source?: string | null;
  administered_by_user_id?: string | null;
  organization_id?: string | null;
  next_due_at?: string | null;
  booster_of_immunization_id?: string | null;
}

export interface ImmunizationDueItem {
  immunization_id: string;
  vaccine_code: string;
  vaccine_display: string;
  series_name: string | null;
  series_dose_number: number | null;
  series_doses_expected: number | null;
  last_administered_date: string;
  next_due_at: string;
  days_until_due: number;
}

export interface ImmunizationDueOut {
  as_of: string;
  horizon_days: number;
  overdue: ImmunizationDueItem[];
  upcoming: ImmunizationDueItem[];
}

export interface ImmunizationOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  vaccine_code_system: string;
  vaccine_code: string;
  vaccine_display: string;
  manufacturer_display: string | null;
  status: ImmunizationStatus;
  status_reason_code: string | null;
  administered_date: string;
  administered_precision: string;
  administered_at: string | null;
  lot_number: string | null;
  expiration_date: string | null;
  site_display: string | null;
  route_display: string | null;
  dose_quantity: string | null;
  dose_unit: string | null;
  series_name: string | null;
  series_dose_number: number | null;
  series_doses_expected: number | null;
  funding_source: string | null;
  administered_by_user_id: string | null;
  organization_id: string | null;
  next_due_at: string | null;
  booster_of_immunization_id: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
}

export type ImmunizationStatus = "completed" | "not-done" | "entered-in-error";

export interface ImmunizationSummary {
  total: number;
  completed: number;
  not_done: number;
  latest_administered_date: string | null;
  overdue: number;
  upcoming: number;
  next_due_at: string | null;
}

/** A check submitted alongside the prescription it belongs to.

``medication_request_id`` cannot be supplied yet, so the drug is named by
its position in :attr:`PrescriptionCreate.requests`. */
export interface InlineSafetyCheckIn {
  check_type: SafetyCheckType;
  severity: "none" | "low" | "moderate" | "high" | "contraindicated";
  outcome: SafetyCheckOutcome;
  message: string;
  triggered_by_code_system?: string | null;
  triggered_by_code?: string | null;
  override_reason?: string | null;
  payload?: Record<string, unknown>;
  medication_index?: number | null;
}

export interface InvoiceDetailOut {
  invoice: OperationsInvoiceOut;
  lines: OperationsInvoiceLineOut[];
  payments: PaymentOut[];
  refunds: RefundOut[];
  documents: DocumentLinkOut[];
}

export type InvoiceStatus = "draft" | "issued" | "paid" | "void" | "refunded";

export interface InvoiceSummary {
  id: string;
  invoice_number: string;
  status: InvoiceStatus;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  balance_cents: number;
  currency: string;
  issued_at: string | null;
  due_at: string | null;
}

export interface LabFacilityOut {
  id: string;
  organization_id: string;
  name: string;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  timezone: string;
  home_collection_available: boolean;
  is_active: boolean;
}

export interface LabOrderCreate {
  patient_user_id?: string | null;
  facility_id: string;
  slot_id?: string | null;
  test_ids: string[];
  priority?: "routine" | "urgent" | "stat";
  ordering_provider_user_id?: string | null;
  encounter_id?: string | null;
  note?: string | null;
}

export interface LabOrderDetail {
  id: string;
  patient_user_id: string;
  ordering_provider_user_id?: string | null;
  encounter_id?: string | null;
  facility_id: string;
  slot_id?: string | null;
  order_number: string;
  priority: string;
  status: string;
  invoice_id?: string | null;
  requested_at: string;
  collected_at?: string | null;
  note?: string | null;
  test_count: number;
  tests?: LabOrderTestOut[];
  specimens?: SpecimenOut[];
  results?: LabResultOut[];
  invoice?: LabInvoiceOut | null;
}

export interface LabOrderOut {
  id: string;
  patient_user_id: string;
  ordering_provider_user_id?: string | null;
  encounter_id?: string | null;
  facility_id: string;
  slot_id?: string | null;
  order_number: string;
  priority: string;
  status: string;
  invoice_id?: string | null;
  requested_at: string;
  collected_at?: string | null;
  note?: string | null;
  test_count: number;
}

export interface LabOrderTestOut {
  id: string;
  lab_test_id: string;
  test_code_system: string;
  test_code: string;
  test_display: string;
  name: string;
  status: string;
  price_cents?: number | null;
  currency?: string | null;
}

/** One observation. Mirrors the ``lab_result_single_value`` DB constraint. */
export interface LabResultEntry {
  lab_test_id?: string | null;
  specimen_id?: string | null;
  test_code_system?: string | null;
  test_code?: string | null;
  test_display?: string | null;
  status?: "registered" | "preliminary" | "final" | "amended" | "corrected" | "cancelled";
  value_numeric?: number | string | null;
  value_string?: string | null;
  value_code_system?: string | null;
  value_code?: string | null;
  value_display?: string | null;
  value_boolean?: boolean | null;
  value_comparator?: "<" | "<=" | ">" | ">=" | null;
  unit?: string | null;
  data_absent_reason?: string | null;
  reference_range_low?: number | string | null;
  reference_range_high?: number | string | null;
  reference_range_text?: string | null;
  critical_low?: number | string | null;
  critical_high?: number | string | null;
  effective_at?: string | null;
  issued_at?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
}

export interface LabResultOut {
  id: string;
  lab_order_id?: string | null;
  lab_test_id?: string | null;
  specimen_id?: string | null;
  patient_user_id: string;
  test_code_system: string;
  test_code: string;
  test_display: string;
  status: string;
  value_numeric?: string | null;
  value_string?: string | null;
  value_code_system?: string | null;
  value_code?: string | null;
  value_display?: string | null;
  value_boolean?: boolean | null;
  value_comparator?: string | null;
  unit?: string | null;
  data_absent_reason?: string | null;
  interpretation_code?: string | null;
  reference_range_low?: string | null;
  reference_range_high?: string | null;
  reference_range_text?: string | null;
  is_critical: boolean;
  critical_notified_at?: string | null;
  acknowledged_by_user_id?: string | null;
  acknowledged_at?: string | null;
  acknowledgement_note?: string | null;
  effective_at: string;
  issued_at?: string | null;
  version: number;
  supersedes_id?: string | null;
  superseded_at?: string | null;
  amendment_reason?: string | null;
}

export interface LabResultsCreate {
  results: LabResultEntry[];
}

/** A single orderable entry in the test catalogue. */
export interface LabTestOut {
  id: string;
  test_code_system: string;
  test_code: string;
  test_display: string;
  name: string;
  panel_code_system?: string | null;
  panel_code?: string | null;
  panel_display?: string | null;
  specimen_type_code_system?: string | null;
  specimen_type_code?: string | null;
  specimen_type_display?: string | null;
  container?: string | null;
  prep_instructions?: string | null;
  fasting_required: boolean;
  turnaround_hours?: number | null;
  price_cents?: number | null;
  currency?: string | null;
  department_id?: string | null;
  is_active: boolean;
}

export interface LoyaltyBalance {
  account_id: string | null;
  program: string;
  balance_points: number;
  lifetime_points: number;
  tier: string | null;
  status: string;
  history: Page<LoyaltyLedgerRead>;
}

export interface LoyaltyLedgerRead {
  id: string;
  entry_type: string;
  points: number;
  balance_after: number;
  reason: string;
  reference_type: string;
  reference_id: string;
  expires_at: string | null;
  occurred_at: string;
}

export interface MarketplacePlan {
  plan: PlanSummary;
  recommendation_id: string;
  rank: number;
  score: string;
  history_score: string;
  loyalty_score: string;
  loyalty_points_applied: number;
  estimated_annual_cost_cents: number;
  reason_codes: string[];
  reasons: RecommendationReason[];
  benefit_count: number;
  covered_benefit_count: number;
}

export interface MarketplaceResponse {
  patient_user_id: string;
  model_version: string;
  generated_at: string;
  sort: "recommended" | "premium_asc" | "deductible_asc";
  features: PatientRiskFeatures;
  candidates_scored: number;
  plans: Page<MarketplacePlan>;
}

/** One drug on a script. RxNorm dispensable terms only, never an ingredient. */
export interface MedicationRequestIn {
  medication_code_system: string;
  medication_code: string;
  medication_display: string;
  medication_concept_id?: string | null;
  medication_term_type: "SCD" | "SBD" | "GPCK" | "BPCK";
  ndc_code?: string | null;
  intent?: MedicationRequestIntent;
  indication_condition_id?: string | null;
  substitution_allowed?: boolean;
  quantity?: number | string | null;
  quantity_unit?: string | null;
  days_supply?: number | null;
  refills_allowed?: number;
  controlled_substance_schedule?: "CI" | "CII" | "CIII" | "CIV" | "CV" | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  dosage_instructions: DosageInstructionIn[];
}

export type MedicationRequestIntent = "proposal" | "plan" | "order" | "original-order" | "instance-order";

export interface MedicationRequestOut {
  id: string;
  prescription_id: string;
  patient_user_id: string;
  encounter_id: string | null;
  medication_code_system: string;
  medication_code: string;
  medication_display: string;
  medication_term_type: string;
  ndc_code: string | null;
  status: MedicationRequestStatus;
  intent: MedicationRequestIntent;
  substitution_allowed: boolean;
  quantity: string | null;
  quantity_unit: string | null;
  days_supply: number | null;
  refills_allowed: number;
  refills_remaining: number;
  controlled_substance_schedule: string | null;
  stopped_at: string | null;
  stop_reason: string | null;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
  recorded_at: string;
  dispensed_fills?: number;
  last_dispensed_at?: string | null;
  dosage_instructions?: DosageInstructionOut[];
}

export type MedicationRequestStatus = "draft" | "active" | "on-hold" | "stopped" | "completed" | "cancelled" | "entered-in-error";

export type MedicationScheduleStatus = "active" | "paused" | "completed" | "cancelled";

export interface MedicationStatementOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  medication_code_system: string;
  medication_code: string;
  medication_display: string;
  medication_term_type: string | null;
  status: MedicationStatementStatus;
  sig_text: string | null;
  effective_start_at: string | null;
  effective_end_at: string | null;
  note: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
}

export type MedicationStatementStatus = "active" | "completed" | "not-taken" | "intended" | "stopped" | "entered-in-error";

export type NetworkTier = "in_network" | "out_of_network";

export interface NoteSignRequest {
  cosigner_user_id?: string | null;
}

export type NoteStatus = "draft" | "preliminary" | "final" | "amended" | "entered-in-error";

export type NotificationChannel = "in_app" | "email" | "sms" | "push";

export type ObservationStatus = "registered" | "preliminary" | "final" | "amended" | "corrected" | "cancelled" | "entered-in-error";

export interface OrderCancel {
  reason?: string | null;
}

export interface PatientIdentifierOut {
  id: string;
  system: string;
  value: string;
  type_code: string;
  assigner_organization_id: string | null;
  period_start: string | null;
  period_end: string | null;
  is_active: boolean;
}

export interface PatientResultTrend {
  patient_user_id: string;
  series?: ResultSeries[];
}

/** The medical-history parameters the ranking model consumes. */
export interface PatientRiskFeatures {
  patient_user_id: string;
  age_years: number | null;
  active_condition_count: number;
  chronic_condition_count: number;
  active_allergy_count: number;
  recent_claim_count: number;
  recent_claim_charge_cents: number;
  loyalty_balance_points: number;
}

/** The first screen a clinician opens: one request, no follow-ups. */
export interface PatientSummary {
  patient_user_id: string;
  patient_display_id: string;
  full_name: string;
  date_of_birth: string | null;
  sex_at_birth: string | null;
  blood_type: string | null;
  identifiers: PatientIdentifierOut[];
  active_conditions: ConditionOut[];
  active_allergies: AllergyOut[];
  allergy_status: AllergyStatusOut;
  latest_vitals: VitalOut[];
  immunizations: ImmunizationSummary;
  care_team: CareTeamMemberOut[];
  family_history: FamilyHistoryOut[];
  generated_at: string;
}

export interface PayerSummary {
  organization_id: string;
  slug: string;
  legal_name: string;
  organization_type: string;
}

export type PaymentMethod = "card" | "wallet" | "bank" | "cash" | "loyalty";

export interface PaymentOut {
  id: string;
  invoice_id: string;
  payer_user_id: string;
  method: PaymentMethod;
  amount_cents: number;
  currency: string;
  status: PaymentStatus;
  processor: string;
  processor_intent_id: string | null;
  processor_charge_id: string | null;
  authorized_at: string | null;
  captured_at: string | null;
  failure_code: string | null;
  created_at: string;
}

export interface PaymentResponse {
  id: string;
  invoice_id: string;
  appointment_id: string | null;
  payer_user_id: string;
  method: PaymentMethod;
  amount_cents: number;
  currency: string;
  status: PaymentStatus;
  processor: string;
  processor_intent_id: string | null;
  idempotency_key: string;
  authorized_at: string | null;
  captured_at: string | null;
  appointment_payment_status: string;
  invoice: InvoiceSummary;
}

export interface PaymentResult {
  payment: PaymentOut;
  invoice: OperationsInvoiceOut;
  replayed: boolean;
}

export type PaymentStatus = "requires_action" | "authorized" | "captured" | "failed" | "refunded";

export type PhiAccessAction = "read" | "export" | "print" | "search";

export interface PhiAccessOut {
  id: string;
  tenant_id: string;
  actor_user_id: string;
  actor_email: string;
  actor_account_type: AccountType;
  patient_user_id: string;
  resource_type: string;
  resource_id: string | null;
  action: PhiAccessAction;
  purpose_of_use: string;
  consent_grant_id: string | null;
  request_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  result_count: number | null;
  created_at: string;
}

export interface PlanCreate {
  product_id: string;
  plan_code: string;
  name: string;
  premium_cents: number;
  currency: string;
  effective_from: string;
  effective_to?: string | null;
  metal_tier?: string | null;
  individual_deductible_cents?: number | null;
  family_deductible_cents?: number | null;
  individual_oop_max_cents?: number | null;
  family_oop_max_cents?: number | null;
  term_months?: number;
  eligibility_rules?: Record<string, unknown>;
  is_active?: boolean;
}

export interface PlanDetail {
  plan: PlanSummary;
  as_of: string;
  locale: string;
  reading_level: string;
  benefits: BenefitRow[];
}

export interface PlanResponse {
  id: string;
  product_id: string;
  product_code: string;
  product_name: string;
  plan_code: string;
  name: string;
  metal_tier: string | null;
  premium_cents: number;
  currency: string;
  individual_deductible_cents: number | null;
  family_deductible_cents: number | null;
  individual_oop_max_cents: number | null;
  family_oop_max_cents: number | null;
  term_months: number;
  eligibility_rules: Record<string, unknown>;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  benefit_count: number;
  created_at: string;
  updated_at: string;
}

export interface PlanSummary {
  id: string;
  plan_code: string;
  name: string;
  metal_tier: string | null;
  product_id: string;
  product_code: string;
  product_name: string;
  product_type: string;
  network_name: string | null;
  premium_cents: number;
  currency: string;
  individual_deductible_cents: number | null;
  family_deductible_cents: number | null;
  individual_oop_max_cents: number | null;
  family_oop_max_cents: number | null;
  term_months: number;
  effective_from: string;
  effective_to: string | null;
  payer: PayerSummary;
}

export interface PlanUpdate {
  name?: string | null;
  premium_cents?: number | null;
  currency?: string | null;
  metal_tier?: string | null;
  individual_deductible_cents?: number | null;
  family_deductible_cents?: number | null;
  individual_oop_max_cents?: number | null;
  family_oop_max_cents?: number | null;
  term_months?: number | null;
  eligibility_rules?: Record<string, unknown> | null;
  effective_to?: string | null;
  is_active?: boolean | null;
}

export interface PlatformAnalytics {
  window_from: string;
  window_to: string;
  roles: RoleActivity[];
  encounter_count: number;
  encounters_by_status: CountBucket[];
  appointment_count: number;
  appointments_by_status: CountBucket[];
  no_show_rate: number;
  claims: ClaimActivity;
  open_support_cases: number;
  breached_support_cases: number;
  phi_access_events: number;
  break_glass_events: number;
}

export interface PolicyMemberRead {
  id: string;
  patient_user_id: string;
  relationship: string;
  member_suffix: string | null;
  effective_from: string;
  effective_to: string | null;
}

export interface PolicySummary {
  id: string;
  policy_number: string;
  member_id: string;
  status: string;
  effective_from: string;
  effective_to: string | null;
  premium_cents: number;
  currency: string;
  premium_frequency: string;
  subscriber_user_id: string;
  member_relationship: string | null;
  purchased_via_application_id: string | null;
  plan: PlanSummary;
}

export interface PractitionerRoleCreate {
  practitioner_user_id: string;
  role_code: string;
  organization_id?: string | null;
  department_id?: string | null;
  specialty_code?: string | null;
  taxonomy_code?: string | null;
  privileges?: string[];
  credentialing_status?: "pending" | "active" | "suspended" | "expired" | "revoked";
  credentialed_at?: string | null;
  credential_expires_at?: string | null;
  accepts_new_patients?: boolean;
  is_active?: boolean;
}

export interface PractitionerRoleOut {
  id: string;
  practitioner_user_id: string;
  practitioner_name: string;
  license_number: string;
  organization_id: string;
  department_id: string | null;
  role_code: string;
  specialty_code: string | null;
  taxonomy_code: string | null;
  privileges: string[];
  credentialing_status: string;
  credentialed_at: string | null;
  credential_expires_at: string | null;
  days_until_expiry: number | null;
  accepts_new_patients: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PractitionerRoleUpdate {
  department_id?: string | null;
  specialty_code?: string | null;
  taxonomy_code?: string | null;
  privileges?: string[] | null;
  credentialing_status?: "pending" | "active" | "suspended" | "expired" | "revoked" | null;
  credentialed_at?: string | null;
  credential_expires_at?: string | null;
  accepts_new_patients?: boolean | null;
  is_active?: boolean | null;
}

export interface PremiumInstalment {
  id: string;
  due_date: string;
  amount_cents: number;
  currency: string;
  status: string;
}

export interface PremiumSummary {
  due_count: number;
  due_cents: number;
  paid_count: number;
  paid_cents: number;
  overdue_count: number;
  overdue_cents: number;
}

export interface PrescriptionCreate {
  prescriber_user_id: string;
  encounter_id?: string | null;
  prescription_number?: string | null;
  written_at?: string | null;
  dosing_weight_kg?: number | string | null;
  dosing_weight_observed_at?: string | null;
  note?: string | null;
  source?: ProvenanceSource;
  source_document_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  requests: MedicationRequestIn[];
  safety_checks?: InlineSafetyCheckIn[];
}

export interface PrescriptionOut {
  id: string;
  tenant_id: string;
  patient_user_id: string;
  prescriber_user_id: string;
  encounter_id: string | null;
  prescription_number: string;
  status: PrescriptionStatus;
  written_at: string;
  dosing_weight_kg: string | null;
  dosing_weight_observed_at: string | null;
  note: string | null;
  source: ProvenanceSource;
  recorded_by_user_id: string;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
  amendment_reason: string | null;
  requests?: MedicationRequestOut[];
  safety_checks?: SafetyCheckOut[];
}

export type PrescriptionStatus = "draft" | "active" | "completed" | "cancelled" | "entered_in_error";

export interface PriorAuthCreate {
  policy_id: string;
  patient_user_id: string;
  requesting_provider_user_id: string;
  service_codes: string[];
  diagnosis_codes?: string[];
  units_requested?: number | null;
  clinical_justification?: string | null;
  criteria_met?: Record<string, unknown>;
  submit?: boolean;
  document_asset_ids?: string[];
}

export interface PriorAuthDecision {
  decision: "approved" | "partially_approved" | "denied" | "pended";
  reason?: string | null;
  units_approved?: number | null;
  valid_from?: string | null;
  valid_to?: string | null;
  authorization_number?: string | null;
  reviewer_user_id?: string | null;
}

export interface PriorAuthResponse {
  id: string;
  policy_id: string;
  patient_user_id: string;
  requesting_provider_user_id: string;
  service_codes: string[];
  diagnosis_codes: string[];
  units_requested: number | null;
  units_approved: number | null;
  clinical_justification: string | null;
  criteria_met: Record<string, unknown>;
  status: PriorAuthStatus;
  reviewer_user_id: string | null;
  decision_at: string | null;
  decision_reason: string | null;
  authorization_number: string | null;
  valid_from: string | null;
  valid_to: string | null;
  evidence_document_count: number;
  created_at: string;
  updated_at: string;
}

export type PriorAuthStatus = "draft" | "submitted" | "pended" | "approved" | "partially_approved" | "denied" | "appealed" | "expired";

export interface PriorAuthSummary {
  total: number;
  approved: number;
  partially_approved: number;
  denied: number;
  pending: number;
  approval_rate: number;
  avg_days_to_decision: number | null;
}

export interface ProductCreate {
  code: string;
  name: string;
  product_type: "hmo" | "ppo" | "epo" | "pos" | "indemnity";
  payer_organization_id?: string | null;
  network_name?: string | null;
  filing_id?: string | null;
  regulator_approval_id?: string | null;
  is_active?: boolean;
}

export interface ProductResponse {
  id: string;
  payer_organization_id: string;
  code: string;
  name: string;
  product_type: string;
  network_name: string | null;
  filing_id: string | null;
  regulator_approval_id: string | null;
  is_active: boolean;
  plan_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProductUpdate {
  name?: string | null;
  product_type?: "hmo" | "ppo" | "epo" | "pos" | "indemnity" | null;
  network_name?: string | null;
  filing_id?: string | null;
  regulator_approval_id?: string | null;
  is_active?: boolean | null;
}

export type ProvenanceSource = "patient-reported" | "practitioner" | "device" | "imported" | "ai-extracted";

export interface ProviderScheduleCreate {
  provider_user_id: string;
  organization_id?: string | null;
  department_id?: string | null;
  /** 0=Monday .. 6=Sunday */
  day_of_week: number;
  start_time: string;
  end_time: string;
  slot_minutes?: number;
  timezone: string;
  channel?: EncounterChannel;
  valid_from: string;
  valid_to?: string | null;
  is_active?: boolean;
}

export interface ProviderScheduleResponse {
  id: string;
  provider_user_id: string;
  provider_name?: string | null;
  organization_id: string;
  department_id: string | null;
  day_of_week: number;
  start_time: string;
  end_time: string;
  slot_minutes: number;
  timezone: string;
  channel: EncounterChannel;
  valid_from: string;
  valid_to: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PurchaseMember {
  patient_user_id: string;
  relationship: "spouse" | "child" | "other";
}

export interface PurchaseRequest {
  effective_from?: string | null;
  premium_frequency?: "monthly" | "quarterly" | "annual";
  members?: PurchaseMember[];
}

export interface PurchaseResult {
  policy: PolicySummary;
  members: PolicyMemberRead[];
  premium_schedule: PremiumInstalment[];
  loyalty_entries: LoyaltyLedgerRead[];
  loyalty_balance_points: number;
  application: ApplicationRead;
  already_issued: boolean;
}

export type ReactionSeverity = "mild" | "moderate" | "severe";

export interface RecommendationReason {
  code: string;
  detail: string;
}

export interface ReferralCreate {
  patient_user_id: string;
  specialty_code: string;
  reason: string;
  urgency?: "routine" | "urgent" | "emergent";
  referring_provider_user_id?: string | null;
  referring_organization_id?: string | null;
  receiving_provider_user_id?: string | null;
  receiving_organization_id?: string | null;
  encounter_id?: string | null;
  expires_at?: string | null;
  send?: boolean;
}

export interface ReferralOut {
  id: string;
  patient_user_id: string;
  referring_provider_user_id: string;
  referring_organization_id: string;
  receiving_provider_user_id: string | null;
  receiving_organization_id: string | null;
  encounter_id: string | null;
  specialty_code: string;
  urgency: string;
  reason: string;
  status: ReferralStatus;
  prior_authorization_id: string | null;
  appointment_id: string | null;
  expires_at: string | null;
  feedback_note: string | null;
  created_at: string;
  updated_at: string;
}

export type ReferralStatus = "draft" | "sent" | "accepted" | "declined" | "scheduled" | "completed" | "expired";

export interface ReferralStatusChange {
  status: ReferralStatus;
  reason?: string | null;
  receiving_provider_user_id?: string | null;
  receiving_organization_id?: string | null;
  appointment_id?: string | null;
}

export interface RefundCreate {
  amount_cents: number;
  reason: string;
  processor_refund_id?: string | null;
}

export interface RefundOut {
  id: string;
  payment_id: string;
  amount_cents: number;
  currency: string;
  reason: string;
  status: RefundStatus;
  processor_refund_id: string | null;
  refunded_at: string | null;
  created_at: string;
}

export interface RefundResult {
  refund: RefundOut;
  payment: PaymentOut;
  invoice: OperationsInvoiceOut;
}

export type RefundStatus = "pending" | "succeeded" | "failed";

export interface ReminderAck {
  action: "taken" | "skipped" | "snoozed";
  taken_at?: string | null;
  dose_taken_quantity?: number | string | null;
  dose_unit?: string | null;
  reason_code?: string | null;
  note?: string | null;
  snooze_minutes?: number;
}

export interface ReminderOut {
  id: string;
  schedule_id: string;
  patient_user_id: string;
  medication_request_id: string;
  scheduled_at: string;
  time_local: string;
  timezone: string;
  status: ReminderStatus;
  channel: NotificationChannel;
  sent_at: string | null;
  attempts: number;
  medication_code: string;
  medication_display: string;
  dose_quantity: string;
  dose_unit: string;
  route_code: string;
  sig_text: string;
}

export type ReminderStatus = "pending" | "sent" | "failed" | "cancelled" | "suppressed";

export interface RescheduleRequest {
  slot_id: string;
  reason?: string | null;
}

export interface ResultAcknowledge {
  note?: string | null;
}

export interface ResultSeries {
  test_code_system: string;
  test_code: string;
  test_display: string;
  unit?: string | null;
  point_count: number;
  points?: TrendPoint[];
}

export interface RevenueCycleSummary {
  window_from: string;
  window_to: string;
  currency: string | null;
  billed_cents: number;
  collected_cents: number;
  refunded_cents: number;
  outstanding_cents: number;
  collection_rate: number;
  invoice_count: number;
  aging: AgingBucket[];
  invoices_by_status: StatusBucket[];
  claims: ClaimDenialStats;
}

export type ReviewStatus = "pending" | "accepted" | "rejected";

export interface RoleActivity {
  account_type: AccountType;
  total_users: number;
  active_users: number;
  signed_in_users: number;
}

export interface SafetyCheckBatch {
  checks: SafetyCheckIn[];
}

export interface SafetyCheckIn {
  check_type: SafetyCheckType;
  severity: "none" | "low" | "moderate" | "high" | "contraindicated";
  outcome: SafetyCheckOutcome;
  message: string;
  triggered_by_code_system?: string | null;
  triggered_by_code?: string | null;
  override_reason?: string | null;
  payload?: Record<string, unknown>;
  medication_request_id?: string | null;
}

export interface SafetyCheckOut {
  id: string;
  prescription_id: string;
  medication_request_id: string | null;
  patient_user_id: string;
  check_type: SafetyCheckType;
  severity: string;
  triggered_by_code_system: string | null;
  triggered_by_code: string | null;
  message: string;
  outcome: SafetyCheckOutcome;
  overridden_by_user_id: string | null;
  override_reason: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export type SafetyCheckOutcome = "no_alert" | "alerted" | "overridden";

export type SafetyCheckType = "drug_allergy" | "drug_drug" | "duplicate_therapy" | "dose_range" | "drug_condition";

/** The recurrence rule the reminder generator walks forward. */
export interface ScheduleCreate {
  dosage_instruction_id?: string | null;
  times_local: string[];
  timezone: string;
  days_of_week?: Array<"mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun">;
  starts_on?: string | null;
  ends_on?: string | null;
  is_chronic?: boolean;
  total_doses?: number | null;
  channels?: NotificationChannel[];
}

export interface ScheduleOut {
  id: string;
  tenant_id: string;
  patient_user_id: string;
  prescription_id: string;
  medication_request_id: string;
  dosage_instruction_id: string;
  time_local: string;
  timezone: string;
  days_of_week: string[];
  starts_on: string;
  ends_on: string | null;
  is_chronic: boolean;
  total_doses: number | null;
  doses_generated: number;
  generated_through: string | null;
  status: MedicationScheduleStatus;
  channels: string[];
}

export interface ServiceItemCreate {
  service_code_system: string;
  service_code: string;
  service_display: string;
  description: string;
  base_price_cents: number;
  currency: string;
  effective_from: string;
  organization_id?: string | null;
  department_id?: string | null;
  service_concept_id?: string | null;
  cpt_code?: string | null;
  revenue_code?: string | null;
  effective_to?: string | null;
  is_active?: boolean;
}

export interface ServiceItemOut {
  id: string;
  organization_id: string;
  department_id: string | null;
  service_code_system: string;
  service_code: string;
  service_display: string;
  description: string;
  cpt_code: string | null;
  revenue_code: string | null;
  base_price_cents: number;
  currency: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  contracted_payer_count: number;
  best_allowed_cents: number | null;
  created_at: string;
  updated_at: string;
}

export interface ServiceItemUpdate {
  service_display?: string | null;
  description?: string | null;
  base_price_cents?: number | null;
  department_id?: string | null;
  cpt_code?: string | null;
  revenue_code?: string | null;
  effective_to?: string | null;
  is_active?: boolean | null;
}

/** An open slot that offers every requested test, with the tighter of the
facility-level and per-test remaining capacities. */
export interface SlotAvailabilityOut {
  slot_id: string;
  facility_id: string;
  facility_name: string;
  start_at: string;
  end_at: string;
  capacity: number;
  booked_count: number;
  slot_remaining: number;
  test_remaining: number;
  remaining: number;
  offered_test_ids: string[];
  matched_test_count: number;
  total_price_cents: number;
  currency?: string | null;
}

export interface SlotGenerationRequest {
  from_date: string;
  to_date: string;
  capacity?: number;
  price_cents?: number | null;
  currency?: string | null;
}

export interface SlotGenerationResult {
  schedule_id: string;
  from_date: string;
  to_date: string;
  created: number;
  skipped: number;
  slot_ids: string[];
}

export interface SpecimenCreate {
  accession_number?: string | null;
  specimen_type_code_system?: string | null;
  specimen_type_code?: string | null;
  specimen_type_display?: string | null;
  collected_at?: string | null;
  collected_by_user_id?: string | null;
  condition?: string | null;
  received_at?: string | null;
  rejected_reason?: string | null;
}

export interface SpecimenOut {
  id: string;
  lab_order_id: string;
  patient_user_id: string;
  accession_number: string;
  specimen_type_code_system: string;
  specimen_type_code: string;
  specimen_type_display: string;
  collected_at: string;
  collected_by_user_id?: string | null;
  condition?: string | null;
  received_at?: string | null;
  rejected_reason?: string | null;
}

export interface StatusBucket {
  key: string;
  count: number;
  amount_cents: number;
}

/** Payload for the state-machine transition endpoints. */
export interface StatusChange {
  status: string;
  reason?: string | null;
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface SupportCaseCreate {
  subject: string;
  description: string;
  category: string;
  severity?: SupportSeverity;
  queue?: string;
  requester_user_id?: string | null;
  assignee_user_id?: string | null;
  related_record_type?: string | null;
  related_record_id?: string | null;
}

export interface SupportCaseOut {
  id: string;
  case_number: string;
  subject: string;
  description: string;
  category: string;
  severity: SupportSeverity;
  status: SupportStatus;
  queue: string;
  requester_user_id: string;
  assignee_user_id: string | null;
  sla_due_at: string;
  sla_breached: boolean;
  first_response_at: string | null;
  resolved_at: string | null;
  escalated_at: string | null;
  escalation_level: number;
  related_record_type: string | null;
  related_record_id: string | null;
  comment_count: number;
  created_at: string;
  updated_at: string;
}

export interface SupportCaseResult {
  case: SupportCaseOut;
  event: SupportEventOut;
}

export interface SupportCommentCreate {
  body: string;
  visibility?: CommentVisibility;
}

export interface SupportCommentOut {
  id: string;
  case_id: string;
  author_user_id: string;
  body: string;
  visibility: CommentVisibility;
  created_at: string;
}

export interface SupportEscalateRequest {
  reason: string;
  severity?: SupportSeverity | null;
  assignee_user_id?: string | null;
}

export interface SupportEventOut {
  id: string;
  case_id: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string;
  reason: string | null;
  occurred_at: string;
}

export type SupportSeverity = "sev1" | "sev2" | "sev3" | "sev4";

export type SupportStatus = "new" | "triaged" | "in_progress" | "waiting_customer" | "escalated" | "resolved" | "closed";

export interface SupportTransitionRequest {
  status: SupportStatus;
  reason?: string | null;
  assignee_user_id?: string | null;
}

export interface TelehealthCreate {
  recording_consent?: boolean;
  licensure_state?: string | null;
}

/** Join details. ``join_token`` is returned once; only its hash is stored. */
export interface TelehealthSessionResponse {
  id: string;
  appointment_id: string;
  encounter_id: string | null;
  provider_room_id: string;
  join_token: string;
  join_url: string;
  started_at: string | null;
  ended_at: string | null;
  participants: Record<string, unknown>[];
  recording_consent: boolean;
  licensure_state: string | null;
  licensure_verified: boolean;
}

/** One visit, with everything a clinician scans for before opening it. */
export interface TimelineEntry {
  encounter: EncounterOut;
  practitioner_name: string | null;
  practitioner_specialty: string | null;
  diagnoses: DiagnosisOut[];
  note_count: number;
  prescription_count: number;
  result_count: number;
}

export interface TrendPoint {
  result_id: string;
  effective_at: string;
  value_numeric?: string | null;
  value_string?: string | null;
  value_comparator?: string | null;
  unit?: string | null;
  interpretation_code?: string | null;
  is_critical: boolean;
  reference_range_low?: string | null;
  reference_range_high?: string | null;
  status: string;
}

export type VerificationStatus = "unconfirmed" | "provisional" | "differential" | "confirmed" | "refuted" | "entered-in-error";

export interface VitalComponentCreate {
  observation_code_system: string;
  observation_code: string;
  observation_display: string;
  observation_concept_id?: string | null;
  value_numeric?: number | string | null;
  value_string?: string | null;
  unit?: "mm[Hg]" | "kg" | "cm" | "Cel" | "/min" | "%" | "kg/m2" | "[degF]" | "L/min" | null;
  interpretation_code?: "N" | "A" | "AA" | "H" | "HH" | "L" | "LL" | "R" | "S" | "I" | null;
  reference_range_low?: number | string | null;
  reference_range_high?: number | string | null;
  sequence?: number;
}

export interface VitalComponentOut {
  id: string;
  observation_code_system: string;
  observation_code: string;
  observation_display: string;
  value_numeric: string | null;
  value_string: string | null;
  unit: string | null;
  interpretation_code: string | null;
  reference_range_low: string | null;
  reference_range_high: string | null;
  sequence: number;
}

/** One observation. Panel members (systolic/diastolic) ride in ``components``. */
export interface VitalCreate {
  source?: ProvenanceSource;
  source_document_id?: string | null;
  extraction_confidence?: number | string | null;
  asserter_user_id?: string | null;
  human_verified?: boolean;
  encounter_id?: string | null;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  observation_code_system: string;
  observation_code: string;
  observation_display: string;
  observation_concept_id?: string | null;
  status?: ObservationStatus;
  value_numeric?: number | string | null;
  value_string?: string | null;
  value_code_system?: string | null;
  value_code?: string | null;
  value_display?: string | null;
  value_boolean?: boolean | null;
  value_comparator?: "<" | "<=" | ">" | ">=" | null;
  unit?: "mm[Hg]" | "kg" | "cm" | "Cel" | "/min" | "%" | "kg/m2" | "[degF]" | "L/min" | null;
  data_absent_reason?: string | null;
  interpretation_code?: "N" | "A" | "AA" | "H" | "HH" | "L" | "LL" | "R" | "S" | "I" | null;
  reference_range_low?: number | string | null;
  reference_range_high?: number | string | null;
  reference_range_text?: string | null;
  body_site_code?: string | null;
  method_code?: string | null;
  device?: string | null;
  performer_user_id?: string | null;
  note?: string | null;
  effective_at: string;
  issued_at?: string | null;
  components?: VitalComponentCreate[];
}

export interface VitalOut {
  id: string;
  patient_user_id: string;
  encounter_id: string | null;
  observation_code_system: string;
  observation_code: string;
  observation_display: string;
  status: ObservationStatus;
  value_numeric: string | null;
  value_string: string | null;
  value_code: string | null;
  value_display: string | null;
  value_boolean: boolean | null;
  value_comparator: string | null;
  unit: string | null;
  data_absent_reason: string | null;
  interpretation_code: string | null;
  reference_range_low: string | null;
  reference_range_high: string | null;
  reference_range_text: string | null;
  body_site_code: string | null;
  method_code: string | null;
  device: string | null;
  note: string | null;
  effective_at: string;
  issued_at: string | null;
  source: ProvenanceSource;
  recorded_at: string;
  version: number;
  supersedes_id: string | null;
  superseded_at: string | null;
  components: VitalComponentOut[];
}

export interface LabInvoiceLineOut {
  id: string;
  line_number: number;
  description: string;
  service_code_system?: string | null;
  service_code?: string | null;
  quantity: string;
  unit_price_cents: number;
  amount_cents: number;
}

export interface LabInvoiceOut {
  id: string;
  invoice_number: string;
  status: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  balance_cents: number;
  currency: string;
  issued_at?: string | null;
  due_at?: string | null;
  lines?: LabInvoiceLineOut[];
}

export interface OperationsInvoiceLineOut {
  id: string;
  line_number: number;
  service_item_id: string | null;
  service_code: string | null;
  service_display: string | null;
  description: string;
  quantity: number;
  unit_price_cents: number;
  amount_cents: number;
}

export interface OperationsInvoiceOut {
  id: string;
  invoice_number: string;
  organization_id: string;
  payer_user_id: string;
  patient_user_id: string | null;
  appointment_id: string | null;
  lab_order_id: string | null;
  policy_id: string | null;
  status: InvoiceStatus;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  balance_cents: number;
  paid_cents: number;
  refunded_cents: number;
  currency: string;
  issued_at: string | null;
  due_at: string | null;
  days_outstanding: number | null;
  created_at: string;
  updated_at: string;
}

export interface OperationsPaymentCreate {
  method: PaymentMethod;
  amount_cents: number;
  currency: string;
  idempotency_key: string;
  processor?: string;
  processor_intent_id?: string | null;
  processor_charge_id?: string | null;
}

export interface SchedulingPaymentCreate {
  method?: PaymentMethod;
  amount_cents?: number | null;
  processor?: string;
  processor_intent_id?: string | null;
  processor_charge_id?: string | null;
  capture?: boolean;
  idempotency_key?: string | null;
}
