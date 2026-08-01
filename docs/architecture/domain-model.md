# Clinical and insurance domain model

Migration `0009_clinical_insurance_domain` adds 79 normalized tables covering the patient
lifelong record, scheduling, medications, labs, and the full insurance lifecycle.

It is **purely additive**. Nothing pre-existing was dropped, renamed, or altered — the generic
`portal_records` envelope and everything built on it keeps working unchanged, so the two models
coexist during migration.

## Why this exists

Before `0009` the platform had 29 tables and **zero clinical or financial domain tables**. Every
requirement in the problem statement was satisfied — where satisfied at all — by rows in a single
generic table:

```python
class PortalRecord(TimestampMixin, Base):
    category: Mapped[str] = mapped_column(String(64))   # "vitals" | "claims" | "appointments" | ...
    data: Mapped[dict[str, Any]] = mapped_column(JSON)  # everything else
```

That shape cannot express the domain:

| Consequence | Concrete failure |
|---|---|
| No foreign keys between domain objects | An appointment referenced its slot via `data["slot_id"]`, a string. Nothing stopped it pointing at a deleted slot. |
| No typed columns or range checks | A blood pressure of `-40` was storable. |
| No uniqueness guarantees | Double-booking was prevented only by a row lock, with no unique index behind it. |
| No queryable history | "Show this patient's weight trend" meant extracting JSON in Python. |
| No aggregation | Every dashboard number required loading rows and summing them in the application. |

## Design rules

These are the rules the schema is built on. Breaking one is a bug, not a style preference.

**1. Corrections never mutate.** Clinical rows are immutable once written. A correction inserts a
new row, sets the old row's `superseded_at`, and points the new row's `supersedes_id` at it. The
"current" view is `WHERE superseded_at IS NULL`, backed by partial indexes.

**2. Append-only tables are enforced in the database, not in the application.** A
`BEFORE UPDATE OR DELETE` trigger raises on `claim_events`, `appointment_status_events`,
`medication_adherence_events`, `loyalty_ledger`, `phi_access_events`, and
`prescription_safety_checks`. Signed `clinical_notes` are immutable the moment `signed_at` is set;
the only legal amendment is a row in `clinical_note_addenda`.

**3. Terminology is bound by triple, not by foreign key.** Coded columns carry
`(system, code, display)` plus a *nullable* FK to `code_concepts`. A required FK would make
externally-sourced codes unstorable, because no deployment can load all of SNOMED and RxNorm.

**4. Money is integer cents.** `*_cents Integer` plus a NOT NULL 3-letter `currency` with an
ISO-4217 check. No floats anywhere in the financial path.

**5. Patient FKs target `patient_profiles.user_id`, not `users.id`.** This makes "the patient is
actually a patient" a schema invariant at zero cost, since both are primary keys.

**6. `tenant_id` carries no foreign key.** It is an indexed bare UUID because it holds *either* an
organization id *or*, for solo accounts, a user id — the fallback in `core.security`. A FK would
break every patient write. See the scoping section below, which this directly causes.

## Access scoping — three different rules

This is the subtlety most likely to cause a bug, so it is worth stating plainly. There are three
scoping rules and using the wrong one silently returns either nothing or too much.

| Rule | Helper | Applies to | Behaviour |
|---|---|---|---|
| **Tenant** | `tenant_scoped()` | Operational tables you own: invoices, provider schedules, service catalog, support cases | Admin sees all; everyone else sees their own tenant |
| **Consent** | `consent_scoped_patients()` + `apply_patient_scope()` | Longitudinal clinical data: conditions, allergies, vitals, immunizations, results | The patient themselves, plus any clinician holding an active unrevoked consent grant |
| **Discovery** | `discovery_scoped()` / `discovery_predicate()` | Catalogs, marketplace, availability search | Patients **and** admins search across every tenant; organizations stay scoped to capacity they own |

**Why clinical data is not tenant scoped.** A tenant filter would hide a patient's own history the
moment they are treated at a second organization. Longitudinal records must follow the patient, so
they are gated by consent instead.

**Why discovery is not tenant scoped.** A patient's `tenant_id` is their own user id, so a tenant
filter on a catalog matches nothing — the patient sees an empty lab catalog and zero available
appointments, and can never book anything. This was a real defect caught by end-to-end testing:
`GET /labs/tests` returned 0 rows against 32 seeded tests until the rule was corrected. Discovery
is inherently cross-tenant, because the brief requires booking "with any doctor" and insurance
options "aggregated from all participating aggregators".

## PHI access logging

`audit_events` records **writes** only and has no `tenant_id`. HIPAA §164.528 disclosure
accounting needs a record of **reads**, so `phi_access_events` is a separate append-only log.

Every endpoint that returns patient data writes one row per patient touched, in the same
transaction as the read, via `record_phi_access()` / `record_phi_access_many()`. The
`purpose_of_use` column is constrained to HL7 v3 codes, and a partial index on
`purpose_of_use = 'ETREAT'` gives an emergency-access (break-glass) register for free.

