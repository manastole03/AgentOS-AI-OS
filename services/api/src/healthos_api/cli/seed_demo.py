from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cryptography.fernet import Fernet
from sqlalchemy import select, text

from healthos_api.auth.passwords import hash_password
from healthos_api.config import get_settings
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    AuthSession,
    DoctorProfile,
    DocumentAsset,
    IntegrationEvent,
    OAuthIdentity,
    OrganizationProfile,
    OtpChallenge,
    OtpPurpose,
    PatientProfile,
    PortalNotification,
    PortalRecord,
    Role,
    SystemSetting,
    User,
    UserStatus,
)
from healthos_api.db.session import create_database_engine, create_session_factory
from healthos_api.portal.access import PORTAL_MODULES

DEMO_PASSWORD = "Demo@HealthOS2026!"  # noqa: S105
DEMO_NAMESPACE = uuid5(NAMESPACE_URL, "https://healthos.example/demo/v1")


def demo_id(name: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, name)


@dataclass(frozen=True)
class DemoAccount:
    account_type: AccountType
    email: str
    phone: str
    display_name: str
    user_id: UUID


ACCOUNTS = {
    account_type: DemoAccount(
        account_type=account_type,
        email=f"{account_type.value}.demo@healthos.example.com",
        phone=f"+14805550{index:03d}",
        display_name={
            AccountType.PATIENT: "Maya Patel",
            AccountType.DOCTOR: "Dr. Elena Rodriguez",
            AccountType.HOSPITAL: "Desert Valley Medical Center",
            AccountType.INSURANCE: "Sunrise Health Plans",
            AccountType.ADMIN: "Jordan Kim",
        }[account_type],
        user_id=demo_id(f"user:{account_type.value}"),
    )
    for index, account_type in enumerate(AccountType, start=1)
}


@dataclass(frozen=True)
class RecordSpec:
    title: str
    status: str = "active"
    data: dict[str, Any] = field(default_factory=dict)
    amount_cents: int | None = None
    currency: str | None = None
    occurred_days: int | None = None
    due_days: int | None = None
    external_reference: str | None = None


