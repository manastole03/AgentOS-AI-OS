from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from healthos_api.db.base import Base


class AccountType(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    HOSPITAL = "hospital"
    INSURANCE = "insurance"
    ADMIN = "admin"


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class OtpPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    MOBILE_VERIFICATION = "mobile_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105


class EncounterClass(StrEnum):
    AMB = "AMB"
    IMP = "IMP"
    EMER = "EMER"
    VR = "VR"
    HH = "HH"


class EncounterStatus(StrEnum):
    PLANNED = "planned"
    ARRIVED = "arrived"
    IN_PROGRESS = "in-progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"


class ObservationStatus(StrEnum):
    REGISTERED = "registered"
    PRELIMINARY = "preliminary"
    FINAL = "final"
    AMENDED = "amended"
    CORRECTED = "corrected"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"


class ConditionCategory(StrEnum):
    PROBLEM_LIST_ITEM = "problem-list-item"
    ENCOUNTER_DIAGNOSIS = "encounter-diagnosis"


class ClinicalStatus(StrEnum):
    ACTIVE = "active"
    RECURRENCE = "recurrence"
    RELAPSE = "relapse"
    INACTIVE = "inactive"
    REMISSION = "remission"
    RESOLVED = "resolved"


class VerificationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    PROVISIONAL = "provisional"
    DIFFERENTIAL = "differential"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    ENTERED_IN_ERROR = "entered-in-error"


class AllergyVerificationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    PRESUMED = "presumed"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    ENTERED_IN_ERROR = "entered-in-error"


class AllergyType(StrEnum):
    ALLERGY = "allergy"
    INTOLERANCE = "intolerance"


class AllergyCategory(StrEnum):
    FOOD = "food"
    MEDICATION = "medication"
    ENVIRONMENT = "environment"
    BIOLOGIC = "biologic"


class Criticality(StrEnum):
    LOW = "low"
    HIGH = "high"
    UNABLE_TO_ASSESS = "unable-to-assess"


class ReactionSeverity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class AsserterType(StrEnum):
    PATIENT = "patient"
    PRACTITIONER = "practitioner"
    RELATED_PERSON = "related-person"


class MedicationRequestStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on-hold"
    STOPPED = "stopped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"


class MedicationRequestIntent(StrEnum):
    PROPOSAL = "proposal"
    PLAN = "plan"
    ORDER = "order"
    ORIGINAL_ORDER = "original-order"
    INSTANCE_ORDER = "instance-order"


class MedicationStatementStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    NOT_TAKEN = "not-taken"
    INTENDED = "intended"
    STOPPED = "stopped"
    ENTERED_IN_ERROR = "entered-in-error"


class AdherenceStatus(StrEnum):
    TAKEN = "taken"
    NOT_TAKEN = "not-taken"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"
    ENTERED_IN_ERROR = "entered-in-error"


class ImmunizationStatus(StrEnum):
    COMPLETED = "completed"
    NOT_DONE = "not-done"
    ENTERED_IN_ERROR = "entered-in-error"


class NoteStatus(StrEnum):
    DRAFT = "draft"
    PRELIMINARY = "preliminary"
    FINAL = "final"
    AMENDED = "amended"
    ENTERED_IN_ERROR = "entered-in-error"


class SlotStatus(StrEnum):
    OPEN = "open"
    HELD = "held"
    BOOKED = "booked"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class AppointmentStatus(StrEnum):
    REQUESTED = "requested"
    PENDING_PAYMENT = "pending-payment"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked-in"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    NO_SHOW = "no-show"


class ReferralStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    EXPIRED = "expired"


class ProvenanceSource(StrEnum):
    PATIENT_REPORTED = "patient-reported"
    PRACTITIONER = "practitioner"
    DEVICE = "device"
    IMPORTED = "imported"
    AI_EXTRACTED = "ai-extracted"


class PrescriptionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered_in_error"


class MedicationScheduleStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPPRESSED = "suppressed"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class CertificateStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class EncounterChannel(StrEnum):
    IN_PERSON = "in_person"
    TELEHEALTH = "telehealth"


class LabOrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    COLLECTED = "collected"
    IN_PROCESS = "in_process"
    RESULTED = "resulted"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered_in_error"


class LabPriority(StrEnum):
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT = "stat"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    REQUIRES_ACTION = "requires_action"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(StrEnum):
    CARD = "card"
    WALLET = "wallet"
    BANK = "bank"
    CASH = "cash"
    LOYALTY = "loyalty"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LoyaltyEntryType(StrEnum):
    ACCRUAL = "accrual"
    REDEMPTION = "redemption"
    EXPIRY = "expiry"
    ADJUSTMENT = "adjustment"


class PolicyStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    LAPSED = "lapsed"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"


class PolicyApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDERWRITING = "underwriting"
    APPROVED = "approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    ISSUED = "issued"


class MemberRelationship(StrEnum):
    SELF = "self"
    SPOUSE = "spouse"
    CHILD = "child"
    OTHER = "other"


class PremiumFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class NetworkTier(StrEnum):
    IN_NETWORK = "in_network"
    OUT_OF_NETWORK = "out_of_network"


class BenefitLimitPeriod(StrEnum):
    PER_YEAR = "per_year"
    PER_VISIT = "per_visit"
    LIFETIME = "lifetime"


class AccumulatorType(StrEnum):
    INDIVIDUAL_DEDUCTIBLE = "individual_deductible"
    FAMILY_DEDUCTIBLE = "family_deductible"
    INDIVIDUAL_OOP = "individual_oop"
    FAMILY_OOP = "family_oop"
    VISIT_LIMIT = "visit_limit"


class EligibilityStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ClaimType(StrEnum):
    PROFESSIONAL = "professional"
    INSTITUTIONAL = "institutional"
    DENTAL = "dental"
    PHARMACY = "pharmacy"


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PENDED = "pended"
    ADJUDICATED = "adjudicated"
    PAID = "paid"
    DENIED = "denied"
    APPEALED = "appealed"


class PriorAuthStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDED = "pended"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    APPEALED = "appealed"
    EXPIRED = "expired"


class SafetyCheckType(StrEnum):
    DRUG_ALLERGY = "drug_allergy"
    DRUG_DRUG = "drug_drug"
    DUPLICATE_THERAPY = "duplicate_therapy"
    DOSE_RANGE = "dose_range"
    DRUG_CONDITION = "drug_condition"


class SafetyCheckOutcome(StrEnum):
    NO_ALERT = "no_alert"
    ALERTED = "alerted"
    OVERRIDDEN = "overridden"


class CodeType(StrEnum):
    DIAGNOSIS = "diagnosis"
    PROCEDURE = "procedure"
    HCPCS = "hcpcs"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class PhiAccessAction(StrEnum):
    READ = "read"
    EXPORT = "export"
    PRINT = "print"
    SEARCH = "search"


class SupportSeverity(StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class SupportStatus(StrEnum):
    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CommentVisibility(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class DsrType(StrEnum):
    ACCESS = "access"
    RECTIFICATION = "rectification"
    ERASURE = "erasure"
    PORTABILITY = "portability"
    RESTRICTION = "restriction"


class DsrStatus(StrEnum):
    RECEIVED = "received"
    VERIFYING = "verifying"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"


class GrowthSource(StrEnum):
    WHO = "WHO"
    CDC = "CDC"


class GrowthMeasure(StrEnum):
    HEIGHT_FOR_AGE = "height_for_age"
    WEIGHT_FOR_AGE = "weight_for_age"
    BMI_FOR_AGE = "bmi_for_age"
    HC_FOR_AGE = "hc_for_age"
    WEIGHT_FOR_HEIGHT = "weight_for_height"


class BiologicalSex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class DocumentLinkType(StrEnum):
    EVIDENCE = "evidence"
    REPORT = "report"
    CERTIFICATE = "certificate"
    ATTACHMENT = "attachment"
    RECEIPT = "receipt"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        index=True,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, values_callable=enum_values, native_enum=False, length=32),
        default=UserStatus.PENDING_VERIFICATION,
        index=True,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles", back_populates="users", lazy="selectin"
    )
    patient_profile: Mapped[PatientProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    doctor_profile: Mapped[DoctorProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    organization_profile: Mapped[OrganizationProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class PatientProfile(TimestampMixin, Base):
    __tablename__ = "patient_profiles"
    __table_args__ = (
        CheckConstraint("char_length(patient_id) = 15", name="patient_id_length"),
        CheckConstraint("patient_id ~ '^PAT[A-Z0-9]{12}$'", name="patient_id_format"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    patient_id: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    date_of_birth: Mapped[date | None] = mapped_column()
    sex_at_birth: Mapped[str | None] = mapped_column(String(32))
    blood_type: Mapped[str | None] = mapped_column(String(8))
    emergency_contact: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="patient_profile")


class DoctorProfile(TimestampMixin, Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    license_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    license_jurisdiction: Mapped[str | None] = mapped_column(String(100))
    specialty: Mapped[str | None] = mapped_column(String(150))
    affiliation: Mapped[str | None] = mapped_column(String(255))
    credentials_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="doctor_profile")


class OrganizationProfile(TimestampMixin, Base):
    __tablename__ = "organization_profiles"
    __table_args__ = (
        UniqueConstraint("account_type", "registration_number"),
        CheckConstraint(
            "account_type IN ('hospital', 'insurance')", name="organization_account_type"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100))
    organization_type: Mapped[str | None] = mapped_column(String(100))
    product_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    credentials_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    user: Mapped[User] = relationship(back_populates="organization_profile")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")
    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class OAuthIdentity(TimestampMixin, Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str] = mapped_column(CITEXT(), nullable=False)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (Index("ix_otp_active_lookup", "email", "purpose", "consumed_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    purpose: Mapped[OtpPurpose] = mapped_column(
        Enum(OtpPurpose, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_session_family", "family_id", "revoked_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    family_id: Mapped[UUID] = mapped_column(nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(100))
    replaced_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    subject_user_id: Mapped[UUID | None] = mapped_column(index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class PortalRecord(TimestampMixin, Base):
    """Tenant-scoped operational record with a stable envelope and typed payload."""

    __tablename__ = "portal_records"
    __table_args__ = (
        Index("ix_portal_records_scope", "tenant_id", "category", "created_at"),
        Index("ix_portal_records_patient", "patient_user_id", "category"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="active")
    external_reference: Mapped[str | None] = mapped_column(String(255), index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DocumentAsset(TimestampMixin, Base):
    __tablename__ = "document_assets"
    __table_args__ = (Index("ix_documents_scope", "tenant_id", "category", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="stored")
    ocr_text: Mapped[str | None] = mapped_column(Text)
    fhir_resource_type: Mapped[str | None] = mapped_column(String(100))
    fhir_resource_id: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


class PortalNotification(Base):
    __tablename__ = "portal_notifications"
    __table_args__ = (Index("ix_notifications_recipient", "recipient_user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="in_app")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(2048))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JobWatchProfile(TimestampMixin, Base):
    __tablename__ = "job_watch_profiles"
    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint(
            "check_interval_minutes >= 1 AND check_interval_minutes <= 1440",
            name="job_watch_interval_bounds",
        ),
        Index("ix_job_watch_profile_enabled", "enabled", "email_enabled"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    titles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="selectin")
    sources: Mapped[list[JobWatchSource]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JobWatchSource(TimestampMixin, Base):
    __tablename__ = "job_watch_sources"
    __table_args__ = (
        UniqueConstraint("profile_id", "source_type", "board_key"),
        CheckConstraint(
            "source_type IN ('greenhouse', 'lever', 'ashby')",
            name="job_watch_source_type",
        ),
        Index("ix_job_watch_source_enabled", "profile_id", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_watch_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    board_key: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    board_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    initial_sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(String(500))

    profile: Mapped[JobWatchProfile] = relationship(back_populates="sources")


class JobWatchPosting(Base):
    __tablename__ = "job_watch_postings"
    __table_args__ = (
        UniqueConstraint("source_type", "board_key", "external_job_id"),
        CheckConstraint(
            "source_type IN ('greenhouse', 'lever', 'ashby')",
            name="job_watch_posting_source_type",
        ),
        Index("ix_job_watch_posting_active", "source_type", "board_key", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    board_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    employment_type: Mapped[str | None] = mapped_column(String(64))
    workplace_type: Mapped[str | None] = mapped_column(String(64))
    description_text: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class JobWatchAlertDelivery(Base):
    __tablename__ = "job_watch_alert_deliveries"
    __table_args__ = (
        UniqueConstraint("profile_id", "posting_id", "channel"),
        Index("ix_job_watch_delivery_recipient", "recipient_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_watch_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    posting_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_watch_postings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent")
    matched_title: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    __table_args__ = (Index("ix_integration_scope", "tenant_id", "provider", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class Organization(TimestampMixin, Base):
    """A durable tenant boundary; patients may participate through scoped consent."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active", nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class OrganizationMembership(TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_membership"),
        Index("ix_membership_user_status", "user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ConsentGrant(TimestampMixin, Base):
    __tablename__ = "consent_grants"
    __table_args__ = (
        Index("ix_consent_patient_status", "patient_user_id", "status"),
        Index("ix_consent_grantee_scope", "grantee_user_id", "grantee_organization_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    grantee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    grantee_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ApplicationDefinition(TimestampMixin, Base):
    """Versioned runtime UI/workflow/content configuration."""

    __tablename__ = "application_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "kind", "key", "version", name="uq_application_definition_version"
        ),
        Index("ix_definition_lookup", "tenant_id", "kind", "key", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID | None] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True, nullable=False)
    account_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    presentation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("application_definitions.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class WorkflowInstance(TimestampMixin, Base):
    __tablename__ = "workflow_instances"
    __table_args__ = (Index("ix_workflow_scope", "tenant_id", "definition_key", "status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("application_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    definition_key: Mapped[str] = mapped_column(String(100), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class WorkflowTask(TimestampMixin, Base):
    __tablename__ = "workflow_tasks"
    __table_args__ = (Index("ix_workflow_task_queue", "tenant_id", "status", "due_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    workflow_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True, nullable=False)
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_role: Mapped[str | None] = mapped_column(String(64))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "actor_user_id", "operation", "key"),
        Index("ix_idempotency_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_delivery", "status", "available_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CodeSystem(TimestampMixin, Base):
    """Versioned terminology registry; one row per code system release."""

    __tablename__ = "code_systems"
    __table_args__ = (
        UniqueConstraint("uri", "version"),
        Index("ix_code_system_lookup", "uri", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    uri: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255))
    oid: Mapped[str | None] = mapped_column(String(64))
    released_at: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CodeConcept(TimestampMixin, Base):
    """Immutable concept version; never mutate, insert a row and set effective_to."""

    __tablename__ = "code_concepts"
    __table_args__ = (
        UniqueConstraint("code_system_id", "code", "effective_from"),
        Index("ix_code_concepts_lookup", "code_system_id", "code", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code_system_id: Mapped[UUID] = mapped_column(
        ForeignKey("code_systems.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display: Mapped[str] = mapped_column(String(500), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    parent_code: Mapped[str | None] = mapped_column(String(64))
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class PatientIdentifier(TimestampMixin, Base):
    """MRN / health id / payer member id cross-reference for a single human."""

    __tablename__ = "patient_identifiers"
    __table_args__ = (
        UniqueConstraint("system", "value"),
        CheckConstraint(
            "type_code IN ('MR','NI','PPN','DL','MB')",
            name="patient_identifier_type",
        ),
        Index("ix_patient_identifier_patient", "patient_user_id", "is_active"),
        Index("ix_patient_identifier_scope", "tenant_id", "system"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    system: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    type_code: Mapped[str] = mapped_column(String(16), nullable=False)
    assigner_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PractitionerIdentifier(TimestampMixin, Base):
    """NPI / DEA / state licence numbers backing controlled-substance prescribing."""

    __tablename__ = "practitioner_identifiers"
    __table_args__ = (
        UniqueConstraint("system", "value"),
        CheckConstraint(
            "type_code IN ('NPI','DEA','LIC','TAX')",
            name="practitioner_identifier_type",
        ),
        Index("ix_practitioner_identifier_scope", "tenant_id", "type_code", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    practitioner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    system: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    type_code: Mapped[str] = mapped_column(String(16), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(8))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PatientCommunicationPreference(TimestampMixin, Base):
    """Per-patient IANA timezone and notification channel preferences."""

    __tablename__ = "patient_communication_preferences"
    __table_args__ = (
        CheckConstraint(
            "(quiet_hours_start IS NULL) = (quiet_hours_end IS NULL)",
            name="quiet_hours_pair",
        ),
        Index("ix_comm_pref_scope", "tenant_id", "timezone"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["in_app"], nullable=False)
    medication_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    appointment_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )


class GrowthReferenceStandard(TimestampMixin, Base):
    """WHO/CDC L-M-S growth curves; percentile maths is inert until seeded."""

    __tablename__ = "growth_reference_standards"
    __table_args__ = (
        UniqueConstraint("source", "measure", "sex", "age_unit", "age_value"),
        CheckConstraint("age_unit IN ('day','month')", name="growth_age_unit"),
        CheckConstraint("age_value >= 0", name="growth_age_nonneg"),
        CheckConstraint("s > 0", name="growth_sigma_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[GrowthSource] = mapped_column(
        Enum(GrowthSource, values_callable=enum_values, native_enum=False, length=8), nullable=False
    )
    measure: Mapped[GrowthMeasure] = mapped_column(
        Enum(GrowthMeasure, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    sex: Mapped[BiologicalSex] = mapped_column(
        Enum(BiologicalSex, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    age_unit: Mapped[str] = mapped_column(String(8), nullable=False)
    age_value: Mapped[int] = mapped_column(Integer, nullable=False)
    l: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)  # noqa: E741
    m: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    s: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    p3: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    p50: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    p97: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_department_scope", "tenant_id", "organization_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    cost_center: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PractitionerRole(TimestampMixin, Base):
    """Directory source of truth for practitioner affiliation and privileges."""

    __tablename__ = "practitioner_roles"
    __table_args__ = (
        UniqueConstraint("practitioner_user_id", "organization_id", "role_code"),
        CheckConstraint(
            "credentialing_status IN ('pending','active','suspended','expired','revoked')",
            name="credentialing_status",
        ),
        Index("ix_practitioner_role_scope", "tenant_id", "specialty_code", "is_active"),
        Index(
            "ix_practitioner_role_directory",
            "organization_id",
            "specialty_code",
            "accepts_new_patients",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    practitioner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    specialty_code: Mapped[str | None] = mapped_column(String(64))
    taxonomy_code: Mapped[str | None] = mapped_column(String(32))
    privileges: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    credentialing_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    credentialed_at: Mapped[date | None] = mapped_column(Date)
    credential_expires_at: Mapped[date | None] = mapped_column(Date, index=True)
    accepts_new_patients: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceItem(TimestampMixin, Base):
    """Chargemaster entry: the billable service catalogue."""

    __tablename__ = "service_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "service_code", "effective_from"),
        CheckConstraint("base_price_cents >= 0", name="service_price_nonneg"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="service_currency_iso4217"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="service_effective_period",
        ),
        Index("ix_service_item_scope", "tenant_id", "organization_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    service_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    service_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    service_display: Mapped[str] = mapped_column(String(255), nullable=False)
    service_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    cpt_code: Mapped[str | None] = mapped_column(String(16))
    revenue_code: Mapped[str | None] = mapped_column(String(16))
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PayerContractRate(TimestampMixin, Base):
    """Negotiated allowed amounts; the source cost estimates price against."""

    __tablename__ = "payer_contract_rates"
    __table_args__ = (
        UniqueConstraint(
            "payer_organization_id", "provider_organization_id", "service_code", "effective_from"
        ),
        CheckConstraint("allowed_cents >= 0", name="contract_rate_nonneg"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="contract_currency_iso4217"),
        Index("ix_contract_rate_lookup", "payer_organization_id", "service_code", "effective_from"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    payer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    provider_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    service_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    service_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    service_display: Mapped[str] = mapped_column(String(255), nullable=False)
    service_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    allowed_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class ProviderSchedule(TimestampMixin, Base):
    """Recurring availability template a slot generator expands."""

    __tablename__ = "provider_schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="schedule_day_of_week"),
        CheckConstraint("end_time > start_time", name="schedule_time_order"),
        CheckConstraint("slot_minutes BETWEEN 5 AND 480", name="schedule_slot_minutes"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="schedule_valid_period",
        ),
        Index("ix_provider_schedule_scope", "tenant_id", "provider_user_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    provider_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[EncounterChannel] = mapped_column(
        Enum(EncounterChannel, values_callable=enum_values, native_enum=False, length=16),
        default=EncounterChannel.IN_PERSON,
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AppointmentSlot(TimestampMixin, Base):
    __tablename__ = "appointment_slots"
    __table_args__ = (
        UniqueConstraint("provider_user_id", "start_at", name="uq_appointment_slot_provider_start"),
        CheckConstraint("end_at > start_at", name="slot_period"),
        CheckConstraint("capacity >= 1", name="slot_capacity_positive"),
        CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="slot_capacity_bounds",
        ),
        CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="slot_currency_required",
        ),
        Index("ix_slot_scope", "tenant_id", "start_at", "status"),
        Index("ix_slot_open", "tenant_id", "start_at", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    provider_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_schedules.id", ondelete="SET NULL")
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, values_callable=enum_values, native_enum=False, length=32),
        default=SlotStatus.OPEN,
        nullable=False,
    )
    channel: Mapped[EncounterChannel] = mapped_column(
        Enum(EncounterChannel, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "payment_status IN ('unpaid','authorized','paid','refunded')",
            name="appointment_payment_status",
        ),
        Index("ix_appointment_scope", "tenant_id", "status", "booked_at"),
        Index("ix_appointment_patient", "patient_user_id", "status"),
        Index(
            "ix_appointment_slot_booked",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('confirmed','checked-in','fulfilled')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointment_slots.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    provider_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="SET NULL"), index=True
    )
    referral_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("referrals.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[EncounterChannel] = mapped_column(
        Enum(EncounterChannel, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, values_callable=enum_values, native_enum=False, length=32),
        default=AppointmentStatus.REQUESTED,
        nullable=False,
    )
    payment_status: Mapped[str] = mapped_column(String(16), default="unpaid", nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    cancellation_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppointmentStatusEvent(Base):
    __tablename__ = "appointment_status_events"
    __table_args__ = (Index("ix_appointment_event_timeline", "appointment_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Encounter(TimestampMixin, Base):
    """The clinical spine: every clinical child row points back at an encounter."""

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="encounter_period"),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="encounter_confidence_range",
        ),
        Index("ix_encounter_patient", "patient_user_id", "started_at"),
        Index("ix_encounter_scope", "tenant_id", "class_code", "started_at"),
        Index("ix_encounter_practitioner", "primary_practitioner_user_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    primary_practitioner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), index=True
    )
    class_code: Mapped[EncounterClass] = mapped_column(
        Enum(EncounterClass, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[EncounterStatus] = mapped_column(
        Enum(EncounterStatus, values_callable=enum_values, native_enum=False, length=32),
        default=EncounterStatus.PLANNED,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    reason_text: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str | None] = mapped_column(String(64))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelehealthSession(TimestampMixin, Base):
    __tablename__ = "telehealth_sessions"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="telehealth_period"),
        CheckConstraint(
            "recording_asset_id IS NULL OR recording_consent",
            name="telehealth_recording_consent",
        ),
        Index("ix_telehealth_scope", "tenant_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    appointment_id: Mapped[UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    provider_room_id: Mapped[str] = mapped_column(String(255), nullable=False)
    join_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    recording_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recording_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )
    connection_quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    licensure_state: Mapped[str | None] = mapped_column(String(8))
    licensure_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Condition(TimestampMixin, Base):
    """Problem list entry, SNOMED CT primary coding, consent-scoped on read."""

    __tablename__ = "conditions"
    __table_args__ = (
        CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="condition_onset_precision",
        ),
        CheckConstraint(
            "abatement_precision IS NULL OR abatement_precision IN ('day','month','year')",
            name="condition_abatement_precision",
        ),
        CheckConstraint(
            "onset_date IS NULL OR onset_precision IS NOT NULL",
            name="condition_onset_precision_required",
        ),
        CheckConstraint(
            "abatement_date IS NULL OR abatement_date >= onset_date",
            name="condition_abatement_order",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="condition_confidence_range",
        ),
        CheckConstraint(
            "source <> 'ai-extracted' OR verification_status <> 'confirmed' OR "
            "human_verified_at IS NOT NULL",
            name="condition_ai_human_verified",
        ),
        CheckConstraint("version >= 1", name="condition_version_positive"),
        Index("ix_condition_patient", "patient_user_id", "clinical_status", "recorded_at"),
        Index("ix_condition_scope", "tenant_id", "category", "recorded_at"),
        Index(
            "ix_condition_current",
            "patient_user_id",
            "clinical_status",
            postgresql_where=text(
                "superseded_at IS NULL AND verification_status <> 'entered-in-error'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    condition_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    condition_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    condition_display: Mapped[str] = mapped_column(String(255), nullable=False)
    condition_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    category: Mapped[ConditionCategory] = mapped_column(
        Enum(ConditionCategory, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    clinical_status: Mapped[ClinicalStatus] = mapped_column(
        Enum(ClinicalStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    severity_code_system: Mapped[str | None] = mapped_column(String(128))
    severity_code: Mapped[str | None] = mapped_column(String(64))
    severity_display: Mapped[str | None] = mapped_column(String(255))
    severity_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    body_site_code_system: Mapped[str | None] = mapped_column(String(128))
    body_site_code: Mapped[str | None] = mapped_column(String(64))
    body_site_display: Mapped[str | None] = mapped_column(String(255))
    body_site_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    onset_date: Mapped[date | None] = mapped_column(Date)
    onset_precision: Mapped[str | None] = mapped_column(String(8))
    abatement_date: Mapped[date | None] = mapped_column(Date)
    abatement_precision: Mapped[str | None] = mapped_column(String(8))
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conditions.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class EncounterDiagnosis(TimestampMixin, Base):
    """ICD-10-CM billing view of an encounter, linked to the SNOMED condition."""

    __tablename__ = "encounter_diagnoses"
    __table_args__ = (
        UniqueConstraint("encounter_id", "diagnosis_code", "rank"),
        CheckConstraint("rank >= 1", name="encounter_diagnosis_rank"),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="encounter_diagnosis_confidence_range",
        ),
        Index("ix_encounter_diagnosis_scope", "tenant_id", "diagnosis_code"),
        Index(
            "ix_encounter_diagnosis_principal",
            "encounter_id",
            unique=True,
            postgresql_where=text("is_principal"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    encounter_id: Mapped[UUID] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    condition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conditions.id", ondelete="RESTRICT"), index=True
    )
    diagnosis_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    diagnosis_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    diagnosis_display: Mapped[str] = mapped_column(String(255), nullable=False)
    diagnosis_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    present_on_admission: Mapped[str | None] = mapped_column(String(1))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AllergyIntolerance(TimestampMixin, Base):
    __tablename__ = "allergy_intolerances"
    __table_args__ = (
        CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="allergy_onset_precision",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="allergy_confidence_range",
        ),
        CheckConstraint(
            "source <> 'ai-extracted' OR verification_status <> 'confirmed' OR "
            "human_verified_at IS NOT NULL",
            name="allergy_ai_human_verified",
        ),
        CheckConstraint("version >= 1", name="allergy_version_positive"),
        Index("ix_allergy_patient", "patient_user_id", "clinical_status", "recorded_at"),
        Index("ix_allergy_scope", "tenant_id", "category", "recorded_at"),
        Index(
            "ix_allergy_active",
            "patient_user_id",
            "substance_code",
            postgresql_where=text(
                "superseded_at IS NULL AND verification_status <> "
                "'entered-in-error' AND clinical_status = 'active'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    substance_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    substance_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    substance_display: Mapped[str] = mapped_column(String(255), nullable=False)
    substance_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    substance_is_class: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    type: Mapped[AllergyType] = mapped_column(
        Enum(AllergyType, values_callable=enum_values, native_enum=False, length=16), nullable=False
    )
    category: Mapped[AllergyCategory] = mapped_column(
        Enum(AllergyCategory, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    criticality: Mapped[Criticality] = mapped_column(
        Enum(Criticality, values_callable=enum_values, native_enum=False, length=32), nullable=False
    )
    clinical_status: Mapped[ClinicalStatus] = mapped_column(
        Enum(ClinicalStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    verification_status: Mapped[AllergyVerificationStatus] = mapped_column(
        Enum(AllergyVerificationStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    asserter_type: Mapped[AsserterType] = mapped_column(
        Enum(AsserterType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    onset_date: Mapped[date | None] = mapped_column(Date)
    onset_precision: Mapped[str | None] = mapped_column(String(8))
    last_occurrence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("allergy_intolerances.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class AllergyReaction(TimestampMixin, Base):
    """One row per past reaction; the interaction engine reads this relationally."""

    __tablename__ = "allergy_reactions"
    __table_args__ = (Index("ix_allergy_reaction_parent", "allergy_intolerance_id", "onset_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    allergy_intolerance_id: Mapped[UUID] = mapped_column(
        ForeignKey("allergy_intolerances.id", ondelete="CASCADE"), index=True, nullable=False
    )
    manifestation_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    manifestation_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    manifestation_display: Mapped[str] = mapped_column(String(255), nullable=False)
    manifestation_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    severity: Mapped[ReactionSeverity | None] = mapped_column(
        Enum(ReactionSeverity, values_callable=enum_values, native_enum=False, length=16)
    )
    exposure_route_code_system: Mapped[str | None] = mapped_column(String(128))
    exposure_route_code: Mapped[str | None] = mapped_column(String(64))
    exposure_route_display: Mapped[str | None] = mapped_column(String(255))
    exposure_route_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    onset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class PatientAllergyStatus(TimestampMixin, Base):
    """ "No known allergies" recorded as a positive, attributable fact."""

    __tablename__ = "patient_allergy_status"
    __table_args__ = (
        CheckConstraint(
            "NOT no_known_allergies OR last_reviewed_at IS NOT NULL",
            name="nka_requires_review",
        ),
        CheckConstraint(
            "(last_reviewed_at IS NULL) = (reviewed_by_user_id IS NULL)",
            name="review_pair",
        ),
        Index("ix_allergy_status_scope", "tenant_id", "last_reviewed_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    no_known_allergies: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(String(500))


class VitalSign(TimestampMixin, Base):
    """Observation carrying the reference range as applied at result time."""

    __tablename__ = "vital_signs"
    __table_args__ = (
        CheckConstraint(
            "(value_numeric IS NOT NULL)::int + (value_string IS NOT NULL)::int + (value_code "
            "IS NOT NULL)::int + (value_boolean IS NOT NULL)::int + (data_absent_reason IS NOT "
            "NULL)::int = 1",
            name="vital_single_value",
        ),
        CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="vital_unit_required",
        ),
        CheckConstraint(
            "unit IS NULL OR unit IN "
            "('mm[Hg]','kg','cm','Cel','/min','%','kg/m2','[degF]','L/min')",
            name="vital_unit_ucum",
        ),
        CheckConstraint(
            "value_comparator IS NULL OR value_comparator IN ('<','<=','>','>=')",
            name="vital_comparator",
        ),
        CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="vital_interpretation",
        ),
        CheckConstraint(
            "reference_range_high IS NULL OR reference_range_low IS NULL OR "
            "reference_range_high >= reference_range_low",
            name="vital_range_order",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="vital_confidence_range",
        ),
        CheckConstraint("version >= 1", name="vital_version_positive"),
        Index("ix_vital_patient_trend", "patient_user_id", "observation_code", "effective_at"),
        Index("ix_vital_scope", "tenant_id", "observation_code", "effective_at"),
        Index(
            "ix_vital_current",
            "patient_user_id",
            "effective_at",
            postgresql_where=text("superseded_at IS NULL AND status <> 'entered-in-error'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    observation_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    observation_display: Mapped[str] = mapped_column(String(255), nullable=False)
    observation_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    status: Mapped[ObservationStatus] = mapped_column(
        Enum(ObservationStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    value_string: Mapped[str | None] = mapped_column(String(255))
    value_code_system: Mapped[str | None] = mapped_column(String(128))
    value_code: Mapped[str | None] = mapped_column(String(64))
    value_display: Mapped[str | None] = mapped_column(String(255))
    value_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_comparator: Mapped[str | None] = mapped_column(String(2))
    unit: Mapped[str | None] = mapped_column(String(32))
    data_absent_reason: Mapped[str | None] = mapped_column(String(32))
    interpretation_code: Mapped[str | None] = mapped_column(String(8), index=True)
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reference_range_text: Mapped[str | None] = mapped_column(String(255))
    body_site_code: Mapped[str | None] = mapped_column(String(64))
    method_code: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(128))
    performer_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    parent_vital_sign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vital_signs.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("vital_signs.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class VitalSignComponent(TimestampMixin, Base):
    """Systolic/diastolic and other panel members of one observation."""

    __tablename__ = "vital_sign_components"
    __table_args__ = (
        UniqueConstraint("vital_sign_id", "observation_code"),
        CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="vital_component_unit_required",
        ),
        CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="vital_component_interpretation",
        ),
        Index("ix_vital_component_parent", "vital_sign_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    vital_sign_id: Mapped[UUID] = mapped_column(
        ForeignKey("vital_signs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    observation_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    observation_display: Mapped[str] = mapped_column(String(255), nullable=False)
    observation_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    value_string: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(32))
    interpretation_code: Mapped[str | None] = mapped_column(String(8))
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)


class GrowthMeasurement(TimestampMixin, Base):
    """Paediatric growth point; surface percentiles, never a bare adult BMI."""

    __tablename__ = "growth_measurements"
    __table_args__ = (
        CheckConstraint("age_days >= 0", name="growth_age_nonneg"),
        CheckConstraint(
            "bmi_percentile IS NULL OR (bmi_percentile >= 0 AND bmi_percentile <= 100)",
            name="growth_percentile_range",
        ),
        CheckConstraint(
            "height_percentile IS NULL OR (height_percentile >= 0 AND height_percentile <= 100)",
            name="growth_height_percentile_range",
        ),
        CheckConstraint(
            "weight_percentile IS NULL OR (weight_percentile >= 0 AND weight_percentile <= 100)",
            name="growth_weight_percentile_range",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="growth_confidence_range",
        ),
        CheckConstraint("version >= 1", name="growth_version_positive"),
        Index("ix_growth_patient", "patient_user_id", "measured_at"),
        Index("ix_growth_scope", "tenant_id", "measured_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    age_days: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    head_circumference_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bmi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    height_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    weight_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    bmi_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    height_zscore: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    weight_zscore: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    bmi_zscore: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    standard_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("growth_reference_standards.id", ondelete="RESTRICT")
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("growth_measurements.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class Immunization(TimestampMixin, Base):
    """Administered, refused, or contraindicated dose; refusal is a recorded fact."""

    __tablename__ = "immunizations"
    __table_args__ = (
        UniqueConstraint("patient_user_id", "vaccine_code", "series_name", "series_dose_number"),
        CheckConstraint(
            "series_dose_number IS NULL OR series_dose_number >= 1",
            name="immunization_dose_number",
        ),
        CheckConstraint(
            "status <> 'not-done' OR status_reason_code IS NOT NULL",
            name="immunization_not_done_reason",
        ),
        CheckConstraint(
            "status <> 'completed' OR (dose_quantity IS NOT NULL AND dose_unit IS NOT NULL)",
            name="immunization_dose_required",
        ),
        CheckConstraint(
            "administered_precision IN ('day','month','year')",
            name="immunization_date_precision",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="immunization_confidence_range",
        ),
        CheckConstraint("version >= 1", name="immunization_version_positive"),
        Index("ix_immunization_patient", "patient_user_id", "administered_date"),
        Index("ix_immunization_scope", "tenant_id", "vaccine_code", "administered_date"),
        Index(
            "ix_immunization_due",
            "tenant_id",
            "next_due_at",
            postgresql_where=text("next_due_at IS NOT NULL AND status = 'completed'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    vaccine_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    vaccine_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    vaccine_display: Mapped[str] = mapped_column(String(255), nullable=False)
    vaccine_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    manufacturer_code_system: Mapped[str | None] = mapped_column(String(128))
    manufacturer_code: Mapped[str | None] = mapped_column(String(64))
    manufacturer_display: Mapped[str | None] = mapped_column(String(255))
    manufacturer_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    status: Mapped[ImmunizationStatus] = mapped_column(
        Enum(ImmunizationStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    status_reason_code: Mapped[str | None] = mapped_column(String(64))
    administered_date: Mapped[date] = mapped_column(Date, nullable=False)
    administered_precision: Mapped[str] = mapped_column(String(8), default="day", nullable=False)
    administered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lot_number: Mapped[str | None] = mapped_column(String(64))
    expiration_date: Mapped[date | None] = mapped_column(Date)
    site_code_system: Mapped[str | None] = mapped_column(String(128))
    site_code: Mapped[str | None] = mapped_column(String(64))
    site_display: Mapped[str | None] = mapped_column(String(255))
    site_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    route_code_system: Mapped[str | None] = mapped_column(String(128))
    route_code: Mapped[str | None] = mapped_column(String(64))
    route_display: Mapped[str | None] = mapped_column(String(255))
    route_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    dose_quantity: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    dose_unit: Mapped[str | None] = mapped_column(String(16))
    series_name: Mapped[str | None] = mapped_column(String(100))
    series_dose_number: Mapped[int | None] = mapped_column(Integer)
    series_doses_expected: Mapped[int | None] = mapped_column(Integer)
    funding_source: Mapped[str | None] = mapped_column(String(32))
    administered_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    booster_of_immunization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("immunizations.id", ondelete="RESTRICT")
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("immunizations.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class ImmunizationCertificate(TimestampMixin, Base):
    """One verifiable certificate per administered dose."""

    __tablename__ = "immunization_certificates"
    __table_args__ = (
        CheckConstraint(
            "status <> 'revoked' OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="certificate_revocation",
        ),
        Index("ix_certificate_scope", "tenant_id", "status", "issued_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    immunization_id: Mapped[UUID] = mapped_column(
        ForeignKey("immunizations.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    certificate_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issuer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verification_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, values_callable=enum_values, native_enum=False, length=32),
        default=CertificateStatus.ACTIVE,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(255))
    superseded_by_certificate_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("immunization_certificates.id", ondelete="RESTRICT")
    )
    document_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )


class ClinicalNote(TimestampMixin, Base):
    """Signed notes are immutable; corrections are new versions, additions are addenda."""

    __tablename__ = "clinical_notes"
    __table_args__ = (
        UniqueConstraint("encounter_id", "note_type_code", "version"),
        CheckConstraint(
            "content_format IN ('markdown','plain','fhir')",
            name="note_content_format",
        ),
        CheckConstraint(
            "status <> 'final' OR (signed_at IS NOT NULL AND signed_by_user_id IS NOT NULL AND "
            "signature_hash IS NOT NULL)",
            name="final_note_signed",
        ),
        CheckConstraint(
            "(cosigned_at IS NULL) = (cosigner_user_id IS NULL)",
            name="note_cosign_pair",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="note_confidence_range",
        ),
        CheckConstraint("version >= 1", name="note_version_positive"),
        Index("ix_note_scope", "tenant_id", "note_type_code", "created_at"),
        Index("ix_note_patient", "patient_user_id", "created_at"),
        Index(
            "ix_note_unsigned",
            "tenant_id",
            "author_user_id",
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    encounter_id: Mapped[UUID] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    note_type_code: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(16), default="markdown", nullable=False)
    status: Mapped[NoteStatus] = mapped_column(
        Enum(NoteStatus, values_callable=enum_values, native_enum=False, length=32),
        default=NoteStatus.DRAFT,
        nullable=False,
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    cosigner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    cosigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signature_hash: Mapped[str | None] = mapped_column(String(64))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinical_notes.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class ClinicalNoteAddendum(TimestampMixin, Base):
    __tablename__ = "clinical_note_addenda"
    __table_args__ = (
        UniqueConstraint("clinical_note_id", "sequence"),
        Index("ix_note_addendum_parent", "clinical_note_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinical_note_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinical_notes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class EncounterCode(TimestampMixin, Base):
    __tablename__ = "encounter_codes"
    __table_args__ = (
        UniqueConstraint("encounter_id", "billing_code", "code_type", "rank"),
        CheckConstraint("units >= 1", name="encounter_code_units"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="encounter_code_confidence",
        ),
        CheckConstraint(
            "source <> 'ai-extracted' OR review_status <> 'accepted' OR reviewed_by_user_id IS "
            "NOT NULL",
            name="encounter_code_ai_review",
        ),
        Index("ix_encounter_code_scope", "tenant_id", "code_type", "review_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    encounter_id: Mapped[UUID] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    billing_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    billing_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    billing_display: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    code_type: Mapped[CodeType] = mapped_column(
        Enum(CodeType, values_callable=enum_values, native_enum=False, length=16), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    modifiers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    coder_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, values_callable=enum_values, native_enum=False, length=16),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Referral(TimestampMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint("urgency IN ('routine','urgent','emergent')", name="referral_urgency"),
        Index("ix_referral_scope", "tenant_id", "status", "created_at"),
        Index("ix_referral_patient", "patient_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    referring_provider_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), nullable=False
    )
    referring_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    receiving_provider_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT")
    )
    receiving_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    specialty_code: Mapped[str] = mapped_column(String(64), nullable=False)
    urgency: Mapped[str] = mapped_column(String(16), default="routine", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, values_callable=enum_values, native_enum=False, length=32),
        default=ReferralStatus.DRAFT,
        nullable=False,
    )
    prior_authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prior_authorizations.id", ondelete="SET NULL")
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_note: Mapped[str | None] = mapped_column(Text)


class CareTeamMember(TimestampMixin, Base):
    __tablename__ = "care_team_members"
    __table_args__ = (
        UniqueConstraint("patient_user_id", "member_user_id", "role_code", "period_start"),
        CheckConstraint(
            "period_end IS NULL OR period_end >= period_start",
            name="care_team_period",
        ),
        Index("ix_care_team_patient", "patient_user_id", "is_primary"),
        Index("ix_care_team_scope", "tenant_id", "role_code"),
        Index(
            "ix_care_team_primary",
            "patient_user_id",
            unique=True,
            postgresql_where=text("is_primary AND period_end IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    member_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date)


class FamilyHistory(TimestampMixin, Base):
    __tablename__ = "family_history"
    __table_args__ = (
        CheckConstraint(
            "onset_age_years IS NULL OR onset_age_years BETWEEN 0 AND 130",
            name="family_history_age",
        ),
        CheckConstraint(
            "onset_precision IS NULL OR onset_precision IN ('day','month','year')",
            name="family_history_precision",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="family_history_confidence_range",
        ),
        CheckConstraint("version >= 1", name="family_history_version_positive"),
        Index("ix_family_history_patient", "patient_user_id", "condition_code"),
        Index("ix_family_history_scope", "tenant_id", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    relationship_code: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    condition_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    condition_display: Mapped[str] = mapped_column(String(255), nullable=False)
    condition_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    onset_age_years: Mapped[int | None] = mapped_column(Integer)
    onset_precision: Mapped[str | None] = mapped_column(String(8))
    deceased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("family_history.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class Prescription(TimestampMixin, Base):
    """The script issued at an encounter; dosing weight is a snapshot, not a join."""

    __tablename__ = "prescriptions"
    __table_args__ = (
        CheckConstraint(
            "(dosing_weight_kg IS NULL) = (dosing_weight_observed_at IS NULL)",
            name="dosing_weight_pair",
        ),
        CheckConstraint(
            "dosing_weight_kg IS NULL OR dosing_weight_kg > 0",
            name="dosing_weight_positive",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="prescription_confidence_range",
        ),
        CheckConstraint("version >= 1", name="prescription_version_positive"),
        Index("ix_prescription_scope", "tenant_id", "status", "written_at"),
        Index("ix_prescription_patient", "patient_user_id", "written_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    prescriber_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    prescription_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[PrescriptionStatus] = mapped_column(
        Enum(PrescriptionStatus, values_callable=enum_values, native_enum=False, length=32),
        default=PrescriptionStatus.DRAFT,
        nullable=False,
    )
    written_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    dosing_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    dosing_weight_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class MedicationRequest(TimestampMixin, Base):
    """One row per drug on a prescription; RxNorm SCD/SBD only, never an ingredient."""

    __tablename__ = "medication_requests"
    __table_args__ = (
        CheckConstraint(
            "medication_term_type IN ('SCD','SBD','GPCK','BPCK')",
            name="rx_term_type",
        ),
        CheckConstraint("refills_allowed >= 0", name="refills_allowed_nonneg"),
        CheckConstraint(
            "refills_remaining >= 0 AND refills_remaining <= refills_allowed",
            name="refills_bounds",
        ),
        CheckConstraint(
            "controlled_substance_schedule IS NULL OR controlled_substance_schedule IN "
            "('CI','CII','CIII','CIV','CV')",
            name="dea_schedule",
        ),
        CheckConstraint(
            "controlled_substance_schedule <> 'CII' OR refills_allowed = 0",
            name="cii_no_refills",
        ),
        CheckConstraint(
            "status <> 'stopped' OR (stopped_at IS NOT NULL AND stop_reason IS NOT NULL)",
            name="med_request_stop_reason",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="med_request_quantity_positive",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="med_request_confidence_range",
        ),
        CheckConstraint("version >= 1", name="med_request_version_positive"),
        Index("ix_med_request_patient", "patient_user_id", "medication_code", "recorded_at"),
        Index("ix_med_request_scope", "tenant_id", "status", "recorded_at"),
        Index(
            "ix_med_request_active",
            "patient_user_id",
            "medication_code",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    prescription_id: Mapped[UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    medication_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    medication_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    medication_display: Mapped[str] = mapped_column(String(255), nullable=False)
    medication_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    medication_term_type: Mapped[str] = mapped_column(String(8), nullable=False)
    ndc_code: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[MedicationRequestStatus] = mapped_column(
        Enum(MedicationRequestStatus, values_callable=enum_values, native_enum=False, length=32),
        default=MedicationRequestStatus.DRAFT,
        nullable=False,
    )
    intent: Mapped[MedicationRequestIntent] = mapped_column(
        Enum(MedicationRequestIntent, values_callable=enum_values, native_enum=False, length=32),
        default=MedicationRequestIntent.ORDER,
        nullable=False,
    )
    indication_condition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conditions.id", ondelete="RESTRICT")
    )
    substitution_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[str | None] = mapped_column(String(32))
    days_supply: Mapped[int | None] = mapped_column(Integer)
    refills_allowed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refills_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    controlled_substance_schedule: Mapped[str | None] = mapped_column(String(4))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(255))
    stopped_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class MedicationDosageInstruction(TimestampMixin, Base):
    """One row per dose line; a taper is two rows, never free text."""

    __tablename__ = "medication_dosage_instructions"
    __table_args__ = (
        UniqueConstraint("medication_request_id", "sequence"),
        CheckConstraint("dose_quantity > 0", name="dosage_positive"),
        CheckConstraint("frequency > 0", name="dosage_frequency_positive"),
        CheckConstraint("period > 0", name="dosage_period_positive"),
        CheckConstraint("period_unit IN ('h','d','wk','mo')", name="dosage_period_unit"),
        CheckConstraint(
            "effective_end_at IS NULL OR effective_end_at >= effective_start_at",
            name="dosage_effective_period",
        ),
        CheckConstraint(
            "is_chronic OR effective_end_at IS NOT NULL",
            name="dosage_course_bounded",
        ),
        CheckConstraint(
            "NOT as_needed OR as_needed_reason IS NOT NULL",
            name="dosage_prn_reason",
        ),
        Index("ix_dosage_request", "medication_request_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    medication_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    dose_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    dose_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    route_code: Mapped[str] = mapped_column(String(64), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=1, nullable=False)
    period_unit: Mapped[str] = mapped_column(String(8), default="d", nullable=False)
    as_needed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    as_needed_reason: Mapped[str | None] = mapped_column(String(255))
    max_dose_per_period: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    is_chronic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    effective_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sig_text: Mapped[str] = mapped_column(String(500), nullable=False)


class MedicationSchedule(TimestampMixin, Base):
    """One row per dosage instruction and time of day; the reminder generator source."""

    __tablename__ = "medication_schedules"
    __table_args__ = (
        UniqueConstraint("dosage_instruction_id", "time_local"),
        CheckConstraint("is_chronic OR ends_on IS NOT NULL", name="schedule_course_bounded"),
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="schedule_period"),
        CheckConstraint("doses_generated >= 0", name="schedule_generated_nonneg"),
        CheckConstraint(
            "total_doses IS NULL OR total_doses > 0",
            name="schedule_total_positive",
        ),
        Index("ix_med_schedule_patient", "patient_user_id", "status"),
        Index("ix_med_schedule_scope", "tenant_id", "status", "ends_on"),
        Index(
            "ix_med_schedule_generation",
            "status",
            "generated_through",
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    prescription_id: Mapped[UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    medication_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    dosage_instruction_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_dosage_instructions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    time_local: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    days_of_week: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    is_chronic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_doses: Mapped[int | None] = mapped_column(Integer)
    doses_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_through: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MedicationScheduleStatus] = mapped_column(
        Enum(MedicationScheduleStatus, values_callable=enum_values, native_enum=False, length=32),
        default=MedicationScheduleStatus.ACTIVE,
        nullable=False,
    )
    channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["in_app"], nullable=False)


class MedicationReminderOccurrence(Base):
    """Materialized fire list; delivery state only, idempotent per schedule instant."""

    __tablename__ = "medication_reminder_occurrences"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_at", name="uq_reminder_occurrence"),
        CheckConstraint("attempts >= 0", name="reminder_attempts_nonneg"),
        Index("ix_reminder_due", "tenant_id", "status", "scheduled_at"),
        Index("ix_reminder_patient", "patient_user_id", "scheduled_at"),
        Index("ix_reminder_pending", "scheduled_at", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_local: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, values_callable=enum_values, native_enum=False, length=16),
        default=NotificationChannel.IN_APP,
        nullable=False,
    )
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, values_callable=enum_values, native_enum=False, length=32),
        default=ReminderStatus.PENDING,
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    notification_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("portal_notifications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MedicationAdherenceEvent(Base):
    """Clinical adherence assertion, distinct from reminder delivery state."""

    __tablename__ = "medication_adherence_events"
    __table_args__ = (
        UniqueConstraint("occurrence_id", "status", "recorded_at"),
        CheckConstraint(
            "status <> 'taken' OR taken_at IS NOT NULL",
            name="adherence_taken_time",
        ),
        CheckConstraint(
            "dose_taken_quantity IS NULL OR dose_taken_quantity > 0",
            name="adherence_dose_positive",
        ),
        Index("ix_adherence_patient", "patient_user_id", "scheduled_at"),
        Index("ix_adherence_scope", "tenant_id", "status", "scheduled_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_schedules.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    occurrence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("medication_reminder_occurrences.id", ondelete="RESTRICT"), index=True
    )
    medication_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[AdherenceStatus] = mapped_column(
        Enum(AdherenceStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dose_taken_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    dose_unit: Mapped[str | None] = mapped_column(String(32))
    reported_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason_code: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MedicationDispense(TimestampMixin, Base):
    __tablename__ = "medication_dispenses"
    __table_args__ = (
        UniqueConstraint("medication_request_id", "fill_number"),
        CheckConstraint("fill_number >= 0", name="dispense_fill_number"),
        CheckConstraint("quantity > 0", name="dispense_quantity_positive"),
        Index("ix_dispense_scope", "tenant_id", "dispensed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    medication_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    fill_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ndc_code: Mapped[str | None] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    days_supply: Mapped[int | None] = mapped_column(Integer)
    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispenser_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    dispenser_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    lot_number: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class MedicationStatement(TimestampMixin, Base):
    """Patient-reported or imported medication history; ingredient RxCUIs allowed here."""

    __tablename__ = "medication_statements"
    __table_args__ = (
        CheckConstraint(
            "medication_term_type IS NULL OR medication_term_type IN "
            "('IN','PIN','SCD','SBD','GPCK','BPCK')",
            name="statement_term_type",
        ),
        CheckConstraint(
            "effective_end_at IS NULL OR effective_start_at IS NULL OR effective_end_at >= "
            "effective_start_at",
            name="statement_period",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="med_statement_confidence_range",
        ),
        CheckConstraint("version >= 1", name="med_statement_version_positive"),
        Index("ix_med_statement_patient", "patient_user_id", "status", "recorded_at"),
        Index("ix_med_statement_scope", "tenant_id", "recorded_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    medication_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    medication_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    medication_display: Mapped[str] = mapped_column(String(255), nullable=False)
    medication_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    medication_term_type: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[MedicationStatementStatus] = mapped_column(
        Enum(MedicationStatementStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    sig_text: Mapped[str | None] = mapped_column(String(500))
    effective_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("medication_statements.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class PrescriptionSafetyCheck(Base):
    """Durable record of every interaction/allergy check and every override."""

    __tablename__ = "prescription_safety_checks"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('none','low','moderate','high','contraindicated')",
            name="safety_check_severity",
        ),
        CheckConstraint(
            "outcome <> 'overridden' OR (override_reason IS NOT NULL AND overridden_by_user_id "
            "IS NOT NULL)",
            name="override_requires_reason",
        ),
        Index("ix_safety_check_prescription", "prescription_id", "check_type"),
        Index("ix_safety_check_scope", "tenant_id", "outcome", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    prescription_id: Mapped[UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    medication_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("medication_requests.id", ondelete="RESTRICT"), index=True
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    check_type: Mapped[SafetyCheckType] = mapped_column(
        Enum(SafetyCheckType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by_code_system: Mapped[str | None] = mapped_column(String(128))
    triggered_by_code: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    outcome: Mapped[SafetyCheckOutcome] = mapped_column(
        Enum(SafetyCheckOutcome, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    overridden_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    override_reason: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LabFacility(TimestampMixin, Base):
    __tablename__ = "lab_facilities"
    __table_args__ = (
        Index("ix_lab_facility_scope", "tenant_id", "is_active"),
        Index("ix_lab_facility_geo", "latitude", "longitude"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    home_collection_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LabTest(TimestampMixin, Base):
    """Orderable test catalogue; specimen type is SNOMED CT, not LOINC."""

    __tablename__ = "lab_tests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "test_code", "test_code_system"),
        CheckConstraint(
            "price_cents IS NULL OR price_cents >= 0",
            name="lab_test_price_nonneg",
        ),
        CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="lab_test_currency_required",
        ),
        Index("ix_lab_test_scope", "tenant_id", "test_code", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    test_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    test_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    test_display: Mapped[str] = mapped_column(String(255), nullable=False)
    test_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    panel_code_system: Mapped[str | None] = mapped_column(String(128))
    panel_code: Mapped[str | None] = mapped_column(String(64))
    panel_display: Mapped[str | None] = mapped_column(String(255))
    panel_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specimen_type_code_system: Mapped[str | None] = mapped_column(String(128))
    specimen_type_code: Mapped[str | None] = mapped_column(String(64))
    specimen_type_display: Mapped[str | None] = mapped_column(String(255))
    specimen_type_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    container: Mapped[str | None] = mapped_column(String(64))
    prep_instructions: Mapped[str | None] = mapped_column(Text)
    fasting_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    turnaround_hours: Mapped[int | None] = mapped_column(Integer)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LabSlot(TimestampMixin, Base):
    __tablename__ = "lab_slots"
    __table_args__ = (
        UniqueConstraint("facility_id", "start_at"),
        CheckConstraint("end_at > start_at", name="lab_slot_period"),
        CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="lab_slot_capacity_bounds",
        ),
        Index("ix_lab_slot_scope", "tenant_id", "start_at", "status"),
        Index(
            "ix_lab_slot_open", "tenant_id", "start_at", postgresql_where=text("status = 'open'")
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    facility_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_facilities.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, values_callable=enum_values, native_enum=False, length=32),
        default=SlotStatus.OPEN,
        nullable=False,
    )


class LabSlotTest(TimestampMixin, Base):
    """Which tests are bookable in which slot, with per-test capacity."""

    __tablename__ = "lab_slot_tests"
    __table_args__ = (
        CheckConstraint(
            "booked_count >= 0 AND booked_count <= capacity",
            name="lab_slot_test_capacity_bounds",
        ),
        CheckConstraint(
            "price_cents_override IS NULL OR price_cents_override >= 0",
            name="lab_slot_test_price_nonneg",
        ),
        Index("ix_lab_slot_test_lookup", "lab_test_id", "slot_id"),
    )

    slot_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_slots.id", ondelete="CASCADE"), primary_key=True
    )
    lab_test_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="RESTRICT"), primary_key=True
    )
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_cents_override: Mapped[int | None] = mapped_column(Integer)


class LabOrder(TimestampMixin, Base):
    __tablename__ = "lab_orders"
    __table_args__ = (
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="lab_order_confidence_range",
        ),
        Index("ix_lab_order_scope", "tenant_id", "status", "requested_at"),
        Index("ix_lab_order_patient", "patient_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    ordering_provider_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), index=True
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    facility_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_facilities.id", ondelete="RESTRICT"), nullable=False
    )
    slot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_slots.id", ondelete="RESTRICT"), index=True
    )
    order_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    priority: Mapped[LabPriority] = mapped_column(
        Enum(LabPriority, values_callable=enum_values, native_enum=False, length=16),
        default=LabPriority.ROUTINE,
        nullable=False,
    )
    status: Mapped[LabOrderStatus] = mapped_column(
        Enum(LabOrderStatus, values_callable=enum_values, native_enum=False, length=32),
        default=LabOrderStatus.DRAFT,
        nullable=False,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LabOrderTest(TimestampMixin, Base):
    __tablename__ = "lab_order_tests"
    __table_args__ = (
        UniqueConstraint("lab_order_id", "lab_test_id"),
        CheckConstraint(
            "price_cents IS NULL OR currency IS NOT NULL",
            name="lab_order_test_currency_required",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lab_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lab_test_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[LabOrderStatus] = mapped_column(
        Enum(LabOrderStatus, values_callable=enum_values, native_enum=False, length=32),
        default=LabOrderStatus.PLACED,
        nullable=False,
    )
    price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))


class Specimen(TimestampMixin, Base):
    __tablename__ = "specimens"
    __table_args__ = (Index("ix_specimen_scope", "tenant_id", "collected_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    lab_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("lab_orders.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    accession_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    specimen_type_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    specimen_type_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    specimen_type_display: Mapped[str] = mapped_column(String(255), nullable=False)
    specimen_type_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    condition: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(String(255))


class LabResult(TimestampMixin, Base):
    """Result observation; preliminary results must never drive a clinical decision."""

    __tablename__ = "lab_results"
    __table_args__ = (
        CheckConstraint(
            "(value_numeric IS NOT NULL)::int + (value_string IS NOT NULL)::int + (value_code "
            "IS NOT NULL)::int + (value_boolean IS NOT NULL)::int + (data_absent_reason IS NOT "
            "NULL)::int = 1",
            name="lab_result_single_value",
        ),
        CheckConstraint(
            "value_numeric IS NULL OR unit IS NOT NULL",
            name="lab_result_unit_required",
        ),
        CheckConstraint(
            "value_comparator IS NULL OR value_comparator IN ('<','<=','>','>=')",
            name="lab_result_comparator",
        ),
        CheckConstraint(
            "interpretation_code IS NULL OR interpretation_code IN "
            "('N','A','AA','H','HH','L','LL','R','S','I')",
            name="lab_result_interpretation",
        ),
        CheckConstraint(
            "status NOT IN ('final','amended','corrected') OR verified_by_user_id IS NOT NULL",
            name="lab_result_verified",
        ),
        CheckConstraint(
            "(acknowledged_at IS NULL) = (acknowledged_by_user_id IS NULL)",
            name="lab_result_ack_pair",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR (extraction_confidence >= 0 AND "
            "extraction_confidence <= 1)",
            name="lab_result_confidence_range",
        ),
        CheckConstraint("version >= 1", name="lab_result_version_positive"),
        Index("ix_lab_result_patient_trend", "patient_user_id", "test_code", "effective_at"),
        Index("ix_lab_result_scope", "tenant_id", "status", "effective_at"),
        Index(
            "ix_lab_result_unacked",
            "tenant_id",
            "effective_at",
            postgresql_where=text("is_critical AND acknowledged_at IS NULL"),
        ),
        Index(
            "ix_lab_result_current",
            "patient_user_id",
            "effective_at",
            postgresql_where=text("superseded_at IS NULL AND status <> 'entered-in-error'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    lab_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_orders.id", ondelete="RESTRICT"), index=True
    )
    lab_test_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="RESTRICT"), index=True
    )
    specimen_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("specimens.id", ondelete="RESTRICT")
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    test_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    test_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    test_display: Mapped[str] = mapped_column(String(255), nullable=False)
    test_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    panel_code_system: Mapped[str | None] = mapped_column(String(128))
    panel_code: Mapped[str | None] = mapped_column(String(64))
    panel_display: Mapped[str | None] = mapped_column(String(255))
    panel_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    parent_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_results.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[ObservationStatus] = mapped_column(
        Enum(ObservationStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    value_string: Mapped[str | None] = mapped_column(String(255))
    value_code_system: Mapped[str | None] = mapped_column(String(128))
    value_code: Mapped[str | None] = mapped_column(String(64))
    value_display: Mapped[str | None] = mapped_column(String(255))
    value_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_comparator: Mapped[str | None] = mapped_column(String(2))
    unit: Mapped[str | None] = mapped_column(String(32))
    data_absent_reason: Mapped[str | None] = mapped_column(String(32))
    interpretation_code: Mapped[str | None] = mapped_column(String(8), index=True)
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    reference_range_text: Mapped[str | None] = mapped_column(String(255))
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    critical_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement_note: Mapped[str | None] = mapped_column(String(500))
    performer_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    document_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    asserter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[ProvenanceSource] = mapped_column(
        Enum(ProvenanceSource, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL"), index=True
    )
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    human_verified_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    human_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_results.id", ondelete="RESTRICT")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[str | None] = mapped_column(String(500))


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="invoice_currency_iso4217"),
        CheckConstraint(
            "subtotal_cents >= 0 AND tax_cents >= 0 AND total_cents >= 0",
            name="invoice_amounts_nonneg",
        ),
        CheckConstraint(
            "total_cents = subtotal_cents + tax_cents",
            name="invoice_total_consistent",
        ),
        CheckConstraint(
            "status <> 'issued' OR issued_at IS NOT NULL",
            name="invoice_issued_at",
        ),
        Index("ix_invoice_scope", "tenant_id", "status", "issued_at"),
        Index("ix_invoice_patient", "patient_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    payer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), index=True
    )
    lab_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lab_orders.id", ondelete="RESTRICT"), index=True
    )
    policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("policies.id", ondelete="RESTRICT"))
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, values_callable=enum_values, native_enum=False, length=32),
        default=InvoiceStatus.DRAFT,
        nullable=False,
    )
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceLine(TimestampMixin, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number"),
        CheckConstraint("quantity > 0", name="invoice_line_quantity_positive"),
        CheckConstraint(
            "unit_price_cents >= 0 AND amount_cents >= 0",
            name="invoice_line_amounts_nonneg",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    service_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("service_items.id", ondelete="RESTRICT")
    )
    service_code_system: Mapped[str | None] = mapped_column(String(128))
    service_code: Mapped[str | None] = mapped_column(String(64))
    service_display: Mapped[str | None] = mapped_column(String(255))
    service_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("processor", "processor_intent_id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        CheckConstraint("amount_cents > 0", name="payment_amount_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="payment_currency_iso4217"),
        CheckConstraint(
            "status <> 'captured' OR captured_at IS NOT NULL",
            name="payment_captured_at",
        ),
        Index("ix_payment_scope", "tenant_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), index=True
    )
    payer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    processor: Mapped[str] = mapped_column(String(32), nullable=False)
    processor_intent_id: Mapped[str | None] = mapped_column(String(255))
    processor_charge_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="refund_amount_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="refund_currency_iso4217"),
        Index("ix_refund_scope", "tenant_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    payment_id: Mapped[UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus, values_callable=enum_values, native_enum=False, length=32),
        default=RefundStatus.PENDING,
        nullable=False,
    )
    processor_refund_id: Mapped[str | None] = mapped_column(String(255))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoyaltyAccount(TimestampMixin, Base):
    __tablename__ = "loyalty_accounts"
    __table_args__ = (
        CheckConstraint("balance_points >= 0", name="loyalty_balance_nonneg"),
        CheckConstraint("lifetime_points >= 0", name="loyalty_lifetime_nonneg"),
        Index("ix_loyalty_account_scope", "tenant_id", "tier"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    program: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    balance_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tier: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class LoyaltyLedgerEntry(Base):
    """Append-only points ledger; balance_after makes the balance an invariant."""

    __tablename__ = "loyalty_ledger"
    __table_args__ = (
        UniqueConstraint("account_id", "reference_type", "reference_id", "entry_type"),
        CheckConstraint("balance_after >= 0", name="loyalty_ledger_balance_nonneg"),
        CheckConstraint(
            "(entry_type IN ('accrual','adjustment')) OR points <= 0",
            name="loyalty_ledger_sign",
        ),
        Index("ix_loyalty_ledger_account", "account_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("loyalty_accounts.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    entry_type: Mapped[LoyaltyEntryType] = mapped_column(
        Enum(LoyaltyEntryType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[UUID] = mapped_column(nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InsuranceProduct(TimestampMixin, Base):
    __tablename__ = "insurance_products"
    __table_args__ = (
        UniqueConstraint("payer_organization_id", "code"),
        CheckConstraint(
            "product_type IN ('hmo','ppo','epo','pos','indemnity')",
            name="insurance_product_type",
        ),
        Index("ix_insurance_product_scope", "tenant_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    payer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[str] = mapped_column(String(16), nullable=False)
    network_name: Mapped[str | None] = mapped_column(String(255))
    filing_id: Mapped[str | None] = mapped_column(String(64))
    regulator_approval_id: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InsurancePlan(TimestampMixin, Base):
    __tablename__ = "insurance_plans"
    __table_args__ = (
        UniqueConstraint("product_id", "plan_code", "effective_from"),
        CheckConstraint("premium_cents >= 0", name="plan_premium_nonneg"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="plan_currency_iso4217"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="plan_effective_period",
        ),
        Index("ix_insurance_plan_scope", "tenant_id", "is_active", "premium_cents"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("insurance_products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metal_tier: Mapped[str | None] = mapped_column(String(16))
    premium_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    individual_deductible_cents: Mapped[int | None] = mapped_column(Integer)
    family_deductible_cents: Mapped[int | None] = mapped_column(Integer)
    individual_oop_max_cents: Mapped[int | None] = mapped_column(Integer)
    family_oop_max_cents: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    eligibility_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlanBenefit(TimestampMixin, Base):
    """Coverage source of truth for a plan and service category."""

    __tablename__ = "plan_benefits"
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "service_category", "service_code", "network_tier", "effective_from"
        ),
        CheckConstraint(
            "coinsurance_percent IS NULL OR (coinsurance_percent >= 0 AND coinsurance_percent "
            "<= 100)",
            name="benefit_coinsurance_range",
        ),
        CheckConstraint("copay_cents IS NULL OR copay_cents >= 0", name="benefit_copay_nonneg"),
        CheckConstraint(
            "(visit_limit_count IS NULL) = (limit_period IS NULL)",
            name="benefit_limit_pair",
        ),
        Index("ix_plan_benefit_lookup", "plan_id", "service_category", "network_tier"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("insurance_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    service_category: Mapped[str] = mapped_column(String(64), nullable=False)
    service_code_system: Mapped[str | None] = mapped_column(String(128))
    service_code: Mapped[str | None] = mapped_column(String(64))
    service_display: Mapped[str | None] = mapped_column(String(255))
    service_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    network_tier: Mapped[NetworkTier] = mapped_column(
        Enum(NetworkTier, values_callable=enum_values, native_enum=False, length=32),
        default=NetworkTier.IN_NETWORK,
        nullable=False,
    )
    covered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    copay_cents: Mapped[int | None] = mapped_column(Integer)
    coinsurance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    deductible_applies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visit_limit_count: Mapped[int | None] = mapped_column(Integer)
    limit_period: Mapped[BenefitLimitPeriod | None] = mapped_column(
        Enum(BenefitLimitPeriod, values_callable=enum_values, native_enum=False, length=16)
    )
    prior_auth_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    waiting_period_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exclusion_text: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class BenefitExplanation(TimestampMixin, Base):
    """Plain-language coverage summary grounded in a specific plan benefit row."""

    __tablename__ = "benefit_explanations"
    __table_args__ = (
        UniqueConstraint("plan_benefit_id", "locale", "reading_level"),
        CheckConstraint(
            "(reviewed_at IS NULL) = (reviewed_by_user_id IS NULL)",
            name="benefit_explanation_review_pair",
        ),
        Index("ix_benefit_explanation_scope", "tenant_id", "locale"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    plan_benefit_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_benefits.id", ondelete="CASCADE"), index=True, nullable=False
    )
    locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    reading_level: Mapped[str] = mapped_column(String(16), default="grade6", nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    example_scenario: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_document_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )
    generated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64))
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanRecommendation(TimestampMixin, Base):
    """Ranked plan suggestion with separate history and loyalty component scores."""

    __tablename__ = "plan_recommendations"
    __table_args__ = (
        UniqueConstraint("patient_user_id", "plan_id", "generated_at"),
        CheckConstraint("rank >= 1", name="recommendation_rank"),
        CheckConstraint(
            "score >= 0 AND history_score >= 0 AND loyalty_score >= 0",
            name="recommendation_scores_nonneg",
        ),
        CheckConstraint("loyalty_points_applied >= 0", name="recommendation_points_nonneg"),
        Index("ix_recommendation_patient", "patient_user_id", "generated_at", "rank"),
        Index("ix_recommendation_scope", "tenant_id", "generated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("insurance_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    history_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    loyalty_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    loyalty_points_applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_premium_cents: Mapped[int | None] = mapped_column(Integer)
    estimated_annual_cost_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyApplication(TimestampMixin, Base):
    __tablename__ = "policy_applications"
    __table_args__ = (
        CheckConstraint(
            "status <> 'declined' OR decline_reason IS NOT NULL",
            name="application_decline_reason",
        ),
        CheckConstraint(
            "status <> 'submitted' OR submitted_at IS NOT NULL",
            name="application_submitted_at",
        ),
        CheckConstraint("loyalty_points_redeemed >= 0", name="application_points_nonneg"),
        Index("ix_policy_application_scope", "tenant_id", "status", "submitted_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    applicant_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("insurance_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    application_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[PolicyApplicationStatus] = mapped_column(
        Enum(PolicyApplicationStatus, values_callable=enum_values, native_enum=False, length=32),
        default=PolicyApplicationStatus.DRAFT,
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decline_reason: Mapped[str | None] = mapped_column(String(255))
    quoted_premium_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    loyalty_points_redeemed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Policy(TimestampMixin, Base):
    """An issued insurance policy; written in the same transaction as payment capture."""

    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("plan_id", "member_id"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="policy_effective_period",
        ),
        CheckConstraint("premium_cents >= 0", name="policy_premium_nonneg"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="policy_currency_iso4217"),
        Index("ix_policies_active", "tenant_id", "subscriber_user_id", "status", "effective_from"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("insurance_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("policy_applications.id", ondelete="RESTRICT"), unique=True
    )
    subscriber_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    member_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[PolicyStatus] = mapped_column(
        Enum(PolicyStatus, values_callable=enum_values, native_enum=False, length=32),
        default=PolicyStatus.PENDING,
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    premium_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    premium_frequency: Mapped[PremiumFrequency] = mapped_column(
        Enum(PremiumFrequency, values_callable=enum_values, native_enum=False, length=16),
        default=PremiumFrequency.MONTHLY,
        nullable=False,
    )
    policy_document_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )


class PolicyMember(TimestampMixin, Base):
    __tablename__ = "policy_members"
    __table_args__ = (
        UniqueConstraint("policy_id", "patient_user_id", "effective_from"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="policy_member_period",
        ),
        Index("ix_policy_member_patient", "patient_user_id", "policy_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    relationship: Mapped[MemberRelationship] = mapped_column(
        Enum(MemberRelationship, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    member_suffix: Mapped[str | None] = mapped_column(String(8))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)


class PremiumSchedule(TimestampMixin, Base):
    __tablename__ = "premium_schedules"
    __table_args__ = (
        UniqueConstraint("policy_id", "due_date"),
        CheckConstraint(
            "status IN ('due','paid','overdue','waived')",
            name="premium_schedule_status",
        ),
        CheckConstraint("amount_cents >= 0", name="premium_amount_nonneg"),
        Index("ix_premium_schedule_due", "tenant_id", "status", "due_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="due", nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Beneficiary(TimestampMixin, Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        CheckConstraint(
            "share_percent > 0 AND share_percent <= 100",
            name="beneficiary_share_range",
        ),
        Index("ix_beneficiary_policy", "policy_id", "is_primary"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship: Mapped[MemberRelationship] = mapped_column(
        Enum(MemberRelationship, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    share_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BenefitAccumulator(TimestampMixin, Base):
    """Deductible and out-of-pocket running totals cost estimates must read."""

    __tablename__ = "benefit_accumulators"
    __table_args__ = (
        UniqueConstraint("policy_id", "patient_user_id", "accumulator_type", "benefit_year"),
        CheckConstraint(
            "consumed_cents >= 0 AND consumed_count >= 0",
            name="accumulator_nonneg",
        ),
        CheckConstraint(
            "limit_cents IS NULL OR consumed_cents <= limit_cents",
            name="accumulator_within_limit",
        ),
        Index("ix_accumulator_lookup", "policy_id", "benefit_year"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    accumulator_type: Mapped[AccumulatorType] = mapped_column(
        Enum(AccumulatorType, values_callable=enum_values, native_enum=False, length=40),
        nullable=False,
    )
    benefit_year: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_cents: Mapped[int | None] = mapped_column(Integer)
    consumed_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    limit_count: Mapped[int | None] = mapped_column(Integer)
    consumed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EligibilityCheck(TimestampMixin, Base):
    """Persisted payer eligibility response, cacheable until cached_until."""

    __tablename__ = "eligibility_checks"
    __table_args__ = (
        Index("ix_eligibility_lookup", "member_id", "service_date"),
        Index("ix_eligibility_scope", "tenant_id", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("policies.id", ondelete="RESTRICT"))
    payer_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    member_id: Mapped[str] = mapped_column(String(64), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[EligibilityStatus] = mapped_column(
        Enum(EligibilityStatus, values_callable=enum_values, native_enum=False, length=16),
        default=EligibilityStatus.PENDING,
        nullable=False,
    )
    coverage_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active_from: Mapped[date | None] = mapped_column(Date)
    active_to: Mapped[date | None] = mapped_column(Date)
    benefits_returned: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(64))
    cached_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriorAuthorization(TimestampMixin, Base):
    __tablename__ = "prior_authorizations"
    __table_args__ = (
        CheckConstraint(
            "status NOT IN ('denied','partially_approved') OR decision_reason IS NOT NULL",
            name="prior_auth_decision_reason",
        ),
        CheckConstraint(
            "status <> 'approved' OR authorization_number IS NOT NULL",
            name="prior_auth_number_required",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="prior_auth_period",
        ),
        CheckConstraint(
            "units_approved IS NULL OR units_requested IS NULL OR units_approved <= "
            "units_requested",
            name="prior_auth_units_bounds",
        ),
        Index("ix_prior_auth_scope", "tenant_id", "status", "created_at"),
        Index("ix_prior_auth_patient", "patient_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    requesting_provider_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT"), nullable=False
    )
    service_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    diagnosis_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    units_requested: Mapped[int | None] = mapped_column(Integer)
    units_approved: Mapped[int | None] = mapped_column(Integer)
    clinical_justification: Mapped[str | None] = mapped_column(Text)
    criteria_met: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[PriorAuthStatus] = mapped_column(
        Enum(PriorAuthStatus, values_callable=enum_values, native_enum=False, length=32),
        default=PriorAuthStatus.DRAFT,
        nullable=False,
    )
    reviewer_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    authorization_number: Mapped[str | None] = mapped_column(String(64), unique=True)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class Claim(TimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("service_to >= service_from", name="claim_service_period"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="claim_currency_iso4217"),
        CheckConstraint("total_charge_cents >= 0", name="claim_charge_nonneg"),
        CheckConstraint(
            "status <> 'denied' OR denial_reason_code IS NOT NULL",
            name="claim_denial_reason",
        ),
        Index("ix_claim_scope", "tenant_id", "status", "submitted_at"),
        Index("ix_claim_patient", "patient_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    claim_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    subscriber_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    billing_provider_organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    rendering_provider_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("doctor_profiles.user_id", ondelete="RESTRICT")
    )
    encounter_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("encounters.id", ondelete="RESTRICT"), index=True
    )
    prior_authorization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prior_authorizations.id", ondelete="RESTRICT")
    )
    claim_type: Mapped[ClaimType] = mapped_column(
        Enum(ClaimType, values_callable=enum_values, native_enum=False, length=32), nullable=False
    )
    service_from: Mapped[date] = mapped_column(Date, nullable=False)
    service_to: Mapped[date] = mapped_column(Date, nullable=False)
    total_charge_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allowed_cents: Mapped[int | None] = mapped_column(Integer)
    paid_cents: Mapped[int | None] = mapped_column(Integer)
    patient_responsibility_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, values_callable=enum_values, native_enum=False, length=32),
        default=ClaimStatus.DRAFT,
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denial_reason_code: Mapped[str | None] = mapped_column(String(32))


class ClaimLine(TimestampMixin, Base):
    __tablename__ = "claim_lines"
    __table_args__ = (
        UniqueConstraint("claim_id", "line_number"),
        CheckConstraint("units > 0", name="claim_line_units_positive"),
        CheckConstraint("charge_cents >= 0", name="claim_line_charge_nonneg"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_code_system: Mapped[str] = mapped_column(String(128), nullable=False)
    service_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    service_display: Mapped[str] = mapped_column(String(255), nullable=False)
    service_concept_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("code_concepts.id", ondelete="SET NULL")
    )
    modifiers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1, nullable=False)
    charge_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_cents: Mapped[int | None] = mapped_column(Integer)
    paid_cents: Mapped[int | None] = mapped_column(Integer)
    copay_cents: Mapped[int | None] = mapped_column(Integer)
    coinsurance_cents: Mapped[int | None] = mapped_column(Integer)
    deductible_cents: Mapped[int | None] = mapped_column(Integer)
    diagnosis_pointers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    adjustment_reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ClaimEvent(Base):
    __tablename__ = "claim_events"
    __table_args__ = (Index("ix_claim_event_timeline", "claim_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CostEstimate(TimestampMixin, Base):
    __tablename__ = "cost_estimates"
    __table_args__ = (
        CheckConstraint(
            "billed_cents >= 0 AND member_liability_cents >= 0 AND plan_pays_cents >= 0",
            name="cost_estimate_nonneg",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="cost_estimate_confidence",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="cost_estimate_currency_iso4217"),
        Index("ix_cost_estimate_patient", "patient_user_id", "created_at"),
        Index("ix_cost_estimate_scope", "tenant_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    policy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("policies.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    service_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("service_items.id", ondelete="RESTRICT")
    )
    service_bundle: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    billed_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    contracted_rate_cents: Mapped[int | None] = mapped_column(Integer)
    deductible_applied_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coinsurance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    copay_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    member_liability_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_pays_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deductible_remaining_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentLink(TimestampMixin, Base):
    """Ties a stored document to the clinical or financial row it evidences."""

    __tablename__ = "document_links"
    __table_args__ = (
        UniqueConstraint("document_asset_id", "subject_type", "subject_id"),
        Index("ix_document_link_subject", "subject_type", "subject_id"),
        Index("ix_document_link_scope", "tenant_id", "link_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    document_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    link_type: Mapped[DocumentLinkType] = mapped_column(
        Enum(DocumentLinkType, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
    )
    linked_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class DocumentExtraction(TimestampMixin, Base):
    """Structured extraction of a document, linked back to the asset it came from."""

    __tablename__ = "document_extractions"
    __table_args__ = (
        UniqueConstraint("document_asset_id", "extraction_schema", "schema_version"),
        CheckConstraint(
            "overall_confidence IS NULL OR (overall_confidence >= 0 AND overall_confidence <= 1)",
            name="extraction_confidence_range",
        ),
        CheckConstraint(
            "validation_status <> 'accepted' OR reviewed_by_user_id IS NOT NULL",
            name="extraction_review_required",
        ),
        Index("ix_extraction_scope", "tenant_id", "validation_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    document_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    extraction_schema: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    field_confidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    overall_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    validation_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, values_callable=enum_values, native_enum=False, length=16),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    corrected_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str | None] = mapped_column(String(64))
    external_run_id: Mapped[str | None] = mapped_column(String(64))


class PhiAccessEvent(Base):
    """Append-only PHI read log backing HIPAA disclosure accounting."""

    __tablename__ = "phi_access_events"
    __table_args__ = (
        CheckConstraint(
            "purpose_of_use IN ('TREAT','ETREAT','HPAYMT','HOPERAT','PATRQT','PUBHLTH','RESEARCH')",
            name="phi_purpose_of_use",
        ),
        Index("ix_phi_access_patient", "patient_user_id", "created_at"),
        Index("ix_phi_access_scope", "tenant_id", "created_at"),
        Index("ix_phi_access_actor", "actor_user_id", "created_at"),
        Index(
            "ix_phi_access_breakglass",
            "tenant_id",
            "created_at",
            postgresql_where=text("purpose_of_use = 'ETREAT'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    patient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("patient_profiles.user_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column()
    action: Mapped[PhiAccessAction] = mapped_column(
        Enum(PhiAccessAction, values_callable=enum_values, native_enum=False, length=16),
        nullable=False,
    )
    purpose_of_use: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("consent_grants.id", ondelete="SET NULL")
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    result_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataSubjectRequest(TimestampMixin, Base):
    """Privacy workflow that replaces cascade deletion of a patient."""

    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint(
            "status <> 'refused' OR refusal_reason IS NOT NULL",
            name="dsr_refusal_reason",
        ),
        CheckConstraint(
            "status <> 'fulfilled' OR fulfilled_at IS NOT NULL",
            name="dsr_fulfilled_at",
        ),
        Index("ix_dsr_scope", "tenant_id", "status", "due_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    subject_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    request_type: Mapped[DsrType] = mapped_column(
        Enum(DsrType, values_callable=enum_values, native_enum=False, length=32), nullable=False
    )
    status: Mapped[DsrStatus] = mapped_column(
        Enum(DsrStatus, values_callable=enum_values, native_enum=False, length=32),
        default=DsrStatus.RECEIVED,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refusal_reason: Mapped[str | None] = mapped_column(String(500))
    handled_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    export_document_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_assets.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class SupportCase(TimestampMixin, Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        CheckConstraint("escalation_level >= 0", name="support_escalation_level"),
        CheckConstraint(
            "status <> 'resolved' OR resolved_at IS NOT NULL",
            name="support_resolved_at",
        ),
        Index("ix_support_cases_queue", "tenant_id", "status", "sla_due_at"),
        Index("ix_support_case_assignee", "assignee_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    case_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[SupportSeverity] = mapped_column(
        Enum(SupportSeverity, values_callable=enum_values, native_enum=False, length=16),
        default=SupportSeverity.SEV3,
        nullable=False,
    )
    status: Mapped[SupportStatus] = mapped_column(
        Enum(SupportStatus, values_callable=enum_values, native_enum=False, length=32),
        default=SupportStatus.NEW,
        nullable=False,
    )
    queue: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    sla_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    related_record_type: Mapped[str | None] = mapped_column(String(64))
    related_record_id: Mapped[UUID | None] = mapped_column()


class SupportCaseComment(Base):
    __tablename__ = "support_case_comments"
    __table_args__ = (Index("ix_support_comment_case", "case_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[CommentVisibility] = mapped_column(
        Enum(CommentVisibility, values_callable=enum_values, native_enum=False, length=16),
        default=CommentVisibility.INTERNAL,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupportCaseEvent(Base):
    __tablename__ = "support_case_events"
    __table_args__ = (Index("ix_support_event_timeline", "case_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_cases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
