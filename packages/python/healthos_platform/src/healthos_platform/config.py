from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    otel_exporter_otlp_endpoint: str = ""
    otel_trace_sample_ratio: float = Field(default=0.1, ge=0, le=1)

    @model_validator(mode="after")
    def validate_production_baseline(self) -> "BaseServiceSettings":
        if self.environment == Environment.PRODUCTION:
            if self.log_format != LogFormat.JSON:
                raise ValueError("LOG_FORMAT must be json in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is forbidden in production")
        return self