def _patient_specs(document_id: UUID, doctor_id: UUID) -> dict[str, RecordSpec]:
    return {
        "medical_history": RecordSpec(
            "Childhood asthma — resolved",
            "completed",
            {
                "condition": "Childhood asthma",
                "clinical_code": "J45.909",
                "provider": "Mesa Pediatrics",
            },
            occurred_days=-6200,
        ),
        "vitals": RecordSpec(
            "Annual wellness vitals",
            data={
                "weight_kg": 68.2,
                "height_cm": 167,
                "bmi": 24.5,
                "blood_pressure": "118/76",
                "heart_rate": 72,
                "oxygen_saturation": "98%",
                "co2_mm_hg": 40,
            },
            occurred_days=-14,
        ),
        "allergies": RecordSpec(
            "Penicillin allergy",
            data={"allergen": "Penicillin", "reaction": "Hives", "severity": "moderate"},
        ),
        "vaccinations": RecordSpec(
            "Influenza vaccination 2025–26",
            data={
                "vaccine": "Influenza quadrivalent",
                "dose": "Annual dose",
                "lot_number": "FLU25-AZ-1842",
                "certificate_document_id": str(document_id),
                "booster_due": "2026-10-01",
            },
            occurred_days=-250,
            due_days=91,
        ),
        "visits": RecordSpec(
            "Orthopedic consultation",
            "completed",
            {
                "doctor": "Dr. Elena Rodriguez",
                "diagnosis": "Patellofemoral pain syndrome",
                "prescription": "PT-6W-2026",
                "medicines": "Naproxen 250 mg with food for 7 days",
            },
            occurred_days=-7,
        ),
        "medications": RecordSpec(
            "Naproxen short course",
            data={
                "medicine": "Naproxen",
                "dosage": "250 mg with food",
                "times": ["08:00", "20:00"],
                "course_end": "2026-07-09",
            },
            occurred_days=-1,
            due_days=7,
        ),
        "appointments": RecordSpec(
            "Physical therapy evaluation",
            "scheduled",
            {
                "provider": "Desert Valley PT",
                "location": "North Clinic",
                "visit_type": "evaluation",
            },
            amount_cents=4500,
            currency="USD",
            occurred_days=5,
        ),
        "telemedicine": RecordSpec(
            "Medication follow-up video visit",
            "scheduled",
            {
                "provider": "Dr. Elena Rodriguez",
                "session_url": "https://telehealth.example/demo-room",
                "follow_up": "Review pain and mobility",
            },
            occurred_days=12,
        ),
        "lab_reports": RecordSpec(
            "Complete blood count",
            "final",
            {
                "test_name": "CBC",
                "result": "Within normal limits",
                "reference_range": "See attached laboratory ranges",
            },
            occurred_days=-30,
        ),
        "lab_bookings": RecordSpec(
            "Comprehensive metabolic panel",
            "scheduled",
            {"test_name": "CMP", "laboratory": "Desert Valley Lab", "slot": "2026-07-08 08:30"},
            amount_cents=3500,
            currency="USD",
            occurred_days=6,
        ),
        "insurance": RecordSpec(
            "Sunrise Silver PPO — active coverage",
            data={
                "payer": "Sunrise Health Plans",
                "member_id": "SHP-MAYA-2601",
                "plan_name": "Sunrise Silver PPO",
                "plain_language_coverage": (
                    "Primary care is $25, specialists are $50, and in-network hospital care "
                    "is covered after the $1,500 deductible. Prior authorization is required "
                    "for planned surgery."
                ),
                "claim_helpline": "1-800-555-0147",
                "deductible_remaining_cents": 86000,
            },
        ),
        "buy_insurance": RecordSpec(
            "Marketplace comparison saved",
            "draft",
            {
                "plan_name": "Sunrise Gold PPO",
                "payer": "Sunrise Health Plans",
                "loyalty_points_used": 250,
            },
            amount_cents=49200,
            currency="USD",
        ),
        "loyalty_points": RecordSpec(
            "Wellness visit reward",
            "earned",
            {"source": "Annual wellness visit", "points": 750, "balance": 1250},
            occurred_days=-14,
        ),
        "claims": RecordSpec(
            "Orthopedic consultation claim",
            "processing",
            {
                "claim_number": "CLM-2026-004281",
                "payer": "Sunrise Health Plans",
                "service_code": "99204",
                "submitted_amount_cents": 28500,
            },
            amount_cents=28500,
            currency="USD",
            occurred_days=-6,
        ),
        "cost_estimates": RecordSpec(
            "Knee arthroscopy estimate",
            "estimated",
            {
                "service_code": "29881",
                "provider": "Desert Valley Medical Center",
                "estimated_patient_cost": "$1,240–$1,680",
                "disclaimer": "Estimate only; final coverage is determined by the payer.",
            },
            amount_cents=146000,
            currency="USD",
        ),
        "payments": RecordSpec(
            "Physical therapy booking payment",
            "succeeded",
            {
                "provider": "local-demo",
                "payment_reference": "pay_demo_maya_001",
                "description": "Physical therapy copay",
            },
            amount_cents=4500,
            currency="USD",
            occurred_days=-1,
        ),
        "notifications": RecordSpec(
            "Appointment reminder preference",
            data={"channel": "email", "lead_time_hours": 24, "enabled": True},
        ),
        "health_reminders": RecordSpec(
            "Take Naproxen",
            data={
                "reminder_type": "medication",
                "frequency": "daily",
                "time": "08:00",
                "active_until": "2026-07-09",
            },
            due_days=7,
        ),
        "consents": RecordSpec(
            "Treatment access for Dr. Rodriguez",
            data={
                "grantee_user_id": str(doctor_id),
                "scopes": [
                    "visits",
                    "lab_reports",
                    "medications",
                    "medical_history",
                    "allergies",
                    "vitals",
                ],
                "purpose": "treatment",
            },
            due_days=365,
        ),
        "documents": RecordSpec(
            "Vaccination certificate index",
            data={"document_id": str(document_id), "filename": "maya-influenza-certificate.txt"},
        ),
        "ai_assistant": RecordSpec(
            "Care and coverage question",
            "completed",
            {
                "prompt": "Is knee arthroscopy covered and what should I do next?",
                "teams": ["patient", "insurance", "clinical"],
                "safety": "Informational only; not a diagnosis.",
            },
            occurred_days=-1,
        ),
        "growth": RecordSpec(
            "Adult growth and BMI trend",
            data={
                "height_cm": 167,
                "weight_kg": 68.2,
                "bmi": 24.5,
                "bmi_percentile": 62,
                "measurement_source": "clinic",
            },
            occurred_days=-14,
        ),
        "immunizations": RecordSpec(
            "Tdap booster",
            "completed",
            {
                "vaccine": "Tdap",
                "dose_number": 1,
                "series_complete": True,
                "administered_by": "Mesa Community Pharmacy",
                "next_due": "2036-03-18",
            },
            occurred_days=-1200,
        ),
        "adherence": RecordSpec(
            "Naproxen adherence — 30 days",
            data={
                "medication": "Naproxen 500 mg",
                "doses_expected": 60,
                "doses_taken": 55,
                "adherence_percent": 91.7,
                "last_refill": "2026-06-18",
            },
            occurred_days=-30,
        ),
        "care_team": RecordSpec(
            "Primary care team",
            data={
                "primary_care_provider": "Dr. Elena Rodriguez",
                "provider_user_id": str(doctor_id),
                "role": "orthopedic surgeon",
                "care_coordinator": "Priya Nair, RN",
            },
        ),
        "family_history": RecordSpec(
            "Maternal type 2 diabetes",
            data={
                "relative": "mother",
                "condition": "Type 2 diabetes mellitus",
                "clinical_code": "E11.9",
                "age_at_onset": 52,
            },
        ),
        "policies": RecordSpec(
            "Sunrise Silver PPO — member policy",
            data={
                "policy_number": "SUN-PPO-2026-004821",
                "plan_name": "Sunrise Silver PPO",
                "member_id": "SUN884213901",
                "effective_date": "2026-01-01",
                "renewal_date": "2026-12-31",
            },
            due_days=180,
        ),
    }


