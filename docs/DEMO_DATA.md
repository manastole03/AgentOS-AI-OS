# Synthetic demo database

HealthOS includes an idempotent demo seeder that populates the PostgreSQL database with a
connected, synthetic healthcare and insurance journey. No row represents a real person,
provider, facility, or insurer.

## Create the database and start the demo

From the repository root:

```bash
cp .env.example .env
make demo
```

`make demo` builds the containers, creates the PostgreSQL database and pgvector extension,
runs both Alembic migration histories, inserts the demo data, and starts the full stack.
PostgreSQL and Redis bind only to loopback on ports `55432` and `56379` by default so they do
not collide with common host installations; both ports can be overridden in `.env`.

To refresh the deterministic sample rows without recreating the database:

```bash
make seed-demo
```

The seeder can be run repeatedly. It updates the same deterministic demo records and does not
duplicate them. Existing non-demo records are left intact.

## Demo accounts

All accounts use the password `Demo@HealthOS2026!` unless `HEALTHOS_DEMO_PASSWORD` is set for
the seed command.

| Role | Email | Entry route |
| --- | --- | --- |
| Patient | `patient.demo@healthos.example.com` | `http://localhost:3000/patient/login` |
| Doctor | `doctor.demo@healthos.example.com` | `http://localhost:3000/doctors/login` |
| Hospital | `hospital.demo@healthos.example.com` | `http://localhost:3000/hospital/login` |
| Insurance | `insurance.demo@healthos.example.com` | `http://localhost:3000/insurance/login` |
| Admin | `admin.demo@healthos.example.com` | `http://localhost:3000/admin/login` |

The patient is Maya Patel and her permanent HealthOS ID is `PATDEMO00000001` (15 characters).

## What is populated

The seed contains 5 users and 60 role-scoped portal records. Every module exposed by
`PORTAL_MODULES` has at least one sample record:

| Workspace | Module records | Example linked data |
| --- | ---: | --- |
| Patient | 21 | Lifelong history, vitals/BMI/CO₂, allergy, vaccination certificate, visit, medication reminders, bookings, active policy, marketplace selection, loyalty points, claim, cost estimate, payment, consent, and AI request |
| Doctor | 12 | Credentialed provider, future bookable slot, patient panel, prescription, signed note, reviewed coding suggestions, referral, care plan, telemedicine, and AI draft requiring review |
| Hospital | 12 | Staff, department, bed, operating room, service catalog, future lab slot, billing, revenue cycle, eligibility, and operational report |
| Insurance | 7 | Marketplace policy, eligibility, claim, prior authorization, cost estimate, fraud review, and indexed coverage document |
| Admin | 8 | Analytics, audit verification, user review queue, monitoring, settings, escalation, support ticket, and compliance evidence |

Dedicated tables are populated as well:

| Database table | Sample entry |
| --- | --- |
| `users`, `patient_profiles`, `doctor_profiles`, `organization_profiles` | Active, verified identities with role-specific registration fields |
| `roles`, `permissions`, `user_roles`, `role_permissions` | Complete RBAC policy installed by migrations |
| `oauth_identities` | Linked Google identity example |
| `otp_challenges` | Consumed email verification challenge; only a hash is stored |
| `auth_sessions` | Revoked/expired sample session; only a token hash is stored |
| `portal_records` | 60 typed records spanning every role module |
| `document_assets` | Content-addressed vaccination certificate with OCR and FHIR metadata |
| `portal_notifications` | One role-appropriate notification per demo account |
| `integration_events` | FHIR, payer, OCR, and notification adapter events |
| `system_settings` | Claim helpline, human-review policy, and synthetic demo flag |
| `audit_events` | Append-only, database-sealed events linked by hashes |
| `ai_agent_runs` | Completed knee-care request coordinated across patient and insurance agents |
| `ai_agent_messages` | Encrypted patient-to-insurance agent handoff |
| `ai_knowledge_documents`, `ai_knowledge_chunks` | PPO benefit summary with a pgvector embedding |
| `ai_long_term_memories` | Consented appointment preference with a pgvector embedding |
| `ai_agent_audit_events` | Append-only, database-sealed AI run event |

## Inspect sample rows

```bash
docker compose exec postgres psql -U healthos -d healthos -c \
  "SELECT account_type, email, status FROM users WHERE email LIKE '%.demo@healthos.example.com';"

docker compose exec postgres psql -U healthos -d healthos -c \
  "SELECT u.account_type, count(*), count(DISTINCT r.category) AS modules
   FROM portal_records r JOIN users u ON u.id = r.owner_user_id
   WHERE u.email LIKE '%.demo@healthos.example.com'
   GROUP BY u.account_type ORDER BY u.account_type;"

docker compose exec postgres psql -U healthos -d healthos -c \
  "SELECT category, title, status, data
   FROM portal_records
   WHERE patient_user_id = (
     SELECT id FROM users WHERE email = 'patient.demo@healthos.example.com'
   ) ORDER BY category;"
```

The demo records intentionally illustrate workflow behavior; they are not medical advice,
coverage determinations, production credentials, or a substitute for validation against real
systems of record.
