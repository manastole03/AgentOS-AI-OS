"""Add complete role registration data and dual-channel verification.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.add_column(
        "users",
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("patient_profiles", sa.Column("date_of_birth", sa.Date()))
    op.add_column("patient_profiles", sa.Column("sex_at_birth", sa.String(32)))
    op.add_column("patient_profiles", sa.Column("blood_type", sa.String(8)))
    op.add_column("patient_profiles", sa.Column("emergency_contact", sa.String(255)))

    op.add_column("doctor_profiles", sa.Column("license_jurisdiction", sa.String(100)))
    op.add_column("doctor_profiles", sa.Column("specialty", sa.String(150)))
    op.add_column("doctor_profiles", sa.Column("affiliation", sa.String(255)))
    op.add_column(
        "doctor_profiles",
        sa.Column("credentials_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column("organization_profiles", sa.Column("license_number", sa.String(100)))
    op.add_column("organization_profiles", sa.Column("organization_type", sa.String(100)))
    op.add_column(
        "organization_profiles",
        sa.Column("product_types", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "organization_profiles",
        sa.Column("credentials_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.drop_constraint("valid_otp_purpose", "otp_challenges", type_="check")
    op.create_check_constraint(
        "valid_otp_purpose",
        "otp_challenges",
        "purpose IN ('email_verification','mobile_verification','password_reset')",
    )

    # Existing users predate mobile OTP. Grandfather them so this migration does not lock
    # active accounts; every new registration must complete both challenges.
    op.execute("UPDATE users SET phone_verified = true WHERE status = 'active'")

    op.add_column("audit_events", sa.Column("previous_hash", sa.String(64)))
    op.add_column("audit_events", sa.Column("event_hash", sa.String(64)))
    op.execute(
        """
        DO $$
        DECLARE item RECORD; prior TEXT := '';
        BEGIN
          FOR item IN SELECT id, event_type, event_data FROM audit_events ORDER BY created_at, id
          LOOP
            UPDATE audit_events
            SET previous_hash = prior,
                event_hash = encode(digest(
                  prior || item.id::text || item.event_type || item.event_data::text,
                  'sha256'
                ), 'hex')
            WHERE id = item.id;
            SELECT event_hash INTO prior FROM audit_events WHERE id = item.id;
          END LOOP;
        END $$;
        """
    )
    op.alter_column("audit_events", "previous_hash", nullable=False)
    op.alter_column("audit_events", "event_hash", nullable=False)
    op.create_unique_constraint("uq_audit_events_event_hash", "audit_events", ["event_hash"])
    op.execute(
        """
        CREATE FUNCTION healthos_seal_audit_event() RETURNS trigger AS $$
        DECLARE prior TEXT;
        BEGIN
          PERFORM pg_advisory_xact_lock(hashtext('healthos-audit-chain'));
          SELECT event_hash INTO prior FROM audit_events
          ORDER BY created_at DESC, id DESC LIMIT 1;
          NEW.previous_hash := COALESCE(prior, '');
          NEW.event_hash := encode(digest(
            NEW.previous_hash || NEW.id::text || NEW.event_type || NEW.event_data::text,
            'sha256'
          ), 'hex');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER seal_audit_event BEFORE INSERT ON audit_events
          FOR EACH ROW EXECUTE FUNCTION healthos_seal_audit_event()
        """
    )
    op.execute(
        """
        CREATE FUNCTION healthos_reject_audit_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_audit_mutation BEFORE UPDATE OR DELETE ON audit_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS reject_audit_mutation ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS seal_audit_event ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS healthos_reject_audit_mutation()")
    op.execute("DROP FUNCTION IF EXISTS healthos_seal_audit_event()")
    op.drop_constraint("uq_audit_events_event_hash", "audit_events", type_="unique")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
    op.drop_constraint("valid_otp_purpose", "otp_challenges", type_="check")
    op.create_check_constraint(
        "valid_otp_purpose",
        "otp_challenges",
        "purpose IN ('email_verification','password_reset')",
    )
    for column in ("credentials_verified", "product_types", "organization_type", "license_number"):
        op.drop_column("organization_profiles", column)
    for column in ("credentials_verified", "affiliation", "specialty", "license_jurisdiction"):
        op.drop_column("doctor_profiles", column)
    for column in ("emergency_contact", "blood_type", "sex_at_birth", "date_of_birth"):
        op.drop_column("patient_profiles", column)
    op.drop_column("users", "phone_verified")