## Race conditions the schema prevents

Two resources can be contended by concurrent users. Both are defended in depth, with the database
as the final authority rather than the application.

**Appointment double-booking** — three layers:

1. `SELECT ... FOR UPDATE` on the slot row serialises concurrent bookers,
2. `booked_count < capacity` is re-checked while holding the lock,
3. `ix_appointment_slot_booked`, a **partial unique index** on `slot_id` restricted to live
   statuses, is the database's last word:

```sql
CREATE UNIQUE INDEX ix_appointment_slot_booked ON appointments (slot_id)
  WHERE status IN ('confirmed', 'checked-in', 'fulfilled');
```

The partial predicate matters: a cancelled appointment must not block rebooking the slot.

**Loyalty balance drift** — the ledger is append-only, `balance_after` carries a non-negative
check, entry signs are constrained by type, and
`UNIQUE (account_id, reference_type, reference_id, entry_type)` makes accrual idempotent, so a
retried purchase cannot award points twice.

These are verified behaviourally, not just declared. Against the live database:

```
PASS: append-only blocks UPDATE
PASS: append-only blocks DELETE
PASS: negative balance rejected
PASS: positive-points redemption rejected
PASS: duplicate accrual for same reference rejected
```

## Table groups

| Group | Tables |
|---|---|
| Terminology & identity | `code_systems`, `code_concepts`, `patient_identifiers`, `practitioner_identifiers`, `patient_communication_preferences`, `growth_reference_standards` |
| Organization | `departments`, `practitioner_roles`, `service_items`, `payer_contract_rates` |
| Scheduling | `provider_schedules`, `appointment_slots`, `appointments`, `appointment_status_events`, `encounters`, `telehealth_sessions` |
| Clinical core | `conditions`, `encounter_diagnoses`, `allergy_intolerances`, `allergy_reactions`, `patient_allergy_status`, `vital_signs`, `vital_sign_components`, `growth_measurements`, `immunizations`, `immunization_certificates`, `clinical_notes`, `clinical_note_addenda`, `encounter_codes`, `referrals`, `care_team_members`, `family_history` |
| Medications | `prescriptions`, `medication_requests`, `medication_dosage_instructions`, `medication_schedules`, `medication_reminder_occurrences`, `medication_adherence_events`, `medication_dispenses`, `medication_statements`, `prescription_safety_checks` |
| Labs | `lab_facilities`, `lab_tests`, `lab_slots`, `lab_slot_tests`, `lab_orders`, `lab_order_tests`, `specimens`, `lab_results` |
| Money & insurance | `invoices`, `invoice_lines`, `payments`, `refunds`, `loyalty_accounts`, `loyalty_ledger`, `insurance_products`, `insurance_plans`, `plan_benefits`, `benefit_explanations`, `plan_recommendations`, `policy_applications`, `policies`, `policy_members`, `premium_schedules`, `beneficiaries`, `benefit_accumulators`, `eligibility_checks`, `prior_authorizations`, `claims`, `claim_lines`, `claim_events`, `cost_estimates` |
| Documents & compliance | `document_links`, `document_extractions`, `phi_access_events`, `data_subject_requests`, `support_cases`, `support_case_comments`, `support_case_events` |

## Modelling notes worth knowing

**Vitals use a parent/component split.** A blood pressure is one `vital_signs` row with two
`vital_sign_components`. A second scalar column would have worked for BP alone and broken on any
three-component panel.

**Prescriptions are four levels deep**: `prescriptions` → `medication_requests` →
`medication_dosage_instructions` → `medication_schedules`. A flat row cannot express a taper or a
multi-drug script.

**Medication courses terminate by construction.** `medication_schedules` carries
`generated_through`, `doses_generated`, and `total_doses`; occurrences are materialized forward in
a bounded horizon and the schedule flips to `completed` when `ends_on` passes or the dose count is
reached. `ends_on` may only be null when `is_chronic` is true, enforced by a check constraint.
This is what makes the brief's "daily reminders that continue until the medication course is
complete" actually stop.

**Growth percentiles are computed from real WHO LMS data**, not approximated:

```
z = ((value / M)^L − 1) / (L × S)      when L ≠ 0
z = ln(value / M) / S                   when L = 0
```

Verified: a 12-month-old boy at the WHO median weight (9.6479 kg) scores z = 0.0, 50th percentile.

## Deliberately deferred

Left to a later migration, all additive and blocked by nothing: beds/equipment/rosters, 837/835
claim batches and AR aging, fraud scoring, care plans, a FHIR resource store, and PHI field-level
encryption with Postgres row-level security. Each is real work; none is needed for the journeys in
the brief.

## Applying it

```bash
export DATABASE_URL='postgresql+asyncpg://healthos:<password>@localhost:55432/healthos'
uv run alembic -c services/api/alembic.ini upgrade head
```

`downgrade` reverses cleanly: seeds → triggers → functions → deferred FKs → indexes → tables, in
exact reverse order.
