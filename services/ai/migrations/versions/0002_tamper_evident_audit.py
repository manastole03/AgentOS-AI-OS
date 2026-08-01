"""Seal the AI audit trail with an append-only hash chain.

Revision ID: 0002_tamper_evident_audit
Revises: 0001_ai_operating_system
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tamper_evident_audit"
down_revision: str | None = "0001_ai_operating_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.add_column("ai_agent_audit_events", sa.Column("previous_hash", sa.String(64)))
    op.add_column("ai_agent_audit_events", sa.Column("event_hash", sa.String(64)))
    op.execute(
        """
        DO $$
        DECLARE item RECORD; prior TEXT := '';
        BEGIN
          FOR item IN SELECT id, event_type, details
          FROM ai_agent_audit_events ORDER BY created_at, id
          LOOP
            UPDATE ai_agent_audit_events
            SET previous_hash = prior,
                event_hash = encode(digest(
                  prior || item.id::text || item.event_type || item.details::text,
                  'sha256'
                ), 'hex')
            WHERE id = item.id;
            SELECT event_hash INTO prior FROM ai_agent_audit_events WHERE id = item.id;
          END LOOP;
        END $$;
        """
    )
    op.alter_column("ai_agent_audit_events", "previous_hash", nullable=False)
    op.alter_column("ai_agent_audit_events", "event_hash", nullable=False)
    op.create_unique_constraint(
        "uq_ai_agent_audit_event_hash", "ai_agent_audit_events", ["event_hash"]
    )
    op.execute(
        """
        CREATE FUNCTION healthos_seal_ai_audit_event() RETURNS trigger AS $$
        DECLARE prior TEXT;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtext('healthos-ai-audit-chain'));
          SELECT event_hash INTO prior FROM ai_agent_audit_events
          ORDER BY created_at DESC, id DESC LIMIT 1;
          NEW.previous_hash := COALESCE(prior, '');
          NEW.event_hash := encode(digest(
            NEW.previous_hash || NEW.id::text || NEW.event_type || NEW.details::text,
            'sha256'
          ), 'hex');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER seal_ai_audit_event BEFORE INSERT ON ai_agent_audit_events
          FOR EACH ROW EXECUTE FUNCTION healthos_seal_ai_audit_event()
        """
    )
    op.execute(
        """
        CREATE FUNCTION healthos_reject_ai_audit_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'AI audit events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_ai_audit_mutation BEFORE UPDATE OR DELETE ON ai_agent_audit_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_ai_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS reject_ai_audit_mutation ON ai_agent_audit_events")
    op.execute("DROP TRIGGER IF EXISTS seal_ai_audit_event ON ai_agent_audit_events")
    op.execute("DROP FUNCTION IF EXISTS healthos_reject_ai_audit_mutation()")
    op.execute("DROP FUNCTION IF EXISTS healthos_seal_ai_audit_event()")
    op.drop_constraint("uq_ai_agent_audit_event_hash", "ai_agent_audit_events", type_="unique")
    op.drop_column("ai_agent_audit_events", "event_hash")
    op.drop_column("ai_agent_audit_events", "previous_hash")