def _doctor_specs(patient_id: UUID) -> dict[str, RecordSpec]:
    return {
        "schedule": RecordSpec(
            "Dr. Rodriguez — Orthopedics",
            "available",
            {
                "specialty": "Orthopedics",
                "location": "Desert Valley Medical Plaza, Suite 310",
                "visit_type": "new patient",
            },
            22500,
            "USD",
            8,
        ),
        "patients": RecordSpec(
            "Maya Patel care panel",
            data={
                "patient_id": "PATDEMO00000001",
                "care_program": "Knee mobility recovery",
                "risk_level": "low",
            },
        ),
        "prescriptions": RecordSpec(
            "Naproxen 250 mg",
            "signed",
            {
                "patient_id": "PATDEMO00000001",
                "medication": "Naproxen",
                "dosage": "250 mg",
                "frequency": "Twice daily with food",
                "human_reviewed": True,
            },
        ),
        "documentation": RecordSpec(
            "Orthopedic consultation note",
            "signed",
            {
                "patient_id": "PATDEMO00000001",
                "note_type": "consult",
                "encounter_id": "ENC-DEMO-1001",
                "ai_assisted": True,
                "clinician_attested": True,
            },
        ),
        "medical_coding": RecordSpec(
            "Coding review — orthopedic consult",
            "approved",
            {
                "patient_id": "PATDEMO00000001",
                "encounter_id": "ENC-DEMO-1001",
                "suggested_codes": ["M22.2X1", "99204"],
                "human_review_required": True,
            },
        ),
        "referrals": RecordSpec(
            "Physical therapy referral",
            "accepted",
            {
                "patient_id": "PATDEMO00000001",
                "specialty": "Physical Therapy",
                "reason": "Six-week strengthening and mobility program",
            },
        ),
        "care_coordination": RecordSpec(
            "Knee recovery care plan",
            data={
                "patient_id": "PATDEMO00000001",
                "care_plan": "PT twice weekly plus home exercise",
                "next_action": "PT evaluation on July 7",
            },
        ),
        "telemedicine": RecordSpec(
            "Maya Patel follow-up",
            "scheduled",
            {
                "provider": "Dr. Elena Rodriguez",
                "session_url": "https://telehealth.example/demo-room",
                "follow_up": "Reassess after two weeks of PT",
            },
            occurred_days=12,
        ),
        "lab_reports": RecordSpec(
            "Maya Patel pre-procedure labs",
            "reviewed",
            {
                "test_name": "CBC and CMP",
                "result": "No contraindications identified",
                "reference_range": "Laboratory reference ranges",
            },
        ),
        "appointments": RecordSpec(
            "Maya Patel orthopedic follow-up",
            "scheduled",
            {
                "patient_id": "PATDEMO00000001",
                "visit_type": "follow-up",
                "location": "Telemedicine",
            },
            occurred_days=12,
        ),
        "ai_assistant": RecordSpec(
            "Draft follow-up summary",
            "review_required",
            {
                "task": "clinical_documentation",
                "patient_id": "PATDEMO00000001",
                "disclaimer": "AI draft—clinician review and signature required.",
            },
        ),
        "documents": RecordSpec(
            "Referral packet",
            data={"document_type": "referral", "patient_id": "PATDEMO00000001"},
        ),
        "encounters": RecordSpec(
            "Orthopedic follow-up encounter",
            "in_progress",
            {
                "patient_user_id": str(patient_id),
                "encounter_class": "ambulatory",
                "reason": "Right knee pain follow-up",
                "location": "Medical Plaza — Orthopedics",
            },
            occurred_days=-2,
        ),
        "clinical_notes": RecordSpec(
            "Progress note — right knee pain",
            "draft",
            {
                "note_type": "progress",
                "patient_user_id": str(patient_id),
                "subjective": "Improved pain with NSAIDs; mild stiffness after activity.",
                "assessment": "Right knee osteoarthritis, stable.",
                "signature_required": True,
            },
            occurred_days=-2,
        ),
        "lab_orders": RecordSpec(
            "CBC and CMP panel order",
            "ordered",
            {
                "patient_user_id": str(patient_id),
                "panel": ["CBC", "CMP"],
                "priority": "routine",
                "fasting_required": True,
            },
            due_days=5,
        ),
        "prior_authorization": RecordSpec(
            "Knee arthroscopy authorization request",
            "submitted",
            {
                "patient_user_id": str(patient_id),
                "procedure_code": "29881",
                "payer": "Sunrise Health Plans",
                "clinical_justification": "Failed 12 weeks conservative therapy.",
            },
            occurred_days=-1,
        ),
    }


