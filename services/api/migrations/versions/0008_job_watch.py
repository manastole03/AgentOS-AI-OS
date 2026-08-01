"""Add job watch profiles, sources, postings, and alert deliveries.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
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
        "job_watch_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("check_interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("titles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("user_id"),
        sa.CheckConstraint(
            "check_interval_minutes >= 1 AND check_interval_minutes <= 1440",
            name="job_watch_interval_bounds",
        ),
    )
    op.create_index("ix_job_watch_profiles_user_id", "job_watch_profiles", ["user_id"])
    op.create_index("ix_job_watch_profiles_tenant_id", "job_watch_profiles", ["tenant_id"])
    op.create_index(
        "ix_job_watch_profile_enabled", "job_watch_profiles", ["enabled", "email_enabled"]
    )

    op.create_table(
        "job_watch_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_watch_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("board_key", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("board_url", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("initial_sync_completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_message", sa.String(length=500)),
        *timestamps(),
        sa.UniqueConstraint("profile_id", "source_type", "board_key"),
        sa.CheckConstraint(
            "source_type IN ('greenhouse', 'lever', 'ashby')",
            name="job_watch_source_type",
        ),
    )
    op.create_index("ix_job_watch_sources_profile_id", "job_watch_sources", ["profile_id"])
    op.create_index("ix_job_watch_source_enabled", "job_watch_sources", ["profile_id", "enabled"])

    op.create_table(
        "job_watch_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("board_key", sa.String(length=255), nullable=False),
        sa.Column("external_job_id", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255)),
        sa.Column("job_url", sa.String(length=2048), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True)),
        sa.Column("employment_type", sa.String(length=64)),
        sa.Column("workplace_type", sa.String(length=64)),
        sa.Column("description_text", sa.Text()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("source_type", "board_key", "external_job_id"),
        sa.CheckConstraint(
            "source_type IN ('greenhouse', 'lever', 'ashby')",
            name="job_watch_posting_source_type",
        ),
    )
    op.create_index(
        "ix_job_watch_posting_active",
        "job_watch_postings",
        ["source_type", "board_key", "is_active"],
    )

    op.create_table(
        "job_watch_alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_watch_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "posting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_watch_postings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="email"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("matched_title", sa.String(length=255)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("profile_id", "posting_id", "channel"),
    )
    op.create_index(
        "ix_job_watch_alert_deliveries_profile_id", "job_watch_alert_deliveries", ["profile_id"]
    )
    op.create_index(
        "ix_job_watch_alert_deliveries_posting_id", "job_watch_alert_deliveries", ["posting_id"]
    )
    op.create_index(
        "ix_job_watch_delivery_recipient",
        "job_watch_alert_deliveries",
        ["recipient_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_watch_delivery_recipient", table_name="job_watch_alert_deliveries")
    op.drop_index(
        "ix_job_watch_alert_deliveries_posting_id", table_name="job_watch_alert_deliveries"
    )
    op.drop_index(
        "ix_job_watch_alert_deliveries_profile_id", table_name="job_watch_alert_deliveries"
    )
    op.drop_table("job_watch_alert_deliveries")
    op.drop_index("ix_job_watch_posting_active", table_name="job_watch_postings")
    op.drop_table("job_watch_postings")
    op.drop_index("ix_job_watch_source_enabled", table_name="job_watch_sources")
    op.drop_index("ix_job_watch_sources_profile_id", table_name="job_watch_sources")
    op.drop_table("job_watch_sources")
    op.drop_index("ix_job_watch_profile_enabled", table_name="job_watch_profiles")
    op.drop_index("ix_job_watch_profiles_tenant_id", table_name="job_watch_profiles")
    op.drop_index("ix_job_watch_profiles_user_id", table_name="job_watch_profiles")
    op.drop_table("job_watch_profiles")
