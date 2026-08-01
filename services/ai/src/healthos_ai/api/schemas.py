from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from healthos_ai.teams import TeamName


class ExecutionMode(StrEnum):
    SYNC = "sync"
    ASYNC = "async"


class ProviderPreference(StrEnum):
    AUTO = "auto"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class MemoryMode(StrEnum):
    NONE = "none"
    READ = "read"
    READ_WRITE = "read_write"


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=30_000)
    team: TeamName | None = None
    execution_mode: ExecutionMode = ExecutionMode.SYNC
    provider: ProviderPreference = ProviderPreference.AUTO
    memory_mode: MemoryMode = MemoryMode.READ
    thread_id: UUID | None = None


class RunResponse(BaseModel):
    id: UUID
    thread_id: UUID
    status: str
    selected_team: TeamName | None = None
    collaborators: list[TeamName] = Field(default_factory=list)
    response: str | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=1_000_000)
    team: TeamName = TeamName.DOCUMENT_INTELLIGENCE
    source_uri: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    id: UUID
    chunk_count: int
    duplicate: bool = False


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)
    category: str = Field(default="preference", min_length=1, max_length=100)
    team: TeamName
    salience: float = Field(default=1.0, ge=0, le=10)


class MemoryResponse(BaseModel):
    id: UUID
    team: TeamName
    category: str
    content: str
    salience: float
    created_at: datetime


class AgentCatalogEntry(BaseModel):
    team: TeamName
    description: str
    model: str
    specialists: list[str]


class EvidenceCitation(BaseModel):
    source_id: str = Field(min_length=1, max_length=255)
    label: str = Field(min_length=1, max_length=255)
    observed_at: datetime | None = None


class ActionProposalCreate(BaseModel):
    run_id: UUID
    action_type: str = Field(
        pattern=(
            r"^(hold_slot|book|reschedule|cancel_appointment|book_lab_order"
            r"|verify_eligibility|estimate_cost|submit_claim|appeal_claim"
            r"|submit_prior_authorization|purchase_policy|apply_for_policy"
            r"|draft_clinical_document|draft_medical_codes|draft_referral"
            r"|draft_prescription|schedule_medication_reminders"
            r"|acknowledge_lab_result|explain_coverage|redeem_loyalty_points)$"
        )
    )
    arguments: dict[str, Any]
    evidence: list[EvidenceCitation] = Field(min_length=1, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    affected_resources: list[str] = Field(default_factory=list, max_length=100)
    expires_in_seconds: int = Field(default=900, ge=60, le=3600)


class ActionProposalResponse(BaseModel):
    id: UUID
    run_id: UUID
    action_type: str
    risk_level: str
    status: str
    payload_digest: str
    evidence: list[EvidenceCitation]
    warnings: list[str]
    affected_resources: list[str]
    expires_at: datetime
    created_at: datetime
    confirmation_token: str | None = None


class ActionConfirmation(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=255)
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