def _hospital_specs(patient_id: UUID) -> dict[str, RecordSpec]:
    return {
        "staff": RecordSpec(
            "Elena Rodriguez, MD",
            data={
                "employee_id": "DVMC-2048",
                "role": "Attending Orthopedic Surgeon",
                "department": "Orthopedics",
            },
        ),
        "departments": RecordSpec(
            "Orthopedics",
            data={
                "department_code": "ORTHO",
                "service_line": "Musculoskeletal care",
                "leader": "Dr. Priya Shah",
            },
        ),
        "beds": RecordSpec(
            "Medical/Surgical bed 4B-12",
            "available",
            {"unit": "4B", "room": "412", "bed_number": "B"},
        ),
        "resources": RecordSpec(
            "Operating Room 3",
            "available",
            {"resource_type": "operating_theater", "capacity": 1, "location": "Surgical Pavilion"},
        ),
        "service_catalog": RecordSpec(
            "Knee arthroscopy",
            "active",
            {
                "service_code": "29881",
                "service_name": "Knee arthroscopy with meniscectomy",
                "availability": "Monday–Friday",
                "requires_prior_authorization": True,
            },
            1860000,
            "USD",
        ),
        "lab_slots": RecordSpec(
            "Desert Valley Laboratory",
            "available",
            {
                "test_code": "CMP",
                "test_name": "Comprehensive metabolic panel",
                "location": "Main Campus Lab",
                "price": 35,
            },
            3500,
            "USD",
            9,
        ),
        "billing": RecordSpec(
            "Invoice DV-2026-8841",
            "submitted",
            {
                "invoice_number": "DV-2026-8841",
                "payer": "Sunrise Health Plans",
                "service_code": "99204",
            },
            28500,
            "USD",
        ),
        "revenue_cycle": RecordSpec(
            "Orthopedics claim follow-up",
            "in_progress",
            {
                "stage": "payer adjudication",
                "owner": "Revenue Integrity Team",
                "days_outstanding": 6,
            },
        ),
        "eligibility": RecordSpec(
            "Maya Patel eligibility verification",
            "verified",
            {
                "member_id": "SHP-MAYA-2601",
                "plan_name": "Sunrise Silver PPO",
                "coverage_date": "2026-07-02",
            },
        ),
        "reports": RecordSpec(
            "June 2026 operating dashboard",
            "published",
            {
                "report_type": "operational",
                "period": "June 2026",
                "occupancy_percent": 78,
                "claim_clean_rate_percent": 94.2,
            },
        ),
        "appointments": RecordSpec(
            "Orthopedic clinic block",
            "scheduled",
            {
                "provider": "Dr. Elena Rodriguez",
                "location": "Medical Plaza",
                "visit_type": "clinic",
            },
            occurred_days=8,
        ),
        "documents": RecordSpec(
            "Facility license and accreditation",
            "verified",
            {"document_type": "facility_license", "license_number": "AZ-HOSP-00421"},
        ),
        "invoices": RecordSpec(
            "Invoice INV-2026-004812 — orthopedic visit",
            "open",
            {
                "invoice_number": "INV-2026-004812",
                "patient_user_id": str(patient_id),
                "line_items": [
                    {"code": "99213", "description": "Office visit, level 3", "cents": 18500},
                    {"code": "73562", "description": "Knee X-ray, 3 views", "cents": 9500},
                ],
                "payer_responsibility_cents": 22400,
                "patient_responsibility_cents": 5600,
            },
            amount_cents=28000,
            currency="USD",
            due_days=30,
        ),
        "claims": RecordSpec(
            "Claim CLM-2026-118342 submitted to Sunrise",
            "submitted",
            {
                "claim_number": "CLM-2026-118342",
                "patient_user_id": str(patient_id),
                "payer": "Sunrise Health Plans",
                "place_of_service": "11",
                "diagnosis_codes": ["M17.11"],
            },
            amount_cents=28000,
            currency="USD",
            occurred_days=-3,
        ),
        "practitioners": RecordSpec(
            "Elena Rodriguez, MD — orthopedic surgery privileges",
            "credentialed",
            {
                "npi": "1740360000",
                "specialty": "Orthopedic surgery",
                "department": "Orthopedics",
                "privileges": ["outpatient_clinic", "arthroscopy"],
                "credentialed_through": "2027-06-30",
            },
        ),
    }


def _insurance_specs(patient_id: UUID) -> dict[str, RecordSpec]:
    return {
        "policies": RecordSpec(
            "Sunrise Silver PPO",
            "active",
            {
                "policy_number": "SHP-SILVER-PPO-2026",
                "plan_name": "Sunrise Silver PPO",
                "payer": "Sunrise Health Plans",
                "coverage_type": "PPO",
                "plain_language_coverage": (
                    "$25 primary care, $50 specialist visits, and 20% coinsurance after a "
                    "$1,500 deductible for in-network hospital services."
                ),
                "recommended_for": ["adult", "moderate specialist use"],
                "excluded_conditions": [],
                "loyalty_discount_points": 500,
            },
            41800,
            "USD",
        ),
        "eligibility": RecordSpec(
            "Maya Patel — active eligibility",
            "verified",
            {
                "member_id": "SHP-MAYA-2601",
                "plan_name": "Sunrise Silver PPO",
                "coverage_date": "2026-07-02",
                "in_network": True,
            },
        ),
        "claims": RecordSpec(
            "Claim CLM-2026-004281",
            "processing",
            {
                "claim_number": "CLM-2026-004281",
                "member_id": "SHP-MAYA-2601",
                "service_code": "99204",
                "completeness_score": 98,
            },
            28500,
            "USD",
        ),
        "prior_authorization": RecordSpec(
            "Knee arthroscopy authorization",
            "clinical_review",
            {
                "member_id": "SHP-MAYA-2601",
                "service_code": "29881",
                "clinical_rationale": "Persistent symptoms after conservative therapy",
                "human_decision_required": True,
            },
        ),
        "cost_estimates": RecordSpec(
            "Knee arthroscopy member estimate",
            "estimated",
            {
                "service_code": "29881",
                "provider": "Desert Valley Medical Center",
                "estimated_patient_cost": "$1,240–$1,680",
                "not_a_guarantee": True,
            },
            146000,
            "USD",
        ),
        "fraud_detection": RecordSpec(
            "Routine claim integrity review",
            "cleared",
            {
                "case_number": "FR-2026-0192",
                "risk_score": 8,
                "signal_type": "duplicate-service check",
                "human_reviewed": True,
            },
        ),
        "documents": RecordSpec(
            "Silver PPO 2026 evidence of coverage",
            "indexed",
            {
                "document_type": "evidence_of_coverage",
                "ocr_status": "complete",
                "classification": "policy_document",
            },
        ),
        "plan_benefits": RecordSpec(
            "Sunrise Silver PPO — 2026 benefit schedule",
            data={
                "plan_name": "Sunrise Silver PPO",
                "network": "in_network",
                "primary_care_copay_cents": 3000,
                "specialist_copay_cents": 5500,
                "coinsurance_percent": 20,
                "requires_prior_authorization": ["arthroscopy", "advanced_imaging"],
            },
        ),
        "accumulators": RecordSpec(
            "2026 deductible and out-of-pocket accumulators",
            data={
                "member_user_id": str(patient_id),
                "plan_year": 2026,
                "deductible_total_cents": 250000,
                "deductible_met_cents": 84000,
                "out_of_pocket_max_cents": 700000,
                "out_of_pocket_met_cents": 121500,
            },
            occurred_days=-1,
        ),
    }


