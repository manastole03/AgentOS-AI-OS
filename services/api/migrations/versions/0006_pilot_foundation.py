"""Add multi-tenant, dynamic application, consent, and workflow foundations.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("organization_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    op.create_index("ix_organizations_organization_type", "organizations", ["organization_type"])
    op.create_index("ix_organizations_status", "organizations", ["status"])

    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="[]"),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_membership"),
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_membership_user_status", "organization_memberships", ["user_id", "status"])

    # Existing hospital and insurance accounts become their own organization tenant.
    op.execute(
        """
        INSERT INTO organizations (id, slug, legal_name, organization_type, status)
        SELECT op.user_id,
               lower(regexp_replace(op.registration_number, '[^A-Za-z0-9]+', '-', 'g')),
               op.legal_name, op.account_type, 'active'
        FROM organization_profiles op
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO organization_memberships
          (id, organization_id, user_id, role, status, is_primary, permissions)
        SELECT gen_random_uuid(), o.id, o.id, 'owner', 'active', true, '["*"]'::jsonb
        FROM organizations o
        ON CONFLICT (organization_id, user_id) DO NOTHING
        """
    )

    op.create_table(
        "consent_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grantee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "grantee_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        ),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
        sa.CheckConstraint(
            "grantee_user_id IS NOT NULL OR grantee_organization_id IS NOT NULL",
            name="consent_has_grantee",
        ),
    )
    op.create_index("ix_consent_grants_patient_user_id", "consent_grants", ["patient_user_id"])
    op.create_index("ix_consent_grants_grantee_user_id", "consent_grants", ["grantee_user_id"])
    op.create_index(
        "ix_consent_grants_grantee_organization_id", "consent_grants", ["grantee_organization_id"]
    )
    op.create_index("ix_consent_patient_status", "consent_grants", ["patient_user_id", "status"])
    op.create_index(
        "ix_consent_grantee_scope", "consent_grants", ["grantee_user_id", "grantee_organization_id"]
    )
    op.execute(
        """
        INSERT INTO consent_grants
          (id, patient_user_id, grantee_user_id, purpose, scopes, status, expires_at, provenance)
        SELECT id, patient_user_id, assigned_user_id,
               COALESCE(NULLIF(data->>'purpose', ''), 'treatment'),
               CASE WHEN jsonb_typeof(data->'scopes') = 'array' THEN data->'scopes'
                    ELSE to_jsonb(string_to_array(COALESCE(data->>'scopes', ''), ',')) END,
               status, due_at,
               jsonb_build_object('migrated_from', 'portal_records', 'record_id', id)
        FROM portal_records
        WHERE category = 'consents' AND patient_user_id IS NOT NULL AND assigned_user_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    op.create_table(
        "application_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("account_types", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("locale", sa.String(16), nullable=False, server_default="en-US"),
        sa.Column("schema", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("presentation", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application_definitions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        *timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "kind", "key", "version", name="uq_application_definition_version"
        ),
        sa.CheckConstraint(
            "kind IN ('module','form','dashboard','workflow','content')",
            name="application_definition_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft','review','published','retired')",
            name="application_definition_status",
        ),
    )
    op.create_index(
        "ix_application_definitions_tenant_id", "application_definitions", ["tenant_id"]
    )
    op.create_index("ix_application_definitions_kind", "application_definitions", ["kind"])
    op.create_index("ix_application_definitions_key", "application_definitions", ["key"])
    op.create_index("ix_application_definitions_status", "application_definitions", ["status"])
    op.create_index(
        "ix_application_definitions_effective_at", "application_definitions", ["effective_at"]
    )
    op.create_index(
        "ix_definition_lookup", "application_definitions", ["tenant_id", "kind", "key", "status"]
    )

    modules = {
        "patient": [
            "medical_history",
            "vitals",
            "allergies",
            "vaccinations",
            "visits",
            "medications",
            "appointments",
            "telemedicine",
            "lab_reports",
            "lab_bookings",
            "insurance",
            "buy_insurance",
            "loyalty_points",
            "claims",
            "cost_estimates",
            "payments",
            "notifications",
            "health_reminders",
            "consents",
            "documents",
            "ai_assistant",
        ],
        "doctor": [
            "schedule",
            "patients",
            "prescriptions",
            "documentation",
            "medical_coding",
            "referrals",
            "care_coordination",
            "telemedicine",
            "lab_reports",
            "appointments",
            "ai_assistant",
            "documents",
        ],
        "hospital": [
            "staff",
            "departments",
            "beds",
            "resources",
            "service_catalog",
            "lab_slots",
            "billing",
            "revenue_cycle",
            "eligibility",
            "reports",
            "appointments",
            "documents",
        ],
        "insurance": [
            "policies",
            "eligibility",
            "claims",
            "prior_authorization",
            "cost_estimates",
            "fraud_detection",
            "documents",
        ],
        "admin": [
            "analytics",
            "audit_logs",
            "user_management",
            "monitoring",
            "system_settings",
            "escalations",
            "support",
            "documents",
        ],
    }
    bind = op.get_bind()
    all_keys = sorted({key for keys in modules.values() for key in keys})
    for position, key in enumerate(all_keys):
        roles = [role for role, keys in modules.items() if key in keys]
        bind.execute(
            sa.text(
                """INSERT INTO application_definitions
                   (id, kind, key, version, status, account_types, locale, schema,
                    presentation, rules, effective_at, published_at)
                   VALUES (gen_random_uuid(), 'module', :key, 1, 'published',
                           CAST(:roles AS jsonb), 'en-US', '{}'::jsonb,
                           CAST(:presentation AS jsonb), '[]'::jsonb, now(), now())"""
            ),
            {
                "key": key,
                "roles": __import__("json").dumps(roles),
                "presentation": __import__("json").dumps(
                    {
                        "label": key.replace("_", " ").title(),
                        "description": f"Manage {key.replace('_', ' ')}",
                        "position": position,
                    }
                ),
            },
        )

    op.create_table(
        "workflow_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("definition_key", sa.String(100), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    op.create_index("ix_workflow_instances_tenant_id", "workflow_instances", ["tenant_id"])
    op.create_index("ix_workflow_instances_subject_id", "workflow_instances", ["subject_id"])
    op.create_index("ix_workflow_instances_status", "workflow_instances", ["status"])
    op.create_index(
        "ix_workflow_scope", "workflow_instances", ["tenant_id", "definition_key", "status"]
    )

    op.create_table(
        "workflow_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "workflow_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("assigned_role", sa.String(64)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    op.create_index("ix_workflow_tasks_tenant_id", "workflow_tasks", ["tenant_id"])
    op.create_index(
        "ix_workflow_tasks_workflow_instance_id", "workflow_tasks", ["workflow_instance_id"]
    )
    op.create_index("ix_workflow_tasks_status", "workflow_tasks", ["status"])
    op.create_index("ix_workflow_tasks_due_at", "workflow_tasks", ["due_at"])
    op.create_index("ix_workflow_task_queue", "workflow_tasks", ["tenant_id", "status", "due_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "actor_user_id", "operation", "key"),
    )
    op.create_index("ix_idempotency_records_tenant_id", "idempotency_records", ["tenant_id"])
    op.create_index("ix_idempotency_expiry", "idempotency_records", ["expires_at"])

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_outbox_delivery", "outbox_events", ["status", "available_at", "created_at"])


def downgrade() -> None:
    for table in [
        "outbox_events",
        "idempotency_records",
        "workflow_tasks",
        "workflow_instances",
        "application_definitions",
        "consent_grants",
        "organization_memberships",
        "organizations",
    ]:
        op.drop_table(table)
