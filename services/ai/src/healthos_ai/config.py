from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator

from healthos_platform.config import BaseServiceSettings, Environment


class Settings(BaseServiceSettings):
    service_name: str = "healthos-ai"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://healthos:change-me@localhost:5432/healthos"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/1")
    api_service_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    identity_cache_ttl_seconds: int = 5

    litellm_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:4000/v1")
    litellm_master_key: SecretStr = SecretStr("local-litellm-master-key")
    planner_model: str = "healthos-openai"
    router_model: str = "healthos-gemini"
    synthesizer_model: str = "healthos-openai"
    patient_model: str = "healthos-openai"
    insurance_model: str = "healthos-gemini"
    clinical_model: str = "healthos-anthropic"
    administrative_model: str = "healthos-openai"
    infrastructure_model: str = "healthos-anthropic"
    document_model: str = "healthos-gemini"
    embedding_model: str = "healthos-embedding"
    embedding_dimensions: int = 1536
    model_timeout_seconds: float = 120.0
    max_concurrent_team_agents: int = 3
    max_request_characters: int = 30_000

    ai_data_encryption_key: SecretStr = SecretStr("aGVhbHRob3MtbG9jYWwtYWkta2V5LTMyLWJ5dGVzISE=")
    langgraph_aes_key: SecretStr = SecretStr("healthos-local-checkpoint-key-32")
    queue_stream: str = "healthos:ai:runs"
    queue_consumer_group: str = "healthos-ai-workers"
    queue_block_ms: int = 5000
    queue_claim_idle_ms: int = 60_000
    run_event_ttl_seconds: int = 3600

    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mcp_tool_allowlist: list[str] = Field(default_factory=list)

    langsmith_tracing: bool = False
    langsmith_project: str = "healthos"
    otel_exporter_otlp_endpoint: str = ""

    @property
    def psycopg_database_url(self) -> str:
        return self.database_url.get_secret_value().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment == Environment.PRODUCTION:
            protected = {
                "LITELLM_MASTER_KEY": self.litellm_master_key.get_secret_value(),
                "AI_DATA_ENCRYPTION_KEY": self.ai_data_encryption_key.get_secret_value(),
                "LANGGRAPH_AES_KEY": self.langgraph_aes_key.get_secret_value(),
            }
            for name, value in protected.items():
                if "local" in value.lower() or "replace" in value.lower() or len(value) < 24:
                    raise ValueError(f"{name} must be replaced for production")
            if "ssl=require" not in self.database_url.get_secret_value():
                raise ValueError("DATABASE_URL must require TLS in production")
            if not self.redis_url.get_secret_value().startswith("rediss://"):
                raise ValueError("REDIS_URL must use TLS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
