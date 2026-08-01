# Application portals and integration architecture

## Portal model

HealthOS exposes one authenticated application shell with role-specific navigation and server-side authorization. Hiding a navigation item is never treated as authorization; every API operation verifies the current PostgreSQL-backed session, permission, account type, tenant scope, and resource scope.

| Account type | Workspaces                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------- |
| Patient      | Medical history, vaccinations, appointments, labs, insurance, claims, payments, notifications, reminders, documents |
| Doctor       | Schedule, patients, prescriptions, documentation, labs, appointments, AI assistant, documents                       |
| Hospital     | Staff, departments, beds, billing, reports, appointments, documents                                                 |
| Insurance    | Policies, eligibility, claims, prior authorization, fraud detection, documents                                      |
| Admin        | Analytics, audit logs, user management, monitoring, system settings, documents                                      |

Operational resources use a stable `portal_records` envelope with typed category, status, ownership, patient/assignee references, dates, monetary fields, external references, and a bounded JSON payload. This supports evolving FHIR and payer payloads without losing queryable ownership and workflow state. Documents, notifications, settings, and integration events use dedicated tables because their retention and access patterns differ.

## Runtime application definitions

`application_definitions` stores immutable versions of modules, forms, dashboards, workflows,
and content. Definitions use JSON Schema plus an allowlisted declarative rule vocabulary; they
cannot contain executable administrator code. The authenticated manifest selects published,
effective definitions for the active tenant, role, and locale, with tenant definitions overriding
global defaults. Workflow instances retain their exact definition version and use optimistic
locking for transitions. Every transition produces an audit event and an outbox event.

Organizations are durable tenant boundaries. Primary active membership selects the request
tenant; users without an organization retain owner isolation. Typed patient consent grants cover
user or organization grantees, purpose, scopes, expiry, revocation, and provenance. Legacy
consent records remain readable only as a compatibility path during migration.

## Integrations

- **OCR:** UTF-8 text and text-bearing PDFs are processed locally. Images and scanned PDFs use the configured authenticated OCR endpoint. The source file, SHA-256 digest, extraction status, text, and provider metadata are retained.
- **FHIR:** The adapter calls the R4-style `Patient/{id}/$everything` operation with `application/fhir+json`, maps supported resources into authorized portal categories, and records import counts without logging payload bodies.
- **Insurance:** A configurable payer adapter performs eligibility, claim, policy, and prior-authorization operations. Imported records retain external references and raw structured response data.
- **Payments:** The gateway creates idempotent Stripe PaymentIntents when configured and uses a non-chargeable local adapter in development. Signed, timestamp-bounded webhooks synchronize payment status.
- **Notifications:** In-app delivery is native. SMTP and outbound webhook channels are optional and record delivery state.
- **Documents:** Files are size-bounded, content-addressed, tenant-scoped, downloadable with safe headers, and audit logged on access or deletion.
- **AI:** The doctor assistant and insurance fraud workflow call the separately scalable HealthOS AI runtime. Outputs remain decision support and cannot make autonomous clinical or coverage determinations.

## Production configuration

Integration credentials belong in a secrets manager and are injected as environment variables. Base URLs and feature configuration may live in ConfigMaps. Blank endpoints deliberately activate safe local or `configuration_required` behavior; no production request silently calls an unknown vendor.

Required migration order is API `0001` through `0003`, followed independently by the AI migration history. The application and worker deployments should only roll out after both migration jobs succeed.