def _admin_specs() -> dict[str, RecordSpec]:
    return {
        "analytics": RecordSpec(
            "Platform service metrics — July 2026",
            data={
                "time_to_appointment_hours": 38,
                "claim_clean_rate_percent": 94.2,
                "coverage_explanations_served": 1824,
            },
        ),
        "audit_logs": RecordSpec(
            "Daily audit-chain verification",
            "passed",
            {
                "core_chain_valid": True,
                "ai_chain_valid": True,
                "verified_at": "2026-07-02T12:00:00Z",
            },
        ),
        "user_management": RecordSpec(
            "Professional credential review queue",
            "open",
            {"pending_doctors": 3, "pending_organizations": 2},
        ),
        "monitoring": RecordSpec(
            "Production dependency health",
            "healthy",
            {"api": "healthy", "ai": "healthy", "database": "healthy", "redis": "healthy"},
        ),
        "system_settings": RecordSpec(
            "Clinical AI human-review policy",
            "enforced",
            {"policy": "clinical_human_review", "enabled": True},
        ),
        "escalations": RecordSpec(
            "Coverage explanation review",
            "assigned",
            {"priority": "medium", "owner": "Benefits Operations", "sla_hours": 8},
        ),
        "support": RecordSpec(
            "Member booking assistance",
            "in_progress",
            {
                "ticket_number": "SUP-2026-1048",
                "channel": "phone",
                "category": "appointment_booking",
            },
        ),
        "documents": RecordSpec(
            "HIPAA readiness evidence index",
            "current",
            {"document_type": "compliance_evidence", "period": "2026-Q2"},
        ),
        "support_cases": RecordSpec(
            "Member unable to download coverage letter",
            "open",
            {
                "case_number": "CASE-2026-0731",
                "channel": "web",
                "category": "documents",
                "priority": "medium",
                "sla_hours": 24,
            },
            due_days=1,
        ),
        "phi_access": RecordSpec(
            "Break-glass PHI access review",
            "reviewed",
            {
                "access_type": "break_glass",
                "records_reviewed": 4,
                "justification_present": True,
                "reviewer": "Privacy Office",
            },
            occurred_days=-2,
        ),
        "data_subject_requests": RecordSpec(
            "Right-of-access export request",
            "in_progress",
            {
                "request_type": "access",
                "regulation": "HIPAA",
                "received_on": "2026-07-28",
                "due_on": "2026-08-27",
                "verification_status": "identity_verified",
            },
            due_days=27,
        ),
    }


def record_specs(
    document_id: UUID, patient_id: UUID, doctor_id: UUID
) -> dict[AccountType, dict[str, RecordSpec]]:
    return {
        AccountType.PATIENT: _patient_specs(document_id, doctor_id),
        AccountType.DOCTOR: _doctor_specs(patient_id),
        AccountType.HOSPITAL: _hospital_specs(patient_id),
        AccountType.INSURANCE: _insurance_specs(patient_id),
        AccountType.ADMIN: _admin_specs(),
    }


async def _seed_users(db: Any, password: str) -> dict[AccountType, User]:
    roles = {role.name: role for role in (await db.scalars(select(Role))).all()}
    if set(roles) != {item.value for item in AccountType}:
        raise RuntimeError("Run the core API Alembic migrations before seeding demo data")

    users: dict[AccountType, User] = {}
    password_hash = hash_password(password)
    for account in ACCOUNTS.values():
        user = await db.get(User, account.user_id)
        if user is None:
            user = await db.scalar(select(User).where(User.email == account.email))
        if user is None:
            user = User(id=account.user_id, email=account.email, account_type=account.account_type)
            db.add(user)
        user.email = account.email
        user.password_hash = password_hash
        user.account_type = account.account_type
        user.status = UserStatus.ACTIVE
        user.email_verified = True
        user.phone_verified = True
        user.roles = [roles[account.account_type.value]]
        users[account.account_type] = user
    await db.flush()

    patient = users[AccountType.PATIENT]
    patient_profile = await db.get(PatientProfile, patient.id)
    if patient_profile is None:
        patient_profile = PatientProfile(
            user_id=patient.id,
            patient_id="PATDEMO00000001",
            first_name="Maya",
            last_name="Patel",
        )
        db.add(patient_profile)
    patient_profile.phone = ACCOUNTS[AccountType.PATIENT].phone
    patient_profile.date_of_birth = date(1991, 4, 18)
    patient_profile.sex_at_birth = "female"
    patient_profile.blood_type = "O+"
    patient_profile.emergency_contact = "Arjun Patel, +1-480-555-0199"

    doctor = users[AccountType.DOCTOR]
    doctor_profile = await db.get(DoctorProfile, doctor.id)
    if doctor_profile is None:
        doctor_profile = DoctorProfile(
            user_id=doctor.id,
            first_name="Elena",
            last_name="Rodriguez",
            license_number="AZ-MD-458291",
        )
        db.add(doctor_profile)
    doctor_profile.phone = ACCOUNTS[AccountType.DOCTOR].phone
    doctor_profile.license_jurisdiction = "Arizona"
    doctor_profile.specialty = "Orthopedic Surgery"
    doctor_profile.affiliation = "Desert Valley Medical Center"
    doctor_profile.credentials_verified = True

    organizations = {
        AccountType.HOSPITAL: {
            "legal_name": "Desert Valley Medical Center",
            "registration_number": "AZ-CORP-778210",
            "license_number": "AZ-HOSP-00421",
            "organization_type": "Acute care hospital",
            "product_types": ["inpatient", "outpatient", "laboratory", "telemedicine"],
        },
        AccountType.INSURANCE: {
            "legal_name": "Sunrise Health Plans",
            "registration_number": "AZ-INS-991204",
            "license_number": "AZ-DOI-HP-2308",
            "organization_type": "Health insurer and policy aggregator",
            "product_types": ["HMO", "PPO", "dental", "vision"],
        },
    }
    for account_type, values in organizations.items():
        user = users[account_type]
        organization_profile = await db.get(OrganizationProfile, user.id)
        if organization_profile is None:
            organization_profile = OrganizationProfile(
                user_id=user.id,
                account_type=account_type,
                legal_name=values["legal_name"],
                registration_number=values["registration_number"],
            )
            db.add(organization_profile)
        organization_profile.license_number = values["license_number"]
        organization_profile.organization_type = values["organization_type"]
        organization_profile.product_types = values["product_types"]
        organization_profile.credentials_verified = True
        organization_profile.phone = ACCOUNTS[account_type].phone
    await db.flush()
    return users


