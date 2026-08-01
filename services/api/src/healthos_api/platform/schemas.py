from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

DefinitionKind = Literal["module", "form", "dashboard", "workflow", "content"]
DefinitionStatus = Literal["draft", "review", "published", "retired"]


class DefinitionCreate(BaseModel):
    kind: DefinitionKind
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    account_types: list[str] = Field(default_factory=list, max_length=5)
    locale: str = Field(default="en-US", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    presentation: dict[str, Any] = Field(default_factory=dict)
    rules: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    effective_at: datetime | None = None
    tenant_id: UUID | None = None

    @model_validator(mode="after")
    def validate_declarative_content(self) -> "DefinitionCreate":
        encoded_size = len(str(self.schema_)) + len(str(self.presentation)) + len(str(self.rules))
        if encoded_size > 250_000:
            raise ValueError("Definition payload is too large")
        allowed_rule_keys = {"when", "then", "field", "operator", "value", "message"}
        for rule in self.rules:
            if not set(rule).issubset(allowed_rule_keys):
                raise ValueError("Rules may contain only declarative allowlisted keys")
        return self


class DefinitionResponse(BaseModel):
    id: UUID
    tenant_id: UUID | None
    kind: str
    key: str
    version: int
    status: str
    account_types: list[str]
    locale: str
    schema_: dict[str, Any] = Field(serialization_alias="schema")
    presentation: dict[str, Any]
    rules: list[dict[str, Any]]
    effective_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AppManifest(BaseModel):
    tenant_id: UUID
    account_type: str
    locale: str
    generated_at: datetime
    version: str
    modules: list[DefinitionResponse]
    forms: list[DefinitionResponse]
    dashboards: list[DefinitionResponse]
    workflows: list[DefinitionResponse]
    content: list[DefinitionResponse]


class OrganizationResponse(BaseModel):
    id: UUID
    slug: str
    legal_name: str
    organization_type: str
    status: str
    role: str
    is_primary: bool
    permissions: list[str]


class ConsentCreate(BaseModel):
    grantee_user_id: UUID | None = None
    grantee_organization_id: UUID | None = None
    purpose: str = Field(min_length=2, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def exactly_one_grantee(self) -> "ConsentCreate":
        if (self.grantee_user_id is None) == (self.grantee_organization_id is None):
            raise ValueError("Provide exactly one user or organization grantee")
        return self


class ConsentResponse(BaseModel):
    id: UUID
    patient_user_id: UUID
    grantee_user_id: UUID | None
    grantee_organization_id: UUID | None
    purpose: str
    scopes: list[str]
    status: str
    expires_at: datetime | None
    revoked_at: datetime | None
    provenance: dict[str, Any]
    created_at: datetime


class WorkflowStart(BaseModel):
    definition_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    subject_type: str = Field(min_length=1, max_length=64)
    subject_id: UUID
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowTransition(BaseModel):
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{1,99}$")
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class WorkflowResponse(BaseModel):
    id: UUID
    definition_key: str
    definition_version: int
    subject_type: str
    subject_id: UUID
    status: str
    version: int
    context: dict[str, Any]
    available_actions: list[str]
    created_at: datetime
    updated_at: datetime
