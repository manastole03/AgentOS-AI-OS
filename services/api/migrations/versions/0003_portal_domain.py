"""Create portal domain, documents, notifications, and integration schema.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
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
        "portal_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="active"),
        sa.Column("external_reference", sa.String(255)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("amount_cents", sa.Integer()),
        sa.Column("currency", sa.String(3)),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    for name, columns in {
        "ix_portal_records_tenant_id": ["tenant_id"],
        "ix_portal_records_owner_user_id": ["owner_user_id"],
        "ix_portal_records_patient_user_id": ["patient_user_id"],
        "ix_portal_records_assigned_user_id": ["assigned_user_id"],
        "ix_portal_records_category": ["category"],
        "ix_portal_records_status": ["status"],
        "ix_portal_records_external_reference": ["external_reference"],
        "ix_portal_records_occurred_at": ["occurred_at"],
        "ix_portal_records_due_at": ["due_at"],
        "ix_portal_records_scope": ["tenant_id", "category", "created_at"],
        "ix_portal_records_patient": ["patient_user_id", "category"],
    }.items():
        op.create_index(name, "portal_records", columns)

    op.create_table(
        "document_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="stored"),
        sa.Column("ocr_text", sa.Text()),
        sa.Column("fhir_resource_type", sa.String(100)),
        sa.Column("fhir_resource_id", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    for name, columns in {
        "ix_document_assets_tenant_id": ["tenant_id"],
        "ix_document_assets_owner_user_id": ["owner_user_id"],
        "ix_document_assets_patient_user_id": ["patient_user_id"],
        "ix_documents_scope": ["tenant_id", "category", "created_at"],
    }.items():
        op.create_index(name, "document_assets", columns)

    op.create_table(
        "portal_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recipient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(32), nullable=False, server_default="in_app"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(2048)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_portal_notifications_tenant_id", "portal_notifications", ["tenant_id"])
    op.create_index(
        "ix_portal_notifications_recipient_user_id", "portal_notifications", ["recipient_user_id"]
    )
    op.create_index(
        "ix_notifications_recipient", "portal_notifications", ["recipient_user_id", "created_at"]
    )

    op.create_table(
        "integration_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_reference", sa.String(255)),
        sa.Column("request_digest", sa.String(64)),
        sa.Column("response_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_integration_events_tenant_id", "integration_events", ["tenant_id"])
    op.create_index("ix_integration_events_actor_user_id", "integration_events", ["actor_user_id"])
    op.create_index(
        "ix_integration_scope", "integration_events", ["tenant_id", "provider", "created_at"]
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *timestamps(),
    )

    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer()),
        sa.column("permission_id", sa.Integer()),
    )
    op.bulk_insert(
        permissions,
        [
            {"id": 7, "name": "portal:read", "description": "Read authorized portal resources"},
            {"id": 8, "name": "portal:write", "description": "Manage authorized portal resources"},
            {"id": 9, "name": "documents:manage", "description": "Manage authorized documents"},
            {
                "id": 10,
                "name": "integrations:execute",
                "description": "Execute authorized integrations",
            },
            {"id": 11, "name": "system:admin", "description": "Administer the HealthOS platform"},
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            *[
                {"role_id": role, "permission_id": permission}
                for role in range(1, 6)
                for permission in (7, 8, 9)
            ],
            *[{"role_id": role, "permission_id": 10} for role in (2, 3, 4, 5)],
            {"role_id": 5, "permission_id": 11},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id BETWEEN 7 AND 11")
    op.execute("DELETE FROM permissions WHERE id BETWEEN 7 AND 11")
    for table in [
        "system_settings",
        "integration_events",
        "portal_notifications",
        "document_assets",
        "portal_records",
    ]:
        op.drop_table(table)