async def _seed_identity_examples(db: Any, users: dict[AccountType, User]) -> None:
    patient = users[AccountType.PATIENT]
    db.add(
        OAuthIdentity(
            id=demo_id("oauth:patient"),
            user_id=patient.id,
            provider="google",
            provider_subject="demo-google-subject-maya-patel",
            provider_email=patient.email,
        )
    ) if await db.get(OAuthIdentity, demo_id("oauth:patient")) is None else None

    db.add(
        OtpChallenge(
            id=demo_id("otp:patient:email"),
            user_id=patient.id,
            email=patient.email,
            purpose=OtpPurpose.EMAIL_VERIFICATION,
            code_hash=hashlib.sha256(b"demo-consumed-otp").hexdigest(),
            attempts=1,
            max_attempts=5,
            expires_at=datetime.now(UTC) - timedelta(days=120),
            consumed_at=datetime.now(UTC) - timedelta(days=120, minutes=1),
        )
    ) if await db.get(OtpChallenge, demo_id("otp:patient:email")) is None else None

    db.add(
        AuthSession(
            id=demo_id("session:patient:expired"),
            user_id=patient.id,
            family_id=demo_id("session-family:patient"),
            refresh_token_hash=hashlib.sha256(b"expired-demo-refresh-token").hexdigest(),
            user_agent="HealthOS demo browser",
            ip_address="127.0.0.1",
            expires_at=datetime.now(UTC) - timedelta(days=90),
            last_used_at=datetime.now(UTC) - timedelta(days=120),
            revoked_at=datetime.now(UTC) - timedelta(days=90),
            revoke_reason="demo_expired",
        )
    ) if await db.get(AuthSession, demo_id("session:patient:expired")) is None else None


async def _seed_documents(db: Any, users: dict[AccountType, User]) -> UUID:
    document_id = demo_id("document:patient:vaccination")
    content = (
        b"DEMO DOCUMENT - Influenza vaccination certificate for Maya Patel. Not for clinical use."
    )
    item = await db.get(DocumentAsset, document_id)
    if item is None:
        item = DocumentAsset(id=document_id)
        db.add(item)
    item.tenant_id = users[AccountType.PATIENT].id
    item.owner_user_id = users[AccountType.PATIENT].id
    item.patient_user_id = users[AccountType.PATIENT].id
    item.category = "vaccination_certificate"
    item.filename = "maya-influenza-certificate.txt"
    item.content_type = "text/plain"
    item.byte_size = len(content)
    item.sha256 = hashlib.sha256(content).hexdigest()
    item.content = content
    item.status = "indexed"
    item.ocr_text = content.decode()
    item.fhir_resource_type = "Immunization"
    item.fhir_resource_id = "imm-demo-maya-flu-2025"
    item.metadata_ = {"demo": True, "issuer": "Desert Valley Medical Center"}
    return document_id


async def _seed_portal_records(db: Any, users: dict[AccountType, User], document_id: UUID) -> int:
    now = datetime.now(UTC).replace(microsecond=0)
    patient_id = users[AccountType.PATIENT].id
    doctor_id = users[AccountType.DOCTOR].id
    specs = record_specs(document_id, patient_id, doctor_id)
    count = 0
    for account_type, account_specs in specs.items():
        missing = set(PORTAL_MODULES[account_type]) - set(account_specs)
        if missing:
            raise RuntimeError(
                f"Demo data is missing {account_type.value} modules: {sorted(missing)}"
            )
        owner = users[account_type]
        for category, spec in account_specs.items():
            record_id = demo_id(f"record:{account_type.value}:{category}")
            record = await db.get(PortalRecord, record_id)
            if record is None:
                record = PortalRecord(id=record_id)
                db.add(record)
            record.tenant_id = owner.id
            record.owner_user_id = owner.id
            record.patient_user_id = patient_id if account_type != AccountType.ADMIN else None
            record.assigned_user_id = (
                doctor_id
                if account_type == AccountType.PATIENT
                and category in {"appointments", "telemedicine", "consents"}
                else None
            )
            record.category = category
            record.title = spec.title
            record.status = spec.status
            record.external_reference = (
                spec.external_reference or f"DEMO-{account_type.value.upper()}-{category.upper()}"
            )
            record.occurred_at = (
                now + timedelta(days=spec.occurred_days) if spec.occurred_days is not None else None
            )
            record.due_at = (
                now + timedelta(days=spec.due_days) if spec.due_days is not None else None
            )
            record.amount_cents = spec.amount_cents
            record.currency = spec.currency
            record.data = {**spec.data, "demo": True}
            count += 1
    return count


