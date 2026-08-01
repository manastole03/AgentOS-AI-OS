"""Add governed AI action proposals.

Revision ID: 0003_action_proposals
Revises: 0002_tamper_evident_audit
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_action_proposals"
down_revision: str | None = "0002_tamper_evident_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("arguments_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("affected_resources", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("execution_reference", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("risk_level IN ('low','medium','high')", name="ai_proposal_risk"),
        sa.CheckConstraint(
            "status IN ('proposed','confirmed','executing','executed',"
            "'cancelled','expired','failed')",
            name="ai_proposal_status",
        ),
    )
    for name, columns in {
        "ix_ai_action_proposals_run_id": ["run_id"],
        "ix_ai_action_proposals_owner_user_id": ["owner_user_id"],
        "ix_ai_action_proposals_tenant_id": ["tenant_id"],
        "ix_ai_action_proposals_action_type": ["action_type"],
        "ix_ai_action_proposals_status": ["status"],
        "ix_ai_proposal_owner_status": ["owner_user_id", "status", "created_at"],
        "ix_ai_proposal_expiry": ["status", "expires_at"],
    }.items():
        op.create_index(name, "ai_action_proposals", columns)


def downgrade() -> None:
    op.drop_table("ai_action_proposals")
