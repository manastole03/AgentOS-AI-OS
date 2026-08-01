from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RecordCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", min_length=1, max_length=64)
    patient_user_id: UUID | None = None
    assigned_user_id: UUID | None = None
    external_reference: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def bound_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 50_000:
            raise ValueError("Structured payload is too large")
        return value


class RecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, min_length=1, max_length=64)
    patient_user_id: UUID | None = None
    assigned_user_id: UUID | None = None
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    data: dict[str, Any] | None = None


class RecordResponse(BaseModel):
    id: UUID
    category: str
    title: str
    status: str
    patient_user_id: UUID | None
    assigned_user_id: UUID | None
    external_reference: str | None
    occurred_at: datetime | None
    due_at: datetime | None
    amount_cents: int | None
    currency: str | None
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DashboardMetric(BaseModel):
    label: str
    value: int
    trend: str
    tone: str = "neutral"


class DashboardResponse(BaseModel):
    account_type: str
    display_name: str
    metrics: list[DashboardMetric]
    recent: list[RecordResponse]
    unread_notifications: int
    integrations: dict[str, bool]


class NotificationCreate(BaseModel):
    recipient_user_id: UUID | None = None
    channel: str = Field(default="in_app", pattern="^(in_app|email|webhook)$")
    severity: str = Field(default="info", pattern="^(info|success|warning|critical)$")
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=10_000)
    action_url: str | None = Field(default=None, max_length=2048)


class NotificationResponse(BaseModel):
    id: UUID
    channel: str
    severity: str
    title: str
    body: str
    action_url: str | None
    read_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    category: str
    filename: str
    content_type: str
    byte_size: int
    status: str
    ocr_text: str | None
    fhir_resource_type: str | None
    fhir_resource_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class PaymentIntentCreate(BaseModel):
    amount_cents: int = Field(gt=49, le=100_000_000)
    currency: str = Field(default="usd", min_length=3, max_length=3)
    description: str = Field(min_length=1, max_length=500)
    claim_id: UUID | None = None


class PolicyPurchaseCreate(BaseModel):
    policy_id: UUID
    applicant_details: dict[str, Any] = Field(default_factory=dict)
    loyalty_points: int = Field(default=0, ge=0, le=10_000_000)


class AppointmentBookingCreate(BaseModel):
    slot_id: UUID
    reason: str = Field(min_length=2, max_length=500)
    payment_id: UUID | None = None


class LabBookingCreate(BaseModel):
    slot_id: UUID
    test_code: str = Field(min_length=1, max_length=100)


class SyncRequest(BaseModel):
    patient_reference: str | None = Field(default=None, max_length=255)
    operation: str = Field(default="sync", max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)


class UserStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|suspended|disabled)$")


class SettingUpdate(BaseModel):
    value: dict[str, Any]
    description: str = Field(min_length=1, max_length=500)
