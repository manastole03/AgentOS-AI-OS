from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class JobWatchSourceResponse(BaseModel):
    id: UUID | None = None
    source_type: str
    board_key: str
    company_name: str
    board_url: str
    enabled: bool = True
    initial_sync_completed_at: datetime | None = None
    last_scanned_at: datetime | None = None
    last_error_message: str | None = None


class JobWatchResponse(BaseModel):
    enabled: bool
    email_enabled: bool
    destination_email: str
    check_interval_minutes: int
    titles: list[str]
    sources: list[JobWatchSourceResponse]
    last_scanned_at: datetime | None = None


class JobWatchUpdate(BaseModel):
    enabled: bool | None = None
    email_enabled: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    titles: list[str] | None = None
    source_inputs: list[str] | None = None

    @field_validator("titles")
    @classmethod
    def validate_titles(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("At least one target title is required")
        return cleaned

    @field_validator("source_inputs")
    @classmethod
    def validate_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate source entries are not allowed")
        return cleaned
