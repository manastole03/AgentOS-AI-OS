"""AI operating system persistence.

Revision ID: 0001_ai_operating_system
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_ai_operating_system"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ai_agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("requested_team", sa.String(64)),
        sa.Column("selected_team", sa.String(64)),
        sa.Column("collaborators", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("provider_preference", sa.String(32), nullable=False),
        sa.Column("memory_mode", sa.String(32), nullable=False),
        sa.Column("input_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("output_ciphertext", sa.LargeBinary()),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for name, columns in {
        "ix_ai_runs_thread": ["thread_id"],
        "ix_ai_runs_owner": ["owner_user_id"],
        "ix_ai_runs_tenant": ["tenant_id"],
        "ix_ai_runs_status": ["status"],
        "ix_ai_runs_owner_created": ["owner_user_id", "created_at"],
        "ix_ai_runs_status_created": ["status", "created_at"],
    }.items():
        op.create_index(name, "ai_agent_runs", columns)

    op.create_table(
        "ai_agent_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("team", sa.String(64)),
        sa.Column("agent", sa.String(100)),
        sa.Column("tool_name", sa.String(200)),
        sa.Column("model_alias", sa.String(100)),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for name, columns in {
        "ix_ai_audit_run": ["run_id"],
        "ix_ai_audit_actor": ["actor_user_id"],
        "ix_ai_audit_tenant": ["tenant_id"],
        "ix_ai_audit_type": ["event_type"],
        "ix_ai_audit_created": ["created_at"],
        "ix_ai_audit_run_created": ["run_id", "created_at"],
    }.items():
        op.create_index(name, "ai_agent_audit_events", columns)

    op.create_table(
        "ai_agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_team", sa.String(64), nullable=False),
        sa.Column("recipient_team", sa.String(64), nullable=False),
        sa.Column("message_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_ai_messages_run", "ai_agent_messages", ["run_id"])
    op.create_index(
        "ix_ai_messages_run_recipient", "ai_agent_messages", ["run_id", "recipient_team"]
    )

    op.create_table(
        "ai_knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_uri", sa.String(2048)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "team", "content_hash", name="uq_ai_document_content"),
    )
    op.create_index("ix_ai_documents_tenant", "ai_knowledge_documents", ["tenant_id"])
    op.create_index("ix_ai_documents_owner", "ai_knowledge_documents", ["owner_user_id"])
    op.create_index("ix_ai_documents_tenant_team", "ai_knowledge_documents", ["tenant_id", "team"])

    op.create_table(
        "ai_knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ai_knowledge_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_chunks_document", "ai_knowledge_chunks", ["document_id"])
    op.create_index("ix_ai_chunks_tenant", "ai_knowledge_chunks", ["tenant_id"])
    op.create_index("ix_ai_chunks_tenant_team", "ai_knowledge_chunks", ["tenant_id", "team"])

    op.create_table(
        "ai_long_term_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team", sa.String(64), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("salience", sa.Float(), nullable=False, server_default="1"),
        sa.Column("access_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id", "owner_user_id", "team", "content_hash", name="uq_ai_memory_content"
        ),
    )
    op.create_index("ix_ai_memory_tenant", "ai_long_term_memories", ["tenant_id"])
    op.create_index("ix_ai_memory_owner", "ai_long_term_memories", ["owner_user_id"])
    op.create_index(
        "ix_ai_memory_scope", "ai_long_term_memories", ["tenant_id", "owner_user_id", "team"]
    )


def downgrade() -> None:
    for table in [
        "ai_long_term_memories",
        "ai_knowledge_chunks",
        "ai_knowledge_documents",
        "ai_agent_messages",
        "ai_agent_audit_events",
        "ai_agent_runs",
    ]:
        op.drop_table(table)