async def _seed_supporting_tables(db: Any, users: dict[AccountType, User]) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    for account_type, user in users.items():
        notification_id = demo_id(f"notification:{account_type.value}")
        item = await db.get(PortalNotification, notification_id)
        if item is None:
            item = PortalNotification(id=notification_id)
            db.add(item)
        item.tenant_id = user.id
        item.recipient_user_id = user.id
        item.channel = "in_app"
        item.severity = "success" if account_type == AccountType.PATIENT else "info"
        item.title = {
            AccountType.PATIENT: "Your physical therapy visit is confirmed",
            AccountType.DOCTOR: "One clinical note is ready for signature",
            AccountType.HOSPITAL: "Daily eligibility batch completed",
            AccountType.INSURANCE: "Prior authorization entered clinical review",
            AccountType.ADMIN: "All platform dependencies are healthy",
        }[account_type]
        item.body = f"This is sample {account_type.value} notification data for the HealthOS demo."
        item.action_url = "/dashboard"
        item.delivered_at = now

        integration_id = demo_id(f"integration:{account_type.value}")
        integration = await db.get(IntegrationEvent, integration_id)
        if integration is None:
            integration = IntegrationEvent(id=integration_id)
            db.add(integration)
        integration.tenant_id = user.id
        integration.actor_user_id = user.id
        integration.provider = {
            AccountType.PATIENT: "fhir",
            AccountType.DOCTOR: "fhir",
            AccountType.HOSPITAL: "insurance",
            AccountType.INSURANCE: "ocr",
            AccountType.ADMIN: "notification",
        }[account_type]
        integration.operation = "demo_sync"
        integration.status = "completed"
        integration.external_reference = f"EXT-DEMO-{account_type.value.upper()}"
        integration.request_digest = hashlib.sha256(
            f"demo:{account_type.value}".encode()
        ).hexdigest()
        integration.response_metadata = {"demo": True, "records_processed": 1}

        audit_id = demo_id(f"audit:{account_type.value}")
        if await db.get(AuditEvent, audit_id) is None:
            db.add(
                AuditEvent(
                    id=audit_id,
                    actor_user_id=user.id,
                    event_type="demo.account.seeded",
                    subject_user_id=user.id,
                    ip_address="127.0.0.1",
                    user_agent="healthos-demo-seeder",
                    event_data={"account_type": account_type.value, "demo": True},
                    previous_hash="",
                    event_hash="",
                )
            )

    admin = users[AccountType.ADMIN]
    for key, value, description in [
        (
            "claim_assistance_phone",
            {"value": "1-800-555-0147"},
            "Patient claim-assistance helpline",
        ),
        (
            "clinical_ai_human_review",
            {"required": True},
            "Require accountable clinician review for clinical AI output",
        ),
        (
            "demo_mode",
            {"enabled": True, "synthetic_data_only": True},
            "Marks this installation as a synthetic demonstration environment",
        ),
    ]:
        setting = await db.get(SystemSetting, key)
        if setting is None:
            setting = SystemSetting(key=key)
            db.add(setting)
        setting.value = value
        setting.description = description
        setting.updated_by_user_id = admin.id


