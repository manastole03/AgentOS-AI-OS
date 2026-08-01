"""Add clinical, scheduling, medication, lab, and insurance domain tables.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
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
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "code_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("uri", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("publisher", sa.String(length=255)),
        sa.Column("oid", sa.String(length=64)),
        sa.Column("released_at", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("uri", "version"),
    )
    op.create_index("ix_code_systems_uri", "code_systems", ["uri"])
    op.create_index("ix_code_system_lookup", "code_systems", ["uri", "is_active"])

    op.create_table(
        "code_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "code_system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_systems.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display", sa.String(length=500), nullable=False),
        sa.Column("definition", sa.Text()),
        sa.Column("parent_code", sa.String(length=64)),
        sa.Column("properties", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        *timestamps(),
        sa.UniqueConstraint("code_system_id", "code", "effective_from"),
    )
    op.create_index("ix_code_concepts_code_system_id", "code_concepts", ["code_system_id"])
    op.create_index(
        "ix_code_concepts_lookup", "code_concepts", ["code_system_id", "code", "is_active"]
    )
    op.execute(
        "CREATE INDEX ix_code_concepts_display_trgm ON code_concepts "
        "USING gin (display gin_trgm_ops)"
    )

    op.create_table(
        "patient_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("system", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("type_code", sa.String(length=16), nullable=False),
        sa.Column(
            "assigner_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("system", "value"),
        sa.CheckConstraint(
            "type_code IN ('MR','NI','PPN','DL','MB')",
            name="patient_identifier_type",
        ),
    )
    op.create_index("ix_patient_identifiers_tenant_id", "patient_identifiers", ["tenant_id"])
    op.create_index(
        "ix_patient_identifiers_patient_user_id", "patient_identifiers", ["patient_user_id"]
    )
    op.create_index(
        "ix_patient_identifier_patient", "patient_identifiers", ["patient_user_id", "is_active"]
    )
    op.create_index("ix_patient_identifier_scope", "patient_identifiers", ["tenant_id", "system"])

    op.create_table(
        "practitioner_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "practitioner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("system", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("type_code", sa.String(length=16), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8)),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("system", "value"),
        sa.CheckConstraint(
            "type_code IN ('NPI','DEA','LIC','TAX')",
            name="practitioner_identifier_type",
        ),
    )
    op.create_index(
        "ix_practitioner_identifiers_tenant_id", "practitioner_identifiers", ["tenant_id"]
    )
    op.create_index(
        "ix_practitioner_identifiers_practitioner_user_id",
        "practitioner_identifiers",
        ["practitioner_user_id"],
    )
    op.create_index(
        "ix_practitioner_identifier_scope",
        "practitioner_identifiers",
        ["tenant_id", "type_code", "is_active"],
    )

    op.create_table(
        "patient_communication_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="en-US"),
        sa.Column("quiet_hours_start", sa.Time()),
        sa.Column("quiet_hours_end", sa.Time()),
        sa.Column("channels", postgresql.JSONB(), nullable=False, server_default='["in_app"]'),
        sa.Column(
            "medication_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "appointment_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        *timestamps(),
        sa.CheckConstraint(
            "(quiet_hours_start IS NULL) = (quiet_hours_end IS NULL)",
            name="quiet_hours_pair",
        ),
    )
    op.create_index(
        "ix_patient_communication_preferences_tenant_id",
        "patient_communication_preferences",
        ["tenant_id"],
    )
    op.create_index(
        "ix_comm_pref_scope", "patient_communication_preferences", ["tenant_id", "timezone"]
    )

    op.create_table(
        "growth_reference_standards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("measure", sa.String(length=32), nullable=False),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("age_unit", sa.String(length=8), nullable=False),
        sa.Column("age_value", sa.Integer(), nullable=False),
        sa.Column("l", sa.Numeric(10, 6), nullable=False),
        sa.Column("m", sa.Numeric(10, 6), nullable=False),
        sa.Column("s", sa.Numeric(10, 6), nullable=False),
        sa.Column("p3", sa.Numeric(10, 4)),
        sa.Column("p50", sa.Numeric(10, 4)),
        sa.Column("p97", sa.Numeric(10, 4)),
        *timestamps(),
        sa.UniqueConstraint("source", "measure", "sex", "age_unit", "age_value"),
        sa.CheckConstraint("source IN ('WHO','CDC')", name="growth_standard_source"),
        sa.CheckConstraint(
            "measure IN "
            "('height_for_age','weight_for_age','bmi_for_age','hc_for_age','weight_for_height')",
            name="growth_standard_measure",
        ),
        sa.CheckConstraint("sex IN ('male','female')", name="growth_standard_sex"),
        sa.CheckConstraint("age_unit IN ('day','month')", name="growth_age_unit"),
        sa.CheckConstraint("age_value >= 0", name="growth_age_nonneg"),
        sa.CheckConstraint("s > 0", name="growth_sigma_positive"),
    )

    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "parent_department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column("cost_center", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "code"),
    )
    op.create_index("ix_departments_tenant_id", "departments", ["tenant_id"])
    op.create_index("ix_departments_organization_id", "departments", ["organization_id"])
    op.create_index(
        "ix_department_scope", "departments", ["tenant_id", "organization_id", "is_active"]
    )

    op.create_table(
        "practitioner_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "practitioner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("specialty_code", sa.String(length=64)),
        sa.Column("taxonomy_code", sa.String(length=32)),
        sa.Column("privileges", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "credentialing_status", sa.String(length=32), nullable=False, server_default="pending"
        ),
        sa.Column("credentialed_at", sa.Date()),
        sa.Column("credential_expires_at", sa.Date()),
        sa.Column("accepts_new_patients", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("practitioner_user_id", "organization_id", "role_code"),
        sa.CheckConstraint(
            "credentialing_status IN ('pending','active','suspended','expired','revoked')",
            name="credentialing_status",
        ),
    )
    op.create_index("ix_practitioner_roles_tenant_id", "practitioner_roles", ["tenant_id"])
    op.create_index(
        "ix_practitioner_roles_practitioner_user_id", "practitioner_roles", ["practitioner_user_id"]
    )
    op.create_index(
        "ix_practitioner_roles_organization_id", "practitioner_roles", ["organization_id"]
    )
    op.create_index(
        "ix_practitioner_roles_credential_expires_at",
        "practitioner_roles",
        ["credential_expires_at"],
    )
    op.create_index(
        "ix_practitioner_role_scope",
        "practitioner_roles",
        ["tenant_id", "specialty_code", "is_active"],
    )
    op.create_index(
        "ix_practitioner_role_directory",
        "practitioner_roles",
        ["organization_id", "specialty_code", "accepts_new_patients"],
    )

    op.create_table(
        "service_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column("service_code_system", sa.String(length=128), nullable=False),
        sa.Column("service_code", sa.String(length=64), nullable=False),
        sa.Column("service_display", sa.String(length=255), nullable=False),
        sa.Column(
            "service_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("cpt_code", sa.String(length=16)),
        sa.Column("revenue_code", sa.String(length=16)),
        sa.Column("base_price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "service_code", "effective_from"),
        sa.CheckConstraint("base_price_cents >= 0", name="service_price_nonneg"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="service_currency_iso4217"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="service_effective_period",
        ),
    )
    op.create_index("ix_service_items_tenant_id", "service_items", ["tenant_id"])
    op.create_index("ix_service_items_organization_id", "service_items", ["organization_id"])
    op.create_index("ix_service_items_service_code", "service_items", ["service_code"])
    op.create_index(
        "ix_service_item_scope", "service_items", ["tenant_id", "organization_id", "is_active"]
    )

    op.create_table(
        "payer_contract_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payer_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "provider_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service_code_system", sa.String(length=128), nullable=False),
        sa.Column("service_code", sa.String(length=64), nullable=False),
        sa.Column("service_display", sa.String(length=255), nullable=False),
        sa.Column(
            "service_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("allowed_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        *timestamps(),
        sa.UniqueConstraint(
            "payer_organization_id", "provider_organization_id", "service_code", "effective_from"
        ),
        sa.CheckConstraint("allowed_cents >= 0", name="contract_rate_nonneg"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="contract_currency_iso4217"),
    )
    op.create_index("ix_payer_contract_rates_tenant_id", "payer_contract_rates", ["tenant_id"])
    op.create_index(
        "ix_payer_contract_rates_payer_organization_id",
        "payer_contract_rates",
        ["payer_organization_id"],
    )
    op.create_index(
        "ix_payer_contract_rates_provider_organization_id",
        "payer_contract_rates",
        ["provider_organization_id"],
    )
    op.create_index(
        "ix_payer_contract_rates_service_code", "payer_contract_rates", ["service_code"]
    )
    op.create_index(
        "ix_contract_rate_lookup",
        "payer_contract_rates",
        ["payer_organization_id", "service_code", "effective_from"],
    )

    op.create_table(
        "provider_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="in_person"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint("channel IN ('in_person','telehealth')", name="schedule_channel"),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="schedule_day_of_week"),
        sa.CheckConstraint("end_time > start_time", name="schedule_time_order"),
        sa.CheckConstraint("slot_minutes BETWEEN 5 AND 480", name="schedule_slot_minutes"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="schedule_valid_period",
        ),
    )
    op.create_index("ix_provider_schedules_tenant_id", "provider_schedules", ["tenant_id"])
    op.create_index(
        "ix_provider_schedules_provider_user_id", "provider_schedules", ["provider_user_id"]
    )
    op.create_index(
        "ix_provider_schedule_scope",
        "provider_schedules",
        ["tenant_id", "provider_user_id", "is_active"],
    )

    op.create_table(
        "appointment_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider_schedules.id", ondelete="SET NULL"),
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("price_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3)),
        *timestamps(),
        sa.UniqueConstraint(
            "provider_user_id", "start_at", name="uq_appointment_slot_provider_start"
        ),
        sa.CheckConstraint(
            "status IN ('open','held','booked','blocked','cancelled')",
            name="slot_status",
        ),
        sa.CheckConstraint("channel IN ('in_person','telehealth')", name="slot_channel"),
        sa.CheckConstraint("end_at > start_at", name="slot_period"),
        sa.CheckConstraint("capacity >= 1", name="slot_capacity_positive"),
        sa.CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="slot_capacity_bounds",
        ),
        sa.CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="slot_currency_required",
        ),
    )
    op.create_index("ix_appointment_slots_tenant_id", "appointment_slots", ["tenant_id"])
    op.create_index(
        "ix_appointment_slots_provider_user_id", "appointment_slots", ["provider_user_id"]
    )
    op.create_index("ix_appointment_slots_start_at", "appointment_slots", ["start_at"])
    op.create_index("ix_slot_scope", "appointment_slots", ["tenant_id", "start_at", "status"])
    op.create_index(
        "ix_slot_open",
        "appointment_slots",
        ["tenant_id", "start_at"],
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointment_slots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True)),
        sa.Column("referral_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("payment_status", sa.String(length=16), nullable=False, server_default="unpaid"),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True)),
        sa.Column("cancellation_reason", sa.String(length=255)),
        sa.Column(
            "cancelled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "booked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        *timestamps(),
        sa.CheckConstraint("channel IN ('in_person','telehealth')", name="appointment_channel"),
        sa.CheckConstraint(
            "status IN "
            "('requested','pending-payment','confirmed','checked-in','fulfilled','cancelled','no-show')",
            name="appointment_status",
        ),
        sa.CheckConstraint(
            "payment_status IN ('unpaid','authorized','paid','refunded')",
            name="appointment_payment_status",
        ),
    )
    op.create_index("ix_appointments_tenant_id", "appointments", ["tenant_id"])
    op.create_index("ix_appointments_slot_id", "appointments", ["slot_id"])
    op.create_index("ix_appointments_patient_user_id", "appointments", ["patient_user_id"])
    op.create_index("ix_appointments_provider_user_id", "appointments", ["provider_user_id"])
    op.create_index("ix_appointments_encounter_id", "appointments", ["encounter_id"])
    op.create_index("ix_appointment_scope", "appointments", ["tenant_id", "status", "booked_at"])
    op.create_index("ix_appointment_patient", "appointments", ["patient_user_id", "status"])
    op.create_index(
        "ix_appointment_slot_booked",
        "appointments",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('confirmed','checked-in','fulfilled')"),
    )

    op.create_table(
        "appointment_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=32)),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column(
            "changed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=255)),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_appointment_status_events_tenant_id", "appointment_status_events", ["tenant_id"]
    )
    op.create_index(
        "ix_appointment_status_events_appointment_id",
        "appointment_status_events",
        ["appointment_id"],
    )
    op.create_index(
        "ix_appointment_event_timeline",
        "appointment_status_events",
        ["appointment_id", "occurred_at"],
    )

    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "primary_practitioner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
        ),
        sa.Column("class_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("location", sa.String(length=255)),
        sa.Column("reason_text", sa.Text()),
        sa.Column("disposition", sa.String(length=64)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "class_code IN ('AMB','IMP','EMER','VR','HH')",
            name="encounter_class_code",
        ),
        sa.CheckConstraint(
            "status IN "
            "('planned','arrived','in-progress','finished','cancelled','entered-in-error')",
            name="encounter_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="encounter_source",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="encounter_period",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="encounter_confidence_range",
        ),
    )
    op.create_index("ix_encounters_tenant_id", "encounters", ["tenant_id"])
    op.create_index("ix_encounters_patient_user_id", "encounters", ["patient_user_id"])
    op.create_index(
        "ix_encounters_primary_practitioner_user_id", "encounters", ["primary_practitioner_user_id"]
    )
    op.create_index("ix_encounters_appointment_id", "encounters", ["appointment_id"])
    op.create_index("ix_encounters_started_at", "encounters", ["started_at"])
    op.create_index("ix_encounters_recorded_by_user_id", "encounters", ["recorded_by_user_id"])
    op.create_index("ix_encounters_source_document_id", "encounters", ["source_document_id"])
    op.create_index("ix_encounter_patient", "encounters", ["patient_user_id", "started_at"])
    op.create_index("ix_encounter_scope", "encounters", ["tenant_id", "class_code", "started_at"])
    op.create_index(
        "ix_encounter_practitioner", "encounters", ["primary_practitioner_user_id", "started_at"]
    )

    op.create_table(
        "telehealth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("provider_room_id", sa.String(length=255), nullable=False),
        sa.Column("join_token_hash", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("participants", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("recording_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "recording_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("connection_quality", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("licensure_state", sa.String(length=8)),
        sa.Column("licensure_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="telehealth_period",
        ),
        sa.CheckConstraint(
            "recording_asset_id IS NULL OR recording_consent",
            name="telehealth_recording_consent",
        ),
    )
    op.create_index("ix_telehealth_sessions_tenant_id", "telehealth_sessions", ["tenant_id"])
    op.create_index("ix_telehealth_sessions_encounter_id", "telehealth_sessions", ["encounter_id"])
    op.create_index("ix_telehealth_scope", "telehealth_sessions", ["tenant_id", "started_at"])

    op.create_table(
        "conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("condition_code_system", sa.String(length=128), nullable=False),
        sa.Column("condition_code", sa.String(length=64), nullable=False),
        sa.Column("condition_display", sa.String(length=255), nullable=False),
        sa.Column(
            "condition_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("clinical_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("severity_code_system", sa.String(length=128)),
        sa.Column("severity_code", sa.String(length=64)),
        sa.Column("severity_display", sa.String(length=255)),
        sa.Column(
            "severity_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("body_site_code_system", sa.String(length=128)),
        sa.Column("body_site_code", sa.String(length=64)),
        sa.Column("body_site_display", sa.String(length=255)),
        sa.Column(
            "body_site_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("onset_date", sa.Date()),
        sa.Column("onset_precision", sa.String(length=8)),
        sa.Column("abatement_date", sa.Date()),
        sa.Column("abatement_precision", sa.String(length=8)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conditions.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "category IN ('problem-list-item','encounter-diagnosis')",
            name="condition_category",
        ),
        sa.CheckConstraint(
            "clinical_status IN "
            "('active','recurrence','relapse','inactive','remission','resolved')",
            name="condition_clinical_status",
        ),
        sa.CheckConstraint(
            "verification_status IN "
            "('unconfirmed','provisional','differential','confirmed','refuted','entered-in-error')",
            name="condition_verification_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="condition_source",
        ),
        sa.CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="condition_onset_precision",
        ),
        sa.CheckConstraint(
            "abatement_precision IS NULL OR abatement_precision IN ('day','month','year')",
            name="condition_abatement_precision",
        ),
        sa.CheckConstraint(
            "onset_date IS NULL OR onset_precision IS NOT NULL",
            name="condition_onset_precision_required",
        ),
        sa.CheckConstraint(
            "abatement_date IS NULL OR abatement_date >= onset_date",
            name="condition_abatement_order",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="condition_confidence_range",
        ),
        sa.CheckConstraint(
            "source <> 'ai-extracted' OR verification_status <> 'confirmed' OR "
            "human_verified_at IS NOT NULL",
            name="condition_ai_human_verified",
        ),
        sa.CheckConstraint("version >= 1", name="condition_version_positive"),
    )
    op.create_index("ix_conditions_tenant_id", "conditions", ["tenant_id"])
    op.create_index("ix_conditions_patient_user_id", "conditions", ["patient_user_id"])
    op.create_index("ix_conditions_encounter_id", "conditions", ["encounter_id"])
    op.create_index("ix_conditions_condition_code", "conditions", ["condition_code"])
    op.create_index("ix_conditions_recorded_by_user_id", "conditions", ["recorded_by_user_id"])
    op.create_index("ix_conditions_source_document_id", "conditions", ["source_document_id"])
    op.create_index(
        "ix_condition_patient", "conditions", ["patient_user_id", "clinical_status", "recorded_at"]
    )
    op.create_index("ix_condition_scope", "conditions", ["tenant_id", "category", "recorded_at"])
    op.create_index(
        "ix_condition_current",
        "conditions",
        ["patient_user_id", "clinical_status"],
        postgresql_where=sa.text(
            "superseded_at IS NULL AND verification_status <> 'entered-in-error'"
        ),
    )

    op.create_table(
        "encounter_diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "condition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conditions.id", ondelete="RESTRICT"),
        ),
        sa.Column("diagnosis_code_system", sa.String(length=128), nullable=False),
        sa.Column("diagnosis_code", sa.String(length=64), nullable=False),
        sa.Column("diagnosis_display", sa.String(length=255), nullable=False),
        sa.Column(
            "diagnosis_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_principal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("present_on_admission", sa.String(length=1)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("encounter_id", "diagnosis_code", "rank"),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="encounter_diagnosis_source",
        ),
        sa.CheckConstraint("rank >= 1", name="encounter_diagnosis_rank"),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="encounter_diagnosis_confidence_range",
        ),
    )
    op.create_index("ix_encounter_diagnoses_tenant_id", "encounter_diagnoses", ["tenant_id"])
    op.create_index("ix_encounter_diagnoses_encounter_id", "encounter_diagnoses", ["encounter_id"])
    op.create_index(
        "ix_encounter_diagnoses_patient_user_id", "encounter_diagnoses", ["patient_user_id"]
    )
    op.create_index("ix_encounter_diagnoses_condition_id", "encounter_diagnoses", ["condition_id"])
    op.create_index(
        "ix_encounter_diagnoses_diagnosis_code", "encounter_diagnoses", ["diagnosis_code"]
    )
    op.create_index(
        "ix_encounter_diagnoses_recorded_by_user_id", "encounter_diagnoses", ["recorded_by_user_id"]
    )
    op.create_index(
        "ix_encounter_diagnoses_source_document_id", "encounter_diagnoses", ["source_document_id"]
    )
    op.create_index(
        "ix_encounter_diagnosis_scope", "encounter_diagnoses", ["tenant_id", "diagnosis_code"]
    )
    op.create_index(
        "ix_encounter_diagnosis_principal",
        "encounter_diagnoses",
        ["encounter_id"],
        unique=True,
        postgresql_where=sa.text("is_principal"),
    )

    op.create_table(
        "allergy_intolerances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("substance_code_system", sa.String(length=128), nullable=False),
        sa.Column("substance_code", sa.String(length=64), nullable=False),
        sa.Column("substance_display", sa.String(length=255), nullable=False),
        sa.Column(
            "substance_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("substance_is_class", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("criticality", sa.String(length=32), nullable=False),
        sa.Column("clinical_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("asserter_type", sa.String(length=32), nullable=False),
        sa.Column("onset_date", sa.Date()),
        sa.Column("onset_precision", sa.String(length=8)),
        sa.Column("last_occurrence_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("allergy_intolerances.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint("type IN ('allergy','intolerance')", name="allergy_type"),
        sa.CheckConstraint(
            "category IN ('food','medication','environment','biologic')",
            name="allergy_category",
        ),
        sa.CheckConstraint(
            "criticality IN ('low','high','unable-to-assess')",
            name="allergy_criticality",
        ),
        sa.CheckConstraint(
            "clinical_status IN "
            "('active','recurrence','relapse','inactive','remission','resolved')",
            name="allergy_clinical_status",
        ),
        sa.CheckConstraint(
            "verification_status IN "
            "('unconfirmed','presumed','confirmed','refuted','entered-in-error')",
            name="allergy_verification_status",
        ),
        sa.CheckConstraint(
            "asserter_type IN ('patient','practitioner','related-person')",
            name="allergy_asserter_type",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="allergy_source",
        ),
        sa.CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="allergy_onset_precision",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="allergy_confidence_range",
        ),
        sa.CheckConstraint(
            "source <> 'ai-extracted' OR verification_status <> 'confirmed' OR "
            "human_verified_at IS NOT NULL",
            name="allergy_ai_human_verified",
        ),
        sa.CheckConstraint("version >= 1", name="allergy_version_positive"),
    )
    op.create_index("ix_allergy_intolerances_tenant_id", "allergy_intolerances", ["tenant_id"])
    op.create_index(
        "ix_allergy_intolerances_patient_user_id", "allergy_intolerances", ["patient_user_id"]
    )
    op.create_index(
        "ix_allergy_intolerances_encounter_id", "allergy_intolerances", ["encounter_id"]
    )
    op.create_index(
        "ix_allergy_intolerances_substance_code", "allergy_intolerances", ["substance_code"]
    )
    op.create_index(
        "ix_allergy_intolerances_recorded_by_user_id",
        "allergy_intolerances",
        ["recorded_by_user_id"],
    )
    op.create_index(
        "ix_allergy_intolerances_source_document_id", "allergy_intolerances", ["source_document_id"]
    )
    op.create_index(
        "ix_allergy_patient",
        "allergy_intolerances",
        ["patient_user_id", "clinical_status", "recorded_at"],
    )
    op.create_index(
        "ix_allergy_scope", "allergy_intolerances", ["tenant_id", "category", "recorded_at"]
    )
    op.create_index(
        "ix_allergy_active",
        "allergy_intolerances",
        ["patient_user_id", "substance_code"],
        postgresql_where=sa.text(
            "superseded_at IS NULL AND verification_status <> "
            "'entered-in-error' AND clinical_status = 'active'"
        ),
    )

    op.create_table(
        "allergy_reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "allergy_intolerance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("allergy_intolerances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("manifestation_code_system", sa.String(length=128), nullable=False),
        sa.Column("manifestation_code", sa.String(length=64), nullable=False),
        sa.Column("manifestation_display", sa.String(length=255), nullable=False),
        sa.Column(
            "manifestation_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("severity", sa.String(length=16)),
        sa.Column("exposure_route_code_system", sa.String(length=128)),
        sa.Column("exposure_route_code", sa.String(length=64)),
        sa.Column("exposure_route_display", sa.String(length=255)),
        sa.Column(
            "exposure_route_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("onset_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        *timestamps(),
        sa.CheckConstraint(
            "severity IN ('mild','moderate','severe')",
            name="allergy_reaction_severity",
        ),
    )
    op.create_index(
        "ix_allergy_reactions_allergy_intolerance_id",
        "allergy_reactions",
        ["allergy_intolerance_id"],
    )
    op.create_index(
        "ix_allergy_reactions_manifestation_code", "allergy_reactions", ["manifestation_code"]
    )
    op.create_index(
        "ix_allergy_reaction_parent", "allergy_reactions", ["allergy_intolerance_id", "onset_at"]
    )

    op.create_table(
        "patient_allergy_status",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("no_known_allergies", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("note", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "NOT no_known_allergies OR last_reviewed_at IS NOT NULL",
            name="nka_requires_review",
        ),
        sa.CheckConstraint(
            "(last_reviewed_at IS NULL) = (reviewed_by_user_id IS NULL)",
            name="review_pair",
        ),
    )
    op.create_index("ix_patient_allergy_status_tenant_id", "patient_allergy_status", ["tenant_id"])
    op.create_index(
        "ix_allergy_status_scope", "patient_allergy_status", ["tenant_id", "last_reviewed_at"]
    )

    op.create_table(
        "vital_signs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("observation_code_system", sa.String(length=128), nullable=False),
        sa.Column("observation_code", sa.String(length=64), nullable=False),
        sa.Column("observation_display", sa.String(length=255), nullable=False),
        sa.Column(
            "observation_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("value_numeric", sa.Numeric(12, 4)),
        sa.Column("value_string", sa.String(length=255)),
        sa.Column("value_code_system", sa.String(length=128)),
        sa.Column("value_code", sa.String(length=64)),
        sa.Column("value_display", sa.String(length=255)),
        sa.Column(
            "value_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("value_boolean", sa.Boolean()),
        sa.Column("value_comparator", sa.String(length=2)),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("data_absent_reason", sa.String(length=32)),
        sa.Column("interpretation_code", sa.String(length=8)),
        sa.Column("reference_range_low", sa.Numeric(12, 4)),
        sa.Column("reference_range_high", sa.Numeric(12, 4)),
        sa.Column("reference_range_text", sa.String(length=255)),
        sa.Column("body_site_code", sa.String(length=64)),
        sa.Column("method_code", sa.String(length=64)),
        sa.Column("device", sa.String(length=128)),
        sa.Column(
            "performer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "parent_vital_sign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vital_signs.id", ondelete="RESTRICT"),
        ),
        sa.Column("note", sa.Text()),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vital_signs.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN "
            "('registered','preliminary','final','amended','corrected','cancelled','entered-in-error')",
            name="vital_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="vital_source",
        ),
        sa.CheckConstraint(
            "(value_numeric IS NOT NULL)::int + (value_string IS NOT NULL)::int + (value_code "
            "IS NOT NULL)::int + (value_boolean IS NOT NULL)::int + (data_absent_reason IS NOT "
            "NULL)::int = 1",
            name="vital_single_value",
        ),
        sa.CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="vital_unit_required",
        ),
        sa.CheckConstraint(
            "unit IS NULL OR unit IN "
            "('mm[Hg]','kg','cm','Cel','/min','%','kg/m2','[degF]','L/min')",
            name="vital_unit_ucum",
        ),
        sa.CheckConstraint(
            "value_comparator IS NULL OR value_comparator IN ('<','<=','>','>=')",
            name="vital_comparator",
        ),
        sa.CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="vital_interpretation",
        ),
        sa.CheckConstraint(
            "reference_range_high IS NULL OR reference_range_low IS NULL OR "
            "reference_range_high >= reference_range_low",
            name="vital_range_order",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="vital_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="vital_version_positive"),
    )
    op.create_index("ix_vital_signs_tenant_id", "vital_signs", ["tenant_id"])
    op.create_index("ix_vital_signs_patient_user_id", "vital_signs", ["patient_user_id"])
    op.create_index("ix_vital_signs_encounter_id", "vital_signs", ["encounter_id"])
    op.create_index("ix_vital_signs_observation_code", "vital_signs", ["observation_code"])
    op.create_index("ix_vital_signs_interpretation_code", "vital_signs", ["interpretation_code"])
    op.create_index("ix_vital_signs_effective_at", "vital_signs", ["effective_at"])
    op.create_index("ix_vital_signs_recorded_by_user_id", "vital_signs", ["recorded_by_user_id"])
    op.create_index("ix_vital_signs_source_document_id", "vital_signs", ["source_document_id"])
    op.create_index(
        "ix_vital_patient_trend",
        "vital_signs",
        ["patient_user_id", "observation_code", "effective_at"],
    )
    op.create_index(
        "ix_vital_scope", "vital_signs", ["tenant_id", "observation_code", "effective_at"]
    )
    op.create_index(
        "ix_vital_current",
        "vital_signs",
        ["patient_user_id", "effective_at"],
        postgresql_where=sa.text("superseded_at IS NULL AND status <> 'entered-in-error'"),
    )

    op.create_table(
        "vital_sign_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vital_sign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vital_signs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observation_code_system", sa.String(length=128), nullable=False),
        sa.Column("observation_code", sa.String(length=64), nullable=False),
        sa.Column("observation_display", sa.String(length=255), nullable=False),
        sa.Column(
            "observation_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("value_numeric", sa.Numeric(12, 4)),
        sa.Column("value_string", sa.String(length=255)),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("interpretation_code", sa.String(length=8)),
        sa.Column("reference_range_low", sa.Numeric(12, 4)),
        sa.Column("reference_range_high", sa.Numeric(12, 4)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("vital_sign_id", "observation_code"),
        sa.CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="vital_component_unit_required",
        ),
        sa.CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="vital_component_interpretation",
        ),
    )
    op.create_index(
        "ix_vital_sign_components_vital_sign_id", "vital_sign_components", ["vital_sign_id"]
    )
    op.create_index(
        "ix_vital_sign_components_observation_code", "vital_sign_components", ["observation_code"]
    )
    op.create_index(
        "ix_vital_component_parent", "vital_sign_components", ["vital_sign_id", "sequence"]
    )

    op.create_table(
        "growth_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("age_days", sa.Integer(), nullable=False),
        sa.Column("height_cm", sa.Numeric(6, 2)),
        sa.Column("weight_kg", sa.Numeric(6, 3)),
        sa.Column("head_circumference_cm", sa.Numeric(5, 2)),
        sa.Column("bmi", sa.Numeric(5, 2)),
        sa.Column("height_percentile", sa.Numeric(5, 2)),
        sa.Column("weight_percentile", sa.Numeric(5, 2)),
        sa.Column("bmi_percentile", sa.Numeric(5, 2)),
        sa.Column("height_zscore", sa.Numeric(6, 3)),
        sa.Column("weight_zscore", sa.Numeric(6, 3)),
        sa.Column("bmi_zscore", sa.Numeric(6, 3)),
        sa.Column(
            "standard_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("growth_reference_standards.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("growth_measurements.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="growth_source",
        ),
        sa.CheckConstraint("age_days >= 0", name="growth_age_nonneg"),
        sa.CheckConstraint(
            "bmi_percentile IS NULL OR (bmi_percentile >= 0 AND bmi_percentile <= 100)",
            name="growth_percentile_range",
        ),
        sa.CheckConstraint(
            "height_percentile IS NULL OR (height_percentile >= 0 AND height_percentile <= 100)",
            name="growth_height_percentile_range",
        ),
        sa.CheckConstraint(
            "weight_percentile IS NULL OR (weight_percentile >= 0 AND weight_percentile <= 100)",
            name="growth_weight_percentile_range",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="growth_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="growth_version_positive"),
    )
    op.create_index("ix_growth_measurements_tenant_id", "growth_measurements", ["tenant_id"])
    op.create_index(
        "ix_growth_measurements_patient_user_id", "growth_measurements", ["patient_user_id"]
    )
    op.create_index("ix_growth_measurements_encounter_id", "growth_measurements", ["encounter_id"])
    op.create_index("ix_growth_measurements_measured_at", "growth_measurements", ["measured_at"])
    op.create_index(
        "ix_growth_measurements_recorded_by_user_id", "growth_measurements", ["recorded_by_user_id"]
    )
    op.create_index(
        "ix_growth_measurements_source_document_id", "growth_measurements", ["source_document_id"]
    )
    op.create_index("ix_growth_patient", "growth_measurements", ["patient_user_id", "measured_at"])
    op.create_index("ix_growth_scope", "growth_measurements", ["tenant_id", "measured_at"])

    op.create_table(
        "immunizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("vaccine_code_system", sa.String(length=128), nullable=False),
        sa.Column("vaccine_code", sa.String(length=64), nullable=False),
        sa.Column("vaccine_display", sa.String(length=255), nullable=False),
        sa.Column(
            "vaccine_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("manufacturer_code_system", sa.String(length=128)),
        sa.Column("manufacturer_code", sa.String(length=64)),
        sa.Column("manufacturer_display", sa.String(length=255)),
        sa.Column(
            "manufacturer_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_reason_code", sa.String(length=64)),
        sa.Column("administered_date", sa.Date(), nullable=False),
        sa.Column(
            "administered_precision", sa.String(length=8), nullable=False, server_default="day"
        ),
        sa.Column("administered_at", sa.DateTime(timezone=True)),
        sa.Column("lot_number", sa.String(length=64)),
        sa.Column("expiration_date", sa.Date()),
        sa.Column("site_code_system", sa.String(length=128)),
        sa.Column("site_code", sa.String(length=64)),
        sa.Column("site_display", sa.String(length=255)),
        sa.Column(
            "site_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("route_code_system", sa.String(length=128)),
        sa.Column("route_code", sa.String(length=64)),
        sa.Column("route_display", sa.String(length=255)),
        sa.Column(
            "route_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("dose_quantity", sa.Numeric(8, 3)),
        sa.Column("dose_unit", sa.String(length=16)),
        sa.Column("series_name", sa.String(length=100)),
        sa.Column("series_dose_number", sa.Integer()),
        sa.Column("series_doses_expected", sa.Integer()),
        sa.Column("funding_source", sa.String(length=32)),
        sa.Column(
            "administered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column(
            "booster_of_immunization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("immunizations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("immunizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.UniqueConstraint("patient_user_id", "vaccine_code", "series_name", "series_dose_number"),
        sa.CheckConstraint(
            "status IN ('completed','not-done','entered-in-error')",
            name="immunization_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="immunization_source",
        ),
        sa.CheckConstraint(
            "series_dose_number IS NULL OR series_dose_number >= 1",
            name="immunization_dose_number",
        ),
        sa.CheckConstraint(
            "status <> 'not-done' OR status_reason_code IS NOT NULL",
            name="immunization_not_done_reason",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR (dose_quantity IS NOT NULL AND dose_unit IS NOT NULL)",
            name="immunization_dose_required",
        ),
        sa.CheckConstraint(
            "administered_precision IN ('day','month','year')",
            name="immunization_date_precision",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="immunization_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="immunization_version_positive"),
    )
    op.create_index("ix_immunizations_tenant_id", "immunizations", ["tenant_id"])
    op.create_index("ix_immunizations_patient_user_id", "immunizations", ["patient_user_id"])
    op.create_index("ix_immunizations_encounter_id", "immunizations", ["encounter_id"])
    op.create_index("ix_immunizations_vaccine_code", "immunizations", ["vaccine_code"])
    op.create_index("ix_immunizations_next_due_at", "immunizations", ["next_due_at"])
    op.create_index(
        "ix_immunizations_recorded_by_user_id", "immunizations", ["recorded_by_user_id"]
    )
    op.create_index("ix_immunizations_source_document_id", "immunizations", ["source_document_id"])
    op.create_index(
        "ix_immunization_patient", "immunizations", ["patient_user_id", "administered_date"]
    )
    op.create_index(
        "ix_immunization_scope", "immunizations", ["tenant_id", "vaccine_code", "administered_date"]
    )
    op.create_index(
        "ix_immunization_due",
        "immunizations",
        ["tenant_id", "next_due_at"],
        postgresql_where=sa.text("next_due_at IS NOT NULL AND status = 'completed'"),
    )

    op.create_table(
        "immunization_certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "immunization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("immunizations.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("certificate_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "issuer_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_hash", sa.String(length=64), nullable=False),
        sa.Column("qr_payload", sa.Text(), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(length=255)),
        sa.Column(
            "superseded_by_certificate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("immunization_certificates.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('active','revoked','superseded')",
            name="certificate_status",
        ),
        sa.CheckConstraint(
            "status <> 'revoked' OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="certificate_revocation",
        ),
    )
    op.create_index(
        "ix_immunization_certificates_tenant_id", "immunization_certificates", ["tenant_id"]
    )
    op.create_index(
        "ix_certificate_scope", "immunization_certificates", ["tenant_id", "status", "issued_at"]
    )

    op.create_table(
        "clinical_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("note_type_code", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_format", sa.String(length=16), nullable=False, server_default="markdown"
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "signed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "cosigner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("cosigned_at", sa.DateTime(timezone=True)),
        sa.Column("signature_hash", sa.String(length=64)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical_notes.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.UniqueConstraint("encounter_id", "note_type_code", "version"),
        sa.CheckConstraint(
            "status IN ('draft','preliminary','final','amended','entered-in-error')",
            name="note_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="note_source",
        ),
        sa.CheckConstraint(
            "content_format IN ('markdown','plain','fhir')",
            name="note_content_format",
        ),
        sa.CheckConstraint(
            "status <> 'final' OR (signed_at IS NOT NULL AND signed_by_user_id IS NOT NULL AND "
            "signature_hash IS NOT NULL)",
            name="final_note_signed",
        ),
        sa.CheckConstraint(
            "(cosigned_at IS NULL) = (cosigner_user_id IS NULL)",
            name="note_cosign_pair",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="note_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="note_version_positive"),
    )
    op.create_index("ix_clinical_notes_tenant_id", "clinical_notes", ["tenant_id"])
    op.create_index("ix_clinical_notes_encounter_id", "clinical_notes", ["encounter_id"])
    op.create_index("ix_clinical_notes_patient_user_id", "clinical_notes", ["patient_user_id"])
    op.create_index("ix_clinical_notes_author_user_id", "clinical_notes", ["author_user_id"])
    op.create_index(
        "ix_clinical_notes_recorded_by_user_id", "clinical_notes", ["recorded_by_user_id"]
    )
    op.create_index(
        "ix_clinical_notes_source_document_id", "clinical_notes", ["source_document_id"]
    )
    op.create_index(
        "ix_note_scope", "clinical_notes", ["tenant_id", "note_type_code", "created_at"]
    )
    op.create_index("ix_note_patient", "clinical_notes", ["patient_user_id", "created_at"])
    op.create_index(
        "ix_note_unsigned",
        "clinical_notes",
        ["tenant_id", "author_user_id"],
        postgresql_where=sa.text("status = 'draft'"),
    )

    op.create_table(
        "clinical_note_addenda",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clinical_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinical_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature_hash", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("clinical_note_id", "sequence"),
    )
    op.create_index(
        "ix_clinical_note_addenda_clinical_note_id", "clinical_note_addenda", ["clinical_note_id"]
    )
    op.create_index(
        "ix_note_addendum_parent", "clinical_note_addenda", ["clinical_note_id", "sequence"]
    )

    op.create_table(
        "encounter_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("billing_code_system", sa.String(length=128), nullable=False),
        sa.Column("billing_code", sa.String(length=64), nullable=False),
        sa.Column("billing_display", sa.String(length=255), nullable=False),
        sa.Column(
            "billing_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("code_type", sa.String(length=16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("modifiers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "coder_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("review_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("encounter_id", "billing_code", "code_type", "rank"),
        sa.CheckConstraint(
            "code_type IN ('diagnosis','procedure','hcpcs')",
            name="encounter_code_code_type",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="encounter_code_source",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','accepted','rejected')",
            name="encounter_code_review_status",
        ),
        sa.CheckConstraint("units >= 1", name="encounter_code_units"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="encounter_code_confidence",
        ),
        sa.CheckConstraint(
            "source <> 'ai-extracted' OR review_status <> 'accepted' OR reviewed_by_user_id IS "
            "NOT NULL",
            name="encounter_code_ai_review",
        ),
    )
    op.create_index("ix_encounter_codes_tenant_id", "encounter_codes", ["tenant_id"])
    op.create_index("ix_encounter_codes_encounter_id", "encounter_codes", ["encounter_id"])
    op.create_index("ix_encounter_codes_billing_code", "encounter_codes", ["billing_code"])
    op.create_index(
        "ix_encounter_code_scope", "encounter_codes", ["tenant_id", "code_type", "review_status"]
    )

    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "referring_provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "referring_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "receiving_provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "receiving_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("specialty_code", sa.String(length=64), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False, server_default="routine"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("prior_authorization_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("feedback_note", sa.Text()),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','sent','accepted','declined','scheduled','completed','expired')",
            name="referral_status",
        ),
        sa.CheckConstraint(
            "urgency IN ('routine','urgent','emergent')",
            name="referral_urgency",
        ),
    )
    op.create_index("ix_referrals_tenant_id", "referrals", ["tenant_id"])
    op.create_index("ix_referrals_patient_user_id", "referrals", ["patient_user_id"])
    op.create_index("ix_referrals_encounter_id", "referrals", ["encounter_id"])
    op.create_index("ix_referral_scope", "referrals", ["tenant_id", "status", "created_at"])
    op.create_index("ix_referral_patient", "referrals", ["patient_user_id", "status"])

    op.create_table(
        "care_team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "member_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date()),
        *timestamps(),
        sa.UniqueConstraint("patient_user_id", "member_user_id", "role_code", "period_start"),
        sa.CheckConstraint(
            "period_end IS NULL OR period_end >= period_start",
            name="care_team_period",
        ),
    )
    op.create_index("ix_care_team_members_tenant_id", "care_team_members", ["tenant_id"])
    op.create_index(
        "ix_care_team_members_patient_user_id", "care_team_members", ["patient_user_id"]
    )
    op.create_index("ix_care_team_members_member_user_id", "care_team_members", ["member_user_id"])
    op.create_index("ix_care_team_patient", "care_team_members", ["patient_user_id", "is_primary"])
    op.create_index("ix_care_team_scope", "care_team_members", ["tenant_id", "role_code"])
    op.create_index(
        "ix_care_team_primary",
        "care_team_members",
        ["patient_user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND period_end IS NULL"),
    )

    op.create_table(
        "family_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relationship_code", sa.String(length=32), nullable=False),
        sa.Column("condition_code_system", sa.String(length=128), nullable=False),
        sa.Column("condition_code", sa.String(length=64), nullable=False),
        sa.Column("condition_display", sa.String(length=255), nullable=False),
        sa.Column(
            "condition_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("onset_age_years", sa.Integer()),
        sa.Column("onset_precision", sa.String(length=8)),
        sa.Column("deceased", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("family_history.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="family_history_source",
        ),
        sa.CheckConstraint(
            "onset_age_years IS NULL OR onset_age_years BETWEEN 0 AND 130",
            name="family_history_age",
        ),
        sa.CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="family_history_precision",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="family_history_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="family_history_version_positive"),
    )
    op.create_index("ix_family_history_tenant_id", "family_history", ["tenant_id"])
    op.create_index("ix_family_history_patient_user_id", "family_history", ["patient_user_id"])
    op.create_index("ix_family_history_condition_code", "family_history", ["condition_code"])
    op.create_index(
        "ix_family_history_recorded_by_user_id", "family_history", ["recorded_by_user_id"]
    )
    op.create_index(
        "ix_family_history_source_document_id", "family_history", ["source_document_id"]
    )
    op.create_index(
        "ix_family_history_patient", "family_history", ["patient_user_id", "condition_code"]
    )
    op.create_index("ix_family_history_scope", "family_history", ["tenant_id", "recorded_at"])

    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "prescriber_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("prescription_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dosing_weight_kg", sa.Numeric(6, 2)),
        sa.Column("dosing_weight_observed_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prescriptions.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','active','completed','cancelled','entered_in_error')",
            name="prescription_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="prescription_source",
        ),
        sa.CheckConstraint(
            "(dosing_weight_kg IS NULL) = (dosing_weight_observed_at IS NULL)",
            name="dosing_weight_pair",
        ),
        sa.CheckConstraint(
            "dosing_weight_kg IS NULL OR dosing_weight_kg > 0",
            name="dosing_weight_positive",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="prescription_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="prescription_version_positive"),
    )
    op.create_index("ix_prescriptions_tenant_id", "prescriptions", ["tenant_id"])
    op.create_index("ix_prescriptions_patient_user_id", "prescriptions", ["patient_user_id"])
    op.create_index("ix_prescriptions_prescriber_user_id", "prescriptions", ["prescriber_user_id"])
    op.create_index("ix_prescriptions_encounter_id", "prescriptions", ["encounter_id"])
    op.create_index("ix_prescriptions_written_at", "prescriptions", ["written_at"])
    op.create_index(
        "ix_prescriptions_recorded_by_user_id", "prescriptions", ["recorded_by_user_id"]
    )
    op.create_index("ix_prescriptions_source_document_id", "prescriptions", ["source_document_id"])
    op.create_index("ix_prescription_scope", "prescriptions", ["tenant_id", "status", "written_at"])
    op.create_index("ix_prescription_patient", "prescriptions", ["patient_user_id", "written_at"])

    op.create_table(
        "medication_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "prescription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prescriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("medication_code_system", sa.String(length=128), nullable=False),
        sa.Column("medication_code", sa.String(length=64), nullable=False),
        sa.Column("medication_display", sa.String(length=255), nullable=False),
        sa.Column(
            "medication_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("medication_term_type", sa.String(length=8), nullable=False),
        sa.Column("ndc_code", sa.String(length=16)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("intent", sa.String(length=32), nullable=False, server_default="order"),
        sa.Column(
            "indication_condition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conditions.id", ondelete="RESTRICT"),
        ),
        sa.Column("substitution_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("quantity", sa.Numeric(12, 3)),
        sa.Column("quantity_unit", sa.String(length=32)),
        sa.Column("days_supply", sa.Integer()),
        sa.Column("refills_allowed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refills_remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("controlled_substance_schedule", sa.String(length=4)),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("stop_reason", sa.String(length=255)),
        sa.Column(
            "stopped_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN "
            "('draft','active','on-hold','stopped','completed','cancelled','entered-in-error')",
            name="med_request_status",
        ),
        sa.CheckConstraint(
            "intent IN ('proposal','plan','order','original-order','instance-order')",
            name="med_request_intent",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="med_request_source",
        ),
        sa.CheckConstraint(
            "medication_term_type IN ('SCD','SBD','GPCK','BPCK')",
            name="rx_term_type",
        ),
        sa.CheckConstraint("refills_allowed >= 0", name="refills_allowed_nonneg"),
        sa.CheckConstraint(
            "refills_remaining >= 0 AND refills_remaining <= refills_allowed",
            name="refills_bounds",
        ),
        sa.CheckConstraint(
            "controlled_substance_schedule IS NULL OR controlled_substance_schedule IN "
            "('CI','CII','CIII','CIV','CV')",
            name="dea_schedule",
        ),
        sa.CheckConstraint(
            "controlled_substance_schedule <> 'CII' OR refills_allowed = 0",
            name="cii_no_refills",
        ),
        sa.CheckConstraint(
            "status <> 'stopped' OR (stopped_at IS NOT NULL AND stop_reason IS NOT NULL)",
            name="med_request_stop_reason",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="med_request_quantity_positive",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="med_request_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="med_request_version_positive"),
    )
    op.create_index("ix_medication_requests_tenant_id", "medication_requests", ["tenant_id"])
    op.create_index(
        "ix_medication_requests_prescription_id", "medication_requests", ["prescription_id"]
    )
    op.create_index(
        "ix_medication_requests_patient_user_id", "medication_requests", ["patient_user_id"]
    )
    op.create_index("ix_medication_requests_encounter_id", "medication_requests", ["encounter_id"])
    op.create_index(
        "ix_medication_requests_medication_code", "medication_requests", ["medication_code"]
    )
    op.create_index(
        "ix_medication_requests_recorded_by_user_id", "medication_requests", ["recorded_by_user_id"]
    )
    op.create_index(
        "ix_medication_requests_source_document_id", "medication_requests", ["source_document_id"]
    )
    op.create_index(
        "ix_med_request_patient",
        "medication_requests",
        ["patient_user_id", "medication_code", "recorded_at"],
    )
    op.create_index(
        "ix_med_request_scope", "medication_requests", ["tenant_id", "status", "recorded_at"]
    )
    op.create_index(
        "ix_med_request_active",
        "medication_requests",
        ["patient_user_id", "medication_code"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "medication_dosage_instructions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "medication_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("dose_quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("dose_unit", sa.String(length=32), nullable=False),
        sa.Column("route_code", sa.String(length=64), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("period", sa.Numeric(8, 2), nullable=False, server_default="1"),
        sa.Column("period_unit", sa.String(length=8), nullable=False, server_default="d"),
        sa.Column("as_needed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("as_needed_reason", sa.String(length=255)),
        sa.Column("max_dose_per_period", sa.Numeric(12, 4)),
        sa.Column("is_chronic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_end_at", sa.DateTime(timezone=True)),
        sa.Column("sig_text", sa.String(length=500), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("medication_request_id", "sequence"),
        sa.CheckConstraint("dose_quantity > 0", name="dosage_positive"),
        sa.CheckConstraint("frequency > 0", name="dosage_frequency_positive"),
        sa.CheckConstraint("period > 0", name="dosage_period_positive"),
        sa.CheckConstraint("period_unit IN ('h','d','wk','mo')", name="dosage_period_unit"),
        sa.CheckConstraint(
            "effective_end_at IS NULL OR effective_end_at >= effective_start_at",
            name="dosage_effective_period",
        ),
        sa.CheckConstraint(
            "is_chronic OR effective_end_at IS NOT NULL",
            name="dosage_course_bounded",
        ),
        sa.CheckConstraint(
            "NOT as_needed OR as_needed_reason IS NOT NULL",
            name="dosage_prn_reason",
        ),
    )
    op.create_index(
        "ix_medication_dosage_instructions_medication_request_id",
        "medication_dosage_instructions",
        ["medication_request_id"],
    )
    op.create_index(
        "ix_dosage_request", "medication_dosage_instructions", ["medication_request_id", "sequence"]
    )

    op.create_table(
        "medication_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "prescription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prescriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "medication_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dosage_instruction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_dosage_instructions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("time_local", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("days_of_week", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date()),
        sa.Column("is_chronic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("total_doses", sa.Integer()),
        sa.Column("doses_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_through", sa.Date()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("channels", postgresql.JSONB(), nullable=False, server_default='["in_app"]'),
        *timestamps(),
        sa.UniqueConstraint("dosage_instruction_id", "time_local"),
        sa.CheckConstraint(
            "status IN ('active','paused','completed','cancelled')",
            name="med_schedule_status",
        ),
        sa.CheckConstraint("is_chronic OR ends_on IS NOT NULL", name="schedule_course_bounded"),
        sa.CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="schedule_period"),
        sa.CheckConstraint("doses_generated >= 0", name="schedule_generated_nonneg"),
        sa.CheckConstraint(
            "total_doses IS NULL OR total_doses > 0",
            name="schedule_total_positive",
        ),
    )
    op.create_index("ix_medication_schedules_tenant_id", "medication_schedules", ["tenant_id"])
    op.create_index(
        "ix_medication_schedules_patient_user_id", "medication_schedules", ["patient_user_id"]
    )
    op.create_index(
        "ix_medication_schedules_prescription_id", "medication_schedules", ["prescription_id"]
    )
    op.create_index(
        "ix_medication_schedules_medication_request_id",
        "medication_schedules",
        ["medication_request_id"],
    )
    op.create_index(
        "ix_medication_schedules_dosage_instruction_id",
        "medication_schedules",
        ["dosage_instruction_id"],
    )
    op.create_index(
        "ix_med_schedule_patient", "medication_schedules", ["patient_user_id", "status"]
    )
    op.create_index(
        "ix_med_schedule_scope", "medication_schedules", ["tenant_id", "status", "ends_on"]
    )
    op.create_index(
        "ix_med_schedule_generation",
        "medication_schedules",
        ["status", "generated_through"],
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "medication_reminder_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_schedules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_local", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="in_app"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portal_notifications.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("schedule_id", "scheduled_at", name="uq_reminder_occurrence"),
        sa.CheckConstraint(
            "channel IN ('in_app','email','sms','push')",
            name="reminder_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','cancelled','suppressed')",
            name="reminder_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="reminder_attempts_nonneg"),
    )
    op.create_index(
        "ix_medication_reminder_occurrences_tenant_id",
        "medication_reminder_occurrences",
        ["tenant_id"],
    )
    op.create_index(
        "ix_medication_reminder_occurrences_schedule_id",
        "medication_reminder_occurrences",
        ["schedule_id"],
    )
    op.create_index(
        "ix_medication_reminder_occurrences_patient_user_id",
        "medication_reminder_occurrences",
        ["patient_user_id"],
    )
    op.create_index(
        "ix_reminder_due",
        "medication_reminder_occurrences",
        ["tenant_id", "status", "scheduled_at"],
    )
    op.create_index(
        "ix_reminder_patient",
        "medication_reminder_occurrences",
        ["patient_user_id", "scheduled_at"],
    )
    op.create_index(
        "ix_reminder_pending",
        "medication_reminder_occurrences",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "medication_adherence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_schedules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "occurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_reminder_occurrences.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "medication_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("taken_at", sa.DateTime(timezone=True)),
        sa.Column("dose_taken_quantity", sa.Numeric(12, 4)),
        sa.Column("dose_unit", sa.String(length=32)),
        sa.Column(
            "reported_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=64)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("occurrence_id", "status", "recorded_at"),
        sa.CheckConstraint(
            "status IN ('taken','not-taken','skipped','snoozed','entered-in-error')",
            name="adherence_status",
        ),
        sa.CheckConstraint(
            "status <> 'taken' OR taken_at IS NOT NULL",
            name="adherence_taken_time",
        ),
        sa.CheckConstraint(
            "dose_taken_quantity IS NULL OR dose_taken_quantity > 0",
            name="adherence_dose_positive",
        ),
    )
    op.create_index(
        "ix_medication_adherence_events_tenant_id", "medication_adherence_events", ["tenant_id"]
    )
    op.create_index(
        "ix_medication_adherence_events_patient_user_id",
        "medication_adherence_events",
        ["patient_user_id"],
    )
    op.create_index(
        "ix_medication_adherence_events_schedule_id", "medication_adherence_events", ["schedule_id"]
    )
    op.create_index(
        "ix_medication_adherence_events_occurrence_id",
        "medication_adherence_events",
        ["occurrence_id"],
    )
    op.create_index(
        "ix_medication_adherence_events_medication_request_id",
        "medication_adherence_events",
        ["medication_request_id"],
    )
    op.create_index(
        "ix_adherence_patient", "medication_adherence_events", ["patient_user_id", "scheduled_at"]
    )
    op.create_index(
        "ix_adherence_scope", "medication_adherence_events", ["tenant_id", "status", "scheduled_at"]
    )

    op.create_table(
        "medication_dispenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "medication_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fill_number", sa.Integer(), nullable=False),
        sa.Column("ndc_code", sa.String(length=16)),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("quantity_unit", sa.String(length=32), nullable=False),
        sa.Column("days_supply", sa.Integer()),
        sa.Column("dispensed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "dispenser_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "dispenser_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("lot_number", sa.String(length=64)),
        sa.Column("note", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("medication_request_id", "fill_number"),
        sa.CheckConstraint("fill_number >= 0", name="dispense_fill_number"),
        sa.CheckConstraint("quantity > 0", name="dispense_quantity_positive"),
    )
    op.create_index("ix_medication_dispenses_tenant_id", "medication_dispenses", ["tenant_id"])
    op.create_index(
        "ix_medication_dispenses_medication_request_id",
        "medication_dispenses",
        ["medication_request_id"],
    )
    op.create_index(
        "ix_medication_dispenses_patient_user_id", "medication_dispenses", ["patient_user_id"]
    )
    op.create_index("ix_dispense_scope", "medication_dispenses", ["tenant_id", "dispensed_at"])

    op.create_table(
        "medication_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("medication_code_system", sa.String(length=128), nullable=False),
        sa.Column("medication_code", sa.String(length=64), nullable=False),
        sa.Column("medication_display", sa.String(length=255), nullable=False),
        sa.Column(
            "medication_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("medication_term_type", sa.String(length=8)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sig_text", sa.String(length=500)),
        sa.Column("effective_start_at", sa.DateTime(timezone=True)),
        sa.Column("effective_end_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_statements.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('active','completed','not-taken','intended','stopped','entered-in-error')",
            name="med_statement_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="med_statement_source",
        ),
        sa.CheckConstraint(
            "medication_term_type IS NULL OR medication_term_type IN "
            "('IN','PIN','SCD','SBD','GPCK','BPCK')",
            name="statement_term_type",
        ),
        sa.CheckConstraint(
            "effective_end_at IS NULL OR effective_start_at IS NULL OR effective_end_at >= "
            "effective_start_at",
            name="statement_period",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="med_statement_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="med_statement_version_positive"),
    )
    op.create_index("ix_medication_statements_tenant_id", "medication_statements", ["tenant_id"])
    op.create_index(
        "ix_medication_statements_patient_user_id", "medication_statements", ["patient_user_id"]
    )
    op.create_index(
        "ix_medication_statements_encounter_id", "medication_statements", ["encounter_id"]
    )
    op.create_index(
        "ix_medication_statements_medication_code", "medication_statements", ["medication_code"]
    )
    op.create_index(
        "ix_medication_statements_recorded_by_user_id",
        "medication_statements",
        ["recorded_by_user_id"],
    )
    op.create_index(
        "ix_medication_statements_source_document_id",
        "medication_statements",
        ["source_document_id"],
    )
    op.create_index(
        "ix_med_statement_patient",
        "medication_statements",
        ["patient_user_id", "status", "recorded_at"],
    )
    op.create_index("ix_med_statement_scope", "medication_statements", ["tenant_id", "recorded_at"])

    op.create_table(
        "prescription_safety_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "prescription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prescriptions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "medication_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("medication_requests.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("check_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("triggered_by_code_system", sa.String(length=128)),
        sa.Column("triggered_by_code", sa.String(length=64)),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column(
            "overridden_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("override_reason", sa.String(length=500)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "check_type IN "
            "('drug_allergy','drug_drug','duplicate_therapy','dose_range','drug_condition')",
            name="safety_check_check_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('no_alert','alerted','overridden')",
            name="safety_check_outcome",
        ),
        sa.CheckConstraint(
            "severity IN ('none','low','moderate','high','contraindicated')",
            name="safety_check_severity",
        ),
        sa.CheckConstraint(
            "outcome <> 'overridden' OR (override_reason IS NOT NULL AND overridden_by_user_id "
            "IS NOT NULL)",
            name="override_requires_reason",
        ),
    )
    op.create_index(
        "ix_prescription_safety_checks_tenant_id", "prescription_safety_checks", ["tenant_id"]
    )
    op.create_index(
        "ix_prescription_safety_checks_prescription_id",
        "prescription_safety_checks",
        ["prescription_id"],
    )
    op.create_index(
        "ix_prescription_safety_checks_medication_request_id",
        "prescription_safety_checks",
        ["medication_request_id"],
    )
    op.create_index(
        "ix_prescription_safety_checks_patient_user_id",
        "prescription_safety_checks",
        ["patient_user_id"],
    )
    op.create_index(
        "ix_safety_check_prescription",
        "prescription_safety_checks",
        ["prescription_id", "check_type"],
    )
    op.create_index(
        "ix_safety_check_scope",
        "prescription_safety_checks",
        ["tenant_id", "outcome", "created_at"],
    )

    op.create_table(
        "lab_facilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address_line1", sa.String(length=255)),
        sa.Column("address_line2", sa.String(length=255)),
        sa.Column("city", sa.String(length=100)),
        sa.Column("region", sa.String(length=100)),
        sa.Column("postal_code", sa.String(length=20)),
        sa.Column("country", sa.String(length=2)),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column(
            "home_collection_available", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
    )
    op.create_index("ix_lab_facilities_tenant_id", "lab_facilities", ["tenant_id"])
    op.create_index("ix_lab_facilities_organization_id", "lab_facilities", ["organization_id"])
    op.create_index("ix_lab_facility_scope", "lab_facilities", ["tenant_id", "is_active"])
    op.create_index("ix_lab_facility_geo", "lab_facilities", ["latitude", "longitude"])

    op.create_table(
        "lab_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_code_system", sa.String(length=128), nullable=False),
        sa.Column("test_code", sa.String(length=64), nullable=False),
        sa.Column("test_display", sa.String(length=255), nullable=False),
        sa.Column(
            "test_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("panel_code_system", sa.String(length=128)),
        sa.Column("panel_code", sa.String(length=64)),
        sa.Column("panel_display", sa.String(length=255)),
        sa.Column(
            "panel_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("specimen_type_code_system", sa.String(length=128)),
        sa.Column("specimen_type_code", sa.String(length=64)),
        sa.Column("specimen_type_display", sa.String(length=255)),
        sa.Column(
            "specimen_type_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("container", sa.String(length=64)),
        sa.Column("prep_instructions", sa.Text()),
        sa.Column("fasting_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("turnaround_hours", sa.Integer()),
        sa.Column("price_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3)),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="RESTRICT"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("tenant_id", "test_code", "test_code_system"),
        sa.CheckConstraint(
            "price_cents IS NULL OR price_cents >= 0",
            name="lab_test_price_nonneg",
        ),
        sa.CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="lab_test_currency_required",
        ),
    )
    op.create_index("ix_lab_tests_tenant_id", "lab_tests", ["tenant_id"])
    op.create_index("ix_lab_tests_test_code", "lab_tests", ["test_code"])
    op.create_index("ix_lab_test_scope", "lab_tests", ["tenant_id", "test_code", "is_active"])

    op.create_table(
        "lab_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_facilities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        *timestamps(),
        sa.UniqueConstraint("facility_id", "start_at"),
        sa.CheckConstraint(
            "status IN ('open','held','booked','blocked','cancelled')",
            name="lab_slot_status",
        ),
        sa.CheckConstraint("end_at > start_at", name="lab_slot_period"),
        sa.CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="lab_slot_capacity_bounds",
        ),
    )
    op.create_index("ix_lab_slots_tenant_id", "lab_slots", ["tenant_id"])
    op.create_index("ix_lab_slots_facility_id", "lab_slots", ["facility_id"])
    op.create_index("ix_lab_slots_start_at", "lab_slots", ["start_at"])
    op.create_index("ix_lab_slot_scope", "lab_slots", ["tenant_id", "start_at", "status"])
    op.create_index(
        "ix_lab_slot_open",
        "lab_slots",
        ["tenant_id", "start_at"],
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "lab_slot_tests",
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_slots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "lab_test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_tests.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents_override", sa.Integer()),
        *timestamps(),
        sa.CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="lab_slot_test_capacity_bounds",
        ),
        sa.CheckConstraint(
            "price_cents_override IS NULL OR price_cents_override >= 0",
            name="lab_slot_test_price_nonneg",
        ),
    )
    op.create_index("ix_lab_slot_test_lookup", "lab_slot_tests", ["lab_test_id", "slot_id"])

    op.create_table(
        "lab_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ordering_provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "facility_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_facilities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_slots.id", ondelete="RESTRICT"),
        ),
        sa.Column("order_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="routine"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "priority IN ('routine','urgent','stat')",
            name="lab_order_priority",
        ),
        sa.CheckConstraint(
            "status IN "
            "('draft','placed','collected','in_process','resulted','cancelled','entered_in_error')",
            name="lab_order_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="lab_order_source",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="lab_order_confidence_range",
        ),
    )
    op.create_index("ix_lab_orders_tenant_id", "lab_orders", ["tenant_id"])
    op.create_index("ix_lab_orders_patient_user_id", "lab_orders", ["patient_user_id"])
    op.create_index(
        "ix_lab_orders_ordering_provider_user_id", "lab_orders", ["ordering_provider_user_id"]
    )
    op.create_index("ix_lab_orders_encounter_id", "lab_orders", ["encounter_id"])
    op.create_index("ix_lab_orders_slot_id", "lab_orders", ["slot_id"])
    op.create_index("ix_lab_orders_recorded_by_user_id", "lab_orders", ["recorded_by_user_id"])
    op.create_index("ix_lab_orders_source_document_id", "lab_orders", ["source_document_id"])
    op.create_index("ix_lab_order_scope", "lab_orders", ["tenant_id", "status", "requested_at"])
    op.create_index("ix_lab_order_patient", "lab_orders", ["patient_user_id", "status"])

    op.create_table(
        "lab_order_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lab_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lab_test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_tests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="placed"),
        sa.Column("price_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3)),
        *timestamps(),
        sa.UniqueConstraint("lab_order_id", "lab_test_id"),
        sa.CheckConstraint(
            "status IN "
            "('draft','placed','collected','in_process','resulted','cancelled','entered_in_error')",
            name="lab_order_test_status",
        ),
        sa.CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="lab_order_test_currency_required",
        ),
    )
    op.create_index("ix_lab_order_tests_lab_order_id", "lab_order_tests", ["lab_order_id"])
    op.create_index("ix_lab_order_tests_lab_test_id", "lab_order_tests", ["lab_test_id"])

    op.create_table(
        "specimens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "lab_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accession_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("specimen_type_code_system", sa.String(length=128), nullable=False),
        sa.Column("specimen_type_code", sa.String(length=64), nullable=False),
        sa.Column("specimen_type_display", sa.String(length=255), nullable=False),
        sa.Column(
            "specimen_type_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "collected_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("condition", sa.String(length=64)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_reason", sa.String(length=255)),
        *timestamps(),
    )
    op.create_index("ix_specimens_tenant_id", "specimens", ["tenant_id"])
    op.create_index("ix_specimens_lab_order_id", "specimens", ["lab_order_id"])
    op.create_index("ix_specimens_patient_user_id", "specimens", ["patient_user_id"])
    op.create_index("ix_specimens_specimen_type_code", "specimens", ["specimen_type_code"])
    op.create_index("ix_specimen_scope", "specimens", ["tenant_id", "collected_at"])

    op.create_table(
        "lab_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "lab_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_orders.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "lab_test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_tests.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "specimen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("specimens.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column("test_code_system", sa.String(length=128), nullable=False),
        sa.Column("test_code", sa.String(length=64), nullable=False),
        sa.Column("test_display", sa.String(length=255), nullable=False),
        sa.Column(
            "test_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("panel_code_system", sa.String(length=128)),
        sa.Column("panel_code", sa.String(length=64)),
        sa.Column("panel_display", sa.String(length=255)),
        sa.Column(
            "panel_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "parent_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_results.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("value_numeric", sa.Numeric(14, 4)),
        sa.Column("value_string", sa.String(length=255)),
        sa.Column("value_code_system", sa.String(length=128)),
        sa.Column("value_code", sa.String(length=64)),
        sa.Column("value_display", sa.String(length=255)),
        sa.Column(
            "value_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("value_boolean", sa.Boolean()),
        sa.Column("value_comparator", sa.String(length=2)),
        sa.Column("unit", sa.String(length=32)),
        sa.Column("data_absent_reason", sa.String(length=32)),
        sa.Column("interpretation_code", sa.String(length=8)),
        sa.Column("reference_range_low", sa.Numeric(14, 4)),
        sa.Column("reference_range_high", sa.Numeric(14, 4)),
        sa.Column("reference_range_text", sa.String(length=255)),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("critical_notified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "notified_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "acknowledged_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledgement_note", sa.String(length=500)),
        sa.Column(
            "performer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "asserter_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("extraction_confidence", sa.Numeric(4, 3)),
        sa.Column(
            "human_verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("human_verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_results.id", ondelete="RESTRICT"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("amendment_reason", sa.String(length=500)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN "
            "('registered','preliminary','final','amended','corrected','cancelled','entered-in-error')",
            name="lab_result_status",
        ),
        sa.CheckConstraint(
            "source IN ('patient-reported','practitioner','device','imported','ai-extracted')",
            name="lab_result_source",
        ),
        sa.CheckConstraint(
            "(value_numeric IS NOT NULL)::int + (value_string IS NOT NULL)::int + (value_code "
            "IS NOT NULL)::int + (value_boolean IS NOT NULL)::int + (data_absent_reason IS NOT "
            "NULL)::int = 1",
            name="lab_result_single_value",
        ),
        sa.CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="lab_result_unit_required",
        ),
        sa.CheckConstraint(
            "value_comparator IS NULL OR value_comparator IN ('<','<=','>','>=')",
            name="lab_result_comparator",
        ),
        sa.CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="lab_result_interpretation",
        ),
        sa.CheckConstraint(
            "status NOT IN ('final','amended','corrected') OR verified_by_user_id IS NOT NULL",
            name="lab_result_verified",
        ),
        sa.CheckConstraint(
            "(acknowledged_at IS NULL) = (acknowledged_by_user_id IS NULL)",
            name="lab_result_ack_pair",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="lab_result_confidence_range",
        ),
        sa.CheckConstraint("version >= 1", name="lab_result_version_positive"),
    )
    op.create_index("ix_lab_results_tenant_id", "lab_results", ["tenant_id"])
    op.create_index("ix_lab_results_lab_order_id", "lab_results", ["lab_order_id"])
    op.create_index("ix_lab_results_lab_test_id", "lab_results", ["lab_test_id"])
    op.create_index("ix_lab_results_patient_user_id", "lab_results", ["patient_user_id"])
    op.create_index("ix_lab_results_encounter_id", "lab_results", ["encounter_id"])
    op.create_index("ix_lab_results_test_code", "lab_results", ["test_code"])
    op.create_index("ix_lab_results_parent_result_id", "lab_results", ["parent_result_id"])
    op.create_index("ix_lab_results_interpretation_code", "lab_results", ["interpretation_code"])
    op.create_index("ix_lab_results_effective_at", "lab_results", ["effective_at"])
    op.create_index("ix_lab_results_recorded_by_user_id", "lab_results", ["recorded_by_user_id"])
    op.create_index("ix_lab_results_source_document_id", "lab_results", ["source_document_id"])
    op.create_index(
        "ix_lab_result_patient_trend",
        "lab_results",
        ["patient_user_id", "test_code", "effective_at"],
    )
    op.create_index("ix_lab_result_scope", "lab_results", ["tenant_id", "status", "effective_at"])
    op.create_index(
        "ix_lab_result_unacked",
        "lab_results",
        ["tenant_id", "effective_at"],
        postgresql_where=sa.text("is_critical AND acknowledged_at IS NULL"),
    )
    op.create_index(
        "ix_lab_result_current",
        "lab_results",
        ["patient_user_id", "effective_at"],
        postgresql_where=sa.text("superseded_at IS NULL AND status <> 'entered-in-error'"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "lab_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lab_orders.id", ondelete="RESTRICT"),
        ),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','issued','paid','void','refunded')",
            name="invoice_status",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="invoice_currency_iso4217"),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="invoice_amounts_nonneg",
        ),
        sa.CheckConstraint(
            "total_cents = subtotal_cents + tax_cents",
            name="invoice_total_consistent",
        ),
        sa.CheckConstraint(
            "status <> 'issued' OR issued_at IS NOT NULL",
            name="invoice_issued_at",
        ),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"])
    op.create_index("ix_invoices_payer_user_id", "invoices", ["payer_user_id"])
    op.create_index("ix_invoices_patient_user_id", "invoices", ["patient_user_id"])
    op.create_index("ix_invoices_appointment_id", "invoices", ["appointment_id"])
    op.create_index("ix_invoices_lab_order_id", "invoices", ["lab_order_id"])
    op.create_index("ix_invoice_scope", "invoices", ["tenant_id", "status", "issued_at"])
    op.create_index("ix_invoice_patient", "invoices", ["patient_user_id", "status"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_items.id", ondelete="RESTRICT"),
        ),
        sa.Column("service_code_system", sa.String(length=128)),
        sa.Column("service_code", sa.String(length=64)),
        sa.Column("service_display", sa.String(length=255)),
        sa.Column(
            "service_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("invoice_id", "line_number"),
        sa.CheckConstraint("quantity > 0", name="invoice_line_quantity_positive"),
        sa.CheckConstraint(
            "unit_price_cents >= 0 AND amount_cents >= 0",
            name="invoice_line_amounts_nonneg",
        ),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("processor", sa.String(length=32), nullable=False),
        sa.Column("processor_intent_id", sa.String(length=255)),
        sa.Column("processor_charge_id", sa.String(length=255)),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True)),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=100)),
        *timestamps(),
        sa.UniqueConstraint("processor", "processor_intent_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
        sa.CheckConstraint(
            "method IN ('card','wallet','bank','cash','loyalty')",
            name="payment_method",
        ),
        sa.CheckConstraint(
            "status IN ('requires_action','authorized','captured','failed','refunded')",
            name="payment_status",
        ),
        sa.CheckConstraint("amount_cents > 0", name="payment_amount_positive"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="payment_currency_iso4217"),
        sa.CheckConstraint(
            "status <> 'captured' OR captured_at IS NOT NULL",
            name="payment_captured_at",
        ),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_appointment_id", "payments", ["appointment_id"])
    op.create_index("ix_payments_payer_user_id", "payments", ["payer_user_id"])
    op.create_index("ix_payment_scope", "payments", ["tenant_id", "status", "created_at"])

    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("processor_refund_id", sa.String(length=255)),
        sa.Column("refunded_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("status IN ('pending','succeeded','failed')", name="refund_status"),
        sa.CheckConstraint("amount_cents > 0", name="refund_amount_positive"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="refund_currency_iso4217"),
    )
    op.create_index("ix_refunds_tenant_id", "refunds", ["tenant_id"])
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index("ix_refund_scope", "refunds", ["tenant_id", "status", "created_at"])

    op.create_table(
        "loyalty_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("program", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("balance_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tier", sa.String(length=32)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        *timestamps(),
        sa.CheckConstraint("balance_points >= 0", name="loyalty_balance_nonneg"),
        sa.CheckConstraint("lifetime_points >= 0", name="loyalty_lifetime_nonneg"),
    )
    op.create_index("ix_loyalty_accounts_tenant_id", "loyalty_accounts", ["tenant_id"])
    op.create_index("ix_loyalty_account_scope", "loyalty_accounts", ["tenant_id", "tier"])

    op.create_table(
        "loyalty_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("loyalty_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("account_id", "reference_type", "reference_id", "entry_type"),
        sa.CheckConstraint(
            "entry_type IN ('accrual','redemption','expiry','adjustment')",
            name="loyalty_ledger_entry_type",
        ),
        sa.CheckConstraint("balance_after >= 0", name="loyalty_ledger_balance_nonneg"),
        sa.CheckConstraint(
            "(entry_type IN ('accrual','adjustment')) OR points <= 0",
            name="loyalty_ledger_sign",
        ),
    )
    op.create_index("ix_loyalty_ledger_tenant_id", "loyalty_ledger", ["tenant_id"])
    op.create_index("ix_loyalty_ledger_account_id", "loyalty_ledger", ["account_id"])
    op.create_index("ix_loyalty_ledger_account", "loyalty_ledger", ["account_id", "occurred_at"])

    op.create_table(
        "insurance_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payer_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("product_type", sa.String(length=16), nullable=False),
        sa.Column("network_name", sa.String(length=255)),
        sa.Column("filing_id", sa.String(length=64)),
        sa.Column("regulator_approval_id", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("payer_organization_id", "code"),
        sa.CheckConstraint(
            "product_type IN ('hmo','ppo','epo','pos','indemnity')",
            name="insurance_product_type",
        ),
    )
    op.create_index("ix_insurance_products_tenant_id", "insurance_products", ["tenant_id"])
    op.create_index(
        "ix_insurance_products_payer_organization_id",
        "insurance_products",
        ["payer_organization_id"],
    )
    op.create_index("ix_insurance_product_scope", "insurance_products", ["tenant_id", "is_active"])

    op.create_table(
        "insurance_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("insurance_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("metal_tier", sa.String(length=16)),
        sa.Column("premium_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("individual_deductible_cents", sa.Integer()),
        sa.Column("family_deductible_cents", sa.Integer()),
        sa.Column("individual_oop_max_cents", sa.Integer()),
        sa.Column("family_oop_max_cents", sa.Integer()),
        sa.Column("term_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("eligibility_rules", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("product_id", "plan_code", "effective_from"),
        sa.CheckConstraint("premium_cents >= 0", name="plan_premium_nonneg"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="plan_currency_iso4217"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="plan_effective_period",
        ),
    )
    op.create_index("ix_insurance_plans_tenant_id", "insurance_plans", ["tenant_id"])
    op.create_index("ix_insurance_plans_product_id", "insurance_plans", ["product_id"])
    op.create_index(
        "ix_insurance_plan_scope", "insurance_plans", ["tenant_id", "is_active", "premium_cents"]
    )

    op.create_table(
        "plan_benefits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("insurance_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service_category", sa.String(length=64), nullable=False),
        sa.Column("service_code_system", sa.String(length=128)),
        sa.Column("service_code", sa.String(length=64)),
        sa.Column("service_display", sa.String(length=255)),
        sa.Column(
            "service_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "network_tier", sa.String(length=32), nullable=False, server_default="in_network"
        ),
        sa.Column("covered", sa.Boolean(), nullable=False),
        sa.Column("copay_cents", sa.Integer()),
        sa.Column("coinsurance_percent", sa.Numeric(5, 2)),
        sa.Column("deductible_applies", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("visit_limit_count", sa.Integer()),
        sa.Column("limit_period", sa.String(length=16)),
        sa.Column("prior_auth_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("waiting_period_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exclusion_text", sa.Text()),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        *timestamps(),
        sa.UniqueConstraint(
            "plan_id", "service_category", "service_code", "network_tier", "effective_from"
        ),
        sa.CheckConstraint(
            "network_tier IN ('in_network','out_of_network')",
            name="benefit_network_tier",
        ),
        sa.CheckConstraint(
            "limit_period IN ('per_year','per_visit','lifetime')",
            name="benefit_limit_period",
        ),
        sa.CheckConstraint(
            "coinsurance_percent IS NULL OR (coinsurance_percent >= 0 AND coinsurance_percent "
            "<= 100)",
            name="benefit_coinsurance_range",
        ),
        sa.CheckConstraint(
            "copay_cents IS NULL OR copay_cents >= 0",
            name="benefit_copay_nonneg",
        ),
        sa.CheckConstraint(
            "(visit_limit_count IS NULL) = (limit_period IS NULL)",
            name="benefit_limit_pair",
        ),
    )
    op.create_index("ix_plan_benefits_tenant_id", "plan_benefits", ["tenant_id"])
    op.create_index("ix_plan_benefits_plan_id", "plan_benefits", ["plan_id"])
    op.create_index(
        "ix_plan_benefit_lookup", "plan_benefits", ["plan_id", "service_category", "network_tier"]
    )

    op.create_table(
        "benefit_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_benefit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plan_benefits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="en-US"),
        sa.Column("reading_level", sa.String(length=16), nullable=False, server_default="grade6"),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("example_scenario", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "source_document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("generated_by", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64)),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("plan_benefit_id", "locale", "reading_level"),
        sa.CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by_user_id IS NULL)",
            name="benefit_explanation_review_pair",
        ),
    )
    op.create_index("ix_benefit_explanations_tenant_id", "benefit_explanations", ["tenant_id"])
    op.create_index(
        "ix_benefit_explanations_plan_benefit_id", "benefit_explanations", ["plan_benefit_id"]
    )
    op.create_index("ix_benefit_explanation_scope", "benefit_explanations", ["tenant_id", "locale"])

    op.create_table(
        "plan_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("insurance_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(6, 4), nullable=False),
        sa.Column("history_score", sa.Numeric(6, 4), nullable=False),
        sa.Column("loyalty_score", sa.Numeric(6, 4), nullable=False),
        sa.Column("loyalty_points_applied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_premium_cents", sa.Integer()),
        sa.Column("estimated_annual_cost_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3)),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("feature_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("patient_user_id", "plan_id", "generated_at"),
        sa.CheckConstraint("rank >= 1", name="recommendation_rank"),
        sa.CheckConstraint(
            "score >= 0 AND history_score >= 0 AND loyalty_score >= 0",
            name="recommendation_scores_nonneg",
        ),
        sa.CheckConstraint("loyalty_points_applied >= 0", name="recommendation_points_nonneg"),
    )
    op.create_index("ix_plan_recommendations_tenant_id", "plan_recommendations", ["tenant_id"])
    op.create_index(
        "ix_plan_recommendations_patient_user_id", "plan_recommendations", ["patient_user_id"]
    )
    op.create_index("ix_plan_recommendations_plan_id", "plan_recommendations", ["plan_id"])
    op.create_index(
        "ix_recommendation_patient",
        "plan_recommendations",
        ["patient_user_id", "generated_at", "rank"],
    )
    op.create_index(
        "ix_recommendation_scope", "plan_recommendations", ["tenant_id", "generated_at"]
    )

    op.create_table(
        "policy_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "applicant_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("insurance_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("application_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("decision_at", sa.DateTime(timezone=True)),
        sa.Column("decline_reason", sa.String(length=255)),
        sa.Column("quoted_premium_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3)),
        sa.Column("loyalty_points_redeemed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
        ),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
        sa.CheckConstraint(
            "status IN "
            "('draft','submitted','underwriting','approved','declined','withdrawn','issued')",
            name="application_status",
        ),
        sa.CheckConstraint(
            "status <> 'declined' OR decline_reason IS NOT NULL",
            name="application_decline_reason",
        ),
        sa.CheckConstraint(
            "status <> 'submitted' OR submitted_at IS NOT NULL",
            name="application_submitted_at",
        ),
        sa.CheckConstraint("loyalty_points_redeemed >= 0", name="application_points_nonneg"),
    )
    op.create_index("ix_policy_applications_tenant_id", "policy_applications", ["tenant_id"])
    op.create_index(
        "ix_policy_applications_applicant_user_id", "policy_applications", ["applicant_user_id"]
    )
    op.create_index("ix_policy_applications_plan_id", "policy_applications", ["plan_id"])
    op.create_index(
        "ix_policy_application_scope",
        "policy_applications",
        ["tenant_id", "status", "submitted_at"],
    )

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("insurance_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_applications.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column(
            "subscriber_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column(
            "payer_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("premium_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "premium_frequency", sa.String(length=16), nullable=False, server_default="monthly"
        ),
        sa.Column(
            "policy_document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        *timestamps(),
        sa.UniqueConstraint("plan_id", "member_id"),
        sa.CheckConstraint(
            "status IN ('pending','active','lapsed','cancelled','terminated')",
            name="policy_status",
        ),
        sa.CheckConstraint(
            "premium_frequency IN ('monthly','quarterly','annual')",
            name="policy_premium_frequency",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="policy_effective_period",
        ),
        sa.CheckConstraint("premium_cents >= 0", name="policy_premium_nonneg"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="policy_currency_iso4217"),
    )
    op.create_index("ix_policies_tenant_id", "policies", ["tenant_id"])
    op.create_index("ix_policies_plan_id", "policies", ["plan_id"])
    op.create_index("ix_policies_subscriber_user_id", "policies", ["subscriber_user_id"])
    op.create_index(
        "ix_policies_active",
        "policies",
        ["tenant_id", "subscriber_user_id", "status", "effective_from"],
    )

    op.create_table(
        "policy_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("member_suffix", sa.String(length=8)),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        *timestamps(),
        sa.UniqueConstraint("policy_id", "patient_user_id", "effective_from"),
        sa.CheckConstraint(
            "relationship IN ('self','spouse','child','other')",
            name="policy_member_relationship",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="policy_member_period",
        ),
    )
    op.create_index("ix_policy_members_tenant_id", "policy_members", ["tenant_id"])
    op.create_index("ix_policy_members_policy_id", "policy_members", ["policy_id"])
    op.create_index("ix_policy_members_patient_user_id", "policy_members", ["patient_user_id"])
    op.create_index("ix_policy_member_patient", "policy_members", ["patient_user_id", "policy_id"])

    op.create_table(
        "premium_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="due"),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("policy_id", "due_date"),
        sa.CheckConstraint(
            "status IN ('due','paid','overdue','waived')",
            name="premium_schedule_status",
        ),
        sa.CheckConstraint("amount_cents >= 0", name="premium_amount_nonneg"),
    )
    op.create_index("ix_premium_schedules_tenant_id", "premium_schedules", ["tenant_id"])
    op.create_index("ix_premium_schedules_policy_id", "premium_schedules", ["policy_id"])
    op.create_index(
        "ix_premium_schedule_due", "premium_schedules", ["tenant_id", "status", "due_date"]
    )

    op.create_table(
        "beneficiaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("share_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("contact", sa.String(length=255)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.CheckConstraint(
            "relationship IN ('self','spouse','child','other')",
            name="beneficiary_relationship",
        ),
        sa.CheckConstraint(
            "share_percent > 0 AND share_percent <= 100",
            name="beneficiary_share_range",
        ),
    )
    op.create_index("ix_beneficiaries_tenant_id", "beneficiaries", ["tenant_id"])
    op.create_index("ix_beneficiaries_policy_id", "beneficiaries", ["policy_id"])
    op.create_index("ix_beneficiary_policy", "beneficiaries", ["policy_id", "is_primary"])

    op.create_table(
        "benefit_accumulators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accumulator_type", sa.String(length=40), nullable=False),
        sa.Column("benefit_year", sa.Integer(), nullable=False),
        sa.Column("limit_cents", sa.Integer()),
        sa.Column("consumed_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("limit_count", sa.Integer()),
        sa.Column("consumed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "as_of", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        *timestamps(),
        sa.UniqueConstraint("policy_id", "patient_user_id", "accumulator_type", "benefit_year"),
        sa.CheckConstraint(
            "accumulator_type IN "
            "('individual_deductible','family_deductible','individual_oop','family_oop','visit_limit')",
            name="accumulator_accumulator_type",
        ),
        sa.CheckConstraint(
            "consumed_cents >= 0 AND consumed_count >= 0",
            name="accumulator_nonneg",
        ),
        sa.CheckConstraint(
            "limit_cents IS NULL OR consumed_cents <= limit_cents",
            name="accumulator_within_limit",
        ),
    )
    op.create_index("ix_benefit_accumulators_tenant_id", "benefit_accumulators", ["tenant_id"])
    op.create_index("ix_benefit_accumulators_policy_id", "benefit_accumulators", ["policy_id"])
    op.create_index(
        "ix_benefit_accumulators_patient_user_id", "benefit_accumulators", ["patient_user_id"]
    )
    op.create_index("ix_accumulator_lookup", "benefit_accumulators", ["policy_id", "benefit_year"])

    op.create_table(
        "eligibility_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "payer_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("service_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("coverage_found", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active_from", sa.Date()),
        sa.Column("active_to", sa.Date()),
        sa.Column("benefits_returned", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_request", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_response", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("transaction_id", sa.String(length=64)),
        sa.Column("cached_until", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','active','inactive','error')",
            name="eligibility_status",
        ),
    )
    op.create_index("ix_eligibility_checks_tenant_id", "eligibility_checks", ["tenant_id"])
    op.create_index(
        "ix_eligibility_checks_patient_user_id", "eligibility_checks", ["patient_user_id"]
    )
    op.create_index("ix_eligibility_lookup", "eligibility_checks", ["member_id", "service_date"])
    op.create_index(
        "ix_eligibility_scope", "eligibility_checks", ["tenant_id", "status", "created_at"]
    )

    op.create_table(
        "prior_authorizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requesting_provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("service_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("diagnosis_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("units_requested", sa.Integer()),
        sa.Column("units_approved", sa.Integer()),
        sa.Column("clinical_justification", sa.Text()),
        sa.Column("criteria_met", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("decision_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.String(length=500)),
        sa.Column("authorization_number", sa.String(length=64), unique=True),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        *timestamps(),
        sa.CheckConstraint(
            "status IN "
            "('draft','submitted','pended','approved','partially_approved','denied','appealed','expired')",
            name="prior_auth_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('denied','partially_approved') OR decision_reason IS NOT NULL",
            name="prior_auth_decision_reason",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR authorization_number IS NOT NULL",
            name="prior_auth_number_required",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="prior_auth_period",
        ),
        sa.CheckConstraint(
            "units_approved IS NULL OR units_requested IS NULL OR units_approved <= "
            "units_requested",
            name="prior_auth_units_bounds",
        ),
    )
    op.create_index("ix_prior_authorizations_tenant_id", "prior_authorizations", ["tenant_id"])
    op.create_index("ix_prior_authorizations_policy_id", "prior_authorizations", ["policy_id"])
    op.create_index(
        "ix_prior_authorizations_patient_user_id", "prior_authorizations", ["patient_user_id"]
    )
    op.create_index(
        "ix_prior_auth_scope", "prior_authorizations", ["tenant_id", "status", "created_at"]
    )
    op.create_index("ix_prior_auth_patient", "prior_authorizations", ["patient_user_id", "status"])

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscriber_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "billing_provider_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rendering_provider_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "encounter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("encounters.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "prior_authorization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prior_authorizations.id", ondelete="RESTRICT"),
        ),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("service_from", sa.Date(), nullable=False),
        sa.Column("service_to", sa.Date(), nullable=False),
        sa.Column("total_charge_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allowed_cents", sa.Integer()),
        sa.Column("paid_cents", sa.Integer()),
        sa.Column("patient_responsibility_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("adjudicated_at", sa.DateTime(timezone=True)),
        sa.Column("denial_reason_code", sa.String(length=32)),
        *timestamps(),
        sa.CheckConstraint(
            "claim_type IN ('professional','institutional','dental','pharmacy')",
            name="claim_claim_type",
        ),
        sa.CheckConstraint(
            "status IN "
            "('draft','submitted','accepted','pended','adjudicated','paid','denied','appealed')",
            name="claim_status",
        ),
        sa.CheckConstraint("service_to >= service_from", name="claim_service_period"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="claim_currency_iso4217"),
        sa.CheckConstraint("total_charge_cents >= 0", name="claim_charge_nonneg"),
        sa.CheckConstraint(
            "status <> 'denied' OR denial_reason_code IS NOT NULL",
            name="claim_denial_reason",
        ),
    )
    op.create_index("ix_claims_tenant_id", "claims", ["tenant_id"])
    op.create_index("ix_claims_policy_id", "claims", ["policy_id"])
    op.create_index("ix_claims_patient_user_id", "claims", ["patient_user_id"])
    op.create_index("ix_claims_encounter_id", "claims", ["encounter_id"])
    op.create_index("ix_claim_scope", "claims", ["tenant_id", "status", "submitted_at"])
    op.create_index("ix_claim_patient", "claims", ["patient_user_id", "status"])

    op.create_table(
        "claim_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("service_code_system", sa.String(length=128), nullable=False),
        sa.Column("service_code", sa.String(length=64), nullable=False),
        sa.Column("service_display", sa.String(length=255), nullable=False),
        sa.Column(
            "service_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("code_concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("modifiers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("units", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("charge_cents", sa.Integer(), nullable=False),
        sa.Column("allowed_cents", sa.Integer()),
        sa.Column("paid_cents", sa.Integer()),
        sa.Column("copay_cents", sa.Integer()),
        sa.Column("coinsurance_cents", sa.Integer()),
        sa.Column("deductible_cents", sa.Integer()),
        sa.Column("diagnosis_pointers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "adjustment_reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        *timestamps(),
        sa.UniqueConstraint("claim_id", "line_number"),
        sa.CheckConstraint("units > 0", name="claim_line_units_positive"),
        sa.CheckConstraint("charge_cents >= 0", name="claim_line_charge_nonneg"),
    )
    op.create_index("ix_claim_lines_claim_id", "claim_lines", ["claim_id"])
    op.create_index("ix_claim_lines_service_code", "claim_lines", ["service_code"])

    op.create_table(
        "claim_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32)),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_claim_events_tenant_id", "claim_events", ["tenant_id"])
    op.create_index("ix_claim_events_claim_id", "claim_events", ["claim_id"])
    op.create_index("ix_claim_event_timeline", "claim_events", ["claim_id", "occurred_at"])

    op.create_table(
        "cost_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policies.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "service_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_items.id", ondelete="RESTRICT"),
        ),
        sa.Column("service_bundle", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("billed_cents", sa.Integer(), nullable=False),
        sa.Column("contracted_rate_cents", sa.Integer()),
        sa.Column("deductible_applied_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coinsurance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("copay_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_liability_cents", sa.Integer(), nullable=False),
        sa.Column("plan_pays_cents", sa.Integer(), nullable=False),
        sa.Column("deductible_remaining_cents", sa.Integer()),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "billed_cents >= 0 AND member_liability_cents >= 0 AND plan_pays_cents >= 0",
            name="cost_estimate_nonneg",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="cost_estimate_confidence",
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="cost_estimate_currency_iso4217"),
    )
    op.create_index("ix_cost_estimates_tenant_id", "cost_estimates", ["tenant_id"])
    op.create_index("ix_cost_estimates_patient_user_id", "cost_estimates", ["patient_user_id"])
    op.create_index("ix_cost_estimates_policy_id", "cost_estimates", ["policy_id"])
    op.create_index("ix_cost_estimate_patient", "cost_estimates", ["patient_user_id", "created_at"])
    op.create_index("ix_cost_estimate_scope", "cost_estimates", ["tenant_id", "expires_at"])

    op.create_table(
        "document_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=32), nullable=False),
        sa.Column(
            "linked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *timestamps(),
        sa.UniqueConstraint("document_asset_id", "subject_type", "subject_id"),
        sa.CheckConstraint(
            "link_type IN ('evidence','report','certificate','attachment','receipt')",
            name="document_link_link_type",
        ),
    )
    op.create_index("ix_document_links_tenant_id", "document_links", ["tenant_id"])
    op.create_index("ix_document_links_document_asset_id", "document_links", ["document_asset_id"])
    op.create_index("ix_document_links_subject_id", "document_links", ["subject_id"])
    op.create_index("ix_document_link_subject", "document_links", ["subject_type", "subject_id"])
    op.create_index("ix_document_link_scope", "document_links", ["tenant_id", "link_type"])

    op.create_table(
        "document_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extraction_schema", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("fields", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("field_confidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("overall_confidence", sa.Numeric(5, 4)),
        sa.Column(
            "validation_status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("corrected_fields", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("model_version", sa.String(length=64)),
        sa.Column("external_run_id", sa.String(length=64)),
        *timestamps(),
        sa.UniqueConstraint("document_asset_id", "extraction_schema", "schema_version"),
        sa.CheckConstraint(
            "validation_status IN ('pending','accepted','rejected')",
            name="extraction_validation_status",
        ),
        sa.CheckConstraint(
            "overall_confidence IS NULL OR (overall_confidence >= 0 AND overall_confidence <= 1)",
            name="extraction_confidence_range",
        ),
        sa.CheckConstraint(
            "validation_status <> 'accepted' OR reviewed_by_user_id IS NOT NULL",
            name="extraction_review_required",
        ),
    )
    op.create_index("ix_document_extractions_tenant_id", "document_extractions", ["tenant_id"])
    op.create_index(
        "ix_document_extractions_document_asset_id", "document_extractions", ["document_asset_id"]
    )
    op.create_index(
        "ix_extraction_scope", "document_extractions", ["tenant_id", "validation_status"]
    )

    op.create_table(
        "phi_access_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "patient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("purpose_of_use", sa.String(length=64), nullable=False),
        sa.Column(
            "consent_grant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consent_grants.id", ondelete="SET NULL"),
        ),
        sa.Column("request_id", sa.String(length=64)),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=512)),
        sa.Column("result_count", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('read','export','print','search')",
            name="phi_access_action",
        ),
        sa.CheckConstraint(
            "purpose_of_use IN ('TREAT','ETREAT','HPAYMT','HOPERAT','PATRQT','PUBHLTH','RESEARCH')",
            name="phi_purpose_of_use",
        ),
    )
    op.create_index("ix_phi_access_events_tenant_id", "phi_access_events", ["tenant_id"])
    op.create_index("ix_phi_access_events_actor_user_id", "phi_access_events", ["actor_user_id"])
    op.create_index(
        "ix_phi_access_events_patient_user_id", "phi_access_events", ["patient_user_id"]
    )
    op.create_index("ix_phi_access_patient", "phi_access_events", ["patient_user_id", "created_at"])
    op.create_index("ix_phi_access_scope", "phi_access_events", ["tenant_id", "created_at"])
    op.create_index("ix_phi_access_actor", "phi_access_events", ["actor_user_id", "created_at"])
    op.create_index(
        "ix_phi_access_breakglass",
        "phi_access_events",
        ["tenant_id", "created_at"],
        postgresql_where=sa.text("purpose_of_use = 'ETREAT'"),
    )

    op.create_table(
        "data_subject_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subject_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.Column("refusal_reason", sa.String(length=500)),
        sa.Column(
            "handled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "export_document_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("notes", sa.Text()),
        *timestamps(),
        sa.CheckConstraint(
            "request_type IN ('access','rectification','erasure','portability','restriction')",
            name="dsr_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('received','verifying','in_progress','fulfilled','refused','withdrawn')",
            name="dsr_status",
        ),
        sa.CheckConstraint(
            "status <> 'refused' OR refusal_reason IS NOT NULL",
            name="dsr_refusal_reason",
        ),
        sa.CheckConstraint(
            "status <> 'fulfilled' OR fulfilled_at IS NOT NULL",
            name="dsr_fulfilled_at",
        ),
    )
    op.create_index("ix_data_subject_requests_tenant_id", "data_subject_requests", ["tenant_id"])
    op.create_index(
        "ix_data_subject_requests_subject_user_id", "data_subject_requests", ["subject_user_id"]
    )
    op.create_index("ix_dsr_scope", "data_subject_requests", ["tenant_id", "status", "due_at"])

    op.create_table(
        "support_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="sev3"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("queue", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column(
            "requester_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assignee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("related_record_type", sa.String(length=64)),
        sa.Column("related_record_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint(
            "severity IN ('sev1','sev2','sev3','sev4')",
            name="support_severity",
        ),
        sa.CheckConstraint(
            "status IN "
            "('new','triaged','in_progress','waiting_customer','escalated','resolved','closed')",
            name="support_status",
        ),
        sa.CheckConstraint("escalation_level >= 0", name="support_escalation_level"),
        sa.CheckConstraint(
            "status <> 'resolved' OR resolved_at IS NOT NULL",
            name="support_resolved_at",
        ),
    )
    op.create_index("ix_support_cases_tenant_id", "support_cases", ["tenant_id"])
    op.create_index("ix_support_cases_requester_user_id", "support_cases", ["requester_user_id"])
    op.create_index("ix_support_cases_assignee_user_id", "support_cases", ["assignee_user_id"])
    op.create_index("ix_support_cases_sla_due_at", "support_cases", ["sla_due_at"])
    op.create_index(
        "ix_support_cases_queue", "support_cases", ["tenant_id", "status", "sla_due_at"]
    )
    op.create_index("ix_support_case_assignee", "support_cases", ["assignee_user_id", "status"])

    op.create_table(
        "support_case_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="internal"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "visibility IN ('internal','external')",
            name="support_comment_visibility",
        ),
    )
    op.create_index("ix_support_case_comments_case_id", "support_case_comments", ["case_id"])
    op.create_index("ix_support_comment_case", "support_case_comments", ["case_id", "created_at"])

    op.create_table(
        "support_case_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=32)),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=255)),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_support_case_events_case_id", "support_case_events", ["case_id"])
    op.create_index("ix_support_event_timeline", "support_case_events", ["case_id", "occurred_at"])

    op.create_foreign_key(
        "fk_appointments_encounter_id_encounters",
        "appointments",
        "encounters",
        ["encounter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_referral_id_referrals",
        "appointments",
        "referrals",
        ["referral_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_appointments_invoice_id_invoices",
        "appointments",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_lab_orders_invoice_id_invoices",
        "lab_orders",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_referrals_prior_authorization_id_prior_authorizations",
        "referrals",
        "prior_authorizations",
        ["prior_authorization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_invoices_policy_id_policies",
        "invoices",
        "policies",
        ["policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION healthos_reject_log_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'append-only table';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_appointment_status_events_mutation
          BEFORE UPDATE OR DELETE ON appointment_status_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_prescription_safety_checks_mutation
          BEFORE UPDATE OR DELETE ON prescription_safety_checks
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_medication_adherence_events_mutation
          BEFORE UPDATE OR DELETE ON medication_adherence_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_loyalty_ledger_mutation
          BEFORE UPDATE OR DELETE ON loyalty_ledger
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_claim_events_mutation
          BEFORE UPDATE OR DELETE ON claim_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_phi_access_events_mutation
          BEFORE UPDATE OR DELETE ON phi_access_events
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_log_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION healthos_reject_signed_note_mutation() RETURNS trigger AS $$
        BEGIN
          IF OLD.signed_at IS NOT NULL THEN
            RAISE EXCEPTION 'signed clinical notes are immutable; add an addendum or a new version';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER reject_signed_note_mutation
          BEFORE UPDATE OR DELETE ON clinical_notes
          FOR EACH ROW EXECUTE FUNCTION healthos_reject_signed_note_mutation()
        """
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
            {"id": 12, "name": "clinical:read", "description": "Read authorized clinical records"},
            {"id": 13, "name": "clinical:write", "description": "Record authorized clinical data"},
            {"id": 14, "name": "prescribe:write", "description": "Issue prescriptions"},
            {"id": 15, "name": "lab:manage", "description": "Manage laboratory orders and results"},
            {
                "id": 16,
                "name": "scheduling:manage",
                "description": "Manage schedules, slots, and appointments",
            },
            {
                "id": 17,
                "name": "billing:manage",
                "description": "Manage invoices, payments, and estimates",
            },
            {"id": 18, "name": "claims:manage", "description": "Manage insurance claims"},
            {
                "id": 19,
                "name": "policy:manage",
                "description": "Manage insurance products, plans, and policies",
            },
            {
                "id": 20,
                "name": "terminology:read",
                "description": "Read terminology and reference data",
            },
            {"id": 21, "name": "support:manage", "description": "Manage support cases"},
            {
                "id": 22,
                "name": "phi:audit:read",
                "description": "Read PHI access and disclosure logs",
            },
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            *[
                {"role_id": role, "permission_id": 12}
                for role in (
                    1,
                    2,
                    3,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 13}
                for role in (
                    2,
                    3,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 14}
                for role in (
                    2,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 15}
                for role in (
                    3,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 16}
                for role in (
                    2,
                    3,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 17}
                for role in (
                    3,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 18}
                for role in (
                    1,
                    3,
                    4,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 19}
                for role in (
                    4,
                    5,
                )
            ],
            *[
                {"role_id": role, "permission_id": 20}
                for role in (
                    1,
                    2,
                    3,
                    4,
                    5,
                )
            ],
            *[{"role_id": role, "permission_id": 21} for role in (5,)],
            *[{"role_id": role, "permission_id": 22} for role in (5,)],
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id BETWEEN 12 AND 22")
    op.execute("DELETE FROM permissions WHERE id BETWEEN 12 AND 22")

    op.execute("DROP TRIGGER IF EXISTS reject_signed_note_mutation ON clinical_notes")
    op.execute("DROP TRIGGER IF EXISTS reject_phi_access_events_mutation ON phi_access_events")
    op.execute("DROP TRIGGER IF EXISTS reject_claim_events_mutation ON claim_events")
    op.execute("DROP TRIGGER IF EXISTS reject_loyalty_ledger_mutation ON loyalty_ledger")
    op.execute(
        "DROP TRIGGER IF EXISTS reject_medication_adherence_events_mutation "
        "ON medication_adherence_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS reject_prescription_safety_checks_mutation "
        "ON prescription_safety_checks"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS reject_appointment_status_events_mutation "
        "ON appointment_status_events"
    )
    op.execute("DROP FUNCTION IF EXISTS healthos_reject_signed_note_mutation()")
    op.execute("DROP FUNCTION IF EXISTS healthos_reject_log_mutation()")

    op.drop_constraint("fk_invoices_policy_id_policies", "invoices", type_="foreignkey")
    op.drop_constraint(
        "fk_referrals_prior_authorization_id_prior_authorizations", "referrals", type_="foreignkey"
    )
    op.drop_constraint("fk_lab_orders_invoice_id_invoices", "lab_orders", type_="foreignkey")
    op.drop_constraint("fk_appointments_invoice_id_invoices", "appointments", type_="foreignkey")
    op.drop_constraint("fk_appointments_referral_id_referrals", "appointments", type_="foreignkey")
    op.drop_constraint(
        "fk_appointments_encounter_id_encounters", "appointments", type_="foreignkey"
    )

    op.drop_index("ix_support_event_timeline", table_name="support_case_events")
    op.drop_index("ix_support_case_events_case_id", table_name="support_case_events")
    op.drop_table("support_case_events")

    op.drop_index("ix_support_comment_case", table_name="support_case_comments")
    op.drop_index("ix_support_case_comments_case_id", table_name="support_case_comments")
    op.drop_table("support_case_comments")

    op.drop_index("ix_support_case_assignee", table_name="support_cases")
    op.drop_index("ix_support_cases_queue", table_name="support_cases")
    op.drop_index("ix_support_cases_sla_due_at", table_name="support_cases")
    op.drop_index("ix_support_cases_assignee_user_id", table_name="support_cases")
    op.drop_index("ix_support_cases_requester_user_id", table_name="support_cases")
    op.drop_index("ix_support_cases_tenant_id", table_name="support_cases")
    op.drop_table("support_cases")

    op.drop_index("ix_dsr_scope", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_subject_user_id", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_tenant_id", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")

    op.drop_index("ix_phi_access_breakglass", table_name="phi_access_events")
    op.drop_index("ix_phi_access_actor", table_name="phi_access_events")
    op.drop_index("ix_phi_access_scope", table_name="phi_access_events")
    op.drop_index("ix_phi_access_patient", table_name="phi_access_events")
    op.drop_index("ix_phi_access_events_patient_user_id", table_name="phi_access_events")
    op.drop_index("ix_phi_access_events_actor_user_id", table_name="phi_access_events")
    op.drop_index("ix_phi_access_events_tenant_id", table_name="phi_access_events")
    op.drop_table("phi_access_events")

    op.drop_index("ix_extraction_scope", table_name="document_extractions")
    op.drop_index("ix_document_extractions_document_asset_id", table_name="document_extractions")
    op.drop_index("ix_document_extractions_tenant_id", table_name="document_extractions")
    op.drop_table("document_extractions")

    op.drop_index("ix_document_link_scope", table_name="document_links")
    op.drop_index("ix_document_link_subject", table_name="document_links")
    op.drop_index("ix_document_links_subject_id", table_name="document_links")
    op.drop_index("ix_document_links_document_asset_id", table_name="document_links")
    op.drop_index("ix_document_links_tenant_id", table_name="document_links")
    op.drop_table("document_links")

    op.drop_index("ix_cost_estimate_scope", table_name="cost_estimates")
    op.drop_index("ix_cost_estimate_patient", table_name="cost_estimates")
    op.drop_index("ix_cost_estimates_policy_id", table_name="cost_estimates")
    op.drop_index("ix_cost_estimates_patient_user_id", table_name="cost_estimates")
    op.drop_index("ix_cost_estimates_tenant_id", table_name="cost_estimates")
    op.drop_table("cost_estimates")

    op.drop_index("ix_claim_event_timeline", table_name="claim_events")
    op.drop_index("ix_claim_events_claim_id", table_name="claim_events")
    op.drop_index("ix_claim_events_tenant_id", table_name="claim_events")
    op.drop_table("claim_events")

    op.drop_index("ix_claim_lines_service_code", table_name="claim_lines")
    op.drop_index("ix_claim_lines_claim_id", table_name="claim_lines")
    op.drop_table("claim_lines")

    op.drop_index("ix_claim_patient", table_name="claims")
    op.drop_index("ix_claim_scope", table_name="claims")
    op.drop_index("ix_claims_encounter_id", table_name="claims")
    op.drop_index("ix_claims_patient_user_id", table_name="claims")
    op.drop_index("ix_claims_policy_id", table_name="claims")
    op.drop_index("ix_claims_tenant_id", table_name="claims")
    op.drop_table("claims")

    op.drop_index("ix_prior_auth_patient", table_name="prior_authorizations")
    op.drop_index("ix_prior_auth_scope", table_name="prior_authorizations")
    op.drop_index("ix_prior_authorizations_patient_user_id", table_name="prior_authorizations")
    op.drop_index("ix_prior_authorizations_policy_id", table_name="prior_authorizations")
    op.drop_index("ix_prior_authorizations_tenant_id", table_name="prior_authorizations")
    op.drop_table("prior_authorizations")

    op.drop_index("ix_eligibility_scope", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_lookup", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_patient_user_id", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_tenant_id", table_name="eligibility_checks")
    op.drop_table("eligibility_checks")

    op.drop_index("ix_accumulator_lookup", table_name="benefit_accumulators")
    op.drop_index("ix_benefit_accumulators_patient_user_id", table_name="benefit_accumulators")
    op.drop_index("ix_benefit_accumulators_policy_id", table_name="benefit_accumulators")
    op.drop_index("ix_benefit_accumulators_tenant_id", table_name="benefit_accumulators")
    op.drop_table("benefit_accumulators")

    op.drop_index("ix_beneficiary_policy", table_name="beneficiaries")
    op.drop_index("ix_beneficiaries_policy_id", table_name="beneficiaries")
    op.drop_index("ix_beneficiaries_tenant_id", table_name="beneficiaries")
    op.drop_table("beneficiaries")

    op.drop_index("ix_premium_schedule_due", table_name="premium_schedules")
    op.drop_index("ix_premium_schedules_policy_id", table_name="premium_schedules")
    op.drop_index("ix_premium_schedules_tenant_id", table_name="premium_schedules")
    op.drop_table("premium_schedules")

    op.drop_index("ix_policy_member_patient", table_name="policy_members")
    op.drop_index("ix_policy_members_patient_user_id", table_name="policy_members")
    op.drop_index("ix_policy_members_policy_id", table_name="policy_members")
    op.drop_index("ix_policy_members_tenant_id", table_name="policy_members")
    op.drop_table("policy_members")

    op.drop_index("ix_policies_active", table_name="policies")
    op.drop_index("ix_policies_subscriber_user_id", table_name="policies")
    op.drop_index("ix_policies_plan_id", table_name="policies")
    op.drop_index("ix_policies_tenant_id", table_name="policies")
    op.drop_table("policies")

    op.drop_index("ix_policy_application_scope", table_name="policy_applications")
    op.drop_index("ix_policy_applications_plan_id", table_name="policy_applications")
    op.drop_index("ix_policy_applications_applicant_user_id", table_name="policy_applications")
    op.drop_index("ix_policy_applications_tenant_id", table_name="policy_applications")
    op.drop_table("policy_applications")

    op.drop_index("ix_recommendation_scope", table_name="plan_recommendations")
    op.drop_index("ix_recommendation_patient", table_name="plan_recommendations")
    op.drop_index("ix_plan_recommendations_plan_id", table_name="plan_recommendations")
    op.drop_index("ix_plan_recommendations_patient_user_id", table_name="plan_recommendations")
    op.drop_index("ix_plan_recommendations_tenant_id", table_name="plan_recommendations")
    op.drop_table("plan_recommendations")

    op.drop_index("ix_benefit_explanation_scope", table_name="benefit_explanations")
    op.drop_index("ix_benefit_explanations_plan_benefit_id", table_name="benefit_explanations")
    op.drop_index("ix_benefit_explanations_tenant_id", table_name="benefit_explanations")
    op.drop_table("benefit_explanations")

    op.drop_index("ix_plan_benefit_lookup", table_name="plan_benefits")
    op.drop_index("ix_plan_benefits_plan_id", table_name="plan_benefits")
    op.drop_index("ix_plan_benefits_tenant_id", table_name="plan_benefits")
    op.drop_table("plan_benefits")

    op.drop_index("ix_insurance_plan_scope", table_name="insurance_plans")
    op.drop_index("ix_insurance_plans_product_id", table_name="insurance_plans")
    op.drop_index("ix_insurance_plans_tenant_id", table_name="insurance_plans")
    op.drop_table("insurance_plans")

    op.drop_index("ix_insurance_product_scope", table_name="insurance_products")
    op.drop_index("ix_insurance_products_payer_organization_id", table_name="insurance_products")
    op.drop_index("ix_insurance_products_tenant_id", table_name="insurance_products")
    op.drop_table("insurance_products")

    op.drop_index("ix_loyalty_ledger_account", table_name="loyalty_ledger")
    op.drop_index("ix_loyalty_ledger_account_id", table_name="loyalty_ledger")
    op.drop_index("ix_loyalty_ledger_tenant_id", table_name="loyalty_ledger")
    op.drop_table("loyalty_ledger")

    op.drop_index("ix_loyalty_account_scope", table_name="loyalty_accounts")
    op.drop_index("ix_loyalty_accounts_tenant_id", table_name="loyalty_accounts")
    op.drop_table("loyalty_accounts")

    op.drop_index("ix_refund_scope", table_name="refunds")
    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_index("ix_refunds_tenant_id", table_name="refunds")
    op.drop_table("refunds")

    op.drop_index("ix_payment_scope", table_name="payments")
    op.drop_index("ix_payments_payer_user_id", table_name="payments")
    op.drop_index("ix_payments_appointment_id", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_tenant_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_invoice_lines_invoice_id", table_name="invoice_lines")
    op.drop_table("invoice_lines")

    op.drop_index("ix_invoice_patient", table_name="invoices")
    op.drop_index("ix_invoice_scope", table_name="invoices")
    op.drop_index("ix_invoices_lab_order_id", table_name="invoices")
    op.drop_index("ix_invoices_appointment_id", table_name="invoices")
    op.drop_index("ix_invoices_patient_user_id", table_name="invoices")
    op.drop_index("ix_invoices_payer_user_id", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_lab_result_current", table_name="lab_results")
    op.drop_index("ix_lab_result_unacked", table_name="lab_results")
    op.drop_index("ix_lab_result_scope", table_name="lab_results")
    op.drop_index("ix_lab_result_patient_trend", table_name="lab_results")
    op.drop_index("ix_lab_results_source_document_id", table_name="lab_results")
    op.drop_index("ix_lab_results_recorded_by_user_id", table_name="lab_results")
    op.drop_index("ix_lab_results_effective_at", table_name="lab_results")
    op.drop_index("ix_lab_results_interpretation_code", table_name="lab_results")
    op.drop_index("ix_lab_results_parent_result_id", table_name="lab_results")
    op.drop_index("ix_lab_results_test_code", table_name="lab_results")
    op.drop_index("ix_lab_results_encounter_id", table_name="lab_results")
    op.drop_index("ix_lab_results_patient_user_id", table_name="lab_results")
    op.drop_index("ix_lab_results_lab_test_id", table_name="lab_results")
    op.drop_index("ix_lab_results_lab_order_id", table_name="lab_results")
    op.drop_index("ix_lab_results_tenant_id", table_name="lab_results")
    op.drop_table("lab_results")

    op.drop_index("ix_specimen_scope", table_name="specimens")
    op.drop_index("ix_specimens_specimen_type_code", table_name="specimens")
    op.drop_index("ix_specimens_patient_user_id", table_name="specimens")
    op.drop_index("ix_specimens_lab_order_id", table_name="specimens")
    op.drop_index("ix_specimens_tenant_id", table_name="specimens")
    op.drop_table("specimens")

    op.drop_index("ix_lab_order_tests_lab_test_id", table_name="lab_order_tests")
    op.drop_index("ix_lab_order_tests_lab_order_id", table_name="lab_order_tests")
    op.drop_table("lab_order_tests")

    op.drop_index("ix_lab_order_patient", table_name="lab_orders")
    op.drop_index("ix_lab_order_scope", table_name="lab_orders")
    op.drop_index("ix_lab_orders_source_document_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_recorded_by_user_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_slot_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_encounter_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_ordering_provider_user_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_patient_user_id", table_name="lab_orders")
    op.drop_index("ix_lab_orders_tenant_id", table_name="lab_orders")
    op.drop_table("lab_orders")

    op.drop_index("ix_lab_slot_test_lookup", table_name="lab_slot_tests")
    op.drop_table("lab_slot_tests")

    op.drop_index("ix_lab_slot_open", table_name="lab_slots")
    op.drop_index("ix_lab_slot_scope", table_name="lab_slots")
    op.drop_index("ix_lab_slots_start_at", table_name="lab_slots")
    op.drop_index("ix_lab_slots_facility_id", table_name="lab_slots")
    op.drop_index("ix_lab_slots_tenant_id", table_name="lab_slots")
    op.drop_table("lab_slots")

    op.drop_index("ix_lab_test_scope", table_name="lab_tests")
    op.drop_index("ix_lab_tests_test_code", table_name="lab_tests")
    op.drop_index("ix_lab_tests_tenant_id", table_name="lab_tests")
    op.drop_table("lab_tests")

    op.drop_index("ix_lab_facility_geo", table_name="lab_facilities")
    op.drop_index("ix_lab_facility_scope", table_name="lab_facilities")
    op.drop_index("ix_lab_facilities_organization_id", table_name="lab_facilities")
    op.drop_index("ix_lab_facilities_tenant_id", table_name="lab_facilities")
    op.drop_table("lab_facilities")

    op.drop_index("ix_safety_check_scope", table_name="prescription_safety_checks")
    op.drop_index("ix_safety_check_prescription", table_name="prescription_safety_checks")
    op.drop_index(
        "ix_prescription_safety_checks_patient_user_id", table_name="prescription_safety_checks"
    )
    op.drop_index(
        "ix_prescription_safety_checks_medication_request_id",
        table_name="prescription_safety_checks",
    )
    op.drop_index(
        "ix_prescription_safety_checks_prescription_id", table_name="prescription_safety_checks"
    )
    op.drop_index(
        "ix_prescription_safety_checks_tenant_id", table_name="prescription_safety_checks"
    )
    op.drop_table("prescription_safety_checks")

    op.drop_index("ix_med_statement_scope", table_name="medication_statements")
    op.drop_index("ix_med_statement_patient", table_name="medication_statements")
    op.drop_index("ix_medication_statements_source_document_id", table_name="medication_statements")
    op.drop_index(
        "ix_medication_statements_recorded_by_user_id", table_name="medication_statements"
    )
    op.drop_index("ix_medication_statements_medication_code", table_name="medication_statements")
    op.drop_index("ix_medication_statements_encounter_id", table_name="medication_statements")
    op.drop_index("ix_medication_statements_patient_user_id", table_name="medication_statements")
    op.drop_index("ix_medication_statements_tenant_id", table_name="medication_statements")
    op.drop_table("medication_statements")

    op.drop_index("ix_dispense_scope", table_name="medication_dispenses")
    op.drop_index("ix_medication_dispenses_patient_user_id", table_name="medication_dispenses")
    op.drop_index(
        "ix_medication_dispenses_medication_request_id", table_name="medication_dispenses"
    )
    op.drop_index("ix_medication_dispenses_tenant_id", table_name="medication_dispenses")
    op.drop_table("medication_dispenses")

    op.drop_index("ix_adherence_scope", table_name="medication_adherence_events")
    op.drop_index("ix_adherence_patient", table_name="medication_adherence_events")
    op.drop_index(
        "ix_medication_adherence_events_medication_request_id",
        table_name="medication_adherence_events",
    )
    op.drop_index(
        "ix_medication_adherence_events_occurrence_id", table_name="medication_adherence_events"
    )
    op.drop_index(
        "ix_medication_adherence_events_schedule_id", table_name="medication_adherence_events"
    )
    op.drop_index(
        "ix_medication_adherence_events_patient_user_id", table_name="medication_adherence_events"
    )
    op.drop_index(
        "ix_medication_adherence_events_tenant_id", table_name="medication_adherence_events"
    )
    op.drop_table("medication_adherence_events")

    op.drop_index("ix_reminder_pending", table_name="medication_reminder_occurrences")
    op.drop_index("ix_reminder_patient", table_name="medication_reminder_occurrences")
    op.drop_index("ix_reminder_due", table_name="medication_reminder_occurrences")
    op.drop_index(
        "ix_medication_reminder_occurrences_patient_user_id",
        table_name="medication_reminder_occurrences",
    )
    op.drop_index(
        "ix_medication_reminder_occurrences_schedule_id",
        table_name="medication_reminder_occurrences",
    )
    op.drop_index(
        "ix_medication_reminder_occurrences_tenant_id", table_name="medication_reminder_occurrences"
    )
    op.drop_table("medication_reminder_occurrences")

    op.drop_index("ix_med_schedule_generation", table_name="medication_schedules")
    op.drop_index("ix_med_schedule_scope", table_name="medication_schedules")
    op.drop_index("ix_med_schedule_patient", table_name="medication_schedules")
    op.drop_index(
        "ix_medication_schedules_dosage_instruction_id", table_name="medication_schedules"
    )
    op.drop_index(
        "ix_medication_schedules_medication_request_id", table_name="medication_schedules"
    )
    op.drop_index("ix_medication_schedules_prescription_id", table_name="medication_schedules")
    op.drop_index("ix_medication_schedules_patient_user_id", table_name="medication_schedules")
    op.drop_index("ix_medication_schedules_tenant_id", table_name="medication_schedules")
    op.drop_table("medication_schedules")

    op.drop_index("ix_dosage_request", table_name="medication_dosage_instructions")
    op.drop_index(
        "ix_medication_dosage_instructions_medication_request_id",
        table_name="medication_dosage_instructions",
    )
    op.drop_table("medication_dosage_instructions")

    op.drop_index("ix_med_request_active", table_name="medication_requests")
    op.drop_index("ix_med_request_scope", table_name="medication_requests")
    op.drop_index("ix_med_request_patient", table_name="medication_requests")
    op.drop_index("ix_medication_requests_source_document_id", table_name="medication_requests")
    op.drop_index("ix_medication_requests_recorded_by_user_id", table_name="medication_requests")
    op.drop_index("ix_medication_requests_medication_code", table_name="medication_requests")
    op.drop_index("ix_medication_requests_encounter_id", table_name="medication_requests")
    op.drop_index("ix_medication_requests_patient_user_id", table_name="medication_requests")
    op.drop_index("ix_medication_requests_prescription_id", table_name="medication_requests")
    op.drop_index("ix_medication_requests_tenant_id", table_name="medication_requests")
    op.drop_table("medication_requests")

    op.drop_index("ix_prescription_patient", table_name="prescriptions")
    op.drop_index("ix_prescription_scope", table_name="prescriptions")
    op.drop_index("ix_prescriptions_source_document_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_recorded_by_user_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_written_at", table_name="prescriptions")
    op.drop_index("ix_prescriptions_encounter_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_prescriber_user_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_user_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_tenant_id", table_name="prescriptions")
    op.drop_table("prescriptions")

    op.drop_index("ix_family_history_scope", table_name="family_history")
    op.drop_index("ix_family_history_patient", table_name="family_history")
    op.drop_index("ix_family_history_source_document_id", table_name="family_history")
    op.drop_index("ix_family_history_recorded_by_user_id", table_name="family_history")
    op.drop_index("ix_family_history_condition_code", table_name="family_history")
    op.drop_index("ix_family_history_patient_user_id", table_name="family_history")
    op.drop_index("ix_family_history_tenant_id", table_name="family_history")
    op.drop_table("family_history")

    op.drop_index("ix_care_team_primary", table_name="care_team_members")
    op.drop_index("ix_care_team_scope", table_name="care_team_members")
    op.drop_index("ix_care_team_patient", table_name="care_team_members")
    op.drop_index("ix_care_team_members_member_user_id", table_name="care_team_members")
    op.drop_index("ix_care_team_members_patient_user_id", table_name="care_team_members")
    op.drop_index("ix_care_team_members_tenant_id", table_name="care_team_members")
    op.drop_table("care_team_members")

    op.drop_index("ix_referral_patient", table_name="referrals")
    op.drop_index("ix_referral_scope", table_name="referrals")
    op.drop_index("ix_referrals_encounter_id", table_name="referrals")
    op.drop_index("ix_referrals_patient_user_id", table_name="referrals")
    op.drop_index("ix_referrals_tenant_id", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_encounter_code_scope", table_name="encounter_codes")
    op.drop_index("ix_encounter_codes_billing_code", table_name="encounter_codes")
    op.drop_index("ix_encounter_codes_encounter_id", table_name="encounter_codes")
    op.drop_index("ix_encounter_codes_tenant_id", table_name="encounter_codes")
    op.drop_table("encounter_codes")

    op.drop_index("ix_note_addendum_parent", table_name="clinical_note_addenda")
    op.drop_index("ix_clinical_note_addenda_clinical_note_id", table_name="clinical_note_addenda")
    op.drop_table("clinical_note_addenda")

    op.drop_index("ix_note_unsigned", table_name="clinical_notes")
    op.drop_index("ix_note_patient", table_name="clinical_notes")
    op.drop_index("ix_note_scope", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_source_document_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_recorded_by_user_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_author_user_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_patient_user_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_encounter_id", table_name="clinical_notes")
    op.drop_index("ix_clinical_notes_tenant_id", table_name="clinical_notes")
    op.drop_table("clinical_notes")

    op.drop_index("ix_certificate_scope", table_name="immunization_certificates")
    op.drop_index("ix_immunization_certificates_tenant_id", table_name="immunization_certificates")
    op.drop_table("immunization_certificates")

    op.drop_index("ix_immunization_due", table_name="immunizations")
    op.drop_index("ix_immunization_scope", table_name="immunizations")
    op.drop_index("ix_immunization_patient", table_name="immunizations")
    op.drop_index("ix_immunizations_source_document_id", table_name="immunizations")
    op.drop_index("ix_immunizations_recorded_by_user_id", table_name="immunizations")
    op.drop_index("ix_immunizations_next_due_at", table_name="immunizations")
    op.drop_index("ix_immunizations_vaccine_code", table_name="immunizations")
    op.drop_index("ix_immunizations_encounter_id", table_name="immunizations")
    op.drop_index("ix_immunizations_patient_user_id", table_name="immunizations")
    op.drop_index("ix_immunizations_tenant_id", table_name="immunizations")
    op.drop_table("immunizations")

    op.drop_index("ix_growth_scope", table_name="growth_measurements")
    op.drop_index("ix_growth_patient", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_source_document_id", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_recorded_by_user_id", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_measured_at", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_encounter_id", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_patient_user_id", table_name="growth_measurements")
    op.drop_index("ix_growth_measurements_tenant_id", table_name="growth_measurements")
    op.drop_table("growth_measurements")

    op.drop_index("ix_vital_component_parent", table_name="vital_sign_components")
    op.drop_index("ix_vital_sign_components_observation_code", table_name="vital_sign_components")
    op.drop_index("ix_vital_sign_components_vital_sign_id", table_name="vital_sign_components")
    op.drop_table("vital_sign_components")

    op.drop_index("ix_vital_current", table_name="vital_signs")
    op.drop_index("ix_vital_scope", table_name="vital_signs")
    op.drop_index("ix_vital_patient_trend", table_name="vital_signs")
    op.drop_index("ix_vital_signs_source_document_id", table_name="vital_signs")
    op.drop_index("ix_vital_signs_recorded_by_user_id", table_name="vital_signs")
    op.drop_index("ix_vital_signs_effective_at", table_name="vital_signs")
    op.drop_index("ix_vital_signs_interpretation_code", table_name="vital_signs")
    op.drop_index("ix_vital_signs_observation_code", table_name="vital_signs")
    op.drop_index("ix_vital_signs_encounter_id", table_name="vital_signs")
    op.drop_index("ix_vital_signs_patient_user_id", table_name="vital_signs")
    op.drop_index("ix_vital_signs_tenant_id", table_name="vital_signs")
    op.drop_table("vital_signs")

    op.drop_index("ix_allergy_status_scope", table_name="patient_allergy_status")
    op.drop_index("ix_patient_allergy_status_tenant_id", table_name="patient_allergy_status")
    op.drop_table("patient_allergy_status")

    op.drop_index("ix_allergy_reaction_parent", table_name="allergy_reactions")
    op.drop_index("ix_allergy_reactions_manifestation_code", table_name="allergy_reactions")
    op.drop_index("ix_allergy_reactions_allergy_intolerance_id", table_name="allergy_reactions")
    op.drop_table("allergy_reactions")

    op.drop_index("ix_allergy_active", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_scope", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_patient", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_source_document_id", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_recorded_by_user_id", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_substance_code", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_encounter_id", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_patient_user_id", table_name="allergy_intolerances")
    op.drop_index("ix_allergy_intolerances_tenant_id", table_name="allergy_intolerances")
    op.drop_table("allergy_intolerances")

    op.drop_index("ix_encounter_diagnosis_principal", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnosis_scope", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_source_document_id", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_recorded_by_user_id", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_diagnosis_code", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_condition_id", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_patient_user_id", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_encounter_id", table_name="encounter_diagnoses")
    op.drop_index("ix_encounter_diagnoses_tenant_id", table_name="encounter_diagnoses")
    op.drop_table("encounter_diagnoses")

    op.drop_index("ix_condition_current", table_name="conditions")
    op.drop_index("ix_condition_scope", table_name="conditions")
    op.drop_index("ix_condition_patient", table_name="conditions")
    op.drop_index("ix_conditions_source_document_id", table_name="conditions")
    op.drop_index("ix_conditions_recorded_by_user_id", table_name="conditions")
    op.drop_index("ix_conditions_condition_code", table_name="conditions")
    op.drop_index("ix_conditions_encounter_id", table_name="conditions")
    op.drop_index("ix_conditions_patient_user_id", table_name="conditions")
    op.drop_index("ix_conditions_tenant_id", table_name="conditions")
    op.drop_table("conditions")

    op.drop_index("ix_telehealth_scope", table_name="telehealth_sessions")
    op.drop_index("ix_telehealth_sessions_encounter_id", table_name="telehealth_sessions")
    op.drop_index("ix_telehealth_sessions_tenant_id", table_name="telehealth_sessions")
    op.drop_table("telehealth_sessions")

    op.drop_index("ix_encounter_practitioner", table_name="encounters")
    op.drop_index("ix_encounter_scope", table_name="encounters")
    op.drop_index("ix_encounter_patient", table_name="encounters")
    op.drop_index("ix_encounters_source_document_id", table_name="encounters")
    op.drop_index("ix_encounters_recorded_by_user_id", table_name="encounters")
    op.drop_index("ix_encounters_started_at", table_name="encounters")
    op.drop_index("ix_encounters_appointment_id", table_name="encounters")
    op.drop_index("ix_encounters_primary_practitioner_user_id", table_name="encounters")
    op.drop_index("ix_encounters_patient_user_id", table_name="encounters")
    op.drop_index("ix_encounters_tenant_id", table_name="encounters")
    op.drop_table("encounters")

    op.drop_index("ix_appointment_event_timeline", table_name="appointment_status_events")
    op.drop_index(
        "ix_appointment_status_events_appointment_id", table_name="appointment_status_events"
    )
    op.drop_index("ix_appointment_status_events_tenant_id", table_name="appointment_status_events")
    op.drop_table("appointment_status_events")

    op.drop_index("ix_appointment_slot_booked", table_name="appointments")
    op.drop_index("ix_appointment_patient", table_name="appointments")
    op.drop_index("ix_appointment_scope", table_name="appointments")
    op.drop_index("ix_appointments_encounter_id", table_name="appointments")
    op.drop_index("ix_appointments_provider_user_id", table_name="appointments")
    op.drop_index("ix_appointments_patient_user_id", table_name="appointments")
    op.drop_index("ix_appointments_slot_id", table_name="appointments")
    op.drop_index("ix_appointments_tenant_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("ix_slot_open", table_name="appointment_slots")
    op.drop_index("ix_slot_scope", table_name="appointment_slots")
    op.drop_index("ix_appointment_slots_start_at", table_name="appointment_slots")
    op.drop_index("ix_appointment_slots_provider_user_id", table_name="appointment_slots")
    op.drop_index("ix_appointment_slots_tenant_id", table_name="appointment_slots")
    op.drop_table("appointment_slots")

    op.drop_index("ix_provider_schedule_scope", table_name="provider_schedules")
    op.drop_index("ix_provider_schedules_provider_user_id", table_name="provider_schedules")
    op.drop_index("ix_provider_schedules_tenant_id", table_name="provider_schedules")
    op.drop_table("provider_schedules")

    op.drop_index("ix_contract_rate_lookup", table_name="payer_contract_rates")
    op.drop_index("ix_payer_contract_rates_service_code", table_name="payer_contract_rates")
    op.drop_index(
        "ix_payer_contract_rates_provider_organization_id", table_name="payer_contract_rates"
    )
    op.drop_index(
        "ix_payer_contract_rates_payer_organization_id", table_name="payer_contract_rates"
    )
    op.drop_index("ix_payer_contract_rates_tenant_id", table_name="payer_contract_rates")
    op.drop_table("payer_contract_rates")

    op.drop_index("ix_service_item_scope", table_name="service_items")
    op.drop_index("ix_service_items_service_code", table_name="service_items")
    op.drop_index("ix_service_items_organization_id", table_name="service_items")
    op.drop_index("ix_service_items_tenant_id", table_name="service_items")
    op.drop_table("service_items")

    op.drop_index("ix_practitioner_role_directory", table_name="practitioner_roles")
    op.drop_index("ix_practitioner_role_scope", table_name="practitioner_roles")
    op.drop_index("ix_practitioner_roles_credential_expires_at", table_name="practitioner_roles")
    op.drop_index("ix_practitioner_roles_organization_id", table_name="practitioner_roles")
    op.drop_index("ix_practitioner_roles_practitioner_user_id", table_name="practitioner_roles")
    op.drop_index("ix_practitioner_roles_tenant_id", table_name="practitioner_roles")
    op.drop_table("practitioner_roles")

    op.drop_index("ix_department_scope", table_name="departments")
    op.drop_index("ix_departments_organization_id", table_name="departments")
    op.drop_index("ix_departments_tenant_id", table_name="departments")
    op.drop_table("departments")

    op.drop_table("growth_reference_standards")

    op.drop_index("ix_comm_pref_scope", table_name="patient_communication_preferences")
    op.drop_index(
        "ix_patient_communication_preferences_tenant_id",
        table_name="patient_communication_preferences",
    )
    op.drop_table("patient_communication_preferences")

    op.drop_index("ix_practitioner_identifier_scope", table_name="practitioner_identifiers")
    op.drop_index(
        "ix_practitioner_identifiers_practitioner_user_id", table_name="practitioner_identifiers"
    )
    op.drop_index("ix_practitioner_identifiers_tenant_id", table_name="practitioner_identifiers")
    op.drop_table("practitioner_identifiers")

    op.drop_index("ix_patient_identifier_scope", table_name="patient_identifiers")
    op.drop_index("ix_patient_identifier_patient", table_name="patient_identifiers")
    op.drop_index("ix_patient_identifiers_patient_user_id", table_name="patient_identifiers")
    op.drop_index("ix_patient_identifiers_tenant_id", table_name="patient_identifiers")
    op.drop_table("patient_identifiers")

    op.execute("DROP INDEX IF EXISTS ix_code_concepts_display_trgm")
    op.drop_index("ix_code_concepts_lookup", table_name="code_concepts")
    op.drop_index("ix_code_concepts_code_system_id", table_name="code_concepts")
    op.drop_table("code_concepts")

    op.drop_index("ix_code_system_lookup", table_name="code_systems")
    op.drop_index("ix_code_systems_uri", table_name="code_systems")
    op.drop_table("code_systems")
