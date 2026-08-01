"""Seed runtime forms, dashboards, content, and governed workflows.

Revision ID: 0007
Revises: 0006
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FORM_PROPERTIES: dict[str, dict[str, dict[str, Any]]] = {
    "vitals": {
        "weight_kg": {"title": "Weight (kg)", "type": "number"},
        "height_cm": {"title": "Height (cm)", "type": "number"},
        "blood_pressure": {"title": "Blood pressure", "type": "string"},
        "heart_rate": {"title": "Heart rate", "type": "number"},
        "oxygen_saturation": {"title": "Oxygen saturation", "type": "number"},
    },
    "allergies": {
        "allergen": {"title": "Allergen", "type": "string"},
        "reaction": {"title": "Reaction", "type": "string"},
        "severity": {"title": "Severity", "type": "string"},
    },
    "vaccinations": {
        "vaccine": {"title": "Vaccine", "type": "string"},
        "dose": {"title": "Dose", "type": "string"},
        "lot_number": {"title": "Lot number", "type": "string"},
        "certificate_document_id": {"title": "Certificate", "type": "string"},
    },
    "medications": {
        "medicine": {"title": "Medicine", "type": "string"},
        "dosage": {"title": "Dosage", "type": "string"},
        "times": {"title": "Reminder times", "type": "string"},
        "course_end": {"title": "Course end", "type": "string"},
    },
    "appointments": {
        "provider": {"title": "Provider", "type": "string"},
        "location": {"title": "Location", "type": "string"},
        "visit_type": {"title": "Visit type", "type": "string"},
    },
    "lab_reports": {
        "test_name": {"title": "Test", "type": "string"},
        "result": {"title": "Result", "type": "string"},
        "reference_range": {"title": "Reference range", "type": "string"},
    },
    "insurance": {
        "payer": {"title": "Payer", "type": "string"},
        "member_id": {"title": "Member ID", "type": "string"},
        "plan_name": {"title": "Plan", "type": "string"},
        "plain_language_coverage": {"title": "Coverage summary", "type": "string"},
    },
    "claims": {
        "claim_number": {"title": "Claim number", "type": "string"},
        "payer": {"title": "Payer", "type": "string"},
        "service_code": {"title": "Service code", "type": "string"},
    },
    "prescriptions": {
        "patient_id": {"title": "HealthOS Patient ID", "type": "string"},
        "medication": {"title": "Medication", "type": "string"},
        "dosage": {"title": "Dosage", "type": "string"},
        "frequency": {"title": "Frequency", "type": "string"},
    },
    "documentation": {
        "patient_id": {"title": "HealthOS Patient ID", "type": "string"},
        "note_type": {"title": "Note type", "type": "string"},
        "encounter_id": {"title": "Encounter ID", "type": "string"},
    },
    "policies": {
        "plan_name": {"title": "Plan name", "type": "string"},
        "network": {"title": "Network", "type": "string"},
        "premium": {"title": "Premium", "type": "number"},
    },
    "prior_authorization": {
        "patient_id": {"title": "Patient ID", "type": "string"},
        "service_code": {"title": "Service code", "type": "string"},
        "clinical_rationale": {"title": "Clinical rationale", "type": "string"},
    },
}


def insert_definition(
    bind: sa.Connection,
    *,
    kind: str,
    key: str,
    account_types: list[str],
    schema: dict[str, Any],
    presentation: dict[str, Any],
) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO application_definitions
              (id, kind, key, version, status, account_types, locale, schema,
               presentation, rules, effective_at, published_at)
            VALUES (gen_random_uuid(), :kind, :key, 1, 'published',
                    CAST(:account_types AS jsonb), 'en-US', CAST(:schema AS jsonb),
                    CAST(:presentation AS jsonb), '[]'::jsonb, now(), now())
            """
        ),
        {
            "kind": kind,
            "key": key,
            "account_types": json.dumps(account_types),
            "schema": json.dumps(schema),
            "presentation": json.dumps(presentation),
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    module_rows = bind.execute(
        sa.text(
            """
            SELECT key, account_types FROM application_definitions
            WHERE kind = 'module' AND status = 'published' AND tenant_id IS NULL
            """
        )
    ).all()
    for key, account_types in module_rows:
        insert_definition(
            bind,
            kind="form",
            key=key,
            account_types=list(account_types),
            schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": FORM_PROPERTIES.get(key, {}),
                "additionalProperties": False,
            },
            presentation={"submitLabel": "Save", "layout": "responsive-grid"},
        )

    dashboard_metrics = {
        "patient": ["appointments", "lab_reports", "claims", "health_reminders"],
        "doctor": ["schedule", "patients", "prescriptions", "documentation"],
        "hospital": ["staff", "beds", "billing", "eligibility"],
        "insurance": ["policies", "eligibility", "claims", "prior_authorization"],
        "admin": ["user_management", "audit_logs", "monitoring", "escalations"],
    }
    for role, metrics in dashboard_metrics.items():
        insert_definition(
            bind,
            kind="dashboard",
            key=f"{role}_dashboard",
            account_types=[role],
            schema={"metrics": metrics, "recentLimit": 6},
            presentation={"title": f"{role.title()} overview"},
        )

    insert_definition(
        bind,
        kind="content",
        key="claim_assistance",
        account_types=["patient"],
        schema={
            "title": "Need help with a claim?",
            "body": "Contact the configured claim assistance team.",
            "settingKey": "claim_helpline",
        },
        presentation={"tone": "support"},
    )

    workflow_specs = {
        "appointment_booking": {
            "roles": ["patient", "doctor", "hospital"],
            "states": {
                "draft": {"transitions": [{"action": "hold", "to": "held", "roles": ["patient"]}]},
                "held": {
                    "transitions": [
                        {"action": "confirm", "to": "booked", "roles": ["patient"]},
                        {"action": "expire", "to": "expired", "roles": ["hospital"]},
                    ]
                },
                "booked": {
                    "transitions": [
                        {"action": "complete", "to": "completed", "roles": ["doctor", "hospital"]},
                        {"action": "cancel", "to": "cancelled"},
                    ]
                },
            },
        },
        "claim_review": {
            "roles": ["patient", "hospital", "insurance"],
            "states": {
                "draft": {
                    "transitions": [
                        {"action": "submit", "to": "submitted", "roles": ["patient", "hospital"]}
                    ]
                },
                "submitted": {
                    "transitions": [
                        {
                            "action": "request_information",
                            "to": "information_requested",
                            "roles": ["insurance"],
                        },
                        {"action": "approve", "to": "approved", "roles": ["insurance"]},
                        {"action": "deny", "to": "denied", "roles": ["insurance"]},
                    ]
                },
                "information_requested": {
                    "transitions": [
                        {"action": "resubmit", "to": "submitted", "roles": ["patient", "hospital"]}
                    ]
                },
                "denied": {
                    "transitions": [
                        {"action": "appeal", "to": "appealed", "roles": ["patient", "hospital"]}
                    ]
                },
            },
        },
        "prior_authorization_review": {
            "roles": ["doctor", "hospital", "insurance"],
            "states": {
                "draft": {
                    "transitions": [
                        {"action": "submit", "to": "review", "roles": ["doctor", "hospital"]}
                    ]
                },
                "review": {
                    "transitions": [
                        {"action": "approve", "to": "approved", "roles": ["insurance"]},
                        {"action": "deny", "to": "denied", "roles": ["insurance"]},
                        {
                            "action": "request_information",
                            "to": "information_requested",
                            "roles": ["insurance"],
                        },
                    ]
                },
                "information_requested": {
                    "transitions": [
                        {"action": "resubmit", "to": "review", "roles": ["doctor", "hospital"]}
                    ]
                },
            },
        },
    }
    for key, spec in workflow_specs.items():
        insert_definition(
            bind,
            kind="workflow",
            key=key,
            account_types=spec["roles"],
            schema={"initial": "draft", "states": spec["states"]},
            presentation={"auditReasonRequired": True},
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM application_definitions
        WHERE kind IN ('form', 'dashboard', 'content', 'workflow')
          AND version = 1 AND tenant_id IS NULL AND created_by_user_id IS NULL
        """
    )