async def _seed_ai_tables(db: Any, users: dict[AccountType, User]) -> None:
    exists = await db.scalar(text("SELECT to_regclass('public.ai_agent_runs')"))
    if exists is None:
        raise RuntimeError("Run the AI Alembic migrations before seeding demo data")

    patient = users[AccountType.PATIENT]
    run_id = demo_id("ai:run:knee-care")
    thread_id = demo_id("ai:thread:knee-care")
    prompt = (
        "I need knee surgery—is it covered, what might it cost, and can you find an "
        "orthopedic appointment?"
    )
    response = (
        "Your Sunrise Silver PPO may cover medically necessary in-network knee surgery "
        "after deductible and coinsurance. Prior authorization is required. A cost estimate "
        "and orthopedic slot are available; final coverage must be confirmed by the payer. "
        "This is informational and not a diagnosis."
    )
    key = os.getenv("AI_DATA_ENCRYPTION_KEY", "aGVhbHRob3MtbG9jYWwtYWkta2V5LTMyLWJ5dGVzISE=")
    cipher = Fernet(key.encode())
    params = {
        "id": run_id,
        "thread_id": thread_id,
        "owner_user_id": patient.id,
        "tenant_id": str(patient.id),
        "input": cipher.encrypt(prompt.encode()),
        "output": cipher.encrypt(response.encode()),
        "digest": hashlib.sha256(prompt.encode()).hexdigest(),
        "now": datetime.now(UTC),
        "collaborators": json.dumps(["eligibility_verification", "cost_estimation", "appointment"]),
    }
    await db.execute(
        text(
            """
            INSERT INTO ai_agent_runs
              (id, thread_id, owner_user_id, tenant_id, account_type, status, execution_mode,
               requested_team, selected_team, collaborators, provider_preference, memory_mode,
               input_ciphertext, output_ciphertext, input_digest, prompt_tokens,
               completion_tokens, cost_usd, started_at, completed_at)
            VALUES
              (:id, :thread_id, :owner_user_id, :tenant_id, 'patient', 'completed', 'sync',
               NULL, 'patient', CAST(:collaborators AS jsonb), 'auto', 'read_write',
               :input, :output, :digest, 24, 73, 0.0042, :now, :now)
            ON CONFLICT (id) DO UPDATE SET
              status = EXCLUDED.status, output_ciphertext = EXCLUDED.output_ciphertext,
              collaborators = EXCLUDED.collaborators, completed_at = EXCLUDED.completed_at
            """
        ),
        params,
    )

    message_id = demo_id("ai:message:patient-to-insurance")
    await db.execute(
        text(
            """
            INSERT INTO ai_agent_messages
              (id, run_id, sender_team, recipient_team, message_ciphertext)
            VALUES (:id, :run_id, 'patient', 'insurance', :message)
            ON CONFLICT (id) DO UPDATE SET message_ciphertext = EXCLUDED.message_ciphertext
            """
        ),
        {
            "id": message_id,
            "run_id": run_id,
            "message": cipher.encrypt(
                b"Verify eligibility, authorization rules, and member cost for CPT 29881."
            ),
        },
    )

    document_id = demo_id("ai:knowledge:silver-ppo")
    content = (
        "Sunrise Silver PPO: specialist copay $50; planned surgery requires prior "
        "authorization; in-network hospital services have 20% coinsurance after deductible."
    )
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    await db.execute(
        text(
            """
            INSERT INTO ai_knowledge_documents
              (id, tenant_id, owner_user_id, team, title, source_uri, content_hash,
               metadata, chunk_count)
            VALUES (:id, :tenant_id, :owner_user_id, 'insurance',
                    'Sunrise Silver PPO benefit summary',
                    'demo://policies/sunrise-silver-ppo', :content_hash,
                    CAST(:metadata AS jsonb), 1)
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title, metadata = EXCLUDED.metadata, chunk_count = 1
            """
        ),
        {
            "id": document_id,
            "tenant_id": str(patient.id),
            "owner_user_id": patient.id,
            "content_hash": content_hash,
            "metadata": json.dumps({"demo": True, "document_type": "benefit_summary"}),
        },
    )
    vector = "[" + ",".join(["0"] * 1536) + "]"
    await db.execute(
        text(
            """
            INSERT INTO ai_knowledge_chunks
              (id, document_id, tenant_id, team, chunk_index, content, token_estimate, embedding)
            VALUES (:id, :document_id, :tenant_id, 'insurance', 0, :content, 29,
                    CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
              content = EXCLUDED.content, token_estimate = EXCLUDED.token_estimate
            """
        ),
        {
            "id": demo_id("ai:chunk:silver-ppo:0"),
            "document_id": document_id,
            "tenant_id": str(patient.id),
            "content": content,
            "embedding": vector,
        },
    )
    memory = (
        "Maya prefers morning appointments and has consented to care-navigation memory "
        "for this demo."
    )
    await db.execute(
        text(
            """
            INSERT INTO ai_long_term_memories
              (id, tenant_id, owner_user_id, team, category, content, content_hash, embedding,
               salience, access_count, last_accessed_at)
            VALUES (:id, :tenant_id, :owner_user_id, 'patient', 'preference', :content,
                    :content_hash, CAST(:embedding AS vector), 0.8, 2, :now)
            ON CONFLICT (id) DO UPDATE SET
              content = EXCLUDED.content, access_count = EXCLUDED.access_count
            """
        ),
        {
            "id": demo_id("ai:memory:patient:appointment-preference"),
            "tenant_id": str(patient.id),
            "owner_user_id": patient.id,
            "content": memory,
            "content_hash": hashlib.sha256(memory.encode()).hexdigest(),
            "embedding": vector,
            "now": datetime.now(UTC),
        },
    )

    audit_id = demo_id("ai:audit:run-completed")
    found = await db.scalar(
        text("SELECT 1 FROM ai_agent_audit_events WHERE id = :id"), {"id": audit_id}
    )
    if found is None:
        await db.execute(
            text(
                """
                INSERT INTO ai_agent_audit_events
                  (id, run_id, actor_user_id, tenant_id, event_type, team, agent, model_alias,
                   duration_ms, success, details, previous_hash, event_hash)
                VALUES (:id, :run_id, :actor_user_id, :tenant_id, 'run.completed', 'patient',
                        'patient_assistant', 'healthos-demo', 842.5, true,
                        CAST(:details AS jsonb), '', '')
                """
            ),
            {
                "id": audit_id,
                "run_id": run_id,
                "actor_user_id": patient.id,
                "tenant_id": str(patient.id),
                "details": json.dumps(
                    {"demo": True, "collaborator_count": 3, "safety_review": "passed"}
                ),
            },
        )


async def seed_demo(password: str) -> dict[str, int]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    factory = create_session_factory(engine)
    try:
        async with factory() as db:
            users = await _seed_users(db, password)
            await _seed_identity_examples(db, users)
            document_id = await _seed_documents(db, users)
            record_count = await _seed_portal_records(db, users, document_id)
            await _seed_supporting_tables(db, users)
            await db.flush()
            await _seed_ai_tables(db, users)
            await db.commit()
            return {
                "users": len(users),
                "portal_records": record_count,
                "documents": 1,
                "notifications": len(users),
                "integrations": len(users),
                "ai_runs": 1,
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a complete synthetic HealthOS demo dataset")
    parser.add_argument(
        "--password",
        default=os.getenv("HEALTHOS_DEMO_PASSWORD", DEMO_PASSWORD),
        help="Shared demo password (or set HEALTHOS_DEMO_PASSWORD)",
    )
    args = parser.parse_args()
    if len(args.password) < 12:
        raise SystemExit("Demo password must contain at least 12 characters")
    summary = asyncio.run(seed_demo(args.password))
    print("HealthOS demo data is ready (synthetic data only).")  # noqa: T201
    print(json.dumps(summary, indent=2, sort_keys=True))  # noqa: T201
    print("Accounts: " + ", ".join(account.email for account in ACCOUNTS.values()))  # noqa: T201


if __name__ == "__main__":
    main()
